"""Verify all immutable release bytes without dependencies or internet."""
from pathlib import Path
import hashlib,json,sys
ROOT=Path(__file__).resolve().parents[1]
manifest=json.loads((ROOT/'FINAL_FILE_MANIFEST.json').read_text(encoding='utf-8'))
failures=[]
for entry in manifest['files']:
    path=ROOT/entry['path']
    if not path.resolve().is_relative_to(ROOT):raise ValueError('Invalid manifest path')
    if not path.is_file():failures.append(dict(path=entry['path'],reason='MISSING'));continue
    with path.open('rb') as f:actual=hashlib.file_digest(f,'sha256').hexdigest()
    if actual!=entry['sha256'] or path.stat().st_size!=entry['bytes']:failures.append(dict(path=entry['path'],reason='CHANGED'))
print(json.dumps(dict(status='FAIL' if failures else 'PASS',files_checked=len(manifest['files']),failures=failures),indent=2))
sys.exit(bool(failures))
