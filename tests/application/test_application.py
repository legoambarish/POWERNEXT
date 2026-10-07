"""Independent consumer checks against frozen upstream artifacts and APIs."""
import base64,copy,io,json,threading,time,zipfile
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from pathlib import Path
import numpy as np
import pytest
from powernext_app.common import OPTIMIZER,read_json,write_json,file_hash,safe_child
from powernext_app.fixtures import DEMOS
from powernext_app.service import Application
from powernext_app.store import RunStore
from powernext_app.server import make_server
from powernext_app.reports import html_report,bundle_zip
from powernext_optimizer.assessment import rank_key
from physics_engine.evaluator import evaluate

@pytest.fixture(scope='module')
def app(tmp_path_factory):
    a=Application(tmp_path_factory.mktemp('app'))
    yield a
    a.close()

@pytest.fixture(scope='module')
def runs(app):
    return {d['id']:app.load_demo(d['id'])['run_id'] for d in DEMOS}

@pytest.mark.parametrize('identifier',[d['id'] for d in DEMOS])
def test_fixtures_are_exact_original_bytes(app,runs,identifier):
    d=next(d for d in DEMOS if d['id']==identifier)
    source=OPTIMIZER/'examples'/d['result']
    assert app.store.result_path(runs[identifier]).read_bytes()==source.read_bytes()
    b=app.get_run(runs[identifier]);p=b['result']
    assert b['artifact_compatibility']=='MATCHES_CURRENT_STACK'
    assert p['stack_sha256']==app.stack.fingerprint
    assert p['candidates']==sorted(p['candidates'],key=rank_key)
    assert len(p['candidates'])==(0 if identifier=='approved' else 588 if identifier=='li' else 84 if identifier=='li_disagreement' else 504)
    assert all(r['recipe_status'].startswith('PROVISIONAL') and not r['hard_constraints']['operator_ready'] for r in p['candidates'])
    assert all(r['equipment_profile_id']==p['request']['equipment_profile_id'] for r in p['candidates'])

@pytest.mark.parametrize('identifier',['si','li','li_disagreement','crest','load','ood','band','infeasible','output_shunt'])
def test_every_waveform_api_and_metric_is_saved_truth(app,runs,identifier):
    """All 504 candidate curves are independently evaluated from served arrays."""
    p=app.store.result(runs[identifier])
    for row in p['candidates']:
        w=app.waveform(runs[identifier],row['candidate_id'])
        assert w['metrics']==row['prediction']['physics_reference']['metrics']
        with np.load(safe_child(app.store.directory(runs[identifier]),row['waveform_reference']['path'])) as z:
            assert np.array_equal(w['time_s'],z['time_s'])
            assert np.array_equal(w['voltage_V'],z['voltage_V'])
        m=evaluate(w['time_s'],w['voltage_V'],p['request']['impulse_type'],p['request']['polarity'],target_crest_V=p['request']['target_crest_V'],curve_id=w['curve_id'])
        for key in ['crest_magnitude_V','T1_s','Tp_s','T2_s','waveform_status','compliance_status']:
            assert m.get(key)==w['metrics'].get(key),(identifier,row['candidate_id'],key)

def test_required_demo_decisions(app,runs):
    p={k:app.store.result(v) for k,v in runs.items()}
    assert p['si']['best_configuration']['configuration']['stages']==9
    assert p['si']['search']['numeric_pass_count']==14
    assert p['crest']['best_configuration']['configuration']['stages']==11
    assert p['load']['best_configuration']['configuration']['stages']==8
    assert p['li_single']['best_configuration'] is None and p['li_single']['closest_noncompliant']
    assert p['li']['search']['numeric_pass_count']==3
    gap=next(r for r in p['li_disagreement']['candidates'] if r['candidate_id']=='cfg_3754ce6cb55b96c7')
    assert 'ML_REFERENCE_COMPLIANCE_DISAGREEMENT' in gap['reason_codes'] and gap['assessment']['compliance_status']=='FAIL'
    assert all(r['prediction']['status']=='PHYSICS_FALLBACK' for r in p['ood']['candidates'])
    assert p['infeasible']['best_configuration'] is None
    b=next(r for r in p['band']['candidates'] if r['candidate_id']=='cfg_1ef05d2a542a16f6');assert b['configuration']['stage_charge_V']==200000
    assert b['prediction']['physics_reference']['metrics']['crest_magnitude_V']<p['band']['request']['target_crest_V']
    assert b['assessment']['compliance_status']=='PASS'
    assert not p['approved']['candidates'] and p['approved']['no_solution']

@pytest.mark.parametrize('identifier',['si','li_disagreement','ood'])
def test_evidence_separates_model_baseline_reference(app,runs,identifier):
    p=app.store.result(runs[identifier]);r=p['best_configuration'] or p['closest_noncompliant']
    if identifier=='li_disagreement':r=next(r for r in p['candidates'] if r['candidate_id']=='cfg_3754ce6cb55b96c7')
    e=app.evidence(runs[identifier],r['candidate_id'])
    assert e['prediction']==r['prediction']
    assert e['baseline']['version']==p['provenance']['physics']['baseline_version']
    assert p['provenance']['physics']==app.catalog.adapter.provenance
    selected=p['provenance']['model_selection'][f"{p['request']['impulse_type']}:{r['topology_id']}"]
    assert e['model_card']['model_id']==selected
    if identifier=='ood':assert e['prediction']['ml_prediction'] is None
    assert e['model_card']['split_counts']['test_rows']>0
    assert e['model_card']['real_data_calibrated'] is False
    if identifier=='li_disagreement':
        assert e['prediction']['ml_prediction']['crest_V']>=.97*p['request']['target_crest_V']
        assert e['prediction']['physics_reference']['metrics']['crest_magnitude_V']<.97*p['request']['target_crest_V']

def test_comparison_is_original_ordering(app,runs):
    p=app.store.result(runs['si']);a,b=p['candidates'][:2]
    c=app.compare(runs['si'],b['candidate_id'],a['candidate_id'])
    assert c['preferred_id']==a['candidate_id']
    assert c['decisive_factor']=='reference conformity score J'

def test_history_and_exact_case_versions(app,runs):
    s=RunStore(app.store.root)
    assert s.result(runs['si'])==app.store.result(runs['si'])
    p=s.result(runs['si']);q=copy.deepcopy(p['request'])
    v=app.validate(q,{'notes':'<operator note>','value_provenance':{'dut_capacitance_F':'estimated'}})
    assert v['request']==q
    assert any(r['run_id']==runs['si'] and r['same_stack'] for r in v['previous_exact_cases'])
    metadata=s.metadata(runs['si']);original=metadata['stack_sha256'];metadata['stack_sha256']='old-stack';s.update(metadata)
    assert any(not r['same_stack'] for r in app.validate(q)['previous_exact_cases'])
    metadata['stack_sha256']=original;s.update(metadata)
    assert s.result(runs['si'])==p

def test_interrupted_run_is_not_promoted(tmp_path):
    s=RunStore(tmp_path);m=s.create({'request_id':'interrupted'})
    s.recover_interrupted()
    assert s.metadata(m['run_id'])['status']=='FAILED'
    with pytest.raises(ValueError):s.result(m['run_id'])

@pytest.mark.parametrize('identifier',['si','li','approved','ood'])
def test_exports_contain_unchanged_results_and_all_curves(app,runs,identifier):
    rid=runs[identifier];html=html_report(app,rid)
    assert 'not an official CPRI test certificate' in html
    assert 'Operational approval not established' in html
    with zipfile.ZipFile(io.BytesIO(bundle_zip(app,rid))) as z:
        assert z.testzip() is None
        assert z.read('result.json')==app.store.result_path(rid).read_bytes()
        p=app.store.result(rid)
        for row in p['candidates']:
            ref=row['waveform_reference'];assert z.read(ref['path'])==safe_child(app.store.directory(rid),ref['path']).read_bytes()
        assert z.read('engineering_report.html').decode()==html
    if identifier!='approved':assert 'data:image/png;base64,' in html

def test_integrity_failure_is_explicit(app):
    rid=app.load_demo('si')['run_id'];p=app.store.result(rid);row=p['candidates'][0]
    file=safe_child(app.store.directory(rid),row['waveform_reference']['path']);file.write_bytes(b'tampered')
    with pytest.raises(ValueError,match='integrity'):app.waveform(rid,row['candidate_id'])
    file=app.store.result_path(rid);file.write_bytes(file.read_bytes()+b' ')
    with pytest.raises(ValueError,match='integrity'):app.get_run(rid)

def test_measured_ingestion_gates_and_byte_preservation(app,runs):
    with pytest.raises(ValueError):app.import_measurement(runs['si'],'time,voltage\n0,0\n',{})
    # Test-only fabricated instrument export exercises importer mechanics, not CPRI evidence.
    q=app.store.result(runs['si']);row=q['candidates'][0]
    raw=b'\xef\xbb\xbftime,voltage\r\n'+b''.join(f'{i},{v}\r\n'.encode() for i,v in enumerate([0,1,4,8,10,8,4,1,0]))
    meta=dict(shot_id='TEST_ONLY_NOT_REAL_CPRI',setup_id='TEST_SETUP',shot_series_id='TEST_ONLY',acquisition_time_utc='2026-10-02T00:00:00Z',source_organization='CPRI',configuration=row['configuration'],setup=q['request']['setup'],provenance={'evidence_kind':'ACTUAL_LABORATORY_EXPORT','note':'TEST FIXTURE ONLY; NOT CPRI EVIDENCE'},measurement=dict(time_column='time',voltage_column='voltage',time_unit='us',voltage_unit='kV',voltage_scale_to_DUT=10,divider_id='TEST_ONLY',digitizer_id='TEST_ONLY',channel_id='TEST_ONLY',measurement_plane='DUT',baseline_V=0,beginning_s=0,polarity=1,calibration_reference='TEST_ONLY'))
    imported=app.import_measurement(runs['si'],raw,meta);shot=imported['measurement_id']
    folder=app.store.directory(runs['si'])/'measurements'/shot
    assert (folder/'raw_export.csv').read_bytes()==raw
    w=app.measured_waveform(runs['si'],shot)
    assert w['voltage_V'][4]==100000 and w['time_s'][4]==4e-6
    assert w['record']['calibration_status']=='NOT_FITTED'
    assert not w['record']['regression_eligible'] and not w['record']['physical_profile_verified']
    assert any(r['measurement_id']==shot for r in app.measurements(runs['si']))
    (folder/'waveform_SI.npz').write_bytes(b'altered')
    with pytest.raises(ValueError,match='integrity'):app.measured_waveform(runs['si'],shot)

@pytest.fixture(scope='module')
def http(app):
    server=make_server(app,0);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    def call(path,body=None,headers=None):
        h={'Content-Type':'application/json',**(headers or {})}
        req=Request(f'http://127.0.0.1:{server.server_port}'+path,data=None if body is None else json.dumps(body).encode(),headers=h)
        return urlopen(req,timeout=120)
    yield call
    server.shutdown();server.server_close();thread.join()

def test_http_and_local_only_contract(http,runs):
    assert json.load(http('/api/meta'))['offline'] is True
    assert 'PowerNext' in http('/').read().decode()
    assert json.load(http('/api/runs/'+runs['si']))['result']['request']['impulse_type']=='SI'
    for path,body,headers in [('/api/meta',None,{'Origin':'https://external.example'}),('/api/meta',None,{'Host':'external.example'}),('/../requirements.txt',None,{}),('/api/validate',{'request':{'target_crest_V':float('nan')}},{})]:
        with pytest.raises(HTTPError) as error:http(path,body,headers)
        assert error.value.code==400
    with pytest.raises(HTTPError) as error:http('/api/no-such-route')
    assert error.value.code==404

@pytest.mark.parametrize('mode,polarity',[('LI',1),('SI',-1)])
def test_real_request_through_http_cli_to_saved_reference(http,app,mode,polarity):
    q=read_json(OPTIMIZER/f'examples/{mode}_request.json');q['polarity']=polarity;q['request_id']=f'APPLICATION_E2E_{mode}_{polarity}'
    validation=json.load(http('/api/validate',{'request':q}));assert validation['catalog_count']==504
    response=http('/api/runs',{'request':q,'annotations':{'notes':'Integration test'}});assert response.status==202
    rid=json.load(response)['run_id'];deadline=time.monotonic()+240
    while time.monotonic()<deadline:
        b=json.load(http('/api/runs/'+rid))
        if b['run']['status'] not in ['QUEUED','RUNNING']:break
        time.sleep(.3)
    assert b['run']['status']=='COMPLETED',b['run']
    assert b['artifact_compatibility']=='MATCHES_CURRENT_STACK'
    p=b['result'];assert p['request']==validation['request']
    assert p['search']['evaluated_count']==504
    assert p['request']['setup']==validation['request']['setup']
    r=p['best_configuration'] or p['closest_noncompliant'];w=json.load(http(f'/api/runs/{rid}/waveform?candidate='+r['candidate_id']))
    assert app.evidence(rid,r['candidate_id'])['baseline']['version']
    if polarity==-1:assert min(w['voltage_V'])<0 and max(w['voltage_V'])<1e-8
    assert http(f'/api/runs/{rid}/export?format=json').read()==app.store.result_path(rid).read_bytes()
    assert (p['best_configuration'] is not None)==(mode=='SI')

@pytest.mark.parametrize('field,value',[('target_crest_V',float('inf')),('polarity',0),('equipment_profile_id','invented'),('topology_id','best'),('tolerance',.5)])
def test_invalid_requests_rejected_before_job(app,field,value):
    q=read_json(OPTIMIZER/'examples/SI_request.json');q[field]=value
    with pytest.raises(ValueError):app.validate(q)
