"""Immutable local model artifacts with provenance and runtime checking."""
from pathlib import Path
import json
import joblib
from functools import lru_cache
from .common import digest,file_hash,write_json,runtime_versions,source_hashes


def register(model,card,root):
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    card=dict(card,schema_version="model_registry_v1",feature_order=model.columns,runtime=runtime_versions(),training_code_sha256=source_hashes(),
              model_family=model.family,formulation=model.formulation,domain=model.domain,hardware_recommendations_enabled=False,
              real_data_calibrated=False,model_persistence="joblib; load only trusted locally produced artifacts")
    model_id="model_"+digest(card)[:20]
    folder=root/model_id
    if folder.exists():raise FileExistsError(f"Immutable model already exists: {folder}")
    folder.mkdir()
    joblib.dump(model,folder/"model.joblib",compress=3)
    card.update(model_id=model_id,model_sha256=file_hash(folder/"model.joblib"))
    write_json(folder/"card.json",card)
    return card


def load_model(folder,expected_provenance=None):
    folder=Path(folder)
    card=json.loads((folder/"card.json").read_text(encoding="utf-8"))
    if file_hash(folder/"model.joblib")!=card["model_sha256"]:raise ValueError("Model hash mismatch")
    installed=runtime_versions()
    for name in ["python","numpy","scipy","sklearn"]:
        if installed[name]!=card["runtime"][name]:raise ValueError(f"Model runtime mismatch: {name}")
    if expected_provenance is not None and card["provenance"]!=expected_provenance:raise ValueError("Model/physics provenance mismatch; regenerate and retrain")
    return joblib.load(folder/"model.joblib"),card


@lru_cache(maxsize=8)
def _verified_cached_model(folder,provenance_json,model_hash,card_hash):
    # All keys identify immutable bytes, not modification times. The caller
    # checks the bytes again even on a cache hit. This avoids repeated joblib
    # deserialization without weakening provenance or integrity checks.
    return load_model(Path(folder),json.loads(provenance_json) if provenance_json else None)


def load_model_cached(folder,expected_provenance=None):
    folder=Path(folder).resolve()
    before=(file_hash(folder/'model.joblib'),file_hash(folder/'card.json'))
    key=json.dumps(expected_provenance,sort_keys=True,allow_nan=False) if expected_provenance is not None else ''
    result=_verified_cached_model(str(folder),key,*before)
    if before!=(file_hash(folder/'model.joblib'),file_hash(folder/'card.json')):
        raise ValueError('Model changed while loading or checking cache')
    return result
