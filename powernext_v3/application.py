"""Offline application boundary for the independent PowerNext v3 stack.

The legacy application owns the original ``/api`` routes and result store.
This module gives the network catalogue its own small, versioned application
surface.  Search jobs are persisted before work starts, progress is written
atomically, and an artifact is visible only after the optimizer child process
has saved every waveform and its result hash.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import math
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
import re
import sys
import threading
import time
import uuid
from typing import Any, Mapping

import numpy as np

from . import ROOT
from .features import baseline, feature_matrix
from .networks import COMPONENTS, canonicalize, equivalent_resistance
from .optimizer import (
    REGISTRY as DEFAULT_REGISTRY,
    SELECTION as DEFAULT_SELECTION,
    load_predictor,
    normalize_request,
)
from .profiles import PROFILES


SCHEMA_VERSION = "network_application_v3"
PREDICTION_SCHEMA = "network_prediction_v3"
REFERENCE_SCHEMA = "network_reference_comparison_v3"
_ID_RE = re.compile(r"^(?:v3|pred_v3)_[a-f0-9]{20}$")
_LOAD_FEATURE_UNSUPPORTED = "L0 feature baseline does not support load_resistance_ohm; use the physics route"
# The live product is intentionally fixed to exactly two resistor modules per
# branch.  ``networks.py`` and the historical catalog still retain the
# one-through-four-module synthesis space for archival replay; this boundary
# is where the active product scope is enforced.
PUBLIC_MAX_MODULES = 2
PUBLIC_MODULE_OPTIONS = (2,)
UNSUPPORTED_CURRENT_SCOPE = "UNSUPPORTED_CURRENT_SCOPE"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _digest(value: Any) -> str:
    return _sha256_bytes(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    )


def _json_copy(value: Any) -> Any:
    """Copy only JSON values, rejecting non-finite values at the boundary."""

    return json.loads(json.dumps(value, allow_nan=False))


def _network_module_count(tree: Mapping[str, Any]) -> int:
    """Count resistor leaves in an already canonical JSON tree."""

    if tree.get("op") == "R":
        return 1
    children = tree.get("children")
    if not isinstance(children, list):
        raise ValueError("network tree children must be a list")
    return sum(_network_module_count(child) for child in children)


def normalize_public_request(raw: Mapping[str, Any]) -> tuple[dict[str, Any], Any]:
    """Normalize a request at the active application/CLI scope boundary.

    The low-level catalogue still supports its historical one-through-four
    module space.  The live application and CLI require exactly two modules
    per front and tail branch, rejecting single-part, three-module, and
    four-module requests before a job or result artifact can be created.
    """

    if not isinstance(raw, Mapping):
        raise ValueError("Request must be an object")
    value = dict(raw)
    value.setdefault("min_modules", PUBLIC_MAX_MODULES)
    value.setdefault("max_modules", PUBLIC_MAX_MODULES)
    for name in ("min_modules", "max_modules"):
        requested = value.get(name)
        if type(requested) is int and requested != PUBLIC_MAX_MODULES:
            raise ValueError(
                f"{UNSUPPORTED_CURRENT_SCOPE}: {name}={requested!r} is outside the active exact-two scope; "
                "the public product requires exactly 2 resistor modules in both the front and tail branches. "
                "Single-part, three-module, and four-module historical artifacts remain retained only for "
                "low-level replay.",
            )
    return normalize_request(value)


def _write_json_atomic(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".{uuid.uuid4().hex}.tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False), encoding="utf-8")
    os.replace(temporary, path)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _safe_id(value: Any, *, prefix: str) -> str:
    if not isinstance(value, str) or not _ID_RE.fullmatch(value) or not value.startswith(prefix):
        raise ValueError("Invalid v3 identifier")
    return value


def _finite_number(value: Any, name: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float, np.number)):
        raise ValueError(f"{name} must be a finite number")
    result = float(value)
    if not math.isfinite(result) or (positive and result <= 0):
        raise ValueError(f"{name} must be a finite {'positive ' if positive else ''}number")
    return result


def _default_request() -> dict[str, Any]:
    return {
        "schema_version": "network_request_v3",
        "request_id": "NETWORK_UI_DEFAULT",
        "domain_id": "cpri_0p5uf",
        "impulse_type": "LI",
        "topology_id": "GSHUNT_v0",
        "target_crest_V": 1_000_000.0,
        "polarity": 1,
        "setup": {
            "setup_id": "V3_UI_DECLARED_SETUP",
            "dut_capacitance_F": 850e-12,
            "divider_capacitance_F": 500e-12,
            "stray_capacitance_F": 150e-12,
            "loop_inductance_H": 18.5e-6,
            "loop_resistance_ohm": 0.0,
            "basic_coverage_assumption": "ADDITIONAL_DISJOINT",
            "auxiliary_assumption": "UNCONFIRMED_AUXILIARY_BRANCHES_OMITTED",
        },
        "min_modules": PUBLIC_MAX_MODULES,
        "max_modules": PUBLIC_MAX_MODULES,
        "stages": list(range(2, 16)),
        "search_mode": "adaptive",
        "priority": "combined",
        "max_ml_candidates": 4096,
        "max_physics_evaluations": 128,
        "budget_seconds": 90.0,
        "alternatives": 4,
        "inventory": None,
        "assumptions": [
            "Uniform ideal two-terminal resistor networks are a declared research model.",
            "Component quantities, sockets, pulse ratings, and mounting remain unknown.",
        ],
    }


class V3Application:
    """Persisted, local-only v3 jobs, predictions, and reference comparisons."""

    def __init__(
        self,
        data_dir: str | Path,
        *,
        registry: str | Path | None = None,
        selection: str | Path | None = None,
        workers: int = 1,
        timeout_seconds: float = 90.0,
    ) -> None:
        if isinstance(workers, bool) or type(workers) is not int or not 1 <= workers <= 4:
            raise ValueError("v3 workers must be an integer from 1 through 4")
        self.root = Path(data_dir).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.jobs = self.root / "jobs"
        self.jobs.mkdir(exist_ok=True)
        self.predictions = self.root / "predictions"
        self.predictions.mkdir(exist_ok=True)
        self.registry = Path(registry or DEFAULT_REGISTRY).resolve()
        self.selection = Path(selection or DEFAULT_SELECTION).resolve()
        self.timeout_seconds = _finite_number(timeout_seconds, "timeout_seconds", positive=True)
        self.executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="powernext-v3")
        self._lock = threading.RLock()
        self._futures: dict[str, Any] = {}
        self._recover_interrupted()

    def close(self) -> None:
        self.executor.shutdown(wait=True)

    # ------------------------------------------------------------------ metadata and validation
    @staticmethod
    def default_request() -> dict[str, Any]:
        return _default_request()

    def _model_routes(self) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        for domain in PROFILES:
            for mode in ("LI", "SI"):
                for topology in ("GSHUNT_v0", "OSHUNT_v0"):
                    route = f"{domain}:{mode}:{topology}"
                    available = False
                    identifier = None
                    if self.selection.is_file():
                        try:
                            mapping = _read_json(self.selection)
                            identifier = mapping.get(route)
                            available = (
                                isinstance(identifier, str)
                                and (self.registry / identifier / "card.json").is_file()
                                and (self.registry / identifier / "model.joblib").is_file()
                            )
                        except (OSError, ValueError, TypeError, json.JSONDecodeError):
                            available = False
                    result[route] = {
                        "available": available,
                        "model_id": identifier if available else None,
                        "fallback": "PHYSICS_L0_BASELINE_UNTIL_TRAINED_MODEL_IS_AVAILABLE",
                    }
        return result

    def metadata(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "application_version": "3.0.0",
            "offline": True,
            "hardware_control": False,
            "components_ohm": list(COMPONENTS),
            "min_modules": PUBLIC_MAX_MODULES,
            "max_modules": PUBLIC_MAX_MODULES,
            "supported_module_bounds": list(PUBLIC_MODULE_OPTIONS),
            "network_scope": "EXACTLY_TWO_MODULES_PER_BRANCH",
            "profiles": [profile.as_dict() for profile in PROFILES.values()],
            "default_request": self.default_request(),
            "model_routes": self._model_routes(),
            "model_policy": "MODEL_PREDICTION_ONLY_WHEN_A_ROUTE_ARTIFACT_LOADS; OTHERWISE_EXPLICIT_PHYSICS_L0_FALLBACK",
            "endpoints": {
                "validate": "/api/v3/validate",
                "runs": "/api/v3/runs",
                "predict": "/api/v3/predict",
                "predictions": "/api/v3/predictions/{prediction_id}",
                "prediction_waveform": "/api/v3/predictions/{prediction_id}/waveform",
                "reference_metrics": "/api/v3/predictions/{prediction_id}/reference-metrics",
            },
            "limitations": [
                "Topology and mounting are provisional mathematical hypotheses.",
                "Inventory quantities, pulse ratings, insulation, and thermal duty remain unresolved.",
                "Measured traces retain their raw bytes and use the existing evaluator limitations; they do not establish IEC or laboratory qualification.",
            ],
            "data_directory": str(self.root),
        }

    def validate(self, raw: Mapping[str, Any]) -> dict[str, Any]:
        if not isinstance(raw, Mapping):
            raise ValueError("Request must be an object")
        request, catalog = normalize_public_request(raw)
        routes = self._model_routes()
        route = f"{request['domain_id']}:{request['impulse_type']}:{request['topology_id']}"
        return {
            "schema_version": SCHEMA_VERSION,
            "request": request,
            "catalog": catalog.info(),
            "route": route,
            "model": routes.get(route),
            "component_inventory": list(COMPONENTS),
            "valid": True,
        }

    # ------------------------------------------------------------------ persisted jobs
    def _job_dir(self, job_id: str) -> Path:
        job_id = _safe_id(job_id, prefix="v3_")
        path = (self.jobs / job_id).resolve()
        if not path.is_relative_to(self.jobs.resolve()):
            raise ValueError("Invalid v3 job path")
        return path

    def _state_path(self, job_id: str) -> Path:
        return self._job_dir(job_id) / "state.json"

    def _read_state(self, job_id: str) -> dict[str, Any]:
        # Windows can briefly deny a reader while another thread replaces the
        # state file.  Serialize readers with the atomic writer so status
        # polling never leaks that filesystem race to the API caller.
        with self._lock:
            path = self._state_path(job_id)
            if not path.is_file():
                raise FileNotFoundError("v3 run not found")
            state = _read_json(path)
            if state.get("job_id") != job_id:
                raise ValueError("v3 run identity mismatch")
            return state

    def _update_state(self, job_id: str, **changes: Any) -> dict[str, Any]:
        with self._lock:
            state = self._read_state(job_id)
            state.update(changes)
            state["updated_at"] = _now()
            _write_json_atomic(self._state_path(job_id), state)
            return state

    def _recover_interrupted(self) -> None:
        for state_path in self.jobs.glob("v3_*/state.json"):
            try:
                state = _read_json(state_path)
            except (OSError, ValueError, json.JSONDecodeError):
                continue
            if state.get("status") in {"QUEUED", "RUNNING"}:
                state.update(
                    status="FAILED",
                    progress="Interrupted before a complete artifact was published",
                    error="The prior application process stopped before the immutable result was committed.",
                    completed_at=_now(),
                    updated_at=_now(),
                )
                _write_json_atomic(state_path, state)

    def _new_job(self, request: dict[str, Any]) -> dict[str, Any]:
        job_id = "v3_" + uuid.uuid4().hex[:20]
        folder = self._job_dir(job_id)
        folder.mkdir(parents=True, exist_ok=False)
        state = {
            "schema_version": "network_job_v3",
            "job_id": job_id,
            "run_id": job_id,
            "status": "QUEUED",
            "created_at": _now(),
            "updated_at": _now(),
            "progress": "Queued",
            "events": [],
            "execution_log": "execution.log",
            "request": request,
            "result_sha256": None,
            "result_status": None,
            "error": None,
        }
        _write_json_atomic(folder / "request.json", request)
        _write_json_atomic(folder / "state.json", state)
        return state

    def start_search(self, raw: Mapping[str, Any]) -> dict[str, Any]:
        validated = self.validate(raw)
        with self._lock:
            active = [
                item["job_id"]
                for item in self.list_runs()
                if item.get("status") in {"QUEUED", "RUNNING"}
            ]
            if active:
                raise ValueError(f"A v3 search is already active: {active[0]}")
            state = self._new_job(validated["request"])
            job_id = state["job_id"]
            future = self.executor.submit(self._run_search, job_id, validated["request"])
            self._futures[job_id] = future
        return state

    # Legacy-style naming makes the facade easy to mount beside the existing
    # application while keeping all paths and records v3-specific.
    optimize = start_search
    create_run = start_search

    def _progress(self, job_id: str, message: str) -> None:
        if not isinstance(message, str):
            message = str(message)
        message = message.strip()[:500] or "Working"
        with self._lock:
            state = self._read_state(job_id)
            events = list(state.get("events", []))
            if not events or events[-1].get("message") != message:
                events.append({"at": _now(), "message": message})
            state.update(progress=message, events=events[-200:], updated_at=_now())
            _write_json_atomic(self._state_path(job_id), state)

    def _run_search(self, job_id: str, request: dict[str, Any]) -> None:
        started = time.perf_counter()
        self._update_state(job_id, status="RUNNING", progress="Starting versioned Physics + ML search")
        artifact = self._job_dir(job_id) / "artifact"
        execution_log = self._job_dir(job_id) / "execution.log"
        try:
            # Keep the optimizer in a killable child process.  It writes the
            # complete result into a new private directory only after every
            # waveform and hash is saved; a timeout or crash therefore cannot
            # promote a partial recommendation through this application.
            from powernext_app.process import stream_process

            command = [
                sys.executable,
                "-B",
                "-m",
                "powernext_v3",
                "optimize",
                "--request",
                str(self._job_dir(job_id) / "request.json"),
                "--output",
                str(artifact),
                "--registry",
                str(self.registry),
                "--selection",
                str(self.selection),
            ]
            timeout = min(self.timeout_seconds, float(request["budget_seconds"]) + 30.0)
            with execution_log.open("w", encoding="utf-8", newline="") as output:
                code = stream_process(
                    command,
                    cwd=ROOT,
                    env=os.environ.copy(),
                    output=output,
                    on_progress=lambda message: self._progress(job_id, message),
                    timeout_seconds=timeout,
                )
            if code != 0:
                raise RuntimeError(f"v3 optimizer process exited with code {code}")
            result_path = artifact / "result.json"
            if not result_path.is_file():
                raise RuntimeError("v3 optimizer exited without a complete result artifact")
            result = _read_json(result_path)
            if result.get("schema_version") != "network_result_v3":
                raise RuntimeError("v3 optimizer wrote an unexpected result schema")
            result_hash = _sha256_bytes(result_path.read_bytes())
            self._update_state(
                job_id,
                status="COMPLETED",
                progress="Complete",
                completed_at=_now(),
                elapsed_seconds=time.perf_counter() - started,
                result_sha256=result_hash,
                result_status=result.get("status"),
                result_path="artifact/result.json",
                search=result.get("search", {}),
            )
        except Exception as exc:  # preserve the failed state and never publish a partial result
            if artifact.exists():
                # Keep forensic bytes private while ensuring the public
                # ``artifact/result.json`` path can never look publishable
                # after a timeout, crash, or schema failure.
                try:
                    os.replace(artifact, self._job_dir(job_id) / f"failed_artifact_{uuid.uuid4().hex}")
                except OSError:
                    pass
            self._update_state(
                job_id,
                status="FAILED",
                progress="Search failed; no partial result was published",
                completed_at=_now(),
                elapsed_seconds=time.perf_counter() - started,
                error=str(exc),
            )
        finally:
            with self._lock:
                self._futures.pop(job_id, None)

    def list_runs(self) -> list[dict[str, Any]]:
        with self._lock:
            values: list[dict[str, Any]] = []
            for path in self.jobs.glob("v3_*/state.json"):
                try:
                    values.append(_read_json(path))
                except (OSError, ValueError, json.JSONDecodeError):
                    continue
            return sorted(values, key=lambda item: (item.get("created_at", ""), item.get("job_id", "")), reverse=True)

    list_jobs = list_runs

    def _result_path(self, job_id: str, state: dict[str, Any] | None = None) -> Path:
        state = state or self._read_state(job_id)
        if state.get("status") != "COMPLETED" or state.get("result_path") != "artifact/result.json":
            raise ValueError("v3 run has no completed result")
        path = self._job_dir(job_id) / "artifact" / "result.json"
        if not path.is_file() or _sha256_bytes(path.read_bytes()) != state.get("result_sha256"):
            raise ValueError("v3 result integrity mismatch")
        return path

    def get_run(self, job_id: str) -> dict[str, Any]:
        state = self._read_state(job_id)
        result = None
        if state.get("status") == "COMPLETED":
            result = _read_json(self._result_path(job_id, state))
        return {"run": state, "result": result}

    get_job = get_run

    def _candidate(self, job_id: str, candidate_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
        if not isinstance(candidate_id, str) or not re.fullmatch(r"net_[a-f0-9]+_[0-9]+", candidate_id):
            raise ValueError("Invalid candidate identifier")
        result = _read_json(self._result_path(job_id))
        for row in result.get("candidates", []):
            if row.get("candidate_id") == candidate_id:
                return result, row
        raise FileNotFoundError("v3 candidate not found")

    def waveform(self, job_id: str, candidate_id: str) -> dict[str, Any]:
        result, row = self._candidate(job_id, candidate_id)
        reference = row.get("waveform_reference")
        if not isinstance(reference, Mapping):
            raise ValueError("Candidate has no waveform artifact")
        relative = reference.get("path")
        if not isinstance(relative, str):
            raise ValueError("Invalid waveform reference")
        root = (self._job_dir(job_id) / "artifact").resolve()
        path = (root / relative).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError("Waveform path escapes the v3 artifact")
        if _sha256_bytes(path.read_bytes()) != reference.get("sha256"):
            raise ValueError("v3 waveform integrity mismatch")
        with np.load(path, allow_pickle=False) as archive:
            time_s = archive["time_s"].tolist()
            voltage_v = archive["voltage_V"].tolist()
        return {
            "schema_version": "network_waveform_v3",
            "job_id": job_id,
            "candidate_id": candidate_id,
            "request": result.get("request"),
            "time_s": time_s,
            "voltage_V": voltage_v,
            "sha256": reference.get("sha256"),
        }

    # ------------------------------------------------------------------ fixed unseen prediction and immutable reference comparison
    def _fixed_inputs(self, raw: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
        if not isinstance(raw, Mapping):
            raise ValueError("Prediction request must be an object")
        if "request" in raw:
            request_raw = raw["request"]
            configuration = raw.get("configuration")
        else:
            request_raw = {key: value for key, value in raw.items() if key not in {"configuration", "reference"}}
            configuration = raw.get("configuration")
        if not isinstance(request_raw, Mapping) or not isinstance(configuration, Mapping):
            raise ValueError("A fixed prediction requires request and configuration objects")
        request, _ = normalize_public_request(request_raw)
        configuration = _json_copy(dict(configuration))
        # A fixed prediction has one immutable route identity.  Defaults make
        # the compact UI configuration convenient, but explicit route fields
        # must agree with the request before Physics or artifact creation.
        for name in ("impulse_type", "topology_id", "polarity", "domain_id"):
            if name not in configuration:
                continue
            expected = request[name] if name != "domain_id" else request["domain_id"]
            if configuration[name] != expected:
                raise ValueError(f"configuration {name} does not match request: expected {expected!r}")
        configuration.setdefault("impulse_type", request["impulse_type"])
        configuration.setdefault("topology_id", request["topology_id"])
        configuration.setdefault("polarity", request["polarity"])
        for branch in ("front_network", "tail_network"):
            if branch not in configuration:
                raise ValueError(
                    f"{UNSUPPORTED_CURRENT_SCOPE}: fixed prediction requires an exactly-two-resistor "
                    f"{branch} S/P tree; single-part and historical three-/four-module trees are unavailable."
                )
            configuration[branch] = canonicalize(configuration[branch])
            count = _network_module_count(configuration[branch])
            if count != PUBLIC_MAX_MODULES:
                raise ValueError(
                    f"{UNSUPPORTED_CURRENT_SCOPE}: {branch} uses {count} resistor modules; "
                    "the public fixed-recipe scope requires exactly 2 in both the front and tail branches. "
                    "Single-part, three-module, and four-module historical trees remain available only in "
                    "retained low-level artifacts."
                )
            equivalent = float(equivalent_resistance(configuration[branch]))
            key = "front_per_stage_ohm" if branch == "front_network" else "tail_per_stage_ohm"
            if key in configuration and not math.isclose(float(configuration[key]), equivalent, rel_tol=1e-12, abs_tol=0.0):
                raise ValueError(f"{key} disagrees with {branch}")
            configuration[key] = equivalent
        for name in ("stages", "stage_charge_V", "front_per_stage_ohm", "tail_per_stage_ohm"):
            if name not in configuration:
                raise ValueError(f"Fixed prediction requires {name}")
        if configuration["stages"] not in request["stages"]:
            raise ValueError("Fixed configuration stages are outside the requested stage set")
        # derive() validates domain limits, topology, capacitance coverage, and
        # charge/energy before a model or reference evaluator sees this input.
        from .physics import derive

        derive(configuration, request["setup"], request["domain_id"])
        return request, configuration

    def _fixed_physics(self, request: Mapping[str, Any], configuration: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, np.ndarray] | None]:
        """Solve the frozen configuration and return metadata plus arrays.

        ML/L0 values are kept in their own record.  This second result is the
        detailed numerical Physics reference for the exact same input, and an
        unsupported solve is recorded explicitly instead of being hidden by a
        successful baseline prediction.
        """

        from .physics import simulate
        try:
            solved = simulate(
                dict(configuration),
                request["setup"],
                domain_id=request["domain_id"],
                target_crest_V=request["target_crest_V"],
                n_points=1600,
            )
            metadata = _json_copy(solved.metadata)
            metrics = metadata.get("metrics") if isinstance(metadata.get("metrics"), Mapping) else {}
            waveform_status = metadata.get("waveform_status", metrics.get("waveform_status"))
            numeric_status = metadata.get("numeric_status")
            fully_verified = (
                numeric_status == "VALID"
                and waveform_status == "VALID_CLEAN_FULL_IMPULSE"
            )
            status = "PHYSICS_VERIFIED" if fully_verified else "PHYSICS_UNSUPPORTED"
            metadata["application_status"] = status
            if not fully_verified:
                metadata["physics_error_code"] = "WAVEFORM_NOT_CLEAN_FULL_IMPULSE"
                metadata["physics_unsupported_reason"] = (
                    "Detailed Physics computed a waveform but it is not a clean full impulse: "
                    f"numeric_status={numeric_status!r}, waveform_status={waveform_status!r}"
                )
            arrays = {
                key: np.asarray(value, dtype=float)
                for key, value in solved.arrays.items()
                if key in {"time_s", "voltage_V", "generator_voltage_V", "front_current_A", "stored_energy_J", "dissipated_power_W"}
            }
            return metadata, arrays
        except Exception as exc:
            # PhysicsError is a declared, user-facing unsupported solve.  Do
            # not turn an unexpected programming or numerical failure into a
            # plausible-looking Physics fallback or verified record.
            from physics_engine.network import PhysicsError

            if not isinstance(exc, PhysicsError):
                raise
            return {
                "schema_version": "physics_networks_v3",
                "application_status": "PHYSICS_UNSUPPORTED",
                "error": str(exc),
                "physics_error_code": exc.code,
                "eligible_for_hardware_recommendation": False,
                "numerical_pass_is_not_IEC_certification": True,
            }, None

    def predict_fixed(self, raw: Mapping[str, Any]) -> dict[str, Any]:
        request, configuration = self._fixed_inputs(raw)
        physics_metadata, physics_arrays = self._fixed_physics(request, configuration)
        feature_fallback_reason = None
        try:
            features = feature_matrix(
                [configuration["stages"]],
                [configuration["front_per_stage_ohm"]],
                [configuration["tail_per_stage_ohm"]],
                request["setup"],
                request["domain_id"],
                request["impulse_type"],
                request["topology_id"],
            )
        except ValueError as exc:
            # Detailed Physics models an optional leakage branch, while the
            # L0 feature contract intentionally refuses to ignore it.  Keep
            # the Physics result and record an explicit non-ML fallback.  A
            # different feature error remains a hard input/program failure.
            load_resistance = request["setup"].get("load_resistance_ohm") if isinstance(request["setup"], Mapping) else None
            if load_resistance is None or str(exc) != _LOAD_FEATURE_UNSUPPORTED:
                raise
            feature_fallback_reason = str(exc)
            features = None
        model = None
        card = None
        fallback_reason = feature_fallback_reason
        route = f"{request['domain_id']}:{request['impulse_type']}:{request['topology_id']}"
        if feature_fallback_reason is not None:
            metrics = physics_metadata.get("metrics", {}) if isinstance(physics_metadata, Mapping) else {}
            front_key = "T1_s" if request["impulse_type"] == "LI" else "Tp_s"
            prediction = {
                "status": "PHYSICS_FALLBACK",
                "source": "DETAILED_PHYSICS",
                "model_id": None,
                "gain": None if physics_metadata.get("voltage_gain") is None else float(physics_metadata["voltage_gain"]),
                "front_us": None if metrics.get(front_key) is None else float(metrics[front_key]) * 1e6,
                "tail_us": None if metrics.get("T2_s") is None else float(metrics["T2_s"]) * 1e6,
                "crest_V": None if metrics.get("crest_magnitude_V") is None else float(metrics["crest_magnitude_V"]),
                "ml_ood": None,
                "ml_unsupported_reason": feature_fallback_reason,
                "prediction_is_not_an_ml_claim": True,
            }
            model_info = {
                "status": "UNAVAILABLE",
                "fallback_reason": fallback_reason,
                "ml_unsupported_reason": feature_fallback_reason,
                "fallback_source": "DETAILED_PHYSICS",
                "prediction_is_not_an_ml_claim": True,
                "route": route,
            }
        else:
            try:
                model, card = load_predictor(request, registry=self.registry, selection=self.selection)
            except (OSError, ValueError, KeyError, RuntimeError) as exc:
                fallback_reason = str(exc)
            if model is None:
                values = baseline(features)[0]
                prediction = {
                    "status": "PHYSICS_FALLBACK",
                    "source": "L0_PHYSICS_BASELINE",
                    "model_id": None,
                    "gain": float(values[0]),
                    "front_us": float(values[1]),
                    "tail_us": float(values[2]),
                    "crest_V": float(values[0] * configuration["stages"] * configuration["stage_charge_V"]),
                    "ml_ood": None,
                }
                model_info = {
                    "status": "UNAVAILABLE",
                    "fallback_reason": fallback_reason,
                    "prediction_is_not_an_ml_claim": True,
                    "route": route,
                }
            else:
                predicted = np.asarray(model.predict(features), dtype=float)[0]
                if not np.isfinite(predicted).all() or (predicted <= 0).any():
                    raise ValueError("Loaded model returned a non-positive or non-finite prediction")
                ood = bool(np.asarray(model.ood(features), dtype=bool).reshape(-1)[0])
                prediction = {
                    "status": "ML_PREDICTION",
                    "source": "VERSIONED_ROUTE_MODEL",
                    "model_id": card.get("model_id"),
                    "gain": float(predicted[0]),
                    "front_us": float(predicted[1]),
                    "tail_us": float(predicted[2]),
                    "crest_V": float(predicted[0] * configuration["stages"] * configuration["stage_charge_V"]),
                    "ml_ood": ood,
                }
                model_info = {
                    "status": "LOADED",
                    "model_id": card.get("model_id"),
                    "card_sha256": _sha256_bytes(json.dumps(card, sort_keys=True, allow_nan=False).encode()),
                    "route": route,
                }
        prediction_id = "pred_v3_" + uuid.uuid4().hex[:20]
        source_fingerprint = self._source_fingerprint()
        record = {
            "schema_version": PREDICTION_SCHEMA,
            "prediction_id": prediction_id,
            "created_at": _now(),
            "input": {"request": request, "configuration": configuration},
            "input_sha256": _digest({"request": request, "configuration": configuration}),
            "prediction": prediction,
            "model": model_info,
            "physics": physics_metadata,
            "physics_waveform": None,
            "source_fingerprint": source_fingerprint,
            "reference": None,
            "reference_policy": "A_LATER_REFERENCE_CAN_ONLY_CREATE_A_COMPARISON_RECORD; IT_NEVER_MUTATES_THIS_PREDICTION",
        }
        folder = self.predictions / prediction_id
        folder.mkdir(parents=True, exist_ok=False)
        if physics_arrays is not None:
            waveform_path = folder / "physics_waveform.npz"
            temporary = folder / f"physics_waveform.{uuid.uuid4().hex}.tmp.npz"
            np.savez_compressed(temporary, **physics_arrays)
            os.replace(temporary, waveform_path)
            record["physics_waveform"] = {
                "path": "physics_waveform.npz",
                "sha256": _sha256_bytes(waveform_path.read_bytes()),
                "sample_count": int(len(physics_arrays["time_s"])),
                "arrays": sorted(physics_arrays),
            }
        _write_json_atomic(folder / "prediction.json", record)
        prediction_hash = _sha256_bytes((folder / "prediction.json").read_bytes())
        (folder / "prediction.sha256").write_text(prediction_hash + "\n", encoding="ascii")
        return record

    predict = predict_fixed

    def _source_fingerprint(self) -> dict[str, Any]:
        from .registry import source_fingerprint

        return source_fingerprint()

    def _prediction_path(self, prediction_id: str) -> Path:
        prediction_id = _safe_id(prediction_id, prefix="pred_v3_")
        path = (self.predictions / prediction_id / "prediction.json").resolve()
        if not path.is_relative_to(self.predictions.resolve()) or not path.is_file():
            raise FileNotFoundError("v3 prediction not found")
        digest_path = path.with_name("prediction.sha256")
        if not digest_path.is_file():
            raise ValueError("v3 prediction integrity record is missing")
        expected = digest_path.read_text(encoding="ascii").strip()
        if not re.fullmatch(r"[a-f0-9]{64}", expected) or _sha256_bytes(path.read_bytes()) != expected:
            raise ValueError("v3 prediction integrity mismatch")
        return path

    def get_prediction(self, prediction_id: str) -> dict[str, Any]:
        return _read_json(self._prediction_path(prediction_id))

    def prediction_waveform(self, prediction_id: str) -> dict[str, Any]:
        record = self.get_prediction(prediction_id)
        reference = record.get("physics_waveform")
        if not isinstance(reference, Mapping) or reference.get("path") != "physics_waveform.npz":
            raise ValueError("v3 prediction has no verified Physics waveform")
        root = self._prediction_path(prediction_id).parent.resolve()
        path = (root / reference["path"]).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise FileNotFoundError("v3 prediction waveform not found")
        if _sha256_bytes(path.read_bytes()) != reference.get("sha256"):
            raise ValueError("v3 prediction waveform integrity mismatch")
        with np.load(path, allow_pickle=False) as archive:
            arrays = {name: archive[name].tolist() for name in archive.files}
        return {
            "schema_version": "network_prediction_waveform_v3",
            "prediction_id": prediction_id,
            "prediction_input_sha256": record["input_sha256"],
            "physics": record.get("physics"),
            "waveform_reference": reference,
            "arrays": arrays,
        }

    def _parse_reference_csv(self, raw_bytes: bytes, metadata: Mapping[str, Any], request: Mapping[str, Any]) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
        if len(raw_bytes) == 0 or len(raw_bytes) > 10_000_000:
            raise ValueError("Reference CSV must be between 1 byte and 10 MB")
        try:
            text = raw_bytes.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError("Reference CSV must be UTF-8") from exc
        reader = csv.DictReader(io.StringIO(text, newline=""))
        if not reader.fieldnames or len(reader.fieldnames) < 2:
            raise ValueError("Reference CSV requires named time and voltage columns")
        measurement = metadata.get("measurement", {}) if isinstance(metadata, Mapping) else {}
        if not isinstance(measurement, Mapping):
            raise ValueError("metadata.measurement must be an object")
        time_name = measurement.get("time_column", reader.fieldnames[0])
        voltage_name = measurement.get("voltage_column", reader.fieldnames[1])
        if time_name not in reader.fieldnames or voltage_name not in reader.fieldnames:
            raise ValueError("Reference CSV columns do not match metadata")
        time_scale = {"s": 1.0, "ms": 1e-3, "us": 1e-6, "µs": 1e-6, "ns": 1e-9}.get(str(measurement.get("time_unit", "s")))
        voltage_scale = {"V": 1.0, "kV": 1e3, "mV": 1e-3}.get(str(measurement.get("voltage_unit", "V")))
        if time_scale is None or voltage_scale is None:
            raise ValueError("Unsupported reference CSV units")
        dut_scale = _finite_number(measurement.get("voltage_scale_to_DUT", 1.0), "voltage_scale_to_DUT", positive=True)
        times: list[float] = []
        voltages: list[float] = []
        for row in reader:
            try:
                times.append(float(row[time_name]) * time_scale)
                voltages.append(float(row[voltage_name]) * voltage_scale * dut_scale)
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError("Reference CSV contains a non-numeric time or voltage") from exc
        t = np.asarray(times, dtype=float)
        v = np.asarray(voltages, dtype=float)
        if len(t) < 8 or not np.isfinite(t).all() or not np.isfinite(v).all() or np.any(np.diff(t) <= 0):
            raise ValueError("Reference CSV requires finite, strictly increasing time and at least 8 samples")
        details = {
            "time_unit": measurement.get("time_unit", "s"),
            "voltage_unit": measurement.get("voltage_unit", "V"),
            "voltage_scale_to_DUT": dut_scale,
            "baseline_V": _finite_number(measurement.get("baseline_V", 0.0), "baseline_V"),
            "beginning_s": measurement.get("beginning_s", 0.0),
            "source_organization": metadata.get("source_organization"),
        }
        return t, v, details

    @staticmethod
    def _reference_metric_values(metrics: Mapping[str, Any], request: Mapping[str, Any]) -> dict[str, float | None]:
        if not isinstance(metrics, Mapping):
            raise ValueError("Reference metrics must be an object")
        front_key = "T1_s" if request["impulse_type"] == "LI" else "Tp_s"
        values = {
            "crest_magnitude_V": metrics.get("crest_magnitude_V", metrics.get("crest_V")),
            front_key: metrics.get(front_key, metrics.get("front_s", metrics.get("peak_time_s"))),
            "T2_s": metrics.get("T2_s", metrics.get("tail_s")),
        }
        if all(value is None for value in values.values()):
            raise ValueError("Reference metrics must include crest, front/peak, or tail")
        normalized: dict[str, float | None] = {}
        for key, value in values.items():
            if value is None or value == "":
                normalized[key] = None
            else:
                normalized[key] = _finite_number(value, key, positive=True)
        return normalized

    @staticmethod
    def _reference_expected(original_prediction: Mapping[str, Any]) -> tuple[dict[str, float | None], str, dict[str, Any]]:
        request = original_prediction["input"]["request"]
        predicted = original_prediction["prediction"]
        front_key = "T1_s" if request["impulse_type"] == "LI" else "Tp_s"
        model_values = {
            "crest_magnitude_V": predicted.get("crest_V"),
            front_key: None if predicted.get("front_us") is None else float(predicted["front_us"]) * 1e-6,
            "T2_s": None if predicted.get("tail_us") is None else float(predicted["tail_us"]) * 1e-6,
        }
        physics = original_prediction.get("physics")
        physics_metrics = physics.get("metrics") if isinstance(physics, Mapping) else None
        if isinstance(physics_metrics, Mapping) and physics.get("application_status") == "PHYSICS_VERIFIED":
            values = {key: physics_metrics.get(key) for key in model_values}
            if all(value is not None and math.isfinite(float(value)) for value in values.values()):
                return values, "PHYSICS_VERIFIED", model_values
        return model_values, "ML_PREDICTION" if predicted.get("status") == "ML_PREDICTION" else "L0_PHYSICS_BASELINE", model_values

    @staticmethod
    def _comparison_errors(
        measured: Mapping[str, Any],
        expected: Mapping[str, Any],
        request: Mapping[str, Any],
    ) -> dict[str, dict[str, Any]]:
        from physics_engine.evaluator import LIMITS

        mode_limits = LIMITS[request["impulse_type"]]
        front_key = "T1_s" if request["impulse_type"] == "LI" else "Tp_s"
        specifications = {
            "crest_magnitude_V": (float(request["target_crest_V"]), .03 * float(request["target_crest_V"])),
            front_key: (float(mode_limits["nominal_s"][0]), (mode_limits["front_s"][1] - mode_limits["front_s"][0]) / 2),
            "T2_s": (float(mode_limits["nominal_s"][1]), (mode_limits["tail_s"][1] - mode_limits["tail_s"][0]) / 2),
        }
        errors: dict[str, dict[str, Any]] = {}
        for key, (nominal, half_width) in specifications.items():
            reference = measured.get(key)
            prediction = expected.get(key)
            if reference is None or prediction is None:
                errors[key] = {
                    "reference_value": reference,
                    "predicted_value": prediction,
                    "signed_error": None,
                    "absolute_error": None,
                    "relative_error": None,
                    "relative_error_basis": "reference_value",
                    "nominal_value": nominal,
                    "tolerance_half_width": half_width,
                    "tolerance_normalized_error": None,
                }
                continue
            reference_value = float(reference)
            prediction_value = float(prediction)
            signed = prediction_value - reference_value
            errors[key] = {
                "reference_value": reference_value,
                "predicted_value": prediction_value,
                "signed_error": signed,
                "absolute_error": abs(signed),
                "relative_error": signed / reference_value if reference_value else None,
                "relative_error_basis": "reference_value",
                "nominal_value": nominal,
                "tolerance_half_width": half_width,
                "tolerance_normalized_error": abs(signed) / half_width if half_width else None,
            }
        return errors

    def _write_reference_comparison(
        self,
        prediction_id: str,
        original_prediction: Mapping[str, Any],
        measured: Mapping[str, Any],
        metadata: Mapping[str, Any],
        *,
        metadata_bytes: bytes | None,
        raw_bytes: bytes | None = None,
        sample_count: int | None = None,
        evaluation: Mapping[str, Any] | None = None,
        source_kind: str,
    ) -> dict[str, Any]:
        if metadata_bytes is not None and not isinstance(metadata_bytes, bytes):
            raise ValueError("metadata_bytes must be bytes")
        expected, comparison_source, model_values = self._reference_expected(original_prediction)
        errors = self._comparison_errors(measured, expected, original_prediction["input"]["request"])
        comparison_id = "ref_v3_" + uuid.uuid4().hex[:20]
        folder = self.predictions / _safe_id(prediction_id, prefix="pred_v3_") / comparison_id
        folder.mkdir(parents=True, exist_ok=False)
        metadata_raw = metadata_bytes if metadata_bytes is not None else json.dumps(metadata, indent=2, sort_keys=True, allow_nan=False).encode("utf-8")
        (folder / "source_metadata.json").write_bytes(metadata_raw)
        if raw_bytes is not None:
            (folder / "raw_export.csv").write_bytes(raw_bytes)
        else:
            (folder / "reference_metrics.json").write_text(json.dumps(dict(measured), indent=2, sort_keys=True, allow_nan=False), encoding="utf-8")
        prediction_digest = self._prediction_path(prediction_id).with_name("prediction.sha256").read_text(encoding="ascii").strip()
        comparison = {
            "schema_version": REFERENCE_SCHEMA,
            "comparison_id": comparison_id,
            "prediction_id": prediction_id,
            "created_at": _now(),
            "prediction_input_sha256": original_prediction["input_sha256"],
            "prediction_record_sha256": prediction_digest,
            "raw_sha256": None if raw_bytes is None else _sha256_bytes(raw_bytes),
            "metadata_sha256": _sha256_bytes(metadata_raw),
            "raw_sample_count": sample_count,
            "source_kind": source_kind,
            "comparison_source": comparison_source,
            "reference_values": dict(measured),
            "predicted_values": expected,
            "model_predicted_values": model_values,
            "reference_evaluation": None if evaluation is None else dict(evaluation),
            "comparison": errors,
            "qualification": {
                "status": "NUMERICAL_SCALAR_REFERENCE_ONLY" if raw_bytes is None else "NUMERICAL_REFERENCE_COMPARISON_ONLY",
                "standards_certified": False,
                "limitations": [
                    "Reference values are compared against a frozen v3 record; no retraining or mutation is performed.",
                    "Raw acquisition bytes are preserved only for CSV imports; scalar values retain caller metadata and provenance.",
                    "This numerical comparison does not establish CPRI, IEC, laboratory, or hardware qualification.",
                ],
            },
        }
        _write_json_atomic(folder / "comparison.json", comparison)
        comparison_hash = _sha256_bytes((folder / "comparison.json").read_bytes())
        (folder / "comparison.sha256").write_text(comparison_hash + "\n", encoding="ascii")
        return comparison

    def attach_reference(
        self,
        prediction_id: str,
        raw_csv: bytes | str,
        metadata: Mapping[str, Any],
        *,
        metadata_bytes: bytes | None = None,
    ) -> dict[str, Any]:
        if not isinstance(metadata, Mapping):
            raise ValueError("Reference metadata must be an object")
        original_prediction = self.get_prediction(prediction_id)
        if isinstance(raw_csv, str):
            raw_bytes = raw_csv.encode("utf-8")
        elif isinstance(raw_csv, bytes):
            raw_bytes = bytes(raw_csv)
        else:
            raise ValueError("Reference CSV must be text or bytes")
        request = original_prediction["input"]["request"]
        t, v, details = self._parse_reference_csv(raw_bytes, metadata, request)
        from physics_engine.evaluator import evaluate

        beginning = details.get("beginning_s", 0.0)
        if beginning is not None:
            beginning = _finite_number(beginning, "beginning_s")
        evaluation = evaluate(
            t,
            v,
            request["impulse_type"],
            request["polarity"],
            beginning_s=beginning,
            baseline_V=details["baseline_V"],
            target_crest_V=request["target_crest_V"],
            source_kind="measured_import",
            curve_id="v3_reference_import",
        )
        front_key = "T1_s" if request["impulse_type"] == "LI" else "Tp_s"
        measured = {
            "crest_magnitude_V": evaluation.get("crest_magnitude_V"),
            front_key: evaluation.get(front_key),
            "T2_s": evaluation.get("T2_s"),
        }
        return self._write_reference_comparison(
            prediction_id,
            original_prediction,
            measured,
            metadata,
            metadata_bytes=metadata_bytes,
            raw_bytes=raw_bytes,
            sample_count=int(len(t)),
            evaluation=evaluation,
            source_kind="MEASURED_CSV_IMPORT",
        )

    def attach_reference_metrics(
        self,
        prediction_id: str,
        metrics: Mapping[str, Any],
        metadata: Mapping[str, Any],
        *,
        metadata_bytes: bytes | None = None,
    ) -> dict[str, Any]:
        if not isinstance(metadata, Mapping):
            raise ValueError("Reference metadata must be an object")
        original_prediction = self.get_prediction(prediction_id)
        measured = self._reference_metric_values(metrics, original_prediction["input"]["request"])
        return self._write_reference_comparison(
            prediction_id,
            original_prediction,
            measured,
            metadata,
            metadata_bytes=metadata_bytes,
            source_kind="SCALAR_REFERENCE_VALUES",
        )

    reference = attach_reference
    reference_metrics = attach_reference_metrics

    def get_reference(self, prediction_id: str, comparison_id: str) -> dict[str, Any]:
        prediction_id = _safe_id(prediction_id, prefix="pred_v3_")
        # Reference records are meaningful only while the frozen prediction
        # remains intact; verify its sidecar hash before exposing a comparison.
        self.get_prediction(prediction_id)
        if not isinstance(comparison_id, str) or not re.fullmatch(r"ref_v3_[a-f0-9]{20}", comparison_id):
            raise ValueError("Invalid reference comparison identifier")
        path = (self.predictions / prediction_id / comparison_id / "comparison.json").resolve()
        if not path.is_relative_to(self.predictions.resolve()) or not path.is_file():
            raise FileNotFoundError("v3 reference comparison not found")
        digest_path = path.with_name("comparison.sha256")
        if not digest_path.is_file():
            raise ValueError("v3 reference comparison integrity record is missing")
        expected = digest_path.read_text(encoding="ascii").strip()
        if not re.fullmatch(r"[a-f0-9]{64}", expected) or _sha256_bytes(path.read_bytes()) != expected:
            raise ValueError("v3 reference comparison integrity mismatch")
        return _read_json(path)


# Alias used by the server and by callers migrating from the legacy service.
Application = V3Application


__all__ = ["Application", "V3Application", "SCHEMA_VERSION", "PREDICTION_SCHEMA", "REFERENCE_SCHEMA"]
