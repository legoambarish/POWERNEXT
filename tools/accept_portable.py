"""Exercise the shipped application through loopback HTTP and Windows launchers.

Uses a separate, explicitly synthetic acceptance data folder. No remote traffic,
hardware operation, or user-history edits. Logs all completed gates.
"""
import argparse,base64,copy,hashlib,io,json,os,subprocess,sys,time,zipfile
from pathlib import Path
from urllib.request import Request,urlopen
import powernext_config as config

def main():
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);p.add_argument('--port',type=int,default=8771);p.add_argument('--keep-running',action='store_true');p.add_argument('--baseline-li',type=Path);a=p.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=True);data=out/'data';base=f'http://127.0.0.1:{a.port}';report=dict(root=str(config.ROOT),runtime=sys.executable,port=a.port,gates=[])
    sys.stdout.reconfigure(encoding='utf-8',errors='replace')
    def gate(name,**detail):
        print('PASS '+name,flush=True);report['gates'].append(dict(name=name,**detail));(out/'acceptance.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    def request(path,value=None,raw=None):
        body=raw if raw is not None else json.dumps(value).encode() if value is not None else None
        req=Request(base+path,data=body,headers={'Content-Type':'application/zip' if raw is not None else 'application/json'})
        with urlopen(req,timeout=120) as r:
            content=r.read();return json.loads(content) if r.headers['Content-Type'].startswith('application/json') else content
    def start():
        log=(out/'server.log').open('ab')
        env=dict(os.environ,POWERNEXT_TEST_OFFLINE='1',PYTHONIOENCODING='utf-8')
        process=subprocess.Popen([str(config.ROOT/'Launch_PowerNext.cmd'),'--no-browser','--port',str(a.port),'--data-dir',str(data)],cwd=out,env=env,stdout=log,stderr=subprocess.STDOUT)
        began=time.monotonic()
        while time.monotonic()-began<45:
            try:
                meta=request('/api/meta');assert Path(meta['data_directory'])==data
                return process,log
            except (OSError,AssertionError):time.sleep(.3)
        raise RuntimeError('Portable server did not start: '+(out/'server.log').read_text(errors='replace'))
    def stop(process,log):
        answer=subprocess.run([str(config.ROOT/'Stop_PowerNext.cmd'),'--data-dir',str(data)],cwd=out,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=410)
        (out/'stop.log').write_bytes(answer.stdout)
        assert answer.returncode==0,answer.stdout.decode(errors='replace')
        process.wait(timeout=20);log.close();assert not (data/'server_connection.json').exists()
    def optimize(name,q,count):
        start_time=time.perf_counter();rid=request('/api/runs',dict(request=q))['run_id'];last=0
        while time.perf_counter()-start_time<390:
            saved=request('/api/runs/'+rid);status=saved['run']['status']
            if status=='COMPLETED':break
            if status=='FAILED':raise RuntimeError(saved['run'].get('error'))
            if time.perf_counter()-start_time-last>20:print(f'RUNNING {name}: {time.perf_counter()-start_time:.0f}s',flush=True);last=time.perf_counter()-start_time
            time.sleep(.5)
        else:raise RuntimeError('Timed out without complete result')
        result=saved['result'];assert saved['artifact_compatibility']=='MATCHES_CURRENT_STACK'
        assert result['search']['evaluated_count']==count==result['search']['catalog_count'] and result['search']['pruned_count']==0
        gate(name,run_id=rid,seconds=time.perf_counter()-start_time,application_elapsed_seconds=saved['run']['elapsed_seconds'],search=result['search'])
        return rid,result
    process,log=start();running=True
    try:
        meta=request('/api/meta');assert len(meta['model_selection'])==4 and meta['offline'] and not meta['hardware_control']
        gate('launch_from_foreign_working_directory',stack=meta['stack_sha256'],application_version=meta['application_version'])
        manifest=subprocess.run([sys.executable,str(config.ROOT/'tests/verify_manifest.py')],cwd=out,capture_output=True)
        assert manifest.returncode==0,manifest.stdout.decode();(out/'manifest_before.json').write_bytes(manifest.stdout)
        q=json.loads((config.DEMOS/'SI_request.json').read_text());rid,result=optimize('SI_complete_504',q,504)
        assert result['search']['numeric_pass_count']==14
        best=result['best_configuration'];scenario=dict(configuration=best['configuration'],setup=result['request']['setup'],target_crest_V=q['target_crest_V'])
        predicted=request('/api/predict',scenario);assert predicted['ml_prediction'] and predicted['physics_reference']['metrics']['compliance_status']=='PASS'
        gate('single_ML_Physics_prediction',metrics=predicted['physics_reference']['metrics'])
        scenarios=[]
        for inductance in [i*40e-6/16 for i in range(17)]:
            for capacitance in [700e-12+i*300e-12/16 for i in range(17)]:
                s=copy.deepcopy(scenario);s['setup'].update(dut_capacitance_F=capacitance,loop_inductance_H=inductance);scenarios.append(s)
        discovery=request('/api/discoveries',dict(scenarios=scenarios,policy='FIXED_SETTING',notes='SYNTHETIC ACCEPTANCE: explicit exploratory ranges, not measured uncertainty'))
        assert discovery['screen']['physics_simulations']==0 and not discovery['screen']['final_optimizer_pruning']
        verified=request(f"/api/discoveries/{discovery['discovery_id']}/verify",dict(indices=discovery['screen']['suggested_physics_indices']))
        assert all(v['configuration']==scenario['configuration'] for v in verified['verifications'].values())
        assert request('/api/discoveries/'+discovery['discovery_id'])['verifications']=={}
        gate('289_fixed_setting_scenarios_and_boundary_Physics',discovery_id=verified['discovery_id'],batch_ms=discovery['screen']['elapsed_ms'],physics_checks=len(verified['verifications']))
        unsupported=copy.deepcopy(scenario);unsupported['setup']['dut_capacitance_F']=1e-3
        ood=request('/api/discoveries',dict(scenarios=[unsupported],policy='EXPLICIT_SCENARIOS'))
        assert ood['screen']['rows'][0]['status']=='ABSTAIN';gate('OOD_abstention')
        current=dict(best['configuration'],stage_charge_V=100000)
        adjustment=request(f'/api/runs/{rid}/next-adjustment',dict(configuration=current));assert adjustment['passing_alternative_exists'] and adjustment['catalog_count']==504
        assert adjustment['alternatives'][0]['hardware_changes']==0
        assert request(f'/api/runs/{rid}/next-measurement')['calibration_enabled'] is False
        gate('next_legal_adjustment_and_measurement_guidance',adjustment=adjustment['alternatives'][0]['changes'])
        wave=predicted['waveform_arrays'];csv='time,voltage\r\n'+''.join(f'{t:.17g},{v:.17g}\r\n' for t,v in zip(wave['time_s'],wave['voltage_V']))
        metadata=dict(shot_id='SYNTHETIC_PORTABLE_ACCEPTANCE',setup_id='acceptance',shot_series_id='software',acquisition_time_utc='2026-10-08T00:00:00Z',source_organization='Software acceptance test',configuration=scenario['configuration'],setup=scenario['setup'],provenance={'evidence_kind':'SYNTHETIC_TEST'},measurement=dict(time_column='time',voltage_column='voltage',time_unit='s',voltage_unit='V',voltage_scale_to_DUT=1,divider_id='not physical',digitizer_id='not physical',channel_id='generated',measurement_plane='DUT',baseline_V=0,beginning_s=0,polarity=1,calibration_reference='Synthetic software test only'))
        raw_meta=json.dumps(metadata,indent=3)+'\r\n'
        imported=request(f'/api/runs/{rid}/measurements',dict(csv_base64=base64.b64encode(csv.encode()).decode(),metadata=metadata,metadata_text=raw_meta));mid=imported['measurement_id']
        original=request(f'/api/runs/{rid}/measurement/{mid}');assert not original['record']['regression_eligible']
        bundle=request(f'/api/runs/{rid}/export?format=zip');(out/'SYNTHETIC_ACCEPTANCE_evidence.zip').write_bytes(bundle)
        with zipfile.ZipFile(io.BytesIO(bundle)) as archive:
            assert archive.read(f'measurements/{mid}/raw_export.csv')==csv.encode()
            assert archive.read(f'measurements/{mid}/source_metadata.json')==raw_meta.encode()
        reopened=request('/api/reopen',raw=bundle)['run_id']
        assert request(f'/api/runs/{reopened}/measurement/{mid}')==original
        assert request(f'/api/runs/{reopened}/export?format=json')==request(f'/api/runs/{rid}/export?format=json')
        html=request(f'/api/runs/{reopened}/export?format=html');assert b'SYNTHETIC_PORTABLE_ACCEPTANCE' in html
        (out/'SYNTHETIC_ACCEPTANCE_report.html').write_bytes(html)
        (out/'SYNTHETIC_ACCEPTANCE_trace.csv').write_bytes(csv.encode());(out/'SYNTHETIC_ACCEPTANCE_metadata.json').write_bytes(raw_meta.encode())
        gate('raw_bytes_metadata_analysis_export_reopen',run_id=reopened,measurement_id=mid,bundle_sha256=hashlib.sha256(bundle).hexdigest())
        renamed=copy.deepcopy(q);renamed['request_id']='Cosmetic different ID'
        assert any(x['run_id']==rid and x['same_stack'] for x in request('/api/validate',dict(request=renamed))['previous_exact_cases']);gate('semantic_history_matching')
        params=dict(charge_V=5,generator_C_F=1e-6,load_C_F=100e-9,front_R_ohm=330,tail_R_ohm=4700)
        bench=request('/api/bench',dict(parameters=params));trace='time_s,voltage_V\n'+''.join(f'{t},{v}\n' for t,v in zip(bench['time_s'],bench['voltage_V']))
        comparison=request('/api/bench/compare',dict(parameters=params,csv_text=trace,source_filename='SYNTHETIC_bench.csv'))
        assert comparison['raw_csv']==trace and comparison['rmse_V']<1e-12 and bench['metrics']['compliance_status']=='NOT_APPLICABLE_BENCH';gate('isolated_bench_and_trace_comparison')
        li=json.loads((config.DEMOS/'LI_request.json').read_text());li['recipe_ids']=['DEV_UNIFORM_SINGLE_v2','HYP_LI_TAIL_180_PAR_520_v1']
        lid,lir=optimize('LI_complete_588_explicit_parallel',li,588);assert lir['search']['numeric_pass_count']>0
        if a.baseline_li:
            before=json.loads(a.baseline_li.read_text());semantic=lambda result:[(r['candidate_id'],r['configuration'],r['assessment'],r['score'],r['rank']) for r in result['candidates']]
            assert semantic(before)==semantic(lir);gate('LI_588_identical_to_previous_application')
        no=json.loads((config.DEMOS/'SI_infeasible_recommendation.json').read_text())['request'];nid,nor=optimize('no_solution_complete_504',no,504);assert nor['best_configuration'] is None and nor['search']['numeric_pass_count']==0
        for name in meta['technical_documents']:assert request('/api/technical/'+name)
        gate('technical_reports_accessible')
        before_history=request('/api/runs');before_discovery=request('/api/discoveries')
        stop(process,log);running=False;gate('Windows_stop_launcher')
        process,log=start();running=True
        assert request('/api/runs')==before_history and request('/api/discoveries')==before_discovery
        assert request(f'/api/runs/{reopened}/measurement/{mid}')==original;gate('restart_preserves_history_discovery_and_raw_measurements')
        verify=subprocess.run([sys.executable,str(config.ROOT/'tests/verify_manifest.py')],cwd=out,capture_output=True);assert verify.returncode==0
        (out/'manifest_after.json').write_bytes(verify.stdout);gate('immutable_manifest_after_actual_application_use')
        report['status']='PASS';report['offline_boundary']='Python non-loopback socket connects blocked in server and spawned workers; browser used only local assets';(out/'acceptance.json').write_text(json.dumps(report,indent=2))
    finally:
        if running and not a.keep_running:stop(process,log)
    print('PORTABLE ACCEPTANCE PASS',flush=True)
if __name__=='__main__':main()
