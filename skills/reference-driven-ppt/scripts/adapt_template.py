"""Replace explicit native text slots in one-slide PPTX, preserving its layout/media.
Uses only Python stdlib. Does not draw, rasterize, recolor, or invoke Office.
"""
import argparse,copy,hashlib,json,re,sys,zipfile
from pathlib import Path
import xml.etree.ElementTree as ET
NS={'p':'http://schemas.openxmlformats.org/presentationml/2006/main','a':'http://schemas.openxmlformats.org/drawingml/2006/main'}
for prefix,uri in NS.items():ET.register_namespace(prefix,uri)
ET.register_namespace('r','http://schemas.openxmlformats.org/officeDocument/2006/relationships')
def read(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def replace_runs(shape,value):
    body=shape.find('p:txBody',NS)
    if body is None:raise ValueError('Mapped shape has no native text body')
    paragraphs=body.findall('a:p',NS);first=paragraphs[0] if paragraphs else ET.Element('{'+NS['a']+'}p')
    ppr=first.find('a:pPr',NS);rpr=first.find('a:r/a:rPr',NS)
    if rpr is None:rpr=first.find('a:endParaRPr',NS)
    for p in paragraphs:body.remove(p)
    for line in str(value).split('\n'):
      p=ET.SubElement(body,'{'+NS['a']+'}p')
      if ppr is not None:p.append(copy.deepcopy(ppr))
      r=ET.SubElement(p,'{'+NS['a']+'}r')
      if rpr is not None:
        style=copy.deepcopy(rpr);style.tag='{'+NS['a']+'}rPr';r.append(style)
      t=ET.SubElement(r,'{'+NS['a']+'}t');t.text=line
def adapt(template,objmap,changes,out,allow_partial=False):
    template=Path(template);out=Path(out)
    if template.resolve()==out.resolve():raise ValueError('Output must differ from source template')
    b=template.read_bytes()
    if hashlib.sha256(b).hexdigest()!=objmap['template_sha256']:raise ValueError('Template hash mismatch')
    allowed={e['slot']:e for e in objmap['text_slots']};extra=set(changes)-allowed.keys()
    if extra:raise ValueError('Unknown slots: '+','.join(sorted(extra)))
    if not allow_partial and allowed.keys()-changes.keys():raise ValueError('Missing slots; explicitly supply all source text fields or use --allow-partial for a deliberate partial edit')
    for key,value in changes.items():
      if not isinstance(value,str):raise ValueError('Slot values must be strings')
      cap=allowed[key].get('suggested_max_chars',100)
      if len(value)>cap:raise ValueError(f'Capacity exceeded {key}: {len(value)}>{cap}; change layout/font explicitly, do not truncate')
    changed=0;out.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(template) as zin,zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as zout:
      for info in zin.infolist():
        data=zin.read(info.filename)
        if info.filename==objmap['slide_part']:
          root=ET.fromstring(data)
          shapes={s.find('p:nvSpPr/p:cNvPr',NS).get('id'):s for s in root.findall('.//p:sp',NS) if s.find('p:nvSpPr/p:cNvPr',NS) is not None}
          replacements={}
          for key,value in changes.items():
            id=str(allowed[key]['shape_id'])
            if id not in shapes:raise ValueError('Mapped shape missing: '+id)
            replace_runs(shapes[id],value);changed+=1
            replacements[id]=ET.tostring(shapes[id].find('p:txBody',NS),encoding='unicode')
          # Preserve root namespace declarations and mc:Ignorable values verbatim.
          # Whole-slide ElementTree serialization can invalidate Office extension prefixes.
          source_xml=data.decode('utf-8')
          prefix=next((p for p,u in re.findall(r'xmlns:([\w]+)="([^"]+)"',source_xml) if u==NS['p']),None)
          if not prefix:raise ValueError('Presentation namespace prefix not found')
          def patch_shape(match):
            fragment=match.group(0);m=re.search(r'<'+prefix+r':cNvPr\b[^>]*\bid="([^"]+)"',fragment)
            if m and m.group(1) in replacements:
              return re.sub(r'<'+prefix+r':txBody\b[\s\S]*?</'+prefix+r':txBody>',lambda _:replacements[m.group(1)],fragment,count=1)
            return fragment
          data=re.sub(r'<'+prefix+r':sp(?=[\s>])[\s\S]*?</'+prefix+r':sp>',patch_shape,source_xml).encode('utf-8')
        zout.writestr(info,data)
    return {'output':str(out.resolve()),'changed_text_shapes':changed,'image_generation':False,'visual_validation_required':True}
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--template',required=True);ap.add_argument('--map',required=True);ap.add_argument('--content',required=True);ap.add_argument('--out',required=True);ap.add_argument('--allow-partial',action='store_true');a=ap.parse_args();print(json.dumps(adapt(a.template,read(a.map),read(a.content),a.out,a.allow_partial),ensure_ascii=False))
if __name__=='__main__':
    try:main()
    except Exception as e:print(json.dumps({'error':str(e)},ensure_ascii=False),file=sys.stderr);sys.exit(1)
