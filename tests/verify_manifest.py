"""Verify all immutable release bytes without dependencies or internet."""
from pathlib import Path
import hashlib,json,sys
from concurrent.futures import ThreadPoolExecutor
ROOT=Path(__file__).resolve().parents[1]
manifest=json.loads((ROOT/'FINAL_FILE_MANIFEST.json').read_text(encoding='utf-8'))
def verify(entry):
    path=ROOT/entry['path']
    if not path.resolve().is_relative_to(ROOT):raise ValueError('Invalid manifest path')
    if not path.is_file():return dict(path=entry['path'],reason='MISSING')
    with path.open('rb') as f:actual=hashlib.file_digest(f,'sha256').hexdigest()
    if actual!=entry['sha256'] or path.stat().st_size!=entry['bytes']:return dict(path=entry['path'],reason='CHANGED')
with ThreadPoolExecutor(max_workers=8) as pool:
    failures=[value for value in pool.map(verify,manifest['files']) if value]
# Detect additions within immutable application directories as well as changes.
expected={row['path'] for row in manifest['files']}
roots={Path(name).parts[0] for name in expected if len(Path(name).parts)>1}
for directory in sorted(roots):
    for path in (ROOT/directory).rglob('*'):
        if not path.is_file() or any(p in {'__pycache__','.pytest_cache'} for p in path.parts):continue
        name=path.relative_to(ROOT).as_posix()
        if name.startswith('evidence/test_logs/'):continue
        if name not in expected:failures.append(dict(path=name,reason='UNEXPECTED'))
print(json.dumps(dict(status='FAIL' if failures else 'PASS',files_checked=len(manifest['files']),failures=failures),indent=2))
sys.exit(bool(failures))
