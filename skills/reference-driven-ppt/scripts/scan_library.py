"""Incremental, read-only PPTX inventory; no Office or third-party dependencies."""
import argparse, concurrent.futures, hashlib, json, os, re, time, zipfile
from pathlib import Path
import xml.etree.ElementTree as ET
NS={'p':'http://schemas.openxmlformats.org/presentationml/2006/main','a':'http://schemas.openxmlformats.org/drawingml/2006/main'}
def dump(path,data):
    path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
def inspect_file(args):
    path,root,cache=args; st=path.stat(); key=hashlib.sha256(str(path.relative_to(root)).encode()).hexdigest()[:20]; out=cache/(key+'.json')
    if out.exists():
        old=json.loads(out.read_text(encoding='utf-8'))
        if old.get('size')==st.st_size and old.get('mtime_ns')==st.st_mtime_ns:return old
    result={'id':key,'relative_path':str(path.relative_to(root)),'size':st.st_size,'mtime_ns':st.st_mtime_ns,'status':'ok','slides':[]}
    if path.suffix.lower()!='.pptx':result['status']='unsupported';return result
    try:
      with zipfile.ZipFile(path) as z:
        doc=ET.fromstring(z.read('ppt/presentation.xml')); sz=doc.find('p:sldSz',NS); w,h=int(sz.get('cx')),int(sz.get('cy')); result['aspect']=round(w/h,4)
        names=sorted((n for n in z.namelist() if re.fullmatch(r'ppt/slides/slide\d+.xml',n)),key=lambda n:int(re.search(r'(\d+)\.xml',n).group(1)))
        for sn,name in enumerate(names,1):
          x=ET.fromstring(z.read(name)); texts=[''.join(t.itertext()) for t in x.findall('.//a:t',NS)]; shapes=[]
          for sp in x.findall('.//p:sp',NS)+x.findall('.//p:pic',NS)+x.findall('.//p:graphicFrame',NS):
            xf=sp.find('.//a:xfrm',NS)
            if xf is None:xf=sp.find('p:xfrm',NS)
            if xf is None:continue
            off=xf.find('a:off',NS); ext=xf.find('a:ext',NS)
            if off is None or ext is None:continue
            text=''.join(t.text or '' for t in sp.findall('.//a:t',NS)); kind=sp.tag.split('}')[-1]
            box=[round(int(off.get('x','0'))/w,3),round(int(off.get('y','0'))/h,3),round(int(ext.get('cx','0'))/w,3),round(int(ext.get('cy','0'))/h,3)]
            shapes.append({'kind':kind,'box':box,'chars':len(text),'text':text[:140]})
          n_pic=len(x.findall('.//p:pic',NS)); n_chart=len(x.findall('.//{http://schemas.openxmlformats.org/drawingml/2006/chart}chart')); n_table=len(x.findall('.//a:tbl',NS)); n_line=len(x.findall('.//p:cxnSp',NS)); text=' '.join(texts); chars=len(text)
          lower=(result['relative_path']+' '+text[:280]).lower(); cats=[]
          rules={'process':['流程','步骤','闭环','循环'],'architecture':['架构','体系','层级','支撑','平台'],'timeline':['时间轴','历程','路线图','规划','阶段'],'comparison':['对比','比较','优劣','前后','分析'],'data':['数据','图表','业绩','成果','增长'],'evidence':['图片','照片','案例','展示'],'relationship':['关系','逻辑','关联','循环'],'cover':['封面','目录','章节','过渡']}
          for cat,terms in rules.items():
            if any(t in lower for t in terms):cats.append(cat)
          if n_chart and 'data' not in cats:cats.append('data')
          if n_table and 'comparison' not in cats:cats.append('comparison')
          if n_pic>=2 and 'evidence' not in cats:cats.append('evidence')
          if not cats:cats=['general']
          signature=';'.join(sorted(f"{s['kind']}:{','.join(str(round(v*10)) for v in s['box'])}" for s in shapes))
          result['slides'].append({'slide':sn,'title':text[:100],'chars':chars,'pictures':n_pic,'charts':n_chart,'tables':n_table,'connectors':n_line,'objects':len(shapes),'categories':cats,'classification':'heuristic_unreviewed','layout_hash':hashlib.sha256(signature.encode()).hexdigest()[:16],'shapes':shapes})
        result['slide_count']=len(names)
    except Exception as e:result.update(status='error',error=f'{type(e).__name__}: {e}')
    dump(out,result); return result
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--root',required=True);ap.add_argument('--out',required=True);ap.add_argument('--include',nargs='+',default=None);ap.add_argument('--workers',type=int,default=4);a=ap.parse_args()
    root=Path(a.root);out=Path(a.out);cache=out/'file-cache';cache.mkdir(parents=True,exist_ok=True)
    selected=a.include or [p.name for p in root.iterdir() if p.is_dir()]; files=sorted(p for name in selected for p in (root/name).rglob('*') if p.is_file()); files += ([] if a.include else sorted(p for p in root.iterdir() if p.is_file())); counts={}; summary={'source_root':str(root),'included_folders':selected,'excluded_folders':sorted(p.name for p in root.iterdir() if p.is_dir() and p.name not in selected),'files':len(files),'bytes':sum(p.stat().st_size for p in files),'extensions':{},'decks':[]}; start=time.time()
    for p in files:summary['extensions'][p.suffix.lower()]=summary['extensions'].get(p.suffix.lower(),0)+1
    summary['office_lock_files']=[str(p.relative_to(root)) for p in files if p.name.startswith('~$')]
    pptx=[p for p in files if p.suffix.lower()=='.pptx' and not p.name.startswith('~$')];seen=set();candidates=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=a.workers) as pool:
      for i,d in enumerate(pool.map(inspect_file,[(p,root,cache) for p in pptx]),1):
        summary['decks'].append({k:v for k,v in d.items() if k!='slides'})
        for s in d['slides']:
          for cat in s['categories']:counts[cat]=counts.get(cat,0)+1
          # Select representative structural pages; filename/structure are signals, not aesthetic approval.
          if s['layout_hash'] in seen:continue
          seen.add(s['layout_hash'])
          if 4<=s['objects']<=95 and 12<=s['chars']<=1500 and 1.2<d.get('aspect',0)<2.1:
            candidates.append({'deck_id':d['id'],'relative_path':d['relative_path'],**{k:v for k,v in s.items() if k!='shapes'},'score':(10 if d['relative_path'].startswith('01ppt组件') else 0)+(8 if s['connectors'] else 0)+(8 if s['charts'] or s['tables'] else 0)+min(s['objects'],30)/5-abs(s['chars']-160)/100})
        if i%25==0:print(json.dumps({'processed':i,'total':len(pptx),'seconds':round(time.time()-start)},ensure_ascii=False),flush=True)
    summary.update(slides=sum(d.get('slide_count',0) for d in summary['decks']),unique_layout_signatures=len(seen),category_counts=counts,elapsed_seconds=round(time.time()-start),errors=[d for d in summary['decks'] if d['status']!='ok'])
    dump(out/'inventory.json',summary); dump(out/'candidates.json',sorted(candidates,key=lambda x:-x['score']));print(json.dumps({k:v for k,v in summary.items() if k not in ['decks','errors']},ensure_ascii=False),flush=True)
if __name__=='__main__':main()
