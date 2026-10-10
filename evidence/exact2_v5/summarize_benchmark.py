"""Summarize immutable post-selection exact-two search evidence."""
from pathlib import Path
import hashlib
import json
import statistics

ROOT=Path(__file__).resolve().parents[2]
p=ROOT/'evidence/exact2_v5/search_benchmark'
m=json.loads((p/'manifest.json').read_text(encoding='utf-8'))
assert m['status']=='COMPLETE' and m['purpose']=='test'
selected=json.loads((ROOT/'powernext/ml/results/networks_exact2_v5/selected_models.json').read_text(encoding='utf-8'))
sealed=json.loads((ROOT/'evidence/exact2_v5/sealed_test_request_design.json').read_text(encoding='utf-8'))
requests=json.loads((p/'requests.json').read_text(encoding='utf-8'))
assert requests[:16]==sealed and len(requests)==17
assert hashlib.sha256((p/'requests.json').read_bytes()).hexdigest()==m['requests_sha256']
cases=[]
for row in m['cases']:
 b=(p/row['path']).read_bytes();assert hashlib.sha256(b).hexdigest()==row['sha256']
 d=json.loads(b);assert d['model']['model_id']==selected[row['route']]
 cases.append(d)
assert len(cases)==17

def aggregate(group):
 out={}
 for policy in ('complete_physics','analytical','ml','combined'):
  rows=[next(r for r in c['policies'] if r['policy']==policy) for c in group]
  feasible=[r for r in rows if r['oracle_feasible_count']>0]
  out[policy]=dict(request_count=len(rows),feasible_request_count=len(feasible),retained_feasible_requests=sum(bool(r['feasible_candidates_found']) for r in feasible),missed_feasible_requests=sum(r['missed_feasible_request'] for r in rows),verified_passing_candidates=sum(r['feasible_candidates_found'] for r in rows),reference_passing_candidates=sum(r['oracle_feasible_count'] for r in rows),max_regret=max((r['regret'] for r in feasible if r['regret'] is not None),default=None),physics_candidate_checks=sum(r['search']['physics_evaluated_count'] for r in rows),ml_predictions=sum(r['search']['ml_predicted_count'] for r in rows),total_seconds=sum(r['search']['total_seconds'] for r in rows),median_search_seconds=statistics.median(r['search']['total_seconds'] for r in rows))
 return out
fresh=[c for c in cases if not c['request']['request_id'].startswith('KNOWN_')]
known=[c for c in cases if c['request']['request_id'].startswith('KNOWN_')]
r=dict(status='COMPLETE',manifest_sha256=hashlib.sha256((p/'manifest.json').read_bytes()).hexdigest(),request_seed=m['request_seed'],selection_sha256=hashlib.sha256((ROOT/'powernext/ml/results/networks_exact2_v5/selected_models.json').read_bytes()).hexdigest(),fresh=aggregate(fresh),known_regression=aggregate(known),all=aggregate(cases),limitations=['Fresh requests use stages 6/9/12; the known regression uses stages 2 through 15.','All policies use identical conditions within each request.','Complete enumeration does not remove numerical support limitations; optima are relative to supported verified outputs.','Timings were measured on a shared machine, with concurrent audit and upload activity; they do not establish a controlled general speedup.','Final tests did not change model selection or trigger fitting.'])
out=p/'summary.json'
assert not out.exists()
out.write_text(json.dumps(r,indent=2,allow_nan=False)+'\n',encoding='utf-8')
print(json.dumps(r,indent=2))
