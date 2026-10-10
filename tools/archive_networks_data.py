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


def _source_folders(root, source_folder=None):
    """Resolve the requested data folder without accepting path traversal.

    The default keeps the original multi-folder archive behavior.  Explicit
    archives are intentionally restricted to one literal child basename of
    ``powernext/ml/data`` so a caller cannot accidentally archive an unrelated
    checkout or a path supplied through shell expansion.
    """
    if source_folder is None:
        return FOLDERS, None
    value = str(source_folder)
    if (not value or value in {".", ".."} or Path(value).name != value
            or any(sep in value for sep in ("/", "\\"))
            or any(char in value for char in "*?[]")):
        raise ValueError("source folder must be one literal child basename")
    if not value.startswith("networks_v3_validation_oracles"):
        raise ValueError("explicit source folder is restricted to validation-oracle folders")
    data_root = (root / "powernext/ml/data").resolve()
    folder = (data_root / value).resolve()
    if folder.parent != data_root or not folder.is_relative_to(root) or not folder.is_dir():
        raise FileNotFoundError(folder)
    manifest_path = folder / "manifest.json"
    if not manifest_path.is_file():
        raise ValueError("validation-oracle folder must contain manifest.json")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("validation-oracle manifest is not valid JSON") from exc
    if manifest.get("purpose") != "validation" or manifest.get("status") != "COMPLETE":
        raise ValueError("validation-oracle manifest must have purpose=validation and status=COMPLETE")
    return (value,), value


def archive(output, source_folder=None):
    output=Path(output).resolve()
    manifest_path=output.with_suffix(".manifest.json")
    sidecar=output.with_suffix(".zip.sha256")
    if any(path.exists() for path in (output,manifest_path,sidecar)):
        raise FileExistsError("Use a new archive identity")
    root=config.ROOT.resolve()
    entries=[]
    sources=[]
    folder_names, explicit_name = _source_folders(root, source_folder)
    for name in folder_names:
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
    if explicit_name is None:
        value=dict(schema_version="network_data_archive_v3",status="VERIFIED",
            created_at=datetime.now(timezone.utc).isoformat(),archive=output.name,
            archive_bytes=output.stat().st_size,archive_sha256=digest(output),files=entries,
            accepted_training_dataset="powernext/ml/data/networks_v3_r2",
            rejected_training_dataset="powernext/ml/data/networks_v3",
            note="Other pilot folders are diagnostic development evidence, not production training data. Validation oracles select models; they are not final test requests.")
    else:
        value=dict(schema_version="network_oracle_archive_v3",status="VERIFIED",
            created_at=datetime.now(timezone.utc).isoformat(),archive=output.name,
            archive_bytes=output.stat().st_size,archive_sha256=digest(output),files=entries,
            source_folder=f"powernext/ml/data/{explicit_name}",
            training_role="NOT_TRAINING_DATA",
            validation_role="INDEPENDENT_MODEL_SELECTION_ORACLES_ONLY",
            note="This archive contains complete Physics validation oracles for model selection. It is not a training dataset and is not final test evidence.")
    manifest_path.write_text(json.dumps(value,indent=2),encoding="utf-8")
    sidecar.write_text(value["archive_sha256"]+"  "+output.name+"\n",encoding="utf-8")
    print(json.dumps({key:value[key] for key in ("status","archive","archive_bytes","archive_sha256")}),flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser();parser.add_argument("output",type=Path)
    parser.add_argument("--source-folder", help="Archive one literal folder under powernext/ml/data; default preserves the original multi-folder archive.")
    args=parser.parse_args()
    archive(args.output,args.source_folder)
