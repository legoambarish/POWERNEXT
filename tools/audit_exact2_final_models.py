"""Independent actual-loader, split, selection and eight-route serving audit."""
from collections import Counter, defaultdict
import argparse
import hashlib
import json
from pathlib import Path
import tempfile

import powernext_config
from powernext_v3.application import V3Application
from powernext_v3.catalog import Catalog
from powernext_v3.training import load_rows, assign_splits, _eligible, _deduplicate_training_rows
from powernext_v3.optimizer import load_predictor

ROOT = powernext_config.ROOT
ASSET = "networks_exact2_v5"


def run(output):
    data = ROOT / "powernext/ml/data/networks_exact2_v5_aug1"
    results_path = ROOT / "powernext/ml/results" / ASSET / "results.json"
    rows, manifest = load_rows(data)
    eligible = [row for row in rows if _eligible(row)]
    canonical, splits, dedup, _ = _deduplicate_training_rows(eligible, assign_splits(eligible))
    results = json.loads(results_path.read_text(encoding="utf-8"))
    assert results["status"] == "COMPLETE"
    assert results["data_manifest"]["rows_sha256"] == manifest["rows_sha256"]
    assert results["training_dataset_scope"]["exact_modules_per_branch"] == 2
    by_route = defaultdict(list)
    for row, split in zip(canonical, splits):
        route = f"{row['domain_id']}:{row.get('mode', row.get('impulse_type'))}:{row.get('topology', row.get('topology_id'))}"
        by_route[route].append((row, split))
    expected_approaches = {(f, a) for f in ("physics_guided", "residual") for a in ("extra_trees", "hist_gradient_boosting")}
    reports = []
    with tempfile.TemporaryDirectory(prefix="powernext_exact2_actual_models_") as temp:
        app = V3Application(Path(temp))
        try:
            for route_result in results["routes"]:
                route = route_result["route_id"]
                candidate_set = {(c["formulation"], c["family"]) for c in route_result["candidates"]}
                assert candidate_set == expected_approaches, candidate_set
                assert len(route_result["candidates"]) == 4
                counts = Counter(split for _, split in by_route[route])
                for split, field in (("train", "train_rows"), ("validation", "validation_rows"), ("test", "test_rows")):
                    assert counts[split] == route_result[field]
                selected = [c for c in route_result["candidates"] if c["selected"]]
                assert len(selected) == 1
                assert selected[0]["model_id"] == results["selected_models"][route] == route_result["selected_model_id"]
                # Inspect the immutable recorded validation-only selection key.
                assert tuple(selected[0]["selection_key"]) == min(tuple(c["selection_key"]) for c in route_result["candidates"])
                row = next(row for row, split in by_route[route] if split == "test")
                domain, mode, topology = route.split(":")
                request = dict(domain_id=domain, impulse_type=mode, topology_id=topology,
                               target_crest_V=row.get("target_crest_V", 1_000_000.), setup=row["setup"],
                               min_modules=2, max_modules=2, polarity=row["configuration"].get("polarity", 1))
                model, card = load_predictor(request)
                assert card["model_id"] == selected[0]["model_id"]
                assert card["data_sha256"] == manifest["rows_sha256"]
                assert card["provenance"]["training_dataset_scope"]["exact_modules_per_branch"] == 2
                prediction = app.predict_fixed(dict(request=request, configuration=row["configuration"]))
                assert prediction["prediction"]["status"] == "ML_PREDICTION", prediction["prediction"]
                assert prediction["model"]["model_id"] == selected[0]["model_id"]
                groups = {split: len({r.get("setup_family_key", r.get("group_id")) for r, s in by_route[route] if s == split}) for split in counts}
                reports.append(dict(route=route, counts=dict(counts), setup_family_counts=groups,
                    selected_model_id=card["model_id"], selected_formulation=route_result["selected_formulation"],
                    selected_family=route_result["selected_family"],
                    held_out_metrics={key: route_result["selected_test"][key] for key in ("gain", "front_us", "tail_us", "n", "ood_count")},
                    actual_fixed_prediction=prediction["prediction"], actual_physics=prediction["physics"],
                    feature_order=card["feature_order"]))
                print(f"ACTUAL MODEL PASS {route}: {card['model_id']}", flush=True)
        finally:
            app.close()
    assert len(reports) == 8 and len(by_route) == 8
    report = dict(status="PASS", raw_rows=len(rows), eligible_rows=len(eligible), canonical_rows=len(canonical),
        dataset_id=manifest["dataset_id"], dataset_rows_sha256=manifest["rows_sha256"],
        results_sha256=hashlib.sha256(results_path.read_bytes()).hexdigest(),
        exact_two_catalog=Catalog(2, min_modules=2).info(), deduplication=dedup, routes=reports,
        limitations="Distinct shapes are correlated within setup families. Held-out rows are never fitted; retained old test rows are historical regression evidence. Fresh request-level tests remain a separate benchmark.")
    output = Path(output)
    if output.exists():
        raise FileExistsError("Preserve prior audit evidence")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    run(parser.parse_args().output)
