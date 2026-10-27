/** Native editable authoring from semantic recipes; no image-generation calls. */
import fs from 'node:fs/promises';
import path from 'node:path';
import {createRequire} from 'node:module';
import {pathToFileURL} from 'node:url';
import crypto from 'node:crypto';
const args={};for(let i=2;i<process.argv.length;i+=2)args[process.argv[i].replace(/^--/,'')]=process.argv[i+1];
for(const k of ['spec','cache','out'])if(!args[k])throw new Error(`Missing --${k}`);
let engine;
try{
 const req=createRequire(path.join(path.resolve(args.modules||'.'),'__resolve.cjs'));
 engine=await import(pathToFileURL(req.resolve('@oai/artifact-tool')).href);
}catch(e){throw new Error('Native authoring dependency @oai/artifact-tool unavailable. Use host workspace runtime and --modules; no image-generation fallback. '+e.message)}
const {Presentation,PresentationFile}=engine;
const load=async p=>JSON.parse(await fs.readFile(p,'utf8'));
const spec=await load(args.spec),catalog=await load(path.join(args.cache,'catalog.json'));
if(!Array.isArray(spec.slides)||!spec.slides.length)throw new Error('slides must be nonempty');
const W=1280,H=720;
const defaults={ink:'#142D45',accent:'#137F94',secondary:'#D98B42',muted:'#576E7B',light:'#EDF5F6',white:'#FFFFFF',rule:'#CEDFE4'};
const palette={...defaults,...spec.design?.palette};
const font=spec.design?.font||'Microsoft YaHei';
const color=v=>palette[v]||v||'none';
const pos=b=>({left:b[0]*W,top:b[1]*H,width:b[2]*W,height:b[3]*H});
const presentation=Presentation.create({slideSize:{width:W,height:H}});
const report={schema_version:1,engine:'@oai/artifact-tool',image_generation:false,font,slides:[],errors:[]};
await fs.mkdir(path.join(args.out,'rendered'),{recursive:true});
function addShape(slide,e){return slide.shapes.add({name:e.id,geometry:e.geometry||'rect',position:pos(e.box),fill:color(e.fill),line:{style:'solid',fill:color(e.stroke||'none'),width:e.stroke_width||0}})}
function text(slide,e,value){
 const shape=addShape(slide,{...e,geometry:'textbox',fill:'none'});shape.text=String(value);shape.text.insets=0;
 shape.text.style={typeface:font,fontSize:e.font_size||22,color:color(e.color||'ink'),bold:!!e.bold,alignment:e.align||'left',verticalAlignment:'top',wrap:'square',autoFit:'none'};return shape;
}
for(let index=0;index<spec.slides.length;index++){
 const page=spec.slides[index];const entry=catalog.items.find(e=>e.id===page.layout);if(!entry)throw new Error('Unknown layout '+page.layout);
 if(!entry.recipe)throw new Error('This is an editable source template, not a geometry recipe: use adapt_template.py and host template-preserving authoring.');
 const override=page.recipe_overrides?path.resolve(path.dirname(args.spec),page.recipe_overrides):null;
 const recipePath=override||path.join(args.cache,entry.recipe.path);
 const bytes=await fs.readFile(recipePath);
 if(!override&&crypto.createHash('sha256').update(bytes).digest('hex')!==entry.recipe.sha256)throw new Error('Recipe hash mismatch '+page.layout);
 const recipe=JSON.parse(bytes),slots=page.slots||{},used=new Set();
 const binds=new Set(recipe.elements.filter(e=>e.kind==='text'&&e.bind).map(e=>e.bind));
 for(const key of Object.keys(slots))if(!binds.has(key))throw new Error(`Unused slot ${key} on page ${index+1}`);
 for(const [kind,field] of [['table','tables'],['chart','charts'],['image','images']]){
  const expected=new Set(recipe.elements.filter(e=>e.kind===kind).map(e=>e.bind));
  for(const key of Object.keys(page[field]||{}))if(!expected.has(key))throw new Error(`Unused ${field} field ${key} on page ${index+1}`);
 }
 if(!page.title)throw new Error('Missing title page '+(index+1));
 const slide=presentation.slides.add();slide.background.fill=color(recipe.background||'white');
 const title=recipe.title||{box:[.055,.055,.89,.09],font_size:36,bold:true,color:'ink'};
 text(slide,{id:'title',...title},page.title);
 const stat={page:index+1,id:page.id||String(index+1),layout:page.layout,composition:entry.composition,texts:1,shapes:0,charts:0,tables:0,images:0,reference_viewed:page.reference_viewed===true};
 for(const e of recipe.elements){
  if(e.kind==='text'){
   let v=e.text||'';
   if(e.bind){used.add(e.bind);if(!(e.bind in slots)&&!page.allow_missing_slots)throw new Error(`Missing slot ${e.bind} on page ${index+1}`);v=slots[e.bind]??'';if(typeof v!=='string'&&typeof v!=='number')throw new Error('Text slot must be string or number');if(e.max_chars&&String(v).length>e.max_chars)throw new Error(`Capacity exceeded ${e.bind}: ${String(v).length}>${e.max_chars}`)}
   text(slide,e,v);stat.texts++;
  }else if(e.kind==='shape'||e.kind==='line'){addShape(slide,e);stat.shapes++;
  }else if(e.kind==='table'){
   const values=page.tables?.[e.bind];if(!Array.isArray(values)||values.length<1||!values.every(r=>Array.isArray(r)&&r.length===values[0].length))throw new Error('Missing/irregular native table '+e.bind);
   const p=pos(e.box);const table=slide.tables.add({rows:values.length,columns:values[0].length,left:p.left,top:p.top,width:p.width,height:p.height,values});
   table.borders.assign({style:'solid',fill:color('rule'),width:1});
   table.cells.block({row:0,column:0,rowCount:values.length,columnCount:values[0].length}).assign({anchor:'center',margins:{top:10,bottom:10,left:12,right:12}});
   for(let r=0;r<values.length;r++)for(let c=0;c<values[r].length;c++){
    const cell=table.getCell(r,c);cell.fill=color(r===0?'accent':r%2?'light':'white');cell.text.style={typeface:font,fontSize:e.font_size||21,bold:r===0,color:color(r===0?'white':'ink')};
   }stat.tables++;
  }else if(e.kind==='chart'){
   const data=page.charts?.[e.bind];if(!data?.categories?.length||!data?.series?.length)throw new Error('Missing native chart '+e.bind);
   for(const s of data.series)if(s.values.length!==data.categories.length||s.values.some(v=>typeof v!=='number'||!Number.isFinite(v)))throw new Error('Invalid numeric chart data');
   const chartStyle={typeface:font,fontSize:18};
   const chart=slide.charts.add(data.type||'bar',{position:pos(e.box),title:data.title||page.title,categories:data.categories,series:data.series.map((s,i)=>({...s,fill:color(i?'secondary':'accent')})),hasLegend:data.series.length>1,titleTextStyle:chartStyle,xAxis:{textStyle:chartStyle},yAxis:{textStyle:chartStyle},legend:{textStyle:chartStyle},dataLabels:{showValue:true,position:'outEnd',textStyle:chartStyle}});
   if(engine.applyPresentationChartFont)engine.applyPresentationChartFont(chart,{fontFamily:font});stat.charts++;
  }else if(e.kind==='image'){
   const asset=page.images?.[e.bind];if(!asset?.path)throw new Error('Missing source image '+e.bind);
   const p=path.resolve(path.dirname(args.spec),asset.path);const data=await fs.readFile(p);const mime=asset.mime||(p.toLowerCase().endsWith('.png')?'image/png':'image/jpeg');
   slide.images.add({blob:new Uint8Array(data),contentType:mime,position:pos(e.box),fit:'contain'});stat.images++;
  }else throw new Error('Unsupported element '+e.kind);
 }
 slide.speakerNotes.text=`[Sources]\n${(page.sources||[]).join('\n')}\n[Layout reference]\n${page.layout} / ${entry.source_ref||'native recipe'}\n${page.notes||''}`;
 report.slides.push(stat);
}
await(await PresentationFile.exportPptx(presentation)).save(path.join(args.out,'deck.pptx'));
for(let i=0;i<presentation.slides.items.length;i++){
 try{const blob=await presentation.export({slide:presentation.slides.items[i],format:'png',scale:1});await fs.writeFile(path.join(args.out,'rendered',`slide-${String(i+1).padStart(2,'0')}.png`),new Uint8Array(await blob.arrayBuffer()));}
 catch(e){report.errors.push({page:i+1,stage:'render',message:e.message});}
}
await fs.writeFile(path.join(args.out,'build-report.json'),JSON.stringify(report,null,2));
console.log(JSON.stringify({pptx:path.resolve(args.out,'deck.pptx'),slides:report.slides.length,render_errors:report.errors.length}));
if(report.errors.length)process.exitCode=2;
