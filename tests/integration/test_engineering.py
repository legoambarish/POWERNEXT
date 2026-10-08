"""Independent release gates for definitions, workflow invariants and evidence."""
import copy,hashlib,io,json,os,zipfile
from pathlib import Path
import numpy as np
import pytest
from scipy.optimize import brentq
from scipy.linalg import expm
import powernext_config as config
from physics_engine.evaluator import evaluate,LIMITS
from physics_engine.target import nominal_target
from physics_engine import Configuration,Setup,simulate
from powernext_optimizer.assessment import parameter_score
from powernext_app.service import Application
from powernext_app.engineering import discover,verify_discovery,predict_configuration,next_adjustment,load_discovery
from powernext_app.evidence import build_bundle,reopen_bundle
from powernext_app.bench import predict_bench,compare_bench
from powernext_ml.measurement_quality import inspect_trace
from powernext_integrity import verified_snapshot,file_hash,artifact_bytes,strong_hash

@pytest.mark.parametrize('mode,alpha,beta',[('LI',14000.,2500000.),('SI',320.,16000.)])
@pytest.mark.parametrize('polarity',[1,-1])
def test_independent_double_exponential_definitions(mode,alpha,beta,polarity):
    # Independent analytic extremum + scalar root solver, not the target helper.
    peak_time=np.log(beta/alpha)/(beta-alpha)
    raw=lambda t:np.exp(-alpha*t)-np.exp(-beta*t)
    peak=raw(peak_time);voltage=lambda t:raw(t)/peak*1e6
    t30=brentq(lambda t:voltage(t)-3e5,0,peak_time,xtol=1e-18)
    t90=brentq(lambda t:voltage(t)-9e5,0,peak_time,xtol=1e-18)
    t50=brentq(lambda t:voltage(t)-5e5,peak_time,20/alpha,xtol=1e-18)
    origin=t30-(t90-t30)/2
    t=np.unique(np.r_[0,np.geomspace(peak_time*1e-6,15/alpha,18000),peak_time,t30,t90,t50])
    shift=17e-6;baseline=43.
    m=evaluate(t+shift,polarity*voltage(t)+baseline,mode,polarity,beginning_s=shift,baseline_V=baseline,target_crest_V=1e6)
    assert m['waveform_status']=='VALID_CLEAN_FULL_IMPULSE'
    assert m['crest_magnitude_V']==pytest.approx(1e6,rel=1e-12)
    if mode=='LI':
        assert m['T1_s']==pytest.approx((t90-t30)/.6,rel=1e-9)
        assert m['virtual_origin_s']==pytest.approx(origin+shift,abs=1e-14)
        assert m['T2_s']==pytest.approx(t50-origin,rel=1e-9)
        assert m['T1_s']!=pytest.approx(peak_time,rel=.01)
    else:
        assert m['Tp_s']==pytest.approx(peak_time,rel=1e-12)
        assert m['T2_s']==pytest.approx(t50,rel=1e-9)

@pytest.mark.parametrize('mode',['LI','SI'])
def test_target_matches_independent_evaluation_and_legacy_profile(mode):
    p=nominal_target(mode,1e6,-1);m=evaluate(p['time_s'],p['voltage_V'],mode,-1,target_crest_V=1e6)
    assert m['compliance_status']=='PASS'
    assert m['T1_s' if mode=='LI' else 'Tp_s']==pytest.approx(1.2e-6 if mode=='LI' else 250e-6,rel=1e-7)
    assert m['T2_s']==pytest.approx(50e-6 if mode=='LI' else .0025,rel=1e-7)

@pytest.mark.parametrize('mode',['LI','SI'])
def test_inclusive_scalar_boundaries_without_tolerance_relaxation(mode):
    front='T1_s' if mode=='LI' else 'Tp_s';bounds=LIMITS[mode]
    for field,interval in [('crest_V',(970000.,1030000.)),(front,bounds['front_s']),('T2_s',bounds['tail_s'])]:
        for j,edge in enumerate(interval):
            v=dict(crest_V=1e6,**{front:bounds['nominal_s'][0]},T2_s=bounds['nominal_s'][1]);v[field]=edge
            assert parameter_score(v,mode,1e6,.03)['scalar_limits_pass']
            v[field]=np.nextafter(edge,-np.inf if j==0 else np.inf)
            assert not parameter_score(v,mode,1e6,.03)['scalar_limits_pass']

@pytest.mark.parametrize('topology',['GSHUNT_v0','OSHUNT_v0'])
def test_independent_two_node_capacitor_matrix(topology):
    c=Configuration('SI',9,150000,3700,5000,topology)
    s=Setup(.85e-9,.5e-9,.15e-9,0,'ADDITIONAL_DISJOINT')
    r=simulate(c,s,n_points=1600,solver='modal');cg=.5e-6/9;cl=1.98e-9;rf=9*3700.;rt=9*5000.
    # KCL equations independently stamped, without Network or analytic rates.
    matrix=np.array([[-1/rf/cg,1/rf/cg],[1/rf/cl,-1/rf/cl]])
    matrix[0 if topology=='GSHUNT_v0' else 1,0 if topology=='GSHUNT_v0' else 1]-=1/rt/(cg if topology=='GSHUNT_v0' else cl)
    indices=np.linspace(0,len(r.arrays['time_s'])-1,50,dtype=int)
    expected=np.array([(expm(matrix*r.arrays['time_s'][i])@np.array([9*150000.,0]))[1] for i in indices])
    assert np.allclose(expected,r.arrays['voltage_V'][indices],rtol=1e-8,atol=1e-7)

def test_snapshot_consumes_verified_bytes_and_detects_same_mtime_replacement(tmp_path):
    p=tmp_path/'model.bin';p.write_bytes(b'ABCD');identity=strong_hash(p);stamp=p.stat()
    with pytest.raises(ValueError,match='changed during'):
        with verified_snapshot({p:identity}):
            p.write_bytes(b'WXYZ');os.utime(p,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
            assert artifact_bytes(p)==b'ABCD'
            assert file_hash(p)==identity
    assert file_hash(p)!=identity

@pytest.fixture(scope='module')
def app(tmp_path_factory):
    a=Application(tmp_path_factory.mktemp('integration'),workers=1)
    yield a
    a.close()

@pytest.fixture(scope='module')
def scenario(app):
    result=json.loads((config.DEMOS/'SI_recommendation.json').read_text())
    return dict(configuration=result['best_configuration']['configuration'],setup=result['request']['setup'],target_crest_V=result['request']['target_crest_V'])

def test_single_batch_and_fixed_charge_verification(app,scenario):
    p=predict_configuration(app,scenario);assert p['ml_prediction'] and p['physics_reference']['metrics']['compliance_status']=='PASS'
    scenarios=[copy.deepcopy(scenario) for _ in range(3)]
    for i,s in enumerate(scenarios):s['setup']['dut_capacitance_F']*=.9+i*.1
    record=discover(app,dict(scenarios=scenarios,policy='FIXED_SETTING',notes='Explicit test range'))
    assert record['screen']['physics_simulations']==0 and not record['screen']['final_optimizer_pruning']
    verified=verify_discovery(app,record['discovery_id'],[0,2])
    assert len(verified['verifications'])==2
    assert all(v['configuration']==scenario['configuration'] for v in verified['verifications'].values())
    assert load_discovery(app,record['discovery_id'])['verifications']=={} # immutable prior record
    scenarios[1]['configuration']['stage_charge_V']+=1
    with pytest.raises(ValueError,match='hold stages'):discover(app,dict(scenarios=scenarios,policy='FIXED_SETTING'))

def test_explorer_ood_is_not_hidden(app,scenario):
    s=copy.deepcopy(scenario);s['setup']['dut_capacitance_F']=1e-3
    r=discover(app,dict(scenarios=[s],policy='EXPLICIT_SCENARIOS'))
    assert r['screen']['rows'][0]['status']=='ABSTAIN'
    assert len(r['scenarios'])==1

def test_complete_measurement_export_reopen(app,scenario):
    run=app.load_demo('si')['run_id'];p=predict_configuration(app,scenario);wave=p['waveform_arrays']
    # Deliberately explicit synthetic import; never relabel as actual laboratory data.
    csv='time,voltage\n'+''.join(f'{t:.17g},{v:.17g}\n' for t,v in zip(wave['time_s'],wave['voltage_V']))
    meta=dict(shot_id='SYNTHETIC_ROUNDTRIP',setup_id='test',shot_series_id='series',acquisition_time_utc='2026-10-08T00:00:00Z',source_organization='Software test',configuration=scenario['configuration'],setup=scenario['setup'],provenance={'evidence_kind':'SYNTHETIC_TEST'},measurement=dict(time_column='time',voltage_column='voltage',time_unit='s',voltage_unit='V',voltage_scale_to_DUT=1,divider_id='not physical',digitizer_id='not physical',channel_id='generated',measurement_plane='DUT',baseline_V=0,beginning_s=0,polarity=1,calibration_reference='synthetic test only'))
    raw_meta=json.dumps(meta,indent=3)+'\n'
    imported=app.import_measurement(run,csv,meta,raw_meta);mid=imported['measurement_id']
    bundle=build_bundle(app,run,'<p>Test report</p>');opened=reopen_bundle(app,bundle)['run_id']
    assert app.store.result_path(run).read_bytes()==app.store.result_path(opened).read_bytes()
    original=app.measured_waveform(run,mid);restored=app.measured_waveform(opened,mid)
    assert original==restored
    folder=app.store.directory(opened)/'measurements'/mid
    assert (folder/'raw_export.csv').read_bytes()==csv.encode()
    assert (folder/'source_metadata.json').read_bytes()==raw_meta.encode()
    assert not restored['record']['regression_eligible']
    assert app.get_run(opened)['run']['source']=='REOPENED_EVIDENCE'
    bad=io.BytesIO()
    with zipfile.ZipFile(bad,'w') as z:z.writestr('../escape.json','{}')
    with pytest.raises(ValueError):reopen_bundle(app,bad.getvalue())

def test_polarity_quality_and_tail_diagnostics():
    t=np.linspace(0,100e-6,100);v=np.r_[np.linspace(0,1000,90),np.full(10,1000.)]
    meta={'configuration':{'polarity':-1},'measurement':dict(polarity=1,baseline_V=0,beginning_s=0,time_column='time(ns)',voltage_column='voltage(kV)',time_unit='us',voltage_unit='V')}
    flags={r['code'] for r in inspect_trace(t,v,meta)['flags']}
    assert {'POLARITY_METADATA_CONFLICT','POSSIBLE_CLIPPING_OR_FLAT_PEAK','TAIL_NOT_CAPTURED','HEADER_UNIT_CONFLICT'}<=flags

def test_bench_is_separate_and_trace_export_is_complete():
    params=dict(charge_V=5,generator_C_F=1e-6,load_C_F=100e-9,front_R_ohm=330,tail_R_ohm=4700)
    p=predict_bench(params);assert 4<p['metrics']['crest_magnitude_V']<4.5
    assert p['stored_energy_J']==pytest.approx(12.5e-6)
    assert p['metrics']['compliance_status']=='NOT_APPLICABLE_BENCH'
    csv='time_s,voltage_V\n'+''.join(f'{t},{v}\n' for t,v in zip(p['time_s'],p['voltage_V']))
    r=compare_bench(params,csv,'synthetic_fixture.csv');assert r['rmse_V']<1e-12 and r['raw_csv']==csv
    with pytest.raises(ValueError):predict_bench(dict(params,charge_V=500))

def test_next_adjustment_uses_evaluated_catalog_and_keeps_setup(app,scenario):
    from powernext_optimizer.service import recommend
    q=json.loads((config.DEMOS/'SI_request.json').read_text())
    q.update(available_front_per_stage_ohm=[3700],available_tail_per_stage_ohm=[5000])
    result=recommend(q,workers=1,progress=False);data=app.store.create(result.payload['request'])
    path=app.store.directory(data['run_id'])/'result.json';result.save(path);app.store.finish(data,path)
    current=dict(scenario['configuration'],stage_charge_V=100000)
    answer=next_adjustment(app,data['run_id'],current)
    assert answer['passing_alternative_exists'] and answer['catalog_count']==14
    best=answer['alternatives'][0]
    assert best['hardware_changes']==0 and best['changes'][0]['field']=='stage_charge_V'
    assert best['expected_metrics']['compliance_status']=='PASS'
    assert answer['current']['setup']==result.payload['request']['setup']
    for field,value in [('polarity',-1),('topology_id','OSHUNT_v0'),('impulse_type','LI')]:
        with pytest.raises(ValueError,match='differs from the saved request'):
            next_adjustment(app,data['run_id'],dict(current,**{field:value}))
    renamed=copy.deepcopy(result.payload['request']);renamed['request_id']='different label only'
    assert any(r['run_id']==data['run_id'] and r['same_stack'] for r in app.validate(renamed)['previous_exact_cases'])
