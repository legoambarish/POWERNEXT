"""Engineering workflows around the unchanged circuit and trained models."""
import copy,json,uuid
import numpy as np
from .common import write_json,read_json,file_hash,safe_child,checked_id,now,digest
from powernext_ml.screening import screen_batch
from powernext_optimizer.assessment import changes
from physics_engine.evaluator import LIMITS
from physics_engine.recipes import resolve_recipe

def predict_configuration(app,scenario):
    if not isinstance(scenario,dict):raise ValueError('A configuration, setup and target are required')
    c,s=scenario['configuration'],scenario['setup'];target=scenario['target_crest_V']
    app.catalog.adapter.validate(c,s)
    if type(target) not in (int,float) or not np.isfinite(target) or not 50e3<=target<=2400e3:
        raise ValueError('CPRI requested output crest must be 50–2400 kV; use the separate bench workflow for low voltage')
    with app.stack.batch():
        result=app.stack.call(c,s,target)
        model_id=result.get('model_id') or app.stack.models.get(f"{c['impulse_type']}:{c['topology_id']}")
        card=read_json(app.stack.registry/model_id/'card.json') if model_id else None
        if card:
            result['model_evidence']={k:card.get(k) for k in ['model_id','mode','topology_version','test_metrics','nominal_validation_absolute_error_p95','uncertainty_status','domain']}
        result['configuration']=copy.deepcopy(c);result['setup']=copy.deepcopy(s);result['target_crest_V']=target
        result['stack_sha256']=app.stack.fingerprint
        result['component_recipe']=resolve_recipe(app.catalog.adapter.validate(c,s)[0])
        result['target']=copy.deepcopy(__import__('physics_engine.target',fromlist=['nominal_target']).nominal_target(c['impulse_type'],target,c.get('polarity',1)))
        p=result.get('physics_reference',{}).get('metrics',{});ml=result.get('ml_prediction')
        result['ml_minus_physics']={k:ml.get(k)-p.get('crest_magnitude_V' if k=='crest_V' else k) if ml and ml.get(k) is not None and p.get('crest_magnitude_V' if k=='crest_V' else k) is not None else None for k in ['crest_V','T1_s','Tp_s','T2_s']}
    return result

def _discovery_root(app):
    root=app.store.root/'discoveries';root.mkdir(exist_ok=True);return root

def save_discovery(app,record):
    identifier='explore_'+uuid.uuid4().hex[:20]
    folder=_discovery_root(app)/identifier;folder.mkdir()
    record=dict(record,discovery_id=identifier,created_at=now())
    write_json(folder/'record.json',record)
    write_json(folder/'integrity.json',{'record.json':file_hash(folder/'record.json')})
    return record

def load_discovery(app,identifier):
    folder=safe_child(_discovery_root(app),checked_id(identifier))
    if file_hash(folder/'record.json')!=read_json(folder/'integrity.json')['record.json']:raise ValueError('Exploration integrity mismatch')
    return read_json(folder/'record.json')

def discover(app,data):
    scenarios=data.get('scenarios');policy=data.get('policy','EXPLICIT_SCENARIOS')
    if policy not in ('FIXED_SETTING','EXPLICIT_SCENARIOS'):raise ValueError('Unknown exploration policy')
    if not isinstance(scenarios,list) or not 1<=len(scenarios)<=4096:raise ValueError('Provide 1–4096 explicit scenarios')
    if policy=='FIXED_SETTING':
        first=scenarios[0]['configuration']
        if any(s['configuration']!=first for s in scenarios):raise ValueError('Fixed-setting sensitivity must hold stages, resistors, polarity and charge unchanged')
        if any(s['target_crest_V']!=scenarios[0]['target_crest_V'] for s in scenarios):raise ValueError('Fixed-setting sensitivity requires a common target')
    with app.stack.batch():result=screen_batch(scenarios,app.stack.registry,app.stack.selection,app.adapter_name)
    indices=[];margins=[]
    for i,(row,s) in enumerate(zip(result['rows'],scenarios)):
        if row.get('prediction'):
            p=row['prediction'];bounds=LIMITS[s['configuration']['impulse_type']]
            values=[(p['crest_V'],(.97*s['target_crest_V'],1.03*s['target_crest_V'])),(p['front_us'],np.array(bounds['front_s'])*1e6),(p['tail_us'],np.array(bounds['tail_s'])*1e6)]
            margin=min(min(v-lo,hi-v)/(hi-lo) for v,(lo,hi) in values)
            row['estimated_minimum_band_margin']=float(margin);margins.append((abs(margin),i))
    indices=[i for _,i in sorted(margins)[:4]]
    # Include setup endpoints and an unsupported point, not just estimated passes.
    for key in ['dut_capacitance_F','loop_inductance_H']:
        for method in (min,max):
            i=method(range(len(scenarios)),key=lambda j:scenarios[j]['setup'].get(key,0))
            if i not in indices:indices.append(i)
    unsupported=next((i for i,r in enumerate(result['rows']) if r['status']=='ABSTAIN'),None)
    if unsupported is not None and unsupported not in indices:indices.append(unsupported)
    result['suggested_physics_indices']=indices[:8]
    result['suggestion_basis']='Closest estimated scalar-band boundaries, setup endpoints and a support boundary when present. Not an optimized experimental design.'
    result['scenario_band_count']=sum(bool(r.get('predicted_scalar_bands')) for r in result['rows'])
    result['fraction_interpretation']='Count over these user-declared scenarios only; not a probability of laboratory success.'
    return save_discovery(app,dict(schema_version='engineering_discovery_v1',policy=policy,scenarios=copy.deepcopy(scenarios),screen=result,verifications={},stack_sha256=app.stack.fingerprint,notes=str(data.get('notes',''))[:4000]))

def verify_discovery(app,identifier,indices):
    record=load_discovery(app,identifier)
    if record['stack_sha256']!=app.stack.fingerprint:raise ValueError('Exploration uses a different stack; screen its explicit scenarios again')
    if not isinstance(indices,list) or not 1<=len(indices)<=8 or any(type(i) is not int or not 0<=i<len(record['scenarios']) for i in indices):raise ValueError('Select 1–8 valid scenario indices')
    with app.stack.batch():
        for i in sorted(set(indices)):
            record['verifications'][str(i)]=predict_configuration(app,record['scenarios'][i])
    record['parent_discovery_id']=identifier
    return save_discovery(app,record)

def next_adjustment(app,run_id,configuration):
    result=app.store.result(run_id);request=result['request']
    if not app._compatible(result):raise ValueError('Run a new complete search before comparing adjustments with the current stack')
    if not isinstance(configuration,dict):raise ValueError('Current configuration must be an object')
    for field in ('impulse_type','topology_id','polarity'):
        if field in configuration and configuration[field]!=request[field]:
            raise ValueError('Current '+field+' differs from the saved request; run a complete catalog for that declared condition')
    c=dict(configuration,impulse_type=request['impulse_type'],topology_id=request['topology_id'],polarity=request['polarity'])
    current=predict_configuration(app,dict(configuration=c,setup=request['setup'],target_crest_V=request['target_crest_V']))
    current_metrics=(current.get('physics_reference') or {}).get('metrics',{})
    viable=[r for r in result['candidates'] if r['ranking_tier']<=1]
    options=[]
    for row in viable:
        delta=changes(row['configuration'],c);hardware=delta['hardware_change_count'] if 'hardware_change_count' in delta else sum(c.get(k)!=row['configuration'].get(k) for k in ['stages','front_per_stage_ohm','tail_per_stage_ohm','recipe_id'])
        if all(c.get(k)==row['configuration'].get(k) for k in ['stages','stage_charge_V','front_per_stage_ohm','tail_per_stage_ohm','recipe_id']):continue
        m=row['prediction']['physics_reference']['metrics']
        change_list=[dict(field=k,before=c.get(k),after=row['configuration'].get(k)) for k in ['stages','stage_charge_V','front_per_stage_ohm','tail_per_stage_ohm','recipe_id'] if c.get(k)!=row['configuration'].get(k)]
        effects={k:m.get(k)-current_metrics.get(k) if m.get(k) is not None and current_metrics.get(k) is not None else None for k in ['crest_magnitude_V','T1_s','Tp_s','T2_s']}
        options.append(dict(candidate_id=row['candidate_id'],configuration=row['configuration'],assessment=row['assessment'],score=row['score'],hardware_changes=hardware,changes=change_list,expected_metrics=m,expected_minus_current=effects,component_bill_of_materials=row['component_bill_of_materials'],hard_constraints=row['hard_constraints']))
    passing=[r for r in options if r['assessment']['compliance_status']=='PASS']
    chosen=sorted(passing,key=lambda r:(r['hardware_changes'],r['score']['J'],r['candidate_id'])) if passing else sorted(options,key=lambda r:(r['score']['J'],r['hardware_changes'],r['candidate_id']))
    return dict(current=current,alternatives=chosen[:3],passing_alternative_exists=bool(passing),catalog_count=result['search']['evaluated_count'],
                policy='Among Physics-passing alternatives, fewest changed hardware fields then conformity score; charge is shown separately. If none pass, closest conformity score.',
                reason='A passing numerical alternative exists in this declared catalog.' if passing else 'No passing alternative in this declared catalog; closest evaluated settings remain nonconforming.',
                limiting_parameters=result.get('no_solution',{}).get('limiting_parameters',[]) if result.get('no_solution') else [],
                operational_status='Permitted by declared numerical constraints; arrangement, quantities and pulse ratings still require hardware confirmation.')

def informative_measurement(app,run_id):
    result=app.store.result(run_id);q=result['request'];row=result.get('best_configuration') or result.get('closest_noncompliant')
    items=[dict(question='Which auxiliary branches remain connected after firing?',action='Obtain an annotated fired-state circuit showing 135 kΩ charging, 2 MΩ potential and 5.45/13 kΩ discharge resistors, switches and earth return.',resolves='Branch nodes and switch states are unconfirmed; resistor magnitudes alone cannot define an RLC branch.'),
           dict(question='What does the 480 pF basic load include?',action='Confirm the boundary of the supplied capacitance and record DUT, divider and connection capacitances separately.',resolves='Prevents double counting basic and external capacitance.')]
    if row:
        items.append(dict(question='Does the declared model reproduce this actual setting?',action='If the laboratory independently approves this setting, retain the raw positive/negative waveform, actual stage charge, resistor placement, DUT/setup, divider ratio, digitizer settings and calibration reference.',resolves='Compare crest and timing residuals without automatic fitting. A single discrepancy cannot identify a physical cause.',configuration=row['configuration']))
    items.append(dict(question='Does a known setup change explain the predicted timing sensitivity?',action='Use Discovery to specify known DUT or lead-inductance alternatives at a fixed setting; verify boundary scenarios in Physics, then compare qualified laboratory records if available.',resolves='Separates model sensitivity from measured repeatability; no automatic experiment execution.'))
    return dict(items=items,automatic_operation=False,calibration_enabled=False)
