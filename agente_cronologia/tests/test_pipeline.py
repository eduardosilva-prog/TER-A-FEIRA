import copy
import datetime as dt
import json
import pathlib
import tempfile
import unittest
from unittest.mock import patch
from cronologia.core import DB,record,export,load_seed,today,relevante
from cronologia.collectors import normalize_pmc,normalize_espn,normalize_openfootball,parse_uefa,ibge,campinas
from cronologia.agent import validate_events,extract,review,response_payload
from cronologia.agent import call_openai
from cronologia.net import allowed
from cronologia.__main__ import collect,lock

ROOT=pathlib.Path(__file__).resolve().parent.parent
CFG=json.loads((ROOT/'config/settings.json').read_text())

class FakeHTTP:
    def __init__(self,items):self.items=iter(items);self.urls=[]
    def get(self,url,fmt='json'):self.urls.append(url);return next(self.items)

class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.db=DB(self.tmp.name);self.cfg=copy.deepcopy(CFG)
    def tearDown(self):self.db.cx.close();self.tmp.cleanup()
    def item(self):return record('2026-10-07','Publicação','Evento','https://campinas.sp.gov.br/a','pmc-123','Campinas','Publicado')
    def doc(self):return {'id':'pmc-123','title':'Evento','text':'O encontro será em 15/10/2026, em Campinas.','published_at':'2026-10-07','url':'https://campinas.sp.gov.br/a','scope':'Campinas'}
    def result(self):return {'events':[{'title':'Encontro','start_date':'2026-10-15','end_date':None,'location':'Campinas','category':'Cultura','event_status':'announced','evidence':'O encontro será em 15/10/2026, em Campinas.','confidence':.95}]}
    def test_upsert_idempotent(self):
        r=self.item();self.assertEqual(self.db.upsert(r,'campinas'),'inserted');self.assertEqual(self.db.upsert(r,'campinas'),'unchanged')
        r['Titulo']='Corrigido';self.assertEqual(self.db.upsert(r,'campinas'),'updated');self.assertEqual(self.db.cx.execute('SELECT count(*) FROM records').fetchone()[0],1)
    def test_filtro_do_painel(self):
        jogo=lambda comp,m,v:record('2026-10-12','Futebol',m+' x '+v,'https://espn.com/x','espn-1','Brazil','Programado',Competicao=comp,Mandante=m,Visitante=v)
        self.assertTrue(relevante(jogo('Brazilian Serie B','Ponte Preta','Guarani'),self.cfg))
        self.assertTrue(relevante(jogo("Women's International Friendly",'Brazil','Argentina'),self.cfg))
        self.assertFalse(relevante(jogo('English Premier League 2025/26','Arsenal','Chelsea'),self.cfg))
        self.assertFalse(relevante(self.item(),self.cfg))  # publicação
        self.assertTrue(relevante(record('2026-10-12','Feriado nacional','N. Sra. Aparecida','https://gov.br','cur-1','Brasil'),self.cfg))
        self.assertTrue(relevante(self.item(),{k:v for k,v in self.cfg.items() if k!='export_filtro'}))
    def test_match_moved_updates_same_id(self):
        r=self.item();r['Tipo']='Futebol';self.db.upsert(r,'espn');r['Data']='2026-10-20';self.db.upsert(r,'espn')
        self.assertEqual(self.db.cx.execute('SELECT day FROM records').fetchone()[0],'2026-10-20')
    def test_source_rollback(self):
        self.db.cx.commit()
        def bad(*args):yield self.item(),None;raise ValueError('broken')
        with patch('cronologia.__main__.COLLECTORS',{'campinas':bad}):self.assertEqual(collect(self.db,None,self.cfg,'2024-01-01','2026-12-31',['campinas']),['campinas'])
        self.assertEqual(self.db.cx.execute('SELECT count(*) FROM records').fetchone()[0],0)
        self.assertEqual(self.db.cx.execute('SELECT status FROM runs').fetchone()[0],'failed')
    def test_calendar_includes_leap_day_and_empty_days(self):
        result=export(self.db,self.cfg,pathlib.Path(self.tmp.name)/'out');self.assertEqual(result['dias'],1096)
        self.assertIn('2024-02-29',(pathlib.Path(self.tmp.name)/'out/calendario.csv').read_text(encoding='utf-8-sig'))
    def test_pmc_date_is_publication(self):
        r,text=normalize_pmc({'id':'1','titulo':'Domingo tem evento','criado':'08/10/2026 - 13:15','url':'https://campinas.sp.gov.br/a'})
        self.assertEqual(r['Data'],'2026-10-08');self.assertIn('publicação',r['Referencia_data'])
    def test_pmc_page_limit_fails_not_silent_truncation(self):
        self.cfg['max_pages']=1
        h=FakeHTTP([{'results':[{'id':'1','titulo':'A','criado':'08/10/2026 - 13:15','url':'https://campinas.sp.gov.br/a'}]}])
        with self.assertRaises(RuntimeError):list(campinas(h,self.cfg,'2024-01-01','2026-12-31'))
    def test_ibge_dd_mm_and_pagination(self):
        x={'id':1,'titulo':'A','data_publicacao':'30/09/2026 09:00:00','link':'https://agenciadenoticias.ibge.gov.br/a'}
        h=FakeHTTP([{'items':[x],'totalPages':2},{'items':[],'totalPages':2}]);rr=list(ibge(h,self.cfg,'2026-09-01','2026-10-08'))
        self.assertEqual(rr[0][0]['Data'],'2026-09-30');self.assertEqual(len(h.urls),2)
        self.assertIn('de=09-01-2026',h.urls[0]);self.assertIn('ate=10-08-2026',h.urls[0])
    def test_ibge_repeated_page_rejected(self):
        x={'id':1,'titulo':'A','data_publicacao':'30/09/2026 09:00:00','link':'https://agenciadenoticias.ibge.gov.br/a'}
        h=FakeHTTP([{'items':[x],'totalPages':2},{'items':[x],'totalPages':2}])
        with self.assertRaises(ValueError):list(ibge(h,self.cfg,'2026-09-01','2026-10-08'))
    def match(self,date,done=False):
        return {'id':'1','competitions':[{'date':date,'status':{'type':{'completed':done,'description':'FT' if done else 'Scheduled'}},'competitors':[{'homeAway':'away','score':'0','team':{'displayName':'B'}},{'homeAway':'home','score':'2','team':{'displayName':'A'}}]}]}
    def test_espn_utc_crosses_day_and_team_order(self):
        r=normalize_espn(self.match('2024-01-02T01:00Z',True),'Liga',self.cfg)
        self.assertEqual(r['Data'],'2024-01-01');self.assertEqual(r['Mandante'],'A');self.assertEqual(r['Gols_mandante'],2)
    def test_future_score_is_not_result(self):
        with patch('cronologia.collectors.today',return_value=dt.date(2026,10,8)):
            r=normalize_espn(self.match('2026-12-01T20:00Z',True),'Liga',self.cfg)
        self.assertIsNone(r['Gols_mandante']);self.assertEqual(r['Status'],'Programado')
    def test_unfinished_zero_is_not_result(self):
        r=normalize_espn(self.match('2024-01-01T20:00Z'),'Liga',self.cfg);self.assertIsNone(r['Gols_visitante'])
    def test_openfootball_two_score_formats(self):
        for score in ([0,0],{'ft':[0,0]}):
            r=normalize_openfootball({'date':'2024-01-01','team1':'A','team2':'B','score':score},'Liga','https://example.org/a','s',0,self.cfg)
            self.assertEqual(r['Gols_mandante'],0)
    def test_uefa_year_rollover_and_penalties(self):
        t='= Champions\n  Tue Dec 12 2023\n    21:00 A v B 2-0\n  Tue Jan 9\n    21:00 A v B 4-3 pen. (1-1)\n'
        rr=list(parse_uefa(t,'2023-24','https://example.org/a','s'));self.assertEqual(rr[1]['Data'],'2024-01-09');self.assertIsNone(rr[1]['Gols_mandante'])
    def test_schema_payload(self):
        p=response_payload(self.doc(),self.cfg['llm']);self.assertEqual(p['text']['format']['type'],'json_schema');self.assertFalse(p['store'])
    def test_evidence_must_exist(self):
        r=self.result();r['events'][0]['evidence']='Uma data inventada'
        with self.assertRaises(ValueError):validate_events(r,self.doc(),self.cfg)
    def test_invalid_calendar_date_rejected(self):
        r=self.result();r['events'][0]['start_date']='2026-02-30'
        with self.assertRaises(ValueError):validate_events(r,self.doc(),self.cfg)
    def test_confidence_outside_range_rejected(self):
        r=self.result();r['events'][0]['confidence']=1.2
        with self.assertRaises(ValueError):validate_events(r,self.doc(),self.cfg)
    def test_interval_inverted_rejected(self):
        r=self.result();r['events'][0]['end_date']='2026-10-01'
        with self.assertRaises(ValueError):validate_events(r,self.doc(),self.cfg)
    def test_cache_and_review(self):
        r=self.item();self.db.upsert(r,'campinas');self.db.document(r['ID'],r,self.doc()['text']);self.db.cx.commit();self.cfg['llm']['fetch_article']=False
        calls=[]
        def caller(doc,settings):calls.append(doc);return self.result(),{'input_tokens':100,'output_tokens':200}
        self.assertEqual(extract(self.db,None,self.cfg,caller=caller)['events'],1)
        self.assertEqual(extract(self.db,None,self.cfg,caller=caller)['documents'],0);self.assertEqual(len(calls),1)
        self.assertEqual(self.db.cx.execute('SELECT count(*) FROM records').fetchone()[0],1)
        cid=self.db.cx.execute('SELECT id FROM candidates').fetchone()[0];review(self.db,self.cfg,cid,'approved','Analista')
        self.assertEqual(self.db.cx.execute('SELECT count(*) FROM records').fetchone()[0],2)
        review(self.db,self.cfg,cid,'rejected','Analista');self.assertEqual(self.db.cx.execute('SELECT count(*) FROM records').fetchone()[0],1)
    def test_daily_limit_persisted(self):
        self.assertIsNotNone(self.db.reserve_call('2026-10-08','gpt-5-mini',1));self.assertIsNone(self.db.reserve_call('2026-10-08','gpt-5-mini',1))
    def test_untrusted_urls_blocked(self):
        for url in ['http://127.0.0.1/a','file:///etc/passwd','https://api.openai.com@evil.com/','https://campinas.sp.gov.br:444/a']:
            with self.assertRaises(ValueError):allowed(url)
    def test_failed_model_retains_pending_document(self):
        r=self.item();self.db.document(r['ID'],r,self.doc()['text']);self.db.cx.commit();self.cfg['llm']['fetch_article']=False
        def fail(*a):raise TimeoutError('timeout')
        self.assertEqual(extract(self.db,None,self.cfg,caller=fail)['failed'],1)
        self.assertEqual(len(self.db.pending_documents(10,'gpt-5-mini','eventos-v1')),1)
    def test_empty_source_file_does_not_delete_history(self):
        r=self.item();r['ID']='of-a-0';self.db.upsert(r,'openfootball');self.db.cx.commit()
        def empty(*args):yield ('empty',r['Fonte']),None
        with patch('cronologia.__main__.COLLECTORS',{'openfootball':empty}):
            self.assertEqual(collect(self.db,None,self.cfg,'2024-01-01','2026-12-31',['openfootball']),[])
        self.assertEqual(self.db.cx.execute('SELECT count(*) FROM records').fetchone()[0],1)
    def test_seed_import_is_atomic(self):
        import csv
        from cronologia.core import FIELDS
        file=pathlib.Path(self.tmp.name)/'bad.csv';bad=self.item();bad['ID']='bad';bad['Data']='2026-02-30'
        with file.open('w',encoding='utf-8-sig',newline='') as f:
            w=csv.DictWriter(f,fieldnames=FIELDS,delimiter=';');w.writeheader();w.writerows([self.item(),bad])
        with self.assertRaises(ValueError):
            with self.db.run('seed'):load_seed(self.db,file)
        self.assertEqual(self.db.cx.execute('SELECT count(*) FROM records').fetchone()[0],0)
    def mock_response(self,payload):
        import io
        from types import SimpleNamespace
        return SimpleNamespace(open=lambda *a,**kw:io.BytesIO(json.dumps(payload).encode()))
    def test_responses_api_output_parsed_without_real_call(self):
        payload={'status':'completed','output':[{'type':'message','content':[{'type':'output_text','text':json.dumps(self.result())}]}],'usage':{'input_tokens':15,'output_tokens':10}}
        with patch.dict('os.environ',{'OPENAI_API_KEY':'fake-key-for-unit-test'}),patch('urllib.request.build_opener',return_value=self.mock_response(payload)):
            result,usage=call_openai(self.doc(),self.cfg['llm'])
        self.assertEqual(result,self.result());self.assertEqual(usage['input_tokens'],15)
    def test_incomplete_response_is_not_imported(self):
        with patch.dict('os.environ',{'OPENAI_API_KEY':'fake-key-for-unit-test'}),patch('urllib.request.build_opener',return_value=self.mock_response({'status':'incomplete','output':[]})):
            with self.assertRaises(ValueError):call_openai(self.doc(),self.cfg['llm'])
    def test_refusal_response_is_not_imported(self):
        p={'status':'completed','output':[{'content':[{'type':'refusal','refusal':'No'}]}]}
        with patch.dict('os.environ',{'OPENAI_API_KEY':'fake-key-for-unit-test'}),patch('urllib.request.build_opener',return_value=self.mock_response(p)):
            with self.assertRaises(ValueError):call_openai(self.doc(),self.cfg['llm'])

if __name__=='__main__':unittest.main()
