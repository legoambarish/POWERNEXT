// Explicit what-if exploration. No scenario becomes a final request implicitly.
import {esc,fmt,tailLabel} from './format.js';

export function scenarioGrid(request,row,{dutMin,dutMax,lMin,lMax,steps}){
  if(![dutMin,dutMax,lMin,lMax].every(Number.isFinite)||dutMin<0||lMin<0||dutMax<dutMin||lMax<lMin||!Number.isInteger(steps)||steps<2||steps>64)throw new Error('Use finite increasing ranges, nonnegative values, and 2–64 points per axis.');
  const scenarios=[];
  for(let j=0;j<steps;j++)for(let i=0;i<steps;i++){
    const setup=structuredClone(request.setup);setup.dut_capacitance_F=(dutMin+(dutMax-dutMin)*i/(steps-1))*1e-12;setup.loop_inductance_H=(lMin+(lMax-lMin)*j/(steps-1))*1e-6;
    scenarios.push({scenario_id:`DUT${i}_L${j}`,configuration:structuredClone(row.configuration),setup,target_crest_V:request.target_crest_V});
  }
  return scenarios;
}

export function screenResults(result,scenarios,steps){
  const estimates=result.rows.filter(r=>r.status==='ML_SCREEN_ONLY').length;
  return `<section class="card"><div class="card-head"><h3>${result.scenario_count} explicit scenarios</h3><span class="chip info">ML exploration only</span></div><p>${estimates} estimates · ${result.scenario_count-estimates} abstentions · ${fmt(result.elapsed_ms,1,1)} ms on this request · ${result.physics_simulations} physics simulations.</p><p class="small muted">Blue: estimated scalar bands inside. Grey: estimated scalar bands outside. Amber: model abstained.</p><div class="scenario-axis"><span>L ${fmt(scenarios[0].setup.loop_inductance_H,1e-6)} → ${fmt(scenarios.at(-1).setup.loop_inductance_H,1e-6)} µH, top to bottom</span></div><div class="scenario-scroll"><div class="scenario-grid" style="grid-template-columns:repeat(${steps},minmax(23px,1fr))">${result.rows.map((r,i)=>`<button type="button" class="scenario-cell ${r.status==='ABSTAIN'?'abstain':r.predicted_scalar_bands?'inside':''}" data-screen-point="${i}" aria-label="DUT ${fmt(scenarios[i].setup.dut_capacitance_F,1e-12)} pF, L ${fmt(scenarios[i].setup.loop_inductance_H,1e-6)} microhenry, ${r.status==='ABSTAIN'?'abstain':r.predicted_scalar_bands?'inside estimated bands, unverified':'outside estimated bands'}">${r.status==='ABSTAIN'?'?':r.predicted_scalar_bands?'·':'−'}</button>`).join('')}</div></div><div class="scenario-axis"><span>DUT ${fmt(scenarios[0].setup.dut_capacitance_F,1e-12)} pF</span><span>DUT ${fmt(scenarios.at(-1).setup.dut_capacitance_F,1e-12)} pF</span></div><div id="screen-point"></div><p class="micro">Select a scenario for detailed Physics verification or use its setup in a complete optimization.</p></section>`;
}

export function mountScenarioScreen(container,{row,request,api,isCurrent}){
  if(!row){container.innerHTML='<section class="card"><h2>No configuration selected</h2><p>Open a result with a declared configuration to explore scenarios.</p></section>';return;}
  const c=row.configuration,d=request.setup.dut_capacitance_F*1e12,l=request.setup.loop_inductance_H*1e6;
  const field=(id,label,value)=>`<div class="field"><label for="${id}">${label}</label><input id="${id}" type="number" min="0" step="any" required value="${Number(value.toPrecision(10))}"></div>`;
  container.innerHTML=`<div class="page-head"><div><div class="eyebrow">Trained surrogate · explicit exploration</div><h1>ML scenario screening</h1><p>Explore a DUT-capacitance and inductance grid for the selected configuration. The saved request, ranking and load remain unchanged.</p></div></div><section class="card"><div class="card-head"><h3>Fixed configuration #${row.rank}</h3><span class="chip caution">Unverified what-if estimates</span></div><p>${c.stages} stages × ${fmt(c.stage_charge_V,1000)} kV · front ${fmt(c.front_per_stage_ohm)} Ω · tail ${tailLabel(row)} Ω · ${esc(c.recipe_id)}</p><form id="screen-form"><div class="fields">${field('screen-dut-min','DUT minimum (pF)',d*.8)}${field('screen-dut-max','DUT maximum (pF)',d*1.2)}${field('screen-l-min','Inductance minimum (µH)',l*.5)}${field('screen-l-max','Inductance maximum (µH)',Math.max(l*1.5,1))}<div class="field"><label for="screen-steps">Points per axis (2–64)</label><input id="screen-steps" type="number" min="2" max="64" step="1" required value="17"></div></div><button class="btn primary" type="submit">Screen explicit scenarios</button><p class="micro">Physics-guided residual Extra Trees. Synthetic training only; empirical error envelopes are not calibrated confidence intervals. The analytical L=0 baseline is faster but does not model finite-L effects.</p></form><div id="screen-error" role="alert"></div></section><div id="screen-results"></div>`;
  container.querySelector('#screen-form').addEventListener('submit',async event=>{
    event.preventDefault();const button=event.submitter;button.disabled=true;const error=container.querySelector('#screen-error');error.textContent='';
    try{
      const value=id=>Number(container.querySelector('#'+id).value),steps=value('screen-steps');
      const scenarios=scenarioGrid(request,row,{dutMin:value('screen-dut-min'),dutMax:value('screen-dut-max'),lMin:value('screen-l-min'),lMax:value('screen-l-max'),steps});
      const result=await api('/api/screen',{scenarios});if(!isCurrent())return;
      const box=container.querySelector('#screen-results');box.innerHTML=screenResults(result,scenarios,steps);
      const show=i=>{const r=result.rows[i],s=scenarios[i],p=r.prediction;box.querySelector('#screen-point').innerHTML=`<div class="note"><div><b>DUT ${fmt(s.setup.dut_capacitance_F,1e-12)} pF · L ${fmt(s.setup.loop_inductance_H,1e-6)} µH</b><p>${p?`Estimated crest ${fmt(p.crest_V,1000)} kV · ${request.impulse_type==='LI'?'T1':'Tp'} ${fmt(p.front_us)} µs · T2 ${fmt(p.tail_us)} µs`:`Abstained: ${esc(r.reason_codes.join(', '))}`}</p><p class="micro">${p?`${esc(r.model_id)} · ${esc(r.uncertainty_status)}`:'No learned output forced.'} Requires complete physics evaluation.</p></div></div>`;};
      box.querySelectorAll('[data-screen-point]').forEach(el=>el.addEventListener('click',()=>show(Number(el.dataset.screenPoint))));show(0);
    }catch(e){if(isCurrent())error.textContent=e.message;}finally{button.disabled=false;}
  });
}
