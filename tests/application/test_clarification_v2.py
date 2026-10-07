"""Meaningful application regressions for the expanded catalog and import path."""
import copy,json
import numpy as np
import pytest
from powernext_app.service import Application
from powernext_app.common import OPTIMIZER,read_json
from powernext_ml.measured import ingest_measurement,adaptation_readiness
from powernext_ml.physics_adapter import ProvisionalAdapter
from physics_engine.target import nominal_target

@pytest.fixture(scope='module')
def app(tmp_path_factory):
    a=Application(tmp_path_factory.mktemp('clarification_app'))
    yield a
    a.close()

@pytest.mark.parametrize('demo,mode',[('li','LI'),('si','SI')])
def test_mathematical_target_keeps_saved_waveform_and_timing_definitions(app,demo,mode):
    rid=app.load_demo(demo)['run_id'];p=app.store.result(rid);r=p['best_configuration']
    before=app.store.result_path(rid).read_bytes();wave=app.waveform(rid,r['candidate_id']);target=wave['target']
    assert target['evidence_domain']=='MATHEMATICAL_REFERENCE' and not target['hardware_prediction']
    assert wave['metrics']==r['prediction']['physics_reference']['metrics']
    assert target['metrics']['compliance_status']=='PASS'
    assert abs(target['metrics']['T1_s' if mode=='LI' else 'Tp_s']/(1.2e-6 if mode=='LI' else 250e-6)-1)<1e-7
    assert app.store.result_path(rid).read_bytes()==before
    if demo=='li':assert r['tail_recipe']['component_values_ohm']==[180,520]

def test_screening_is_model_only_and_never_mutates_a_final_request(app,monkeypatch):
    rid=app.load_demo('si')['run_id'];p=app.store.result(rid);row=p['best_configuration'];before=copy.deepcopy(p['request'])
    scenarios=[dict(scenario_id='in_domain',configuration=row['configuration'],setup=p['request']['setup'],target_crest_V=p['request']['target_crest_V'])]
    bad=copy.deepcopy(scenarios[0]);bad['setup']['dut_capacitance_F']=50e-9;bad['scenario_id']='ood';scenarios.append(bad)
    monkeypatch.setattr(ProvisionalAdapter,'simulate',lambda *a,**kw:(_ for _ in ()).throw(AssertionError('No physics allowed in screen')))
    out=app.screen_scenarios(scenarios)
    assert out['physics_simulations']==0 and not out['final_optimizer_pruning']
    assert out['rows'][0]['status']=='ML_SCREEN_ONLY' and out['rows'][1]['status']=='ABSTAIN'
    assert all(r['requires_physics_verification'] and not r['numerical_compliance_verified'] and not r['eligible_for_hardware_recommendation'] for r in out['rows'])
    assert p['request']==before

def import_fixture(tmp_path,mode,polarity,kind,disturbance=None):
    request=read_json(OPTIMIZER/f'examples/{mode}_request.json')
    c=dict(impulse_type=mode,polarity=polarity,stages=9,stage_charge_V=100000,front_per_stage_ohm=30 if mode=='LI' else 3700,tail_per_stage_ohm=180 if mode=='LI' else 5000,recipe_id='DEV_UNIFORM_SINGLE_v2',topology_id='GSHUNT_v0')
    target=nominal_target(mode,100000,polarity);t=np.array(target['time_s']);v=np.array(target['voltage_V'])
    if disturbance=='noisy':v[len(v)//2:len(v)//2+3]*=[.5,1.5,.5]
    if disturbance=='truncated':t=t[:np.argmax(abs(v))+1];v=v[:len(t)]
    raw='time,voltage\r\n'+''.join(f'{x:.17g},{y:.17g}\r\n' for x,y in zip(t,v))
    metadata=dict(shot_id='SYNTHETIC_REGRESSION_FIXTURE',setup_id='FIXTURE_ONLY',shot_series_id='FIXTURE_ONLY',acquisition_time_utc='2026-10-04T00:00:00Z',source_organization='CPRI' if kind=='ACTUAL_LABORATORY_EXPORT' else 'TEST_FIXTURE',configuration=c,setup=request['setup'],provenance=dict(evidence_kind=kind,note='Synthetic unit-test fixture even when exercising a claimed CPRI source'),measurement=dict(time_column='time',voltage_column='voltage',time_unit='s',voltage_unit='V',voltage_scale_to_DUT=1,divider_id='TEST',digitizer_id='TEST',channel_id='TEST',measurement_plane='DUT',baseline_V=0,beginning_s=0,polarity=polarity,calibration_reference='TEST_NOT_CALIBRATED'))
    (tmp_path/'raw.csv').write_bytes(raw.encode());(tmp_path/'meta.json').write_text(json.dumps(metadata),encoding='utf-8')
    r=ingest_measurement(tmp_path/'raw.csv',tmp_path/'meta.json',tmp_path/'archive')
    assert (tmp_path/'archive/raw_export.csv').read_bytes()==raw.encode()
    return r

@pytest.mark.parametrize('kind,domain',[('SYNTHETIC_TEST','SYNTHETIC_IMPORT'),('BENCH_EXPERIMENT','BENCH_MEASURED_UNVERIFIED'),('ACTUAL_LABORATORY_EXPORT','CPRI_MEASURED_CLAIMED')])
@pytest.mark.parametrize('mode,polarity',[('LI',1),('LI',-1),('SI',1),('SI',-1)])
def test_clean_trace_diagnostics_are_useful_but_never_qualified(tmp_path,kind,domain,mode,polarity):
    r=import_fixture(tmp_path,mode,polarity,kind)
    assert r['evidence_domain']==domain and not r['regression_eligible']
    assert r['local_evaluation']['compliance_status']=='INDETERMINATE'
    d=r['clean_trace_diagnostics'];assert d['status']=='UNQUALIFIED_CLEAN_TRACE_DIAGNOSTIC' and d['compliance_status']=='NOT_QUALIFIED'
    key='T1_s' if mode=='LI' else 'Tp_s';nominal=1.2e-6 if mode=='LI' else 250e-6
    assert abs(d['metrics'][key]/nominal-1)<1e-7
    assert r['predicted_comparison']['status']=='PROVISIONAL_MODEL_COMPARISON'
    assert r['predicted_comparison']['voltage_rmse_V']>=0 and not r['predicted_comparison']['calibration_fitted']
    if kind=='ACTUAL_LABORATORY_EXPORT':assert not adaptation_readiness([r])['ready']
    else:
        with pytest.raises(ValueError,match='mix'):adaptation_readiness([r])

@pytest.mark.parametrize('disturbance',['noisy','truncated'])
def test_unsupported_imports_do_not_acquire_timing_labels(tmp_path,disturbance):
    r=import_fixture(tmp_path,'LI',1,'SYNTHETIC_TEST',disturbance)
    assert r['clean_trace_diagnostics']['status']=='UNSUPPORTED_TRACE'
    assert r['clean_trace_diagnostics']['metrics']['T1_s'] is None
    assert not r['regression_eligible']

def test_source_claim_cannot_enable_training_gate():
    records=[dict(evidence_domain='CPRI_MEASURED_CLAIMED',regression_eligible=True,physical_profile_verified=True,metadata={'setup_id':str(i)},source_identity_policy='USER_SUPPLIED_NOT_AUTHENTICATED') for i in range(12)]
    assert 'UNAUTHENTICATED_SOURCE' in adaptation_readiness(records)['reason_codes']

def test_candidate_cache_verifies_bytes_and_detaches_served_metrics(app):
    import os
    rid=app.load_demo('si')['run_id'];p=app.store.result(rid);cid=p['best_configuration']['candidate_id']
    wave=app.waveform(rid,cid);crest=wave['metrics']['crest_magnitude_V'];wave['metrics']['crest_magnitude_V']=-1
    assert app.waveform(rid,cid)['metrics']['crest_magnitude_V']==crest
    path=app.store.result_path(rid);stamp=path.stat();raw=path.read_bytes();path.write_bytes(raw+b' ')
    os.utime(path,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
    with pytest.raises(ValueError,match='integrity'):app.waveform(rid,cid)
