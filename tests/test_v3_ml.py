"""Small explicit Phase B v3 fixtures; these are API tests, not acceptance runs."""
from __future__ import annotations

import json

import numpy as np
import pytest

from powernext_v3.features import BASELINE_COLUMNS, FEATURE_COLUMNS, feature_matrix, feature_rows
from powernext_v3.models import NetworkModel, make_candidates
from powernext_v3.registry import load_model, register_model
from powernext_v3.training import _deduplicate_training_rows, _digest, _pairwise_rank_accuracy, _selection_key, _training_dataset_scope, _validate_exact_two_rows, _validate_training_scope, assign_splits, load_rows, optimization_validation_metrics, train, write_rows_jsonl


SETUP = {
    "dut_capacitance_F": 850e-12,
    "divider_capacitance_F": 500e-12,
    "stray_capacitance_F": 150e-12,
    "loop_inductance_H": 18.5e-6,
    "basic_coverage_assumption": "ADDITIONAL_DISJOINT",
    "loop_resistance_ohm": 0.0,
    "load_resistance_ohm": None,
}


def _fixture_rows(count: int = 15):
    rows = []
    for i in range(count):
        stages = 5 + i % 6
        front = 30.0 + 16.0 * ((i % 5) / 4.0)
        tail = 180.0 + 340.0 * ((i % 4) / 3.0)
        x = feature_matrix(stages, front, tail, SETUP, "cpri_0p5uf", "LI", "GSHUNT_v0")[0]
        baseline = x[-3:]
        scale = 1.0 + 0.002 * (i - count / 2)
        rows.append(
            {
                "row_id": f"fixture_{i:03d}",
                "domain_id": "cpri_0p5uf",
                "mode": "LI",
                "topology": "GSHUNT_v0",
                "features": dict(zip(FEATURE_COLUMNS, x.tolist())),
                "gain": float(baseline[0] * scale),
                "front_us": float(baseline[1] * (1.0 + 0.003 * (i % 2))),
                "tail_us": float(baseline[2] * (1.0 - 0.002 * (i % 3))),
                "split": "train" if i < 9 else ("validation" if i < 12 else "test"),
                "group_id": f"request_{i:03d}",
                "eligible": True,
                "status": "VALID",
                "configuration": {
                    "impulse_type": "LI",
                    "stages": stages,
                    "stage_charge_V": 100000.0,
                    "front_per_stage_ohm": front,
                    "tail_per_stage_ohm": tail,
                    "topology_id": "GSHUNT_v0",
                    "polarity": 1,
                },
                "setup": SETUP,
                "target_crest_V": 0.9 * stages * 100000.0,
            }
        )
    return rows


def _exact_two_scope_manifest():
    scope = {
        "field_front": "front_network_module_count",
        "field_tail": "tail_network_module_count",
        "exact_modules_per_branch": 2,
        "rule": "front_network_module_count == 2 and tail_network_module_count == 2",
        "scope_contract": "EXACT_MODULES_PER_BRANCH_V5",
    }
    return {
        "dataset_id": "fixture_exact2",
        "scope_contract": "EXACT_MODULES_PER_BRANCH_V5",
        "exact_modules_per_branch": 2,
        "scope_filter": scope,
        "scope_filter_sha256": _digest(scope),
        "parent_dataset_id": "parent",
        "parent_manifest_sha256": "manifest-hash",
        "parent_rows_sha256": "rows-hash",
        "parent_design_sha256": "design-hash",
        "parent_design_file_sha256": "design-file-hash",
    }


def _exact_two_row():
    row = _fixture_rows(1)[0]
    row["configuration"]["front_network"] = {"op": "S", "children": [{"op": "R", "ohm": 30}, {"op": "R", "ohm": 46}]}
    row["configuration"]["tail_network"] = {"op": "P", "children": [{"op": "R", "ohm": 180}, {"op": "R", "ohm": 520}]}
    row["front_network_module_count"] = 2
    row["tail_network_module_count"] = 2
    return row


def test_exact_two_scope_rejects_forged_less_than_or_equal_scope():
    manifest = _exact_two_scope_manifest()
    manifest["scope_filter"] = dict(manifest["scope_filter"], rule="max(front_network_module_count, tail_network_module_count) <= 2")
    manifest["scope_filter_sha256"] = _digest(manifest["scope_filter"])
    with pytest.raises(ValueError, match="scope rule"):
        _training_dataset_scope(manifest)


def test_exact_two_row_gate_checks_trees_and_declared_counts():
    manifest = _exact_two_scope_manifest()
    row = _exact_two_row()
    _validate_exact_two_rows([row], manifest)
    row["configuration"]["front_network"] = {"op": "R", "ohm": 30}
    with pytest.raises(ValueError, match="front_network must be an S/P tree"):
        _validate_exact_two_rows([row], manifest)
    row = _exact_two_row()
    row["tail_network_module_count"] = 1
    with pytest.raises(ValueError, match="tail_network_module_count"):
        _validate_exact_two_rows([row], manifest)


def test_feature_schema_excludes_request_and_recipe_identity():
    forbidden = {"stage_charge_V", "charge", "target", "target_crest_V", "polarity", "recipe", "recipe_id"}
    assert not any(any(token in name.lower() for token in forbidden) for name in FEATURE_COLUMNS)
    x = feature_matrix([5, 6], [30, 46], [180, 520], SETUP, "cpri_0p5uf", "LI", "GSHUNT_v0")
    assert x.shape == (2, len(FEATURE_COLUMNS))
    assert tuple(FEATURE_COLUMNS[-3:]) == BASELINE_COLUMNS


def test_vectorized_baseline_matches_legacy_scalar_oracle():
    from physics_engine.analytic import double_exponential_metrics, rates

    x = feature_matrix(9, 30.0, 180.0, SETUP, "cpri_0p5uf", "LI", "GSHUNT_v0")[0]
    cg, cl, rf, rt = x[10] * 1e-9, x[11] * 1e-9, x[12], x[13]
    alpha, beta = rates(cg, cl, rf, rt, "GSHUNT_v0")
    scalar = double_exponential_metrics(alpha, beta, "LI")
    expected = np.array([scalar["coefficient_to_crest"] / (rf * cl * (beta - alpha)), scalar["T1_s"] * 1e6, scalar["T2_s"] * 1e6])
    np.testing.assert_allclose(x[-3:], expected, rtol=2e-10, atol=2e-10)


@pytest.mark.parametrize("formulation", ["physics_guided", "residual"])
@pytest.mark.parametrize("family", ["extra_trees", "hist_gradient_boosting"])
def test_four_candidate_models_predict_and_use_continuous_ood(formulation, family):
    rows = _fixture_rows()
    model = NetworkModel("cpri_0p5uf", "LI", "GSHUNT_v0", formulation, family).fit(rows[:10])
    query = feature_matrix([7, 8], [38.0, 40.0], [280.0, 350.0], SETUP, "cpri_0p5uf", "LI", "GSHUNT_v0")
    prediction = model.predict(query)
    assert prediction.shape == (2, 3)
    assert np.isfinite(prediction).all() and (prediction > 0).all()
    # 38 ohm is unseen as an exact catalog value, but it lies inside the
    # continuous support and should not trigger an all-unseen-value rejection.
    assert not bool(model.ood(query).all())
    with pytest.raises(ValueError, match="route"):
        NetworkModel("research_3uf", "LI", "GSHUNT_v0", formulation, family).fit(rows[:10])


def test_registry_verifies_artifact_hash(tmp_path):
    rows = _fixture_rows()
    model = NetworkModel("cpri_0p5uf", "LI", "GSHUNT_v0", "residual", "extra_trees").fit(rows[:10])
    card = register_model(model, provenance={"fixture": True}, root=tmp_path / "registry", training_rows=10)
    folder = tmp_path / "registry" / card["model_id"]
    loaded, loaded_card = load_model(folder, expected_provenance={"fixture": True})
    assert loaded_card["model_sha256"] == card["model_sha256"]
    np.testing.assert_allclose(loaded.predict(np.asarray([[rows[0]["features"][c] for c in FEATURE_COLUMNS]])), model.predict(np.asarray([[rows[0]["features"][c] for c in FEATURE_COLUMNS]])))
    with (folder / "model.joblib").open("ab") as stream:
        stream.write(b"tamper")
    with pytest.raises(ValueError, match="hash"):
        load_model(folder)


def test_request_oracle_hook_receives_fitted_model_and_validation_rows():
    rows = _fixture_rows()
    model = NetworkModel("cpri_0p5uf", "LI", "GSHUNT_v0", "residual", "extra_trees").fit(rows[:9])
    features = np.asarray([[row["features"][column] for column in model.columns] for row in rows[9:12]], dtype=float)
    truth = np.asarray([[row[name] for name in ("gain", "front_us", "tail_us")] for row in rows[9:12]], dtype=float)
    seen = []

    def oracle(fitted_model, validation_rows):
        seen.append((fitted_model.route_id, len(validation_rows)))
        return {"status": "COMPLETE", "missed_feasible_at_5": 0, "mean_regret_at_25": 0.25, "request_count": 1, "feasible_request_count": 1}

    report = optimization_validation_metrics(rows[9:12], truth, model.predict(features), oracle, model=model)
    assert seen == [("cpri_0p5uf:LI:GSHUNT_v0", 3)]
    assert report["request_level_hook"]["status"] == "COMPLETE"
    assert report["request_level_hook"]["feasible_retention_status"] == "AVAILABLE"
    assert report["request_level_hook"]["selection_usable"] is True
    assert report["secondary_gain_order_proxy"]["status"] == "UNAVAILABLE_NO_COMPARABLE_REQUEST_PAIRS"


def test_request_oracle_without_true_feasible_requests_is_explicitly_unavailable():
    rows = _fixture_rows()
    model = NetworkModel("cpri_0p5uf", "LI", "GSHUNT_v0", "residual", "extra_trees").fit(rows[:9])
    features = np.asarray([[row["features"][column] for column in model.columns] for row in rows[9:12]], dtype=float)
    truth = np.asarray([[row[name] for name in ("gain", "front_us", "tail_us")] for row in rows[9:12]], dtype=float)

    def oracle(fitted_model, validation_rows):
        assert fitted_model.route_id == "cpri_0p5uf:LI:GSHUNT_v0"
        assert len(validation_rows) == 3
        return {
            "status": "COMPLETE_INDEPENDENT_PHYSICS_ORACLE_VALIDATION",
            "request_count": 2,
            "feasible_request_count": 0,
            "missed_feasible_at_5": 0,
            "feasible_hit_at_5": None,
            "mean_regret_at_25": None,
        }

    report = optimization_validation_metrics(rows[9:12], truth, model.predict(features), oracle, model=model)
    hook = report["request_level_hook"]
    assert hook["feasible_retention_status"] == "UNAVAILABLE_NO_TRUE_FEASIBLE_REQUESTS"
    assert hook["selection_usable"] is False
    assert hook["selection_fallback"] == "REGRESSION_VALIDATION"


@pytest.mark.parametrize(
    "identity_rows,identity_name",
    [
        ([{"group_id": "g", "split": "train"}, {"group_id": "g", "split": "validation"}], "group_id"),
        ([{"group_id": "a", "response_group_id": "shape", "split": "train"}, {"group_id": "b", "response_group_id": "shape", "split": "test"}], "response_group_id"),
        ([{"group_id": "a", "response_group_key": "shape", "split": "train"}, {"group_id": "b", "response_group_key": "shape", "split": "test"}], "response_group_key"),
        ([{"group_id": "a", "setup_family_id": "setup", "split": "train"}, {"group_id": "b", "setup_family_id": "setup", "split": "test"}], "setup_family_id"),
        ([{"group_id": "a", "setup_family_key": "setup", "split": "train"}, {"group_id": "b", "setup_family_key": "setup", "split": "test"}], "setup_family_key"),
    ],
)
def test_explicit_split_fails_closed_on_identity_crossing(identity_rows, identity_name):
    with pytest.raises(ValueError, match=identity_name):
        assign_splits(identity_rows)


def test_explicit_split_fails_closed_on_partial_labels():
    with pytest.raises(ValueError, match="present for every row"):
        assign_splits([{"group_id": "a", "split": "train"}, {"group_id": "b"}])


def test_computed_splits_keep_connected_response_and_setup_identities_together():
    rows = [
        {"row_id": "a", "group_id": "a", "response_group_id": "shape", "setup_family_id": "setup"},
        {"row_id": "b", "group_id": "b", "response_group_id": "shape", "setup_family_id": "other"},
        {"row_id": "c", "group_id": "c", "response_group_id": "other-shape", "setup_family_id": "other"},
    ]
    splits = assign_splits(rows)
    assert splits[0] == splits[1] == splits[2]


def test_repeated_response_shapes_collapse_to_canonical_rows_with_audit():
    rows = _fixture_rows(4)
    rows[0]["response_group_key"] = "shape-a"
    rows[1]["response_group_key"] = "shape-a"
    rows[1]["gain"] = rows[0]["gain"]
    rows[1]["front_us"] = rows[0]["front_us"]
    rows[1]["tail_us"] = rows[0]["tail_us"]
    assignments = ["train", "train", "validation", "test"]
    canonical, canonical_splits, report, audit = _deduplicate_training_rows(rows, assignments)
    assert len(canonical) == 3
    assert canonical_splits == ["train", "validation", "test"]
    assert report["duplicates_removed"] == 1
    assert audit[1]["deduplicated"] is True
    assert audit[1]["canonical_row_id"] == rows[0]["row_id"]


def test_repeated_response_shapes_with_inconsistent_labels_fail_closed():
    rows = _fixture_rows(3)
    rows[0]["response_group_key"] = rows[1]["response_group_key"] = "shape-a"
    with pytest.raises(ValueError, match="Inconsistent duplicate labels"):
        _deduplicate_training_rows(rows, ["train", "train", "validation"])


def test_secondary_gain_proxy_excludes_ties_and_reports_bounded_scope():
    rows = [{"group_id": "request"} for _ in range(5)]
    truth = np.column_stack(([1.0, 2.0, 3.0, 3.0, 5.0], np.zeros((5, 2))))
    pred = np.column_stack(([1.0, 4.0, 2.0, 2.0, 5.0], np.zeros((5, 2))))
    report = _pairwise_rank_accuracy(rows, truth, pred)
    assert report["algorithm"] == "fenwick_exact_non_tied_pairs"
    assert report["scope"] == "within_request_group"
    assert report["pair_count"] == 9
    assert report["retention"] == pytest.approx(7 / 9)


def test_external_oracle_miss_and_regret_precede_waveform_error():
    def candidate(missed, regret, score):
        return {
            "fit_seconds": 1.0,
            "validation": {
                "selection_score": score,
                "prediction_rows_per_second": 100.0,
                "optimization_validation": {
                    "request_level_hook": {
                        "status": "COMPLETE_INDEPENDENT_PHYSICS_ORACLE_VALIDATION",
                        "request_count": 2,
                        "feasible_request_count": 2,
                        "missed_feasible_at_5": missed,
                        "mean_regret_at_25": regret,
                    }
                },
            },
        }

    assert _selection_key(candidate(0, 3.0, 0.1)) < _selection_key(candidate(1, 0.0, 0.0))
    unavailable = candidate(0, 0.0, 0.0)
    unavailable["validation"]["optimization_validation"]["request_level_hook"]["status"] = "UNAVAILABLE_NO_ROUTE_ORACLES"
    assert _selection_key(unavailable)[0] >= 1.0e9


def test_fixture_training_selects_validation_only_and_writes_route_artifact(tmp_path):
    rows = _fixture_rows()
    data_dir = tmp_path / "data"
    write_rows_jsonl(rows, data_dir, fixture=True)
    result_dir = tmp_path / "results"
    registry_dir = tmp_path / "registry"
    result = train(data_dir, result_dir, registry_dir=registry_dir)
    complete = [route for route in result["routes"] if route["status"] == "COMPLETE"]
    assert len(complete) == 1
    route = complete[0]
    assert len(route["candidates"]) == 4
    assert sum(candidate["selected"] for candidate in route["candidates"]) == 1
    assert route["selected_test"]["n"] == 3
    assert result["status"] == "COMPLETE_FIXTURE"
    assert result["scope"]["kind"] == "EXPLICIT_TEST_FIXTURE"
    for stage_index in range(3):
        row_hashes = {candidate["learning_curve"][stage_index]["training_row_ids_sha256"] for candidate in route["candidates"]}
        group_hashes = {candidate["learning_curve"][stage_index]["training_group_ids_sha256"] for candidate in route["candidates"]}
        assert len(row_hashes) == 1
        assert len(group_hashes) == 1
    manifest = json.loads((result_dir / "run_manifest.json").read_text(encoding="utf-8"))
    assert manifest["data_sha256"] == result["data_manifest"]["rows_sha256"]
    assert (registry_dir / route["selected_model_id"] / "card.json").is_file()


def test_production_scope_requires_all_routes_and_three_partitions():
    one_route = {
        ("cpri_0p5uf", "LI", "GSHUNT_v0"): [
            {"split": "train"},
            {"split": "validation"},
            {"split": "test"},
        ]
    }
    with pytest.raises(ValueError, match="exactly eight routes"):
        _validate_training_scope(one_route, fixture=False)


def test_fixture_scope_allows_scoped_route():
    route = {("cpri_0p5uf", "LI", "GSHUNT_v0"): [{"split": "train"}]}
    scope = _validate_training_scope(route, fixture=True)
    assert scope["kind"] == "EXPLICIT_TEST_FIXTURE"
    assert scope["actual_route_count"] == 1


def test_load_rows_requires_completed_manifest_and_row_hash(tmp_path):
    data_dir = tmp_path / "raw"
    data_dir.mkdir()
    (data_dir / "rows.jsonl").write_text(json.dumps({"row_id": "x"}) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="manifest.json is required"):
        load_rows(data_dir)


@pytest.mark.parametrize("status", ["STAGE_COMPLETE", "FULL_DESIGN_COMPLETE"])
def test_load_rows_accepts_data_worker_completion_statuses_for_explicit_fixture(tmp_path, status):
    data_dir = tmp_path / "data"
    write_rows_jsonl(_fixture_rows(3), data_dir, fixture=True)
    manifest_path = data_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["status"] = status
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    rows, loaded = load_rows(data_dir)
    assert len(rows) == 3
    assert loaded["status"] == status


def test_load_rows_rejects_in_progress_manifest(tmp_path):
    data_dir = tmp_path / "data"
    write_rows_jsonl(_fixture_rows(3), data_dir, fixture=True)
    manifest_path = data_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["status"] = "IN_PROGRESS"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="not complete"):
        load_rows(data_dir)
