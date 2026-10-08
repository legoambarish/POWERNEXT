import copy,json,os,shutil,subprocess,sys,time,io
from pathlib import Path
import pytest
import powernext_config as config
from powernext_app.service import Application
from powernext_app.process import stream_process
from powernext_optimizer.storage import HistoryStore
from powernext_ml.registry import load_model
from powernext_app.server import make_server
from powernext_app.instance import InstanceLock

def test_existing_listener_cannot_be_shadowed(tmp_path):
    app=Application(tmp_path/'records');server=make_server(app,0)
    try:
        with pytest.raises(OSError):make_server(app,server.server_port)
    finally:server.server_close();app.close()

def test_second_instance_cannot_recover_active_records(tmp_path):
    first=InstanceLock(tmp_path)
    try:
        with pytest.raises(RuntimeError,match='already open'):InstanceLock(tmp_path)
    finally:first.close()
    second=InstanceLock(tmp_path);second.close()

def test_all_models_preload_with_original_profile(tmp_path):
    config.validate_assets()
    app=Application(tmp_path/'records')
    try:
        config.validate_models(app)
        assert len(app.stack.models)==4
        assert [x['value'] for x in app.catalog.profile['resistors']['LI_tail_per_stage_confirmed']]==[30,46,180,520,3700,5000]
    finally:app.close()

def test_history_survives_data_directory_move(tmp_path):
    original=tmp_path/'first'
    app=Application(original)
    run=app.load_demo('si');result=app.store.result(run['run_id']);app.close()
    relocated=tmp_path/'moved'
    shutil.move(str(original),str(relocated))
    reopened=Application(relocated)
    try:
        assert reopened.store.result(run['run_id'])==result
        hits=reopened.history.lookup(result['request_sha256'],result['stack_sha256'])
        assert len(hits)==1 and hits[0]['candidate_id']==result['best_configuration']['candidate_id']
    finally:reopened.close()

def test_watchdog_kills_child_tree(tmp_path):
    import psutil
    pidfile=tmp_path/'child.pid'
    child='import time; time.sleep(60)'
    parent=f'import subprocess,sys,time,pathlib; p=subprocess.Popen([sys.executable,"-c",{child!r}]); pathlib.Path({str(pidfile)!r}).write_text(str(p.pid)); print("ready",flush=True); time.sleep(60)'
    with pytest.raises(TimeoutError,match='No partial recommendation'):
        stream_process([sys.executable,'-c',parent],cwd=tmp_path,env=os.environ.copy(),output=io.StringIO(),on_progress=lambda _:None,timeout_seconds=2)
    assert pidfile.is_file()
    pid=int(pidfile.read_text())
    for _ in range(20):
        if not psutil.pid_exists(pid):break
        time.sleep(.1)
    assert not psutil.pid_exists(pid),'Optimizer descendant survived watchdog'

def test_application_timeout_has_no_publishable_partial_result(tmp_path):
    app=Application(tmp_path/'records',timeout_seconds=.1)
    try:
        q=json.loads((config.DEMOS/'SI_request.json').read_text())
        r=app.optimize(q)
        app.active.result(timeout=20)
        b=app.get_run(r['run_id'])
        assert b['run']['status']=='FAILED' and b['result'] is None
        assert 'No partial recommendation' in b['run']['error']
        with pytest.raises(ValueError,match='completed result'):app.store.result_path(r['run_id'])
    finally:app.close()

def test_restricted_inventory_reaches_live_recommendation(tmp_path):
    app=Application(tmp_path/'records')
    try:
        q=json.loads((config.DEMOS/'SI_request.json').read_text())
        q.update(available_front_per_stage_ohm=[3700],available_tail_per_stage_ohm=[5000])
        assert app.validate(q)['catalog_count']==14
        r=app.optimize(q);app.active.result(timeout=390)
        b=app.get_run(r['run_id']);assert b['run']['status']=='COMPLETED',b['run'].get('error')
        assert b['artifact_compatibility']=='MATCHES_CURRENT_STACK'
        assert len(b['result']['candidates'])==14
        assert not (app.store.root/'prediction_cache').exists()
        assert {c['configuration']['front_per_stage_ohm'] for c in b['result']['candidates']}=={3700}
        assert {c['configuration']['tail_per_stage_ohm'] for c in b['result']['candidates']}=={5000}
    finally:app.close()

def test_bundled_runtime_has_no_user_site_or_external_import_paths():
    if Path(sys.executable).resolve()!=config.ROOT/'runtime/python.exe':pytest.fail('Final acceptance must use bundled runtime')
    assert sys.flags.isolated==1 and sys.flags.no_site==1
    for p in sys.path:assert Path(p).resolve().is_relative_to(config.ROOT),p
    for name in ['numpy','scipy','pandas','sklearn','matplotlib','powernext_app','powernext_ml','powernext_optimizer','physics_engine']:
        module=__import__(name)
        assert Path(module.__file__).resolve().is_relative_to(config.ROOT)
