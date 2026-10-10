"""Build a NEW v3 offline release, preserving the accepted v2 directory and ZIP.

Training corpora and unselected model binaries are separate reproducibility
artifacts; the offline application contains every selected route and legacy
runtime asset. A pre-existing destination is never silently updated.
"""
from pathlib import Path
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import shutil
import time
import zipfile
import powernext_config as config

DIRECTORIES=("powernext","powernext_app","powernext_v3","ui","runtime","tests","docs","examples","competition-materials","evidence","tools")
FILES=("README.md","Launch_PowerNext.cmd","Stop_PowerNext.cmd","run.ps1","powernext_config.py","powernext_integrity.py",
       "requirements.txt","pytest.ini","RELEASE_METADATA.json","excel_comparison.py")


def digest(path):
    with Path(path).open("rb") as stream:return hashlib.file_digest(stream,"sha256").hexdigest()


def selected_ids(root):
    selection=root/"powernext/ml/results/networks_v3/selected_models.json"
    values=json.loads(selection.read_text(encoding="utf-8"))
    required={f"{domain}:{mode}:{top}" for domain in ("cpri_0p5uf","research_3uf") for mode in ("LI","SI") for top in ("GSHUNT_v0","OSHUNT_v0")}
    if set(values)!=required:raise ValueError("All eight selected domain-compatible model routes are required for release")
    for identifier in values.values():
        if not isinstance(identifier,str) or Path(identifier).name!=identifier:raise ValueError("Invalid selected model identifier")
        if not (root/"powernext/ml/registry/networks_v3"/identifier/"model.joblib").is_file():raise FileNotFoundError(identifier)
    return set(values.values())


def source_files(root,*,include_research=False):
    selected=selected_ids(root)
    for directory in DIRECTORIES:
        for path in (root/directory).rglob("*"):
            if not path.is_file() or any(p in {"__pycache__",".pytest_cache"} for p in path.parts):continue
            relative=path.relative_to(root)
            name=relative.as_posix()
            if name.startswith("evidence/test_logs/"):continue
            if not include_research:
                if name.startswith("powernext/ml/data/networks_v3"):continue
                registry_prefix="powernext/ml/registry/networks_v3/"
                if name.startswith(registry_prefix) and name[len(registry_prefix):].split("/")[0] not in selected:continue
            yield path
    for name in FILES:
        path=root/name
        if path.is_file():yield path


def write_manifest(root,paths):
    metadata=json.loads((root/"RELEASE_METADATA.json").read_text(encoding="utf-8"))
    def entry(path):return dict(path=path.relative_to(root).as_posix(),bytes=path.stat().st_size,sha256=digest(path))
    with ThreadPoolExecutor(max_workers=8) as pool:rows=list(pool.map(entry,sorted(paths)))
    value=dict(schema_version="powernext_release_manifest_v3",algorithm="SHA-256",application_version=metadata["application_version"],
        mutable_exclusions=["data/**","evidence/test_logs/**","**/__pycache__/**","**/.pytest_cache/**"],files=rows)
    (root/"FINAL_FILE_MANIFEST.json").write_text(json.dumps(value,indent=2),encoding="utf-8")
    return value


def build(destination,*,archive=False):
    destination=Path(destination).resolve()
    if destination.exists():raise FileExistsError("Use a new release destination; accepted releases are preserved")
    if destination==config.ROOT or config.ROOT in destination.parents:raise ValueError("Release must be outside the source checkout")
    sources=list(source_files(config.ROOT))
    destination.mkdir(parents=True)
    started=time.monotonic()
    copied=[]
    for index,path in enumerate(sources,1):
        if path.is_symlink() or path.is_junction():raise ValueError("Unexpected linked source asset")
        target=destination/path.relative_to(config.ROOT)
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(path,target);copied.append(target)
        if index%2000==0:print(f"PACK {index}/{len(sources)} files; {time.monotonic()-started:.1f}s",flush=True)
    manifest=write_manifest(destination,copied)
    print(f"MANIFEST {len(manifest['files'])} immutable files",flush=True)
    if archive:
        output=destination.with_suffix(".zip")
        if output.exists():raise FileExistsError("Archive already exists")
        with zipfile.ZipFile(output,"x",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
            for index,row in enumerate(manifest["files"],1):
                z.write(destination/row["path"],destination.name+"/"+row["path"])
                if index%2000==0:print(f"ZIP {index}/{len(manifest['files'])}",flush=True)
            z.write(destination/"FINAL_FILE_MANIFEST.json",destination.name+"/FINAL_FILE_MANIFEST.json")
        with zipfile.ZipFile(output) as z:
            bad=z.testzip()
            if bad:raise ValueError("Archive CRC failure: "+bad)
        output.with_suffix(".zip.sha256").write_text(digest(output)+"  "+output.name+"\n",encoding="utf-8")
        print(f"ZIP VERIFIED {output} ({output.stat().st_size} bytes)",flush=True)
    return manifest


def main():
    parser=argparse.ArgumentParser();parser.add_argument("destination",type=Path)
    parser.add_argument("--zip",action="store_true");parser.add_argument("--source-manifest-only",action="store_true")
    args=parser.parse_args()
    if args.source_manifest_only:
        if args.destination.resolve()!=config.ROOT:raise ValueError("Source manifest target must be current checkout")
        manifest=write_manifest(config.ROOT,list(source_files(config.ROOT,include_research=True)))
        print(f"SOURCE MANIFEST {len(manifest['files'])}")
    else:build(args.destination,archive=args.zip)


if __name__=="__main__":main()
