import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {fmt,fromDisplay,inputNumber,readForm,statusAxes} from '../../ui/format.js';
import * as views from '../../ui/views.js';
const source=new URL('../../powernext/optimizer/examples/',import.meta.url);
const load=name=>JSON.parse(fs.readFileSync(new URL(name,source),'utf8'));

test('browser textarea newline normalization cannot alter unchanged uploaded metadata',async()=>{
  const code=fs.readFileSync(new URL('../../ui/app.js',import.meta.url),'utf8');
  const block=code.slice(code.indexOf('function bindMeasurement(){'),code.indexOf('\nfunction measurementTemplate('));
  const elements=new Map(),sent=[];
  const element=id=>{if(!elements.has(id)){const listeners={};let value='';elements.set(id,{listeners,files:[],innerHTML:'',disabled:false,addEventListener:(event,fn)=>listeners[event]=fn,get value(){return value;},set value(text){value=text.replaceAll('\r\n','\n');}});}return elements.get(id);};
  element('measurement-csv').files=[{size:18,arrayBuffer:async()=>new TextEncoder().encode('time,voltage\r\n0,0\r\n').buffer}];
  const context=vm.createContext({document:{getElementById:element},state:{bundle:{run:{run_id:'test'}}},renderToken:1,Uint8Array,btoa,esc:String,showMeasurement:()=>{},savedMeasurements:async()=>{},toast:()=>{},api:async(path,data)=>{if(data){sent.push(data);return {measurement_id:'shot'};}return {};}});
  vm.runInContext(block+'\nbindMeasurement();',context);
  const original='{\r\n  "shot_id": "SYNTHETIC_CRLF",\r\n  "note": "µs"\r\n}\r\n';
  await element('measurement-metadata').listeners.change({target:{files:[{text:async()=>original}]}});
  assert.notEqual(element('measurement-json').value,original,'The fixture reproduces real textarea newline normalization');
  await element('import-measurement').listeners.click({currentTarget:element('import-measurement')});
  assert.equal(sent[0].metadata_text,original);
  assert.equal(atob(sent[0].csv_base64),'time,voltage\r\n0,0\r\n');
  element('measurement-json').value='{"shot_id":"INTENTIONAL_EDIT"}';
  await element('import-measurement').listeners.click({currentTarget:element('import-measurement')});
  assert.equal(sent[1].metadata_text,'{"shot_id":"INTENTIONAL_EDIT"}');
});
test('engineering units round-trip without mutating untouched source precision',()=>{
  for(const [original,scale] of [[5e-10,1e-12],[1.85e-5,1e-6],[164366.2942328273,1000],[3.333333333333333e-10,1e-12]]) assert.equal(fromDisplay(inputNumber(original/scale),scale,original),original);
  assert.equal(inputNumber(5e-10*1e12),500);
  assert.equal(fromDisplay('600',1e-12,5e-10),6e-10);
  assert.equal(fromDisplay('160',1000,164366.29),160000);
});
test('form preserves SI conditions, negative polarity and zero capacitance',()=>{
  const q=load('SI_request.json');q.polarity=-1;
  const fields={target:'1300',mode:'SI',profile:q.equipment_profile_id,topology:q.topology_id,scope:q.catalog_scope,polarity:'-1',dut:'850',divider:'500',stray:'0',inductance:'18.5','loop-r':'0','load-r':'',coverage:'ADDITIONAL_DISJOINT','setup-id':q.setup.setup_id,auxiliary:'UNCONFIRMED_AUXILIARY_BRANCHES_OMITTED','request-id':q.request_id,assumptions:q.assumptions.join('\n'),notes:'<test>'};
  globalThis.document={getElementById:id=>id==='use-current'?{checked:false}:{value:fields[id]},querySelectorAll:()=>[]};
  const copy=JSON.stringify(q);const v=readForm(q);assert.equal(JSON.stringify(q),copy);
  assert.equal(v.request.setup.divider_capacitance_F,q.setup.divider_capacitance_F);
  assert.equal(v.request.setup.loop_inductance_H,q.setup.loop_inductance_H);
  assert.equal(v.request.setup.stray_capacitance_F,0);assert.equal(v.request.polarity,-1);
  assert.equal(v.annotations.notes,'<test>');assert.equal(v.request.target_crest_V,1300000);
});
for(const mode of ['LI','SI'])test(`${mode}: rendered scalar attributes equal every saved original; rendering never reranks`,()=>{
  const p=load(`${mode}_recommendation.json`);const before=JSON.stringify(p);
  const html=views.candidateTable(p.candidates,p,{expert:true});
  const values=[...html.matchAll(/data-raw-value="([^"]*)"/g)].map(m=>m[1]);
  const expected=p.candidates.flatMap(r=>{const m=r.prediction.physics_reference.metrics;return [m.crest_magnitude_V,m[mode==='LI'?'T1_s':'Tp_s'],m.T2_s].map(x=>x==null?'':String(x));});
  assert.deepEqual(values,expected);assert.equal(JSON.stringify(p),before);
  const ids=[...html.matchAll(/data-candidate-row="([^"]*)"/g)].map(m=>m[1]);assert.deepEqual(ids,p.candidates.map(r=>r.candidate_id));
  const row=p.best_configuration??p.closest_noncompliant;const card=views.metricsBlock(row,p);assert.ok(card.includes(fmt(row.prediction.physics_reference.metrics.T2_s,1e-6)));
});
test('numerical pass never becomes hardware or operational approval',()=>{
  const p=load('SI_recommendation.json');const html=views.axes(p.best_configuration);
  for(const label of ['Compliant','Waveform evaluation','EVALUABLE'])assert.ok(html.includes(label));
  const axes=statusAxes(p.best_configuration);
  assert.equal(axes.find(a=>a.key==='hardware').code,'PROVISIONAL');
  assert.equal(axes.find(a=>a.key==='operational').value,'Not established');
  assert.ok(!html.includes('Approved by recorded gate'));
});
test('no-solution, zero approved recipes, waveform gate and escaping are visible',()=>{
  for(const name of ['LI_recommendation.json','SI_approved_only_recommendation.json']){
    const p=load(name);const html=views.resultView({bundle:{result:p},row:p.closest_noncompliant});assert.ok(html.includes('No compliant configuration found in the declared catalog'));
  }
  const p=load('SI_recommendation.json');const r=p.candidates.find(r=>r.assessment.evaluation_status!=='EVALUABLE');assert.ok(views.axes(r).includes('Indeterminate'));
  assert.ok(views.head('<script>','<img src=x>','test').includes('&lt;img src=x&gt;'));
});
