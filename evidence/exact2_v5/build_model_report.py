"""Build the exact-two ML report from frozen artifacts and saved predictions."""
from __future__ import annotations

import hashlib
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "powernext/ml/data/networks_exact2_v5_aug1"
RESULTS = ROOT / "powernext/ml/results/networks_exact2_v5"
REGISTRY = ROOT / "powernext/ml/registry/networks_exact2_v5"
OUT = ROOT / "evidence/exact2_v5/final_model_evaluation.json"
REPORT = ROOT / "docs/EXACT2_MODEL_REPORT.md"
LOG = ROOT / "evidence/phase_b/networks_exact2_v5_training_20261010T140441Z.log"
ACTUAL_AUDIT = ROOT / "evidence/exact2_v5/actual_model_integration.json"


def load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def compact_metrics(metrics: dict[str, Any] | None) -> dict[str, Any] | None:
    if not metrics:
        return None
    output = {k: metrics.get(k) for k in ("n", "selection_score", "ood_count", "prediction_seconds", "prediction_rows_per_second")}
    for target in ("gain", "front_us", "tail_us"):
        source = metrics.get(target) or {}
        output[target] = {k: source.get(k) for k in ("MAE", "RMSE", "P95_absolute_error", "max_absolute_error", "tolerance_normalized_MAE", "tolerance_normalized_P95")}
    return output


def compact_oracle(metrics: dict[str, Any] | None) -> dict[str, Any] | None:
    if not metrics:
        return None
    hook = metrics.get("request_level_hook") or {}
    return {
        "status": metrics.get("status"),
        "group_count": metrics.get("group_count"),
        "valid_group_count": metrics.get("valid_group_count"),
        "feasible_group_count": metrics.get("feasible_group_count"),
        "groups_coverage_status": metrics.get("groups_coverage_status"),
        "request_level_hook": {k: hook.get(k) for k in ("status", "request_count", "feasible_request_count", "missed_feasible_at_5", "feasible_hit_at_5", "mean_regret_at_25", "retention", "feasible_retention_status", "selection_usable")},
        "cases": [{k: case.get(k) for k in ("request_id", "candidate_count", "feasible_count", "first_feasible_rank", "hit_at_k", "regret_at_k", "predict_seconds", "candidates_per_second")} for case in hook.get("cases", [])],
    }


def route_key(route_id: str) -> str:
    domain, mode, topology = route_id.split(":", 2)
    return f"{domain}::{mode}::{topology}"


def fmt(value: Any, digits: int = 6) -> str:
    if value is None:
        return "—"
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return "—" if not math.isfinite(value) else f"{value:.{digits}g}"
    return str(value)


def curve(stage: dict[str, Any]) -> dict[str, Any]:
    return {"fraction": stage.get("fraction"), "training_rows": stage.get("training_rows"), "selection_score": stage.get("selection_score"), "ood_count": stage.get("ood_count")}


def test_source_metadata() -> dict[str, dict[str, Any]]:
    metadata: dict[str, dict[str, Any]] = {}
    with (DATA / "rows.jsonl").open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if row.get("split") != "test" or not row.get("regression_eligible") or row.get("row_id") is None:
                continue
            metadata[str(row["row_id"])] = {
                "segment": "supplement_test_context" if row.get("augmentation_context") == "test" else "retained_parent_test_rows",
                "mode": row.get("mode", row.get("impulse_type")),
                "configuration": row.get("configuration") or {},
                # target_crest_V is a row-level label in the frozen dataset, not
                # part of configuration. Keep it for the independent crest edge
                # error calculation below.
                "target_crest_V": row.get("target_crest_V"),
            }
    return metadata


def source_metrics(items: list[dict[str, Any]], metadata: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if not items:
        return {"n": 0}
    truth = np.asarray([item["truth"] for item in items], dtype=float)
    pred = np.asarray([item["prediction"] for item in items], dtype=float)
    mode = metadata[str(items[0]["row_id"])]["mode"]
    front_half = 0.36 if mode == "LI" else 50.0
    tail_half = 10.0 if mode == "LI" else 1500.0
    tol = np.column_stack((0.03 * np.maximum(np.abs(truth[:, 0]), 1e-12), np.full(len(items), front_half), np.full(len(items), tail_half)))
    error = np.abs(truth - pred)
    normalized = error / tol
    output = {"n": len(items), "ood_count": sum(bool(item.get("ood")) for item in items), "selection_score": float(np.mean(normalized))}
    for index, target in enumerate(("gain", "front_us", "tail_us")):
        output[target] = {"MAE": float(np.mean(error[:, index])), "RMSE": float(np.sqrt(np.mean(error[:, index] ** 2))), "P95_absolute_error": float(np.quantile(error[:, index], .95)), "max_absolute_error": float(np.max(error[:, index])), "tolerance_normalized_MAE": float(np.mean(normalized[:, index])), "tolerance_normalized_P95": float(np.quantile(normalized[:, index], .95))}
    return output


def near_boundary(items: list[dict[str, Any]], mode: str, metadata: dict[str, dict[str, Any]]) -> dict[str, Any]:
    definition = "truth within 0.25 tolerance half-width of either fixed boundary; absolute prediction-minus-truth error"
    truth = np.asarray([item["truth"] for item in items], dtype=float)
    pred = np.asarray([item["prediction"] for item in items], dtype=float)
    bounds = ((.84, 1.56), (40.0, 60.0)) if mode == "LI" else ((200.0, 300.0), (1000.0, 4000.0))
    result: dict[str, Any] = {"definition": definition}
    for index, target, (lo, hi) in ((1, "front_us", bounds[0]), (2, "tail_us", bounds[1])):
        half = (hi - lo) / 2.0
        mask = np.minimum(np.abs(truth[:, index] - lo), np.abs(truth[:, index] - hi)) <= .25 * half
        error = np.abs(pred[:, index] - truth[:, index])[mask]
        result[target] = {"n": int(error.size), "truth_near_boundary_count": int(error.size), "truth_near_boundary_fraction": float(error.size / len(items)), "MAE": None if not error.size else float(error.mean()), "RMSE": None if not error.size else float(np.sqrt(np.mean(error ** 2))), "P95_absolute_error": None if not error.size else float(np.quantile(error, .95)), "max_absolute_error": None if not error.size else float(error.max()), "tolerance_normalized_MAE": None if not error.size else float(np.mean(error / half)), "tolerance_normalized_P95": None if not error.size else float(np.quantile(error / half, .95))}
    true_crest, pred_crest, targets = [], [], []
    for item in items:
        meta = metadata[str(item["row_id"])]
        config = meta["configuration"]
        charge = config.get("stage_charge_V")
        stages = config.get("stages")
        target = item.get("target_crest_V") or meta.get("target_crest_V") or config.get("target_crest_V") or config.get("target_V")
        if charge is None or stages is None or target is None:
            continue
        try:
            charge, stages, target = abs(float(charge)), float(stages), float(target)
            if not all(math.isfinite(x) and x > 0 for x in (charge, stages, target)):
                continue
            true_crest.append(item["truth"][0] * charge * stages); pred_crest.append(item["prediction"][0] * charge * stages); targets.append(target)
        except (TypeError, ValueError):
            continue
    if true_crest:
        tc, pc, tv = np.asarray(true_crest), np.asarray(pred_crest), np.asarray(targets)
        half = .03 * tv; mask = np.minimum(np.abs(tc - .97 * tv), np.abs(tc - 1.03 * tv)) <= .25 * half
        error = np.abs(pc - tc)[mask]
        result["crest_V"] = {"n": int(error.size), "truth_near_boundary_count": int(error.size), "truth_near_boundary_fraction": float(error.size / len(items)), "MAE": None if not error.size else float(error.mean()), "RMSE": None if not error.size else float(np.sqrt(np.mean(error ** 2))), "P95_absolute_error": None if not error.size else float(np.quantile(error, .95)), "max_absolute_error": None if not error.size else float(error.max()), "tolerance_normalized_MAE": None if not error.size else float(np.mean(error / half[mask])), "tolerance_normalized_P95": None if not error.size else float(np.quantile(error / half[mask], .95))}
    else:
        result["crest_V"] = {"status": "UNAVAILABLE_ROW_SCHEMA"}
    return result


def main() -> None:
    data_manifest = load(DATA / "manifest.json")
    coverage = load(DATA / "normalized_coverage_audit.json")
    results = load(RESULTS / "results.json")
    run_manifest = load(RESULTS / "run_manifest.json")
    actual_audit = load(ACTUAL_AUDIT)
    actual_by_route = {item["route"]: item for item in actual_audit.get("routes", [])}
    oracle_dir = ROOT / "powernext/ml/data/networks_exact2_v5_validation_oracles"
    oracle_manifest = load(oracle_dir / "manifest.json")
    metadata = test_source_metadata()
    routes: list[dict[str, Any]] = []
    for route in results["routes"]:
        selected = next(candidate for candidate in route["candidates"] if candidate["selected"])
        selected_key = f"{selected['formulation']}:{selected['family']}"
        predictions = route["test_predictions"][selected_key]
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for item in predictions:
            grouped[metadata[str(item["row_id"])] ["segment"]].append(item)
        candidates = []
        for candidate in route["candidates"]:
            card_dir = REGISTRY / candidate["model_id"]
            card = load(card_dir / "card.json")
            validation = compact_metrics(candidate["validation"])
            test = compact_metrics(candidate["test"])
            candidates.append({"formulation": candidate["formulation"], "family": candidate["family"], "selected": candidate["selected"], "model_id": candidate["model_id"], "validation": validation, "test": test, "learning_curve": [curve(stage) for stage in candidate["learning_curve"]], "artifact_bytes": card.get("model_artifact_bytes"), "model_sha256": card.get("model_sha256"), "card_sha256": sha(card_dir / "card.json")})
        cov = coverage["routes"][route_key(route["route_id"])]
        selected_oracle = compact_oracle(selected["validation"].get("optimization_validation"))
        usable_families = actual_by_route.get(route["route_id"], {}).get("setup_family_counts")
        routes.append({"route_id": route["route_id"], "selection": {"formulation": route["selected_formulation"], "family": route["selected_family"], "model_id": route["selected_model_id"], "evidence": route["selection_evidence"], "policy": route["selection_policy"]}, "counts": {"raw_rows": cov["raw_rows"], "eligible_rows": cov["eligible_rows"], "canonical_rows": cov["canonical_eligible_rows"], "train": route["train_rows"], "validation": route["validation_rows"], "test": route["test_rows"], "eligible_pairs": cov["eligible_pair_count"], "unsupported_pairs": cov["unsupported_pair_count"], "setup_family_count": cov["setup_family_count"], "usable_setup_family_counts": usable_families, "supplement_setup_family_count": cov["supplement_setup_family_count"], "supplement_context_counts": cov["supplement_context_counts"]}, "candidates": candidates, "selected_validation": compact_metrics(selected["validation"]), "selected_test": compact_metrics(selected["test"]), "selected_legacy_boundary_errors": selected["test"].get("boundary_errors"), "selected_test_near_boundary_actual_error": near_boundary(predictions, route["route_id"].split(":")[1], metadata), "selected_test_source_breakdown": {name: source_metrics(items, metadata) for name, items in sorted(grouped.items())}, "oracle_validation": selected_oracle, "artifact": {"bytes": candidates[[c["model_id"] for c in candidates].index(route["selected_model_id"])]["artifact_bytes"], "model_sha256": candidates[[c["model_id"] for c in candidates].index(route["selected_model_id"])]["model_sha256"], "test_prediction_rows_per_second": selected["test"].get("prediction_rows_per_second")}})
    manifest_path = DATA / "manifest.json"
    result_path = RESULTS / "results.json"
    run_path = RESULTS / "run_manifest.json"
    audit_path = DATA / "normalized_coverage_audit.json"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    evidence = {"schema_version": "exact2_model_evaluation_v1", "status": "COMPLETE", "scope": {"contract": data_manifest.get("scope_contract"), "exact_modules_per_branch": data_manifest.get("exact_modules_per_branch"), "dataset_id": data_manifest.get("dataset_id"), "data_path": str(DATA.relative_to(ROOT)).replace("\\", "/"), "results_path": str(RESULTS.relative_to(ROOT)).replace("\\", "/"), "registry_path": str(REGISTRY.relative_to(ROOT)).replace("\\", "/")}, "dataset": {"status": data_manifest.get("status"), "raw_rows": data_manifest.get("row_count"), "eligible_rows": coverage["totals"]["eligible_rows"], "canonical_rows": coverage["totals"]["canonical_eligible_rows"], "duplicates_removed": coverage["totals"]["deduplication"]["duplicates_removed"], "rows_sha256": data_manifest.get("rows_sha256"), "design_sha256": data_manifest.get("design_sha256"), "design_file_sha256": data_manifest.get("design_file_sha256"), "design_sha256_algorithm": data_manifest.get("design_sha256_algorithm"), "manifest_sha256": sha(manifest_path), "post_write_validation": data_manifest.get("post_write_validation"), "coverage_audit_sha256": sha(audit_path), "coverage_audit_status": coverage.get("status"), "actual_model_audit_sha256": sha(ACTUAL_AUDIT), "actual_model_audit_status": actual_audit.get("status"), "all_routes_have_1764_pairs": coverage["totals"]["all_routes_have_1764_pairs"], "potential_unsupported_pair_count": coverage.get("potential_unsupported_pair_count"), "route_coverage": {key: {"raw_rows": value["raw_rows"], "eligible_rows": value["eligible_rows"], "canonical_rows": value["canonical_eligible_rows"], "eligible_pairs": value["eligible_pair_count"], "unsupported_pairs": value["unsupported_pair_count"], "setup_family_count": value["setup_family_count"], "usable_setup_family_counts": actual_by_route.get(key.replace("::", ":"), {}).get("setup_family_counts"), "supplement_context_counts": value["supplement_context_counts"]} for key, value in sorted(coverage["routes"].items())}}, "training": {"status": run_manifest.get("status"), "route_count": run_manifest.get("route_count"), "candidate_count": 32, "artifact_count": len(list(REGISTRY.glob("model_*/model.joblib"))), "results_sha256": sha(result_path), "run_manifest_sha256": sha(run_path), "training_log": str(LOG.relative_to(ROOT)).replace("\\", "/"), "training_log_sha256": sha(LOG), "load_seconds": run_manifest.get("load_seconds"), "load_rows_per_second": run_manifest.get("load_rows_per_second"), "learning_curve_fractions": [.25, .5, 1.0]}, "oracle_validation": {"path": str(oracle_dir.relative_to(ROOT)).replace("\\", "/"), "status": oracle_manifest.get("status"), "manifest_sha256": sha(oracle_dir / "manifest.json"), "requests_sha256": sha(oracle_dir / "requests.json"), "request_count": len(oracle_manifest.get("cases", [])), "per_route_selected": {route["route_id"]: route["oracle_validation"] for route in routes}}, "routes": routes, "interpretation": {"legacy_boundary_errors": "Stored boundary_errors measure predicted distance outside conformity bands; they are diagnostics, not prediction-minus-truth near-boundary errors.", "near_boundary_actual_error": "Near-boundary values use truth within 0.25 tolerance half-width of either boundary and report absolute prediction-minus-truth error.", "test_partition": "The test partition contains retained parent rows and the fresh supplemental test setup context; source-separated metrics are reported for selected models.", "fresh_optimizer_test": "The sealed seed-20261202 request design was frozen before fitting; final optimizer evaluation is post-selection and was never used to retune.", "unsupported_routes": "research_3uf LI/OSHUNT_v0 and SI/OSHUNT_v0 have no feasible validation requests; retention/regret are unavailable and regression fallback is used.", "serving_scope": "Exactly two resistor leaves in each front and tail canonical S/P branch."}}
    OUT.write_text(json.dumps(evidence, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")

    lines = ["# Exact-two v5 ML model report", "", "This report covers the active exact-two serving scope: exactly two resistor leaves in each front and tail branch, with canonical series or parallel (`S/P`) roots. All 32 candidates (four candidates across eight routes) were fit from the immutable composite Physics dataset. Candidate selection used validation partitions and the independent request oracle; held-out test predictions were generated afterward with no refit or tuning.", "", "## Scope and provenance", "", f"- Dataset: `{data_manifest.get('dataset_id')}`, {data_manifest.get('row_count')} raw rows, {coverage['totals']['eligible_rows']} eligible, {coverage['totals']['canonical_eligible_rows']} canonical; {coverage['totals']['deduplication']['duplicates_removed']} response-equivalent duplicates removed.", f"- Rows SHA256 `{data_manifest.get('rows_sha256')}`; design bytes SHA256 `{data_manifest.get('design_file_sha256')}`; design content SHA256 `{data_manifest.get('design_sha256')}` via `{data_manifest.get('design_sha256_algorithm')}`.", f"- Normalized coverage audit: `powernext/ml/data/networks_exact2_v5_aug1/normalized_coverage_audit.json`, SHA256 `{sha(audit_path)}`; all eight routes contain the 1,764 input pair grid, with lower eligible counts where Physics rejects pairs.", f"- Actual model integration audit: `evidence/exact2_v5/actual_model_integration.json`, SHA256 `{sha(ACTUAL_AUDIT)}`, status `{actual_audit.get('status')}`; its split-family counts are reported separately from raw attempt groups below.", f"- Results SHA256 `{sha(result_path)}`; run manifest SHA256 `{sha(run_path)}`; training log `evidence/phase_b/{LOG.name}`.", f"- Predictive source fingerprint: `{run_manifest['provenance']['predictive_contract_source_fingerprint']['sha256']}`; runtime Python `{run_manifest['runtime']['python']}`, NumPy `{run_manifest['runtime']['numpy']}`, scikit-learn `{run_manifest['runtime']['sklearn']}`.", "", "Canonical rows are waveform records after response-equivalent deduplication. Setup-family counts are independent grouped contexts used by the split audit; they are not interchangeable with raw rows or canonical waveform counts. The composite retains parent rows and adds three train contexts plus independent validation and test setup contexts generated by Physics. The parent test rows were historical evidence; source-separated test metrics below identify them from the fresh supplemental test context.", "", "## Dataset coverage", "", "| Route | Raw | Eligible | Canonical | Eligible pairs / 1,764 | Unsupported pairs | Train / validation / test | Raw attempt groups | Usable setup families (train/val/test) |", "|---|---:|---:|---:|---:|---:|---:|---:|---|"]
    for key, value in sorted(coverage["routes"].items()):
        split = value["canonical_eligible_split_counts"]
        route_actual = actual_by_route.get(key.replace("::", ":"), {})
        usable = route_actual.get("setup_family_counts") or {}
        usable_text = f"{usable.get('train', '—')} / {usable.get('validation', '—')} / {usable.get('test', '—')}"
        lines.append(f"| {key.replace('::', ' ')} | {value['raw_rows']} | {value['eligible_rows']} | {value['canonical_eligible_rows']} | {value['eligible_pair_count']} | {value['unsupported_pair_count']} | {split['train']} / {split['validation']} / {split['test']} | {value['setup_family_count']} ({value['supplement_setup_family_count']} supplemental) | {usable_text} |")
    lines += ["", "Unsupported Physics rows remain explicit negative evidence; they do not receive fabricated targets.", "", "## Selected routes and held-out test summary", "", "| Route | Selected | Model | Train / val / test | Validation norm | Test norm | Test OOD | Artifact KiB | Test rows/s | Oracle retention |", "|---|---|---|---:|---:|---:|---:|---:|---:|---|"]
    for route in routes:
        selected = route["selection"]; v = route["selected_validation"]; t = route["selected_test"]; ev = selected["evidence"]; count = route["counts"]; retention = "available" if ev.get("feasible_retention_status") == "AVAILABLE" else "unavailable"
        lines.append(f"| {route['route_id']} | {selected['formulation']}/{selected['family']} | `{selected['model_id']}` | {count['train']} / {count['validation']} / {count['test']} | {fmt(v.get('selection_score'))} | {fmt(t.get('selection_score'))} | {t.get('ood_count')} | {fmt(route['artifact']['bytes'] / 1024, 5)} | {fmt(route['artifact']['test_prediction_rows_per_second'])} | {retention} |")
    lines += ["", "Throughput is model prediction throughput from the sequential evaluator, not a full search-policy benchmark. OOD is a disclosure signal, not a hard serving gate.", "", "## All four candidates by route", "", "| Route | Candidate | Selected | Model | Validation norm | Test norm | Gain test MAE / P95 | Front test MAE / P95 | Tail test MAE / P95 | Test OOD | Artifact KiB | Test rows/s |", "|---|---|:---:|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for route in routes:
        for candidate in route["candidates"]:
            t = candidate["test"]; lines.append(f"| {route['route_id']} | {candidate['formulation']}/{candidate['family']} | {'yes' if candidate['selected'] else ''} | `{candidate['model_id']}` | {fmt(candidate['validation']['selection_score'])} | {fmt(t['selection_score'])} | {fmt(t['gain']['MAE'])} / {fmt(t['gain']['P95_absolute_error'])} | {fmt(t['front_us']['MAE'])} / {fmt(t['front_us']['P95_absolute_error'])} | {fmt(t['tail_us']['MAE'])} / {fmt(t['tail_us']['P95_absolute_error'])} | {t['ood_count']} | {fmt(candidate['artifact_bytes'] / 1024, 5)} | {fmt(t.get('prediction_rows_per_second'))} |")
    lines += ["", "## Selected target errors", "", "Native units are used below. Normalized values divide by 3% of gain, the LI/SI front half-width, or the LI/SI tail half-width.", "", "| Route | Target | n | MAE | RMSE | P95 | Max | Norm MAE | Norm P95 |", "|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for route in routes:
        for target in ("gain", "front_us", "tail_us"):
            metric = route["selected_test"][target]; lines.append(f"| {route['route_id']} | {target} | {route['selected_test']['n']} | {fmt(metric['MAE'])} | {fmt(metric['RMSE'])} | {fmt(metric['P95_absolute_error'])} | {fmt(metric['max_absolute_error'])} | {fmt(metric['tolerance_normalized_MAE'])} | {fmt(metric['tolerance_normalized_P95'])} |")
    lines += ["", "## Fresh supplemental versus retained parent test rows", "", "The selected-model test predictions are separated by immutable row provenance.", "", "| Route | Test segment | n | Gain MAE | Front MAE | Tail MAE | Norm score | OOD |", "|---|---|---:|---:|---:|---:|---:|---:|"]
    for route in routes:
        for segment, metrics in sorted(route["selected_test_source_breakdown"].items()):
            lines.append(f"| {route['route_id']} | {segment} | {metrics['n']} | {fmt(metrics['gain']['MAE'])} | {fmt(metrics['front_us']['MAE'])} | {fmt(metrics['tail_us']['MAE'])} | {fmt(metrics['selection_score'])} | {metrics['ood_count']} |")
    lines += ["", "## Actual near-boundary errors", "", "This metric selects truth within 25% of a tolerance half-width from either fixed boundary and reports absolute prediction-minus-truth error. It is separate from stored `boundary_errors`, which measure predicted distance outside the conformity band and remain diagnostics only.", "", "| Route | Target | n | MAE | RMSE | P95 | Max | Norm P95 |", "|---|---|---:|---:|---:|---:|---:|---:|"]
    for route in routes:
        near = route["selected_test_near_boundary_actual_error"]
        for target in ("front_us", "tail_us", "crest_V"):
            metric = near.get(target, {})
            if metric.get("status"):
                lines.append(f"| {route['route_id']} | {target} | — | — | — | — | — | — |")
            else:
                lines.append(f"| {route['route_id']} | {target} | {metric.get('n')} | {fmt(metric.get('MAE'))} | {fmt(metric.get('RMSE'))} | {fmt(metric.get('P95_absolute_error'))} | {fmt(metric.get('max_absolute_error'))} | {fmt(metric.get('tolerance_normalized_P95'))} |")
    lines += ["", "## Validation oracle and learning curves", "", "The validation oracle covers two complete 5,292-candidate requests per route. Routes with no feasible request use the declared regression-validation fallback; they do not claim feasible-retention evidence.", "", "| Route | Requests | Feasible requests | Missed feasible @5 | Mean regret @25 | Basis |", "|---|---:|---:|---:|---:|---|"]
    for route in routes:
        ev = route["selection"]["evidence"]; lines.append(f"| {route['route_id']} | {ev.get('request_count')} | {ev.get('feasible_request_count')} | {ev.get('missed_feasible_at_5') if ev.get('feasible_request_count') else '—'} | {fmt(ev.get('mean_regret_at_25'))} | {ev.get('selection_basis')} |")
    lines += ["", "| Route | Candidate | 25% | 50% | 100% |", "|---|---|---:|---:|---:|"]
    for route in routes:
        for candidate in route["candidates"]:
            curve_scores = {str(stage["fraction"]): stage["selection_score"] for stage in candidate["learning_curve"]}; lines.append(f"| {route['route_id']} | {candidate['formulation']}/{candidate['family']} | {fmt(curve_scores.get('0.25'))} | {fmt(curve_scores.get('0.5'))} | {fmt(curve_scores.get('1.0'))} |")
    lines += ["", "## Limits", "", "- The active scope is exactly two resistor leaves per front and tail S/P branch. Historical one-through-four-module artifacts remain outside this model set.", "- The seed-20261202 optimizer request design was frozen before fitting; any final optimizer evaluation is post-selection and was never used to retune these models.", "- Hardware mounting, pulse ratings, auxiliary topology state, and production feasibility are outside this numerical report.", "", f"Machine-readable evidence: `evidence/exact2_v5/final_model_evaluation.json`.", ""]
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"status": "COMPLETE", "routes": len(routes), "candidates": sum(len(route['candidates']) for route in routes), "artifact_count": len(list(REGISTRY.glob('model_*/model.joblib')),), "report": str(REPORT), "evidence": str(OUT)}, sort_keys=True))


if __name__ == "__main__":
    main()
