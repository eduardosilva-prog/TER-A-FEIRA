import contextlib
import csv
import datetime as dt
import hashlib
import json
import os
import pathlib
import sqlite3
import uuid
from zoneinfo import ZoneInfo

FIELDS = ['Data','Tipo','Titulo','Abrangencia','Status','Referencia_data','Detalhes',
          'Competicao','Mandante','Visitante','Gols_mandante','Gols_visitante',
          'Horario','Fuso','Local','Fonte','ID']

def today(config):
    return dt.datetime.now(ZoneInfo(config['timezone'])).date()

def stamp():
    return dt.datetime.now(dt.timezone.utc).isoformat()

def digest(obj):
    return hashlib.sha256(json.dumps(obj, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

def record(day, kind, title, source, id_, scope='', status='', **kw):
    r = dict.fromkeys(FIELDS, '')
    r.update(Data=day, Tipo=kind, Titulo=title, Fonte=source, ID=id_, Abrangencia=scope, Status=status)
    r.update(kw)
    return r

def validate(r):
    dt.date.fromisoformat(r['Data'])
    if not r['ID'] or not r['Fonte'] or not r['Titulo']:
        raise ValueError('Registro sem ID, fonte ou título')
    if not r['Fonte'].startswith(('http://', 'https://')):
        raise ValueError('Fonte deve ser URL HTTP(S)')
    for col in ['Gols_mandante','Gols_visitante']:
        v=r.get(col)
        if v not in ('',None) and (not str(v).isdigit() or int(v)<0):
            raise ValueError('Placar inválido')

class DB:
    def __init__(self, root):
        self.root=pathlib.Path(root);self.root.mkdir(parents=True,exist_ok=True)
        self.cx=sqlite3.connect(self.root/'chronology.sqlite',timeout=30)
        self.cx.row_factory=sqlite3.Row
        self.cx.executescript('''
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS records(
          id TEXT PRIMARY KEY,source TEXT NOT NULL,day TEXT NOT NULL,kind TEXT NOT NULL,
          title TEXT NOT NULL,data TEXT NOT NULL,hash TEXT NOT NULL,revision INTEGER NOT NULL,
          first_seen TEXT NOT NULL,last_seen TEXT NOT NULL,updated_at TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS records_day ON records(day,kind);
        CREATE TABLE IF NOT EXISTS documents(
          id TEXT PRIMARY KEY,record_id TEXT NOT NULL,data TEXT NOT NULL,hash TEXT NOT NULL,
          updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS processed(
          doc_id TEXT PRIMARY KEY,hash TEXT NOT NULL,model TEXT NOT NULL,prompt TEXT NOT NULL,
          result TEXT NOT NULL,processed_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS candidates(
          id TEXT PRIMARY KEY,doc_id TEXT NOT NULL,data TEXT NOT NULL,decision TEXT NOT NULL,
          reviewer TEXT,reviewed_at TEXT,updated_at TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS runs(
          id TEXT PRIMARY KEY,source TEXT NOT NULL,started_at TEXT NOT NULL,ended_at TEXT,
          status TEXT NOT NULL,stats TEXT,error TEXT);
        CREATE TABLE IF NOT EXISTS llm_calls(
          id TEXT PRIMARY KEY,day TEXT NOT NULL,model TEXT NOT NULL,status TEXT NOT NULL,
          input_tokens INTEGER,output_tokens INTEGER,created_at TEXT NOT NULL);
        ''')
        self.cx.commit()

    def upsert(self,r,source):
        validate(r);encoded=json.dumps(r,ensure_ascii=False,sort_keys=True);hash_=digest(r);now=stamp()
        old=self.cx.execute('SELECT hash FROM records WHERE id=?',(r['ID'],)).fetchone()
        if old and old['hash']==hash_:
            self.cx.execute('UPDATE records SET last_seen=? WHERE id=?',(now,r['ID']));return 'unchanged'
        self.cx.execute('''INSERT INTO records VALUES(?,?,?,?,?,?,?,1,?,?,?)
          ON CONFLICT(id) DO UPDATE SET source=excluded.source,day=excluded.day,kind=excluded.kind,
          title=excluded.title,data=excluded.data,hash=excluded.hash,revision=records.revision+1,
          last_seen=excluded.last_seen,updated_at=excluded.updated_at''',
          (r['ID'],source,r['Data'],r['Tipo'],r['Titulo'],encoded,hash_,now,now,now))
        return 'updated' if old else 'inserted'

    def document(self,id_,r,text):
        obj={'id':id_,'published_at':r['Data'],'title':r['Titulo'],'url':r['Fonte'],
             'scope':r['Abrangencia'],'text':text}
        self.cx.execute('''INSERT INTO documents VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE
          SET data=excluded.data,hash=excluded.hash,updated_at=excluded.updated_at''',
          (id_,r['ID'],json.dumps(obj,ensure_ascii=False),digest(obj),stamp()))

    def pending_documents(self,limit,model,prompt):
        return self.cx.execute('''SELECT d.* FROM documents d LEFT JOIN processed p ON d.id=p.doc_id
          WHERE p.doc_id IS NULL OR p.hash!=d.hash OR p.model!=? OR p.prompt!=?
          ORDER BY d.updated_at DESC,d.id LIMIT ?''',(model,prompt,limit)).fetchall()

    @contextlib.contextmanager
    def run(self,source):
        rid=uuid.uuid4().hex;stats={}
        self.cx.execute('INSERT INTO runs(id,source,started_at,status) VALUES(?,?,?,?)',
                        (rid,source,stamp(),'running'));self.cx.commit()
        try:
            yield stats
            self.cx.commit()
        except Exception as exc:
            self.cx.rollback()
            self.cx.execute('UPDATE runs SET ended_at=?,status=?,stats=?,error=? WHERE id=?',
                (stamp(),'failed',json.dumps(stats),type(exc).__name__+': '+str(exc)[:500],rid))
            self.cx.commit();raise
        else:
            self.cx.execute('UPDATE runs SET ended_at=?,status=?,stats=? WHERE id=?',
                           (stamp(),'success',json.dumps(stats),rid));self.cx.commit()

    def reserve_call(self,day,model,limit):
        # Reserva persistente antes da chamada: timeout também consome o limite local.
        self.cx.execute('BEGIN IMMEDIATE')
        n=self.cx.execute('SELECT count(*) FROM llm_calls WHERE day=?',(day,)).fetchone()[0]
        if n>=limit:
            self.cx.rollback();return None
        rid=uuid.uuid4().hex
        self.cx.execute('INSERT INTO llm_calls(id,day,model,status,created_at) VALUES(?,?,?,?,?)',
                        (rid,day,model,'reserved',stamp()));self.cx.commit();return rid

def source_of_id(id_):
    if id_.startswith('pmc-'):return 'campinas'
    if id_.startswith('ibge-'):return 'ibge'
    if id_.startswith('espn-'):return 'espn'
    if id_.startswith('of-'):return 'openfootball'
    return 'curadoria'

def load_seed(db,path):
    counts={}
    with open(path,encoding='utf-8-sig',newline='') as f:
        for r in csv.DictReader(f,delimiter=';'):
            for key in ['Gols_mandante','Gols_visitante']:
                r[key]=int(r[key]) if r[key] else None
            result=db.upsert(r,source_of_id(r['ID']));counts[result]=counts.get(result,0)+1
    return counts

def relevante(r,config):
    # Sem 'export_filtro' exporta tudo. Com ele, só o que o painel Promo usa:
    # datas/acontecimentos e futebol de competições brasileiras ou da Seleção.
    f=config.get('export_filtro')
    if not f:return True
    if r['Tipo']=='Futebol':
        return r['Competicao'] in f['competicoes_futebol'] or f.get('selecao') in (r['Mandante'],r['Visitante'])
    return r['Tipo'] in f['tipos']

def entregar_promo(out,config,root):
    # Copia ocorrencias.csv para a entrada do painel; a ingestão ignora conteúdo repetido.
    destino=config.get('promo_entrada')
    if not destino:return None
    destino=(pathlib.Path(root)/destino).resolve()
    if not destino.parent.exists():return None
    import shutil
    shutil.copyfile(pathlib.Path(out)/'ocorrencias.csv',destino.with_suffix('.tmp'));os.replace(destino.with_suffix('.tmp'),destino)
    return str(destino)

def export(db,config,path):
    import collections
    out=pathlib.Path(path);out.mkdir(parents=True,exist_ok=True);cut=today(config).isoformat()
    rows=[]
    for x in db.cx.execute('SELECT data FROM records ORDER BY day,kind,title'):
        r=json.loads(x[0])
        if config['start_date']<=r['Data']<=config['end_date'] and relevante(r,config):
            if r['Data']>cut and r['Tipo']=='Futebol':
                r['Status']='Programado';r['Gols_mandante']=r['Gols_visitante']=None
            rows.append(r)
    def write(name,items,fields):
        tmp=out/(name+'.tmp')
        with tmp.open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=fields,delimiter=';',extrasaction='ignore');w.writeheader()
            for r in items:
                # Protege abertura dos CSV no Excel de valores interpretados como fórmulas.
                w.writerow({k:("'"+v if isinstance(v,str) and v.startswith(('=','+','-','@')) else v) for k,v in r.items()})
        os.replace(tmp,out/name)
    write('ocorrencias.csv',rows,FIELDS)
    by=collections.defaultdict(list)
    for r in rows:by[r['Data']].append(r)
    days=[];d=dt.date.fromisoformat(config['start_date']);end=dt.date.fromisoformat(config['end_date'])
    week=['segunda-feira','terça-feira','quarta-feira','quinta-feira','sexta-feira','sábado','domingo']
    while d<=end:
        key=d.isoformat();rr=by[key];cnt=collections.Counter(r['Tipo'] for r in rr)
        days.append({'Data':key,'Ano':d.year,'Mes':d.month,'Dia_semana':week[d.weekday()],
          'Semana_ISO':d.isocalendar().week,'Fim_de_semana':d.weekday()>4,
          'Periodo':'Futuro' if key>cut else ('Hoje — parcial' if key==cut else 'Histórico'),
          'Feriados':' | '.join(r['Titulo']+' ['+r['Abrangencia']+']' for r in rr if r['Tipo'].startswith('Feriado')),
          'Jogos':cnt['Futebol'],'Publicacoes':cnt['Publicação'],'Acontecimentos':cnt['Acontecimento'],
          'Total_registros':len(rr)})
        d+=dt.timedelta(days=1)
    write('calendario.csv',days,list(days[0]))
    reviews=[]
    for x in db.cx.execute("SELECT * FROM candidates WHERE decision='pending' ORDER BY updated_at DESC"):
        r=json.loads(x['data']);r.update(ID=x['id'],Documento=x['doc_id']);reviews.append(r)
    fields=['ID','Documento','title','start_date','end_date','location','category','event_status','evidence','confidence']
    write('revisao.csv',reviews,fields)
    return {'registros':len(rows),'dias':len(days),'pendentes':len(reviews),'pasta':str(out.resolve())}
