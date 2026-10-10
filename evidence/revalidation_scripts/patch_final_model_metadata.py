"""Add aggregate schema-audit metadata to the completed final report.

This helper intentionally reads only immutable JSON artifacts and regenerates
the Markdown view. It never loads a model or performs inference.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
REPORT_PATH = ROOT / "evidence" / "phase_b" / "final_model_evaluation.json"
RESULTS_PATH = ROOT / "powernext" / "ml" / "results" / "networks_v3" / "results.json"
MARKDOWN_PATH = ROOT / "docs" / "PHASE_B_MODEL_REPORT.md"

STRICT_TOP_LEVEL = frozenset(
    {
        "status",
        "request_count",
        "feasible_request_count",
        "missed_feasible_at_5",
        "feasible_hit_at_5",
        "mean_regret_at_25",
        "retention",
        "cases",
    }
)
STRICT_CASE_LEVEL = frozenset(
    {
        "request_id",
        "candidate_count",
        "feasible_count",
        "first_feasible_rank",
        "hit_at_k",
        "regret_at_k",
        "predict_seconds",
        "candidates_per_second",
    }
)
TIMING_KEYS = frozenset({"predict_seconds", "candidates_per_second"})
WRAPPER_KEYS = frozenset(
    {
        "selection_usable",
        "feasible_retention_status",
        "selection_fallback",
        "selection_fallback_reason",
        "request_level_oracle_status",
        "selection_basis",
    }
)


def _schema_difference(old: dict, new_top: frozenset[str], new_case: frozenset[str]) -> dict:
    old_top = set(old)
    old_case = {
        key
        for case in old.get("cases", [])
        if isinstance(case, dict)
        for key in case
    }
    return {
        "training_record_top_level_only": sorted(old_top - new_top),
        "strict_v2_top_level_only": sorted(new_top - old_top),
        "training_record_case_level_only": sorted(old_case - new_case),
        "strict_v2_case_level_only": sorted(new_case - old_case),
        "timing_keys_excluded_from_scientific_comparison": sorted(TIMING_KEYS),
        "wrapper_annotation_keys_excluded_from_scientific_comparison": sorted(WRAPPER_KEYS),
    }


def main() -> int:
    report = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
    results = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    result_by_route = {
        route["route_id"]: {candidate["model_id"]: candidate for candidate in route["candidates"]}
        for route in results["routes"]
    }
    differences = []
    for route in report["routes"]:
        candidates = result_by_route[route["route_id"]]
        for candidate in route["candidates"]:
            old = (
                candidates[candidate["model_id"]]
                .get("validation", {})
                .get("optimization_validation", {})
                .get("request_level_hook")
                or {}
            )
            difference = _schema_difference(old, STRICT_TOP_LEVEL, STRICT_CASE_LEVEL)
            candidate["oracle_schema_difference"] = difference
            differences.append(difference)

    top_only = sorted({key for item in differences for key in item["training_record_top_level_only"]})
    strict_top_only = sorted({key for item in differences for key in item["strict_v2_top_level_only"]})
    case_only = sorted({key for item in differences for key in item["training_record_case_level_only"]})
    strict_case_only = sorted({key for item in differences for key in item["strict_v2_case_level_only"]})
    raw_mismatch = bool(top_only or strict_top_only or case_only or strict_case_only)
    oracle = report["oracle_equivalence"]
    oracle.update(
        {
            "comparison_scope": "compact OracleValidation scientific fields; excludes measured prediction timing and documented training-wrapper annotations",
            "excluded_timing_keys": sorted(TIMING_KEYS),
            "excluded_wrapper_annotation_keys": sorted(WRAPPER_KEYS),
            "schema_audit": {
                "training_record_top_level_only_union": top_only,
                "strict_v2_top_level_only_union": strict_top_only,
                "training_record_case_level_only_union": case_only,
                "strict_v2_case_level_only_union": strict_case_only,
            },
            "raw_initial_comparison": {
                "observed_mismatch": raw_mismatch,
                "first_mismatch": ":key_set" if raw_mismatch else None,
                "reason": "The immutable training record wraps OracleValidation with selection annotations; raw top-level equality therefore fails before the documented scientific comparison scope is applied.",
                "comparison_after_documented_exclusions": bool(oracle["all_candidate_scientific_fields_match"]),
                "reconstructed_from_immutable_results": True,
                "results_sha256": report["provenance"]["results_sha256"],
            },
        }
    )
    report["learning_curve_interpretation"] = {
        "curve_100_is_same_serving_artifact": False,
        "reason": "The staged 100% learning-curve fit and the frozen full-capacity train fit use the same canonical partition but may receive different row order; final serving-artifact validation metrics are authoritative.",
    }
    REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")

    helper_path = Path(__file__).with_name("phase_b_final_ml_evaluation.py")
    spec = importlib.util.spec_from_file_location("phase_b_final_ml_evaluation", helper_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load report renderer")
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    MARKDOWN_PATH.write_text(helper._markdown(report), encoding="utf-8")
    print("patched aggregate schema audit and Markdown report")
    print(f"raw_schema_mismatch={raw_mismatch}")
    print(f"scientific_equivalence={oracle['all_candidate_scientific_fields_match']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
