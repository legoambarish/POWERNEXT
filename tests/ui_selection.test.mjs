import test from 'node:test';
import assert from 'node:assert/strict';
import {harness,bundle,tick} from './ui_harness.mjs';
import {inventoryControls,inventorySummary,runFrame} from '../ui/views.js';
import {readForm,fromDisplay} from '../ui/format.js';
import fs from 'node:fs';

test('late evidence import preserves a newer navigation choice',async()=>{
  const h=harness();let submit,resolveImport;
  h.element('reopen-bundle').addEventListener=(_,callback)=>submit=callback;
  h.element('reopen-file').files=[{size:10}];
  h.context.fetch=()=>new Promise(resolve=>resolveImport=resolve);
  h.context.bindReopen();const importing=submit({currentTarget:h.element('reopen-bundle')});
  h.state.screen='measured';h.context.renderToken++;
  resolveImport({ok:true,json:async()=>({run_id:'reopened'})});await importing;
  assert.equal(h.state.screen,'measured');assert.equal(h.state.bundle.run.run_id,'old');
  assert.equal(h.pending.has('/api/runs/reopened'),false);
});

test('navigation during a selected run fetch is not overwritten on completion',async()=>{
  const h=harness();const opening=h.context.openRun('reopened');
  h.state.screen='measured';h.context.renderToken++;
  h.finish('/api/runs/reopened',bundle('reopened'));await opening;
  assert.equal(h.state.screen,'measured');assert.equal(h.state.bundle.run.run_id,'reopened');
  assert.equal(h.state.opening,null);
});

test('navigation during scenario creation and live-search creation remains active',async()=>{
  for(const kind of ['scenario','search']){
    const h=harness(),opening=kind==='scenario'?h.context.openDemo('si'):h.context.startRun();
    h.state.screen='measured';h.context.renderToken++;
    if(kind==='scenario'){
      h.finish('/api/demos/si',{run_id:'si'});await tick();h.finish('/api/runs/si',bundle('si'));
    }else h.finish('/api/runs',{run_id:'new',status:'RUNNING'});
    await opening;assert.equal(h.state.screen,'measured');
  }
});

test('original RT-08: late earlier scenario POST cannot open its result',async()=>{
  const h=harness();const first=h.context.openDemo('si'),last=h.context.openDemo('approved');
  assert.equal(h.state.bundle,null);assert.equal(h.context.main.innerHTML,'<loading>');
  h.finish('/api/demos/approved',{run_id:'approved-last-choice'});await tick();
  h.finish('/api/runs/approved-last-choice',bundle('approved-last-choice'));await last;
  h.finish('/api/demos/si',{run_id:'si-earlier-choice'});await first;
  assert.equal(h.state.bundle.run.run_id,'approved-last-choice');assert.deepEqual(h.renders,['approved-last-choice']);
  assert.equal(h.pending.has('/api/runs/si-earlier-choice'),false);assert.equal(h.element('scenario-jump').value,'approved');
});
test('old run GET resolving during a newer scenario POST never renders',async()=>{
  const h=harness();const first=h.context.openRun('si');const last=h.context.openDemo('approved');
  h.finish('/api/runs/si',bundle('si'));await first;assert.equal(h.state.bundle,null);assert.deepEqual(h.renders,[]);
  h.finish('/api/demos/approved',{run_id:'approved'});await tick();h.finish('/api/runs/approved',bundle('approved'));await last;
  assert.deepEqual(h.renders,['approved']);
});
test('new history selection supersedes pending scenario import',async()=>{
  const h=harness();const a=h.context.openDemo('si'),b=h.context.openRun('saved');
  h.finish('/api/runs/saved',bundle('saved'));await b;h.finish('/api/demos/si',{run_id:'si'});await a;
  assert.equal(h.state.bundle.run.run_id,'saved');assert.deepEqual(h.renders,['saved']);
});
test('stale errors/finally do not clear new loading state or emit notices',async()=>{
  const h=harness();const a=h.context.openDemo('si'),b=h.context.openDemo('approved');
  h.finish('/api/demos/si',new Error('OLD FAILURE'),true);await a;
  assert.equal(h.state.opening,'demo:approved');assert.equal(h.buttons[0].disabled,true);assert.deepEqual(h.messages,[]);
  h.finish('/api/demos/approved',{run_id:'approved'});await tick();h.finish('/api/runs/approved',bundle('approved'));await b;
  assert.equal(h.buttons[0].disabled,false);
});
test('same run selected twice still obeys generation, not just matching ID',async()=>{
  const h=harness();const a=h.context.openRun('same'),b=h.context.openRun('same');
  h.finish('/api/runs/same',bundle('stale'));await a;assert.equal(h.state.bundle,null);
  h.finish('/api/runs/same',bundle('current'));await b;assert.deepEqual(h.renders,['current']);
});
test('late live-search creation stays in history without replacing new selection',async()=>{
  const h=harness();const a=h.context.startRun(),b=h.context.openRun('saved');
  h.finish('/api/runs/saved',bundle('saved'));await b;h.finish('/api/runs',{run_id:'new-job',status:'RUNNING'});await a;
  assert.equal(h.state.bundle.run.run_id,'saved');assert.deepEqual(h.renders,['saved']);assert.equal(h.scheduled.length,0);
});
test('in-flight poll cannot restore the previous run',async()=>{
  const h=harness();const a=h.context.pollRun('old');const b=h.context.openRun('new');
  h.finish('/api/runs/old',bundle('old'));await a;assert.equal(h.state.bundle,null);
  h.finish('/api/runs/new',bundle('new'));await b;assert.deepEqual(h.renders,['new']);assert.equal(h.scheduled.length,0);
});
test('profile inventory is mode-specific, includes empty state and includes confirmed 520 ohm',()=>{
  const p=JSON.parse(fs.readFileSync(new URL('../powernext/physics/CPRI_EQUIPMENT_PROFILE.json',import.meta.url)));
  const li=inventoryControls({impulse_type:'LI',available_front_per_stage_ohm:[],available_tail_per_stage_ohm:[]},p);
  assert.ok(li.includes('value="180"'));assert.ok(li.includes('value="520"'));assert.ok(!li.includes(' checked'));
  assert.ok(inventorySummary({available_front_per_stage_ohm:[]}).includes('None available'));
  assert.ok(inventoryControls({impulse_type:'SI'},p).includes('data-inventory="tail" value="5000" checked'));
});
test('blank numeric draft is unknown instead of a manufactured zero',()=>assert.equal(fromDisplay('',1000,1300000),null));
test('historical status remains visible in the result frame',()=>{
  const p=JSON.parse(fs.readFileSync(new URL('../powernext/optimizer/examples/SI_recommendation.json',import.meta.url)));
  assert.ok(runFrame({bundle:{result:p,run:{},artifact_compatibility:'RECORDED_ARTIFACT_DIFFERENT_OR_UNAVAILABLE_STACK'}}).includes('data-historical-status'));
  const reopened=runFrame({bundle:{result:p,run:{source:'REOPENED_EVIDENCE',status:'COMPLETED'},artifact_compatibility:'MATCHES_CURRENT_STACK'}});
  assert.ok(reopened.includes('Reopened evidence'));assert.ok(!reopened.includes('Computed locally'));
});
