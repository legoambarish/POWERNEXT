"""Verify a fresh extracted portable build using only its embedded runtime."""
import argparse, copy, json, os, subprocess, sys, time
from pathlib import Path
from urllib.request import Request, urlopen
import powernext_config as config


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('output', type=Path)
    parser.add_argument('evidence_bundle', type=Path)
    parser.add_argument('--port', type=int, default=8772)
    args = parser.parse_args()
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    base = f'http://127.0.0.1:{args.port}'
    report = dict(root=str(config.ROOT), runtime=sys.executable, gates=[])

    def gate(name, **detail):
        report['gates'].append(dict(name=name, **detail))
        (out/'acceptance.json').write_text(json.dumps(report, indent=2))
        print('PASS ' + name, flush=True)

    def request(path, value=None, raw=None):
        body = raw if raw is not None else json.dumps(value).encode() if value is not None else None
        headers = {'Content-Type': 'application/zip' if raw is not None else 'application/json'}
        with urlopen(Request(base+path, data=body, headers=headers), timeout=120) as response:
            data = response.read()
            return json.loads(data) if response.headers['Content-Type'].startswith('application/json') else data

    def start():
        log = (out/'server.log').open('ab')
        process = subprocess.Popen([str(config.ROOT/'Launch_PowerNext.cmd'), '--no-browser', '--port', str(args.port)],
                                   cwd=out, env=dict(os.environ, POWERNEXT_TEST_OFFLINE='1'), stdout=log, stderr=subprocess.STDOUT)
        for _ in range(150):
            try:
                meta = request('/api/meta')
                assert Path(meta['data_directory']) == config.ROOT/'data'
                return process, log
            except (OSError, AssertionError):
                time.sleep(.3)
        raise RuntimeError('Fresh extraction did not launch')

    def stop(process, log):
        result = subprocess.run([str(config.ROOT/'Stop_PowerNext.cmd')], cwd=out, capture_output=True, timeout=410)
        (out/'stop.log').write_bytes(result.stdout+result.stderr)
        assert result.returncode == 0
        process.wait(timeout=20)
        log.close()
        assert not (config.ROOT/'data/server_connection.json').exists()

    assert not (config.ROOT/'data/application.sqlite').exists(), 'Must start with a fresh extraction'
    verified = subprocess.run([sys.executable, str(config.ROOT/'tests/verify_manifest.py')], cwd=out, capture_output=True)
    (out/'manifest.json').write_bytes(verified.stdout)
    assert verified.returncode == 0
    process, log = start()
    try:
        assert request('/api/runs') == []
        gate('fresh_extraction_foreign_cwd_default_data_empty_history')
        query = json.loads((config.DEMOS/'SI_request.json').read_text())
        query.update(request_id='SYNTHETIC_FRESH_EXTRACTION', available_front_per_stage_ohm=[3700], available_tail_per_stage_ohm=[5000])
        rid = request('/api/runs', dict(request=query))['run_id']
        started = time.monotonic()
        while time.monotonic()-started < 120:
            saved = request('/api/runs/'+rid)
            if saved['run']['status'] == 'COMPLETED':
                break
            assert saved['run']['status'] != 'FAILED', saved['run'].get('error')
            time.sleep(.5)
        else:
            raise RuntimeError('Fresh optimization did not complete')
        result = saved['result']
        assert result['search']['evaluated_count'] == 14 and result['search']['pruned_count'] == 0
        gate('new_restricted_catalog_request', seconds=saved['run']['elapsed_seconds'])
        scenario = dict(configuration=result['best_configuration']['configuration'], setup=query['setup'], target_crest_V=query['target_crest_V'])
        predicted = request('/api/predict', scenario)
        assert predicted['ml_prediction'] and predicted['physics_reference']['metrics']['compliance_status'] == 'PASS'
        alternative = copy.deepcopy(scenario)
        alternative['setup']['dut_capacitance_F'] = 900e-12
        discovery = request('/api/discoveries', dict(scenarios=[scenario, alternative], policy='FIXED_SETTING'))
        verification = request('/api/discoveries/'+discovery['discovery_id']+'/verify', dict(indices=[1]))
        assert verification['verifications']['1']['configuration'] == scenario['configuration']
        gate('ML_single_discovery_fixed_charge_Physics')
        archive = request(f'/api/runs/{rid}/export?format=zip')
        (out/'fresh_request_evidence.zip').write_bytes(archive)
        reopened = request('/api/reopen', raw=archive)['run_id']
        assert request(f'/api/runs/{reopened}/export?format=json') == request(f'/api/runs/{rid}/export?format=json')
        acquired = request('/api/reopen', raw=args.evidence_bundle.read_bytes())['run_id']
        assert b'SYNTHETIC_PORTABLE_ACCEPTANCE' in request(f'/api/runs/{acquired}/export?format=html')
        gate('exports_reopen_and_imported_waveform_evidence')
        history = request('/api/runs')
        discoveries = request('/api/discoveries')
    finally:
        stop(process, log)
    process, log = start()
    try:
        assert request('/api/runs') == history and request('/api/discoveries') == discoveries
        gate('stop_restart_persists_all_records')
    finally:
        stop(process, log)
    report['status'] = 'PASS'
    (out/'acceptance.json').write_text(json.dumps(report, indent=2))
    print('FRESH EXTRACTION ACCEPTANCE PASS', flush=True)


if __name__ == '__main__':
    main()
