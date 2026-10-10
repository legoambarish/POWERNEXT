"""Bounded actual <=2 versus <=3 waveform study for difficult PowerNext routes.

This utility extends the accepted five-case preliminary comparison with the
declared rare CPRI LI setup and the two research 3 uF O-shunt requests.  It
uses the frozen catalog and Physics-only ``verify_candidate`` helper.  The
rare request is exhaustively verified over its complete 14-stage <=2 catalog;
the <=3 catalog is sampled deterministically with stage, module-pair, local,
and broad strata.  Research requests reuse their completed <=2 catalog
identity and retain a finite failed Physics diagnostic when no compliant row
exists.  No ML artifact is loaded and no training data is written.
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
from typing import Any, Mapping

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
TOOLS_ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(TOOLS_ROOT) not in sys.path:
    sys.path.insert(0, str(TOOLS_ROOT))

from powernext_v3 import physics  # noqa: E402
from powernext_v3.catalog import Catalog  # noqa: E402
from powernext_v3.optimizer import verify_candidate  # noqa: E402
from powernext_v3.profiles import get_profile  # noqa: E402
from physics_engine.network import PhysicsError  # noqa: E402
import compare_two_three_waveforms as prelim  # noqa: E402


N_POINTS = 1600
SEED = 20261010
DEFAULT_MAX_THREE = 256
PRELIMINARY_REQUEST_IDS = (
    "FROZEN_test_cpri_0p5uf_LI_GSHUNT_v0_0",
    "FROZEN_test_cpri_0p5uf_LI_GSHUNT_v0_1",
    "FROZEN_test_cpri_0p5uf_LI_OSHUNT_v0_0",
    "FROZEN_test_cpri_0p5uf_SI_GSHUNT_v0_0",
    "FROZEN_test_cpri_0p5uf_SI_OSHUNT_v0_0",
)
RESEARCH_REQUEST_IDS = (
    "FROZEN_test_research_3uf_LI_OSHUNT_v0_0",
    "FROZEN_test_research_3uf_SI_OSHUNT_v0_0",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _jsonable(value: Any) -> Any:
    return prelim._jsonable(value)


def _write_json(path: Path, value: Any) -> None:
    prelim._write_json(path, value)


def _short_id(value: str) -> str:
    return prelim._short_id(value)


@dataclass(frozen=True)
class ExtendedCase:
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
    stages: tuple[int, ...]

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
            "stages": list(self.stages),
        }


def _load_extended_cases() -> list[ExtendedCase]:
    cases: list[ExtendedCase] = []
    for old in prelim._load_cases():
        cases.append(
            ExtendedCase(
                case_id=old.case_id,
                request_id=old.request_id,
                domain_id=old.domain_id,
                mode=old.mode,
                topology_id=old.topology_id,
                target_crest_V=old.target_crest_V,
                setup=dict(old.setup),
                source_path=old.source_path,
                source_sha256=old.source_sha256,
                source_kind=old.source_kind,
                stages=tuple(prelim.STAGES),
            )
        )

    request_path = ROOT / "evidence" / "phase_b" / "search_benchmark" / "requests.json"
    requests = json.loads(request_path.read_text(encoding="utf-8"))
    by_id = {str(row["request_id"]): row for row in requests}
    for request_id in RESEARCH_REQUEST_IDS:
        row = by_id[request_id]
        setup = dict(row["setup"])
        setup.setdefault("load_resistance_ohm", None)
        setup.setdefault("auxiliary_assumption", "UNCONFIRMED_AUXILIARY_BRANCHES_OMITTED")
        setup.setdefault("setup_id", request_id)
        mode = str(row.get("impulse_type", row.get("mode")))
        domain = str(row.get("domain_id", "research_3uf"))
        cases.append(
            ExtendedCase(
                case_id=_short_id(f"{domain}_{mode}_{row['topology_id']}_{request_id}"),
                request_id=request_id,
                domain_id=domain,
                mode=mode,
                topology_id=str(row["topology_id"]),
                target_crest_V=float(row["target_crest_V"]),
                setup=setup,
                source_path=str(request_path.relative_to(ROOT)).replace("\\", "/"),
                source_sha256=_sha256(request_path),
                source_kind="FROZEN_RESEARCH_BENCHMARK_REQUEST",
                stages=tuple(int(n) for n in row["stages"]),
            )
        )

    rare_path = ROOT / "powernext" / "optimizer" / "examples" / "LI_rare_timing_pass.json"
    rare = json.loads(rare_path.read_text(encoding="utf-8"))
    rare_setup = dict(rare["setup"])
    rare_setup.setdefault("load_resistance_ohm", None)
    rare_setup.setdefault("auxiliary_assumption", "UNCONFIRMED_AUXILIARY_BRANCHES_OMITTED")
    cases.append(
        ExtendedCase(
            case_id=_short_id(f"cpri_0p5uf_LI_{rare['topology_id']}_{rare['request_id']}"),
            request_id=str(rare["request_id"]),
            domain_id="cpri_0p5uf",
            mode=str(rare["impulse_type"]),
            topology_id=str(rare["topology_id"]),
            target_crest_V=float(rare["target_crest_V"]),
            setup=rare_setup,
            source_path=str(rare_path.relative_to(ROOT)).replace("\\", "/"),
            source_sha256=_sha256(rare_path),
            source_kind="PHASE_A_RARE_DIAGNOSTIC_INPUT",
            stages=tuple(range(2, 16)),
        )
    )
    return cases


def _request(case: ExtendedCase, max_modules: int) -> dict[str, Any]:
    return {
        "schema_version": "network_request_v3",
        "request_id": f"TWO_VS_THREE_EXTENDED_{case.case_id}",
        "domain_id": case.domain_id,
        "impulse_type": case.mode,
        "topology_id": case.topology_id,
        "target_crest_V": case.target_crest_V,
        "setup": dict(case.setup),
        "stages": list(case.stages),
        "max_modules": max_modules,
        "search_mode": "complete",
        "priority": "complete_physics",
        "inventory": None,
        "polarity": 1,
    }


def _rank(row: Mapping[str, Any]) -> tuple[Any, ...]:
    value = row.get("objective_J", math.inf)
    try:
        value = float(value)
    except (TypeError, ValueError):
        value = math.inf
    return (row.get("status") != "PASS", not math.isfinite(value), value, int(row.get("candidate_index") or -1))


def _verify_row(case: ExtendedCase, index: int, catalog: Catalog, *, scope: str, provenance: str) -> tuple[dict[str, Any], Any | None]:
    started = time.perf_counter()
    request = _request(case, catalog.max_modules)
    profile = get_profile(case.domain_id)
    row, result, _ = verify_candidate(int(index), catalog, request, profile)
    elapsed = time.perf_counter() - started
    if result is None:
        status = "UNSUPPORTED"
        record: dict[str, Any] = {
            "scope": scope,
            "candidate_index": int(index),
            "provenance": provenance,
            "status": status,
            "verification_status": row.get("verification_status"),
            "reason_codes": list(row.get("reason_codes") or []),
            "configuration": row.get("configuration"),
            "objective_J": None,
            "simulation_seconds": float(elapsed),
            "numeric_status": None,
            "waveform_status": None,
            "compliance_status": None,
            "compliant": False,
        }
        return record, None
    record = prelim._metrics(result, case, scope=scope, candidate_index=int(index), provenance=provenance, elapsed_s=elapsed)
    record["configuration"] = dict(row.get("configuration") or result.metadata.get("inputs", {}).get("configuration", {}))
    record["canonical_score"] = row.get("score")
    record["objective_J"] = None if row.get("score") is None else float(row["score"]["J"])
    record["verification_status"] = row.get("verification_status")
    record["reason_codes"] = list(row.get("reason_codes") or record.get("reason_codes") or [])
    record["compliant"] = bool(row.get("compliant"))
    record["front_recipe"] = row.get("front_recipe")
    record["tail_recipe"] = row.get("tail_recipe")
    record["front_physical_alternatives"] = row.get("front_physical_alternatives")
    record["tail_physical_alternatives"] = row.get("tail_physical_alternatives")
    record["stored_energy_J"] = row.get("stored_energy_J")
    return record, result


def _candidate_details(catalog: Catalog, index: int) -> dict[str, Any]:
    stages, front, tail = catalog.decode([int(index)])
    remainder = int(index) % (catalog.width * catalog.width)
    fi, ti = divmod(remainder, catalog.width)
    return {
        "catalog_index": int(index),
        "stage": int(stages[0]),
        "front_equivalent_ohm": float(front[0]),
        "tail_equivalent_ohm": float(tail[0]),
        "front_index": int(fi),
        "tail_index": int(ti),
    }


def _selected_recipe_details(catalog: Catalog, index: int) -> dict[str, Any]:
    item = catalog.physical(int(index))
    return {
        "catalog_details": _candidate_details(catalog, index),
        "catalog_candidate_id": item["candidate_id"],
        "physical_alternative_count": item["physical_alternative_count"],
        "front_recipe": item["front"].as_dict(),
        "tail_recipe": item["tail"].as_dict(),
        "front_network": item["front"].tree,
        "tail_network": item["tail"].tree,
    }


def _benchmark_identity(case: ExtendedCase, catalog: Catalog, benchmark_dir: Path) -> dict[str, Any]:
    path = benchmark_dir / f"{case.request_id}.json"
    result: dict[str, Any] = {"path": str(path.relative_to(ROOT)).replace("\\", "/"), "exists": path.exists(), "checks": {}}
    if not path.exists():
        result.update(passed=False, failure_reasons=["BENCHMARK_FILE_MISSING"])
        return result
    payload = json.loads(path.read_text(encoding="utf-8"))
    request = payload.get("request") or {}
    complete = next((row for row in payload.get("policies", []) if row.get("policy") == "complete_physics"), None)
    search = (complete or {}).get("search") or {}
    best = (complete or {}).get("best_configuration")
    expected = catalog.info()
    checks: dict[str, bool] = {
        "request_id": request.get("request_id") == case.request_id,
        "domain_id": request.get("domain_id") == case.domain_id,
        "impulse_type": request.get("impulse_type") == case.mode,
        "topology_id": request.get("topology_id") == case.topology_id,
        "target_crest_V": isinstance(request.get("target_crest_V"), (int, float)) and math.isclose(float(request["target_crest_V"]), case.target_crest_V, rel_tol=0.0, abs_tol=1e-9),
        "setup_identity": prelim._same_setup(request.get("setup") or {}, case.setup),
        "stages_request": request.get("stages") == list(case.stages),
        "stages_catalog": search.get("stages") == list(case.stages),
        "max_modules": request.get("max_modules") == 2 and search.get("max_modules_per_branch") == 2,
        "polarity": request.get("polarity", 1) in (None, 1),
        "complete_strategy": search.get("requested_strategy") == "complete_physics" and search.get("effective_strategy") == "complete_physics",
        "catalog_sha256": search.get("catalog_sha256") == expected["catalog_sha256"],
        "catalog_count": search.get("distinct_response_candidates") == expected["distinct_response_candidates"],
        "catalog_recipe_count": search.get("theoretical_recipe_configurations") == expected["theoretical_recipe_configurations"],
        "catalog_complete": search.get("catalog_complete") is True,
        "termination": search.get("termination_reason") == "DECLARED_CATALOG_COMPLETED",
    }
    no_pass_status = (complete or {}).get("status") == "NO_COMPLIANT_CONFIGURATION_IN_DECLARED_CATALOG"
    pass_status = (complete or {}).get("status") == "VERIFIED_COMPLIANT"
    checks["complete_status_known"] = no_pass_status or pass_status
    if pass_status:
        checks.update({
            "best_configuration_present": isinstance(best, Mapping),
            "best_configuration_route": isinstance(best, Mapping) and best.get("impulse_type") == case.mode and best.get("topology_id") == case.topology_id,
            "best_configuration_stages": isinstance(best, Mapping) and best.get("stages") in case.stages,
            "best_configuration_networks": isinstance(best, Mapping) and isinstance(best.get("front_network"), Mapping) and isinstance(best.get("tail_network"), Mapping),
            "best_configuration_polarity": isinstance(best, Mapping) and best.get("polarity", 1) == 1,
        })
    else:
        checks["no_pass_has_no_best_configuration"] = best is None
    result["checks"] = checks
    result["passed"] = all(checks.values())
    result["failure_reasons"] = [key for key, value in checks.items() if not value]
    result["complete_status"] = (complete or {}).get("status")
    result["complete_best_configuration_present"] = isinstance(best, Mapping)
    return result


def _load_completed_best(case: ExtendedCase, guard: Mapping[str, Any], benchmark_dir: Path) -> dict[str, Any] | None:
    if not guard.get("passed") or guard.get("complete_status") != "VERIFIED_COMPLIANT":
        return None
    payload = json.loads((benchmark_dir / f"{case.request_id}.json").read_text(encoding="utf-8"))
    complete = next(row for row in payload.get("policies", []) if row.get("policy") == "complete_physics")
    return dict(complete["best_configuration"])


def _nearest_indices(catalog: Catalog, target: float, module_count: int | None = None, limit: int = 4) -> list[int]:
    choices: list[tuple[float, int]] = []
    target = max(float(target), 1e-30)
    for index, value in enumerate(catalog.exact_values):
        if module_count is not None and not any(recipe.module_count == module_count for recipe in catalog.groups[value]):
            continue
        choices.append((abs(math.log(max(float(value), 1e-30) / target)), index))
    choices.sort(key=lambda item: (item[0], item[1]))
    return [index for _, index in choices[:limit]]


def _sample_three_indices(case: ExtendedCase, catalog: Catalog, anchor: Mapping[str, Any] | None, max_count: int) -> list[int]:
    digest = hashlib.sha256(case.case_id.encode("utf-8")).hexdigest()
    case_seed = int(digest[:12], 16) % 1_000_000
    rng = np.random.default_rng(SEED + case_seed)
    anchor_stage = int((anchor or {}).get("stages", case.stages[len(case.stages) // 2]))
    anchor_front = float((anchor or {}).get("front_per_stage_ohm", 30.0))
    anchor_tail = float((anchor or {}).get("tail_per_stage_ohm", 180.0))
    ids: list[int] = []
    seen: set[int] = set()

    def add(stage: int, fi: int, ti: int) -> None:
        index = catalog.encode(catalog.stages.index(int(stage)), int(fi), int(ti))
        if index not in seen and len(ids) < max_count:
            seen.add(index)
            ids.append(index)

    # Every declared stage and all nine front/tail module-count pairs get
    # deterministic nearest equivalent values.  This is the fixed coverage
    # stratum, independent of observed outcomes.
    for stage in case.stages:
        for fm in (1, 2, 3):
            for tm in (1, 2, 3):
                fs = _nearest_indices(catalog, anchor_front, fm, limit=2)
                ts = _nearest_indices(catalog, anchor_tail, tm, limit=2)
                for fi, ti in zip(fs, ts):
                    add(stage, fi, ti)
                    if len(ids) >= max_count:
                        return ids

    # Local response neighbours around the actual <=2 anchor, with three
    # modules on each branch where available.
    local_stage = anchor_stage if anchor_stage in catalog.stages else catalog.stages[len(catalog.stages) // 2]
    for fi in _nearest_indices(catalog, anchor_front, 3, limit=12):
        for ti in _nearest_indices(catalog, anchor_tail, 3, limit=12):
            add(local_stage, fi, ti)
            if len(ids) >= max_count:
                return ids

    # Deterministic broad draws fill the remaining budget without pretending
    # that an analytic distance is a feasibility filter.
    while len(ids) < max_count:
        add(int(catalog.stages[int(rng.integers(0, len(catalog.stages)))]), int(rng.integers(0, catalog.width)), int(rng.integers(0, catalog.width)))
        if len(seen) >= catalog.count:
            break
    return ids


def _scan_complete_two(case: ExtendedCase, catalog: Catalog, case_dir: Path) -> tuple[dict[str, Any], dict[str, Any] | None, Any | None]:
    case_dir.mkdir(parents=True, exist_ok=True)
    jsonl = case_dir / "complete_two_catalog.jsonl"
    counts: dict[str, int] = {}
    pass_count = 0
    finite_count = 0
    best_pass: tuple[dict[str, Any], Any] | None = None
    best_finite: tuple[dict[str, Any], Any] | None = None
    started = time.perf_counter()
    with jsonl.open("w", encoding="utf-8") as handle:
        for index in range(catalog.count):
            row, result = _verify_row(case, index, catalog, scope="<=2_COMPLETE_14_STAGE" if len(case.stages) == 14 else "<=2_COMPLETE", provenance="complete_declared_catalog")
            status = str(row.get("verification_status") or row.get("status"))
            counts[status] = counts.get(status, 0) + 1
            if result is not None and math.isfinite(float(row.get("objective_J", math.inf))):
                finite_count += 1
                if row.get("status") == "PASS":
                    pass_count += 1
                    if best_pass is None or _rank(row) < _rank(best_pass[0]):
                        best_pass = (row, result)
                if best_finite is None or _rank(row) < _rank(best_finite[0]):
                    best_finite = (row, result)
            compact = {
                **_candidate_details(catalog, index),
                "verification_status": row.get("verification_status"),
                "status": row.get("status"),
                "compliant": bool(row.get("compliant")),
                "objective_J": row.get("objective_J"),
                "crest_V": row.get("crest_V"),
                "front_us": row.get("front_us"),
                "tail_us": row.get("tail_us"),
                "reason_codes": row.get("reason_codes", []),
            }
            handle.write(json.dumps(_jsonable(compact), sort_keys=True, allow_nan=False) + "\n")
            if (index + 1) % 256 == 0 or index + 1 == catalog.count:
                elapsed = time.perf_counter() - started
                print(f"[{datetime.now(timezone.utc).isoformat()}] {case.case_id} two {index + 1:,}/{catalog.count:,} finite={finite_count:,} pass={pass_count:,} elapsed={elapsed:.1f}s", flush=True)
    selected = best_pass or best_finite
    summary = {
        "complete": True,
        "catalog_count": catalog.count,
        "evaluated_count": catalog.count,
        "index_sequence": "0..count-1",
        "full_declared_stage_coverage": list(case.stages),
        "verification_status_counts": counts,
        "finite_waveform_count": finite_count,
        "pass_count": pass_count,
        "selected_semantics": "BEST_PASS" if best_pass is not None else "BEST_FINITE_FAILED_DIAGNOSTIC",
        "selected_row": selected[0] if selected else None,
        "jsonl_path": str(jsonl.relative_to(case_dir.parent.parent)).replace("\\", "/"),
        "jsonl_sha256": _sha256(jsonl),
        "elapsed_seconds": float(time.perf_counter() - started),
    }
    return summary, None if selected is None else selected[0], None if selected is None else selected[1]


def _find_finite_failed(case: ExtendedCase, catalog: Catalog, limit: int = 256) -> tuple[dict[str, Any], Any | None, dict[str, Any]]:
    counts: dict[str, int] = {}
    chosen: tuple[dict[str, Any], Any] | None = None
    started = time.perf_counter()
    for index in range(min(limit, catalog.count)):
        row, result = _verify_row(case, index, catalog, scope="<=2_FINITE_FAILED_DIAGNOSTIC", provenance="bounded_diagnostic_after_complete_catalog_no_pass")
        status = str(row.get("verification_status") or row.get("status"))
        counts[status] = counts.get(status, 0) + 1
        if result is not None and math.isfinite(float(row.get("objective_J", math.inf))) and row.get("status") != "PASS":
            if chosen is None or _rank(row) < _rank(chosen[0]):
                chosen = (row, result)
    if chosen is None:
        raise RuntimeError(f"No finite failed Physics diagnostic found within {limit} candidates for {case.case_id}")
    return chosen[0], chosen[1], {"attempt_limit": min(limit, catalog.count), "status_counts": counts, "elapsed_seconds": float(time.perf_counter() - started), "unsupported_not_selected": True}


def _add_selected_details(catalog: Catalog, row: dict[str, Any]) -> dict[str, Any]:
    index = row.get("candidate_index")
    if index is not None:
        row.update(_selected_recipe_details(catalog, int(index)))
    return row


def _save_case_waveforms(output_dir: Path, case: ExtendedCase, baseline_result: Any | None, display_three_result: Any | None, control_result: Any | None, reference_time: np.ndarray | None, reference_wave: np.ndarray | None) -> dict[str, str]:
    paths: dict[str, str] = {}
    waveform_dir = output_dir / "waveforms"
    plot_dir = output_dir / "plots"
    if baseline_result is not None:
        path = waveform_dir / f"{case.case_id}__selected_two.npz"
        prelim._save_waveform(path, baseline_result, reference_time, reference_wave)
        paths["selected_two"] = str(path.relative_to(output_dir)).replace("\\", "/")
    if display_three_result is not None:
        path = waveform_dir / f"{case.case_id}__selected_three_actual.npz"
        prelim._save_waveform(path, display_three_result, reference_time, reference_wave)
        paths["selected_three_actual"] = str(path.relative_to(output_dir)).replace("\\", "/")
    if control_result is not None:
        path = waveform_dir / f"{case.case_id}__controlled_three_post_selection.npz"
        prelim._save_waveform(path, control_result, reference_time, reference_wave)
        paths["controlled_three_post_selection"] = str(path.relative_to(output_dir)).replace("\\", "/")
    if baseline_result is not None and display_three_result is not None:
        path = plot_dir / f"{case.case_id}__overlay.png"
        prelim._plot_overlay(path, case, baseline_result, display_three_result, reference_time, reference_wave, control_result)
        paths["overlay_plot"] = str(path.relative_to(output_dir)).replace("\\", "/")
    return paths


def _evaluate_case(case: ExtendedCase, output_dir: Path, benchmark_dir: Path, max_three: int, n_points: int) -> dict[str, Any]:
    case_dir = output_dir / "cases" / case.case_id
    case_dir.mkdir(parents=True, exist_ok=True)
    cat2 = Catalog(max_modules=2, stages=case.stages)
    cat3 = Catalog(max_modules=3, stages=case.stages)
    identity = _benchmark_identity(case, cat2, benchmark_dir) if case.request_id.startswith("FROZEN_test_") else {"applicable": False, "passed": False, "reason": "rare_input_or_no_benchmark_replay"}
    baseline_row: dict[str, Any] | None = None
    baseline_result: Any | None = None
    scan_summary: dict[str, Any] | None = None
    baseline_policy: str

    if case.request_id in PRELIMINARY_REQUEST_IDS:
        config = _load_completed_best(case, identity, benchmark_dir)
        if config is None:
            raise RuntimeError(f"Guarded complete benchmark unavailable for {case.request_id}: {identity.get('failure_reasons')}")
        baseline_row, baseline_result = prelim._simulate(case, config, scope="<=2", candidate_index=None, provenance="guarded_complete_benchmark_replay", n_points=n_points)
        baseline_row.update({"label": "best2_existing_complete", "catalog_count": cat2.count, "catalog_identity": cat2.identity, "baseline_catalog_complete_identity": True})
        baseline_policy = "LOCKED_GUARDED_COMPLETE_PHYSICS_REPLAY"
    elif case.request_id == "LI_RARE_DIAGNOSTIC":
        scan_summary, scanned_row, scanned_result = _scan_complete_two(case, cat2, case_dir)
        if scanned_row is None or scanned_result is None:
            raise RuntimeError(f"Rare complete <=2 scan produced no finite waveform for {case.case_id}")
        baseline_row, baseline_result = scanned_row, scanned_result
        baseline_row.update({"label": "complete_two_all14_best_pass" if baseline_row.get("status") == "PASS" else "complete_two_all14_best_finite_failed_diagnostic", "catalog_count": cat2.count, "catalog_identity": cat2.identity, "baseline_catalog_complete_identity": True})
        _add_selected_details(cat2, baseline_row)
        baseline_policy = "COMPLETE_PHYSICS_ALL_14_STAGES"
    else:
        if not identity.get("passed"):
            raise RuntimeError(f"Research complete catalog identity failed for {case.request_id}: {identity.get('failure_reasons')}")
        baseline_row, baseline_result, diagnostic = _find_finite_failed(case, cat2)
        baseline_row.update({"label": "best_finite_failed_diagnostic_after_complete_two_no_pass", "catalog_count": cat2.count, "catalog_identity": cat2.identity, "baseline_catalog_complete_identity": True, "diagnostic_scan": diagnostic})
        _add_selected_details(cat2, baseline_row)
        baseline_policy = "COMPLETED_TWO_CATALOG_NO_PASS_FINITE_DIAGNOSTIC"

    if baseline_result is None:
        raise RuntimeError(f"No baseline waveform available for {case.case_id}")
    base_config = dict(baseline_row.get("configuration") or {})
    fixed_stage = int(base_config.get("stages", case.stages[len(case.stages) // 2]))
    fixed_charge = float(base_config.get("stage_charge_V", prelim._charge_for(case, fixed_stage)))
    ids = _sample_three_indices(case, cat3, base_config, max_three)
    three_rows: list[dict[str, Any]] = []
    three_results: dict[int, Any] = {}
    # The exact <=2 baseline is retained in the <=3 response pool.  It is
    # separately labelled from actual three-module catalog candidates.
    exact_row = dict(baseline_row)
    exact_row.update({"scope": "<=3", "label": "exact_two_baseline_in_three_pool", "provenance": "exact_two_baseline_in_three_pool", "candidate_index": None, "seed": -1, "catalog_count": cat3.count})
    three_rows.append(exact_row)
    for position, index in enumerate(ids):
        seed = int(position % 4)
        row, result = _verify_row(case, index, cat3, scope="<=3_BOUNDED_SAMPLE", provenance=f"deterministic_extended_sample_seed_{seed}")
        row.update(_candidate_details(cat3, index))
        row.update({"label": "three_module_catalog_sample", "seed": seed, "catalog_count": cat3.count})
        if result is not None:
            physical = cat3.physical(int(index))
            row["physical_alternative_count"] = physical["physical_alternative_count"]
        three_rows.append(row)
        if result is not None:
            three_results[int(index)] = result
        if (position + 1) % 64 == 0 or position + 1 == len(ids):
            print(f"[{datetime.now(timezone.utc).isoformat()}] {case.case_id} three {position + 1:,}/{len(ids):,}", flush=True)

    finite_pool = [row for row in three_rows if math.isfinite(float(row.get("objective_J", math.inf)))]
    finite_actual = [row for row in three_rows if row.get("label") == "three_module_catalog_sample" and math.isfinite(float(row.get("objective_J", math.inf)))]
    pool_row = min(finite_pool, key=_rank) if finite_pool else exact_row
    actual_row = min(finite_actual, key=_rank) if finite_actual else None
    pool_result = baseline_result if pool_row.get("label") == "exact_two_baseline_in_three_pool" else three_results.get(int(pool_row.get("candidate_index")))
    actual_result = None if actual_row is None else three_results.get(int(actual_row.get("candidate_index")))
    display_row = actual_row or pool_row
    display_result = actual_result or pool_result

    controlled_row: dict[str, Any] | None = None
    controlled_result: Any | None = None
    if actual_row is not None and actual_result is not None:
        control_config = dict(actual_row.get("configuration") or {})
        control_config["stages"] = fixed_stage
        control_config["stage_charge_V"] = fixed_charge
        controlled_row, controlled_result = prelim._simulate(case, control_config, scope="<=3_CONTROLLED_POST_SELECTION_REPLAY_FIXED_N_Q", candidate_index=actual_row.get("candidate_index"), provenance="post_selection_replay_selected_three_network_at_two_baseline_N_and_charge", n_points=n_points)
        controlled_row.update({"label": "post_selection_replay_three_same_N_charge", "seed": actual_row.get("seed"), "catalog_count": cat3.count, "source_sample_row": actual_row.get("candidate_index"), "front_recipe": actual_row.get("front_recipe"), "tail_recipe": actual_row.get("tail_recipe")})

    max_end = max(float(baseline_result.arrays["time_s"][-1]), float(display_result.arrays["time_s"][-1]) if display_result is not None else 0.0, float(controlled_result.arrays["time_s"][-1]) if controlled_result is not None else 0.0)
    reference_time = np.linspace(0.0, max_end, n_points)
    reference_wave, reference_meta = prelim._reference_waveform(reference_time, case.mode, case.target_crest_V)
    actual_pair = None if display_result is None else prelim._common_grid_metrics(baseline_result, display_result, case, reference_time, reference_wave, reference_meta)
    pool_pair = None if pool_result is None else prelim._common_grid_metrics(baseline_result, pool_result, case, reference_time, reference_wave, reference_meta)
    control_pair = None if controlled_result is None else prelim._common_grid_metrics(baseline_result, controlled_result, case, reference_time, reference_wave, reference_meta)
    waveforms = _save_case_waveforms(output_dir, case, baseline_result, display_result, controlled_result, reference_time, reference_wave)
    best_three_improvement = bool(actual_row is not None and baseline_row.get("status") == "PASS" and actual_row.get("status") == "PASS" and float(actual_row.get("objective_J", math.inf)) < float(baseline_row.get("objective_J", math.inf)))
    crossover_eligible = bool(identity.get("passed") or (case.request_id == "LI_RARE_DIAGNOSTIC" and scan_summary and scan_summary.get("complete"))) and baseline_row.get("status") == "PASS" and actual_row is not None and actual_row.get("status") == "PASS"
    if best_three_improvement and crossover_eligible:
        recommendation = "BOUNDED_SAMPLE_IMPROVEMENT"
    elif actual_row is None:
        recommendation = "NO_THREE_MODULE_FINITE_DIAGNOSTIC"
    elif not crossover_eligible:
        recommendation = "DIAGNOSTIC_ONLY_BASELINE_HAS_NO_COMPLETE_PASS"
    else:
        recommendation = "NO_MEANINGFUL_BOUNDED_SAMPLE_IMPROVEMENT"

    case_record = {
        "schema_version": "two_vs_three_waveform_extended_case_v1",
        "case": case.as_dict(),
        "catalogs": {"max_modules_2": cat2.info(), "max_modules_3": cat3.info(), "three_sample_count_including_exact_two": len(three_rows), "three_actual_candidate_count": len(ids)},
        "baseline_identity_guard": identity,
        "baseline_selection_policy": baseline_policy,
        "complete_two_scan": scan_summary,
        "selection": {
            "best_two": _add_selected_details(cat2, dict(baseline_row)),
            "best_three_pool": pool_row,
            "best_three_sampled_actual": actual_row,
            "selected_three_for_overlay": display_row,
            "controlled_same_N_charge_three": controlled_row,
            "selected_three_interpretation": "PASS_SELECTED_ACTUAL_THREE" if actual_row and actual_row.get("status") == "PASS" else ("NOT_RECOMMENDED_BEST_FAILED_DIAGNOSTIC" if actual_row else "EXACT_TWO_POOL_ONLY"),
            "crossover_claim_eligible": crossover_eligible,
            "bounded_sample_improvement": best_three_improvement,
            "recommendation": recommendation,
        },
        "three_sample_records": three_rows,
        "actual_three_pair_metrics": actual_pair,
        "pooled_best_three_pair_metrics": pool_pair,
        "post_selection_control_metrics": control_pair,
        "waveforms": waveforms,
        "reference": reference_meta,
        "simulation_cost": {
            "attempt_count": len(three_rows) + 1 + (1 if controlled_row is not None else 0),
            "total_simulation_seconds": float(sum(float(row.get("simulation_seconds", 0.0)) for row in three_rows) + float(baseline_row.get("simulation_seconds", 0.0)) + (float(controlled_row.get("simulation_seconds", 0.0)) if controlled_row else 0.0)),
            "controlled_simulation_included": controlled_row is not None,
            "complete_two_scan_included": scan_summary is not None,
        },
        "study_limits": {
            "no_ml": True,
            "no_training": True,
            "no_optimizer_search": True,
            "physics_helper": "powernext_v3.optimizer.verify_candidate; no model prediction",
            "n_points": n_points,
            "fixed_control_semantics": "POST_SELECTION_REPLAY_NETWORK_SELECTED_AT_LEGAL_OPTIMIZED_CHARGE_THEN_REPLAYED_AT_BASELINE_N_AND_Q",
            "common_grid_intersection_only": True,
            "no_peak_shift_or_amplitude_renormalization": True,
            "global_optimum_claim": False,
            "hardware_claim": False,
        },
    }
    _write_json(case_dir / "case.json", case_record)
    return case_record


def run_extended(output_dir: Path, *, max_three: int = DEFAULT_MAX_THREE, n_points: int = N_POINTS) -> dict[str, Any]:
    if output_dir.exists() and any(output_dir.iterdir()):
        raise FileExistsError(f"Refusing to overwrite non-empty study directory: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=False)
    benchmark_dir = ROOT / "evidence" / "phase_b" / "search_benchmark"
    cases = _load_extended_cases()
    started = time.perf_counter()
    records: list[dict[str, Any]] = []
    for number, case in enumerate(cases, 1):
        print(f"[{datetime.now(timezone.utc).isoformat()}] case {number}/{len(cases)} {case.case_id} start", flush=True)
        record = _evaluate_case(case, output_dir, benchmark_dir, max_three, n_points)
        records.append(record)
        print(f"[{datetime.now(timezone.utc).isoformat()}] case {number}/{len(cases)} done recommendation={record['selection']['recommendation']}", flush=True)
    manifest = {
        "schema_version": "two_vs_three_waveform_extended_v1",
        "purpose": "BOUNDED_ACTUAL_WAVEFORM_COMPARISON_NO_ML_NO_TRAINING",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "cases": [case.as_dict() for case in cases],
        "case_files": [str((output_dir / "cases" / case.case_id / "case.json").relative_to(output_dir)).replace("\\", "/") for case in cases],
        "policy": {
            "existing_preliminary_cases": list(PRELIMINARY_REQUEST_IDS),
            "research_cases": list(RESEARCH_REQUEST_IDS),
            "rare_case": "LI_RARE_DIAGNOSTIC",
            "rare_two_catalog": "complete 32,256 candidates over all stages 2..15",
            "three_sample_max_per_case": max_three,
            "three_sample_design": "deterministic stage coverage, nine module-count pairs, local response neighbours, then broad fixed-seed draws",
            "selection": "canonical parameter_score at legal charge; exact <=2 baseline retained in <=3 pool; actual three-module sample reported separately",
        },
        "source_artifacts": {
            "extended_script": {"path": "tools/compare_two_three_extended.py", "sha256": _sha256(Path(__file__).resolve())},
            "preliminary_script": {"path": "tools/compare_two_three_waveforms.py", "sha256": _sha256(TOOLS_ROOT / "compare_two_three_waveforms.py")},
            "target_reference_helper": {"path": "tools/impulse_target_reference.py", "sha256": _sha256(TOOLS_ROOT / "impulse_target_reference.py")},
        },
        "physics_source_fingerprint": physics.source_fingerprint(),
        "runtime": {"python": sys.version, "platform": platform.platform(), "pid": os.getpid()},
        "concurrent_load_caveat": "Wall timing includes concurrent desktop workloads and is not a cross-machine throughput measurement.",
        "no_claims": ["not a global <=3 optimum", "not hardware approval", "not IEC certification", "not measured-data validation", "not an ML result", "not a training-data generation run"],
        "recommendations": [{"case_id": row["case"]["case_id"], "request_id": row["case"]["request_id"], "recommendation": row["selection"]["recommendation"], "crossover_claim_eligible": row["selection"]["crossover_claim_eligible"]} for row in records],
        "elapsed_seconds": float(time.perf_counter() - started),
    }
    _write_json(output_dir / "study_manifest.json", manifest)
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "evidence" / "two_vs_three" / "extended_v1")
    parser.add_argument("--max-three", type=int, default=DEFAULT_MAX_THREE, help="bounded actual <=3 candidates per case")
    parser.add_argument("--n-points", type=int, default=N_POINTS)
    args = parser.parse_args(argv)
    if args.max_three < 256 or args.max_three > 512:
        parser.error("--max-three must be between 256 and 512 for the extended bounded study")
    if args.n_points < 400:
        parser.error("--n-points must be at least 400")
    run_extended(args.output, max_three=args.max_three, n_points=args.n_points)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
