"""Read-only detailed Physics comparison of the <=2 and <=3 module catalogs.

The preliminary mode is deliberately small.  It replays matching frozen
requests, reuses a completed <=2 Physics result when one exists, and samples
the <=3 response catalog with deterministic, inverse-guided strata plus local
neighbours of the frozen <=2 anchor.  It never loads a model or trains one.
The existing Physics-only candidate verifier is used for legal charge scaling
and the canonical score.  Full waveform files are written only for the
selected comparison pair and the fixed-N/charge control.

This is an evidence utility rather than a training or serving path.  The
reduced graph remains a provisional synthetic topology, as reported by the
v3 Physics API.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping

import numpy as np
from scipy.integrate import simpson
from scipy.optimize import brentq

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
TOOLS_ROOT = Path(__file__).resolve().parent
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from powernext_v3 import physics  # noqa: E402
from powernext_v3.catalog import Catalog  # noqa: E402
from powernext_v3.profiles import get_profile  # noqa: E402
from physics_engine.network import PhysicsError  # noqa: E402


STAGES = (6, 9, 12)
N_POINTS = 1600
SEED = 20261010
SAMPLE_SEEDS = (0, 1, 2)
DEFAULT_THREE_PER_SEED = 32


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _digest(value: Any) -> str:
    raw = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    return hashlib.sha256(raw).hexdigest()


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        value = float(value)
        return value if math.isfinite(value) else None
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, np.ndarray):
        return [_jsonable(v) for v in value.tolist()]
    if isinstance(value, Path):
        return str(value)
    return value


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_jsonable(value), indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def _short_id(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in value)


_SETUP_DEFAULTS = {
    "load_resistance_ohm": None,
    "auxiliary_assumption": "UNCONFIRMED_AUXILIARY_BRANCHES_OMITTED",
}


def _normalized_setup(setup: Mapping[str, Any] | None) -> dict[str, Any]:
    value = dict(setup or {})
    for key, default in _SETUP_DEFAULTS.items():
        value.setdefault(key, default)
    return value


def _same_setup(left: Mapping[str, Any], right: Mapping[str, Any]) -> bool:
    """Compare the complete normalized setup identity, including setup_id."""
    left_value = _normalized_setup(left)
    right_value = _normalized_setup(right)
    if set(left_value) != set(right_value):
        return False
    for key in sorted(left_value):
        a = left_value[key]
        b = right_value[key]
        if isinstance(a, (int, float)) and isinstance(b, (int, float)):
            if not math.isclose(float(a), float(b), rel_tol=0.0, abs_tol=1e-18):
                return False
        elif a != b:
            return False
    return True


@dataclass(frozen=True)
class Case:
    case_id: str
    request_id: str
    domain_id: str
    mode: str
    topology_id: str
    target_crest_V: float
    setup: dict[str, Any]
    source_path: str
    source_sha256: str
    source_kind: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "request_id": self.request_id,
            "domain_id": self.domain_id,
            "mode": self.mode,
            "topology_id": self.topology_id,
            "target_crest_V": self.target_crest_V,
            "setup": self.setup,
            "source_path": self.source_path,
            "source_sha256": self.source_sha256,
            "source_kind": self.source_kind,
            "stages": list(STAGES),
        }


def _load_cases() -> list[Case]:
    request_path = ROOT / "evidence" / "phase_b" / "search_benchmark" / "requests.json"
    requests = json.loads(request_path.read_text(encoding="utf-8"))
    by_id = {row["request_id"]: row for row in requests}

    selected_ids = (
        "FROZEN_test_cpri_0p5uf_LI_GSHUNT_v0_0",
        "FROZEN_test_cpri_0p5uf_LI_GSHUNT_v0_1",
        "FROZEN_test_cpri_0p5uf_LI_OSHUNT_v0_0",
        "FROZEN_test_cpri_0p5uf_SI_GSHUNT_v0_0",
        "FROZEN_test_cpri_0p5uf_SI_OSHUNT_v0_0",
    )
    entries: list[tuple[dict[str, Any], Path, str]] = [(by_id[row], request_path, "FROZEN_BENCHMARK_REQUEST") for row in selected_ids]

    cases: list[Case] = []
    for row, source, kind in entries:
        mode = row.get("impulse_type", row.get("mode"))
        domain = row.get("domain_id", "cpri_0p5uf")
        request_id = str(row["request_id"])
        case_id = _short_id(f"{domain}_{mode}_{row['topology_id']}_{request_id}")
        setup = dict(row["setup"])
        # The v3 Setup dataclass supplies these defaults; explicit fields make
        # the frozen replay record unambiguous without changing the request.
        setup.setdefault("load_resistance_ohm", None)
        setup.setdefault("auxiliary_assumption", "UNCONFIRMED_AUXILIARY_BRANCHES_OMITTED")
        setup.setdefault("setup_id", request_id)
        cases.append(
            Case(
                case_id=case_id,
                request_id=request_id,
                domain_id=domain,
                mode=mode,
                topology_id=str(row["topology_id"]),
                target_crest_V=float(row["target_crest_V"]),
                setup=setup,
                source_path=str(source.relative_to(ROOT)).replace("\\", "/"),
                source_sha256=_sha256(source),
                source_kind=kind,
            )
        )
    return cases


def _charge_for(case: Case, stages: int) -> float:
    profile = get_profile(case.domain_id)
    return float(min(profile.stage_charge_max_V, case.target_crest_V / float(stages)))


def _nominals(mode: str) -> tuple[float, float]:
    return (1.2, 50.0) if mode == "LI" else (250.0, 2500.0)


def _ideal_resistances(case: Case, stages: int) -> tuple[float, float]:
    front_nom_us, tail_nom_us = _nominals(case.mode)
    profile = get_profile(case.domain_id)
    cl = sum(float(case.setup.get(key, 0.0)) for key in ("dut_capacitance_F", "divider_capacitance_F", "stray_capacitance_F"))
    if case.setup.get("basic_coverage_assumption") == "ADDITIONAL_DISJOINT":
        cl += profile.basic_load_capacitance_F
    cg = profile.stage_capacitance_F / stages
    front = max(1e-6, front_nom_us * 1e-6 / (1.67 * cl * stages) - float(case.setup.get("loop_resistance_ohm", 0.0)) / stages)
    tail = max(1e-6, tail_nom_us * 1e-6 / (0.693 * (cg + cl) * stages))
    return front, tail


def _nearest_indices(cat: Catalog, target: float, *, module_count: int | None = None, limit: int = 6) -> list[int]:
    choices: list[tuple[float, int]] = []
    for index, value in enumerate(cat.exact_values):
        if module_count is not None and not any(recipe.module_count == module_count for recipe in cat.groups[value]):
            continue
        choices.append((abs(math.log(max(float(value), 1e-30) / max(target, 1e-30))), index))
    choices.sort(key=lambda item: (item[0], item[1]))
    return [index for _, index in choices[:limit]]


def _sample_three_ids(case: Case, cat: Catalog, per_seed: int, *, anchor_config: Mapping[str, Any] | None = None) -> dict[int, list[int]]:
    """Return deterministic <=3 IDs with stage/module/resistance coverage."""
    result: dict[int, list[int]] = {}
    module_pairs = tuple((front_modules, tail_modules) for front_modules in (1, 2, 3) for tail_modules in (1, 2, 3))
    for seed_offset in SAMPLE_SEEDS:
        case_seed = int(hashlib.sha256(case.case_id.encode("utf-8")).hexdigest()[:12], 16) % 100000
        rng = np.random.default_rng(SEED + 7919 * (seed_offset + 1) + case_seed)
        ids: list[int] = []
        seen: set[int] = set()

        def add(index: int) -> None:
            if index not in seen:
                seen.add(index)
                ids.append(int(index))

        # Reserve one exact-three-module candidate for every declared stage so
        # fixed-N crossover coverage survives the small per-seed budget.
        for stage_index, stages in enumerate(STAGES):
            ideal_front, ideal_tail = _ideal_resistances(case, stages)
            fs = _nearest_indices(cat, ideal_front, module_count=3, limit=1)
            ts = _nearest_indices(cat, ideal_tail, module_count=3, limit=1)
            if fs and ts:
                add(cat.encode(stage_index, fs[0], ts[0]))

        # Spread the nine front/tail module-count pairs over the three seeds
        # and three stages.  Across seeds this visits every (1,1) ... (3,3)
        # pair once, while each seed still has one candidate at every stage.
        for stage_index, stages in enumerate(STAGES):
            pair_index = seed_offset * len(STAGES) + stage_index
            front_modules, tail_modules = module_pairs[pair_index]
            ideal_front, ideal_tail = _ideal_resistances(case, stages)
            fs = _nearest_indices(cat, ideal_front, module_count=front_modules, limit=3)
            ts = _nearest_indices(cat, ideal_tail, module_count=tail_modules, limit=3)
            if fs and ts:
                fi = fs[seed_offset % len(fs)]
                ti = ts[(seed_offset + stage_index) % len(ts)]
                add(cat.encode(stage_index, fi, ti))

        # Keep a small local neighbourhood around the matching frozen <=2
        # anchor.  This is an input design rule, not a result-driven filter:
        # the anchor is selected before any <=3 waveform is simulated, and a
        # deterministic rotation gives each seed a different slice of the
        # same physical three-module response neighbourhood.
        if anchor_config is not None:
            anchor_stage = int(anchor_config.get("stages", 9))
            if anchor_stage in STAGES:
                anchor_stage_index = STAGES.index(anchor_stage)
                anchor_front = float(anchor_config.get("front_per_stage_ohm", 30.0))
                anchor_tail = float(anchor_config.get("tail_per_stage_ohm", 180.0))
                local_front = _nearest_indices(cat, anchor_front, module_count=3, limit=5)
                local_tail = _nearest_indices(cat, anchor_tail, module_count=3, limit=5)
                local_ids = [cat.encode(anchor_stage_index, fi, ti) for fi in local_front for ti in local_tail]
                if local_ids:
                    offset = (seed_offset * 7) % len(local_ids)
                    for local_pos in range(2):
                        add(local_ids[(offset + local_pos) % len(local_ids)])
        # Add a reproducible broad tail over the full <=3 response catalog.
        while len(ids) < per_seed:
            add(int(rng.integers(0, cat.count)))
        result[seed_offset] = ids[:per_seed]
    return result


def _config(case: Case, stages: int, front: float, tail: float, charge: float, *, front_network: Any = None, tail_network: Any = None) -> dict[str, Any]:
    value = {
        "impulse_type": case.mode,
        "stages": int(stages),
        "stage_charge_V": float(charge),
        "front_per_stage_ohm": float(front),
        "tail_per_stage_ohm": float(tail),
        "topology_id": case.topology_id,
        "polarity": 1,
    }
    if front_network is not None:
        value["front_network"] = front_network
    if tail_network is not None:
        value["tail_network"] = tail_network
    return value


def _metrics(result: Any, case: Case, *, scope: str, candidate_index: int | None, provenance: str, elapsed_s: float) -> dict[str, Any]:
    metadata = result.metadata
    metrics = metadata.get("metrics", {})
    front_key = "T1_s" if case.mode == "LI" else "Tp_s"
    front = metrics.get(front_key)
    tail = metrics.get("T2_s")
    crest = metrics.get("crest_magnitude_V", metrics.get("raw_crest_magnitude_V"))
    numeric_status = metadata.get("numeric_status")
    waveform_status = metrics.get("waveform_status")
    compliance_status = metrics.get("compliance_status")
    eligible = bool(numeric_status == "VALID" and waveform_status == "VALID_CLEAN_FULL_IMPULSE" and compliance_status == "PASS")
    front_us = None if front is None else float(front) * 1e6
    tail_us = None if tail is None else float(tail) * 1e6
    crest_f = None if crest is None else float(crest)
    nominal_front, nominal_tail = _nominals(case.mode)
    if crest_f is not None and front_us is not None and tail_us is not None:
        objective = float(
            ((crest_f - case.target_crest_V) / (0.03 * case.target_crest_V)) ** 2
            + ((front_us - nominal_front) / (0.36 if case.mode == "LI" else 50.0)) ** 2
            + ((tail_us - nominal_tail) / (10.0 if case.mode == "LI" else 1500.0)) ** 2
        )
    else:
        objective = float("inf")
    return {
        "scope": scope,
        "candidate_index": candidate_index,
        "provenance": provenance,
        "status": "PASS" if eligible else "FAIL",
        "numeric_status": numeric_status,
        "waveform_status": waveform_status,
        "compliance_status": compliance_status,
        "reason_codes": list(metrics.get("reasons", [])),
        "crest_V": crest_f,
        "gain": metadata.get("voltage_gain"),
        "front_us": front_us,
        "tail_us": tail_us,
        "target_crest_V": case.target_crest_V,
        "objective_J": objective,
        "energy_balance_relative_error": metadata.get("energy_balance_relative_error"),
        "simulation_seconds": float(elapsed_s),
        "solver": metadata.get("solver"),
        "hardware_status": metadata.get("hardware_status"),
        "eligible_for_hardware_recommendation": metadata.get("eligible_for_hardware_recommendation"),
    }


def _simulate(case: Case, configuration: Mapping[str, Any], *, scope: str, candidate_index: int | None, provenance: str, n_points: int) -> tuple[dict[str, Any], Any | None]:
    started = time.perf_counter()
    try:
        result = physics.simulate(
            dict(configuration),
            dict(case.setup),
            domain_id=case.domain_id,
            target_crest_V=case.target_crest_V,
            n_points=n_points,
            solver="modal",
        )
    except PhysicsError as exc:
        # PhysicsError is the declared unsupported/invalid boundary.  Other
        # exceptions intentionally escape so implementation defects are not
        # hidden as data failures.
        return {
            "scope": scope,
            "candidate_index": candidate_index,
            "provenance": provenance,
            "status": "UNSUPPORTED",
            "error": {"type": type(exc).__name__, "code": getattr(exc, "code", None), "message": str(exc)},
            "configuration": dict(configuration),
            "simulation_seconds": float(time.perf_counter() - started),
        }, None
    record = _metrics(result, case, scope=scope, candidate_index=candidate_index, provenance=provenance, elapsed_s=time.perf_counter() - started)
    record["configuration"] = dict(configuration)
    record["derived"] = dict(result.metadata.get("derived", {}))
    record["stored_energy_J"] = result.metadata.get("stored_energy_J")
    record["integrated_loss_J"] = result.metadata.get("integrated_loss_J")
    return record, result


def _verify_sampled_catalog_candidate(case: Case, index: int, cat3: Catalog, *, seed: int, n_points: int) -> tuple[dict[str, Any], Any | None]:
    """Use the existing deterministic Physics-only candidate verifier.

    ``verify_candidate`` performs one detailed solve at the legal charge cap,
    exact linear charge scaling to the requested crest, and the canonical
    parameter-score calculation.  It does not load ML artifacts or train.
    """
    from powernext_v3.optimizer import verify_candidate

    request = {
        "schema_version": "network_request_v3",
        "request_id": f"TWO_VS_THREE_{case.case_id}",
        "domain_id": case.domain_id,
        "impulse_type": case.mode,
        "topology_id": case.topology_id,
        "target_crest_V": case.target_crest_V,
        "setup": dict(case.setup),
        "stages": list(STAGES),
        "max_modules": 3,
        "search_mode": "complete",
        "priority": "complete_physics",
        "inventory": None,
        "polarity": 1,
    }
    started = time.perf_counter()
    p = get_profile(case.domain_id)
    row, result, _ = verify_candidate(index, cat3, request, p)
    elapsed = time.perf_counter() - started
    if result is None:
        return {
            "scope": "<=3",
            "candidate_index": int(index),
            "provenance": f"deterministic_sample_seed_{seed}",
            "status": "UNSUPPORTED",
            "error": {"type": "PhysicsVerificationUnavailable", "code": (row.get("reason_codes") or [None])[0], "message": row.get("verification_status")},
            "configuration": row.get("configuration"),
            "verification_status": row.get("verification_status"),
            "reason_codes": row.get("reason_codes", []),
            "simulation_seconds": float(elapsed),
        }, None
    record = _metrics(result, case, scope="<=3", candidate_index=index, provenance=f"deterministic_sample_seed_{seed}", elapsed_s=elapsed)
    record["configuration"] = dict(row.get("configuration") or result.metadata.get("inputs", {}).get("configuration", {}))
    record["canonical_score"] = row.get("score")
    if row.get("score") is not None:
        record["objective_J"] = float(row["score"]["J"])
    record["verification_status"] = row.get("verification_status")
    record["front_recipe"] = row.get("front_recipe")
    record["tail_recipe"] = row.get("tail_recipe")
    record["front_physical_alternatives"] = row.get("front_physical_alternatives")
    record["tail_physical_alternatives"] = row.get("tail_physical_alternatives")
    return record, result


def _candidate_record(cat: Catalog, index: int) -> tuple[int, float, float, dict[str, Any]]:
    stage_index, front_index, tail_index = divmod(index, cat.width * cat.width)[0], None, None
    stages, front, tail = cat.decode([index])
    stage = int(stages[0])
    # Decode indices without relying on floating-point resistance matching.
    remainder = int(index) % (cat.width * cat.width)
    fi, ti = divmod(remainder, cat.width)
    physical = cat.physical(int(index))
    return stage, float(front[0]), float(tail[0]), {
        "front_index": int(fi),
        "tail_index": int(ti),
        "physical_alternative_count": physical["physical_alternative_count"],
        "front_module_options": sorted({int(row["module_count"]) for row in physical["front_physical_alternatives"]}),
        "tail_module_options": sorted({int(row["module_count"]) for row in physical["tail_physical_alternatives"]}),
        "front_representative": physical["front_physical_alternatives"][0],
        "tail_representative": physical["tail_physical_alternatives"][0],
    }


def _benchmark_identity_guard(case: Case, cat2: Catalog, benchmark_dir: Path) -> dict[str, Any]:
    """Validate a completed <=2 benchmark before it can become the anchor.

    This guard is deliberately stricter than a request-id lookup.  A saved
    result is reusable only when its route, complete normalized setup, target,
    polarity, declared stages, and catalog identity all match this study's
    <=2 catalog.  The generated v3 evidence predates this post-run hardening;
    no Physics result is recomputed by the guard itself.
    """
    benchmark_dir = Path(benchmark_dir)
    if not benchmark_dir.is_absolute():
        benchmark_dir = ROOT / benchmark_dir
    benchmark_path = benchmark_dir / f"{case.request_id}.json"
    record: dict[str, Any] = {
        "path": str(benchmark_path.relative_to(ROOT)).replace("\\", "/"),
        "exists": benchmark_path.exists(),
        "checks": {},
    }
    if not benchmark_path.exists():
        record["passed"] = False
        record["failure_reasons"] = ["BENCHMARK_FILE_MISSING"]
        return record
    payload = json.loads(benchmark_path.read_text(encoding="utf-8"))
    request = payload.get("request") or {}
    complete = next((row for row in payload.get("policies", []) if row.get("policy") == "complete_physics"), None)
    search = (complete or {}).get("search") or {}
    configuration = (complete or {}).get("best_configuration") or {}
    expected_info = cat2.info()
    checks = {
        "request_id": request.get("request_id") == case.request_id,
        "domain_id": request.get("domain_id") == case.domain_id,
        "impulse_type": request.get("impulse_type") == case.mode,
        "topology_id": request.get("topology_id") == case.topology_id,
        "target_crest_V": isinstance(request.get("target_crest_V"), (int, float)) and math.isclose(float(request["target_crest_V"]), case.target_crest_V, rel_tol=0.0, abs_tol=1e-9),
        "setup_identity": _same_setup(request.get("setup") or {}, case.setup),
        "stages": request.get("stages") == list(STAGES) and search.get("stages") == list(STAGES),
        "request_max_modules_bound": request.get("max_modules") == 2,
        "request_polarity": request.get("polarity", 1) == 1,
        "complete_policy_status": (complete or {}).get("status") == "VERIFIED_COMPLIANT",
        "complete_strategy": search.get("requested_strategy") == "complete_physics" and search.get("effective_strategy") == "complete_physics",
        "catalog_sha256": search.get("catalog_sha256") == expected_info["catalog_sha256"],
        "catalog_max_modules_bound": search.get("max_modules_per_branch") == 2 and int(search.get("max_modules_per_branch", -1)) <= 2,
        "catalog_candidate_count": search.get("distinct_response_candidates") == expected_info["distinct_response_candidates"],
        "catalog_recipe_count": search.get("theoretical_recipe_configurations") == expected_info["theoretical_recipe_configurations"],
        "catalog_complete": search.get("catalog_complete") is True,
        "catalog_completion_reason": search.get("termination_reason") == "DECLARED_CATALOG_COMPLETED",
        "best_configuration_route": configuration.get("impulse_type") == case.mode and configuration.get("topology_id") == case.topology_id,
        "best_configuration_stage_bound": configuration.get("stages") in STAGES,
        "best_configuration_polarity": configuration.get("polarity", 1) == 1,
        "best_configuration_has_networks": isinstance(configuration.get("front_network"), Mapping) and isinstance(configuration.get("tail_network"), Mapping),
    }
    record["checks"] = checks
    record["passed"] = all(checks.values())
    record["failure_reasons"] = [name for name, passed in checks.items() if not passed]
    return record


def _baseline_configs(case: Case, cat2: Catalog, benchmark_dir: Path) -> list[tuple[str, dict[str, Any], str]]:
    result: list[tuple[str, dict[str, Any], str]] = []
    benchmark_path = benchmark_dir / f"{case.request_id}.json"
    guard = _benchmark_identity_guard(case, cat2, benchmark_dir)
    if guard["passed"]:
        payload = json.loads(benchmark_path.read_text(encoding="utf-8"))
        complete = next(row for row in payload.get("policies", []) if row.get("policy") == "complete_physics")
        # The complete catalog replay is the locked baseline.  Guided and
        # simple diagnostics remain useful rows, but can never replace it in
        # baseline selection when this guard passes.
        result.append(("best2_existing_complete", dict(complete["best_configuration"]), str(benchmark_path.relative_to(ROOT)).replace("\\", "/")))
    stage = 9
    ideal_front, ideal_tail = _ideal_resistances(case, stage)
    fi = _nearest_indices(cat2, ideal_front, limit=1)[0]
    ti = _nearest_indices(cat2, ideal_tail, limit=1)[0]
    idx = cat2.encode(STAGES.index(stage), fi, ti)
    guided_physical = cat2.physical(idx)
    result.append((
        "baseline2_guided",
        _config(
            case,
            stage,
            float(cat2.exact_values[fi]),
            float(cat2.exact_values[ti]),
            _charge_for(case, stage),
            front_network=guided_physical["front_physical_alternatives"][0]["tree"],
            tail_network=guided_physical["tail_physical_alternatives"][0]["tree"],
        ),
        "analytic_guided_catalog2",
    ))
    simple_tail = 180.0 if case.mode == "LI" else 5000.0
    simple_fi = _nearest_indices(cat2, 30.0, limit=1)[0]
    simple_ti = _nearest_indices(cat2, simple_tail, limit=1)[0]
    simple_idx = cat2.encode(STAGES.index(stage), simple_fi, simple_ti)
    simple_physical = cat2.physical(simple_idx)
    result.append((
        "baseline2_simple",
        _config(
            case,
            stage,
            float(cat2.exact_values[simple_fi]),
            float(cat2.exact_values[simple_ti]),
            _charge_for(case, stage),
            front_network=simple_physical["front_physical_alternatives"][0]["tree"],
            tail_network=simple_physical["tail_physical_alternatives"][0]["tree"],
        ),
        "simple_single_module_reference",
    ))
    # Keep exactly two baselines while preferring the completed exact replay.
    if len(result) > 2:
        result = result[:1] + [result[-1]] if result[0][0] == "best2_existing_complete" else result[:2]
    return result


def _record_module_scope(cat: Catalog, index: int, record: dict[str, Any]) -> dict[str, Any]:
    details = _candidate_record(cat, index)
    record.update(details)
    record["catalog_identity"] = cat.identity
    return record


def _reference_waveform(t: np.ndarray, mode: str, target: float) -> tuple[np.ndarray, dict[str, Any]]:
    """Return the shared nominal double-exponential plotting reference."""
    from impulse_target_reference import target_parameters, target_voltage

    parameters = target_parameters(mode)
    wave = target_voltage(np.asarray(t, dtype=float), mode, float(target))
    return wave, {
        **parameters,
        "status": "REFERENCE_GENERATED",
        "crest_normalization_V": float(target),
        "time_origin": "physical_firing_t0",
        "no_peak_shift_or_amplitude_renormalization": True,
    }

def _common_grid_metrics(two: Any, three: Any, case: Case, target_time_s: np.ndarray | None, target_wave: np.ndarray | None, target_meta: dict[str, Any] | None) -> dict[str, Any]:
    t2, v2 = np.asarray(two.arrays["time_s"], dtype=float), np.asarray(two.arrays["voltage_V"], dtype=float)
    t3, v3 = np.asarray(three.arrays["time_s"], dtype=float), np.asarray(three.arrays["voltage_V"], dtype=float)
    end = min(float(t2[-1]), float(t3[-1]))
    start = max(float(t2[0]), float(t3[0]), 0.0)
    n = min(len(t2), len(t3), N_POINTS)
    grid = np.linspace(start, end, n)
    y2 = np.interp(grid, t2, v2)
    y3 = np.interp(grid, t3, v3)
    diff = y3 - y2
    scale = float(case.target_crest_V)
    result = {
        "common_grid_points": int(n),
        "common_time_start_s": start,
        "common_time_end_s": end,
        "common_time_duration_s": end - start,
        "crest_normalization_V": scale,
        "actual_2v3_Linf_V": float(np.max(np.abs(diff))),
        "actual_2v3_MAE_V": float(np.mean(np.abs(diff))),
        "actual_2v3_RMSE_V": float(np.sqrt(np.mean(diff * diff))),
        "actual_2v3_time_integral_abs_Vs": float(simpson(np.abs(diff), x=grid)),
        "actual_2v3_L2_time_norm_sqrt_V2s": float(math.sqrt(simpson(diff * diff, x=grid))),
        "actual_2v3_Linf_normalized": float(np.max(np.abs(diff)) / scale),
        "actual_2v3_MAE_normalized": float(np.mean(np.abs(diff)) / scale),
        "actual_2v3_RMSE_normalized": float(np.sqrt(np.mean(diff * diff)) / scale),
        "actual_2v3_time_integral_abs_normalized_Vs_per_V": float(simpson(np.abs(diff), x=grid) / scale),
        "actual_2v3_L2_time_norm_normalized_sqrt_V2s_per_V": float(math.sqrt(simpson(diff * diff, x=grid)) / scale),
        "target_reference": target_meta,
    }
    if target_wave is not None and target_time_s is not None:
        target = np.interp(grid, target_time_s, target_wave)
        for label, actual in (("2", y2), ("3", y3)):
            residual = actual - target
            result[f"actual_{label}_vs_target_RMSE_V"] = float(np.sqrt(np.mean(residual * residual)))
            result[f"actual_{label}_vs_target_Linf_V"] = float(np.max(np.abs(residual)))
            result[f"actual_{label}_vs_target_RMSE_normalized"] = float(np.sqrt(np.mean(residual * residual)) / scale)
            result[f"actual_{label}_vs_target_Linf_normalized"] = float(np.max(np.abs(residual)) / scale)
    return result


def _save_waveform(path: Path, result: Any, target_time_s: np.ndarray | None = None, target_wave: np.ndarray | None = None) -> None:
    arrays = {key: np.asarray(value) for key, value in result.arrays.items()}
    if target_time_s is not None:
        arrays["target_reference_time_s"] = np.asarray(target_time_s)
    if target_wave is not None:
        arrays["target_reference_voltage_V"] = np.asarray(target_wave)
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(path, **arrays)


def _plot_overlay(path: Path, case: Case, two: Any, three: Any, target_time_s: np.ndarray | None, target_wave: np.ndarray | None, control_three: Any | None = None) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, (ax, ax_zoom) = plt.subplots(2, 1, figsize=(10, 8.0), dpi=150, sharey=True)
    t2 = np.asarray(two.arrays["time_s"]) * 1e6
    t3 = np.asarray(three.arrays["time_s"]) * 1e6
    v2 = np.asarray(two.arrays["voltage_V"]) / 1e3
    v3 = np.asarray(three.arrays["voltage_V"]) / 1e3
    if control_three is not None:
        tc = np.asarray(control_three.arrays["time_s"]) * 1e6
        vc = np.asarray(control_three.arrays["voltage_V"]) / 1e3
    else:
        tc = vc = None
    if target_wave is not None and target_time_s is not None:
        tref = np.asarray(target_time_s) * 1e6
        vref = target_wave / 1e3
    else:
        tref = vref = None
    # The upper panel retains the complete simulated duration.  The lower
    # panel makes the front and first peak inspectable without shifting or
    # rescaling any curve; its limit is a fixed nominal-time window.
    for panel in (ax, ax_zoom):
        panel.plot(t2, v2, label="<=2 selected", linewidth=1.2)
        panel.plot(t3, v3, label="<=3 selected", linewidth=1.2)
        if tc is not None:
            panel.plot(tc, vc, label="<=3 post-selection replay N/q", linewidth=1.0, alpha=.75)
        if tref is not None:
            panel.plot(tref, vref, "k--", label="nominal double-exponential reference", linewidth=1.0)
        panel.set_ylabel("Output voltage (kV)")
        panel.grid(True, alpha=.25)
    ax.set_title(f"{case.case_id}: actual waveform crossover (full simulated duration)")
    front_nom_us, _ = _nominals(case.mode)
    zoom_end_us = 8.0 * front_nom_us if case.mode == "LI" else 6.0 * front_nom_us
    ax_zoom.set_title(f"Front and first peak (0 to {zoom_end_us:g} µs nominal window)")
    ax_zoom.set_xlim(left=0.0, right=zoom_end_us)
    ax_zoom.set_xlabel("Physical time from firing (µs)")
    ax.legend(loc="best")
    ax_zoom.legend(loc="best", fontsize="small")
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path)
    plt.close(fig)


def _evaluate_case(case: Case, *, output_dir: Path, max_three: int, n_points: int, benchmark_dir: Path, cat2: Catalog, cat3: Catalog) -> dict[str, Any]:
    case_dir = output_dir / "cases" / case.case_id
    waveform_dir = output_dir / "waveforms"
    plot_dir = output_dir / "plots"
    case_dir.mkdir(parents=True, exist_ok=True)
    baseline_specs = _baseline_configs(case, cat2, benchmark_dir)
    baseline_identity_guard = _benchmark_identity_guard(case, cat2, benchmark_dir)
    baseline_rows: list[dict[str, Any]] = []
    baseline_results: list[Any | None] = []
    for label, config, source in baseline_specs:
        row, result = _simulate(case, config, scope="<=2", candidate_index=None, provenance=source, n_points=n_points)
        row["label"] = label
        row["catalog_count"] = cat2.count
        if result is not None:
            # Configs loaded from the benchmark may carry exact recipe trees.
            row["front_module_options"] = sorted({int(recipe.module_count) for recipe in cat2.groups.get(cat2.exact_values[0], ())}) if "front_network" in config else [1, 2]
            row["tail_module_options"] = [1, 2]
        baseline_rows.append(row)
        baseline_results.append(result)

    # Prefer an actual finite baseline, then the first row.  The selected
    # crossover remains labelled as sampled/best-found, never globally exact.
    finite = [(row, result) for row, result in zip(baseline_rows, baseline_results) if result is not None and math.isfinite(float(row.get("objective_J", math.inf)))]
    locked_complete = next((item for item in zip(baseline_rows, baseline_results) if item[0].get("label") == "best2_existing_complete"), None)
    if locked_complete is not None:
        # A guarded complete benchmark is the declared <=2 baseline even if
        # a weaker diagnostic happens to receive a lower score in a replay.
        baseline_row, baseline_result = locked_complete
        baseline_selection_policy = "LOCKED_GUARDED_COMPLETE_PHYSICS_REPLAY"
    else:
        baseline_row, baseline_result = min(finite, key=lambda item: (item[0].get("status") != "PASS", item[0].get("objective_J", math.inf))) if finite else (baseline_rows[0], None)
        baseline_selection_policy = "GUIDED_OR_SIMPLE_DIAGNOSTIC_FALLBACK_ONLY_WHEN_GUARDED_COMPLETE_UNAVAILABLE"
    # If every two-module diagnostic is outside the evaluator domain, retain
    # the first actual failed waveform as the explicit negative diagnostic.
    if baseline_result is None and locked_complete is None:
        for row, result in zip(baseline_rows, baseline_results):
            if result is not None:
                baseline_row, baseline_result = row, result
                break
    base_config = baseline_row.get("configuration", {})
    fixed_stage = int(base_config.get("stages", 9))
    fixed_charge = float(base_config.get("stage_charge_V", _charge_for(case, fixed_stage)))

    seed_ids = _sample_three_ids(
        case,
        cat3,
        max(8, max_three // len(SAMPLE_SEEDS)),
        anchor_config=base_config,
    )
    unique_ids: list[tuple[int, int]] = []
    seen: set[int] = set()
    for seed in SAMPLE_SEEDS:
        for index in seed_ids[seed]:
            if index not in seen and len(unique_ids) < max_three:
                seen.add(index)
                unique_ids.append((seed, index))
    three_rows: list[dict[str, Any]] = []
    three_results: dict[Any, Any] = {}
    # The <=3 search space contains the exact <=2 baseline response.  Replay
    # it into the <=3 pool so a sampled <=3 result can never look better only
    # because the baseline was omitted from the declared comparison set.
    if baseline_result is not None:
        exact_three_row, exact_three_result = _simulate(
            case,
            baseline_row.get("configuration", {}),
            scope="<=3",
            candidate_index=None,
            provenance="exact_two_baseline_in_three_pool",
            n_points=n_points,
        )
        exact_three_row["label"] = "exact_two_baseline_in_three_pool"
        exact_three_row["seed"] = -1
        exact_three_row["catalog_count"] = cat3.count
        exact_three_row["baseline_source"] = baseline_row.get("provenance")
        three_rows.append(exact_three_row)
        if exact_three_result is not None:
            three_results["exact_two_baseline"] = exact_three_result
    for seed, index in unique_ids:
        stage, front, tail, details = _candidate_record(cat3, index)
        row, result = _verify_sampled_catalog_candidate(case, index, cat3, seed=seed, n_points=n_points)
        row["seed"] = seed
        row["label"] = "three_module_catalog_sample"
        row["catalog_count"] = cat3.count
        row.update(details)
        three_rows.append(row)
        if result is not None:
            three_results[index] = result

    def rank(row: Mapping[str, Any]) -> tuple[Any, ...]:
        return (row.get("status") != "PASS", not math.isfinite(float(row.get("objective_J", math.inf))), float(row.get("objective_J", math.inf)))

    finite_three = [row for row in three_rows if row.get("status") != "UNSUPPORTED" and math.isfinite(float(row.get("objective_J", math.inf)))]
    best_three_row = min(finite_three, key=rank) if finite_three else (three_rows[0] if three_rows else None)
    if best_three_row and best_three_row.get("label") == "exact_two_baseline_in_three_pool":
        best_three_result = three_results.get("exact_two_baseline")
    else:
        best_three_result = three_results.get(best_three_row.get("candidate_index")) if best_three_row else None

    # A same-N, same-charge crossover is mandatory.  If the sampled winner is
    # at another stage, retain the best sample in the controlled stratum.
    controlled = [row for row in finite_three if row.get("label") == "three_module_catalog_sample" and int((row.get("configuration") or {}).get("stages", -1)) == fixed_stage]
    controlled_seed_row = min(controlled, key=rank) if controlled else None
    controlled_three_row = None
    controlled_three_result = None
    if controlled_seed_row is not None:
        control_config = dict(controlled_seed_row["configuration"])
        control_config["stages"] = fixed_stage
        control_config["stage_charge_V"] = fixed_charge
        controlled_three_row, controlled_three_result = _simulate(
            case,
            control_config,
            scope="<=3_CONTROLLED_POST_SELECTION_REPLAY_FIXED_N_Q",
            candidate_index=controlled_seed_row.get("candidate_index"),
            provenance="post_selection_replay_selected_three_network_at_two_baseline_N_and_charge",
            n_points=n_points,
        )
        controlled_three_row.update({
            "label": "post_selection_replay_three_same_N_charge",
            "seed": controlled_seed_row.get("seed"),
            "catalog_count": cat3.count,
            "source_sample_row": controlled_seed_row.get("candidate_index"),
            "front_recipe": controlled_seed_row.get("front_recipe"),
            "tail_recipe": controlled_seed_row.get("tail_recipe"),
        })
    reference_wave = None
    reference_time_s: np.ndarray | None = None
    reference_meta: dict[str, Any] | None = None
    selected_two = baseline_result
    # The main result is the best <=3 result in the declared pool, which may
    # be the exact <=2 baseline when no sampled improvement is found.
    selected_three = best_three_result
    selected_three_row = best_three_row
    selected_control_three = controlled_three_result
    if selected_two is None and locked_complete is None:
        selected_two = next((result for result in baseline_results if result is not None), None)
    if selected_two is not None:
        max_end = max(float(selected_two.arrays["time_s"][-1]), float(selected_three.arrays["time_s"][-1]) if selected_three is not None else 0.0, float(selected_control_three.arrays["time_s"][-1]) if selected_control_three is not None else 0.0)
        reference_time_s = np.linspace(0.0, max_end, n_points)
        reference_wave, reference_meta = _reference_waveform(reference_time_s, case.mode, case.target_crest_V)

    crossover = None
    if selected_two is not None and selected_control_three is not None:
        crossover = _common_grid_metrics(selected_two, selected_control_three, case, reference_time_s, reference_wave, reference_meta)
    best_three_pair = None
    if selected_two is not None and selected_three is not None:
        best_three_pair = _common_grid_metrics(selected_two, selected_three, case, reference_time_s, reference_wave, reference_meta)
    selected_waveform_paths: dict[str, str] = {}
    if selected_two is not None:
        path = waveform_dir / f"{case.case_id}__selected_two.npz"
        _save_waveform(path, selected_two, reference_time_s, reference_wave)
        selected_waveform_paths["selected_two"] = str(path.relative_to(output_dir)).replace("\\", "/")
    if selected_three is not None:
        path = waveform_dir / f"{case.case_id}__selected_three.npz"
        _save_waveform(path, selected_three, reference_time_s, reference_wave)
        selected_waveform_paths["selected_three"] = str(path.relative_to(output_dir)).replace("\\", "/")
    if selected_control_three is not None:
        path = waveform_dir / f"{case.case_id}__controlled_three.npz"
        _save_waveform(path, selected_control_three, reference_time_s, reference_wave)
        selected_waveform_paths["controlled_three"] = str(path.relative_to(output_dir)).replace("\\", "/")
    if selected_two is not None and selected_three is not None:
        plot = plot_dir / f"{case.case_id}__overlay.png"
        _plot_overlay(plot, case, selected_two, selected_three, reference_time_s, reference_wave, selected_control_three)
        selected_waveform_paths["overlay_plot"] = str(plot.relative_to(output_dir)).replace("\\", "/")

    cumulative: list[dict[str, Any]] = []
    prior: list[dict[str, Any]] = []
    for seed in SAMPLE_SEEDS:
        prior.extend(row for row in three_rows if row.get("seed") == seed)
        available = [row for row in prior if math.isfinite(float(row.get("objective_J", math.inf)))]
        best = min(available, key=rank) if available else None
        cumulative.append({"through_seed": seed, "sample_count": len(prior), "best_objective_J": None if best is None else best.get("objective_J"), "best_status": None if best is None else best.get("status"), "best_candidate_index": None if best is None else best.get("candidate_index")})

    cost_rows = baseline_rows + three_rows + ([controlled_three_row] if controlled_three_row is not None else [])
    case_record = {
        "schema_version": "two_vs_three_waveform_case_v1",
        "case": case.as_dict(),
        "catalogs": {
            "max_modules_2": cat2.info(),
            "max_modules_3": cat3.info(),
            "three_sample_count": len(three_rows),
            "three_sample_seed_counts": {str(seed): sum(row.get("seed") == seed for row in three_rows) for seed in SAMPLE_SEEDS},
        },
        "selection": {
            "best_two": baseline_row,
            "selected_two_for_crossover": baseline_row,
            "best_three_sampled": best_three_row,
            "controlled_same_N_charge_three": controlled_three_row,
            "selected_three_for_overlay": best_three_row,
            "selected_three_for_crossover": controlled_three_row,
            "selected_three_interpretation": "PASS_SELECTED" if (best_three_row or {}).get("status") == "PASS" else "NOT_RECOMMENDED_BEST_FAILED_DIAGNOSTIC",
            "best_status_semantics": "PASS requires VALID numeric status, VALID_CLEAN_FULL_IMPULSE waveform, and evaluator PASS; otherwise result is retained as FAIL/UNSUPPORTED.",
            "scope": "BEST_FOUND_IN_DECLARED_SAMPLE",
            "cumulative_seed_minima": cumulative,
        },
        "baselines": baseline_rows,
        "baseline_identity_guard": baseline_identity_guard,
        "baseline_selection_policy": baseline_selection_policy,
        "three_sample_records": three_rows,
        "crossover": crossover,
        "best_three_pair_metrics": best_three_pair,
        "waveforms": selected_waveform_paths,
        "simulation_cost": {
            "attempt_count": len(cost_rows),
            "total_simulation_seconds": float(sum(float(row.get("simulation_seconds", 0.0)) for row in cost_rows)),
            "status_counts": {
                status: sum(1 for row in cost_rows if row.get("status") == status)
                for status in ("PASS", "FAIL", "UNSUPPORTED")
            },
            "controlled_simulation_included": controlled_three_row is not None,
            "two_module_coverage": "COMPLETE_PHYSICS_REPLAY" if any(row.get("label") == "best2_existing_complete" for row in baseline_rows) else "TWO_GUIDED_BASELINES_ONLY",
            "three_module_coverage": "DETERMINISTIC_BOUNDED_SAMPLE",
        },
        "study_limits": {
            "no_ml": True,
            "no_training": True,
            "no_model_search": True,
            "physics_verification_helper": "powernext_v3.optimizer.verify_candidate (Physics-only legal-charge verification)",
            "n_points": n_points,
            "fixed_crossover_stage": fixed_stage,
            "fixed_crossover_charge_V": fixed_charge,
            "common_grid_intersection_only": True,
            "no_peak_shift_or_amplitude_renormalization": True,
        },
    }
    _write_json(case_dir / "case.json", case_record)
    return case_record


def run_preliminary(output_dir: Path, *, max_three: int = 96, n_points: int = N_POINTS) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    cases = _load_cases()
    cat2 = Catalog(max_modules=2, stages=STAGES)
    cat3 = Catalog(max_modules=3, stages=STAGES)
    benchmark_dir = ROOT / "evidence" / "phase_b" / "search_benchmark"
    started = time.perf_counter()
    records = []
    for index, case in enumerate(cases, 1):
        print(f"[{datetime.now(timezone.utc).isoformat()}] case {index}/{len(cases)} {case.case_id} start", flush=True)
        record = _evaluate_case(case, output_dir=output_dir, max_three=max_three, n_points=n_points, benchmark_dir=benchmark_dir, cat2=cat2, cat3=cat3)
        records.append(record)
        selected = record["selection"].get("best_three_sampled") or {}
        print(f"[{datetime.now(timezone.utc).isoformat()}] case {index}/{len(cases)} done status={selected.get('status')} J={selected.get('objective_J')}", flush=True)

    manifest = {
        "schema_version": "two_vs_three_waveform_preliminary_v1",
        "purpose": "PRELIMINARY_ACTUAL_WAVEFORM_CROSSOVER_NO_ML_NO_TRAINING",
        "supersedes_output": "evidence/two_vs_three/preliminary and preliminary_v2 (retained immutable drafts; this run is the accepted version)",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "cases": [case.as_dict() for case in cases],
        "stages": list(STAGES),
        "catalogs": {"max_modules_2": cat2.info(), "max_modules_3": cat3.info()},
        "sample_policy": {
            "max_three_records": max_three,
            "seeds": list(SAMPLE_SEEDS),
            "seed_base": SEED,
            "guided_by": "log_distance_to_nominal_front_tail_and_module_count_strata_plus_deterministic_broad_draws_and_frozen_two_anchor_neighbours",
            "anchor_policy": "matching_frozen_or_guided_two_baseline_is_selected_before_three_simulation; up_to_5x5 physical three-module response neighbours at the anchor stage are rotated across seeds",
        },
        "source_artifacts": {
            "comparison_script": {
                "path": "tools/compare_two_three_waveforms.py",
                "sha256": _sha256(Path(__file__).resolve()),
            },
            "target_reference_helper": {
                "path": "tools/impulse_target_reference.py",
                "sha256": _sha256(TOOLS_ROOT / "impulse_target_reference.py"),
            },
        },
        "physics_source_fingerprint": physics.source_fingerprint(),
        "runtime": {"python": sys.version, "platform": platform.platform(), "pid": os.getpid()},
        "concurrent_load_caveat": "The approved four-policy two-module benchmark was running concurrently; wall times are diagnostic and are not cross-machine throughput measurements.",
        "no_claims": ["not a global <=3 optimum", "not hardware approval", "not IEC certification", "not measured-data validation", "not an ML result"],
        "elapsed_seconds": float(time.perf_counter() - started),
        "case_files": [str((output_dir / "cases" / case.case_id / "case.json").relative_to(output_dir)).replace("\\", "/") for case in cases],
    }
    _write_json(output_dir / "study_manifest.json", manifest)
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--preliminary", action="store_true", help="run the bounded five-case preliminary study")
    parser.add_argument("--output", type=Path, default=ROOT / "evidence" / "two_vs_three" / "preliminary")
    parser.add_argument("--max-three", type=int, default=96, help="maximum sampled <=3 candidates across all seeds per case")
    parser.add_argument("--n-points", type=int, default=N_POINTS)
    args = parser.parse_args(argv)
    if not args.preliminary:
        parser.error("--preliminary is required; the full campaign is intentionally deferred")
    if args.max_three < 32 or args.max_three > 128:
        parser.error("--max-three must be between 32 and 128 for the preliminary study")
    run_preliminary(args.output, max_three=args.max_three, n_points=args.n_points)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
