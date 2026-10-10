"""Preserve new research corpora in an immutable Git-LFS archive.

Extracted working copies are retained. Neither legacy archives nor an existing
destination can be overwritten. This command performs no simulations/training.
"""
from pathlib import Path
import argparse
from datetime import datetime, timezone
import hashlib
import json
import zipfile
import powernext_config as config

FOLDERS=("networks_v3", "networks_v3_pilot", "networks_v3_pilot_v2",
    "networks_v3_pilot_splitfix", "networks_v3_pilot_splitfix2",
    "networks_v3_r2", "networks_v3_validation_oracles")


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream,"sha256").hexdigest()


def archive(output):
    output=Path(output).resolve()
    manifest_path=output.with_suffix(".manifest.json")
    sidecar=output.with_suffix(".zip.sha256")
    if any(path.exists() for path in (output,manifest_path,sidecar)):
        raise FileExistsError("Use a new archive identity")
    root=config.ROOT.resolve()
    entries=[]
    sources=[]
    for name in FOLDERS:
        folder=root/"powernext/ml/data"/name
        if not folder.is_dir():raise FileNotFoundError(folder)
        for path in sorted(folder.rglob("*")):
            if not path.is_file():continue
            if path.is_symlink() or path.is_junction() or not path.resolve().is_relative_to(root):
                raise ValueError("Unexpected source link or outside path")
            sources.append(path)
    output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,"x",compression=zipfile.ZIP_DEFLATED,compresslevel=3) as z:
        for index,path in enumerate(sources,1):
            relative=path.relative_to(root).as_posix()
            before=digest(path)
            z.write(path,relative)
            if digest(path)!=before:raise RuntimeError("Source changed during archive: "+relative)
            entries.append(dict(path=relative,bytes=path.stat().st_size,sha256=before))
            if index%25==0:print(f"ARCHIVE {index}/{len(sources)} files",flush=True)
    with zipfile.ZipFile(output) as z:
        for index,entry in enumerate(entries,1):
            with z.open(entry["path"]) as stream:
                if hashlib.file_digest(stream,"sha256").hexdigest()!=entry["sha256"]:
                    raise RuntimeError("Archived bytes differ: "+entry["path"])
            if index%25==0:print(f"VERIFY {index}/{len(entries)} files",flush=True)
    value=dict(schema_version="network_data_archive_v3",status="VERIFIED",
        created_at=datetime.now(timezone.utc).isoformat(),archive=output.name,
        archive_bytes=output.stat().st_size,archive_sha256=digest(output),files=entries,
        accepted_training_dataset="powernext/ml/data/networks_v3_r2",
        rejected_training_dataset="powernext/ml/data/networks_v3",
        note="Other pilot folders are diagnostic development evidence, not production training data. Validation oracles select models; they are not final test requests.")
    manifest_path.write_text(json.dumps(value,indent=2),encoding="utf-8")
    sidecar.write_text(value["archive_sha256"]+"  "+output.name+"\n",encoding="utf-8")
    print(json.dumps({key:value[key] for key in ("status","archive","archive_bytes","archive_sha256")}),flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("output",type=Path)
    archive(parser.parse_args().output)
