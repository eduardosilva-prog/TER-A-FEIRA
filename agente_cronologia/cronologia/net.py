import gzip
import hashlib
import json
import pathlib
import time
import urllib.error
import urllib.parse
import urllib.request

HOSTS={'portal-adm.campinas.sp.gov.br','portal-api.campinas.sp.gov.br','campinas.sp.gov.br',
       'www.campinas.sp.gov.br','servicodados.ibge.gov.br','agenciadenoticias.ibge.gov.br',
       'www.ibge.gov.br','site.api.espn.com','raw.githubusercontent.com','api.openai.com'}

def allowed(url):
    p=urllib.parse.urlparse(url)
    if p.scheme not in ('http','https') or p.hostname not in HOSTS or p.username or p.password or p.port not in (None,80,443):
        raise ValueError('URL fora das fontes permitidas')

class SafeRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        allowed(newurl)
        if req.has_header('Authorization') and (urllib.parse.urlparse(req.full_url).hostname!=urllib.parse.urlparse(newurl).hostname or urllib.parse.urlparse(newurl).scheme!='https'):
            raise ValueError('Redirecionamento autenticado bloqueado')
        return super().redirect_request(req,fp,code,msg,headers,newurl)

class HTTP:
    def __init__(self,root,timeout=40):
        self.root=pathlib.Path(root);self.root.mkdir(parents=True,exist_ok=True)
        self.timeout=timeout;self.opener=urllib.request.build_opener(SafeRedirect)

    def get(self,url,fmt='json'):
        allowed(url)
        for attempt in range(3):
            try:
                req=urllib.request.Request(url,headers={'User-Agent':'CronologiaAgent/1.0','Accept-Encoding':'gzip'})
                with self.opener.open(req,timeout=self.timeout) as resp:
                    data=resp.read(30*1024*1024+1)
                if len(data)>30*1024*1024:raise ValueError('Resposta excedeu 30 MB')
                if data[:2]==b'\x1f\x8b':
                    # Descompressão com limite para não aceitar payload expansivo.
                    import io
                    with gzip.GzipFile(fileobj=io.BytesIO(data)) as gz:data=gz.read(30*1024*1024+1)
                    if len(data)>30*1024*1024:raise ValueError('Resposta descomprimida excedeu 30 MB')
                text=data.decode('utf-8-sig',errors='replace')
                result=json.loads(text) if fmt=='json' else text
                key=hashlib.sha256(url.encode()).hexdigest()
                (self.root/(key+'.'+('json' if fmt=='json' else 'txt'))).write_text(text,encoding='utf8')
                (self.root/(key+'.meta.json')).write_text(json.dumps({'url':url,'sha256':hashlib.sha256(data).hexdigest(),'fetched_at':__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()}))
                time.sleep(.15);return result
            except urllib.error.HTTPError as exc:
                if exc.code not in (429,500,502,503,504) or attempt==2:raise
            except (TimeoutError,urllib.error.URLError):
                if attempt==2:raise
            time.sleep(2**attempt)
        raise RuntimeError('Falha de coleta')
