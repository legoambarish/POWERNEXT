"""Post-hoc held-out accuracy by supported 2/3-module scope.

This helper reuses frozen production ``test_predictions`` from ``results.json``.
It never loads a model, calls ``predict``/``ood``, fits an estimator, or measures
throughput. Module counts are joined from immutable design JSONL by row_id and
checked against leaves in each row's stored canonical network trees.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np

from powernext_v3 import training
from powernext_v3.features import BASELINE_COLUMNS, FEATURE_COLUMNS
from powernext_v3.registry import file_hash


ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "powernext" / "ml" / "data" / "networks_v3_r2"
RESULTS_PATH = ROOT / "powernext" / "ml" / "results" / "networks_v3" / "results.json"
OUTPUT_PATH = ROOT / "evidence" / "phase_b" / "two_three_model_scope.json"
REPORT_PATH = ROOT / "docs" / "PHASE_B_MODEL_REPORT.md"
DOCS_PATH = ROOT / "docs" / "phase_b_ml.md"
TARGETS = tuple(training.TARGET_COLUMNS)
BUCKETS = ("max_module_count_le_2", "max_module_count_eq_3", "max_module_count_gt_3_excluded")


def _json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()


def _leaf_count(tree: Any) -> int:
    if not isinstance(tree, Mapping):
        raise ValueError(f"Network tree must be a mapping, got {type(tree).__name__}")
    op = tree.get("op")
    if op == "R":
        if set(tree) != {"op", "ohm"}:
            raise ValueError(f"Malformed resistor tree fields: {sorted(tree)}")
        return 1
    if op not in {"S", "P"} or set(tree) != {"op", "children"}:
        raise ValueError(f"Malformed network tree fields: {sorted(tree)}")
    children = tree["children"]
    if not isinstance(children, Sequence) or isinstance(children, (str, bytes, bytearray)):
        raise ValueError("Network children must be a sequence")
    return sum(_leaf_count(child) for child in children)


def _row_id(row: Mapping[str, Any]) -> str:
    value = row.get("row_id", row.get("id"))
    if value is None:
        raise ValueError("Canonical row is missing row_id")
    return str(value)


def _route(row: Mapping[str, Any]) -> tuple[str, str, str]:
    values = (row.get("domain_id"), row.get("mode", row.get("impulse_type")), row.get("topology", row.get("topology_id")))
    if any(value is None for value in values):
        raise ValueError(f"Row is missing route fields: {values!r}")
    return tuple(str(value) for value in values)  # type: ignore[return-value]


def _route_id(route: Sequence[str]) -> str:
    return ":".join(route)


def _module_bucket(max_count: int) -> str:
    if max_count <= 2:
        return BUCKETS[0]
    if max_count == 3:
        return BUCKETS[1]
    return BUCKETS[2]


def _metrics(rows: Sequence[Mapping[str, Any]], truth: np.ndarray, prediction: np.ndarray, mode: str, ood: np.ndarray) -> dict[str, Any]:
    if not rows:
        return {"n": 0, "selection_score": None, "ood_count": 0, "ood_fraction": None, "targets": {target: {"n": 0} for target in TARGETS}}
    tolerance = training._tolerances(rows, mode)
    absolute = np.abs(np.asarray(prediction, dtype=float) - np.asarray(truth, dtype=float))
    normalized = absolute / tolerance
    targets: dict[str, Any] = {}
    for index, target in enumerate(TARGETS):
        error = absolute[:, index]
        normalized_error = normalized[:, index]
        targets[target] = {
            "n": int(error.size),
            "MAE": float(np.mean(error)),
            "RMSE": float(np.sqrt(np.mean(error**2))),
            "P95_absolute_error": float(np.quantile(error, 0.95)),
            "max_absolute_error": float(np.max(error)),
            "tolerance_normalized_MAE": float(np.mean(normalized_error)),
            "tolerance_normalized_P95": float(np.quantile(normalized_error, 0.95)),
        }
    return {"n": int(len(rows)), "selection_score": float(np.mean(normalized)), "ood_count": int(np.sum(ood)), "ood_fraction": float(np.mean(ood)), "targets": targets}


def _load_canonical_rows() -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    all_rows, manifest = training.load_rows(DATA_DIR)
    eligible = [row for row in all_rows if training._eligible(row)]
    assignments = training.assign_splits(eligible)
    canonical, canonical_assignments, deduplication, _ = training._deduplicate_training_rows(eligible, assignments)
    rows = []
    for row, split in zip(canonical, canonical_assignments):
        copy = dict(row)
        copy["split"] = split
        rows.append(copy)
    audit = {
        "all_rows": len(all_rows),
        "eligible_rows": len(eligible),
        "canonical_rows": len(rows),
        "deduplication": deduplication,
        "canonical_row_ids_sha256": _digest(sorted(_row_id(row) for row in rows)),
        "canonical_row_ids_unique": len({_row_id(row) for row in rows}) == len(rows),
    }
    if not audit["canonical_row_ids_unique"]:
        raise ValueError("Canonical rows contain duplicate row_id values")
    return rows, dict(manifest), audit


def _load_design_counts(row_ids: set[str]) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    design_path = DATA_DIR / "design.jsonl"
    manifest = _json(DATA_DIR / "manifest.json")
    found: dict[str, dict[str, Any]] = {}
    line_count = 0
    digest = hashlib.sha256()
    with design_path.open("rb") as stream:
        for raw in stream:
            digest.update(raw)
            if not raw.strip():
                continue
            line_count += 1
            record = json.loads(raw)
            row_id = str(record.get("row_id"))
            if row_id not in row_ids:
                continue
            front = record.get("front_network_module_count")
            tail = record.get("tail_network_module_count")
            if not isinstance(front, int) or not isinstance(tail, int):
                raise ValueError(f"Design row {row_id} lacks integer module counts")
            found[row_id] = {
                "front_network_module_count": front,
                "tail_network_module_count": tail,
                "max_module_count": max(front, tail),
                "domain_id": record.get("domain_id"),
                "mode": record.get("mode"),
                "topology_id": record.get("topology_id"),
                "split": record.get("split"),
            }
    actual_hash = digest.hexdigest()
    expected_hashes = [manifest.get("design_sha256"), manifest.get("design_file_sha256")]
    expected_hashes = [value for value in expected_hashes if isinstance(value, str)]
    if expected_hashes and actual_hash not in expected_hashes:
        raise ValueError(f"design.jsonl hash mismatch: actual={actual_hash} expected={expected_hashes}")
    return found, {
        "path": str(design_path),
        "sha256": actual_hash,
        "manifest_design_sha256": manifest.get("design_sha256"),
        "manifest_design_file_sha256": manifest.get("design_file_sha256"),
        "line_count": line_count,
        "rows_manifest_row_count": manifest.get("row_count"),
        "line_count_matches_rows_manifest": line_count == int(manifest.get("row_count", line_count)),
        "line_count_scope_note": "design.jsonl retains the full design-attempt catalog; rows.jsonl contains the completed STAGE_COMPLETE row subset",
        "requested_row_ids": len(row_ids),
        "matched_row_ids": len(found),
    }


def _load_predictions() -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    results = _json(RESULTS_PATH)
    return results, {route["route_id"]: route for route in results["routes"]}


def _append_markdown(report: Mapping[str, Any]) -> None:
    text = REPORT_PATH.read_text(encoding="utf-8")
    heading = "## Two/three-module supported-scope held-out accuracy"
    if heading in text:
        text = text[: text.index(heading)].rstrip() + "\n"
    lines = [
        "",
        heading,
        "",
        "This is a post-hoc stratification of the frozen canonical held-out test partition. It reuses the selected model's original `results.json` predictions; it performs no fitting, model loading, new inference, timing run, or waveform regeneration. The trained artifacts remain mixed 1–4-module models. The two active strata are `max(front_network_module_count, tail_network_module_count) <= 2` and exactly `== 3`; rows with a larger maximum are historical four-module data and are excluded from both columns.",
        "",
        "The exact module fields come from the immutable paired `design.jsonl`: `front_network_module_count` and `tail_network_module_count`. Each matched test row's counts were checked against the leaf counts of `configuration.front_network` and `configuration.tail_network` in `rows.jsonl`. The rows themselves carry the equivalent-resistance network trees and do not carry those two scalar module-count fields.",
        "",
        "The v3 feature contract uses equivalent resistance and physics baseline columns; recipe/tree identity, charge, target crest, and polarity are excluded. Therefore these results describe mixed-model accuracy when the forward search is restricted to 2/3-module candidates, not a separately trained 2/3-only model.",
        "",
        "| Route | max ≤2 n | max ≤2 norm | max =3 n | max =3 norm | max >3 excluded |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for route in report["routes"]:
        metrics = route["metrics"]
        le2 = metrics[BUCKETS[0]]
        eq3 = metrics[BUCKETS[1]]
        excluded = metrics[BUCKETS[2]]
        lines.append(f"| {route['route_id']} | {le2['n']} | {le2['selection_score']:.6g} | {eq3['n']} | {eq3['selection_score']:.6g} | {excluded['n']} |")
    lines += [
        "",
        "Target-level MAE/RMSE/P95/max and tolerance-normalized metrics for both strata are in [`two_three_model_scope.json`](../evidence/phase_b/two_three_model_scope.json). The source and prediction hashes, row-join checks, canonical split counts, and four-module exclusions are recorded there.",
        "",
    ]
    REPORT_PATH.write_text(text + "\n".join(lines), encoding="utf-8")


def _append_docs(report: Mapping[str, Any]) -> None:
    text = DOCS_PATH.read_text(encoding="utf-8")
    heading = "### Supported 2/3-module held-out scope"
    if heading in text:
        text = text[: text.index(heading)].rstrip() + "\n"
    lines = [
        "",
        heading,
        "",
        "The supplemental held-out table in [the final model report](PHASE_B_MODEL_REPORT.md) and [`evidence/phase_b/two_three_model_scope.json`](../evidence/phase_b/two_three_model_scope.json) stratifies the frozen canonical test rows by `max(front_network_module_count, tail_network_module_count) <= 2` versus exactly `== 3`, separately for all eight routes. It reuses original selected-model predictions from the production `results.json`; it does not retrain or run new inference. The trained artifacts remain mixed 1–4-module models, and rows with maximum count 4 are historical/excluded from the two active strata.",
        "",
        "The exact count fields are `front_network_module_count` and `tail_network_module_count` in immutable `design.jsonl`; each test row is joined by `row_id` and checked against the leaf count of the equivalent-resistance trees stored in `rows.jsonl`. v3 features use equivalent resistance and physics baseline columns while excluding recipe/tree identity, so this is a scope diagnostic for the existing mixed models rather than evidence from a dedicated 2/3-only fit.",
        "",
    ]
    DOCS_PATH.write_text(text + "\n".join(lines), encoding="utf-8")


def main() -> int:
    rows, data_manifest, canonical_audit = _load_canonical_rows()
    canonical_ids = {_row_id(row) for row in rows}
    design_counts, design_audit = _load_design_counts(canonical_ids)
    missing = sorted(canonical_ids - set(design_counts))
    if missing:
        raise ValueError(f"design.jsonl is missing {len(missing)} canonical row ids; first={missing[:3]}")

    by_route_split: dict[tuple[str, str, str], dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    module_records: dict[str, dict[str, Any]] = {}
    total_canonical_bucket_counts = Counter()
    total_canonical_module_counts = Counter()
    mismatch_examples: list[dict[str, Any]] = []
    for row in rows:
        row_id = _row_id(row)
        route = _route(row)
        counts = design_counts[row_id]
        configuration = row.get("configuration")
        if not isinstance(configuration, Mapping):
            raise ValueError(f"Row {row_id} lacks configuration mapping")
        derived_front = _leaf_count(configuration.get("front_network"))
        derived_tail = _leaf_count(configuration.get("tail_network"))
        if (derived_front, derived_tail) != (counts["front_network_module_count"], counts["tail_network_module_count"]):
            mismatch_examples.append({"row_id": row_id, "design": [counts["front_network_module_count"], counts["tail_network_module_count"]], "configuration_tree": [derived_front, derived_tail]})
        if tuple(str(counts[key]) for key in ("domain_id", "mode", "topology_id")) != route:
            mismatch_examples.append({"row_id": row_id, "route": route, "design_route": counts})
        max_count = counts["max_module_count"]
        bucket = _module_bucket(max_count)
        module_records[row_id] = {**counts, "derived_front_network_leaf_count": derived_front, "derived_tail_network_leaf_count": derived_tail, "bucket": bucket}
        total_canonical_bucket_counts[bucket] += 1
        total_canonical_module_counts[str(max_count)] += 1
        by_route_split[route][str(row["split"])].append(row)
    if mismatch_examples:
        raise ValueError(f"Module-count/tree or route mismatches: {mismatch_examples[:3]}")

    results, result_by_route = _load_predictions()
    routes: list[dict[str, Any]] = []
    total_test_bucket_counts = Counter()
    for route in sorted(by_route_split):
        route_id = _route_id(route)
        route_result = result_by_route[route_id]
        selected_model_id = route_result["selected_model_id"]
        selected_candidate = next(candidate for candidate in route_result["candidates"] if candidate["model_id"] == selected_model_id)
        prediction_key = f"{selected_candidate['formulation']}:{selected_candidate['family']}"
        prediction_records = route_result.get("test_predictions", {}).get(prediction_key)
        if not isinstance(prediction_records, list):
            raise ValueError(f"Missing frozen test_predictions for {route_id} {prediction_key}")
        test_rows = by_route_split[route].get("test", [])
        test_ids = [_row_id(row) for row in test_rows]
        prediction_ids = [str(record.get("row_id")) for record in prediction_records]
        if len(set(prediction_ids)) != len(prediction_ids):
            raise ValueError(f"Duplicate frozen prediction row ids for {route_id}")
        if set(prediction_ids) != set(test_ids):
            raise ValueError(f"Frozen prediction/test row-id set differs for {route_id}")
        prediction_by_id = {str(record["row_id"]): record for record in prediction_records}
        ordered_records = [prediction_by_id[row_id] for row_id in test_ids]
        order_exact = prediction_ids == test_ids
        truth = np.asarray([record["truth"] for record in ordered_records], dtype=float)
        prediction = np.asarray([record["prediction"] for record in ordered_records], dtype=float)
        ood = np.asarray([bool(record.get("ood", False)) for record in ordered_records], dtype=bool)
        expected_truth = training._labels(test_rows)
        if truth.shape != expected_truth.shape or not np.allclose(truth, expected_truth, rtol=1.0e-12, atol=1.0e-12):
            raise ValueError(f"Frozen prediction truth does not match canonical rows for {route_id}")

        metrics: dict[str, Any] = {}
        module_counts_by_bucket: Counter[str] = Counter()
        for bucket in BUCKETS:
            mask = np.asarray([module_records[row_id]["bucket"] == bucket for row_id in test_ids], dtype=bool)
            bucket_rows = [row for row, keep in zip(test_rows, mask) if keep]
            metrics[bucket] = _metrics(bucket_rows, truth[mask], prediction[mask], route[1], ood[mask])
            module_counts_by_bucket[bucket] = len(bucket_rows)
            total_test_bucket_counts[bucket] += len(bucket_rows)

        distributions = {split: dict(sorted(Counter(str(module_records[_row_id(row)]["max_module_count"]) for row in split_rows).items())) for split, split_rows in by_route_split[route].items()}
        routes.append({
            "route_id": route_id,
            "domain_id": route[0],
            "mode": route[1],
            "topology": route[2],
            "selected_model_id": selected_model_id,
            "selected_formulation": selected_candidate["formulation"],
            "selected_family": selected_candidate["family"],
            "prediction_source_key": prediction_key,
            "heldout_partition": "test",
            "canonical_test_rows": len(test_rows),
            "prediction_row_order_exact": order_exact,
            "module_count_distribution_by_split": distributions,
            "module_bucket_counts": dict(module_counts_by_bucket),
            "metrics": metrics,
        })

    row_fields = rows[0] if rows else {}
    row_scalar_module_field_counts = {
        field: sum(1 for row in rows if field in row)
        for field in ("front_network_module_count", "tail_network_module_count")
    }
    row_configuration_field_counts = {
        field: sum(
            1
            for row in rows
            if isinstance(row.get("configuration"), Mapping) and field in row["configuration"]
        )
        for field in ("front_network", "tail_network")
    }
    report = {
        "schema_version": "phase_b_v3_two_three_module_scope_v1",
        "purpose": "posthoc_frozen_selected_model_accuracy_by_network_module_scope",
        "no_retraining": True,
        "no_new_inference": True,
        "no_timing_measurement": True,
        "scope": {
            "active_buckets": ["max(front_network_module_count,tail_network_module_count)<=2", "max(front_network_module_count,tail_network_module_count)==3"],
            "excluded_bucket": "max(front_network_module_count,tail_network_module_count)>3",
            "historical_four_module_data_retained_but_excluded": True,
            "all_existing_mixed_1_to_4_artifacts_untouched": True,
            "route_count": len(routes),
        },
        "data": {
            "data_dir": str(DATA_DIR),
            "manifest_status": data_manifest.get("status"),
            "manifest_rows_sha256": data_manifest.get("rows_sha256"),
            "rows_file_sha256": file_hash(DATA_DIR / "rows.jsonl"),
            "design": design_audit,
            "canonical_audit": canonical_audit,
            "total_canonical_bucket_counts": dict(total_canonical_bucket_counts),
            "total_canonical_module_count_distribution": dict(sorted(total_canonical_module_counts.items())),
            "total_canonical_test_bucket_counts": dict(total_test_bucket_counts),
        },
        "row_field_check": {
            "exact_design_fields": ["front_network_module_count", "tail_network_module_count"],
            "design_fields_present_for_all_canonical_rows": design_audit["matched_row_ids"] == canonical_audit["canonical_rows"],
            "rows_jsonl_scalar_module_fields_present": all(count == len(rows) for count in row_scalar_module_field_counts.values()),
            "rows_jsonl_scalar_module_field_counts": row_scalar_module_field_counts,
            "rows_configuration_fields_present": all(count == len(rows) for count in row_configuration_field_counts.values()),
            "rows_configuration_field_counts": row_configuration_field_counts,
            "tree_leaf_count_matches_design_fields_for_all_canonical_rows": not mismatch_examples,
            "canonical_rows_checked": canonical_audit["canonical_rows"],
        },
        "features_and_provenance": {
            "feature_columns": list(FEATURE_COLUMNS),
            "baseline_columns": list(BASELINE_COLUMNS),
            "recipe_identity_in_features": False,
            "excluded_feature_inputs": ["charge", "target_crest", "polarity", "recipe_identity", "network_tree_identity"],
            "equivalent_resistance_inputs_used": ["front_per_stage_ohm", "tail_per_stage_ohm"],
            "training_scope_disclosure": "The frozen selected models were trained on mixed canonical rows with observed network module counts 1 through 4; this report is a held-out stratification, not a 2/3-only fit.",
        },
        "prediction_source": {
            "results_path": str(RESULTS_PATH),
            "results_sha256": file_hash(RESULTS_PATH),
            "results_schema_version": results.get("schema_version"),
            "selected_test_predictions_reused": True,
            "selected_candidate_only": True,
            "model_loads": 0,
            "predict_calls": 0,
            "ood_calls": 0,
            "candidate_artifacts_retrained": False,
        },
        "routes": routes,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    _append_markdown(report)
    _append_docs(report)
    print(f"wrote {OUTPUT_PATH}")
    print(f"updated {REPORT_PATH}")
    print(f"updated {DOCS_PATH}")
    print(f"canonical_rows={canonical_audit['canonical_rows']} test_buckets={dict(total_test_bucket_counts)} canonical_buckets={dict(total_canonical_bucket_counts)}")
    print("NO_NEW_INFERENCE=true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
