"""Acceptance gates for an extracted PowerNext v3 network release.

The script is deliberately an executable acceptance test rather than a build
helper.  It never installs packages, regenerates a manifest, trains a model,
or writes inside the release root.  Scientific imports and all v3 execution
run in the release's embedded ``runtime/python.exe``.  A checkout with no
trained v3 artifacts is reported as blocked and may run the Physics fallback
smoke checks with ``--allow-pending``; fallback output is never called an ML
acceptance.

Examples (run from the extracted release directory)::

    runtime\\python.exe -B tests\\verify_networks_release.py
    runtime\\python.exe -B tests\\verify_networks_release.py \
        --output C:\\Temp\\powernext-v3-release-acceptance.json \
        --allow-pending

The optional output must be outside the release root so the immutable package
cannot be changed while it is being verified.  Complete catalogue checks are
intentionally exhaustive for the two small max-modules=1 acceptance cases:
both cover stages 2 through 15 (504 distinct response candidates each).
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / "runtime" / ("python.exe" if os.name == "nt" else "bin/python")
MANIFEST = ROOT / "FINAL_FILE_MANIFEST.json"
METADATA = ROOT / "RELEASE_METADATA.json"
SELECTION = ROOT / "powernext" / "ml" / "results" / "networks_v3" / "selected_models.json"
REGISTRY = ROOT / "powernext" / "ml" / "registry" / "networks_v3"
ROUTES = tuple(
    f"{domain}:{mode}:{topology}"
    for domain in ("cpri_0p5uf", "research_3uf")
    for mode in ("LI", "SI")
    for topology in ("GSHUNT_v0", "OSHUNT_v0")
)
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")
_MODEL_ID_RE = re.compile(r"^model_[A-Za-z0-9_-]+$")
_MARKER = "__POWERnext_V3_ACCEPTANCE_RESULT__"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _relative(path: Path) -> str:
    return path.resolve().relative_to(ROOT.resolve()).as_posix()


def _is_mutable_path(relative: str) -> bool:
    """Mirror the builder's mutable/excluded path policy."""

    parts = Path(relative).parts
    return (
        relative == "data"
        or relative.startswith("data/")
        or relative == "evidence/test_logs"
        or relative.startswith("evidence/test_logs/")
        or "__pycache__" in parts
        or ".pytest_cache" in parts
    )


def _child_environment() -> dict[str, str]:
    """Start a clean environment for the bundled isolated Python runtime."""

    blocked_prefixes = ("PYTHON", "CONDA", "VIRTUAL_ENV", "PIP_")
    blocked_exact = {"HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY"}
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.upper().startswith(blocked_prefixes) and key.upper() not in blocked_exact
    }
    environment.update(
        {
            "POWERNEXT_TEST_OFFLINE": "1",
            "PYTHONNOUSERSITE": "1",
            # The embedded runtime's python312._pth supplies its own paths.
            "PYTHONPATH": "",
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
        }
    )
    return environment


def _run_child(name: str, code: str, payload: MappingLike, *, timeout: float) -> dict[str, Any]:
    """Run one JSON-in/JSON-out acceptance probe through the embedded runtime."""

    if not RUNTIME.is_file():
        return {
            "name": name,
            "status": "FAIL",
            "error": f"Bundled runtime is missing: {RUNTIME}",
        }
    started = time.monotonic()
    try:
        completed = subprocess.run(
            [str(RUNTIME), "-B", "-c", code],
            cwd=str(ROOT),
            env=_child_environment(),
            input=json.dumps(payload, sort_keys=True, allow_nan=False),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "name": name,
            "status": "FAIL",
            "error": f"Bundled runtime probe exceeded {timeout:.1f}s",
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "stdout_tail": _tail(exc.stdout),
            "stderr_tail": _tail(exc.stderr),
        }
    except OSError as exc:
        return {
            "name": name,
            "status": "FAIL",
            "error": str(exc),
            "elapsed_seconds": round(time.monotonic() - started, 3),
        }

    result: dict[str, Any] | None = None
    for line in reversed(completed.stdout.splitlines()):
        if line.startswith(_MARKER):
            try:
                result = json.loads(line[len(_MARKER) :])
            except json.JSONDecodeError:
                result = None
            break
    if result is None:
        result = {
            "status": "FAIL",
            "error": "Child did not return an acceptance result",
        }
    result = dict(result)
    result.setdefault("name", name)
    result.setdefault("status", "FAIL" if completed.returncode else "PASS")
    result["elapsed_seconds"] = round(time.monotonic() - started, 3)
    if completed.returncode:
        result["status"] = "FAIL"
        result.setdefault("error", f"Bundled runtime exited with code {completed.returncode}")
    if completed.stderr.strip():
        result["stderr_tail"] = _tail(completed.stderr)
    return result


def _tail(value: Any, limit: int = 2500) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        value = value.decode("utf-8", "replace")
    text = str(value)
    return text[-limit:]


class MappingLike(dict[str, Any]):
    """Typing-only alias that keeps this script stdlib-only."""


def _runtime_probe() -> dict[str, Any]:
    code = r'''
import importlib
import json
import socket
import sys
from pathlib import Path

payload = json.load(sys.stdin)
root = Path(payload["root"]).resolve()
import powernext_config  # noqa: F401  # installs the offline socket guard
modules = ["powernext_v3", "powernext_v3.application", "numpy", "scipy", "sklearn", "joblib"]
loaded = {name: importlib.import_module(name) for name in modules}
bad_paths = []
for value in sys.path:
    if not value:
        continue
    path = Path(value).resolve()
    if not path.is_relative_to(root):
        bad_paths.append(str(path))
bad_modules = {}
for name, module in loaded.items():
    path = getattr(module, "__file__", None)
    if path is None or not Path(path).resolve().is_relative_to(root):
        bad_modules[name] = path
blocked = False
error = None
sock = socket.socket()
try:
    sock.settimeout(0.2)
    sock.connect(("198.51.100.1", 9))
except OSError as exc:
    error = str(exc)
    blocked = "outbound network disabled" in error.lower()
else:
    error = "outbound connection unexpectedly succeeded"
finally:
    sock.close()
result = {
    "status": "PASS" if (
        Path(sys.executable).resolve().is_relative_to(root / "runtime")
        and Path(sys.prefix).resolve().is_relative_to(root / "runtime")
        and sys.flags.isolated == 1
        and sys.flags.no_site == 1
        and not bad_paths
        and not bad_modules
        and blocked
    ) else "FAIL",
    "executable": str(Path(sys.executable).resolve()),
    "prefix": str(Path(sys.prefix).resolve()),
    "isolated": bool(sys.flags.isolated),
    "no_site": bool(sys.flags.no_site),
    "sys_path": [str(Path(value).resolve()) if value else "" for value in sys.path],
    "module_files": {name: str(Path(getattr(module, "__file__", "")).resolve()) for name, module in loaded.items()},
    "bad_paths": bad_paths,
    "bad_modules": bad_modules,
    "outbound_socket_block": blocked,
    "outbound_socket_error": error,
}
print("__POWERnext_V3_ACCEPTANCE_RESULT__" + json.dumps(result, sort_keys=True))
'''
    return _run_child("bundled_runtime_isolation", code, {"root": str(ROOT)}, timeout=45.0)


def _manifest_check() -> tuple[dict[str, Any], list[dict[str, Any]], str | None]:
    """Validate a v3 manifest and return rows for the post-run immutability check."""

    base: dict[str, Any] = {
        "name": "package_manifest",
        "manifest_path": str(MANIFEST),
        "status": "BLOCKED",
        "rows_checked": 0,
        "hash_mismatches": [],
        "unexpected_files": [],
    }
    if not MANIFEST.is_file():
        base["reason"] = "BLOCKED_PENDING_PACKAGE_MANIFEST"
        return base, [], None
    manifest_digest = _sha256(MANIFEST)
    try:
        manifest = _json(MANIFEST)
    except (OSError, json.JSONDecodeError) as exc:
        base.update(status="FAIL", reason=f"Invalid FINAL_FILE_MANIFEST.json: {exc}")
        return base, [], manifest_digest
    if manifest.get("schema_version") != "powernext_release_manifest_v3":
        base.update(
            reason="BLOCKED_PENDING_PACKAGE_MANIFEST",
            actual_schema=manifest.get("schema_version"),
            expected_schema="powernext_release_manifest_v3",
        )
        return base, [], manifest_digest
    try:
        metadata = _json(METADATA)
        expected_version = metadata["application_version"]
    except (OSError, KeyError, json.JSONDecodeError) as exc:
        base.update(status="FAIL", reason=f"Invalid RELEASE_METADATA.json: {exc}")
        return base, [], manifest_digest
    if manifest.get("algorithm") != "SHA-256":
        base.update(status="FAIL", reason="Manifest algorithm is not SHA-256")
        return base, [], manifest_digest
    if manifest.get("application_version") != expected_version:
        base.update(
            status="FAIL",
            reason="Manifest application version does not match RELEASE_METADATA.json",
            manifest_application_version=manifest.get("application_version"),
            metadata_application_version=expected_version,
        )
        return base, [], manifest_digest
    rows = manifest.get("files")
    if not isinstance(rows, list) or not rows:
        base.update(status="FAIL", reason="Manifest files must be a non-empty list")
        return base, [], manifest_digest
    expected: set[str] = set()
    malformed: list[str] = []
    snapshot_rows: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("path"), str):
            malformed.append("row is not an object with a path")
            continue
        relative = row["path"].replace("\\", "/")
        path = (ROOT / Path(relative)).resolve()
        safe = (
            relative
            and not Path(relative).is_absolute()
            and ".." not in Path(relative).parts
            and path.is_relative_to(ROOT.resolve())
            and relative not in expected
            and relative != "FINAL_FILE_MANIFEST.json"
            and isinstance(row.get("bytes"), int)
            and row.get("bytes") >= 0
            and isinstance(row.get("sha256"), str)
            and bool(_HASH_RE.fullmatch(row["sha256"]))
        )
        if not safe:
            malformed.append(relative)
            continue
        expected.add(relative)
        snapshot_rows.append({"path": path, "relative": relative, "bytes": row["bytes"], "sha256": row["sha256"]})
    if malformed:
        base.update(status="FAIL", reason="Malformed or duplicate manifest rows", malformed_rows=malformed[:20])
        return base, snapshot_rows, manifest_digest
    mismatches: list[dict[str, Any]] = []
    for row in snapshot_rows:
        path = row["path"]
        if path.is_symlink() or not path.is_file():
            mismatches.append({"path": row["relative"], "reason": "MISSING_OR_LINKED"})
            continue
        actual_bytes = path.stat().st_size
        actual_sha = _sha256(path)
        if actual_bytes != row["bytes"] or actual_sha != row["sha256"]:
            mismatches.append(
                {
                    "path": row["relative"],
                    "reason": "CHANGED",
                    "expected_bytes": row["bytes"],
                    "actual_bytes": actual_bytes,
                    "expected_sha256": row["sha256"],
                    "actual_sha256": actual_sha,
                }
            )
    roots = {relative.split("/", 1)[0] for relative in expected if "/" in relative}
    unexpected: list[str] = []
    for root_name in sorted(roots):
        directory = ROOT / root_name
        if not directory.is_dir():
            continue
        for path in directory.rglob("*"):
            if not path.is_file():
                continue
            relative = path.relative_to(ROOT).as_posix()
            if relative == "FINAL_FILE_MANIFEST.json" or _is_mutable_path(relative):
                continue
            if relative not in expected:
                unexpected.append(relative)
    base.update(
        status="PASS" if not mismatches and not unexpected else "FAIL",
        rows_checked=len(snapshot_rows),
        hash_mismatches=mismatches[:20],
        hash_mismatch_count=len(mismatches),
        unexpected_files=unexpected[:20],
        unexpected_file_count=len(unexpected),
        manifest_sha256=manifest_digest,
        application_version=expected_version,
    )
    return base, snapshot_rows, manifest_digest


def _manifest_immutability(rows: Iterable[dict[str, Any]], manifest_digest: str | None) -> dict[str, Any]:
    """Re-hash the immutable rows after all child probes have completed."""

    if not rows or manifest_digest is None:
        return {
            "name": "package_immutability_after_execution",
            "status": "BLOCKED",
            "reason": "Manifest was not a valid v3 package manifest",
        }
    rows = list(rows)

    def check(row: dict[str, Any]) -> str | None:
        path = row["path"]
        if path.is_symlink() or not path.is_file():
            return row["relative"] + ":MISSING_OR_LINKED"
        if path.stat().st_size != row["bytes"] or _sha256(path) != row["sha256"]:
            return row["relative"] + ":CHANGED"
        return None

    with ThreadPoolExecutor(max_workers=8) as pool:
        changed = [value for value in pool.map(check, rows) if value]
    current_manifest_digest = _sha256(MANIFEST) if MANIFEST.is_file() else None
    return {
        "name": "package_immutability_after_execution",
        "status": "PASS" if not changed and current_manifest_digest == manifest_digest else "FAIL",
        "rows_rechecked": len(rows),
        "changed_files": changed[:20],
        "changed_file_count": len(changed),
        "manifest_sha256_before": manifest_digest,
        "manifest_sha256_after": current_manifest_digest,
    }


def _model_artifact_check() -> tuple[dict[str, Any], bool]:
    """Require exactly eight strict route artifacts when they are present."""

    base: dict[str, Any] = {
        "name": "selected_route_models",
        "required_routes": list(ROUTES),
        "status": "BLOCKED",
        "selection_path": str(SELECTION),
        "registry_path": str(REGISTRY),
    }
    if not SELECTION.is_file() or not REGISTRY.is_dir():
        base.update(
            reason="BLOCKED_PENDING_TRAINED_MODELS",
            selection_exists=SELECTION.is_file(),
            registry_exists=REGISTRY.is_dir(),
            missing_routes=list(ROUTES),
        )
        return base, False
    try:
        selection = _json(SELECTION)
    except (OSError, json.JSONDecodeError) as exc:
        base.update(status="FAIL", reason=f"Invalid selected_models.json: {exc}")
        return base, False
    if not isinstance(selection, dict) or set(selection) != set(ROUTES):
        base.update(
            status="FAIL",
            reason="selected_models.json must contain exactly eight v3 routes",
            actual_routes=sorted(selection) if isinstance(selection, dict) else None,
        )
        return base, False
    invalid: list[str] = []
    missing: list[dict[str, str]] = []
    for route in ROUTES:
        identifier = selection.get(route)
        valid_id = isinstance(identifier, str) and Path(identifier).name == identifier and bool(_MODEL_ID_RE.fullmatch(identifier))
        folder = REGISTRY / identifier if valid_id else None
        if not valid_id or folder is None:
            invalid.append(route)
            continue
        for filename in ("card.json", "model.joblib"):
            path = folder / filename
            if not path.is_file() or path.is_symlink():
                missing.append({"route": route, "path": str(path)})
    if invalid:
        base.update(status="FAIL", reason="Invalid selected model identifiers", invalid_routes=invalid)
        return base, False
    if missing:
        base.update(status="BLOCKED", reason="BLOCKED_PENDING_TRAINED_MODELS", missing_assets=missing)
        return base, False
    child_code = r'''
import json
from pathlib import Path
import powernext_config  # noqa: F401  # installs the offline socket guard
from powernext_v3.optimizer import load_predictor

payload = json.load(__import__("sys").stdin)
loaded = []
for route in payload["routes"]:
    domain, mode, topology = route.split(":")
    request = {"domain_id": domain, "impulse_type": mode, "topology_id": topology}
    model, card = load_predictor(request, registry=payload["registry"], selection=payload["selection"])
    card_route = card.get("route", {})
    if card_route.get("domain_id", card_route.get("domain")) != domain:
        raise ValueError(route + ": card domain mismatch")
    if card_route.get("mode") != mode or card_route.get("topology", card_route.get("topology_id")) != topology:
        raise ValueError(route + ": card route mismatch")
    if getattr(model, "route_id", None) != route:
        raise ValueError(route + ": loaded model route mismatch")
    loaded.append({"route": route, "model_id": card.get("model_id"), "card_schema": card.get("schema_version")})
print("__POWERnext_V3_ACCEPTANCE_RESULT__" + json.dumps({"status": "PASS", "loaded": loaded}, sort_keys=True))
'''
    child = _run_child(
        "strict_selected_route_model_loads",
        child_code,
        {"routes": list(ROUTES), "registry": str(REGISTRY), "selection": str(SELECTION)},
        timeout=180.0,
    )
    base.update(child)
    base["name"] = "selected_route_models"
    return base, child.get("status") == "PASS"


def _fixed_prediction_check(models_available: bool) -> dict[str, Any]:
    """Run all eight fixed routes and attach scalar values in a temp store."""

    child_code = r'''
import copy
import json
from pathlib import Path
import powernext_config  # noqa: F401  # installs the offline socket guard
from powernext_v3.application import V3Application

payload = json.load(__import__("sys").stdin)
app = V3Application(payload["data_dir"], registry=payload["registry"], selection=payload["selection"], workers=1)
records = []
try:
    for route in payload["routes"]:
        domain, mode, topology = route.split(":")
        request = app.default_request()
        request.update({
            "request_id": "RELEASE_ACCEPTANCE_" + route.replace(":", "_"),
            "domain_id": domain,
            "impulse_type": mode,
            "topology_id": topology,
            "target_crest_V": 1000000.0 if mode == "LI" else 1300000.0,
            "search_mode": "complete",
            "priority": "complete_physics",
            "max_modules": 1,
            "stages": list(range(2, 16)),
        })
        configuration = {
            "impulse_type": mode,
            "topology_id": topology,
            "polarity": 1,
            "stages": 2,
            "stage_charge_V": 50000.0,
            # This supplied pair gives a clean evaluator trace for every
            # provisional domain/topology while remaining inside the solver's
            # 200 ms reference window.  It is a fixed Physics smoke
            # configuration, not an optimizer claim.
            "front_per_stage_ohm": 180.0,
            "tail_per_stage_ohm": 30.0,
            "front_network": {"op": "R", "ohm": 180},
            "tail_network": {"op": "R", "ohm": 30},
        }
        record = app.predict_fixed({"request": request, "configuration": configuration})
        physics = record.get("physics", {})
        if physics.get("application_status") != "PHYSICS_VERIFIED":
            raise ValueError(route + ": Physics was not verified: " + str(physics.get("error")))
        before = copy.deepcopy(record)
        metrics = physics.get("metrics", {})
        front_key = "T1_s" if mode == "LI" else "Tp_s"
        reference = {
            "crest_magnitude_V": metrics.get("crest_magnitude_V"),
            front_key: metrics.get(front_key),
            "T2_s": metrics.get("T2_s"),
        }
        if any(value is None for value in reference.values()):
            raise ValueError(route + ": Physics metrics did not contain scalar reference values")
        comparison = app.attach_reference_metrics(
            record["prediction_id"], reference,
            {"source_organization": "offline_release_acceptance", "source_kind": "frozen_physics_scalar_fixture"},
        )
        restored = app.get_reference(record["prediction_id"], comparison["comparison_id"])
        after = app.get_prediction(record["prediction_id"])
        errors = comparison.get("comparison", {})
        if comparison.get("raw_sha256") is not None or comparison.get("qualification", {}).get("status") != "NUMERICAL_SCALAR_REFERENCE_ONLY":
            raise ValueError(route + ": scalar comparison was not marked correctly")
        if before != after or restored.get("comparison_id") != comparison.get("comparison_id"):
            raise ValueError(route + ": frozen prediction changed after reference attachment")
        if any(item.get("absolute_error") not in (0, 0.0) for item in errors.values()):
            raise ValueError(route + ": self scalar comparison was not exact")
        records.append({
            "route": route,
            "prediction_id": record["prediction_id"],
            "comparison_id": comparison["comparison_id"],
            "prediction_status": record["prediction"]["status"],
            "model_status": record["model"]["status"],
            "physics_status": physics["application_status"],
            "qualification": comparison["qualification"]["status"],
            "raw_sha256": comparison.get("raw_sha256"),
        })
finally:
    app.close()
fallback = any(row["prediction_status"] == "PHYSICS_FALLBACK" for row in records)
model_expected = bool(payload["models_available"])
correct_model_state = all(
    (row["prediction_status"] == "ML_PREDICTION" and row["model_status"] == "LOADED") if model_expected
    else (row["prediction_status"] == "PHYSICS_FALLBACK" and row["model_status"] == "UNAVAILABLE")
    for row in records
)
print("__POWERnext_V3_ACCEPTANCE_RESULT__" + json.dumps({
    "status": "PASS" if len(records) == 8 and correct_model_state else "FAIL",
    "mode": "ML_ACCEPTANCE" if model_expected else "PHYSICS_FALLBACK_SMOKE",
    "fallback_used": fallback,
    "records": records,
}, sort_keys=True))
'''
    with tempfile.TemporaryDirectory(prefix="powernext-v3-release-acceptance-") as directory:
        child = _run_child(
            "fixed_prediction_and_scalar_reference",
            child_code,
            {
                "routes": list(ROUTES),
                "root": str(ROOT),
                "data_dir": str(Path(directory) / "v3"),
                "registry": str(REGISTRY),
                "selection": str(SELECTION),
                "models_available": models_available,
            },
            timeout=240.0,
        )
    child["name"] = "fixed_prediction_and_scalar_reference"
    return child


def _complete_catalog_check() -> dict[str, Any]:
    """Exhaustively verify one LI rare and one SI small catalogue."""

    rare_path = ROOT / "powernext" / "optimizer" / "examples" / "LI_rare_timing_pass_recommendation.json"
    si_path = ROOT / "powernext" / "optimizer" / "examples" / "SI_request.json"
    if not rare_path.is_file() or not si_path.is_file():
        return {
            "name": "complete_small_catalogues",
            "status": "FAIL",
            "error": "Required optimizer request fixtures are missing",
        }
    try:
        rare = _json(rare_path)
        si = _json(si_path)
        rare_request = rare["request"]
        si_setup = si["setup"]
    except (OSError, KeyError, json.JSONDecodeError) as exc:
        return {"name": "complete_small_catalogues", "status": "FAIL", "error": str(exc)}
    common = {
        "schema_version": "network_request_v3",
        "polarity": 1,
        "topology_id": "GSHUNT_v0",
        "max_modules": 1,
        "stages": list(range(2, 16)),
        "search_mode": "complete",
        "priority": "complete_physics",
        "max_ml_candidates": 2000000,
        "max_physics_evaluations": 1000,
        "budget_seconds": 240.0,
        "alternatives": 4,
        "inventory": None,
        "assumptions": ["Offline release acceptance; exhaustive mathematical catalogue."],
    }
    li = dict(common, request_id="RELEASE_ACCEPTANCE_LI_RARE", domain_id="cpri_0p5uf", impulse_type="LI", target_crest_V=1000000.0, setup=rare_request["setup"])
    si = dict(common, request_id="RELEASE_ACCEPTANCE_SI", domain_id="cpri_0p5uf", impulse_type="SI", target_crest_V=1300000.0, setup=si_setup)
    child_code = r'''
import json
import powernext_config  # noqa: F401  # installs the offline socket guard
from powernext_v3.optimizer import recommend

payload = json.load(__import__("sys").stdin)
records = []
for item in payload["requests"]:
    name = item["name"]
    result, _ = recommend(item["request"], registry=payload["registry"], selection=payload["selection"], retain_waveforms=False)
    search = result["search"]
    best = result.get("best_configuration")
    best_configuration = None if best is None else best.get("configuration", {})
    expected_pass = item["expected_passing_count"]
    valid = (
        search.get("catalog_complete") is True
        and search.get("theoretical_recipe_configurations") == 504
        and search.get("distinct_response_candidates") == 504
        and search.get("physics_evaluated_count") == 504
        and search.get("considered_count") == 504
        and search.get("passing_count") == expected_pass
    )
    if name == "LI_rare":
        valid = valid and best_configuration is not None and (
            best_configuration.get("stages"),
            best_configuration.get("front_per_stage_ohm"),
            best_configuration.get("tail_per_stage_ohm"),
        ) == (7, 30.0, 180.0)
    records.append({
        "name": name,
        "status": "PASS" if valid else "FAIL",
        "result_status": result.get("status"),
        "catalog_complete": search.get("catalog_complete"),
        "theoretical_recipe_configurations": search.get("theoretical_recipe_configurations"),
        "distinct_response_candidates": search.get("distinct_response_candidates"),
        "considered_count": search.get("considered_count"),
        "physics_evaluated_count": search.get("physics_evaluated_count"),
        "passing_count": search.get("passing_count"),
        "unsupported_count": search.get("unsupported_count"),
        "best_configuration": best_configuration,
    })
print("__POWERnext_V3_ACCEPTANCE_RESULT__" + json.dumps({
    "status": "PASS" if all(row["status"] == "PASS" for row in records) else "FAIL",
    "catalogues": records,
}, sort_keys=True))
'''
    return _run_child(
        "complete_small_catalogues",
        child_code,
        {
            "requests": [
                {"name": "LI_rare", "request": li, "expected_passing_count": 1},
                {"name": "SI", "request": si, "expected_passing_count": 14},
            ],
            "registry": str(REGISTRY),
            "selection": str(SELECTION),
        },
        timeout=360.0,
    )


def _write_output(path: Path | None, report: dict[str, Any]) -> None:
    if path is None:
        return
    path = path.resolve()
    if path == ROOT or path.is_relative_to(ROOT):
        raise ValueError("--output must be outside the extracted release root")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Write the report outside the release root")
    parser.add_argument(
        "--allow-pending",
        action="store_true",
        help="Return zero for explicit pending model/manifest gates after running fallback smoke checks",
    )
    args = parser.parse_args(argv)
    report: dict[str, Any] = {
        "schema_version": "powernext_v3_release_acceptance_v1",
        "root": str(ROOT),
        "runtime": str(RUNTIME),
        "offline": True,
        "started_at_epoch": time.time(),
        "builder_review": {
            "path": "tools/build_networks_release.py",
            "status": "REQUIREMENTS_CHECKED_INDEPENDENTLY_BY_THIS_HARNESS",
            "requirement": "Every selected model must include card.json and model.joblib and pass source, runtime, hash and route compatibility checks. The builder also validates these before copying.",
        },
        "checks": [],
        "pending_reasons": [],
    }
    try:
        if args.output is not None and args.output.resolve().is_relative_to(ROOT):
            raise ValueError("--output must be outside the extracted release root")
        runtime = _runtime_probe()
        report["checks"].append(runtime)
        manifest, rows, manifest_digest = _manifest_check()
        report["checks"].append(manifest)
        models, models_available = _model_artifact_check()
        report["checks"].append(models)
        # The fixed path always runs.  If trained artifacts are absent this is
        # explicitly a Physics fallback smoke test, not a model acceptance.
        fixed = _fixed_prediction_check(models_available)
        report["checks"].append(fixed)
        catalog = _complete_catalog_check()
        report["checks"].append(catalog)
        report["checks"].append(_manifest_immutability(rows, manifest_digest))
    except Exception as exc:
        report["checks"].append({"name": "harness", "status": "FAIL", "error": str(exc)})
    statuses = [check.get("status") for check in report["checks"]]
    if "FAIL" in statuses:
        status = "FAIL"
        code = 1
    elif "BLOCKED" in statuses:
        status = "BLOCKED"
        code = 0 if args.allow_pending else 2
        report["pending_reasons"] = [
            check.get("reason")
            for check in report["checks"]
            if check.get("status") == "BLOCKED" and check.get("reason")
        ]
    else:
        status = "PASS"
        code = 0
    report["status"] = status
    report["completed_at_epoch"] = time.time()
    try:
        _write_output(args.output, report)
    except Exception as exc:
        report["status"] = "FAIL"
        report["checks"].append({"name": "report_output", "status": "FAIL", "error": str(exc)})
        code = 1
    print(json.dumps(report, indent=2, sort_keys=True, allow_nan=False))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
