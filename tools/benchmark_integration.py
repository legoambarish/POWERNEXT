"""Run unchanged requests in the interpreter's own portable application.

Usage: runtime/python.exe tools/benchmark_integration.py OUTPUT [--workers N]
The same script is used with the retained October 4 interpreter for the baseline.
"""
import argparse, importlib, json, time
from pathlib import Path
import powernext_config as config
from powernext_optimizer.service import recommend
from powernext_ml.screening import screen_batch

def main():
    p=argparse.ArgumentParser();p.add_argument('output');p.add_argument('--workers',type=int,default=1)
    a=p.parse_args();out=Path(a.output);out.mkdir(parents=True,exist_ok=True)
    stats={'calls':0,'bytes':0,'seconds':0.0}
    # Count actual file_hash entry points, not reads hidden inside OS disk cache.
    for module in ['powernext_optimizer.common','powernext_optimizer.prediction','powernext_optimizer.service',
                   'powernext_ml.common','powernext_ml.physics_adapter','powernext_ml.registry','powernext_ml.screening']:
        m=importlib.import_module(module);original=m.file_hash
        def counted(path,_original=original):
            start=time.perf_counter();value=_original(path)
            stats['calls']+=1;stats['bytes']+=Path(path).stat().st_size;stats['seconds']+=time.perf_counter()-start
            return value
        m.file_hash=counted
    try:
        from powernext_integrity import IO
    except ImportError:
        IO={}
    report={'application_root':str(config.ROOT),'workers':a.workers,'cases':[]}
    for mode in ['SI','LI']:
        raw=json.loads((config.DEMOS/f'{mode}_request.json').read_text())
        print(f'START {mode} full catalog',flush=True);before=dict(stats);before_io=dict(IO);start=time.perf_counter()
        result=recommend(raw,workers=a.workers,progress=True)
        elapsed=time.perf_counter()-start;payload=result.payload
        semantic=[{'id':r['candidate_id'],'configuration':r['configuration'],'assessment':r['assessment'],
                   'score':r['score'],'rank':r['rank'],'metrics':(r.get('prediction') or {}).get('physics_reference',{}).get('metrics')} for r in payload['candidates']]
        (out/f'{mode}_ranking.json').write_text(json.dumps(semantic,indent=2,allow_nan=False))
        report['cases'].append(dict(mode=mode,seconds=elapsed,search=payload['search'],hash_work={k:stats[k]-before[k] for k in stats},boundary_io={k:IO[k]-before_io[k] for k in IO}))
        print(f'END {mode}: {elapsed:.3f}s',flush=True)
        if mode=='SI':
            row=payload.get('best_configuration') or payload['closest_noncompliant']
            scenarios=[dict(configuration=row['configuration'],setup=dict(raw['setup'],dut_capacitance_F=(.7+i/128*.3)*1e-9),target_crest_V=raw['target_crest_V']) for i in range(128)]
            for label in ['first','warm']:
                start=time.perf_counter();screen=screen_batch(scenarios,config.REGISTRY,config.MODEL_SELECTION)
                report[f'batch_128_{label}']={'seconds':time.perf_counter()-start,'estimates':sum(r['status']=='ML_SCREEN_ONLY' for r in screen['rows'])}
        (out/'benchmark.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2),flush=True)
if __name__=='__main__':main()
