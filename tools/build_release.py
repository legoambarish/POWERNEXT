"""Copy a self-contained Windows application without historical runtime duplicates.

No downloads, deletion, or Git operations. Existing output is updated only when
explicitly named; stale unexpected files are rejected by verify_manifest.py.
"""
from pathlib import Path
import argparse,hashlib,json,shutil,time,zipfile
from concurrent.futures import ThreadPoolExecutor
import powernext_config as config

DIRECTORIES=('powernext','powernext_app','ui','runtime','tests','docs','examples','competition-materials','evidence','tools')
FILES=('README.md','Launch_PowerNext.cmd','Stop_PowerNext.cmd','run.ps1','powernext_config.py','powernext_integrity.py','requirements.txt','pytest.ini','RELEASE_METADATA.json')
def files(root):
    for directory in DIRECTORIES:
        for path in (root/directory).rglob('*'):
            if not path.is_file() or any(x in {'__pycache__','.pytest_cache'} for x in path.parts):continue
            # Acceptance logs are mutable and excluded from the immutable manifest.
            if path.is_relative_to(root/'evidence/test_logs'):continue
            yield path
    for name in FILES:
        path=root/name
        if path.is_file():yield path

def hash_file(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def manifest(root):
    entries=[]
    def entry(path):return dict(path=path.relative_to(root).as_posix(),bytes=path.stat().st_size,sha256=hash_file(path))
    with ThreadPoolExecutor(max_workers=8) as pool:
        for i,row in enumerate(pool.map(entry,sorted(files(root)))):
            entries.append(row)
            if i%2500==0:print(f'HASH {i} files',flush=True)
    value=dict(schema_version='powernext_release_manifest_v2',algorithm='SHA-256',application_version='1.0.0+integration20261008',mutable_exclusions=['data/**','evidence/test_logs/**','**/__pycache__/**','**/.pytest_cache/**'],files=entries)
    (root/'FINAL_FILE_MANIFEST.json').write_text(json.dumps(value,indent=2),encoding='utf-8')
    return value

def main():
    parser=argparse.ArgumentParser();parser.add_argument('destination',type=Path);parser.add_argument('--zip',action='store_true');parser.add_argument('--manifest-only',action='store_true');args=parser.parse_args()
    destination=args.destination.resolve()
    if destination==config.ROOT and not args.manifest_only:raise ValueError('Cannot copy onto source checkout')
    destination.mkdir(parents=True,exist_ok=True);start=time.monotonic()
    if not args.manifest_only:
        for i,path in enumerate(files(config.ROOT)):
            target=destination/path.relative_to(config.ROOT);target.parent.mkdir(parents=True,exist_ok=True)
            if path.is_symlink() or path.is_junction():raise ValueError('Unexpected link: '+str(path))
            if not target.is_file() or hash_file(path)!=hash_file(target):shutil.copy2(path,target)
            if i%2500==0:print(f'PACK {i} files · {time.monotonic()-start:.1f}s',flush=True)
    value=manifest(destination)
    print(f'MANIFEST {len(value["files"])} files, {sum(x["bytes"] for x in value["files"])} bytes',flush=True)
    if args.zip:
        output=destination.with_suffix('.zip')
        if output.exists():raise ValueError('Archive already exists; preserve it before generating another')
        with zipfile.ZipFile(output,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
            for i,row in enumerate(value['files']):
                archive.write(destination/row['path'],destination.name+'/'+row['path'])
                if i%2500==0:print(f'ZIP {i} files',flush=True)
            archive.write(destination/'FINAL_FILE_MANIFEST.json',destination.name+'/FINAL_FILE_MANIFEST.json')
        output.with_suffix('.zip.sha256').write_text(hash_file(output)+'  '+output.name+'\n')
        print(f'ZIP READY {output} ({output.stat().st_size} bytes)',flush=True)
if __name__=='__main__':main()
