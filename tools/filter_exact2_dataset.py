"""Create an immutable exact-two-resistor-per-branch subset of Phase B R2.

The filter operates on raw rows before training eligibility or response-shape
deduplication.  A row is retained only when both canonical network trees have
exactly two resistor leaves and the root operation is ``P`` or ``S``.  Design
records are paired by ``row_id`` and their recipe trees/module-count fields are
validated before either output file is written.  No Physics simulation is
performed.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import sys
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from powernext_v3.networks import enumerate_networks  # noqa: E402
from powernext_v3.training import _deduplicate_training_rows, _eligible, assign_splits, load_rows  # noqa: E402


SCHEMA_VERSION = "powernext_v3_dataset_1.0"
DEFAULT_SOURCE = ROOT / "powernext" / "ml" / "data" / "networks_v3_r2"
DEFAULT_OUTPUT = ROOT / "powernext" / "ml" / "data" / "networks_exact2_v5"
ROUTES = tuple((domain, mode, topology) for domain in ("cpri_0p5uf", "research_3uf") for mode in ("LI", "SI") for topology in ("GSHUNT_v0", "OSHUNT_v0"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json_line(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _json_write(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def _route(row: Mapping[str, Any]) -> str:
    return f"{row.get('domain_id')}::{row.get('mode', row.get('impulse_type'))}::{row.get('topology_id', row.get('topology'))}"


def _canonical(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _canonical(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (list, tuple)):
        return [_canonical(v) for v in value]
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("Non-finite value in canonical network data")
        return float(format(value, ".15g"))
    return value


def _tree_shape(tree: Any) -> tuple[int | None, str | None, str | None]:
    """Return (leaf_count, root_op, recipe_id) for a canonical network tree."""

    if not isinstance(tree, Mapping):
        return None, None, None
    op = tree.get("op")
    if op == "R":
        return 1, "R", f"R{tree.get('ohm')}"
    if op not in ("P", "S"):
        return None, str(op), None
    children = tree.get("children")
    if not isinstance(children, list) or len(children) != 2:
        return None, str(op), None
    child_shapes = [_tree_shape(child) for child in children]
    if any(shape[0] is None for shape in child_shapes):
        return None, str(op), None
    count = int(sum(int(shape[0]) for shape in child_shapes if shape[0] is not None))
    recipe = f"{op}({','.join(str(shape[2]) for shape in child_shapes)})"
    return count, str(op), recipe


def _exact_two(tree: Any) -> tuple[int, str, str]:
    count, op, recipe = _tree_shape(tree)
    if count != 2 or op not in ("P", "S") or recipe is None:
        raise ValueError("network tree is not exactly a two-leaf P/S recipe")
    return int(count), str(op), recipe


def _load_design(source: Path, expected_count: int, expected_hash: str | None) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    path = source / "design.jsonl"
    if not path.is_file():
        raise FileNotFoundError(f"R2 design.jsonl is required: {path}")
    actual_hash = _sha256(path)
    if expected_hash and actual_hash != expected_hash:
        raise ValueError(f"R2 design.jsonl hash mismatch: expected {expected_hash}, got {actual_hash}")
    rows: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8") as stream:
        for line_no, line in enumerate(stream, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"Design row {line_no} is not an object")
            row_id = value.get("row_id")
            if not isinstance(row_id, str) or not row_id:
                raise ValueError(f"Design row {line_no} has no row_id")
            if row_id in by_id:
                raise ValueError(f"Duplicate design row_id: {row_id}")
            rows.append(value)
            by_id[row_id] = value
    # R2 design.jsonl intentionally contains the frozen learning-curve
    # capacity (240,000 records), while the completed stage currently has
    # 122,000 rows.  The filter pairs every materialized source row by
    # row_id; unmaterialized capacity records are not copied into the output.
    if len(rows) < expected_count:
        raise ValueError(f"R2 design count {len(rows)} is smaller than rows.jsonl count {expected_count}")
    return rows, by_id


def _assert_pair(row: Mapping[str, Any], design: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    """Validate row/design identity and exact two-leaf recipes."""

    if row.get("row_id") != design.get("row_id"):
        raise ValueError(f"row/design row_id mismatch: {row.get('row_id')} / {design.get('row_id')}")
    for key in ("domain_id", "mode", "topology_id", "split", "group_id", "response_group_key", "setup_family_key"):
        if row.get(key) != design.get(key):
            raise ValueError(f"row/design {key} mismatch for {row.get('row_id')}: {row.get(key)!r} / {design.get(key)!r}")
    row_config = row.get("configuration")
    design_config = design.get("configuration")
    if not isinstance(row_config, Mapping) or not isinstance(design_config, Mapping):
        raise ValueError(f"row/design configuration missing for {row.get('row_id')}")
    for key in ("front_network", "tail_network"):
        if _canonical(row_config.get(key)) != _canonical(design_config.get(key)):
            raise ValueError(f"row/design {key} mismatch for {row.get('row_id')}")
    front_count, front_op, front_recipe = _exact_two(row_config.get("front_network"))
    tail_count, tail_op, tail_recipe = _exact_two(row_config.get("tail_network"))
    design_front_count, design_front_op, design_front_recipe = _exact_two(design_config.get("front_network"))
    design_tail_count, design_tail_op, design_tail_recipe = _exact_two(design_config.get("tail_network"))
    if (front_count, front_op, front_recipe) != (design_front_count, design_front_op, design_front_recipe):
        raise ValueError(f"front row/design recipe mismatch for {row.get('row_id')}")
    if (tail_count, tail_op, tail_recipe) != (design_tail_count, design_tail_op, design_tail_recipe):
        raise ValueError(f"tail row/design recipe mismatch for {row.get('row_id')}")
    if design.get("front_network_module_count") != front_count or design.get("tail_network_module_count") != tail_count:
        raise ValueError(f"design module-count fields disagree with trees for {row.get('row_id')}")
    if design.get("front_network_family_id") != front_recipe or design.get("tail_network_family_id") != tail_recipe:
        raise ValueError(f"design recipe-family fields disagree with trees for {row.get('row_id')}")
    # Preserve and validate all route-driving configuration fields.  Small
    # numeric differences are not accepted because this is a raw subset.
    for key in ("impulse_type", "topology_id", "polarity", "stages", "front_per_stage_ohm", "tail_per_stage_ohm", "stage_charge_V"):
        if row_config.get(key) != design_config.get(key):
            raise ValueError(f"row/design configuration {key} mismatch for {row.get('row_id')}")
    return {
        "front_count": front_count,
        "tail_count": tail_count,
        "front_op": front_op,
        "tail_op": tail_op,
        "front_recipe": front_recipe,
        "tail_recipe": tail_recipe,
    }, dict(design)


def _expected_two_recipe_ids() -> list[str]:
    return sorted(str(recipe.id) for recipe in enumerate_networks(max_modules=4) if int(recipe.module_count) == 2)


def _coverage(rows: list[dict[str, Any]], designs: list[dict[str, Any]], parent_manifest: Mapping[str, Any]) -> dict[str, Any]:
    expected_recipes = _expected_two_recipe_ids()
    expected_pairs = [f"{front}::{tail}" for front in expected_recipes for tail in expected_recipes]
    by_route: dict[str, list[dict[str, Any]]] = defaultdict(list)
    design_by_id = {str(row["row_id"]): row for row in designs}
    for row in rows:
        by_route[_route(row)].append(row)
    route_reports: dict[str, Any] = {}
    total_eligible = 0
    for route, route_rows in sorted(by_route.items()):
        eligible = [row for row in route_rows if _eligible(row)]
        total_eligible += len(eligible)
        front_recipes = {str(design_by_id[row["row_id"]]["front_network_family_id"]) for row in route_rows}
        tail_recipes = {str(design_by_id[row["row_id"]]["tail_network_family_id"]) for row in route_rows}
        pairs = {f"{design_by_id[row['row_id']]['front_network_family_id']}::{design_by_id[row['row_id']]['tail_network_family_id']}" for row in route_rows}
        pair_ops = {
            f"{_tree_shape(row['configuration']['front_network'])[1]}::{_tree_shape(row['configuration']['tail_network'])[1]}"
            for row in route_rows
        }
        split_counts = Counter(str(row.get("split")) for row in route_rows)
        eligible_split_counts = Counter(str(row.get("split")) for row in eligible)
        response_keys = {str(row.get("response_group_key", row.get("response_group_id"))) for row in eligible}
        route_reports[route] = {
            "raw_rows": len(route_rows),
            "eligible_rows": len(eligible),
            "invalid_or_unsupported_rows": sum(1 for row in route_rows if not _eligible(row)),
            "status_counts": dict(sorted(Counter(str(row.get("status")) for row in route_rows).items())),
            "split_counts": dict(sorted(split_counts.items())),
            "eligible_split_counts": dict(sorted(eligible_split_counts.items())),
            "unique_eligible_response_groups": len(response_keys),
            "front_recipe_count": len(front_recipes),
            "front_recipe_expected": len(expected_recipes),
            "front_recipe_ids": sorted(front_recipes),
            "front_recipe_missing": sorted(set(expected_recipes) - front_recipes),
            "tail_recipe_count": len(tail_recipes),
            "tail_recipe_expected": len(expected_recipes),
            "tail_recipe_ids": sorted(tail_recipes),
            "tail_recipe_missing": sorted(set(expected_recipes) - tail_recipes),
            "paired_recipe_count": len(pairs),
            "paired_recipe_expected": len(expected_pairs),
            "paired_recipe_missing": sorted(set(expected_pairs) - pairs),
            "module_operation_pair_counts": dict(sorted(Counter(pair_ops).items())),
            "missing_module_operation_pairs": sorted({"P::P", "P::S", "S::P", "S::S"} - pair_ops),
            "domain": route.split("::", 1)[0],
        }
    canonical_assignments = assign_splits([row for row in rows if _eligible(row)], seed=20261010)
    eligible_rows = [row for row in rows if _eligible(row)]
    canonical_rows, canonical_splits, dedup_report, _audit = _deduplicate_training_rows(eligible_rows, canonical_assignments)
    canonical_route_split: dict[str, Counter[str]] = defaultdict(Counter)
    for row, split in zip(canonical_rows, canonical_splits):
        canonical_route_split[_route(row)][split] += 1
    return {
        "expected_exact_two_recipe_count_per_branch": len(expected_recipes),
        "expected_exact_two_recipe_pair_count": len(expected_pairs),
        "route_reports": route_reports,
        "total_raw_rows": len(rows),
        "total_eligible_rows": total_eligible,
        "canonical_eligible_rows": len(canonical_rows),
        "canonical_deduplication": dedup_report,
        "canonical_route_split_counts": {route: dict(sorted(counts.items())) for route, counts in sorted(canonical_route_split.items())},
        "parent_route_counts_for_comparison": parent_manifest.get("route_request_counts"),
    }


def _make_manifest(source: Path, output: Path, parent_manifest: Mapping[str, Any], rows: list[dict[str, Any]], designs: list[dict[str, Any]], audit: Mapping[str, Any]) -> dict[str, Any]:
    rows_path = output / "rows.jsonl"
    design_path = output / "design.jsonl"
    parent_manifest_path = source / "manifest.json"
    source_hashes = deepcopy(dict(parent_manifest.get("source_hashes") or {}))
    filter_tool = Path(__file__).resolve()
    provenance = deepcopy(dict(parent_manifest.get("provenance") or {}))
    provenance["filter"] = {
        "tool": "tools/filter_exact2_dataset.py",
        "tool_sha256": _sha256(filter_tool),
        "parent_path": str(source.relative_to(ROOT)).replace("\\", "/"),
        "parent_dataset_id": parent_manifest.get("dataset_id"),
        "predicate": "front and tail canonical trees each exactly two resistor leaves; root operation P or S",
        "filter_before_eligibility_and_response_dedup": True,
        "physics_simulation_performed": False,
    }
    route_counts = Counter(_route(row) for row in rows)
    eligible = [row for row in rows if _eligible(row)]
    route_eligible: dict[str, set[str]] = defaultdict(set)
    for row in eligible:
        route_eligible[_route(row)].add(str(row.get("response_group_key", row.get("response_group_id", row.get("input_sha256", row.get("row_id"))))))
    split_counts = Counter(str(row.get("split")) for row in rows)
    route_split = defaultdict(Counter)
    for row in rows:
        route_split[_route(row)][str(row.get("split"))] += 1
    selected_design_digest = hashlib.sha256(json.dumps([_canonical(row) for row in designs], sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()
    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "dataset_kind": "FILTERED_SUBSET_OF_PHASE_B_R2_EXACT_TWO_PER_BRANCH",
        "status": "COMPLETE",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dataset_id": f"networks_exact2_v5_{hashlib.sha256((str(parent_manifest.get('dataset_id')) + selected_design_digest).encode()).hexdigest()[:12]}",
        "parent_dataset_id": parent_manifest.get("dataset_id"),
        "parent_path": str(source.relative_to(ROOT)).replace("\\", "/"),
        "parent_manifest_sha256": _sha256(parent_manifest_path),
        "parent_rows_sha256": parent_manifest.get("rows_sha256"),
        "parent_design_sha256": parent_manifest.get("design_sha256"),
        "parent_design_file_sha256": parent_manifest.get("design_file_sha256"),
        "source_hashes": source_hashes,
        "physics_source_fingerprint": provenance.get("physics_source_fingerprint"),
        "provenance": provenance,
        "filter": {
            "root_ops": ["P", "S"],
            "front_leaf_count": 2,
            "tail_leaf_count": 2,
            "preserve_original_row_ids": True,
            "preserve_original_split_labels": True,
            "retain_invalid_or_unsupported_rows": True,
            "domains": ["cpri_0p5uf", "research_3uf"],
            "no_physics_rerun": True,
        },
        "row_count": len(rows),
        "rows_sha256": _sha256(rows_path),
        "design_row_count": len(designs),
        "design_sha256": selected_design_digest,
        "design_file_sha256": _sha256(design_path),
        "split_counts": dict(sorted(split_counts.items())),
        "split_route_counts": {route: dict(sorted(counts.items())) for route, counts in sorted(route_split.items())},
        "route_request_counts": dict(sorted(route_counts.items())),
        "route_eligible_counts": {route: len(values) for route, values in sorted(route_eligible.items())},
        "regression_eligible_count": sum(len(values) for values in route_eligible.values()),
        "regression_eligible_row_count": len(eligible),
        "coverage_audit": "coverage_audit.json",
        "parent_manifest_contract_copied": True,
        "source_rows_not_relabelled": True,
        "audit_summary": {
            "raw_retained_rows": audit["total_raw_rows"],
            "eligible_rows": audit["total_eligible_rows"],
            "canonical_eligible_rows": audit["canonical_eligible_rows"],
        },
    }
    return manifest


def filter_dataset(source: Path = DEFAULT_SOURCE, output: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    source = source.resolve()
    output = output.resolve()
    if output.exists():
        raise FileExistsError(f"Immutable exact2 destination already exists: {output}")
    source_rows, parent_manifest = load_rows(source)
    design_rows, design_by_id = _load_design(source, len(source_rows), parent_manifest.get("design_file_sha256"))
    selected_rows: list[dict[str, Any]] = []
    selected_designs: list[dict[str, Any]] = []
    rejected = Counter()
    for row in source_rows:
        row_id = row.get("row_id")
        design = design_by_id.get(str(row_id))
        if design is None:
            raise ValueError(f"No design record for source row_id={row_id!r}")
        try:
            _assert_pair(row, design)
        except ValueError as exc:
            message = str(exc)
            # A malformed pair is a hard source integrity failure, while a
            # valid >2 recipe is simply outside this exact-two subset.
            if "not exactly a two-leaf" in message:
                rejected["not_exactly_two_leaves_or_non_PS"] += 1
                continue
            raise
        selected_rows.append(dict(row))
        selected_designs.append(dict(design))
    if not selected_rows:
        raise ValueError("Exact-two filter retained no rows")
    expected_ids = [str(row["row_id"]) for row in source_rows if row.get("row_id") in design_by_id]
    actual_ids = [str(row["row_id"]) for row in selected_rows]
    if len(actual_ids) != len(set(actual_ids)):
        raise ValueError("Exact-two filter produced duplicate row_ids")
    audit = _coverage(selected_rows, selected_designs, parent_manifest)
    audit = dict(audit, filter_rejected_counts=dict(rejected), source_row_count=len(source_rows), retained_row_count=len(selected_rows), output_routes=sorted({_route(row) for row in selected_rows}), exact_two_coverage=True)
    output.mkdir(parents=True, exist_ok=False)
    rows_path = output / "rows.jsonl"
    design_path = output / "design.jsonl"
    try:
        with rows_path.open("w", encoding="utf-8", newline="\n") as stream:
            for row in selected_rows:
                stream.write(_json_line(row) + "\n")
        with design_path.open("w", encoding="utf-8", newline="\n") as stream:
            for row in selected_designs:
                stream.write(_json_line(row) + "\n")
        manifest = _make_manifest(source, output, parent_manifest, selected_rows, selected_designs, audit)
        # _make_manifest needs file hashes, so rows/design must already exist.
        _json_write(output / "manifest.json", manifest)
        _json_write(output / "coverage_audit.json", audit)
        # Reopen through the production loader and validate the explicit split
        # and post-filter canonicalization contracts before reporting success.
        loaded_rows, loaded_manifest = load_rows(output)
        eligible = [row for row in loaded_rows if _eligible(row)]
        assignments = assign_splits(eligible, seed=20261010)
        _deduplicate_training_rows(eligible, assignments)
        audit["post_write_validation"] = {
            "load_rows": True,
            "row_count": len(loaded_rows),
            "rows_sha256": loaded_manifest.get("rows_sha256"),
            "source_contract": True,
            "assign_splits": True,
            "deduplication": True,
        }
        _json_write(output / "coverage_audit.json", audit)
        # The audit hash is convenience metadata; it is not part of the source
        # rows contract and is intentionally written after validation.
        manifest["coverage_audit_sha256"] = _sha256(output / "coverage_audit.json")
        _json_write(output / "manifest.json", manifest)
    except Exception:
        # A failed new version is never presented as a completed dataset.
        # Keep a small failure receipt for diagnosis while refusing reuse.
        failure = {"status": "FAILED_FILTER", "timestamp": datetime.now(timezone.utc).isoformat(), "error": "filter failed before completion"}
        try:
            _json_write(output / "filter_failure.json", failure)
        finally:
            raise
    return {"manifest": manifest, "audit": audit}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    result = filter_dataset(args.source, args.output)
    print(json.dumps({"dataset_id": result["manifest"]["dataset_id"], "output": str(args.output), "rows": result["manifest"]["row_count"], "eligible": result["manifest"]["regression_eligible_row_count"], "canonical": result["audit"]["canonical_eligible_rows"]}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
