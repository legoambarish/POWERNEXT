import copy
import json
from pathlib import Path
import numpy as np
import pytest
from powernext_optimizer.common import PACKAGE
from powernext_optimizer.catalog import Catalog, normalize_request
from powernext_optimizer.charge import ChargePolicy, charge_choices, legal_interval, hardware_checks
from powernext_optimizer.assessment import parameter_score, rank_key
from powernext_optimizer.prediction import PredictionStack
from powernext_optimizer.service import recommend, evaluate_candidate, evaluate_sensitivity
from powernext_optimizer.storage import HistoryStore, RecommendationResult
from physics_engine.evaluator import LIMITS, evaluate

@pytest.fixture(scope='module')
def catalog():
    return Catalog()

@pytest.fixture
def request_data():
    return json.loads((PACKAGE/'examples/SI_request.json').read_text())

@pytest.mark.parametrize('mode',['LI','SI'])
@pytest.mark.parametrize('topology',['GSHUNT_v0','OSHUNT_v0'])
def test_complete_catalog(catalog,mode,topology):
    rows=catalog.entries(mode,topology)
    assert len(rows)==504 and len({r['candidate_id'] for r in rows})==504
    assert {r['configuration']['stages'] for r in rows}==set(range(2,16))
    assert {r['configuration']['front_per_stage_ohm'] for r in rows}=={30,46,180,520,3700,5000}
    assert all(r['recipe_status']=='PROVISIONAL' and r['exact_module_allocation'] is None for r in rows)
    assert catalog.entries(mode,topology,'approved')==[]

@pytest.mark.parametrize('field,value',[('target_crest_V',float('nan')),('target_crest_V',float('inf')),('target_crest_V',-1),('target_crest_V',5e6),('target_crest_V',True),('impulse_type','unknown'),('impulse_type',[]),('equipment_profile_id','invented'),('topology_id','choose_best'),('polarity',True),('alternatives',0),('setup',None),('tolerance',.5)])
def test_bad_request(request_data,field,value):
    request_data[field]=value
    result=recommend(request_data,progress=False)
    assert result.payload['status']=='INVALID_REQUEST'
    assert not result.payload['candidates']

@pytest.mark.parametrize('field,value,constraint',[('stages',16,'active_stages'),('stages',1,'active_stages'),('stage_charge_V',200001,'stage_charge_V'),('front_per_stage_ohm',465,'shared_configuration_validation'),('tail_per_stage_ohm',521,'shared_configuration_validation'),('recipe_id','invented','shared_configuration_validation')])
def test_hardware_rejections(catalog,request_data,field,value,constraint):
    e=catalog.entries('SI','GSHUNT_v0')[0]
    c=dict(e['configuration'],stage_charge_V=100000,polarity=1);c[field]=value
    h=hardware_checks(catalog,e,c,request_data['setup'])
    assert not h['declared_constraints_satisfied']
    assert any(x['constraint']==constraint and x['status']=='FAIL' for x in h['constraints'])

@pytest.mark.parametrize('limit,constraint',[('summed_stage_charge_max','summed_charge_V'),('stored_energy_per_stage_rated','stage_energy_J'),('stored_energy_total_rated','total_energy_J')])
def test_independent_redundant_limits(request_data,limit,constraint):
    cat=Catalog();cat.limits[limit]=1
    e=cat.entries('SI','GSHUNT_v0')[0]
    h=hardware_checks(cat,e,dict(e['configuration'],stage_charge_V=100000,polarity=1),request_data['setup'])
    assert any(x['constraint']==constraint and x['status']=='FAIL' for x in h['constraints'])

def test_charge_band_instead_of_exact_only():
    p=ChargePolicy(None,200000)
    s=charge_choices(10,2.02e6,.03,p)
    assert s['choices_V']==[200000] and s['band_feasible'] and not s['exact_target_within_continuous_limits']
    assert not charge_choices(10,2.2e6,.03,p)['band_feasible']
    assert charge_choices(10,1.9e6,.03,p)['choices_V']==[190000]
    assert charge_choices(1,99,.03,ChargePolicy(100,200))['choices_V']==[100]
    assert legal_interval(ChargePolicy(201,200)) is None

@pytest.mark.parametrize('origin,step,target',[(0,5000,123456),(2000,7000,189500),(0,.1,.3),(300,5300,90300)])
def test_grid_matches_independent_full_enumeration(origin,step,target):
    maximum=.3 if step==.1 else 200000
    from decimal import Decimal
    grid=[float(Decimal(str(origin))+k*Decimal(str(step))) for k in range(1 if origin==0 else 0, int(maximum/step)+2)]
    grid=[v for v in grid if 0<v<=maximum]
    choices=charge_choices(1,target,.03,ChargePolicy(None,maximum,step,origin))['choices_V']
    assert min(abs(v-target) for v in choices)==pytest.approx(min(abs(v-target) for v in grid))
    assert all(v in grid for v in choices)

@pytest.mark.parametrize('mode',['LI','SI'])
@pytest.mark.parametrize('component',['crest','front','tail'])
@pytest.mark.parametrize('side',[0,1])
def test_exact_inside_outside_boundaries(mode,component,side):
    front='T1_s' if mode=='LI' else 'Tp_s'
    p={'crest_V':1e6,front:LIMITS[mode]['nominal_s'][0],'T2_s':LIMITS[mode]['nominal_s'][1]}
    key={'crest':'crest_V','front':front,'tail':'T2_s'}[component]
    bounds={'crest':(.97e6,1.03e6),'front':LIMITS[mode]['front_s'],'tail':LIMITS[mode]['tail_s']}[component]
    for relative,expect in [(0,True),(1e-8 if side==0 else -1e-8,True),(-1e-8 if side==0 else 1e-8,False)]:
        q=dict(p);q[key]=bounds[side]*(1+relative)
        assert parameter_score(q,mode,1e6,.03)['scalar_limits_pass']==expect

def test_objective_arithmetic():
    s=parameter_score(dict(crest_V=1.015e6,Tp_s=275e-6,T2_s=3250e-6),'SI',1e6,.03)
    assert s['J']==pytest.approx(.75)
    assert s['minimum_margin']==pytest.approx(.5)
    assert parameter_score(dict(crest_V=1e6,Tp_s=None,T2_s=.0025),'SI',1e6,.03) is None

def test_missing_model_and_ood_fallback(tmp_path,catalog,request_data):
    c=dict(impulse_type='SI',stages=10,front_per_stage_ohm=3700,tail_per_stage_ohm=5000,topology_id='GSHUNT_v0',recipe_id='DEV_UNIFORM_SINGLE_v2',stage_charge_V=150000,polarity=1)
    missing=PredictionStack(registry=tmp_path,selection=tmp_path/'missing.json').call(c,request_data['setup'],1.3e6)
    assert 'FALLBACK' in missing['status'] and missing['physics_reference'] and missing['ml_prediction'] is None
    setup=copy.deepcopy(request_data['setup']);setup['dut_capacitance_F']=50e-9
    ood=PredictionStack().call(c,setup,1.3e6)
    assert 'FALLBACK' in ood['status'] and 'OUTSIDE_TRAINING_SUPPORT' in ood['reason_codes']

def test_candidate_inputs_and_status(catalog,request_data):
    request=normalize_request(request_data,catalog);before=copy.deepcopy(request)
    e=next(x for x in catalog.entries('SI','GSHUNT_v0') if x['configuration']['stages']==9 and x['configuration']['front_per_stage_ohm']==3700 and x['configuration']['tail_per_stage_ohm']==5000)
    row,wave=evaluate_candidate(request,e,catalog,PredictionStack())
    assert request==before and wave and row['assessment']['compliance_status']=='PASS'
    assert row['prediction']['ml_prediction'] and not row['eligible_for_hardware_recommendation']
    assert not row['hard_constraints']['operator_ready'] and row['recipe_status']=='PROVISIONAL'

def test_cache_integrity(tmp_path,catalog,request_data):
    stack=PredictionStack(cache=tmp_path)
    c=dict(catalog.entries('SI','GSHUNT_v0')[0]['configuration'],stage_charge_V=112345,polarity=1)
    stack.call(c,request_data['setup'],1.3e6)
    path=next(tmp_path.glob('*.json'));payload=json.loads(path.read_text());payload['response']['status']='FORGED'
    path.write_text(json.dumps(payload))
    with pytest.raises(ValueError,match='integrity'):stack.call(c,request_data['setup'],1.3e6)

def test_approved_only(request_data):
    request_data['catalog_scope']='approved'
    p=recommend(request_data,progress=False).payload
    assert p['search']['catalog_count']==0 and p['status']=='NO_COMPLIANT_CONFIGURATION'
    assert 'MISSING_APPROVED_RECIPE_INFORMATION' in p['no_solution']['categories']

def test_sensitivity_fixed_setting(request_data):
    c=dict(impulse_type='SI',stages=9,front_per_stage_ohm=3700,tail_per_stage_ohm=5000,topology_id='GSHUNT_v0',recipe_id='DEV_UNIFORM_SINGLE_v2',stage_charge_V=164366.2942328273,polarity=1)
    out=evaluate_sensitivity(request_data,c,[dict(name='load_plus_1pct',setup_changes={'dut_capacitance_F':request_data['setup']['dut_capacitance_F']*1.01})])
    assert out['scenarios'][0]['configuration']==c
    with pytest.raises(ValueError):evaluate_sensitivity(request_data,c,[dict(name='bad',setup_changes={'target_crest_V':1})])

def test_history_integrity_and_immutable_output(tmp_path):
    source=json.loads((PACKAGE/'examples/SI_recommendation.json').read_text())
    result=RecommendationResult(source,{})
    h=HistoryStore(tmp_path/'history.sqlite');output=tmp_path/'result.json'
    result.save(output,h)
    assert len(h.lookup(source['request_sha256'],source['stack_sha256']))==1
    assert not h.lookup(source['request_sha256'],'different_stack')
    with pytest.raises(FileExistsError):result.save(output)
    output.write_text('tampered')
    assert not h.lookup(source['request_sha256'],source['stack_sha256'])

def test_invalid_waveform_not_promoted():
    p=json.loads((PACKAGE/'examples/LI_recommendation.json').read_text())
    bad=[r for r in p['candidates'] if r['assessment']['evaluation_status']=='UNSUPPORTED']
    assert bad and all(r['assessment']['compliance_status']=='INDETERMINATE' and r['score'] is None and rank_key(r)[0]==2 for r in bad)
    for row in bad:
        ref=row['waveform_reference'];z=np.load(PACKAGE/'examples'/ref['path'])
        m=evaluate(z['time_s'],z['voltage_V'],'LI',target_crest_V=p['request']['target_crest_V'])
        assert m['waveform_status']=='INDETERMINATE'

def test_real_ml_disagreement_preserved():
    fixture=json.loads((PACKAGE/'examples/ML_boundary_disagreement.json').read_text())
    cat=Catalog();request=normalize_request(fixture['request'],cat)
    entry=next(r for r in cat.entries_for_request(request) if r['candidate_id']==fixture['candidate_id'])
    row,_=evaluate_candidate(request,entry,cat,PredictionStack())
    assert 'ML_REFERENCE_COMPLIANCE_DISAGREEMENT' in row['reason_codes']
    assert row['assessment']['compliance_status']=='FAIL' and row['ml_score']['scalar_limits_pass']
    assert not row['eligible_for_hardware_recommendation']

@pytest.mark.parametrize('mode',['LI','SI'])
@pytest.mark.parametrize('polarity',[-1,1])
@pytest.mark.parametrize('relative,expected',[(.97-1e-8,False),(.97,True),(.97+1e-8,True),(1.03-1e-8,True),(1.03,True),(1.03+1e-8,False)])
def test_shared_evaluator_crest_boundaries(mode,polarity,relative,expected):
    front,tail=LIMITS[mode]['nominal_s']
    t=np.array([0,.1*front,.3*front,.9*front,front,(front+tail)/2,tail,2*tail,4*tail])
    v=np.array([0,.1,.3,.9,1,.7,.5,.15,.01])*relative*1e6*polarity
    m=evaluate(t,v,mode,polarity,target_crest_V=1e6)
    assert m['waveform_status']=='VALID_CLEAN_FULL_IMPULSE'
    assert m['checks']['crest']==expected
    assert m['compliance_status']==('PASS' if expected else 'FAIL')

def test_compliance_precedes_opaque_score():
    p=json.loads((PACKAGE/'examples/SI_recommendation.json').read_text())
    a=copy.deepcopy(p['best_configuration'])
    b=copy.deepcopy(next(r for r in p['candidates'] if r['ranking_tier']==1))
    a['score']['J']=100;b['score']['J']=0
    assert rank_key(a)<rank_key(b)

def test_catalog_identity_rejects_duplicate_or_nonlinear_entries(catalog):
    entries=copy.deepcopy(catalog.entries('SI','GSHUNT_v0'))
    with pytest.raises(ValueError):catalog._validate_entries([entries[0],entries[0]],'SI','GSHUNT_v0')
    entries[0]['amplitude_law']='NONLINEAR_UNVERIFIED'
    with pytest.raises(ValueError):catalog._validate_entries(entries,'SI','GSHUNT_v0')
