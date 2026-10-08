"""Run every upstream and release suite with saved logs and live heartbeat."""
from pathlib import Path
import subprocess,sys,os,time,json
from datetime import datetime,timezone
import powernext_config as config
sys.stdout.reconfigure(encoding='utf-8',errors='replace')

def main():
    label=sys.argv[1] if len(sys.argv)>1 else datetime.now().strftime('%Y%m%d_%H%M%S')
    out=config.ROOT/'evidence/test_logs'/label
    out.mkdir(parents=True,exist_ok=False)
    env=dict(os.environ,OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',PYTHONIOENCODING='utf-8',PYTEST_DISABLE_PLUGIN_AUTOLOAD='1',POWERNEXT_TEST_OFFLINE='1')
    suites=[('physics',[sys.executable,'-m','unittest','discover','-s','powernext/physics/tests','-v']),
            ('ml',[sys.executable,'-m','pytest','powernext/ml/tests','-q','-p','no:cacheprovider']),
            ('optimizer',[sys.executable,'-m','pytest','powernext/optimizer/tests','-q','-p','no:cacheprovider']),
            ('application',[sys.executable,'-m','pytest','tests/application','-q','-p','no:cacheprovider']),
            ('frontend',[str(config.ROOT/'runtime/tools/node.exe'),'--test','tests/application/frontend.test.mjs','tests/application/ui_redesign.test.mjs','tests/application/clarification.test.mjs','tests/ui_selection.test.mjs']),
            ('redteam',[sys.executable,'-m','pytest','tests/redteam','-q','-p','no:cacheprovider']),
            ('ui_race',[str(config.ROOT/'runtime/tools/node.exe'),'tests/redteam/ui_scenario_race.mjs']),
            ('integration',[sys.executable,'-m','pytest','tests/integration','-q','-p','no:cacheprovider']),
            ('final_release',[sys.executable,'-m','pytest','tests/test_final_release.py','-q','-p','no:cacheprovider'])]
    results=[]
    for name,cmd in suites:
        start=time.monotonic();print(f'[{datetime.now(timezone.utc).isoformat()}] START {name}',flush=True)
        with (out/(name+'.log')).open('w',encoding='utf-8') as log:
            p=subprocess.Popen(cmd,cwd=config.ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
            while p.poll() is None:
                try:p.wait(timeout=25)
                except subprocess.TimeoutExpired:print(f'RUNNING {name}: {time.monotonic()-start:.0f}s',flush=True)
        result=dict(suite=name,exit_code=p.returncode,seconds=round(time.monotonic()-start,3),command=cmd,log=name+'.log')
        results.append(result)
        (out/'summary.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
        print(json.dumps(result),flush=True);print((out/(name+'.log')).read_text(encoding='utf-8')[-1500:],flush=True)
    return int(any(r['exit_code'] for r in results))
if __name__=='__main__':sys.exit(main())
