"""OOXML structural/content QA. Visual review and host finalizer remain required."""
import argparse,json,re,sys,zipfile
from pathlib import Path
from collections import Counter
import xml.etree.ElementTree as ET
NS={'p':'http://schemas.openxmlformats.org/presentationml/2006/main','a':'http://schemas.openxmlformats.org/drawingml/2006/main','r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships'}
def norm(t):return re.sub(r'\s+','',str(t))
def inspect(pptx,spec,catalog):
    errors=[];warnings=[];pages=[];font_names=set(); ids=[p.get('id') for p in spec['slides'] if p.get('id')]
    if len(ids)!=len(set(ids)):errors.append('Duplicate page IDs in spec')
    with zipfile.ZipFile(pptx) as z:
      bad=z.testzip()
      if bad:errors.append('Corrupt ZIP entry '+bad)
      root=ET.fromstring(z.read('ppt/presentation.xml'));sz=root.find('p:sldSz',NS);w,h=int(sz.get('cx')),int(sz.get('cy'))
      rels=ET.fromstring(z.read('ppt/_rels/presentation.xml.rels'));targets={r.get('Id'):r.get('Target') for r in rels}
      names=[]
      for slide in root.findall('p:sldIdLst/p:sldId',NS):
        t=targets[slide.get('{'+NS['r']+'}id')];names.append(t.lstrip('/') if t.startswith('/') else 'ppt/'+t)
      if len(names)!=len(spec['slides']):errors.append(f'Slide count {len(names)} != {len(spec["slides"])}')
      for i,name in enumerate(names):
        xml=ET.fromstring(z.read(name));page=spec['slides'][i] if i<len(spec['slides']) else {};texts=[''.join(t.itertext()) for t in xml.findall('.//a:t',NS)];all_text=norm(''.join(texts));missing=[]
        for value in [page.get('title',''),*page.get('slots',{}).values()]:
          if norm(value) and norm(value) not in all_text:missing.append(str(value))
        if missing:errors.append({'page':i+1,'missing_native_text':missing})
        n_chart=len(xml.findall('.//{http://schemas.openxmlformats.org/drawingml/2006/chart}chart'));n_table=len(xml.findall('.//a:tbl',NS));pics=xml.findall('.//p:pic',NS)
        if len(page.get('charts',{}))!=n_chart:errors.append({'page':i+1,'chart_count_mismatch':n_chart})
        if len(page.get('tables',{}))!=n_table:errors.append({'page':i+1,'table_count_mismatch':n_table})
        text_boxes=[]
        for sp in xml.findall('.//p:sp',NS)+pics+xml.findall('.//p:graphicFrame',NS):
          xf=sp.find('p:spPr/a:xfrm',NS)
          if xf is None:xf=sp.find('p:xfrm',NS)
          if xf is None:continue
          off,ext=xf.find('a:off',NS),xf.find('a:ext',NS)
          if off is None or ext is None:continue
          x,y,cx,cy=[int(v) for v in [off.get('x','0'),off.get('y','0'),ext.get('cx','0'),ext.get('cy','0')]]
          if x<-9525 or y<-9525 or x+cx>w+9525 or y+cy>h+9525:errors.append({'page':i+1,'out_of_bounds':[x,y,cx,cy]})
          if sp.tag.endswith('pic') and cx*cy>w*h*.85:errors.append({'page':i+1,'near_full_slide_picture':True})
          text=''.join(t.text or '' for t in sp.findall('.//a:t',NS))
          if text and sp.tag.endswith('sp'):text_boxes.append((x,y,cx,cy,text))
          for latin in sp.findall('.//a:latin',NS):
            if latin.get('typeface'):font_names.add(latin.get('typeface'))
        for a in range(len(text_boxes)):
          for b in range(a+1,len(text_boxes)):
            xa,ya,wa,ha,ta=text_boxes[a];xb,yb,wb,hb,tb=text_boxes[b];ix=max(0,min(xa+wa,xb+wb)-max(xa,xb));iy=max(0,min(ya+ha,yb+hb)-max(ya,yb))
            if ix*iy>min(wa*ha,wb*hb)*.08:errors.append({'page':i+1,'text_box_overlap':[ta[:35],tb[:35]]})
        for tab in xml.findall('.//a:tbl',NS):
          actual=[[norm(''.join(t.text or '' for t in cell.findall('.//a:t',NS))) for cell in row.findall('a:tc',NS)] for row in tab.findall('a:tr',NS)]
          expected=list(page.get('tables',{}).values())
          if expected and actual not in [[[norm(v) for v in row] for row in matrix] for matrix in expected]:errors.append({'page':i+1,'table_data_mismatch':True})
        pages.append({'page':i+1,'native_text_runs':len(texts),'native_text_boxes':len(text_boxes),'native_charts':n_chart,'native_tables':n_table,'images':len(pics),'layout':page.get('layout')})
      # Validate chart XML cached series values against canonical numeric inputs.
      charts=[n for n in z.namelist() if re.fullmatch(r'ppt/(?:slides/)?charts/chart\d+.xml',n)];chart_values=[];cns={'c':'http://schemas.openxmlformats.org/drawingml/2006/chart'}
      for name in charts:
        tree=ET.fromstring(z.read(name));series=[]
        for ser in tree.findall('.//c:ser',cns):
          val=ser.find('c:val',cns)
          if val is not None:series.append([float(p.find('c:v',cns).text) for p in val.findall('.//c:pt',cns)])
        chart_values.append(series)
      expected_charts=[[s['values'] for s in data['series']] for p in spec['slides'] for data in p.get('charts',{}).values()]
      for values in expected_charts:
        if values not in chart_values:errors.append({'chart_data_missing_or_mismatch':values})
      media=[n for n in z.namelist() if n.startswith('ppt/media/')]
      expected_font=spec.get('design',{}).get('font')
      if expected_font and expected_font not in font_names:errors.append('Expected font not found: '+expected_font)
    compositions={e['id']:e['composition'] for e in catalog.get('items',[])}
    for i in range(1,len(spec['slides'])):
      a,b=spec['slides'][i-1:i+1]
      if compositions.get(a['layout'])==compositions.get(b['layout']):warnings.append({'page':i+1,'repeated_adjacent_composition':compositions.get(b['layout'])})
    return {'schema_version':1,'passed':not errors,'errors':errors,'warnings':warnings,'slides':pages,'fonts':sorted(font_names),'media_files':len(media),'limitations':['Does not prove visual aesthetics or all text overflow; inspect actual rendered slides.','Native chart cached values checked; host chart/workbook validation still required.']}
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--pptx',required=True);ap.add_argument('--spec',required=True);ap.add_argument('--catalog',required=True);ap.add_argument('--out',required=True);a=ap.parse_args();r=inspect(a.pptx,json.loads(Path(a.spec).read_text('utf8')),json.loads(Path(a.catalog).read_text('utf8')));Path(a.out).write_text(json.dumps(r,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps({'passed':r['passed'],'errors':len(r['errors']),'warnings':len(r['warnings']),'slides':len(r['slides'])}));sys.exit(0 if r['passed'] else 1)
if __name__=='__main__':main()
