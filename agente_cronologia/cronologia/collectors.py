import datetime as dt
import json
import re
import urllib.error
import urllib.parse
from zoneinfo import ZoneInfo
from .core import record,today

def normalize_pmc(x):
    t=dt.datetime.strptime(x['criado'],'%d/%m/%Y - %H:%M')
    url=x['url'];r=record(t.date().isoformat(),'Publicação',x['titulo'],url,'pmc-'+str(x['id']),
       'Campinas','Publicado',Referencia_data='Data de publicação; não é a data do acontecimento',
       Detalhes='; '.join(s.get('nome','') for s in x.get('secretarias',[])),
       Horario=t.strftime('%H:%M'),Fuso='Horário exibido pelo portal')
    return r,x.get('subtitulo','')+'\nAlterado: '+x.get('alterado','')

def campinas(http,config,start,end):
    for page in range(config['max_pages']):
        data=http.get(f'https://portal-adm.campinas.sp.gov.br/api/busca-noticias?limit=500&page={page}')
        if not isinstance(data.get('results'),list):raise ValueError('Campinas: esquema inesperado')
        items=data['results']
        if not items:return
        days=[]
        for x in items:
            r,text=normalize_pmc(x);days.append(r['Data'])
            if start<=r['Data']<=min(end,today(config).isoformat()):yield r,text
        # Exige página inteira anterior ao corte. A fonte deve permanecer ordenada por criação.
        if max(days)<start:return
    raise RuntimeError('Campinas: max_pages atingido antes do término; aumente o limite')

def ibge(http,config,start,end):
    # Parâmetros desta API usam MM-DD-AAAA, mas a resposta usa DD/MM/AAAA.
    s=dt.date.fromisoformat(start).strftime('%m-%d-%Y')
    end=min(end,today(config).isoformat());e=dt.date.fromisoformat(end).strftime('%m-%d-%Y')
    page=1;seen=set()
    while page<=config['max_pages']:
        p=http.get(f'https://servicodados.ibge.gov.br/api/v3/noticias/?page={page}&de={s}&ate={e}')
        if not isinstance(p.get('items'),list):raise ValueError('IBGE: esquema inesperado')
        items=p['items']
        for x in items:
            day=dt.datetime.strptime(x['data_publicacao'],'%d/%m/%Y %H:%M:%S');key=str(x['id'])
            if key in seen:raise ValueError('IBGE: repetição de ID entre páginas')
            seen.add(key)
            if start<=day.date().isoformat()<=end:
                r=record(day.date().isoformat(),'Publicação',x['titulo'],x['link'],'ibge-'+key,'Brasil — IBGE','Publicado',
                  Referencia_data='Data de publicação; não é a data do acontecimento',
                  Detalhes=x.get('tipo','')+'; '+x.get('editorias',''),Horario=day.strftime('%H:%M'),Fuso='Horário exibido pelo portal')
                yield r,x.get('introducao','')
        total=int(p.get('totalPages',page))
        if page>=total or not items:return
        page+=1
    raise RuntimeError('IBGE: max_pages atingido antes do término')

def normalize_espn(e,name,config):
    c=e['competitions'][0];st=c['status']['type']
    t=dt.datetime.fromisoformat(c['date'].replace('Z','+00:00')).astimezone(ZoneInfo(config['timezone']))
    day=t.date().isoformat();teams={x['homeAway']:x for x in c['competitors']}
    h=teams['home'];a=teams['away'];hn=h['team']['displayName'];an=a['team']['displayName']
    completed=bool(st.get('completed')) and day<=today(config).isoformat()
    status='Concluído' if completed else ('Programado' if day>today(config).isoformat() else 'Sem conclusão confirmada')
    def score(team):return int(team['score']) if completed and str(team.get('score','')).isdigit() else None
    v=c.get('venue',{});url=next((x['href'] for x in e.get('links',[]) if x.get('href','').startswith('https://')),f'https://www.espn.com/soccer/match/_/gameId/{e["id"]}')
    return record(day,'Futebol',hn+' x '+an,url,'espn-'+e['id'],v.get('address',{}).get('country','Internacional'),status,
      Referencia_data='Data da partida no fuso configurado',Competicao=name,Mandante=hn,Visitante=an,
      Gols_mandante=score(h),Gols_visitante=score(a),Horario=t.strftime('%H:%M') if c.get('timeValid',True) else '',
      Fuso=config['timezone'],Local=v.get('fullName',''),Detalhes='Estado na fonte: '+st.get('description','')+'; UTC: '+c['date'])

def espn(http,config,start,end):
    seen=set()
    for year in range(int(start[:4]),int(end[:4])+1):
        for league in config['espn_leagues']:
            url=f'https://site.api.espn.com/apis/site/v2/sports/soccer/{league}/scoreboard?dates={year}&limit=1000'
            p=http.get(url)
            if not isinstance(p.get('events'),list):raise ValueError('ESPN: esquema inesperado')
            if len(p['events'])>=1000:raise ValueError('ESPN: limite de 1000 atingido; cobertura deve ser revisada')
            name=(p.get('leagues') or [{}])[0].get('name',league)
            for e in p['events']:
                if e['id'] in seen:continue
                seen.add(e['id']);r=normalize_espn(e,name,config)
                if start<=r['Data']<=end:yield r,None

def normalize_openfootball(x,name,url,stem,index,config):
    day=x['date'][:10];score=x.get('score',{});ft=score if isinstance(score,list) else score.get('ft')
    future=day>today(config).isoformat()
    if ft is not None and (len(ft)!=2 or any(not isinstance(v,int) or v<0 for v in ft)):raise ValueError('OpenFootball: placar inválido')
    return record(day,'Futebol',x['team1']+' x '+x['team2'],url,f'of-{stem}-{index}','Internacional',
      'Programado' if future else ('Resultado na fonte' if ft is not None else 'Sem resultado confirmado'),
      Referencia_data='Data original da fonte',Competicao=name,Mandante=x['team1'],Visitante=x['team2'],
      Gols_mandante=ft[0] if ft is not None and not future else None,Gols_visitante=ft[1] if ft is not None and not future else None,
      Horario=x.get('time',''),Fuso='Horário original; fuso não informado',Detalhes=x.get('round',''))

def parse_uefa(text,season,url,stem):
    start=int(season[:4]);end=start+1;name=text.splitlines()[0].lstrip('= ');day=None;time='';stage=''
    months=dict(zip(['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'],range(1,13)))
    for i,line in enumerate(text.splitlines()):
        if line.startswith('▪'):stage=line.lstrip('▪ ')
        d=re.match(r'\s+(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun) (\w{3}) (\d{1,2})(?: (20\d{2}))?\s*$',line)
        if d:
            mon=months[d[1]];year=int(d[3]) if d[3] else (start if mon>=7 else end)
            day=f'{year}-{mon:02d}-{int(d[2]):02d}';time='';continue
        if not day or ' v ' not in line:continue
        t=re.match(r'\s*(\d{2}:\d{2})\s+',line)
        if t:time=t[1];line=line[t.end():]
        x=re.match(r'\s*(.*?)\s+v\s+(.*?)\s+(\d+)-(\d+)(.*)$',line)
        if not x:continue
        yield record(day,'Futebol',x[1]+' x '+x[2],url,f'of-{stem}-{i}','Internacional','Resultado na fonte',
          Referencia_data='Data original da fonte',Competicao=name,Mandante=x[1],Visitante=x[2],
          Gols_mandante=int(x[3]) if 'pen.' not in x[5] else None,Gols_visitante=int(x[4]) if 'pen.' not in x[5] else None,
          Horario=time,Fuso='Horário original; fuso não informado',Detalhes=stage+'; placar original: '+x[3]+'-'+x[4]+x[5])

def openfootball(http,config,start,end):
    # O repositório usa índice/linha como identidade; refazemos cada arquivo atomicamente.
    for year in range(int(start[:4])-1,int(end[:4])+1):
        season=f'{year}-{str(year+1)[2:]}'
        files=[]
        for league in config['openfootball_leagues']:
            files.append((f'https://raw.githubusercontent.com/openfootball/football.json/master/{season}/{league}.json',season+'__'+league,'json'))
        if year>=int(start[:4]):
            for league in config.get('openfootball_calendar_leagues',[]):
                files.append((f'https://raw.githubusercontent.com/openfootball/football.json/master/{year}/{league}.json',str(year)+'__'+league,'json'))
        for code in ['cl','clq','el','elq','conf','confq']:
            files.append((f'https://raw.githubusercontent.com/openfootball/champions-league/master/{season}/{code}.txt',season+'__'+code,'text'))
        for url,stem,fmt in files:
            try:p=http.get(url,fmt)
            except urllib.error.HTTPError as exc:
                if exc.code==404:
                    yield ('missing',url),None;continue
                raise
            if fmt=='json':
                if not isinstance(p.get('matches'),list):raise ValueError('OpenFootball: esquema inesperado')
                records=[normalize_openfootball(x,p.get('name',stem),url,stem,i,config) for i,x in enumerate(p['matches']) if x.get('date')]
            else:records=list(parse_uefa(p,season,url,stem))
            if not records:
                yield ('empty',url),None;continue
            filtered=[]
            for r in records:
                if start<=r['Data']<=end:
                    if r['Data']>today(config).isoformat():
                        r['Status']='Programado';r['Gols_mandante']=r['Gols_visitante']=None
                    filtered.append(r)
            # Não mesclar índices antigos com os novos se o arquivo foi reorganizado.
            yield ('replace_file',url,start,end,filtered),None

COLLECTORS={'campinas':campinas,'ibge':ibge,'espn':espn,'openfootball':openfootball}
