// Presentation-rule tests for the redesigned UI. They render original optimizer artifacts and
// check that the interface never changes order, promotes a failure, merges status axes or mislabels units.
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {statusAxes,fmt,paramUnit} from '../../ui/format.js';
import * as views from '../../ui/views.js';
import {toleranceBar,searchMatrix,toleranceScatter,scoreBar} from '../../ui/charts.js';

const examples=new URL('../../powernext/optimizer/examples/',import.meta.url);
const load=name=>JSON.parse(fs.readFileSync(new URL(name,examples),'utf8'));
const fixtures=fs.readFileSync(new URL('../../powernext_app/fixtures.py',import.meta.url),'utf8');
const DEMOS=[...fixtures.matchAll(/id='([^']+)',request='([^']+)',result='([^']+)'/g)].map(m=>({id:m[1],result:m[3]}));
const state=p=>({bundle:{artifact_compatibility:'MATCHES_CURRENT_STACK',result:p,run:{run_id:'run_test',source:'SYNTHETIC_DEMO',created_at:'2026-10-03T00:00:00Z'}},row:p.best_configuration??p.closest_noncompliant??p.candidates[0]??null,screen:'result',range:'tail',compareId:p.candidates[1]?.candidate_id});

test('twelve current synthetic demos are discovered from the fixture routes',()=>assert.equal(DEMOS.length,12));

for(const d of DEMOS)test(`${d.id}: every view renders from the original artifact without mutating it`,()=>{
  const p=load(d.result),before=JSON.stringify(p),s=state(p);
  for(const html of [views.runFrame(s),views.resultView(s),views.alternatives(s),views.waveformView(s),views.searchView(s),views.evidenceView(s)])assert.equal(typeof html,'string');
  if(s.row)views.evidenceContent({baseline:null,model_card:null,baseline_unavailable_reason:'test'},s);
  assert.equal(JSON.stringify(p),before);
});

for(const d of DEMOS)test(`${d.id}: no-solution is never presented as a recommendation`,()=>{
  const p=load(d.result),html=views.resultView(state(p));
  if(p.no_solution){
    assert.ok(html.includes('No compliant configuration found in the declared catalog'));
    assert.ok(!html.includes('Recommended numerical setting'));
    assert.ok(!html.includes('chip pass'),'no pass chip may appear on a no-solution result');
    if(p.closest_noncompliant)assert.ok(html.includes('NOT a recommendation'));
  }else{
    assert.ok(html.includes('Recommended numerical setting'));
    for(const label of ['Numerically compliant','Recipe provisional','Not approved for operation'])assert.ok(html.includes(label),label);
  }
});

test('five status axes stay separate; only numerical compliance may carry the pass tone',()=>{
  for(const d of DEMOS){const p=load(d.result);for(const r of p.candidates){
    const axes=statusAxes(r);assert.equal(axes.length,5);
    assert.deepEqual(axes.map(a=>a.key),['numerical','domain','waveform','hardware','operational']);
    axes.slice(1).forEach(a=>assert.notEqual(a.tone,'pass',`${d.id} ${a.key}`));
    assert.equal(axes[0].tone==='pass',r.assessment.compliance_status==='PASS');
    assert.equal(axes[3].tone,'caution');assert.equal(axes[4].value,'Not established');
  }}
});

test('OOD candidates show the physics fallback and no learned value',()=>{
  const p=load('SI_ood_recommendation.json');
  for(const r of p.candidates){assert.equal(statusAxes(r)[1].value,'Outside ML domain');}
  const s=state(p),html=views.evidenceContent({baseline:null,model_card:null},s);
  assert.ok(html.includes('Outside the trained model’s support'));assert.ok(html.includes('— not used'));
});

test('Physics/ML disagreement stays visible with both values',()=>{
  const p=load('LI_disagreement_recommendation.json'),s=state(p);s.row=p.candidates.find(r=>r.candidate_id==='cfg_3754ce6cb55b96c7');const r=s.row;
  const html=views.evidenceContent({baseline:null,model_card:null},s);
  assert.ok(html.includes('Explicit disagreement'));
  assert.ok(html.includes(fmt(r.prediction.ml_prediction.T2_s,1e-6)));
  assert.ok(html.includes(fmt(r.prediction.physics_reference.metrics.T2_s,1e-6)));
  assert.ok(views.resultView(s).includes('Physics and ML disagree'));
});

test('display sorting and filtering never rewrite the optimizer rank',()=>{
  const p=load('SI_recommendation.json');const shuffled=[...p.candidates].sort((a,b)=>(b.score?.J??0)-(a.score?.J??0));
  const html=views.candidateTable(shuffled,p,{expert:true});
  const ranks=[...html.matchAll(/aria-label="Inspect configuration rank (\d+)"/g)].map(m=>Number(m[1]));
  assert.deepEqual(ranks,shuffled.map(r=>r.rank));
  const top=views.alternatives(state(p));const shown=[...top.matchAll(/class="pick-rank">#(\d+)</g)].map(m=>Number(m[1]));
  assert.deepEqual(shown,[1,2,3]);
});

test('no-solution distance outside the limit equals the saved value minus the unchanged limit',()=>{
  const p=load('LI_recommendation.json'),r=p.closest_noncompliant,c=r.score.components.T2_s;
  const html=views.failurePanel(r,p);const d=Math.max(c.limits[0]-c.value,c.value-c.limits[1]);
  assert.ok(html.includes(`${fmt(d,1e-6)} µs`));assert.ok(d>0);
});

test('binding hardware limits are reported for the infeasible request',()=>{
  const p=load('SI_infeasible_recommendation.json'),html=views.failurePanel(p.closest_noncompliant,p);
  for(const name of ['Charge per stage','Summed charge','Total stored energy'])assert.ok(html.includes(name),name);
});

test('tolerance bars agree with every saved within-limits flag',()=>{
  for(const d of DEMOS){const p=load(d.result);for(const r of p.candidates)for(const [k,c] of Object.entries(r.score?.components??{})){
    const html=toleranceBar(k,c);assert.ok(html.includes(c.within_limits?'class="tol in':'class="tol out'),`${d.id} ${r.candidate_id} ${k}`);
    const [unit,scale]=paramUnit(k);assert.ok(html.includes(`${fmt(c.value,scale,3)} <small>${unit}</small>`));
  }}
});

test('search matrix and scatter cover every candidate exactly once',()=>{
  for(const name of ['SI_recommendation.json','LI_recommendation.json']){const p=load(name);
    const m=searchMatrix(p.candidates);const ids=[...m.matchAll(/data-candidate="([^"]+)"/g)].map(x=>x[1]);
    assert.deepEqual([...ids].sort(),p.candidates.map(r=>r.candidate_id).sort());
    const sc=toleranceScatter(p.candidates,p);const pts=[...sc.matchAll(/<circle class="sc /g)].length;
    assert.equal(pts,p.candidates.filter(r=>r.score?.components?.T2_s).length);
  }
});

test('compare explanation names the original decisive ranking field',()=>{
  const p=load('SI_recommendation.json'),[a,b]=p.candidates;
  const html=views.comparison(a,b,p,{preferred_id:a.candidate_id,decisive_factor:'reference conformity score J',policy:'Original optimizer lexicographic ordering; no UI reranking'});
  assert.ok(html.includes('reference conformity score J'));assert.ok(html.includes(fmt(a.score.J,1,6))&&html.includes(fmt(b.score.J,1,6)));
  const q=load('LI_rare_timing_pass_recommendation.json');
  assert.ok(views.whySentence(q.candidates[0],q.candidates[1],q,{preferred_id:q.candidates[0].candidate_id,decisive_factor:'validity / numerical compliance'}).includes('better validity tier'));
});

test('engineering units are never case-transformed',()=>{
  const css=fs.readFileSync(new URL('../../ui/app.css',import.meta.url),'utf8');
  const rules=[...css.matchAll(/([^{}]+)\{[^}]*text-transform:uppercase[^}]*\}/g)].map(m=>m[1].trim());
  assert.ok(!rules.some(sel=>/\bth\b|\.data|\.metric|\.tol|\.kv|\.num/.test(sel)),`uppercase on unit-bearing selector: ${rules.join(' | ')}`);
  const p=load('LI_recommendation.json');const html=views.candidateTable(p.candidates,p);
  assert.ok(html.includes('T1 µs')&&html.includes('T2 µs')&&html.includes('Crest kV'));
});

test('schematic places the tail resistor according to the declared topology',()=>{
  const setup=load('SI_request.json').setup;
  assert.ok(views.schematic('GSHUNT_v0',setup,4.8e-10).includes('across the generator node'));
  assert.ok(views.schematic('OSHUNT_v0',setup,4.8e-10).includes('across the output node'));
});

test('measured-data screen states provenance and never implies calibration',()=>{
  const html=views.measuredView({bundle:null,row:null});
  assert.ok(html.includes('No genuine CPRI measurement is included in this release'));
  assert.ok(html.includes('Calibration is not fitted'));assert.ok(/id="import-measurement"[^>]*disabled/.test(html));
});

test('score bar decomposes J with the saved squared contributions',()=>{
  const p=load('SI_recommendation.json'),r=p.best_configuration,html=scoreBar(r,p);
  for(const c of Object.values(r.score.components))assert.ok(html.includes(fmt(c.squared_contribution,1,4)));
  assert.ok(html.includes(fmt(r.score.J,1,6)));
});

test('user text is escaped in every new surface',()=>{
  const p=load('SI_recommendation.json');p.request.request_id='<img src=x onerror=1>';
  const html=views.runFrame(state(p));assert.ok(!html.includes('<img src=x'));assert.ok(html.includes('&lt;img'));
  const h=views.historyRows([{run_id:'r',created_at:'2026-10-03T00:00:00Z',status:'COMPLETED',source:'LIVE_OPTIMIZATION',result_status:'NO_COMPLIANT_CONFIGURATION',application_version:'0.1.0',request:{...p.request}}],null);
  assert.ok(!h.includes('<img src=x'));
});
