"""Benign adversarial inputs, local API only; no physical hardware."""
from test_redteam_contracts import ROOT,metadata,request
import numpy as np
import pytest,json,copy,threading
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from physics_engine.evaluator import evaluate
from powernext_ml.measured import ingest_measurement
from powernext_app.service import Application
from powernext_app.server import make_server

def trace(mode):
    # Analytic double-exponential fixtures; synthetic, not measurement evidence.
    slow,fast=(65e-6,.4e-6) if mode=='LI' else (.003,60e-6)
    t=np.linspace(0,slow*8,15001);v=np.exp(-t/slow)-np.exp(-t/fast)
    return t,v/max(v)*1e6

@pytest.mark.parametrize('mode',['LI','SI'])
def test_translation_and_polarity_invariance(mode):
    t,v=trace(mode);a=evaluate(t,v,mode,target_crest_V=1e6)
    for shift in [-.12,.3]:
      for sign in [-1,1]:
        b=evaluate(t+shift,sign*v,mode,sign,beginning_s=shift,target_crest_V=1e6)
        assert a['compliance_status']==b['compliance_status']
        for key in ['T1_s' if mode=='LI' else 'Tp_s','T2_s']:
            assert b[key]==pytest.approx(a[key],rel=1e-7,abs=1e-12)
    if mode=='SI':assert a['virtual_origin_s'] is None

@pytest.mark.parametrize('mode',['LI','SI'])
@pytest.mark.parametrize('attack',['empty','seven','duplicate','backwards','nan','inf','clipped','tail_missing','front_missing','noise','wrong_polarity','double_peak'])
def test_unsupported_records_never_pass(mode,attack):
    t,v=trace(mode);k=int(np.argmax(v))
    if attack=='empty':t=t[:0];v=v[:0]
    if attack=='seven':t=t[:7];v=v[:7]
    if attack=='duplicate':t[3]=t[2]
    if attack=='backwards':t[3]=-1
    if attack=='nan':v[3]=np.nan
    if attack=='inf':v[3]=np.inf
    if attack=='clipped':v=np.minimum(v,6e5)
    if attack=='tail_missing':t=t[:k+4];v=v[:k+4]
    if attack=='front_missing':t=t[k//2:];v=v[k//2:]
    if attack=='noise':v=v+1e4*np.sin(np.arange(len(t))*2)
    if attack=='wrong_polarity':v=-v
    if attack=='double_peak':v=v+7e5*np.exp(-((t-t[-1]/3)/(t[-1]/80))**2)
    try:r=evaluate(t,v,mode,target_crest_V=1e6)
    except ValueError:return
    assert r['compliance_status']!='PASS'

@pytest.mark.parametrize('case',['units','scale_zero','scale_bool','duplicate','gap','negative_polarity','metadata_list','invalid_date','missing_channel','irregular','large','clipped'])
def test_measured_fixture_never_calibrates(tmp_path,case):
    m=metadata();t,v=trace('SI');t=t[::100];v=v[::100]
    if case=='units':m['measurement']['time_unit']='ms_UNKNOWN'
    if case=='scale_zero':m['measurement']['voltage_scale_to_DUT']=0
    if case=='scale_bool':m['measurement']['voltage_scale_to_DUT']=True
    if case=='duplicate':t[3]=t[2]
    if case=='gap':t[4:]+=.2
    if case=='negative_polarity':m['measurement']['polarity']=-1;v=-v
    if case=='metadata_list':m['measurement']=[]
    if case=='invalid_date':m['acquisition_time_utc']='yesterday'
    if case=='missing_channel':m['measurement']['channel_id']=''
    if case=='irregular':t[4]+=(t[5]-t[4])*.4
    if case=='clipped':v=np.minimum(v,5e5)
    if case=='large':t=np.linspace(0,.04,100000);v=1e6*(np.exp(-t/.003)-np.exp(-t/60e-6))
    (tmp_path/'meta.json').write_text(json.dumps(m));np.savetxt(tmp_path/'raw.csv',np.column_stack([t*1e6,v/1e3]),delimiter=',',header='time,voltage',comments='')
    try:r=ingest_measurement(tmp_path/'raw.csv',tmp_path/'meta.json',tmp_path/'archive')
    except (ValueError,KeyError):return
    assert not r['regression_eligible'] and not r['physical_profile_verified'] and r['calibration_status']=='NOT_FITTED'

@pytest.fixture(scope='module')
def http(tmp_path_factory):
    app=Application(tmp_path_factory.mktemp('redteam_http'));server=make_server(app,0)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    def call(raw):
        req=Request(f'http://127.0.0.1:{server.server_port}/api/validate',data=raw.encode(),headers={'Content-Type':'application/json'})
        try:
            with urlopen(req,timeout=5) as r:return r.status,json.load(r)
        except HTTPError as e:return e.code,json.load(e)
    yield call
    server.shutdown();server.server_close();thread.join();app.close()

@pytest.mark.parametrize('raw',['','{','[]','null','"str"','{"request":NaN}','{"request":Infinity}','{"request":{}}'])
def test_malformed_http_is_explained(http,raw):
    code,p=http(raw);assert code==400 and p.get('error')

@pytest.mark.parametrize('field,value',[('target_crest_V',-1),('target_crest_V',0),('target_crest_V',1e308),('target_crest_V','1300000'),('target_crest_V',True),('target_crest_V',49999.99),('target_crest_V',2400000.01),('impulse_type','FOO'),('equipment_profile_id','../bad'),('topology_id','CPRI_APPROVED')])
def test_invalid_request_fields(http,field,value):
    q=json.loads((ROOT/'powernext/optimizer/examples/SI_request.json').read_text());q[field]=value
    code,p=http(json.dumps({'request':q}));assert code==400 and p.get('error')

@pytest.mark.parametrize('field,value',[('dut_capacitance_F',-1),('loop_inductance_H',-1),('loop_resistance_ohm',-1),('load_resistance_ohm',0),('divider_capacitance_F','500 pF'),('stray_capacitance_F',True)])
def test_invalid_setup_fields(http,field,value):
    q=json.loads((ROOT/'powernext/optimizer/examples/SI_request.json').read_text());q['setup'][field]=value
    code,p=http(json.dumps({'request':q}));assert code==400 and p.get('error')
