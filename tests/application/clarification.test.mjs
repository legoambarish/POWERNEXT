import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {scenarioGrid,screenResults} from '../../ui/scenarios.js';
import {tailLabel} from '../../ui/format.js';
import {recipeControls,componentBill,evidenceContent,resultView} from '../../ui/views.js';
import {searchMatrix} from '../../ui/charts.js';
const load=p=>JSON.parse(fs.readFileSync(new URL(p,import.meta.url),'utf8'));
const result=load('../../powernext/optimizer/examples/LI_parallel_recommendation.json');
const profile=load('../../powernext/physics/CPRI_EQUIPMENT_PROFILE.json');
test('matrix retains every single and parallel candidate independently',()=>{
  const html=searchMatrix(result.candidates);const ids=[...html.matchAll(/data-candidate="([^"]+)"/g)].map(m=>m[1]);
  assert.equal(ids.length,588);assert.equal(new Set(ids).size,588);
  assert.ok(html.includes('180 || 520'));
});
test('parallel label and component counts are visible',()=>{
  const r=result.best_configuration;assert.equal(tailLabel(r),'180 || 520');
  const html=componentBill(r);for(const v of ['9 × 30','9 × 180','9 × 520','133.714','Configuration component list'])assert.ok(html.includes(v));
});
test('parallel recipe is not enabled by default and wrong domain is disabled',()=>{
  const q=structuredClone(result.request);delete q.recipe_ids;
  const html=recipeControls(q,profile);assert.ok(!/value="HYP_LI_TAIL_180_PAR_520_v1" checked/.test(html));
  q.impulse_type='SI';q.recipe_ids=['HYP_LI_TAIL_180_PAR_520_v1'];
  assert.ok(/value="HYP_LI_TAIL_180_PAR_520_v1"\s+disabled/.test(recipeControls(q,profile)));
});
test('what-if grids are explicit, bounded, and leave the fixed request unchanged',()=>{
  const before=JSON.stringify(result.request);const grid=scenarioGrid(result.request,result.best_configuration,{dutMin:800,dutMax:1000,lMin:10,lMax:20,steps:17});
  assert.equal(grid.length,289);assert.equal(JSON.stringify(result.request),before);
  assert.ok(Math.abs(grid[0].setup.dut_capacitance_F-800e-12)<1e-22);
  assert.deepEqual(grid[0].configuration,result.best_configuration.configuration);
  assert.throws(()=>scenarioGrid(result.request,result.best_configuration,{dutMin:800,dutMax:700,lMin:10,lMax:20,steps:65}));
});
test('an ML scalar-band estimate never uses the verified pass presentation',()=>{
  const grid=scenarioGrid(result.request,result.best_configuration,{dutMin:800,dutMax:1000,lMin:10,lMax:20,steps:2});
  const response={scenario_count:4,elapsed_ms:1,physics_simulations:0,rows:grid.map((x,i)=>({status:i?'ML_SCREEN_ONLY':'ABSTAIN',predicted_scalar_bands:true}))};
  const html=screenResults(response,grid,2);assert.ok(!html.includes('chip pass'));assert.ok(html.includes('ML exploration only'));assert.ok(html.includes('detailed Physics verification'));
});
test('disagreement explanation supports ML false acceptance and false rejection',()=>{
  for(const [name,id] of [['LI_disagreement_recommendation.json','cfg_3754ce6cb55b96c7'],['LI_rare_timing_pass_recommendation.json',null]]){
    const p=load('../../powernext/optimizer/examples/'+name),r=id?p.candidates.find(x=>x.candidate_id===id):p.best_configuration;
    const s={bundle:{result:p},row:r};const html=evidenceContent({baseline:null,model_card:null},s);
    assert.ok(html.includes(`ML scalar limits: <b>${r.ml_score.scalar_limits_pass?'pass':'fail'}</b>`));
    assert.ok(html.includes(`Saved reference waveform: <b>${r.assessment.compliance_status.toLowerCase()}</b>`));
    assert.ok(!resultView(s).includes('The saved reference waveform passes;'));
  }
});
