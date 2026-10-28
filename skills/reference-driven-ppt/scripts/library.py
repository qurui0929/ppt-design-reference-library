"""Fetch a lightweight pinned index, search Chinese source names, download chosen originals."""
import argparse,hashlib,json,os,sys,tempfile,urllib.parse,urllib.request
from pathlib import Path,PurePosixPath

CONFIG=Path(__file__).resolve().parents[1]/'references/library.json'
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
    return h.hexdigest()
def download(url,dest,expected,size=None):
    urls=url if isinstance(url,list) else [url]
    errors=[]
    for source in urls:
        try:return download_one(source,dest,expected,size)
        except (OSError,ValueError) as e:errors.append(str(e))
    raise RuntimeError('Unable to fetch verified asset: '+'; '.join(errors))
def download_one(url,dest,expected,size=None):
    dest=Path(dest);dest.parent.mkdir(parents=True,exist_ok=True)
    if dest.exists() and sha(dest)==expected:return str(dest.resolve())
    temp=None
    try:
        request=urllib.request.Request(url,headers={'User-Agent':'reference-driven-ppt/2.0','Accept':'application/octet-stream'})
        with urllib.request.urlopen(request,timeout=120) as r,tempfile.NamedTemporaryFile(dir=dest.parent,delete=False) as f:
            temp=Path(f.name);h=hashlib.sha256();count=0
            for b in iter(lambda:r.read(4*1024*1024),b''):
                f.write(b);h.update(b);count+=len(b)
        if h.hexdigest()!=expected or (size is not None and count!=size):raise ValueError('Downloaded file size or SHA-256 mismatch')
        os.replace(temp,dest);return str(dest.resolve())
    finally:
        if temp and temp.exists():temp.unlink()
def sync(cfg,cache,offline):
    p=cache/'catalog-v2.json'
    if not p.exists() or sha(p)!=cfg['catalog_sha256']:
        if offline:raise ValueError('No verified catalog in offline cache')
        url='https://raw.githubusercontent.com/'+cfg['repository']+'/'+cfg['ref']+'/'+urllib.parse.quote(cfg['catalog_path'],safe='/')
        download(url,p,cfg['catalog_sha256'])
    cat=read(p)
    if cat.get('schema_version')!=2:raise ValueError('Expected original-source library schema 2')
    return cat
def destination(cache,relative):
    p=PurePosixPath(relative)
    if p.is_absolute() or '..' in p.parts or '\\' in relative or ':' in relative:raise ValueError('Unsafe relative path')
    return cache/'originals'/Path(*p.parts)
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--config',default=str(CONFIG));sub=ap.add_subparsers(dest='cmd',required=True)
    for cmd in ['sync','search','fetch']:
        p=sub.add_parser(cmd);p.add_argument('--cache',required=True);p.add_argument('--offline',action='store_true')
        if cmd=='search':p.add_argument('--category',choices=['00模板','01ppt组件','10综合灵感、竞品']);p.add_argument('--query',default='');p.add_argument('--limit',type=int,default=20)
        if cmd=='fetch':p.add_argument('--ids',nargs='+',required=True)
    a=ap.parse_args();cfg=read(a.config);cache=Path(a.cache);cat=sync(cfg,cache,a.offline)
    if a.cmd=='sync':result={'version':cat['version'],'files':len(cat['items']),'catalog':str((cache/'catalog-v2.json').resolve())}
    elif a.cmd=='search':
        terms=a.query.lower().split()
        result=[{k:e[k] for k in ['id','name','relative_path','category','subcategory','bytes','review_status']} for e in cat['items'] if (not a.category or e['category']==a.category) and all(t in e['relative_path'].lower() for t in terms)][:a.limit]
    else:
        entries={e['id']:e for e in cat['items']};result={}
        for id in a.ids:
            if id not in entries:raise ValueError('Unknown source ID: '+id)
            e=entries[id];p=destination(cache,e['relative_path'])
            if a.offline:
                if not p.exists() or sha(p)!=e['sha256']:raise ValueError('Missing or corrupt cached original: '+id)
                result[id]=str(p.resolve())
            else:
                assets=e.get('assets',[])
                if len(assets)<=1:result[id]=download([u for u in [e.get('api_url'),e['url']] if u],p,e['sha256'],e['bytes'])
                else:
                    parts=[Path(download([u for u in [x.get('api_url'),x['url']] if u],cache/'parts'/x['asset_name'],x['sha256'],x['bytes'])) for x in assets]
                    p.parent.mkdir(parents=True,exist_ok=True)
                    with tempfile.NamedTemporaryFile(dir=p.parent,delete=False) as out:
                        tmp=Path(out.name)
                        for part in parts:
                            with part.open('rb') as src:
                                for b in iter(lambda:src.read(4*1024*1024),b''):out.write(b)
                    if sha(tmp)!=e['sha256']:tmp.unlink();raise ValueError('Reassembled original SHA-256 mismatch')
                    os.replace(tmp,p);result[id]=str(p.resolve())
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':
    try:main()
    except Exception as e:print(json.dumps({'error':str(e)},ensure_ascii=False),file=sys.stderr);sys.exit(1)
