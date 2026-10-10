// Presentation helpers. Formatting only: no engineering value is recomputed or rewritten here.
export const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export const fmt=(value,scale=1,digits=3)=>value===null||value===undefined||!Number.isFinite(value)?'—':(value/scale).toLocaleString('en-US',{maximumFractionDigits:digits});
export const fixed=(value,scale=1,digits=3)=>value===null||value===undefined||!Number.isFinite(value)?'—':(value/scale).toLocaleString('en-US',{minimumFractionDigits:digits,maximumFractionDigits:digits});
// A value that rounds to zero at the shown precision carries no sign (never "−0").
export const signed=(v,digits=2)=>{if(v===null||v===undefined||!Number.isFinite(v))return '—';const text=fmt(Math.abs(v),1,digits);return `${Number(text.replaceAll(',',''))===0?'':v>0?'+':'−'}${text}`;};
export const frontKey=p=>p?.request?.impulse_type==='LI'?'T1_s':'Tp_s';
export const frontName=p=>p?.request?.impulse_type==='LI'?'T1':'Tp';
export const metrics=row=>row?.prediction?.physics_reference?.metrics??{};
export const json=value=>`<pre class="details-json">${esc(JSON.stringify(value,null,2))}</pre>`;
export const date=value=>value?new Date(value).toLocaleString('en-GB',{dateStyle:'medium',timeStyle:'short'}):'—';
export const domValue=(id)=>document.getElementById(id)?.value;
export const numberValue=id=>Number(domValue(id));
// Human-readable input values without changing untouched SI values on review.
export const inputNumber=v=>typeof v==='number'?Number(v.toPrecision(15)):v;
export const fromDisplay=(value,scale,original)=>String(value).trim()===''?null:Number.isFinite(original)&&Number(value)===inputNumber(original/scale)?original:Number(value)*scale;

// Display-only unit helpers. The stored SI value is never modified.
export const MV=v=>v===null||v===undefined||!Number.isFinite(v)?'—':`${fixed(v,1e6,3)} MV`;
export const ohm=v=>v===null||v===undefined||!Number.isFinite(v)?'—':v>=1000?`${fmt(v,1000,3)} kΩ`:`${fmt(v,1,3)} Ω`;
// Changed-setting values (stages, charge, resistors) in display units; stored values are untouched.
export const changeValue=(field,v)=>typeof v!=='number'?esc(v):field==='stage_charge_V'?`${fmt(v,1000)} kV`:field.endsWith('_ohm')?`${fmt(v)} Ω`:fmt(v);
export const paramLabel=key=>key==='crest'?'Crest':key==='T1_s'?'T1':key==='Tp_s'?'Tp':key==='T2_s'?'T2':key.replace('_s','');
export const paramLong=key=>({crest:'Crest voltage',T1_s:'T1 · front time',Tp_s:'Tp · time to peak',T2_s:'T2 · time to half-value'})[key]??key;
export const paramUnit=key=>key==='crest'?['kV',1000]:['µs',1e-6];
export const paramKeys=p=>['crest',frontKey(p),'T2_s'];

export const reasonNames={
  TOPOLOGY_UNCONFIRMED:'Fired circuit has not been confirmed by CPRI',RECIPE_UNCONFIRMED:'Resistor connection recipe is provisional',HARDWARE_NOT_VERIFIED:'Hardware verification is not established',
  BASIC_CAPACITANCE_COVERAGE_ASSUMED:'Basic capacitance coverage is an explicit assumption',AUXILIARY_BRANCH_STATE_UNCONFIRMED:'Auxiliary branch states are unconfirmed',
  COMPONENT_PULSE_RATINGS_UNKNOWN:'Individual component pulse ratings are unknown',MIN_STAGE_CHARGE_UNKNOWN:'Reliable minimum stage charge is unknown',MINIMUM_RELIABLE_CHARGE_UNKNOWN:'Reliable minimum stage charge is unknown',
  CHARGE_RESOLUTION_UNKNOWN_CONTINUOUS_ASSUMPTION:'Charge resolution is unknown; continuous charging was assumed',OUTSIDE_TRAINING_SUPPORT:'Outside the trained model’s support; physics fallback',
  ML_REFERENCE_COMPLIANCE_DISAGREEMENT:'ML and the reference disagree on numerical compliance',CREST_BAND_UNREACHABLE_WITH_CHARGE_LIMITS:'The crest band cannot be reached within charging limits',
  OUTSIDE_CREST:'Crest is outside the allowed band',OUTSIDE_T1_S:'LI front time T1 is outside its limits',OUTSIDE_TP_S:'SI peak time Tp is outside its limits',OUTSIDE_T2_S:'Tail time T2 is outside its limits',
  MISSING_APPROVED_RECIPE_INFORMATION:'No approved recipe information is available',MISSING_HARDWARE_CONFIRMATION:'Hardware confirmation is missing',
  WAVEFORM_NONCOMPLIANCE_IN_DECLARED_CATALOG:'No evaluated setting meets every waveform limit',MODEL_OR_WAVEFORM_EVALUATION_LIMITATION:'Some waveforms cannot be qualified by the current evaluator',
  DECLARED_CHARGE_LIMIT_INFEASIBILITY_FOR_SOME_CANDIDATES:'Some settings reach their charge limits before the crest band',
  OSCILLATORY_OR_NOISY_REQUIRES_VALIDATED_EVALUATOR:'Oscillatory waveform requires a qualified evaluator',MODEL_UNAVAILABLE_OR_INCOMPATIBLE:'Selected model unavailable or incompatible; physics fallback',
  WAVEFORM_OR_NUMERIC_UNSUPPORTED:'Waveform or numerical evaluation is unsupported',ML_PHYSICAL_BOUND_VIOLATION:'Learned output failed a physical bound; physics fallback'
};
export const reasonList=codes=>`<ul class="reason-list">${[...new Set(codes??[])].map(code=>`<li>${esc(reasonNames[code]??code.replaceAll('_',' ').toLowerCase())}<span class="reason-code">${esc(code)}</span></li>`).join('')}</ul>`;

// Five separate status axes. Only numerical compliance may use the pass tone.
export function statusAxes(row){
  const a=row?.assessment??{},prediction=row?.prediction??{},m=metrics(row),codes=prediction.reason_codes??[];
  const numerical=a.compliance_status??'UNAVAILABLE';
  const domain=prediction.status==='ML_WITH_PHYSICS_VERIFICATION'?['ML in domain','info','Trained model inside its support; the reference still decides']
    :codes.includes('OUTSIDE_TRAINING_SUPPORT')?['Outside ML domain','caution','Physics fallback; no learned estimate is forced']
    :prediction.status==='PHYSICS_FALLBACK'?['Physics fallback','caution','Learned estimate not used']
    :prediction.status==='ABSTAIN_UNSUPPORTED_WAVEFORM'?['ML abstained','caution','Unsupported waveform; no forced estimate']:['Unavailable','neutral','No prediction record'];
  return [
    {key:'numerical',label:'Numerical compliance',value:numerical==='PASS'?'Compliant':numerical==='FAIL'?'Not compliant':'Indeterminate',tone:numerical==='PASS'?'pass':numerical==='FAIL'?'fail':'neutral',icon:numerical==='PASS'?'check':numerical==='FAIL'?'cross':'dash',code:numerical,note:'Saved reference waveform against the tolerance limits'},
    {key:'domain',label:'Model domain',value:domain[0],tone:domain[1],icon:domain[1]==='info'?'dot':'warn',code:prediction.status??'UNAVAILABLE',note:domain[2]},
    {key:'waveform',label:'Waveform evaluation',value:a.evaluation_status==='EVALUABLE'?'Evaluable':'Indeterminate',tone:a.evaluation_status==='EVALUABLE'?'info':'neutral',icon:a.evaluation_status==='EVALUABLE'?'dot':'dash',code:a.evaluation_status??'UNAVAILABLE',note:m.waveform_status?m.waveform_status.replaceAll('_',' ').toLowerCase():'No evaluated waveform'},
    {key:'hardware',label:'Hardware / recipe',value:row?.recipe_status?.startsWith('PROVISIONAL')?'Provisional, not verified':row?.recipe_status??'Not established',tone:'caution',icon:'warn',code:row?.recipe_status??'NOT_ESTABLISHED',note:'Fired topology and module placement are unconfirmed'},
    {key:'operational',label:'Operational approval',value:row?.hard_constraints?.operator_ready?'Approved by recorded gate':'Not established',tone:row?.hard_constraints?.operator_ready?'info':'caution',icon:'lock',code:row?.hard_constraints?.operator_ready?'OPERATOR_READY':'NOT_ESTABLISHED',note:'No result authorises generator operation'}
  ];
}
export const statusTone=s=>s==='PASS'?'pass':s==='FAIL'?'fail':'neutral';
export const statusText=s=>s==='PASS'?'Pass':s==='FAIL'?'Fail':'Indeterminate';
// Labels of the original ordering tiers (display only; the order itself comes from the optimizer).
export const tierName=row=>!row.hard_constraints?.declared_constraints_satisfied?'Declared constraint not met':row.assessment?.evaluation_status!=='EVALUABLE'?'Waveform not evaluable':row.assessment?.compliance_status==='PASS'?'Numerically compliant':'Evaluable, not compliant';

export function readForm(template){
  const q=structuredClone(template);q.schema_version='test_request_v1';
  q.request_id=(domValue('request-id')??q.request_id??'').trim()||'LOCAL_TEST';q.impulse_type=domValue('mode');q.target_crest_V=fromDisplay(domValue('target'),1000,q.target_crest_V);
  q.equipment_profile_id=domValue('profile')??q.equipment_profile_id;q.topology_id=domValue('topology')??q.topology_id;q.catalog_scope=domValue('scope')??q.catalog_scope;q.polarity=Number(domValue('polarity'));
  Object.assign(q.setup,{dut_capacitance_F:fromDisplay(domValue('dut'),1e-12,q.setup.dut_capacitance_F),divider_capacitance_F:fromDisplay(domValue('divider'),1e-12,q.setup.divider_capacitance_F),stray_capacitance_F:fromDisplay(domValue('stray'),1e-12,q.setup.stray_capacitance_F),loop_inductance_H:fromDisplay(domValue('inductance'),1e-6,q.setup.loop_inductance_H),
    basic_coverage_assumption:domValue('coverage'),loop_resistance_ohm:numberValue('loop-r'),load_resistance_ohm:domValue('load-r').trim()===''?null:fromDisplay(domValue('load-r'),1e6,q.setup.load_resistance_ohm),setup_id:(domValue('setup-id')??q.setup.setup_id??'').trim()||'DECLARED_LOCAL_SETUP',auxiliary_assumption:domValue('auxiliary')??q.setup.auxiliary_assumption});
  q.assumptions=domValue('assumptions').split('\n').map(s=>s.trim()).filter(Boolean);
  q.current_setting=document.getElementById('use-current').checked?{stages:numberValue('current-stages'),stage_charge_V:fromDisplay(domValue('current-charge'),1000,q.current_setting?.stage_charge_V),front_per_stage_ohm:numberValue('current-front'),tail_per_stage_ohm:numberValue('current-tail'),recipe_id:domValue('current-recipe')}:null;
  if(document.getElementById('inventory-controls')?.hasAttribute?.('data-resistor-inventory')){
    for(const [kind,key] of [['front','available_front_per_stage_ohm'],['tail','available_tail_per_stage_ohm']]){
      const choices=[...document.querySelectorAll(`[data-inventory="${kind}"]`)];
      const selected=choices.filter(el=>el.checked).map(el=>Number(el.value));
      if(selected.length===choices.length&&!Object.hasOwn(template,key))delete q[key];else q[key]=selected;
    }
  }
  if(document.getElementById('recipe-controls'))q.recipe_ids=[...document.querySelectorAll('[data-recipe]')].filter(el=>el.checked&&!el.disabled).map(el=>el.value);
  const value_provenance=Object.fromEntries([...document.querySelectorAll('[data-provenance]')].map(el=>[el.dataset.provenance,el.value]));
  return {request:q,annotations:{value_provenance,notes:domValue('notes')}};
}

export const tailLabel=row=>{const c=row?.configuration??row;const values=row?.tail_recipe?.component_values_ohm??(c?.recipe_id==='HYP_LI_TAIL_180_PAR_520_v1'?[180,520]:[c?.tail_per_stage_ohm]);return values.map(v=>fmt(v)).join(values.length>1?' || ':'');};
