"""Acceptance using only this release and loopback HTTP; saves real artifacts."""
from pathlib import Path
import base64,copy,hashlib,io,json,os,subprocess,sys,time,urllib.request,zipfile,sqlite3
import powernext_config as config
from powernext_app.fixtures import DEMOS

ROOT=config.ROOT
OUT=ROOT/'evidence/offline_acceptance'
BASE='http://127.0.0.1:8765'
HTTP=urllib.request.build_opener(urllib.request.ProxyHandler({}))
def load(b):return json.loads(b,parse_constant=lambda v:(_ for _ in ()).throw(ValueError(v)))
def call(path,data=None,raw=False):
    req=urllib.request.Request(BASE+path,data=None if data is None else json.dumps(data,allow_nan=False).encode(),headers={'Content-Type':'application/json'})
    with HTTP.open(req,timeout=30) as r:b=r.read()
    return b if raw else load(b)
def dump(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value,indent=2,allow_nan=False),encoding='utf-8')
def normalized(rows):
    rows=copy.deepcopy(rows)
    for row in rows:row.pop('waveform_reference',None)
    return rows
def wait_run(rid):
    start=time.monotonic();last=0
    while time.monotonic()-start<390:
        b=call('/api/runs/'+rid)
        if b['run']['status'] in ('FAILED','COMPLETED'):return b
        if time.monotonic()-last>25:
            print('RUNNING',rid,round(time.monotonic()-start),b['run']['progress'],flush=True);last=time.monotonic()
        time.sleep(.25)
    raise TimeoutError('Acceptance exceeded application deadline')
def start_server(env,number):
    log=(OUT/f'startup_{number}.log').open('w',encoding='utf-8')
    # Exact README command, no flags, no PATH dependency and no external Python.
    process=subprocess.Popen([r'.\runtime\python.exe','-m','powernext_app'],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
    for _ in range(240):
        if process.poll() is not None:raise RuntimeError((OUT/f'startup_{number}.log').read_text())
        try:
            meta=call('/api/meta')
            assert Path(meta['data_directory']).resolve()==ROOT/'data'
            assert meta['application_version']=='0.4.0+cpri20261004'
            return process,log,meta
        except (OSError,urllib.error.URLError):time.sleep(.25)
    process.terminate();raise TimeoutError('Startup')
def main():
    OUT.mkdir(parents=True,exist_ok=False)
    assert not (ROOT/'data/application.sqlite').exists(),'Use a clean extraction'
    windows=os.environ.get('SystemRoot',r'C:\Windows')
    env={k:v for k,v in os.environ.items() if not k.upper().startswith(('PYTHON','CONDA','VIRTUAL','PIP'))}
    env.update(PATH=windows+r'\System32;'+windows,POWERNEXT_TEST_OFFLINE='1',PYTHONPATH=r'Z:\does_not_exist',PYTHONHOME=r'Z:\does_not_exist',OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1')
    probe="import powernext_config,socket,sys,json,numpy,scipy,pandas,sklearn,matplotlib;from pathlib import Path;assert all(Path(p).resolve().is_relative_to(powernext_config.ROOT) for p in sys.path);s=socket.socket();\ntry:s.connect(('203.0.113.1',80));raise AssertionError('outbound allowed')\nexcept OSError as e:assert 'outbound network disabled' in str(e)\nprint(json.dumps({'python':sys.version,'executable':sys.executable,'sys_path':sys.path,'isolated':sys.flags.isolated,'no_site':sys.flags.no_site,'outbound_socket_block':'PASS','packages':{m.__name__:m.__file__ for m in [numpy,scipy,pandas,sklearn,matplotlib]}},indent=2))"
    p=subprocess.run([str(ROOT/'runtime/python.exe'),'-c',probe],cwd=ROOT,env=env,capture_output=True,text=True,check=True)
    (OUT/'runtime_probe.json').write_text(p.stdout,encoding='utf-8')
    process=log=None;results=[];run_ids=[];import_checks=[];screen_checks=[]
    try:
        process,log,meta=start_server(env,1);dump(OUT/'metadata.json',meta)
        assert (ROOT/'data/application.sqlite').is_file()
        assert b'PowerNext' in call('/',raw=True)
        assert len(meta['model_selection'])==4
        for d in DEMOS:
            print('START DEMO',d['id'],flush=True);start=time.monotonic()
            old=load((config.DEMOS/d['result']).read_bytes())
            imported=call('/api/demos/'+d['id'],{})
            rid=imported['run_id'];run_ids.append(rid)
            b=call('/api/runs/'+rid)
            assert b['result']==old
            assert b['artifact_compatibility']=='MATCHES_CURRENT_STACK'
            assert call('/api/runs/'+rid+'/export?format=json',raw=True)==(config.DEMOS/d['result']).read_bytes()
            folder=OUT/'demos'/d['id'];folder.mkdir(parents=True)
            (folder/'saved.html').write_bytes(call('/api/runs/'+rid+'/export?format=html',raw=True))
            blob=call('/api/runs/'+rid+'/export?format=zip',raw=True)
            with zipfile.ZipFile(io.BytesIO(blob)) as z:assert z.testzip() is None
            (folder/'saved.zip').write_bytes(blob)
            request=load((config.DEMOS/d['request']).read_bytes())
            fresh=call('/api/runs',dict(request=request));run_ids.append(fresh['run_id'])
            live=wait_run(fresh['run_id']);dump(folder/'live_bundle.json',live)
            assert live['run']['status']=='COMPLETED',live['run'].get('error')
            r=live['result'];assert live['artifact_compatibility']=='MATCHES_CURRENT_STACK'
            assert normalized(r['candidates'])==normalized(old['candidates']),'Scientific candidate difference: '+d['id']
            assert r['status']==old['status'] and r['search']==old['search']
            assert (r['best_configuration'] or {}).get('candidate_id')==(old['best_configuration'] or {}).get('candidate_id')
            waves=0
            for row in r['candidates']:
                if row.get('waveform_reference'):
                    wave=call('/api/runs/'+fresh['run_id']+'/waveform?candidate='+row['candidate_id'])
                    assert wave['sample_count']==len(wave['time_s'])==len(wave['voltage_V'])
                    assert wave['metrics']==row['prediction']['physics_reference']['metrics'];waves+=1
                    assert wave['target']['evidence_domain']=='MATHEMATICAL_REFERENCE'
                    assert not wave['target']['hardware_prediction']
            if d['id']=='li':
                row=r['best_configuration']
                scenario=dict(scenario_id='offline_in_domain',configuration=row['configuration'],setup=r['request']['setup'],target_crest_V=r['request']['target_crest_V'])
                outside=copy.deepcopy(scenario);outside['scenario_id']='offline_ood';outside['setup']['dut_capacitance_F']=50e-9
                screen=call('/api/screen',dict(scenarios=[scenario,outside]))
                assert screen['physics_simulations']==0 and not screen['final_optimizer_pruning'] and not screen['hardware_verified']
                assert screen['rows'][0]['status']=='ML_SCREEN_ONLY' and screen['rows'][1]['status']=='ABSTAIN'
                dump(OUT/'ml_screen.json',screen);screen_checks.append('PASS: real trained screening plus OOD, zero physics')
                raw=(ROOT/'examples/import/SYNTHETIC_QA_TRACE.csv').read_bytes()
                metadata=load((ROOT/'examples/import/SYNTHETIC_QA_METADATA.json').read_bytes())
                shot=call('/api/runs/'+fresh['run_id']+'/measurements',dict(csv_base64=base64.b64encode(raw).decode('ascii'),metadata=metadata))
                record=shot['record'];mid=shot['measurement_id']
                assert record['evidence_domain']=='SYNTHETIC_IMPORT' and not record['regression_eligible'] and not record['physical_profile_verified']
                assert record['calibration_status']=='NOT_FITTED' and record['source_identity_policy']=='USER_SUPPLIED_NOT_AUTHENTICATED'
                assert record['clean_trace_diagnostics']['compliance_status']=='NOT_QUALIFIED'
                assert record['predicted_comparison']['status']=='PROVISIONAL_MODEL_COMPARISON'
                assert record['raw_sha256']==hashlib.sha256(raw).hexdigest()
                imported_wave=call('/api/runs/'+fresh['run_id']+'/measurement/'+mid)
                assert imported_wave['record']==record
                assert call('/api/runs/'+fresh['run_id']+'/measurements')[0]['measurement_id']==mid
                dump(OUT/'synthetic_import.json',shot)
                import_checks.append(dict(run_id=fresh['run_id'],measurement_id=mid,status='PASS',source='SYNTHETIC_QA_NOT_A_MEASUREMENT'))
            (folder/'live.html').write_bytes(call('/api/runs/'+fresh['run_id']+'/export?format=html',raw=True))
            blob=call('/api/runs/'+fresh['run_id']+'/export?format=zip',raw=True)
            with zipfile.ZipFile(io.BytesIO(blob)) as z:assert z.testzip() is None
            (folder/'live.zip').write_bytes(blob)
            entry=dict(demo=d['id'],status='PASS',result_status=r['status'],candidates=len(r['candidates']),waveforms=waves,numerical_pass_count=r['search']['numeric_pass_count'],exact_scientific_comparison=True,seconds=round(time.monotonic()-start,3),live_run=fresh['run_id'],saved_demo_run=rid)
            results.append(entry);dump(OUT/'progress.json',results);print(json.dumps(entry),flush=True)
        q=load((config.DEMOS/'SI_request.json').read_bytes())
        q.update(available_front_per_stage_ohm=[3700],available_tail_per_stage_ohm=[5000])
        assert call('/api/validate',dict(request=q))['catalog_count']==14
        r=call('/api/runs',dict(request=q));run_ids.append(r['run_id']);b=wait_run(r['run_id']);dump(OUT/'inventory.json',b)
        assert b['run']['status']=='COMPLETED' and len(b['result']['candidates'])==14
        assert {c['configuration']['front_per_stage_ohm'] for c in b['result']['candidates']}=={3700}
        q['available_front_per_stage_ohm']=[]
        assert call('/api/validate',dict(request=q))['catalog_count']==0
        r=call('/api/runs',dict(request=q));run_ids.append(r['run_id']);b=wait_run(r['run_id']);dump(OUT/'empty_inventory.json',b)
        assert b['run']['status']=='COMPLETED' and b['result']['best_configuration'] is None and b['result']['candidates']==[]
        saved={r['run_id']:r['result_sha256'] for r in call('/api/runs')}
        assert set(run_ids)<=set(saved)
        process.terminate();process.wait(timeout=20);log.close();process=None
        process,log,_=start_server(env,2)
        restarted={r['run_id']:r['result_sha256'] for r in call('/api/runs')}
        assert saved==restarted
        for rid in run_ids:assert call('/api/runs/'+rid)['run']['status']=='COMPLETED'
        for shot in import_checks:
            record=call('/api/runs/'+shot['run_id']+'/measurement/'+shot['measurement_id'])['record']
            assert record['evidence_domain']=='SYNTHETIC_IMPORT' and not record['regression_eligible']
        for name in ['application.sqlite','optimizer_history.sqlite']:
            with sqlite3.connect(ROOT/'data'/name) as db:assert db.execute('PRAGMA quick_check').fetchone()[0]=='ok'
        report=dict(status='PASS',root=str(ROOT),command=r'.\runtime\python.exe -m powernext_app',network_boundary='Application and optimizer workers deny outbound socket connects; loopback allowed. OS adapter not disabled.',runtime='Bundled isolated Python 3.12.14 x64; PATH limited to Windows; invalid external PYTHONPATH and PYTHONHOME ignored',models_loaded=4,demos=results,fresh_inventory_runs=2,persisted_runs=len(saved),restart='PASS',sqlite_quick_check='PASS',exports='JSON + HTML + ZIP; strict finite JSON; ZIP CRC checked',screening=screen_checks,imports=import_checks,nominal_targets='PASS for every returned current waveform',presentation_laptop='Not physically available')
        dump(OUT/'summary.json',report);print('OFFLINE ACCEPTANCE PASS',flush=True)
    finally:
        if process is not None:process.terminate();process.wait(timeout=20)
        if log is not None:log.close()
if __name__=='__main__':main()
