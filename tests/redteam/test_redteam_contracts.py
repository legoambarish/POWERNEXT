"""Independent regression contracts. All records here are synthetic test fixtures."""
from pathlib import Path
import sys,json,copy
import numpy as np
import pytest
ROOT=Path(__file__).resolve().parents[2]
for name in ['Physics','ML','Optimizer','Application']:
    sys.path.insert(0,str(ROOT/'powernext'/name.lower()))
from powernext_ml import inference
from powernext_ml.measured import ingest_measurement
from powernext_optimizer.prediction import PredictionStack
from powernext_app.service import Application
from powernext_app.process import stream_process
from powernext_optimizer.catalog import Catalog,normalize_request

def test_declared_resistor_availability_is_honored():
    q=json.loads((ROOT/'powernext/optimizer/examples/SI_request.json').read_text())
    q.update(available_front_per_stage_ohm=[3700],available_tail_per_stage_ohm=[5000])
    catalog=Catalog();normalized=normalize_request(q,catalog)
    rows=catalog.entries_for_request(normalized)
    assert len(rows)==14 and {r['configuration']['front_per_stage_ohm'] for r in rows}=={3700}

def test_missing_inventory_is_not_called_missing_approved_recipe():
    from powernext_optimizer.service import recommend
    q=json.loads((ROOT/'powernext/optimizer/examples/SI_request.json').read_text())
    q['available_tail_per_stage_ohm']=[]
    result=recommend(q,progress=False).payload
    assert result['status']=='NO_COMPLIANT_CONFIGURATION'
    assert result['candidates']==[] and 'NO_AVAILABLE_RESISTOR_COMBINATION' in result['reason_codes']

def test_unfinished_process_is_stopped_without_partial_result(tmp_path):
    import io,os,time
    sentinel=tmp_path/'should_not_complete.txt'
    program='import time,pathlib; print("started",flush=True); time.sleep(5); pathlib.Path('+repr(str(sentinel))+').write_text("bad")'
    start=time.monotonic()
    with pytest.raises(TimeoutError,match='No partial recommendation'):
        stream_process([sys.executable,'-c',program],cwd=tmp_path,env=os.environ.copy(),output=io.StringIO(),on_progress=lambda _:None,timeout_seconds=.25)
    assert time.monotonic()-start<4 and not sentinel.exists()

def request():
    return json.loads((ROOT/'powernext/ml/examples/SI_request.json').read_text())

def metadata():
    r=request()
    # Deliberately spoofed claims exercise an untrusted upload. NOT real lab data.
    return dict(shot_id='SYNTHETIC_RED_TEAM_ONLY',setup_id='SYNTHETIC',shot_series_id='SYNTHETIC',acquisition_time_utc='2026-10-03T00:00:00Z',source_organization='CPRI',configuration=r['configuration'],setup=r['setup'],
        provenance={'evidence_kind':'ACTUAL_LABORATORY_EXPORT','note':'DELIBERATE FALSE CLAIM IN A SYNTHETIC TEST FIXTURE; NOT CPRI DATA'},
        measurement=dict(time_column='time',voltage_column='voltage',time_unit='us',voltage_unit='kV',voltage_scale_to_DUT=1.,divider_id='SYNTHETIC',digitizer_id='SYNTHETIC',channel_id='TEST',measurement_plane='DUT',baseline_V=0.,beginning_s=0.,polarity=1,calibration_reference='SYNTHETIC'),
        analyzer_labels=dict(crest_V=1300000.,Tp_s=250e-6,T1_s=None,T2_s=2500e-6,qualification_evidence='unverified user string',evaluation_curve_id='nonexistent',waveform_status='VALID_QUALIFIED_MEASUREMENT'))

def test_analyzer_claim_cannot_self_qualify_clipped_trace(tmp_path):
    m=metadata();(tmp_path/'meta.json').write_text(json.dumps(m))
    (tmp_path/'raw.csv').write_text('time,voltage\n'+'\n'.join(f'{i},1300' for i in range(12)))
    record=ingest_measurement(tmp_path/'raw.csv',tmp_path/'meta.json',tmp_path/'archive')
    assert not record['regression_eligible'], 'Unverified labels promoted a clipped flat trace to eligible'
    assert record['calibration_status']=='NOT_FITTED'

@pytest.mark.parametrize('field,value',[('stages',-4),('stage_charge_V',float('inf')),('front_per_stage_ohm',-2),('tail_per_stage_ohm',0),('stages',True)])
def test_impossible_measurement_configuration_rejected(tmp_path,field,value):
    m=metadata();m['configuration'][field]=value
    (tmp_path/'meta.json').write_text(json.dumps(m));(tmp_path/'raw.csv').write_text('time,voltage\n'+'\n'.join(f'{i},{i}' for i in range(12)))
    with pytest.raises(ValueError):ingest_measurement(tmp_path/'raw.csv',tmp_path/'meta.json',tmp_path/'archive')

def test_wrong_topology_model_rejected(tmp_path):
    selection=json.loads((ROOT/'powernext/ml/results/simulation_v2/selected_models.json').read_text())
    selection['SI:GSHUNT_v0']=selection['SI:OSHUNT_v0']
    path=tmp_path/'selection.json';path.write_text(json.dumps(selection))
    out=inference.predict(request(),ROOT/'powernext/ml/registry/simulation_v2',path)
    assert out['prediction_source']=='PHYSICS'
    assert 'MODEL_UNAVAILABLE_OR_INCOMPATIBLE' in out['reason_codes']
    assert out['ml_prediction'] is None

def test_nonfinite_model_output_not_exposed(monkeypatch):
    real=inference.load_model
    class Invalid:
        def ood(self,row):return [False]
        def predict(self,row):return np.array([[float('nan'),250.,2500.]])
    def fake(*args,**kwargs):
        model,card=real(*args,**kwargs)
        # Retain model identity attributes after routing validation is added.
        for k in ['domain','mode','topology_version']:
            if hasattr(model,k):setattr(Invalid,k,getattr(model,k))
        return Invalid(),card
    monkeypatch.setattr(inference,'load_model',fake)
    out=inference.predict(request(),ROOT/'powernext/ml/registry/simulation_v2',ROOT/'powernext/ml/results/simulation_v2/selected_models.json')
    assert out['ml_prediction'] is None
    json.dumps(out,allow_nan=False)

@pytest.mark.parametrize('r',[{},[],None,{'configuration':{},'setup':{}},{'configuration':None,'setup':None}])
def test_malformed_prediction_envelope_returns_invalid(r):
    out=inference.predict(r,ROOT/'powernext/ml/registry/simulation_v2')
    assert out['status']=='INVALID_INPUT'

def test_mutated_selection_cannot_use_stale_fingerprint(tmp_path):
    path=tmp_path/'selected.json';path.write_text((ROOT/'powernext/ml/results/simulation_v2/selected_models.json').read_text())
    stack=PredictionStack(selection=path,cache=tmp_path/'cache')
    path.write_text('{}')
    with pytest.raises(ValueError,match='(?i)(changed|drift|mutat|restart)'):
        stack.call(request()['configuration'],request()['setup'])

def test_history_optimizer_version_mismatch_is_visible(tmp_path):
    app=Application(tmp_path/'app')
    try:
        data=app.load_demo('si');saved=app.store.result(data['run_id'])
        saved['optimizer_source_hashes']={'service.py':'deliberately-obsolete'}
        saved['stack_sha256']=app.stack.fingerprint
        # Isolate compatibility logic from file integrity; no saved artifacts modified.
        app.store.result=lambda _:saved
        out=app.get_run(data['run_id'])
        assert out['artifact_compatibility']!='MATCHES_CURRENT_STACK'
    finally:app.close()

def test_baseline_never_recomputed_under_changed_physics(tmp_path):
    app=Application(tmp_path/'app')
    try:
        data=app.load_demo('si');saved=app.store.result(data['run_id']);row=saved['best_configuration']
        saved['provenance']['physics']['baseline_sha256']='different'
        app.candidate=lambda *_:(saved,row)
        assert app.evidence(data['run_id'],row['candidate_id'])['baseline'] is None
    finally:app.close()

@pytest.mark.parametrize('values',[[521],[3700,3700],[True],['3700'],[float('nan')]])
def test_unconfirmed_or_malformed_inventory_rejected(values):
    q=json.loads((ROOT/'powernext/optimizer/examples/SI_request.json').read_text());q['available_front_per_stage_ohm']=values
    with pytest.raises(ValueError):normalize_request(q,Catalog())
