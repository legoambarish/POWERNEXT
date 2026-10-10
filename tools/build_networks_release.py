"""Build a NEW exact-two v5 offline release, preserving historical assets.

Training corpora and unselected model binaries are separate reproducibility
artifacts; the active offline application contains exactly the selected
``networks_exact2_v5`` routes and the legacy runtime assets needed by the original
UI. Historical network model binaries, results and corpora remain in
the source checkout/archive but are excluded from a new active release. A
pre-existing destination is never silently updated.
"""
from pathlib import Path
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import re
import shutil
import time
import zipfile
import powernext_config as config

DIRECTORIES=("powernext","powernext_app","powernext_v3","ui","runtime","tests","docs","examples","competition-materials","evidence","tools")
FILES=("README.md","Launch_PowerNext.cmd","Stop_PowerNext.cmd","run.ps1","powernext_config.py","powernext_integrity.py",
       "requirements.txt","pytest.ini","RELEASE_METADATA.json","excel_comparison.py")
ACTIVE_ASSET_SET="networks_exact2_v5"
ACTIVE_SELECTION_RELATIVE=Path("powernext/ml/results")/ACTIVE_ASSET_SET/"selected_models.json"
ACTIVE_REGISTRY_RELATIVE=Path("powernext/ml/registry")/ACTIVE_ASSET_SET
# The model/result asset set keeps the stable v5 name, while the source
# dataset is the immutable post-filter augmentation published by the worker.
ACTIVE_DATA_RELATIVE=Path("powernext/ml/data")/(ACTIVE_ASSET_SET + "_aug1")
ACTIVE_SCOPE_RELATIVE=Path("powernext/ml/results")/ACTIVE_ASSET_SET/"release_scope.json"
ROUTES=tuple(
    f"{domain}:{mode}:{topology}"
    for domain in ("cpri_0p5uf", "research_3uf")
    for mode in ("LI", "SI")
    for topology in ("GSHUNT_v0", "OSHUNT_v0")
)
_MODEL_ID_RE=re.compile(r"^model_[A-Za-z0-9_-]+$")


def digest(path):
    with Path(path).open("rb") as stream:return hashlib.file_digest(stream,"sha256").hexdigest()


def _network_module_count(node):
    if not isinstance(node,dict):raise ValueError("Dataset network tree must be an object")
    if node.get("op")=="R":return 1
    if node.get("op") not in {"S","P"} or not isinstance(node.get("children"),list):
        raise ValueError("Dataset network tree has invalid series/parallel structure")
    if len(node["children"])<2:raise ValueError("Dataset network tree composite has too few children")
    return sum(_network_module_count(child) for child in node["children"])


def _exact2_dataset_scope(root):
    """Validate the source-only exact-two dataset before models enter a package."""

    data_dir=root/ACTIVE_DATA_RELATIVE
    manifest_path=data_dir/"manifest.json"
    rows_path=data_dir/"rows.jsonl"
    if not manifest_path.is_file() or not rows_path.is_file():
        raise FileNotFoundError(f"Missing active exact-two dataset manifest or rows: {data_dir}")
    manifest=json.loads(manifest_path.read_text(encoding="utf-8"))
    scope=manifest.get("scope_filter") or manifest.get("filter")
    provenance=manifest.get("provenance")
    if not isinstance(scope,dict) and isinstance(provenance,dict):
        scope=provenance.get("derived_scope_filter") or provenance.get("filter")
    if not isinstance(scope,dict):raise ValueError("Active dataset is missing its exact-two scope metadata")
    rule="".join(str(scope.get("rule") or scope.get("predicate") or "").split()).lower()
    front_field = scope.get("field_front") or ("front_leaf_count" if "front_leaf_count" in scope else "front_network_module_count")
    tail_field = scope.get("field_tail") or ("tail_leaf_count" if "tail_leaf_count" in scope else "tail_network_module_count")
    front_declared = scope.get(front_field)
    tail_declared = scope.get(tail_field)
    rule_has_exact_front = (
        re.search(r"front_network_module_count={1,2}2", rule) is not None
        or front_declared == 2
        or "frontandtailcanonicaltreeseachexactlytworesistorleaves" in rule
    )
    rule_has_exact_tail = (
        re.search(r"tail_network_module_count={1,2}2", rule) is not None
        or tail_declared == 2
        or "frontandtailcanonicaltreeseachexactlytworesistorleaves" in rule
    )
    exact_marker = (
        scope.get("exact_two_module_rows_selected") is True
        or scope.get("allow_single_part_recipes") is False
        or (rule_has_exact_front and rule_has_exact_tail)
    )
    if (
        front_field not in {"front_network_module_count", "front_leaf_count"}
        or tail_field not in {"tail_network_module_count", "tail_leaf_count"}
        or front_declared not in (None, 2)
        or tail_declared not in (None, 2)
        or not exact_marker
        or not (rule_has_exact_front and rule_has_exact_tail)
    ):
        raise ValueError("Active dataset does not declare the exact-two network scope")
    rows_sha=manifest.get("rows_sha256")
    if not isinstance(rows_sha,str) or not re.fullmatch(r"[0-9a-f]{64}",rows_sha):
        raise ValueError("Active dataset is missing a valid rows_sha256")
    actual_rows_sha=digest(rows_path)
    if actual_rows_sha!=rows_sha:raise ValueError("Active dataset rows hash does not match manifest")
    row_count=0
    with rows_path.open("r",encoding="utf-8") as stream:
        for line_number,line in enumerate(stream,1):
            if not line.strip():continue
            row_count+=1
            try:row=json.loads(line)
            except json.JSONDecodeError as exc:raise ValueError(f"Invalid active dataset row {line_number}") from exc
            configuration=row.get("configuration") if isinstance(row,dict) else None
            if not isinstance(configuration,dict):raise ValueError(f"Active dataset row {line_number} has no configuration")
            for side in ("front_network","tail_network"):
                count=_network_module_count(configuration.get(side))
                if count!=2:raise ValueError(f"Active dataset row {line_number} violates exact-two scope: {side}={count}")
    declared_count=manifest.get("row_count")
    if declared_count is not None and int(declared_count)!=row_count:
        raise ValueError("Active dataset row_count does not match rows.jsonl")
    return {
        "asset_set":ACTIVE_ASSET_SET,
        "dataset_path":ACTIVE_DATA_RELATIVE.as_posix(),
        "dataset_id":manifest.get("dataset_id"),
        "dataset_rows_sha256":rows_sha,
        "dataset_manifest_sha256":digest(manifest_path),
        "scope_rule":"front_network_module_count == 2 and tail_network_module_count == 2",
        "max_modules":2,
        "min_modules":2,
        "supported_module_options":[2],
        "allow_single_part_recipes":False,
        "network_count_policy":"EXACTLY_TWO_PER_BRANCH",
        "row_count":row_count,
    }


def _selection(root):
    selection=root/ACTIVE_SELECTION_RELATIVE
    if not selection.is_file():raise FileNotFoundError(f"Missing active selected model mapping: {selection}")
    values=json.loads(selection.read_text(encoding="utf-8"))
    required=set(ROUTES)
    if not isinstance(values,dict) or set(values)!=required:
        raise ValueError("All eight selected exact-two model routes are required for release")
    if any(not isinstance(identifier,str) or not _MODEL_ID_RE.fullmatch(identifier) for identifier in values.values()):
        raise ValueError("Selected exact-two routes must point to model identifiers")
    if len(set(values.values()))!=len(ROUTES):
        raise ValueError("Eight distinct selected exact-two model identifiers are required for release")
    return values


def selected_ids(root,scope=None):
    values=_selection(root)
    scope=scope or _exact2_dataset_scope(root)
    from powernext_v3.registry import load_model
    selected=set()
    for route,identifier in values.items():
        if not isinstance(identifier,str) or Path(identifier).name!=identifier or not _MODEL_ID_RE.fullmatch(identifier):
            raise ValueError("Invalid selected exact-two model identifier")
        folder=root/ACTIVE_REGISTRY_RELATIVE/identifier
        if not (folder/"model.joblib").is_file() or not (folder/"card.json").is_file():raise FileNotFoundError(identifier)
        card=json.loads((folder/"card.json").read_text(encoding="utf-8"))
        if card.get("model_id")!=identifier or card.get("data_sha256")!=scope["dataset_rows_sha256"]:
            raise ValueError(f"Selected card {identifier} does not identify the active exact-two dataset")
        provenance=card.get("provenance")
        if not isinstance(provenance,dict) or provenance.get("data_sha256")!=scope["dataset_rows_sha256"]:
            raise ValueError(f"Selected card {identifier} is missing exact-two dataset provenance")
        if provenance.get("data_manifest_sha256") != scope["dataset_manifest_sha256"]:
            raise ValueError(f"Selected card {identifier} has a different dataset manifest")
        domain,mode,topology=route.split(":")
        # Release preparation must reject a stale, mismatched, or tampered
        # selected artifact before any package directory is created.
        load_model(folder,expected_route=dict(domain_id=domain,mode=mode,topology=topology))
        selected.add(identifier)
    return selected


def source_files(root,*,include_research=False,selected=None):
    selected=selected if selected is not None else selected_ids(root)
    for directory in DIRECTORIES:
        for path in (root/directory).rglob("*"):
            if not path.is_file() or any(p in {"__pycache__",".pytest_cache"} for p in path.parts):continue
            relative=path.relative_to(root)
            name=relative.as_posix()
            if name.startswith("evidence/test_logs/"):continue
            if not include_research:
                # No training corpus is an active runtime dependency.  Keep
                # all data manifests/rows/waveforms out of the moved package.
                if name.startswith("powernext/ml/data/"):continue
                historical_registry="powernext/ml/registry/networks_v3/"
                if name.startswith(historical_registry):continue
                active_registry=f"{ACTIVE_REGISTRY_RELATIVE.as_posix()}/"
                if name.startswith(active_registry) and name[len(active_registry):].split("/",1)[0] not in selected:continue
                if name.startswith("powernext/ml/registry/") and not name.startswith(active_registry) and "/networks_" in name:
                    continue
                if name.startswith("powernext/ml/results/networks_") and not name.startswith(f"powernext/ml/results/{ACTIVE_ASSET_SET}/"):
                    continue
                active_results=f"{ACTIVE_SELECTION_RELATIVE.parent.as_posix()}/"
                if name.startswith(active_results) and name!=ACTIVE_SELECTION_RELATIVE.as_posix():continue
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


def write_release_scope(root,scope,selected):
    """Write a package-local attestation because source training data is excluded."""

    path=root/ACTIVE_SCOPE_RELATIVE
    path.parent.mkdir(parents=True,exist_ok=True)
    payload=dict(
        schema_version="network_release_scope_v5",
        asset_set=ACTIVE_ASSET_SET,
        dataset_path=ACTIVE_DATA_RELATIVE.as_posix(),
        min_modules=2,
        max_modules=2,
        supported_module_options=[2],
        allow_single_part_recipes=False,
        network_count_policy="EXACTLY_TWO_PER_BRANCH",
        scope_rule=scope["scope_rule"],
        dataset_id=scope.get("dataset_id"),
        dataset_rows_sha256=scope["dataset_rows_sha256"],
        dataset_manifest_sha256=scope["dataset_manifest_sha256"],
        dataset_row_count=scope.get("row_count"),
        selected_model_ids=sorted(selected),
        selected_route_count=len(ROUTES),
        training_corpora_included=False,
    )
    path.write_text(json.dumps(payload,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    return path


def build(destination,*,archive=False):
    destination=Path(destination).resolve()
    if destination.exists():raise FileExistsError("Use a new release destination; accepted releases are preserved")
    if destination==config.ROOT or config.ROOT in destination.parents:raise ValueError("Release must be outside the source checkout")
    scope=_exact2_dataset_scope(config.ROOT)
    selected=selected_ids(config.ROOT,scope)
    sources=list(source_files(config.ROOT,selected=selected))
    destination.mkdir(parents=True)
    started=time.monotonic()
    copied=[]
    for index,path in enumerate(sources,1):
        if path.is_symlink() or path.is_junction():raise ValueError("Unexpected linked source asset")
        target=destination/path.relative_to(config.ROOT)
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(path,target);copied.append(target)
        if index%2000==0:print(f"PACK {index}/{len(sources)} files; {time.monotonic()-started:.1f}s",flush=True)
    copied.append(write_release_scope(destination,scope,selected))
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
