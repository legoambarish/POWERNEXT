"""Evaluate the frozen Phase B v3 candidate artifacts.

This report runner deliberately does not fit an estimator.  It loads the
immutable train-only registry cards, verifies the current predictive source
fingerprint through the registry loader, runs the strict validation oracle
against every candidate, and then scores the already frozen validation and
test partitions.  The resulting JSON contains aggregates only; per-row test
predictions are never copied into the evidence artifact.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from powernext_v3 import training
from powernext_v3.benchmark import OracleValidation
from powernext_v3.models import FAMILIES, FORMULATIONS
from powernext_v3.registry import (
    file_hash,
    load_model,
    runtime_versions,
    source_fingerprint,
)


TARGETS = tuple(training.TARGET_COLUMNS)
SEALED_KEYS = frozenset(("test_predictions", "selected_test"))
ORACLE_TIMING_KEYS = frozenset(("predict_seconds", "candidates_per_second"))
# These fields are added by the training wrapper around OracleValidation.  They
# are derived selection annotations rather than oracle scientific outputs and
# are recomputed below from the strict v2 aggregate.
ORACLE_WRAPPER_KEYS = frozenset(
    (
        "selection_usable",
        "feasible_retention_status",
        "selection_fallback",
        "selection_fallback_reason",
        "request_level_oracle_status",
        "selection_basis",
    )
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _route_id(route: tuple[str, str, str]) -> str:
    return ":".join(route)


def _route_from_id(value: str) -> tuple[str, str, str]:
    domain, mode, topology = value.split(":", 2)
    return domain, mode, topology


def _feature_matrix(model: Any, rows: Sequence[Mapping[str, Any]]) -> np.ndarray:
    if not rows:
        return np.empty((0, len(model.feature_order)), dtype=float)
    return np.asarray(
        [[row["features"][column] for column in model.feature_order] for row in rows],
        dtype=float,
    )


def _error_stats(errors: np.ndarray, tolerance: np.ndarray) -> dict[str, Any]:
    errors = np.asarray(errors, dtype=float)
    tolerance = np.asarray(tolerance, dtype=float)
    if errors.size == 0:
        return {
            "n": 0,
            "MAE": None,
            "RMSE": None,
            "P95_absolute_error": None,
            "max_absolute_error": None,
            "tolerance_normalized_MAE": None,
            "tolerance_normalized_P95": None,
        }
    normalized = errors / tolerance
    return {
        "n": int(errors.size),
        "MAE": float(np.mean(errors)),
        "RMSE": float(np.sqrt(np.mean(errors**2))),
        "P95_absolute_error": float(np.quantile(errors, 0.95)),
        "max_absolute_error": float(np.max(errors)),
        "tolerance_normalized_MAE": float(np.mean(normalized)),
        "tolerance_normalized_P95": float(np.quantile(normalized, 0.95)),
    }


def _near_boundary_mask(values: np.ndarray, lo: np.ndarray, hi: np.ndarray, half_width: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    lo = np.asarray(lo, dtype=float)
    hi = np.asarray(hi, dtype=float)
    edge = 0.25 * np.asarray(half_width, dtype=float)
    # Include values just inside and just outside either boundary.  The
    # boundary is a conformity decision surface, so restricting the mask to
    # the accepted band would miss the corresponding near-miss cases.
    return np.minimum(np.abs(values - lo), np.abs(values - hi)) <= edge


def _near_boundary_report(
    rows: Sequence[Mapping[str, Any]], mode: str, truth: np.ndarray, pred: np.ndarray
) -> dict[str, Any]:
    """Report actual prediction-minus-truth errors near each true boundary.

    ``training.metric_report(...)["boundary_errors"]`` is intentionally not
    used here as the primary metric.  Those legacy fields measure how far the
    prediction lies outside the conformity band, which is a different
    quantity from actual error on truth rows close to a boundary.
    """

    bounds = training._MODE_BOUNDS[mode]
    result: dict[str, Any] = {
        "definition": "truth within 0.25 tolerance half-width of either fixed boundary; absolute prediction-minus-truth error",
    }
    count = len(rows)
    for name, index in (("front_us", 1), ("tail_us", 2)):
        low, high = bounds[name]
        half_width = (high - low) / 2.0
        mask = _near_boundary_mask(truth[:, index], low, high, half_width)
        errors = np.abs(pred[mask, index] - truth[mask, index])
        result[name] = {
            "truth_near_boundary_count": int(np.sum(mask)),
            "truth_near_boundary_fraction": float(np.mean(mask)) if count else None,
            **_error_stats(errors, np.full(errors.shape, half_width, dtype=float)),
        }

    true_crest = training._crest_values(rows, truth[:, 0])
    pred_crest = training._crest_values(rows, pred[:, 0])
    if true_crest is None or pred_crest is None:
        result["crest_V"] = {"status": "UNAVAILABLE_WITH_ROW_SCHEMA"}
    else:
        true_value, targets = true_crest
        predicted_value, _ = pred_crest
        low = 0.97 * targets
        high = 1.03 * targets
        half_width = (high - low) / 2.0
        mask = _near_boundary_mask(true_value, low, high, half_width)
        errors = np.abs(predicted_value[mask] - true_value[mask])
        result["crest_V"] = {
            "truth_near_boundary_count": int(np.sum(mask)),
            "truth_near_boundary_fraction": float(np.mean(mask)) if count else None,
            **_error_stats(errors, half_width[mask]),
        }
    return result


def _compact_metrics(report: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "n": report.get("n"),
        "selection_score": report.get("selection_score"),
    }
    for name in TARGETS:
        value = report.get(name, {})
        out[name] = {
            key: value.get(key)
            for key in (
                "MAE",
                "RMSE",
                "P95_absolute_error",
                "max_absolute_error",
                "tolerance_normalized_MAE",
                "tolerance_normalized_P95",
            )
            if key in value
        }
    return out


def _partition_evaluation(model: Any, rows: Sequence[Mapping[str, Any]], mode: str) -> dict[str, Any]:
    x = _feature_matrix(model, rows)
    truth = training._labels(rows)
    started = time.perf_counter()
    pred = model.predict(x)
    prediction_seconds = time.perf_counter() - started
    ood_started = time.perf_counter()
    ood = np.asarray(model.ood(x), dtype=bool)
    ood_seconds = time.perf_counter() - ood_started
    report = training.metric_report(rows, truth, pred, mode, model_ood=ood)
    return {
        "metrics": _compact_metrics(report),
        "legacy_conformity_deviation": report.get("boundary_errors"),
        "near_boundary_actual_error": _near_boundary_report(rows, mode, truth, pred),
        "ood_count": int(np.sum(ood)),
        "ood_fraction": float(np.mean(ood)) if len(ood) else None,
        "prediction_seconds": float(prediction_seconds),
        "prediction_rows_per_second": float(len(rows) / prediction_seconds) if prediction_seconds > 0 else None,
        "ood_seconds": float(ood_seconds),
    }


def _strip_oracle_timing(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            key: _strip_oracle_timing(item)
            for key, item in value.items()
            if key not in ORACLE_TIMING_KEYS and key not in ORACLE_WRAPPER_KEYS
        }
    if isinstance(value, list):
        return [_strip_oracle_timing(item) for item in value]
    return value


def _oracle_schema_difference(old: Mapping[str, Any] | None, new: Mapping[str, Any]) -> dict[str, Any]:
    """Audit raw hook schema differences before scientific-key comparison."""

    old = old if isinstance(old, Mapping) else {}
    old_case_keys = set()
    new_case_keys = set()
    for case in old.get("cases", []):
        if isinstance(case, Mapping):
            old_case_keys.update(case)
    for case in new.get("cases", []):
        if isinstance(case, Mapping):
            new_case_keys.update(case)
    return {
        "training_record_top_level_only": sorted(set(old) - set(new)),
        "strict_v2_top_level_only": sorted(set(new) - set(old)),
        "training_record_case_level_only": sorted(old_case_keys - new_case_keys),
        "strict_v2_case_level_only": sorted(new_case_keys - old_case_keys),
        "timing_keys_excluded_from_scientific_comparison": sorted(ORACLE_TIMING_KEYS),
        "wrapper_annotation_keys_excluded_from_scientific_comparison": sorted(ORACLE_WRAPPER_KEYS),
    }


def _scientific_equal(left: Any, right: Any, path: str = "") -> tuple[bool, str | None]:
    left = _strip_oracle_timing(left)
    right = _strip_oracle_timing(right)
    if isinstance(left, Mapping) and isinstance(right, Mapping):
        if set(left) != set(right):
            return False, f"{path}:key_set"
        for key in sorted(left):
            equal, mismatch = _scientific_equal(left[key], right[key], f"{path}.{key}")
            if not equal:
                return False, mismatch
        return True, None
    if isinstance(left, list) and isinstance(right, list):
        if len(left) != len(right):
            return False, f"{path}:length"
        for index, (left_item, right_item) in enumerate(zip(left, right)):
            equal, mismatch = _scientific_equal(left_item, right_item, f"{path}[{index}]")
            if not equal:
                return False, mismatch
        return True, None
    if isinstance(left, (float, int)) and isinstance(right, (float, int)):
        if math.isclose(float(left), float(right), rel_tol=1e-12, abs_tol=1e-12):
            return True, None
        return False, f"{path}:numeric"
    if left == right:
        return True, None
    return False, f"{path}:value"


def _compact_oracle(value: Mapping[str, Any]) -> dict[str, Any]:
    cases = []
    for case in value.get("cases", []):
        cases.append(
            {
                key: case.get(key)
                for key in (
                    "request_id",
                    "candidate_count",
                    "feasible_count",
                    "first_feasible_rank",
                    "hit_at_k",
                    "regret_at_k",
                )
                if key in case
            }
        )
    return {
        key: value.get(key)
        for key in (
            "status",
            "request_count",
            "feasible_request_count",
            "missed_feasible_at_5",
            "feasible_hit_at_5",
            "retention",
            "mean_regret_at_25",
        )
        if key in value
    } | {"cases": cases}


def _learning_curve(candidate: Mapping[str, Any]) -> list[dict[str, Any]]:
    fields = (
        "fraction",
        "training_rows",
        "selection_score",
        "fit_seconds",
        "fit_rows_per_second",
        "serialized_estimate_bytes",
        "training_row_ids_sha256",
        "training_group_ids_sha256",
    )
    return [{key: stage[key] for key in fields if key in stage} for stage in candidate.get("learning_curve", [])]


def _load_rows(data_dir: Path) -> tuple[dict[str, Any], dict[tuple[str, str, str], dict[str, list[dict[str, Any]]]]]:
    all_rows, manifest = training.load_rows(data_dir)
    assignments = training.assign_splits(all_rows)
    pairs = [(dict(row), split) for row, split in zip(all_rows, assignments) if training._eligible(row)]
    eligible_rows = [row for row, _ in pairs]
    eligible_splits = [split for _, split in pairs]
    canonical, canonical_splits, deduplication, _ = training._deduplicate_training_rows(eligible_rows, eligible_splits)
    grouped: dict[tuple[str, str, str], dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for row, split in zip(canonical, canonical_splits):
        grouped[training._route(row)][split].append(row)
    manifest = dict(manifest)
    manifest["canonical_eligible_rows"] = len(canonical)
    manifest["deduplication"] = deduplication
    manifest["all_rows"] = len(all_rows)
    manifest["eligible_rows"] = len(eligible_rows)
    return manifest, grouped


def _candidate_result_map(results: Mapping[str, Any]) -> dict[str, dict[str, Mapping[str, Any]]]:
    return {
        route["route_id"]: {candidate["model_id"]: candidate for candidate in route["candidates"]}
        for route in results["routes"]
    }


def _markdown(report: Mapping[str, Any]) -> str:
    def number(value: Any, digits: int = 5) -> str:
        if value is None:
            return "—"
        if isinstance(value, bool):
            return "yes" if value else "no"
        try:
            value = float(value)
        except (TypeError, ValueError):
            return str(value)
        if not math.isfinite(value):
            return "—"
        return f"{value:.{digits}g}"

    lines = [
        "# Phase B v3 ML model evaluation",
        "",
        "This report evaluates the frozen train-only artifacts from the Phase B v3 run. Selection was frozen from validation evidence before the held-out test partition was read. No estimator was retrained or tuned for this report.",
        "",
        "The registry loader checked each model's card hash, route metadata, runtime, and current predictive-source fingerprint. The strict v2 request oracle was then run for all 32 candidates. Its scientific fields match the earlier validation-oracle results; timing fields are reported separately because they depend on the evaluation process.",
        "",
        "## Provenance",
        "",
        f"- Dataset: `{report['dataset']['data_manifest_sha256']}`; rows `{report['dataset']['rows_sha256']}`; `{report['dataset']['canonical_eligible_rows']}` canonical eligible rows.",
        f"- Training result: `{report['provenance']['results_sha256']}`; run manifest `{report['provenance']['run_manifest_sha256']}`.",
        f"- Oracle-v2 manifest: `{report['provenance']['oracle_v2_manifest_sha256']}`; requests `{report['provenance']['oracle_v2_requests_sha256']}`.",
        f"- Oracle scientific equivalence: `{report['oracle_equivalence']['all_routes_match']}` across `{report['oracle_equivalence']['candidate_route_count']}` candidate-route evaluations.",
        "- Raw hook schema audit: the first unnormalized comparison differed at the top-level key set because the training wrapper records selection annotations; those documented annotations and measured timing fields are retained in the JSON audit and excluded only from the scientific-field equality check.",
        f"- Runtime: Python `{report['provenance']['runtime'].get('python')}`, NumPy `{report['provenance']['runtime'].get('numpy')}`, scikit-learn `{report['provenance']['runtime'].get('sklearn')}`.",
        "",
        "## Route selections and frozen test summary",
        "",
        "Test metrics below are post-freeze evaluations. `Test norm` is the mean tolerance-normalized error across gain, front, and tail. Throughput is measured model prediction throughput in this sequential evaluator and is not a search-policy benchmark.",
        "",
        "| Route | Selected candidate | Model | Validation norm | Test norm | Test OOD | Artifact KiB | Load ms | Test rows/s | Oracle retention |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for route in report["routes"]:
        selected = next(candidate for candidate in route["candidates"] if candidate["selected"])
        test = selected["test"]
        lines.append(
            f"| {route['route_id']} | {selected['formulation']}/{selected['family']} | `{selected['model_id']}` | "
            f"{number(selected['validation']['metrics']['selection_score'])} | {number(test['metrics']['selection_score'])} | "
            f"{test['ood_count']} | {number(selected['artifact']['artifact_size_bytes'] / 1024, 4)} | "
            f"{number(selected['artifact']['load_seconds'] * 1000, 4)} | {number(test['prediction_rows_per_second'], 5)} | "
            f"{number(selected['oracle_v2'].get('retention')) if selected['oracle_v2'].get('feasible_request_count', 0) else 'unavailable'} |"
        )

    lines += ["", "## All four candidates by route", ""]
    for route in report["routes"]:
        lines += [
            f"### `{route['route_id']}`",
            "",
            "| Formulation | Family | Selected | Model | Validation norm | Test norm | Gain test MAE/P95 | Front test MAE/P95 | Tail test MAE/P95 | Test OOD | Size KiB | Load ms | Test rows/s |",
            "|---|---|:---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for candidate in route["candidates"]:
            test = candidate["test"]
            metrics = test["metrics"]
            lines.append(
                f"| {candidate['formulation']} | {candidate['family']} | {'yes' if candidate['selected'] else ''} | `{candidate['model_id']}` | "
                f"{number(candidate['validation']['metrics']['selection_score'])} | {number(metrics['selection_score'])} | "
                f"{number(metrics['gain']['MAE'])}/{number(metrics['gain']['P95_absolute_error'])} | "
                f"{number(metrics['front_us']['MAE'])}/{number(metrics['front_us']['P95_absolute_error'])} | "
                f"{number(metrics['tail_us']['MAE'])}/{number(metrics['tail_us']['P95_absolute_error'])} | "
                f"{test['ood_count']} | {number(candidate['artifact']['artifact_size_bytes'] / 1024, 4)} | "
                f"{number(candidate['artifact']['load_seconds'] * 1000, 4)} | {number(test['prediction_rows_per_second'], 5)} |"
            )
        lines.append("")

    lines += [
        "## Selected-model test errors",
        "",
        "These are the selected candidate's held-out errors. MAE, RMSE, P95, and maximum are in the target's native units; normalized values divide by the training tolerance scale.",
        "",
        "| Route | Target | n | MAE | RMSE | P95 | Max | Norm MAE | Norm P95 |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for route in report["routes"]:
        selected = next(candidate for candidate in route["candidates"] if candidate["selected"])
        for target in TARGETS:
            metric = selected["test"]["metrics"][target]
            lines.append(
                f"| {route['route_id']} | {target} | {selected['test']['metrics'].get('n')} | {number(metric.get('MAE'))} | {number(metric.get('RMSE'))} | "
                f"{number(metric.get('P95_absolute_error'))} | {number(metric.get('max_absolute_error'))} | "
                f"{number(metric.get('tolerance_normalized_MAE'))} | {number(metric.get('tolerance_normalized_P95'))} |"
            )

    lines += ["", "## Actual near-boundary errors", "", "The near-boundary metric selects rows whose true value is within 25% of a tolerance half-width from either boundary, then reports absolute prediction-minus-truth error. This is separate from the legacy `boundary_errors` fields, which measure predicted distance outside the conformity band and are retained only as a diagnostic in the machine-readable evidence.", "", "| Route | Partition | Target | Near-boundary n | MAE | P95 | Max | Norm P95 |", "|---|---|---|---:|---:|---:|---:|---:|"]
    for route in report["routes"]:
        selected = next(candidate for candidate in route["candidates"] if candidate["selected"])
        for partition in ("validation", "test"):
            near = selected[partition]["near_boundary_actual_error"]
            for target in ("front_us", "tail_us", "crest_V"):
                metric = near[target]
                if metric.get("status"):
                    lines.append(f"| {route['route_id']} | {partition} | {target} | — | — | — | — | — |")
                else:
                    lines.append(
                        f"| {route['route_id']} | {partition} | {target} | {metric.get('truth_near_boundary_count')} | "
                        f"{number(metric.get('MAE'))} | {number(metric.get('P95_absolute_error'))} | {number(metric.get('max_absolute_error'))} | "
                        f"{number(metric.get('tolerance_normalized_P95'))} |"
                    )

    lines += ["", "## Learning curves", "", "All candidates used the same nested grouped train subsets per route. Scores below are validation-only normalized error at 25%, 50%, and 100% of the canonical train partition. The 100% curve fit is the staged learning-curve fit; the frozen serving artifact is a separate full-capacity train fit whose row order can differ, so the 100% curve score is not asserted to be the serving artifact's score. The selected artifact's validation metrics above are authoritative for that frozen model.", "", "| Route | Candidate | 25% | 50% | 100% |", "|---|---|---:|---:|---:|"]
    for route in report["routes"]:
        for candidate in route["candidates"]:
            stages = {str(stage["fraction"]): stage.get("selection_score") for stage in candidate["learning_curve"]}
            lines.append(
                f"| {route['route_id']} | {candidate['formulation']}/{candidate['family']} | {number(stages.get('0.25'))} | {number(stages.get('0.5'))} | {number(stages.get('1.0'))} |"
            )

    lines += ["", "## Oracle-v2 selection recheck", "", "The strict v2 oracle was run against all four frozen candidates on each route. Scientific fields exclude only measured prediction-time fields. Selection keys were recomputed with the v2 hook, including the explicit fallback when a route has no true-feasible request.", "", "| Route | All candidate oracle fields match | Selection unchanged | Feasible requests | Missed feasible at 5 | Retention | Selection basis |", "|---|:---:|:---:|---:|---:|---:|---|"]
    for route in report["routes"]:
        oracle = route["oracle_selection_recheck"]
        lines.append(
            f"| {route['route_id']} | {'yes' if oracle['all_candidate_scientific_fields_match'] else 'no'} | {'yes' if oracle['selection_unchanged'] else 'no'} | "
            f"{oracle['feasible_request_count']} | {oracle['missed_feasible_at_5']} | {number(oracle.get('retention')) if oracle['feasible_request_count'] else 'unavailable'} | {oracle['selection_basis']} |"
        )

    lines += ["", "## Interpretation and limits", "", "- The selected artifacts remain the original train-only models; this evaluation performs no refit, calibration, or tuning.", "- The two research 3 µF O-shunt routes have zero true-feasible candidates in their frozen validation oracle requests. Their feasible retention and regret are undefined, so selection explicitly falls back to validation regression evidence; this is not evidence of perfect retention.", "- OOD counts are reported for the selected model and every candidate as a disclosure and prioritization signal. They are not a hard serving gate and do not provide an accuracy guarantee.", "- Artifact load and prediction throughput are sequential measurements from this evaluator. Search-policy timing and any broader speed claim belong to the separate controlled benchmark.", "- The test partition is one finite synthetic held-out partition from this run; it does not establish laboratory accuracy or universal optimizer performance.", ""]
    return "\n".join(lines)


def evaluate(args: argparse.Namespace) -> dict[str, Any]:
    data_dir = Path(args.data_dir)
    results_dir = Path(args.results_dir)
    registry_dir = Path(args.registry_dir)
    oracle_dir = Path(args.oracle_dir)
    output_json = Path(args.output_json)
    output_md = Path(args.output_md)

    results = _json(results_dir / "results.json")
    run_manifest = _json(results_dir / "run_manifest.json")
    data_manifest, grouped = _load_rows(data_dir)
    oracle = OracleValidation(oracle_dir)
    oracle_manifest = _json(oracle_dir / "manifest.json")
    candidate_results = _candidate_result_map(results)
    lead_decision_path = Path(args.lead_decision)

    routes: list[dict[str, Any]] = []
    equivalence_differences: list[dict[str, Any]] = []
    candidate_route_count = 0
    for route in sorted(training.ROUTES):
        route_key = _route_id(route)
        route_result = next(item for item in results["routes"] if item["route_id"] == route_key)
        route_rows = grouped[route]
        val_rows = route_rows["validation"]
        test_rows = route_rows["test"]
        candidate_entries: list[dict[str, Any]] = []
        strict_oracles: dict[str, Mapping[str, Any]] = {}
        for candidate_result in route_result["candidates"]:
            model_id = candidate_result["model_id"]
            folder = registry_dir / model_id
            load_started = time.perf_counter()
            model, card = load_model(folder, expected_route={"domain_id": route[0], "mode": route[1], "topology": route[2]})
            load_seconds = time.perf_counter() - load_started
            validation = _partition_evaluation(model, val_rows, route[1])
            test = _partition_evaluation(model, test_rows, route[1])
            strict = oracle(model, val_rows)
            strict_oracles[model_id] = strict
            old_hook = candidate_result["validation"].get("optimization_validation", {}).get("request_level_hook")
            match, mismatch = _scientific_equal(old_hook, strict)
            if not match:
                equivalence_differences.append({"route_id": route_key, "model_id": model_id, "first_mismatch": mismatch})
            candidate_route_count += 1
            model_path = folder / "model.joblib"
            card_path = folder / "card.json"
            candidate_entries.append(
                {
                    "formulation": candidate_result["formulation"],
                    "family": candidate_result["family"],
                    "model_id": model_id,
                    "selected": bool(candidate_result.get("selected")),
                    "selection_key_recorded": candidate_result.get("selection_key"),
                    "validation": validation,
                    "test": test,
                    "learning_curve": _learning_curve(candidate_result),
                    "oracle_v2": _compact_oracle(strict),
                    "oracle_schema_difference": _oracle_schema_difference(old_hook, strict),
                    "oracle_scientific_fields_match_training_record": match,
                    "artifact": {
                        "model_size_bytes": model_path.stat().st_size,
                        "card_size_bytes": card_path.stat().st_size,
                        "artifact_size_bytes": model_path.stat().st_size + card_path.stat().st_size,
                        "load_seconds": float(load_seconds),
                        "card_sha256": _sha256(card_path),
                        "model_sha256": _sha256(model_path),
                        "card_model_id": card.get("model_id"),
                    },
                }
            )

        # Recompute the exact validation selection key with strict v2 hook data.
        recomputed: list[tuple[tuple[float, ...], str]] = []
        for candidate_result in route_result["candidates"]:
            clone = copy.deepcopy(candidate_result)
            opt = clone.setdefault("validation", {}).setdefault("optimization_validation", {})
            opt["request_level_hook"] = strict_oracles[clone["model_id"]]
            key = training._selection_key(clone)
            recomputed.append((tuple(float(value) for value in key), clone["model_id"]))
        recomputed.sort(key=lambda item: item[0])
        selected_model_id = route_result["selected_model_id"]
        winner = recomputed[0][1]
        winner_entry = next(candidate for candidate in candidate_entries if candidate["model_id"] == selected_model_id)
        strict_selection = _compact_oracle(strict_oracles[selected_model_id])
        selection_basis = route_result.get("selection_evidence", {}).get("selection_basis")
        routes.append(
            {
                "route_id": route_key,
                "selected_model_id": selected_model_id,
                "selected_formulation": route_result["selected_formulation"],
                "selected_family": route_result["selected_family"],
                "selection_evidence_recorded": route_result.get("selection_evidence"),
                "oracle_selection_recheck": {
                    "all_candidate_scientific_fields_match": all(candidate["oracle_scientific_fields_match_training_record"] for candidate in candidate_entries),
                    "selection_unchanged": winner == selected_model_id,
                    "recomputed_winner_model_id": winner,
                    "recomputed_selection_key": list(recomputed[0][0]),
                    **strict_selection,
                    "selection_basis": selection_basis,
                },
                "candidates": candidate_entries,
                "selected_test": winner_entry["test"],
            }
        )

    report = {
        "schema_version": "phase_b_v3_final_model_evaluation_v1",
        "purpose": "frozen_candidate_validation_oracle_recheck_and_authorized_test_evaluation",
        "selection_frozen": True,
        "retrained": False,
        "test_metrics_authorized": True,
        "per_row_predictions_persisted": False,
        "dataset": {
            "data_dir": str(data_dir),
            "data_manifest_sha256": data_manifest.get("manifest_sha256"),
            "rows_sha256": data_manifest.get("rows_sha256"),
            "all_rows": data_manifest.get("all_rows"),
            "eligible_rows": data_manifest.get("eligible_rows"),
            "canonical_eligible_rows": data_manifest.get("canonical_eligible_rows"),
            "deduplication": data_manifest.get("deduplication"),
        },
        "provenance": {
            "results_sha256": _sha256(results_dir / "results.json"),
            "run_manifest_sha256": _sha256(results_dir / "run_manifest.json"),
            "split_assignments_sha256": _sha256(results_dir / "split_assignments.json"),
            "lead_decision_sha256": _sha256(lead_decision_path),
            "oracle_v2_manifest_sha256": _sha256(oracle_dir / "manifest.json"),
            "oracle_v2_requests_sha256": oracle_manifest.get("requests_sha256"),
            "oracle_v2_directory": str(oracle_dir),
            "runtime": runtime_versions(),
            "predictive_source_fingerprint": source_fingerprint(),
        },
        "oracle_equivalence": {
            "oracle_v2_status": oracle_manifest.get("status"),
            "candidate_route_count": candidate_route_count,
            "all_routes_match": not equivalence_differences,
            "differences": equivalence_differences,
            "comparison_scope": "compact OracleValidation scientific fields; excludes measured prediction timing and documented training-wrapper annotations",
            "excluded_timing_keys": sorted(ORACLE_TIMING_KEYS),
            "excluded_wrapper_annotation_keys": sorted(ORACLE_WRAPPER_KEYS),
        },
        "learning_curve_interpretation": {
            "curve_100_is_same_serving_artifact": False,
            "reason": "The staged 100% learning-curve fit and the frozen full-capacity train fit use the same canonical partition but may receive different row order; final serving-artifact validation metrics are authoritative.",
        },
        "routes": routes,
    }
    report["oracle_equivalence"]["all_candidate_scientific_fields_match"] = not equivalence_differences
    schema_differences = [
        candidate["oracle_schema_difference"]
        for route in routes
        for candidate in route["candidates"]
    ]
    report["oracle_equivalence"]["schema_audit"] = {
        "training_record_top_level_only_union": sorted({
            key for difference in schema_differences for key in difference["training_record_top_level_only"]
        }),
        "strict_v2_top_level_only_union": sorted({
            key for difference in schema_differences for key in difference["strict_v2_top_level_only"]
        }),
        "training_record_case_level_only_union": sorted({
            key for difference in schema_differences for key in difference["training_record_case_level_only"]
        }),
        "strict_v2_case_level_only_union": sorted({
            key for difference in schema_differences for key in difference["strict_v2_case_level_only"]
        }),
    }
    report["oracle_equivalence"]["raw_initial_comparison"] = {
        "observed_mismatch": bool(schema_differences and any(
            difference["training_record_top_level_only"] or difference["strict_v2_top_level_only"]
            or difference["training_record_case_level_only"] or difference["strict_v2_case_level_only"]
            for difference in schema_differences
        )),
        "first_mismatch": ":key_set",
        "reason": "The immutable training record wraps OracleValidation with selection annotations; raw top-level equality therefore fails before the documented scientific comparison scope is applied.",
        "comparison_after_documented_exclusions": not equivalence_differences,
    }
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False), encoding="utf-8")
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_md.write_text(_markdown(report), encoding="utf-8")
    print(f"wrote {output_json}")
    print(f"wrote {output_md}")
    print(f"evaluated {candidate_route_count} candidate-route artifacts")
    print(f"oracle_scientific_equivalence={report['oracle_equivalence']['all_candidate_scientific_fields_match']}")
    print(f"selection_unchanged={all(route['oracle_selection_recheck']['selection_unchanged'] for route in routes)}")
    print("CPU_HEAVY_EVALUATION_COMPLETE=true")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", default="powernext/ml/data/networks_v3_r2")
    parser.add_argument("--results-dir", default="powernext/ml/results/networks_v3")
    parser.add_argument("--registry-dir", default="powernext/ml/registry/networks_v3")
    parser.add_argument("--oracle-dir", default="powernext/ml/data/networks_v3_validation_oracles_v2")
    parser.add_argument("--output-json", default="evidence/phase_b/final_model_evaluation.json")
    parser.add_argument("--output-md", default="docs/PHASE_B_MODEL_REPORT.md")
    parser.add_argument("--lead-decision", default="evidence/phase_b/lead_validation_decision.json")
    args = parser.parse_args()
    report = evaluate(args)
    selection_unchanged = all(route["oracle_selection_recheck"]["selection_unchanged"] for route in report["routes"])
    if not report["oracle_equivalence"]["all_candidate_scientific_fields_match"] or not selection_unchanged:
        print("FAIL_CLOSED: oracle scientific equivalence or frozen selection changed")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
