from __future__ import annotations

import copy
import json
from types import SimpleNamespace

import pytest

from powernext_v3 import dataset


def test_phase_b_design_covers_all_routes_and_freezes_splits():
    rows = dataset.design_requests(target_per_route=4, learning_curve_capacity_per_route=6, seed=20261010)
    assert len(rows) == 8 * 6
    routes = {(row["domain_id"], row["mode"], row["topology_id"]) for row in rows}
    assert routes == set(dataset.ROUTES)
    assert all(row["split_frozen"] is True for row in rows)
    for group_id in {row["group_id"] for row in rows}:
        assert len({row["split"] for row in rows if row["group_id"] == group_id}) == 1
    assert all({"configuration", "setup", "setup_family_id", "group_id", "split"} <= row.keys() for row in rows)


def test_amplitude_polarity_and_capacitance_partition_share_response_group():
    original = dataset.design_requests(target_per_route=1, learning_curve_capacity_per_route=1, seed=7)[0]
    duplicate = copy.deepcopy(original)
    duplicate["row_id"] = "duplicate-amplitude"
    duplicate["configuration"]["stage_charge_V"] = original["configuration"]["stage_charge_V"] / 2.0
    duplicate["configuration"]["polarity"] = -1
    duplicate["setup"]["dut_capacitance_F"] += 10e-12
    duplicate["setup"]["divider_capacitance_F"] -= 10e-12
    grouped = dataset.assign_groups_and_splits([original, duplicate])
    assert grouped[0]["response_group_id"] == grouped[1]["response_group_id"]
    assert grouped[0]["group_id"] == grouped[1]["group_id"]
    assert grouped[0]["split"] == grouped[1]["split"]


def test_route_eligible_counts_are_unique_response_shapes():
    rows = [
        {"domain_id": "cpri_0p5uf", "mode": "LI", "topology_id": "GSHUNT_v0", "response_group_key": "same", "regression_eligible": True},
        {"domain_id": "cpri_0p5uf", "mode": "LI", "topology_id": "GSHUNT_v0", "response_group_key": "same", "regression_eligible": True},
        {"domain_id": "cpri_0p5uf", "mode": "LI", "topology_id": "GSHUNT_v0", "response_group_key": "different", "regression_eligible": True},
    ]
    assert dataset._route_eligible_counts(rows) == {"cpri_0p5uf::LI::GSHUNT_v0": 2}


def test_invalid_physics_row_is_retained_with_null_labels():
    request = dataset.design_requests(target_per_route=1, learning_curve_capacity_per_route=1, seed=8)[0]
    request["configuration"]["stages"] = 1
    row, arrays = dataset._simulate_request(request, n_points=1_000)
    assert row["status"] == "INVALID_OR_UNSUPPORTED"
    assert row["regression_eligible"] is False
    assert row["gain"] is None and row["front_us"] is None and row["tail_us"] is None
    assert arrays is None


def test_out_of_design_target_is_retained_without_labels():
    request = dataset.design_requests(target_per_route=32, learning_curve_capacity_per_route=32, seed=8)[31]
    assert request["target_crest_V"] == 5_000_000.0
    row, arrays = dataset._simulate_request(request, n_points=1_000)
    assert row["status"] == "INVALID_OR_UNSUPPORTED"
    assert row["error"]["code"] == "TARGET_OUTSIDE_PHASE_B_RANGE"
    assert row["regression_eligible"] is False
    assert row["gain"] is None and row["front_us"] is None and row["tail_us"] is None
    assert arrays is None


def test_manifest_reports_initial_and_learning_curve_capacity():
    rows = dataset.design_requests(target_per_route=2, learning_curve_capacity_per_route=3, seed=10)
    manifest = dataset._manifest_for(rows, dataset.DatasetPlan(2, 3, 10, workers=1))
    assert manifest["initial_target_per_route"] == 2
    assert manifest["learning_curve_capacity_per_route"] == 3
    assert manifest["learning_curve_stages"] == [2, 3, 3]
    assert len(manifest["routes"]) == 8
    assert manifest["observed_data_used_for_training"] is False


def test_design_covers_all_stages_independent_recipe_strata_and_targets():
    rows = dataset.design_requests(target_per_route=96, learning_curve_capacity_per_route=96, seed=20261010)
    route_rows = [row for row in rows if row["domain_id"] == "cpri_0p5uf" and row["mode"] == "LI" and row["topology_id"] == "GSHUNT_v0"]
    assert {row["configuration"]["stages"] for row in route_rows if row["case_kind"] in {"broad_log_resistance", "inverse_guided_probe"}} == set(range(2, 16))
    assert {row["front_network_module_count"] for row in route_rows} == {1, 2, 3, 4}
    assert {row["tail_network_module_count"] for row in route_rows} == {1, 2, 3, 4}
    assert min(row["target_crest_V"] for row in route_rows) <= 50_000.0
    assert max(row["target_crest_V"] for row in route_rows) >= 2_400_000.0
    assert len({(row["configuration"]["front_per_stage_ohm"], row["configuration"]["tail_per_stage_ohm"]) for row in route_rows}) >= 20


def test_network_catalog_fails_closed_without_public_api(monkeypatch):
    networks = __import__("powernext_v3.networks", fromlist=["enumerate_networks"])
    monkeypatch.setattr(networks, "enumerate_networks", lambda max_modules=4: [])
    with pytest.raises(RuntimeError, match="refusing to substitute single-resistor"):
        dataset._network_catalog()


def test_rare_anchor_and_normalized_setup_audit_are_persisted():
    rows = dataset.design_requests(target_per_route=3, learning_curve_capacity_per_route=3, seed=3)
    rare = [row for row in rows if row["mode"] == "LI" and row["case_kind"] == "rare_feasible_neighborhood"][0]
    assert rare["configuration"]["stages"] == 7
    assert rare["configuration"]["front_per_stage_ohm"] == 30.0
    assert rare["configuration"]["tail_per_stage_ohm"] == 180.0
    assert rare["rare_reference"]["source_path"].endswith("LI_rare_timing_pass_recommendation.json")
    assert rare["response_group_key"] == rare["response_group_id"]
    assert rare["setup_family_key"]
    assert rare["split_audit"]["frozen_before_labels"] is True


def test_missing_waveform_status_is_not_regression_eligible():
    result = SimpleNamespace(
        metadata={
            "numeric_status": "VALID",
            "metrics": {"gain": 0.5, "T1_s": 1e-6, "T2_s": 50e-6, "crest_magnitude_V": 1e6},
        },
        arrays={"time_s": [0.0], "voltage_V": [0.0]},
    )
    request = dataset.design_requests(target_per_route=1, learning_curve_capacity_per_route=1, seed=9)[0]
    row, _ = dataset._extract_result(result, request, 0.01)
    assert row["regression_eligible"] is False
    assert row["gain"] is None and row["front_us"] is None and row["tail_us"] is None


def test_unexpected_worker_exception_fails_manifest(monkeypatch, tmp_path):
    output = tmp_path / "unexpected"

    def explode(request, n_points):
        raise RuntimeError("unexpected worker failure")

    monkeypatch.setattr(dataset, "_simulate_request", explode)
    with pytest.raises(RuntimeError, match="unexpected worker failure"):
        dataset.generate_dataset(output, target_per_route=1, learning_curve_capacity_per_route=1, workers=1, n_points=1000, waveform_policy="none")
    manifest = __import__("json").loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "FAILED"
    assert manifest["failure"]["type"] == "RuntimeError"


def test_sparse_route_extension_reuses_frozen_design(monkeypatch, tmp_path):
    """A sparse route can extend without simulating unrelated route prefixes."""

    def fake_simulate(request, n_points):
        row = dict(request)
        row.update({
            "status": "SIMULATED",
            "regression_eligible": True,
            "gain": 0.8,
            "front_us": 1.0,
            "tail_us": 20.0,
            "crest_V": float(request["target_crest_V"]),
            "metrics": {"numeric_status": "VALID", "waveform_status": "VALID_CLEAN_FULL_IMPULSE"},
        })
        return row, None

    monkeypatch.setattr(dataset, "_simulate_request", fake_simulate)
    output = tmp_path / "sparse"
    route = "cpri_0p5uf::LI::GSHUNT_v0"
    first = dataset.generate_dataset(
        output,
        target_per_route=1,
        learning_curve_capacity_per_route=3,
        stage_per_route=1,
        workers=1,
        n_points=1000,
        waveform_policy="none",
    )
    assert first["status"] == "STAGE_COMPLETE"
    assert first["route_stage_limits"][route] == 1
    second = dataset.generate_dataset(
        output,
        target_per_route=1,
        learning_curve_capacity_per_route=3,
        route_stage_limits={route: 3},
        workers=1,
        n_points=1000,
        waveform_policy="none",
    )
    assert second["status"] == "STAGE_COMPLETE"
    assert second["route_stage_limits"][route] == 3
    assert all(limit == 1 for key, limit in second["route_stage_limits"].items() if key != route)
    rows = [json.loads(line) for line in (output / "rows.jsonl").read_text(encoding="utf-8").splitlines() if line]
    assert len(rows) == 10
    assert sum(1 for row in rows if f"{row['domain_id']}::{row['mode']}::{row['topology_id']}" == route) == 3
