"""Regenerate current examples; preserve and compare October 4 evidence."""
import json,time,shutil
from pathlib import Path
import powernext_config as config
from powernext_optimizer.service import recommend
from powernext_app.fixtures import DEMOS

def main():
    import sys
    archive=config.ROOT.parent/'archive'/(sys.argv[1] if len(sys.argv)>1 else 'integration_predecessor_examples')
    if not archive.resolve().is_relative_to((config.ROOT.parent/'archive').resolve()):raise ValueError('Archive must stay within workspace archive')
    archive.mkdir(parents=True,exist_ok=True)
    report=[]
    # All fixtures, including technical regression cases not on the UI menu.
    for result_path in sorted(config.DEMOS.glob('*_recommendation.json')):
        old=json.loads(result_path.read_text());raw=old.get('request')
        if not raw:continue
        start=time.perf_counter();print('START',result_path.name,flush=True)
        stored=archive/result_path.name
        if stored.exists():raise ValueError('Existing archived example; review before resuming')
        oldassets=result_path.with_suffix('.assets')
        new=recommend(raw,workers=1,progress=True)
        before=[(r['candidate_id'],r['rank'],r['configuration'],r['assessment'],r['score']) for r in old['candidates']]
        after=[(r['candidate_id'],r['rank'],r['configuration'],r['assessment'],r['score']) for r in new.payload['candidates']]
        if before!=after:raise RuntimeError('Numerical/ranking change in '+result_path.name)
        staging=config.ROOT/'data'/('example_refresh_'+archive.name)/result_path.stem;staging.mkdir(parents=True,exist_ok=True)
        output=staging/result_path.name
        new.save(output)
        # This is a same-volume move into a previously empty, explicitly archived
        # backup path, not deletion. The old source bytes remain recoverable.
        for path in [result_path,oldassets,stored,archive/oldassets.name,output,output.with_suffix('.assets')]:
            if not path.resolve().is_relative_to(config.ROOT.parent.resolve()) or path.is_symlink() or path.is_junction():raise ValueError('Unsafe archive path')
        if oldassets.exists() and any(p.is_symlink() or p.is_junction() for p in oldassets.rglob('*')):raise ValueError('Reparse point in assets')
        result_path.rename(stored)
        if oldassets.exists():oldassets.rename(archive/oldassets.name)
        output.rename(result_path);output.with_suffix('.assets').rename(oldassets)
        report.append(dict(file=result_path.name,candidates=len(after),seconds=time.perf_counter()-start,all_configurations_metrics_ranking_unchanged=True,new_stack=new.payload['stack_sha256']))
        (config.ROOT/'evidence/integration/example_refresh.json').write_text(json.dumps(report,indent=2))
        print('END',result_path.name,report[-1]['seconds'],flush=True)
if __name__=='__main__':main()
