"""Focused contract tests for the independent v3 application facade."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import threading
import time
from urllib.request import Request, urlopen

import pytest

from powernext_v3.application import V3Application


def request(**updates):
    value = V3Application.default_request()
    value.update(
        request_id="TEST_NETWORK_APPLICATION",
        max_modules=1,
        stages=[2],
        search_mode="complete",
        priority="complete_physics",
        max_ml_candidates=100,
        max_physics_evaluations=100,
        budget_seconds=30.0,
        alternatives=2,
    )
    value.update(updates)
    return value


def wait_for(app: V3Application, job_id: str, timeout: float = 60.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        bundle = app.get_run(job_id)
        if bundle["run"]["status"] not in {"QUEUED", "RUNNING"}:
            return bundle
        time.sleep(0.05)
    raise AssertionError(app.get_run(job_id))


def test_metadata_and_validation_expose_declared_catalog(tmp_path):
    app = V3Application(tmp_path / "v3")
    try:
        metadata = app.metadata()
        assert metadata["schema_version"] == "network_application_v3"
        assert metadata["offline"] is True
        assert metadata["hardware_control"] is False
        assert metadata["components_ohm"] == [30, 46, 180, 520, 3700, 5000]
        checked = app.validate(request())
        assert checked["valid"] is True
        assert checked["request"]["stages"] == [2]
        assert checked["catalog"]["theoretical_recipe_configurations"] == 36
        assert checked["catalog"]["distinct_response_candidates"] == 36
        assert checked["model"]["fallback"].startswith("PHYSICS_L0_BASELINE")
    finally:
        app.close()


def test_search_job_publishes_only_complete_result_and_waveform_integrity(tmp_path):
    app = V3Application(tmp_path / "v3")
    try:
        state = app.start_search(request())
        bundle = wait_for(app, state["job_id"])
        assert bundle["run"]["status"] == "COMPLETED"
        result = bundle["result"]
        assert result["schema_version"] == "network_result_v3"
        assert result["search"]["catalog_complete"] is True
        assert result["search"]["theoretical_recipe_configurations"] == 36
        assert result["search"]["physics_evaluated_count"] == 36
        assert bundle["run"]["result_sha256"] == hashlib.sha256(
            (tmp_path / "v3" / "jobs" / state["job_id"] / "artifact" / "result.json").read_bytes()
        ).hexdigest()
        row = next(row for row in result["candidates"] if row.get("waveform_reference"))
        waveform = app.waveform(state["job_id"], row["candidate_id"])
        assert waveform["candidate_id"] == row["candidate_id"]
        assert len(waveform["time_s"]) == len(waveform["voltage_V"])
        assert waveform["sha256"] == row["waveform_reference"]["sha256"]
    finally:
        app.close()


def test_budget_result_is_explicitly_partial_and_not_promoted_as_complete(tmp_path):
    app = V3Application(tmp_path / "v3")
    try:
        state = app.start_search(request(max_modules=2, search_mode="adaptive", budget_seconds=0.1, max_physics_evaluations=1))
        bundle = wait_for(app, state["job_id"])
        assert bundle["run"]["status"] == "COMPLETED"
        assert bundle["result"] is not None
        assert bundle["result"]["search"]["catalog_complete"] is False
        assert bundle["result"]["search"]["physics_evaluated_count"] <= 1
        assert bundle["result"]["status"] in {
            "NO_COMPLIANT_CONFIGURATION_YET",
            "VERIFIED_COMPLIANT",
        }
    finally:
        app.close()


def test_only_one_v3_search_job_can_be_active(tmp_path):
    app = V3Application(tmp_path / "v3")
    try:
        first = app.start_search(request(max_modules=2, search_mode="adaptive", budget_seconds=30, max_physics_evaluations=1))
        with pytest.raises(ValueError, match="already active"):
            app.start_search(request(max_modules=2, search_mode="adaptive", budget_seconds=30, max_physics_evaluations=1))
        wait_for(app, first["job_id"])
    finally:
        app.close()


def test_interrupted_queued_job_is_failed_without_result(tmp_path):
    root = tmp_path / "v3"
    first = V3Application(root)
    queued = first._new_job(request())
    first.close()
    second = V3Application(root)
    try:
        bundle = second.get_run(queued["job_id"])
        assert bundle["run"]["status"] == "FAILED"
        assert bundle["result"] is None
        with pytest.raises(ValueError, match="no completed result"):
            second._result_path(queued["job_id"])
    finally:
        second.close()


def test_fixed_prediction_and_later_reference_comparison_are_immutable(tmp_path):
    app = V3Application(tmp_path / "v3")
    try:
        q = request(target_crest_V=100_000.0)
        configuration = {
            "stages": 2,
            "stage_charge_V": 50_000.0,
            "front_network": {"op": "R", "ohm": 3700},
            "tail_network": {"op": "R", "ohm": 5000},
        }
        prediction = app.predict_fixed({"request": q, "configuration": configuration})
        assert prediction["schema_version"] == "network_prediction_v3"
        assert prediction["prediction"]["status"] in {"PHYSICS_FALLBACK", "ML_PREDICTION"}
        assert prediction["physics"]["application_status"] in {"PHYSICS_VERIFIED", "PHYSICS_UNSUPPORTED"}
        if prediction["physics_waveform"]:
            waveform = app.prediction_waveform(prediction["prediction_id"])
            assert waveform["waveform_reference"]["sha256"] == prediction["physics_waveform"]["sha256"]
        before = app.get_prediction(prediction["prediction_id"])

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["time", "voltage"])
        values = [0, 1, 4, 9, 16, 25, 36, 49, 64, 81, 100, 80, 60, 40, 20, 5]
        for index, value in enumerate(values):
            writer.writerow([index, value])
        raw = output.getvalue().encode("utf-8")
        metadata = {
            "measurement": {
                "time_column": "time",
                "voltage_column": "voltage",
                "time_unit": "us",
                "voltage_unit": "V",
                "voltage_scale_to_DUT": 1,
                "baseline_V": 0,
                "beginning_s": 0,
            },
            "source_organization": "TEST_FIXTURE",
        }
        comparison = app.attach_reference(prediction["prediction_id"], raw, metadata)
        assert comparison["schema_version"] == "network_reference_comparison_v3"
        assert comparison["raw_sha256"] == hashlib.sha256(raw).hexdigest()
        assert set(comparison["comparison"]) == {"crest_magnitude_V", "T1_s", "T2_s"}
        assert all("absolute_error" in value and "signed_error" in value and "relative_error" in value and "tolerance_normalized_error" in value for value in comparison["comparison"].values())
        assert app.get_prediction(prediction["prediction_id"]) == before
        stored = tmp_path / "v3" / "predictions" / prediction["prediction_id"] / comparison["comparison_id"] / "raw_export.csv"
        assert stored.read_bytes() == raw
        scalar = app.attach_reference_metrics(prediction["prediction_id"], {"crest_magnitude_V": 95_000, "T1_s": 1.0e-6, "T2_s": 50e-6}, {"source": "TEST_SCALAR"})
        assert scalar["qualification"]["status"] == "NUMERICAL_SCALAR_REFERENCE_ONLY"
        assert scalar["raw_sha256"] is None
        assert scalar["comparison"]["crest_magnitude_V"]["relative_error_basis"] == "reference_value"
        assert (tmp_path / "v3" / "predictions" / prediction["prediction_id"] / scalar["comparison_id"] / "reference_metrics.json").is_file()
        assert app.get_reference(prediction["prediction_id"], scalar["comparison_id"]) == scalar
    finally:
        app.close()


@pytest.mark.parametrize(
    "field,value",
    [
        ("impulse_type", "SI"),
        ("topology_id", "OSHUNT_v0"),
        ("polarity", -1),
        ("domain_id", "research_3uf"),
    ],
)
def test_fixed_prediction_rejects_explicit_route_mismatch_before_artifact(tmp_path, field, value):
    app = V3Application(tmp_path / "v3")
    try:
        configuration = {
            "impulse_type": "LI",
            "topology_id": "GSHUNT_v0",
            "polarity": 1,
            "stages": 2,
            "stage_charge_V": 50_000.0,
            "front_network": {"op": "R", "ohm": 180},
            "tail_network": {"op": "R", "ohm": 30},
        }
        configuration[field] = value
        with pytest.raises(ValueError, match="does not match request"):
            app.predict_fixed({"request": request(), "configuration": configuration})
        assert not list((tmp_path / "v3" / "predictions").glob("pred_v3_*"))
    finally:
        app.close()


def test_optional_load_keeps_detailed_physics_and_marks_ml_unsupported(tmp_path):
    app = V3Application(tmp_path / "v3")
    try:
        q = request(target_crest_V=100_000.0)
        q["setup"]["load_resistance_ohm"] = 100_000.0
        prediction = app.predict_fixed(
            {
                "request": q,
                "configuration": {
                    "impulse_type": "LI",
                    "topology_id": "GSHUNT_v0",
                    "polarity": 1,
                    "stages": 2,
                    "stage_charge_V": 50_000.0,
                    "front_network": {"op": "R", "ohm": 180},
                    "tail_network": {"op": "R", "ohm": 30},
                },
            }
        )
        assert prediction["prediction"]["status"] == "PHYSICS_FALLBACK"
        assert prediction["prediction"]["source"] == "DETAILED_PHYSICS"
        assert prediction["prediction"]["prediction_is_not_an_ml_claim"] is True
        assert prediction["model"]["status"] == "UNAVAILABLE"
        assert prediction["model"]["fallback_source"] == "DETAILED_PHYSICS"
        assert prediction["model"]["ml_unsupported_reason"].startswith(
            "L0 feature baseline does not support load_resistance_ohm"
        )
        assert prediction["physics"]["application_status"] == "PHYSICS_VERIFIED"
        assert prediction["physics"]["metrics"]["crest_magnitude_V"] == prediction["prediction"]["crest_V"]
        assert prediction["physics_waveform"] is not None
    finally:
        app.close()


def test_unexpected_physics_failure_is_not_published_as_unsupported(tmp_path, monkeypatch):
    import powernext_v3.physics as physics

    def broken(*args, **kwargs):
        raise RuntimeError("unexpected solver defect")

    monkeypatch.setattr(physics, "simulate", broken)
    app = V3Application(tmp_path / "v3")
    try:
        with pytest.raises(RuntimeError, match="unexpected solver defect"):
            app.predict_fixed(
                {
                    "request": request(),
                    "configuration": {
                        "stages": 2,
                        "stage_charge_V": 50_000.0,
                        "front_network": {"op": "R", "ohm": 180},
                        "tail_network": {"op": "R", "ohm": 30},
                    },
                }
            )
        assert not list((tmp_path / "v3" / "predictions").glob("pred_v3_*"))
    finally:
        app.close()


def test_invalid_physics_waveform_stays_computed_but_not_verified(tmp_path, monkeypatch):
    from types import SimpleNamespace

    import powernext_v3.physics as physics

    def mocked(*args, **kwargs):
        return SimpleNamespace(
            metadata={
                "schema_version": "physics_networks_v3",
                "numeric_status": "VALID",
                "voltage_gain": 1.0,
                "metrics": {
                    "waveform_status": "INDETERMINATE",
                    "crest_magnitude_V": 100_000.0,
                    "T1_s": None,
                    "T2_s": None,
                },
            },
            arrays={
                "time_s": [0.0, 1.0e-6, 2.0e-6, 3.0e-6],
                "voltage_V": [0.0, 10.0, 20.0, 15.0],
            },
        )

    monkeypatch.setattr(physics, "simulate", mocked)
    app = V3Application(tmp_path / "v3")
    try:
        prediction = app.predict_fixed(
            {
                "request": request(target_crest_V=100_000.0),
                "configuration": {
                    "stages": 2,
                    "stage_charge_V": 50_000.0,
                    "front_network": {"op": "R", "ohm": 180},
                    "tail_network": {"op": "R", "ohm": 30},
                },
            }
        )
        physics_record = prediction["physics"]
        assert physics_record["application_status"] == "PHYSICS_UNSUPPORTED"
        assert physics_record["physics_error_code"] == "WAVEFORM_NOT_CLEAN_FULL_IMPULSE"
        assert "waveform_status='INDETERMINATE'" in physics_record["physics_unsupported_reason"]
        assert physics_record["metrics"]["crest_magnitude_V"] == 100_000.0
        assert prediction["physics_waveform"] is not None
        waveform = app.prediction_waveform(prediction["prediction_id"])
        assert waveform["arrays"]["voltage_V"] == [0.0, 10.0, 20.0, 15.0]
    finally:
        app.close()


def test_http_v3_routes_keep_legacy_server_boundary(tmp_path):
    from powernext_app.server import make_server
    from powernext_app.service import Application as LegacyApplication

    legacy = LegacyApplication(tmp_path / "legacy", workers=1, timeout_seconds=30)
    server = make_server(legacy, 0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_port}"

    def call(path, body=None):
        request_object = Request(
            base + path,
            data=None if body is None else json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
        with urlopen(request_object, timeout=30) as response:
            return response.status, json.load(response)

    try:
        status, metadata = call("/api/v3/meta")
        assert status == 200 and metadata["schema_version"] == "network_application_v3"
        checked_request = request(max_modules=1, stages=[2], max_physics_evaluations=1)
        status, validated = call("/api/v3/validate", checked_request)
        assert status == 200 and validated["valid"] is True
        status, prediction = call(
            "/api/v3/predict",
            {
                "request": checked_request,
                "configuration": {
                    "stages": 2,
                    "stage_charge_V": 50_000,
                    "front_network": {"op": "R", "ohm": 3700},
                    "tail_network": {"op": "R", "ohm": 5000},
                },
            },
        )
        assert status == 201
        assert prediction["prediction_id"].startswith("pred_v3_")
        status, frozen = call(f"/api/v3/predictions/{prediction['prediction_id']}")
        assert status == 200 and frozen["input_sha256"] == prediction["input_sha256"]
        status, waveform = call(f"/api/v3/predictions/{prediction['prediction_id']}/waveform")
        assert status == 200 and waveform["schema_version"] == "network_prediction_waveform_v3"
        status, scalar = call(
            f"/api/v3/predictions/{prediction['prediction_id']}/reference-metrics",
            {"metrics": {"crest_magnitude_V": 95_000, "T1_s": 1.0e-6}, "metadata": {"source": "TEST_SCALAR"}},
        )
        assert status == 201 and scalar["qualification"]["status"] == "NUMERICAL_SCALAR_REFERENCE_ONLY"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=30)
        legacy.close()


@pytest.mark.parametrize(
    "bad",
    [
        {"configuration": {"stages": True}},
        {"configuration": {"stages": 2, "stage_charge_V": 1, "front_network": {"op": "R", "ohm": True}, "tail_network": {"op": "R", "ohm": 180}}},
    ],
)
def test_fixed_prediction_rejects_invalid_network_values(tmp_path, bad):
    app = V3Application(tmp_path / "v3")
    try:
        with pytest.raises((ValueError, TypeError)):
            app.predict_fixed({"request": request(), **bad})
    finally:
        app.close()


def test_prediction_hash_is_checked_before_reference_comparison(tmp_path):
    app = V3Application(tmp_path / "v3")
    try:
        q = request()
        prediction = app.predict_fixed({"request": q, "configuration": {"stages": 2, "stage_charge_V": 50_000, "front_network": {"op": "R", "ohm": 3700}, "tail_network": {"op": "R", "ohm": 5000}}})
        path = tmp_path / "v3" / "predictions" / prediction["prediction_id"] / "prediction.json"
        path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        with pytest.raises(ValueError, match="integrity"):
            app.get_prediction(prediction["prediction_id"])
        with pytest.raises(ValueError, match="integrity"):
            app.attach_reference_metrics(prediction["prediction_id"], {"crest_magnitude_V": 1}, {})
    finally:
        app.close()
