"""Immutable v3 model artifacts with route and provenance checks."""
from __future__ import annotations

import hashlib
import io
import json
import platform
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping

import joblib
import numpy as np

from .features import BASELINE_COLUMNS, FEATURE_COLUMNS


DEFAULT_REGISTRY_ROOT = Path(__file__).resolve().parent.parent / "powernext" / "ml" / "registry" / "networks_v3"
_PREDICTIVE_V3_SOURCES = ("profiles.py", "networks.py", "physics.py", "features.py", "models.py")
_PREDICTIVE_PHYSICS_SOURCES = (
    "powernext_v3/profiles.py",
    "powernext_v3/physics.py",
    "powernext_v3/networks.py",
    "powernext/physics/physics_engine/network.py",
    "powernext/physics/physics_engine/engine.py",
    "powernext/physics/physics_engine/evaluator.py",
    "powernext/physics/physics_engine/analytic.py",
)


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def file_hash(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def runtime_versions() -> dict[str, str]:
    """Capture versions needed to reject incompatible local artifacts."""

    import scipy
    import sklearn

    return {
        "python": platform.python_version(),
        "numpy": np.__version__,
        "scipy": scipy.__version__,
        "sklearn": sklearn.__version__,
        "joblib": joblib.__version__,
        "platform": platform.platform(),
    }


def _source_hashes() -> dict[str, str]:
    root = Path(__file__).resolve().parent
    # Only files that define the predictive contract belong to this identity.
    # Training/registry orchestration is recorded separately so later app
    # wiring cannot invalidate a numerically identical model contract.
    hashes: dict[str, str] = {}
    for name in _PREDICTIVE_V3_SOURCES:
        path = root / name
        if not path.is_file():
            raise FileNotFoundError(f"Missing required predictive source: {path}")
        hashes[name] = file_hash(path)
    return hashes


def source_fingerprint() -> dict[str, Any]:
    """Return v3 code and physics fingerprints for cards/manifests."""

    sources: dict[str, str] = _source_hashes()
    from .physics import source_fingerprint as physics_source_fingerprint

    try:
        physics = physics_source_fingerprint()
    except (ImportError, AttributeError, OSError) as exc:
        raise RuntimeError("Unable to obtain complete v3 Physics source fingerprint") from exc
    if not isinstance(physics, Mapping) or not isinstance(physics.get("sources"), Mapping) or not physics.get("sha256"):
        raise RuntimeError("Physics source fingerprint is incomplete")
    package_root = Path(__file__).resolve().parent.parent
    physics_sources = dict(physics["sources"])
    missing = []
    for relative in _PREDICTIVE_PHYSICS_SOURCES:
        path = package_root / Path(relative)
        if not path.is_file() or relative not in physics_sources:
            missing.append(relative)
            continue
        if file_hash(path) != physics_sources[relative]:
            raise RuntimeError(f"Physics source fingerprint disagrees with {relative}")
    if missing:
        raise FileNotFoundError("Missing required Physics sources: " + ", ".join(missing))
    payload = {"predictive_contract_sources": sources, "physics": physics}
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return {"sha256": sha256_bytes(encoded), "sources": sources, "physics": physics}


def _canonical_digest(value: Any) -> str:
    return sha256_bytes(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode())


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False), encoding="utf-8")


def register_model(
    model: Any,
    *,
    provenance: Mapping[str, Any] | None = None,
    data_sha256: str | None = None,
    root: str | Path | None = None,
    metrics: Mapping[str, Any] | None = None,
    training_rows: int | None = None,
) -> dict[str, Any]:
    """Persist one new model under an immutable route-specific registry.

    The model id is content-addressed by route, candidate, feature schema,
    provenance, and data hash.  Existing folders are never overwritten.
    """

    root_path = Path(root) if root is not None else DEFAULT_REGISTRY_ROOT
    route_card = model.route_card() if hasattr(model, "route_card") else {}
    payload = dict(
        schema_version="model_registry_v3",
        route=route_card,
        feature_order=list(getattr(model, "feature_order", FEATURE_COLUMNS)),
        baseline_columns=list(BASELINE_COLUMNS),
        provenance=dict(provenance or {}),
        data_sha256=data_sha256,
        metrics=dict(metrics or {}),
    )
    model_id = "model_" + _canonical_digest(payload)[:20]
    folder = root_path / model_id
    if folder.exists():
        raise FileExistsError(f"Immutable v3 model already exists: {folder}")
    folder.mkdir(parents=True, exist_ok=False)
    model_path = folder / "model.joblib"
    # Compression is deterministic for a fixed estimator and keeps the local
    # registry reasonably small.  Joblib writes no external files here.
    joblib.dump(model, model_path, compress=3)
    card = dict(
        payload,
        model_id=model_id,
        model_sha256=file_hash(model_path),
        model_artifact_bytes=model_path.stat().st_size,
        runtime=runtime_versions(),
        source_fingerprint=source_fingerprint(),
        training_code_sha256=file_hash(Path(__file__).resolve().parent / "training.py"),
        training_rows=training_rows,
        persistence="joblib; load only trusted locally produced artifacts",
        hardware_recommendations_enabled=False,
        real_data_calibrated=False,
    )
    _write_json(folder / "card.json", card)
    return card


def _read_card(folder: Path) -> dict[str, Any]:
    card_path = folder / "card.json"
    model_path = folder / "model.joblib"
    if not card_path.is_file() or not model_path.is_file():
        raise FileNotFoundError(f"Incomplete v3 model folder: {folder}")
    try:
        card = json.loads(card_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError("Invalid v3 model card") from exc
    if card.get("schema_version") != "model_registry_v3":
        raise ValueError("Unsupported v3 model card schema")
    actual = file_hash(model_path)
    if actual != card.get("model_sha256"):
        raise ValueError("Model artifact hash mismatch")
    if card.get("model_id") != folder.name:
        raise ValueError("Model folder/card identity mismatch")
    return card


def load_model(folder: str | Path, expected_provenance: Mapping[str, Any] | None = None, *, expected_route: Mapping[str, Any] | None = None):
    """Load and verify a model artifact and its immutable card."""

    folder_path = Path(folder).resolve()
    card = _read_card(folder_path)
    installed = runtime_versions()
    for key in ("python", "numpy", "scipy", "sklearn", "joblib"):
        expected = card.get("runtime", {}).get(key)
        if expected is not None and installed.get(key) != expected:
            raise ValueError(f"Model runtime mismatch: {key}")
    recorded_source = card.get("source_fingerprint")
    if not isinstance(recorded_source, Mapping):
        raise ValueError("Model card is missing predictive source fingerprint")
    current_source = source_fingerprint()
    if dict(recorded_source) != dict(current_source):
        raise ValueError("Model predictive source fingerprint mismatch; regenerate and retrain")
    if expected_provenance is not None:
        recorded = card.get("provenance", {})
        if dict(recorded) != dict(expected_provenance):
            raise ValueError("Model/physics provenance mismatch; regenerate and retrain")
    if expected_route is not None:
        recorded_route = card.get("route", {})
        for key, value in expected_route.items():
            if recorded_route.get(key) != value:
                raise ValueError(f"Model route mismatch for {key}")
    model_bytes = (folder_path / "model.joblib").read_bytes()
    model = joblib.load(io.BytesIO(model_bytes))
    if tuple(getattr(model, "feature_order", ())) != tuple(card.get("feature_order", ())):
        raise ValueError("Model feature order/card mismatch")
    recorded_route = card.get("route", {})
    if not isinstance(recorded_route, Mapping):
        raise ValueError("Model card is missing route metadata")
    # A card hash alone cannot protect against a serialized object whose route
    # attributes disagree with the card.  Verify every serving identity field
    # after deserialization, then apply the caller's requested route gate.
    route_attributes = {
        "domain_id": "domain_id",
        "mode": "mode",
        "topology": "topology",
        "formulation": "formulation",
        "family": "family",
        "route_id": "route_id",
    }
    for attribute, card_key in route_attributes.items():
        expected_value = recorded_route.get(card_key)
        actual_value = getattr(model, attribute, None)
        if expected_value is None or actual_value != expected_value:
            raise ValueError(f"Model route/card attribute mismatch for {card_key}")
    aliases = {"domain": "domain", "topology_id": "topology"}
    for alias, attribute in aliases.items():
        if alias in recorded_route and getattr(model, attribute, None) != recorded_route[alias]:
            raise ValueError(f"Model route/card attribute mismatch for {alias}")
    return model, card


@lru_cache(maxsize=32)
def _load_cached(folder: str, model_hash: str, card_hash: str, provenance_json: str, route_json: str):
    provenance = json.loads(provenance_json) if provenance_json else None
    route = json.loads(route_json) if route_json else None
    return load_model(folder, provenance, expected_route=route)


def load_model_cached(folder: str | Path, expected_provenance: Mapping[str, Any] | None = None, *, expected_route: Mapping[str, Any] | None = None):
    folder_path = Path(folder).resolve()
    model_path, card_path = folder_path / "model.joblib", folder_path / "card.json"
    before = (file_hash(model_path), file_hash(card_path))
    provenance_json = json.dumps(expected_provenance, sort_keys=True, separators=(",", ":")) if expected_provenance is not None else ""
    route_json = json.dumps(expected_route, sort_keys=True, separators=(",", ":")) if expected_route is not None else ""
    result = _load_cached(str(folder_path), before[0], before[1], provenance_json, route_json)
    if before != (file_hash(model_path), file_hash(card_path)):
        raise ValueError("Model changed while loading")
    return result


# Short compatibility spelling for callers migrating from the v2 registry.
register = register_model


__all__ = [
    "DEFAULT_REGISTRY_ROOT",
    "file_hash",
    "runtime_versions",
    "source_fingerprint",
    "register_model",
    "register",
    "load_model",
    "load_model_cached",
]
