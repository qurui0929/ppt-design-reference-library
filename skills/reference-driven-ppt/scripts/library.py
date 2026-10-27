"""Small, pinned GitHub reference index + selective, verified offline cache."""
import argparse, hashlib, json, os, sys, tempfile, urllib.error, urllib.parse, urllib.request
from pathlib import Path, PurePosixPath
CONFIG=Path(__file__).resolve().parents[1]/'references'/'library.json'
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def digest(b):return hashlib.sha256(b).hexdigest()
def safe_path(root,rel):
    p=PurePosixPath(rel)
    if p.is_absolute() or '..' in p.parts or '\\' in rel or ':' in rel:raise ValueError('Unsafe cache path')
    return root.joinpath(*p.parts)
def atomic(p,b):
    p.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=p.parent,delete=False) as f:f.write(b);name=f.name
    os.replace(name,p)
def get(cfg,rel,expected):
    repo=cfg['repository'];ref=cfg['ref'];q=urllib.parse.quote(rel,safe='/');last=None
    urls=[f'https://raw.githubusercontent.com/{repo}/{ref}/{q}',f'https://api.github.com/repos/{repo}/contents/{q}?ref={urllib.parse.quote(ref)}']
    for u in urls:
      try:
        headers={'User-Agent':'reference-driven-ppt/1.0','Accept':'application/vnd.github.raw+json'}
        with urllib.request.urlopen(urllib.request.Request(u,headers=headers),timeout=25) as r:b=r.read(32*1024*1024+1)
        if len(b)>32*1024*1024:raise ValueError('Asset exceeds 32 MiB')
        if digest(b)!=expected:raise ValueError('SHA-256 mismatch: '+rel)
        return b
      except (OSError,ValueError) as e:last=e
    raise RuntimeError(f'Cannot fetch verified asset {rel}: {last}')
def sync(cfg,cache,offline=False):
    p=cache/'catalog.json';sha=cfg['catalog_sha256']
    if p.exists() and digest(p.read_bytes())==sha:return read(p)
    if offline:raise RuntimeError('No verified catalog available offline')
    b=get(cfg,cfg['catalog_path'],sha);data=json.loads(b)
    if data.get('schema_version')!=1:raise ValueError('Unsupported catalog schema')
    atomic(p,b);return data
def fetch(cfg,cache,entry,offline=False):
    paths={}
    for role in ['recipe','preview','reference','template','object_map']:
      asset=entry.get(role)
      if not asset:continue
      dest=safe_path(cache,asset['path'])
      if not dest.exists() or digest(dest.read_bytes())!=asset['sha256']:
        if offline:raise RuntimeError('Missing/corrupt offline asset '+asset['path'])
        atomic(dest,get(cfg,asset['path'],asset['sha256']))
      paths[role]=str(dest.resolve())
    return paths
def search(cat,relation,items,chars,limit,exclude):
    hits=[]
    for e in cat['items']:
      if e['id'] in exclude:continue
      if relation and relation not in e['relations']:continue
      low,high=e.get('items_range',[0,100])
      if items is not None and not low<=items<=high:continue
      if chars is not None and chars>e['max_chars']:continue
      score=100-abs((items if items is not None else low)-(low+high)/2)*4
      if chars is not None:score-=max(0,(e['max_chars']-chars)/max(e['max_chars'],1))*8
      if e.get('native_status')=='render_reviewed':score+=5
      hits.append({'id':e['id'],'name':e['name'],'score':round(score,2),'relations':e['relations'],'items_range':[low,high],'max_chars':e['max_chars'],'composition':e['composition'],'review_status':e['review_status'],'native_status':e.get('native_status'),'fit_note':e['fit_note']})
    return sorted(hits,key=lambda e:-e['score'])[:limit]
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--config',default=str(CONFIG));sub=ap.add_subparsers(dest='cmd',required=True)
    for name in ['sync','search','fetch']:
      p=sub.add_parser(name);p.add_argument('--cache',required=True);p.add_argument('--offline',action='store_true')
      if name=='search':p.add_argument('--relation');p.add_argument('--items',type=int);p.add_argument('--chars',type=int);p.add_argument('--limit',type=int,default=5);p.add_argument('--exclude',nargs='*',default=[])
      if name=='fetch':p.add_argument('--ids',nargs='+',required=True)
    a=ap.parse_args();cfg=read(a.config);cache=Path(a.cache);cat=sync(cfg,cache,a.offline)
    if a.cmd=='sync':result={'catalog':str((cache/'catalog.json').resolve()),'version':cat['version'],'items':len(cat['items']),'pinned_ref':cfg['ref']}
    elif a.cmd=='search':result=search(cat,a.relation,a.items,a.chars,a.limit,a.exclude)
    else:
      entries={e['id']:e for e in cat['items']};missing=set(a.ids)-entries.keys()
      if missing:raise ValueError('Unknown IDs: '+','.join(sorted(missing)))
      result={id:fetch(cfg,cache,entries[id],a.offline) for id in a.ids}
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=='__main__':
    try:main()
    except Exception as e:print(json.dumps({'error':str(e)},ensure_ascii=False),file=sys.stderr);sys.exit(1)
