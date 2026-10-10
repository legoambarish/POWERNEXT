from __future__ import annotations

import hashlib

import pytest

import excel_comparison as comparison


def test_original_workbook_is_located_and_unchanged():
    path = comparison.locate_workbook()
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    assert before == comparison.EXPECTED_SOURCE_SHA256
    report = comparison.reproduce_numeric_formulas(path)
    after = hashlib.sha256(path.read_bytes()).hexdigest()
    assert after == before
    assert report["numeric_formula_count"] == 7026
    assert report["status_counts"] == {"REPRODUCED": 7026}


def test_zip_xml_fallback_reproduces_formula_cells():
    path = comparison.locate_workbook()
    formulas, cached, backend = comparison._xml_cells(path)
    book = {"path": str(path), "sha256": comparison._sha256(path), "backend": backend, "formulas": formulas, "cached": cached}
    # Exercise the same public report logic without importing openpyxl.
    original_reader = comparison.read_workbook
    try:
        comparison.read_workbook = lambda _: book
        report = comparison.reproduce_numeric_formulas(path)
    finally:
        comparison.read_workbook = original_reader
    assert report["status_counts"] == {"REPRODUCED": 7026}


def test_all_static_synthetic_theory_and_residual_identities_are_verified():
    path = comparison.locate_workbook()
    before = comparison._sha256(path)
    report = comparison.verify_static_synthetic_dataset(path)
    after = comparison._sha256(path)
    assert before == comparison.EXPECTED_SOURCE_SHA256 == after
    assert report["row_count"] == report["expected_row_count"] == 2000
    assert report["all_rows_checked"] is True
    assert report["id_check"]["expected_sequence"] is True
    assert report["generator_stage_capacitance_F"] == 3.0e-6
    assert report["all_checks_passed"] is True
    assert all(check["count"] == 2000 and check["mismatch_count"] == 0 for check in report["checks"].values())


def test_detailed_rlc_comparison_keeps_theoretical_and_observed_separate():
    path = comparison.locate_workbook()
    report = comparison.compare_detailed_rlc(path, sample_per_stratum=1, seed=11, n_points=1_000)
    assert report["domain_id"] == "research_3uf"
    assert report["comparison_count"] == report["selected_input_count"] * 2
    assert {row["topology_id"] for row in report["comparisons"]} == {"GSHUNT_v0", "OSHUNT_v0"}
    for row in report["comparisons"]:
        assert "workbook_theoretical" in row
        assert "detailed_rlc" in row
        assert "workbook_observed" in row
        assert row["comparison_kind"] == "MODEL_TO_MODEL"
        assert set(row["delta_detailed_minus_synthetic_observed"]) == {"front_us", "tail_us", "crest_kV"}
    assert set(report["aggregates"]) == {"by_impulse", "by_topology", "by_impulse_topology"}
    assert report["unsupported_count"] == sum(report["unsupported_by_code"].values())


def test_detailed_rlc_does_not_mask_unexpected_errors(monkeypatch):
    import powernext_v3.physics as physics

    def explode(*args, **kwargs):
        raise RuntimeError("unexpected comparison failure")

    monkeypatch.setattr(physics, "simulate", explode)
    with pytest.raises(RuntimeError, match="unexpected comparison failure"):
        comparison.compare_detailed_rlc(comparison.locate_workbook(), sample_per_stratum=1, seed=11, n_points=1_000)
