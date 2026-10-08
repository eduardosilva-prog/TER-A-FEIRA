import argparse
import contextlib
import datetime as dt
import json
import os
import pathlib
import sys
from .core import DB,load_seed,export as _export,entregar_promo,today,stamp
from .net import HTTP
from .collectors import COLLECTORS
from .agent import extract,review

ROOT=pathlib.Path(__file__).resolve().parent.parent

def export(db,config,output):
    # Exporta os CSVs e entrega ocorrencias.csv na entrada do painel Promo (config 'promo_entrada').
    res=_export(db,config,output)
    res['promo']=entregar_promo(output,config,ROOT)
    return res

def dotenv(path):
    if not path.exists():return
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        line=line.strip()
        if line and not line.startswith('#') and '=' in line:
            k,v=line.split('=',1)
            if k.strip() in ['OPENAI_API_KEY','OPENAI_MODEL']:os.environ.setdefault(k.strip(),v.strip().strip('"').strip("'"))

@contextlib.contextmanager
def lock(root):
    # Lock do SO, liberado automaticamente mesmo se o processo cair.
    path=pathlib.Path(root)/'pipeline.lock';path.parent.mkdir(parents=True,exist_ok=True)
    f=path.open('a+b');f.seek(0);f.write(b'0');f.flush();f.seek(0)
    try:
        if os.name=='nt':
            import msvcrt
            msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(f.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
    except (OSError,BlockingIOError):
        f.close();raise RuntimeError('Outra execução está ativa neste diretório de estado')
    try:yield
    finally:f.close()

def collect(db,http,config,start,end,sources):
    errors=[]
    for source in sources:
        try:
            with db.run(source) as stats:
                stats.update(inserted=0,updated=0,unchanged=0,missing_files=0,empty_files=0)
                for r,text in COLLECTORS[source](http,config,start,end):
                    if isinstance(r,tuple):
                        if r[0]=='missing':stats['missing_files']+=1;continue
                        if r[0]=='empty':stats['empty_files']+=1;continue
                        _,url,s,e,items=r
                        # Só remove depois de download/parsing bem-sucedidos; 404 preserva histórico.
                        db.cx.execute('DELETE FROM records WHERE source=? AND day BETWEEN ? AND ? AND json_extract(data,\'$.Fonte\')=?',('openfootball',s,e,url))
                        for item in items:stats[db.upsert(item,source)]+=1
                    else:
                        stats[db.upsert(r,source)]+=1
                        if text is not None:db.document(r['ID'],r,text)
                # Zero resultados é sinalizado para revisão, não causa exclusão em massa.
                stats['zero_records']=not (stats['inserted']+stats['updated']+stats['unchanged'])
            print(source,json.dumps(stats,ensure_ascii=False))
        except Exception as exc:
            errors.append(source);print('Fonte falhou; alterações desta fonte revertidas:',source,type(exc).__name__,str(exc)[:180],file=sys.stderr)
    return errors

def main(argv=None):
    p=argparse.ArgumentParser(description='Agente de cronologia com GPT mini')
    p.add_argument('--config',default=str(ROOT/'config/settings.json'))
    p.add_argument('--state',default=str(ROOT/'state'))
    p.add_argument('--output',default=str(ROOT/'exports'))
    sub=p.add_subparsers(dest='command',required=True)
    init=sub.add_parser('init');init.add_argument('--seed',default=str(ROOT/'seed/Ocorrencias_2024_2026.csv'))
    for name in ['backfill','update']:
        s=sub.add_parser(name);s.add_argument('--start');s.add_argument('--end')
        s.add_argument('--sources',nargs='+',choices=list(COLLECTORS));s.add_argument('--with-ai',action='store_true')
        s.add_argument('--limit',type=int)
    ai=sub.add_parser('extract');ai.add_argument('--limit',type=int)
    rev=sub.add_parser('review');rev.add_argument('--id',required=True);rev.add_argument('--decision',choices=['approved','rejected'],required=True);rev.add_argument('--reviewer',required=True)
    sub.add_parser('export');sub.add_parser('status')
    imp=sub.add_parser('import-csv');imp.add_argument('file')
    args=p.parse_args(argv);dotenv(ROOT/'.env');config=json.loads(pathlib.Path(args.config).read_text())
    if getattr(args,'limit',None) is not None and args.limit<1:raise ValueError('--limit deve ser positivo')
    if config['llm']['daily_call_limit']<1 or config['llm']['max_documents_per_run']<1:raise ValueError('Limites de IA devem ser positivos')
    for k in ['start_date','end_date']:dt.date.fromisoformat(config[k])
    if config['start_date']>config['end_date']:raise ValueError('Intervalo configurado inválido')
    with lock(args.state):
        db=DB(args.state);http=HTTP(pathlib.Path(args.state)/'raw',config['request_timeout'])
        try:
            if args.command in ['init','import-csv']:
                with db.run('seed' if args.command=='init' else 'manual-import') as stats:
                    stats.update(load_seed(db,args.seed if args.command=='init' else args.file))
                print(stats);print(export(db,config,args.output))
            elif args.command in ['backfill','update']:
                full=args.command=='backfill'
                default_start=config['start_date'] if full else max(config['start_date'],(today(config)-dt.timedelta(days=config['overlap_days'])).isoformat())
                start=args.start or default_start;end=args.end or config['end_date']
                dt.date.fromisoformat(start);dt.date.fromisoformat(end)
                if start>end:raise ValueError('Intervalo de coleta invertido')
                errors=collect(db,http,config,start,end,args.sources or config['sources'])
                if args.with_ai:
                    with db.run('gpt-mini') as stats:
                        stats.update(extract(db,http,config,args.limit))
                    print('GPT mini',stats)
                    if stats['failed']:errors.append('gpt-mini')
                print(export(db,config,args.output));return 1 if errors else 0
            elif args.command=='extract':
                with db.run('gpt-mini') as stats:stats.update(extract(db,http,config,args.limit))
                print(stats);print(export(db,config,args.output));return 1 if stats['failed'] else 0
            elif args.command=='review':
                review(db,config,args.id,args.decision,args.reviewer);print(export(db,config,args.output))
            elif args.command=='export':print(export(db,config,args.output))
            elif args.command=='status':
                print(json.dumps({'registros':db.cx.execute('SELECT count(*) FROM records').fetchone()[0],
                  'documentos':db.cx.execute('SELECT count(*) FROM documents').fetchone()[0],
                  'pendentes':db.cx.execute("SELECT count(*) FROM candidates WHERE decision='pending'").fetchone()[0],
                  'ultimas_execucoes':[dict(x) for x in db.cx.execute('SELECT * FROM runs ORDER BY started_at DESC LIMIT 12')],
                  'uso_gpt':[dict(x) for x in db.cx.execute('SELECT day,model,count(*) AS chamadas,sum(input_tokens) AS input_tokens,sum(output_tokens) AS output_tokens FROM llm_calls GROUP BY day,model ORDER BY day DESC LIMIT 10')]},ensure_ascii=False,indent=2))
        finally:db.cx.close()
    return 0

if __name__=='__main__':
    try:sys.exit(main())
    except Exception as exc:
        print(type(exc).__name__+': '+str(exc)[:250],file=sys.stderr);sys.exit(1)
