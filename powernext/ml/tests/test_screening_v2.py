import copy,json
from pathlib import Path
import pytest
from powernext_config import REGISTRY,MODEL_SELECTION,ML
from powernext_ml.physics_adapter import ProvisionalAdapter
from powernext_ml.screening import screen_batch
from powernext_ml.training import load_frame

def scenario():
    return dict(scenario_id='TEST_ONLY',configuration=dict(impulse_type='LI',stages=9,stage_charge_V=184238.3311,front_per_stage_ohm=30,tail_per_stage_ohm=180,topology_id='GSHUNT_v0',recipe_id='HYP_LI_TAIL_180_PAR_520_v1',polarity=1),
                setup=dict(dut_capacitance_F=850e-12,divider_capacitance_F=500e-12,stray_capacitance_F=150e-12,loop_inductance_H=18.5e-6,basic_coverage_assumption='ADDITIONAL_DISJOINT'),target_crest_V=1550e3)

def test_parallel_features_and_identity_are_distinct():
    a=ProvisionalAdapter();p=scenario();s=copy.deepcopy(p);s['configuration']['recipe_id']='DEV_UNIFORM_SINGLE_v2'
    fp=a.features(p['configuration'],p['setup']);fs=a.features(s['configuration'],s['setup'])
    assert fp['tail_parallel']==1 and fs['tail_parallel']==0
    assert fp['Rt_ohm']==pytest.approx(9*180*520/700)
    assert a.shape_identity(p['configuration'],p['setup'])!=a.shape_identity(s['configuration'],s['setup'])

def test_batch_runs_no_simulator_and_cannot_authorize(monkeypatch):
    def forbidden(*args,**kwargs):raise AssertionError('Batch screen called simulator')
    monkeypatch.setattr(ProvisionalAdapter,'simulate',forbidden)
    result=screen_batch([scenario() for _ in range(32)],REGISTRY,MODEL_SELECTION)
    assert result['physics_simulations']==0 and not result['final_optimizer_pruning']
    assert all(r['requires_physics_verification'] and not r['numerical_compliance_verified'] and not r['eligible_for_hardware_recommendation'] for r in result['rows'])
    assert all(r['status']=='ML_SCREEN_ONLY' for r in result['rows'])

def test_ood_screen_abstains_without_claiming_a_failure():
    s=scenario();s['setup']['dut_capacitance_F']=50e-9
    row=screen_batch([s],REGISTRY,MODEL_SELECTION)['rows'][0]
    assert row['status']=='ABSTAIN' and row['prediction'] is None
    assert 'OUTSIDE_TRAINING_SUPPORT' in row['reason_codes']
    assert 'predicted_scalar_bands' not in row

def test_invalid_component_screen_abstains():
    s=scenario();s['configuration']['tail_per_stage_ohm']=133.7142857
    row=screen_batch([s],REGISTRY,MODEL_SELECTION)['rows'][0]
    assert row['status']=='ABSTAIN' and row['prediction'] is None

def test_screen_input_bound():
    with pytest.raises(ValueError):screen_batch([],REGISTRY,MODEL_SELECTION)
    with pytest.raises(ValueError):screen_batch([{}]*4097,REGISTRY,MODEL_SELECTION)

def test_current_dataset_covers_six_values_and_parallel_positives():
    frame,prov=load_frame('simulation',ML/'data/clarification_v2')
    assert prov['equipment_profile_version']=='CPRI_IVG_OCT04_2026_v2'
    assert set(frame.front_per_stage_ohm)=={30,46,180,520,3700,5000}
    assert set(frame.tail_per_stage_ohm)=={30,46,180,520,3700,5000}
    li=frame[frame['mode']=='LI']
    passing=li[(li.front_us>=.84)&(li.front_us<=1.56)&(li.tail_us>=40)&(li.tail_us<=60)]
    assert len(passing)>=20
    assert (passing.tail_parallel==1).any()

def test_current_model_routes_only():
    routes=json.loads(MODEL_SELECTION.read_text())
    assert len(routes)==4
    for model in routes.values():
        card=json.loads((REGISTRY/model/'card.json').read_text())
        assert card['provenance']==ProvisionalAdapter().provenance
        assert 'tail_parallel' in card['feature_order']
        assert not card['hardware_recommendations_enabled'] and not card['real_data_calibrated']

def test_loaded_model_cache_rechecks_content_hash(tmp_path):
    import shutil
    from powernext_ml.registry import load_model_cached
    route=json.loads(MODEL_SELECTION.read_text())['LI:GSHUNT_v0']
    folder=tmp_path/'model';shutil.copytree(REGISTRY/route,folder)
    a,_=load_model_cached(folder,ProvisionalAdapter().provenance)
    b,_=load_model_cached(folder,ProvisionalAdapter().provenance)
    assert a is b
    with (folder/'model.joblib').open('ab') as stream:stream.write(b'changed')
    with pytest.raises(ValueError,match='hash mismatch'):
        load_model_cached(folder,ProvisionalAdapter().provenance)
