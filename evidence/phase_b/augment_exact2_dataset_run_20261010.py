"""Complete the exact-two branch scope with a bounded Cartesian supplement.

The R2 filter is deliberately left immutable.  This command reads that
filter, freezes five setup contexts per route (three train contexts plus one
validation and one test context), simulates every 42 x 42 exact-two
front/tail recipe pair, and writes a new composite version.  The Physics API
is the only label source; no ML estimates or observed workbook values enter
the rows.

The command is restart-safe at the artifact level: an existing destination is
never overwritten.  A completed output contains the parent rows unchanged
apart from scope metadata, the supplement rows, both design records, hashes,
and a pair-level coverage audit.  Waveform arrays are intentionally discarded
after each bounded worker result.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from powernext_v3 import dataset as v3_dataset  # noqa: E402
from powernext_v3.networks import enumerate_networks  # noqa: E402
from powernext_v3.training import _deduplicate_training_rows, _eligible, assign_splits, load_rows  # noqa: E402


SCHEMA_VERSION = "powernext_v3_dataset_1.0"
DEFAULT_SOURCE = ROOT / "powernext" / "ml" / "data" / "networks_exact2_v5"
DEFAULT_OUTPUT = ROOT / "powernext" / "ml" / "data" / "networks_exact2_v5_aug1"
DEFAULT_SEED = 20261011
DEFAULT_N_POINTS = 1600
DEFAULT_WORKERS = 6
ROUTES = tuple(
    (domain, mode, topology)
    for domain in ("cpri_0p5uf", "research_3uf")
    for mode in ("LI", "SI")
    for topology in ("GSHUNT_v0", "OSHUNT_v0")
)
CONTEXTS = (
    ("train_a", "train"),
    ("train_b", "train"),
    ("train_c", "train"),
    ("validation", "validation"),
    ("test", "test"),
)
SCOPE_CONTRACT = "EXACT_MODULES_PER_BRANCH_V5"
SCOPE_RULE = "front_network_module_count == 2 and tail_network_module_count == 2"
SCOPE_FILTER = {
    "exact_modules_per_branch": 2,
    "field_front": "front_network_module_count",
    "field_tail": "tail_network_module_count",
    "front_network_module_count": 2,
    "tail_network_module_count": 2,
    "rule": SCOPE_RULE,
}


def _json_default(value: Any) -> Any:
    if hasattr(value, "item") and callable(value.item):
        return value.item()
    raise TypeError(f"not JSON serializable: {type(value).__name__}")


def _canonical(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(k): _canonical(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (tuple, list)):
        return [_canonical(v) for v in value]
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite value in artifact hash")
        return float(format(value, ".15g"))
    return value


def _digest(value: Any) -> str:
    payload = json.dumps(_canonical(value), sort_keys=True, separators=(",", ":"), allow_nan=False, default=_json_default)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False, default=_json_default) + "\n", encoding="utf-8")


def _line(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False, default=_json_default)


def _route(row: Mapping[str, Any]) -> str:
    return f"{row.get('domain_id')}::{row.get('mode', row.get('impulse_type'))}::{row.get('topology_id', row.get('topology'))}"


def _leaf_count(tree: Any) -> int:
    if not isinstance(tree, Mapping):
        return 0
    if tree.get("op") == "R":
        return 1
    return sum(_leaf_count(child) for child in tree.get("children", ()) or ())


def _tree_op(tree: Any) -> str | None:
    return str(tree.get("op")) if isinstance(tree, Mapping) and tree.get("op") in {"S", "P"} else None


def _network_records() -> list[Any]:
    recipes = [recipe for recipe in enumerate_networks(max_modules=2) if int(recipe.module_count) == 2]
    recipes.sort(key=lambda recipe: str(recipe.id))
    if len(recipes) != 42:
        raise RuntimeError(f"exact-two catalogue contract changed: expected 42 recipes, got {len(recipes)}")
    if any(_leaf_count(recipe.tree) != 2 or _tree_op(recipe.tree) not in {"S", "P"} for recipe in recipes):
        raise RuntimeError("exact-two catalogue contains a non-P/S or non-two-leaf recipe")
    return recipes


def _context_setup(domain: str, route_index: int, context_index: int, setup_id: str) -> dict[str, Any]:
    """Return deterministic, distinct fixed setup families.

    The three train contexts and the held-out contexts are physically
    different.  Small route offsets prevent the normalized setup key from
    accidentally joining different domains/routes.  Values remain inside the
    Physics API bounds.
    """

    base = (
        (0.17, 0.061, 0.013, 7.0, 2.3, "INCLUDED_IN_OTHER_COMPONENTS"),
        (1.37, 0.271, 0.093, 23.0, 5.7, "INCLUDED_IN_OTHER_COMPONENTS"),
        (4.37, 0.731, 0.293, 41.0, 8.7, "INCLUDED_IN_OTHER_COMPONENTS"),
        (7.37, 1.731, 0.693, 73.0, 12.7, "ADDITIONAL_DISJOINT"),
        (9.37, 2.71, 1.11, 111.0, 17.3, "ADDITIONAL_DISJOINT"),
    )[context_index]
    # The offsets are intentionally deterministic and avoid exact aliases to
    # the common R2 setup families (10, 3, 1 nF / 120 uH / 20 ohm).
    offset = route_index * 0.017 + (0.004 if domain == "research_3uf" else 0.0)
    dut_nF, divider_nF, stray_nF, loop_uH, loop_r, coverage = base
    return {
        "dut_capacitance_F": (dut_nF + offset) * 1e-9,
        "divider_capacitance_F": (divider_nF + offset / 5.0) * 1e-9,
        "stray_capacitance_F": (stray_nF + offset / 10.0) * 1e-9,
        "loop_inductance_H": (loop_uH + offset * 10.0) * 1e-6,
        "basic_coverage_assumption": coverage,
        "loop_resistance_ohm": loop_r + offset,
        "load_resistance_ohm": None,
        "setup_id": setup_id,
        "auxiliary_assumption": "UNCONFIRMED_AUXILIARY_BRANCHES_OMITTED",
    }


def _split_maps(rows: Sequence[Mapping[str, Any]]) -> tuple[dict[str, str], dict[str, str]]:
    response: dict[str, str] = {}
    setup: dict[str, str] = {}
    for row in rows:
        split = str(row.get("split", "")).lower()
        if split not in {"train", "validation", "test"}:
            raise ValueError(f"parent row has invalid split: {split!r}")
        response_key = row.get("response_group_key", row.get("response_group_id"))
        setup_key = row.get("setup_family_key")
        if response_key is not None:
            previous = response.setdefault(str(response_key), split)
            if previous != split:
                raise ValueError(f"parent response group crosses splits: {response_key}")
        if setup_key is not None:
            previous = setup.setdefault(str(setup_key), split)
            if previous != split:
                raise ValueError(f"parent setup family crosses splits: {setup_key}")
    return response, setup


def _decorate_parent(row: Mapping[str, Any], scope_hash: str) -> dict[str, Any]:
    result = deepcopy(dict(row))
    configuration = result.get("configuration")
    if not isinstance(configuration, Mapping):
        raise ValueError(f"parent row has no configuration: {result.get('row_id')}")
    front_count = _leaf_count(configuration.get("front_network"))
    tail_count = _leaf_count(configuration.get("tail_network"))
    if front_count != 2 or tail_count != 2 or _tree_op(configuration.get("front_network")) not in {"S", "P"} or _tree_op(configuration.get("tail_network")) not in {"S", "P"}:
        raise ValueError(f"parent exact2 row failed raw scope: {result.get('row_id')}")
    result.update(
        {
            "front_network_module_count": front_count,
            "tail_network_module_count": tail_count,
            "scope_contract": SCOPE_CONTRACT,
            "scope_filter_sha256": scope_hash,
            "dataset_segment": "PARENT_EXACT2_FILTER",
        }
    )
    return result


def _decorate_parent_design(design: Mapping[str, Any], scope_hash: str) -> dict[str, Any]:
    result = deepcopy(dict(design))
    result.update(
        {
            "front_network_module_count": 2,
            "tail_network_module_count": 2,
            "scope_contract": SCOPE_CONTRACT,
            "scope_filter_sha256": scope_hash,
            "dataset_segment": "PARENT_EXACT2_FILTER",
        }
    )
    return result


def _build_requests(seed: int, scope_hash: str, parent_rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    recipes = _network_records()
    parent_response_splits, parent_setup_splits = _split_maps(parent_rows)
    requests: list[dict[str, Any]] = []
    context_seed = f"EXACT2_AUG1_CONTEXT_SEED_{seed}"
    for route_index, (domain, mode, topology) in enumerate(ROUTES):
        route_slug = f"{domain}_{mode}_{topology}".replace(".", "p").replace("-", "_")
        for context_index, (context_name, declared_split) in enumerate(CONTEXTS):
            setup_id = f"EXACT2_AUG1_{route_index:02d}_{context_name.upper()}"
            setup = _context_setup(domain, route_index, context_index, setup_id)
            setup_key = v3_dataset._setup_family_identity({"setup": setup})
            for pair_index, (front, tail) in enumerate((front, tail) for front in recipes for tail in recipes):
                stages = 2 + ((pair_index + context_index * 3 + route_index) % 14)
                charge = float(60_000 + ((pair_index * 7919 + context_index * 31_337 + route_index * 104_729) % 140_001))
                targets = (50_000.0, 100_000.0, 200_000.0, 400_000.0, 800_000.0, 1_200_000.0, 1_800_000.0, 2_400_000.0)
                target = targets[(pair_index * 7 + context_index * 3 + route_index) % len(targets)]
                polarity = 1 if (pair_index + context_index + route_index) % 2 == 0 else -1
                configuration = {
                    "impulse_type": mode,
                    "stages": stages,
                    "stage_charge_V": charge,
                    "front_per_stage_ohm": float(front.equivalent_ohm),
                    "tail_per_stage_ohm": float(tail.equivalent_ohm),
                    "topology_id": topology,
                    "polarity": polarity,
                    "front_network": front.tree,
                    "tail_network": tail.tree,
                }
                row_id = f"exact2_aug1_{route_index:02d}_{context_index}_{pair_index:04d}"
                request: dict[str, Any] = {
                    "row_id": row_id,
                    "domain_id": domain,
                    "mode": mode,
                    "topology_id": topology,
                    "configuration": configuration,
                    "setup": deepcopy(setup),
                    "target_crest_V": target,
                    "setup_family_id": setup_id,
                    "setup_family_key": setup_key,
                    "case_kind": "exact2_full_pair_augmentation",
                    "augmentation_context": context_name,
                    "augmentation_context_seed": context_seed,
                    "design_local_index": context_index * len(recipes) * len(recipes) + pair_index,
                    "design_route_index": route_index,
                    "design_seed": seed,
                    "front_network_family_id": str(front.id),
                    "tail_network_family_id": str(tail.id),
                    "front_network_module_count": 2,
                    "tail_network_module_count": 2,
                    "actual_front_per_stage_ohm": float(front.equivalent_ohm),
                    "actual_tail_per_stage_ohm": float(tail.equivalent_ohm),
                    "requested_front_per_stage_ohm": float(front.equivalent_ohm),
                    "requested_tail_per_stage_ohm": float(tail.equivalent_ohm),
                    "recipe_family": "front_modules_2_tail_modules_2",
                    "recipe_family_index": pair_index,
                    "learning_curve_stage": "EXACT2_FULL_PAIR",
                    "boundary_capacitance_variant": None,
                    "rare_reference": None,
                    "scope_contract": SCOPE_CONTRACT,
                    "scope_filter_sha256": scope_hash,
                    "dataset_segment": "SUPPLEMENT_EXACT2_FULL_CARTESIAN",
                    "requested_context_split": declared_split,
                    "split": declared_split,
                    "split_frozen": True,
                }
                response_key = v3_dataset._response_group_identity(request)
                # A single response shape can be represented by multiple
                # recipe trees.  Keep that physical equivalence key so the
                # training loader can deduplicate compatible labels.
                request["response_group_key"] = response_key
                request["response_group_id"] = response_key
                actual_split = declared_split
                previous = parent_response_splits.get(str(response_key))
                if previous is not None:
                    actual_split = previous
                previous_setup = parent_setup_splits.get(str(setup_key))
                if previous_setup is not None and previous_setup != actual_split:
                    raise ValueError(f"new setup family collides with parent split: {setup_key}")
                request["split"] = actual_split
                # Keep one group for the complete fixed setup context.  The
                # response key remains separate for canonical deduplication,
                # while the setup identity keeps pair rows atomically in one
                # learning-curve partition.
                request["group_id"] = _digest({"route": _route(request), "setup_family_key": setup_key})
                request["split_audit"] = {
                    "response_group_key": response_key,
                    "setup_family_key": setup_key,
                    "group_id": request["group_id"],
                    "split": actual_split,
                    "requested_context_split": declared_split,
                    "frozen_before_labels": True,
                    "freeze_seed": seed,
                    "freeze_policy": "five independent setup contexts; parent identities preserved",
                }
                requests.append(request)
    expected = len(ROUTES) * len(CONTEXTS) * len(recipes) * len(recipes)
    if len(requests) != expected:
        raise AssertionError(f"supplement design count mismatch: {len(requests)} != {expected}")
    # Validate all explicit identities before simulation, as required by the
    # split contract.  No Physics label has been computed at this point.
    assign_splits(requests)
    return requests


def _worker(args: tuple[dict[str, Any], int]) -> tuple[dict[str, Any], dict[str, Any] | None]:
    request, n_points = args
    return v3_dataset._simulate_request(request, n_points)


def _decorate_simulation(row: Mapping[str, Any], request: Mapping[str, Any], scope_hash: str) -> dict[str, Any]:
    result = dict(row)
    for key in (
        "domain_id",
        "mode",
        "topology_id",
        "configuration",
        "setup",
        "target_crest_V",
        "setup_family_id",
        "setup_family_key",
        "case_kind",
        "augmentation_context",
        "augmentation_context_seed",
        "design_local_index",
        "design_route_index",
        "design_seed",
        "front_network_family_id",
        "tail_network_family_id",
        "front_network_module_count",
        "tail_network_module_count",
        "actual_front_per_stage_ohm",
        "actual_tail_per_stage_ohm",
        "requested_front_per_stage_ohm",
        "requested_tail_per_stage_ohm",
        "recipe_family",
        "recipe_family_index",
        "learning_curve_stage",
        "boundary_capacitance_variant",
        "rare_reference",
        "scope_contract",
        "scope_filter_sha256",
        "dataset_segment",
        "requested_context_split",
        "split",
        "split_frozen",
        "split_audit",
        "group_id",
        "response_group_id",
        "response_group_key",
    ):
        if key in request:
            result[key] = deepcopy(request[key])
    result["scope_contract"] = SCOPE_CONTRACT
    result["scope_filter_sha256"] = scope_hash
    result["front_network_module_count"] = 2
    result["tail_network_module_count"] = 2
    result["dataset_segment"] = "SUPPLEMENT_EXACT2_FULL_CARTESIAN"
    return result


def _pair_report(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    recipes = [str(recipe.id) for recipe in _network_records()]
    expected_pairs = [f"{front}::{tail}" for front in recipes for tail in recipes]
    by_route: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        by_route[_route(row)].append(row)
    route_reports: dict[str, Any] = {}
    all_unsupported: list[dict[str, Any]] = []
    for route, route_rows in sorted(by_route.items()):
        pair_rows: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
        for row in route_rows:
            cfg = row.get("configuration", {})
            front = row.get("front_network_family_id")
            tail = row.get("tail_network_family_id")
            if not front or not tail:
                # Parent rows have family IDs in design only; derive IDs from
                # their canonical trees for the composite audit.
                front = v3_dataset._network_exact_key(cfg.get("front_network"), cfg.get("front_per_stage_ohm"))
                tail = v3_dataset._network_exact_key(cfg.get("tail_network"), cfg.get("tail_per_stage_ohm"))
            pair_rows[f"{front}::{tail}"].append(row)
        pair_status: dict[str, Any] = {}
        for pair in expected_pairs:
            values = pair_rows.get(pair, [])
            eligible = [row for row in values if _eligible(row)]
            splits = Counter(str(row.get("split")) for row in values)
            statuses = Counter(str(row.get("status")) for row in values)
            item = {
                "raw_rows": len(values),
                "eligible_rows": len(eligible),
                "invalid_or_unsupported_rows": len(values) - len(eligible),
                "status_counts": dict(sorted(statuses.items())),
                "split_counts": dict(sorted(splits.items())),
            }
            pair_status[pair] = item
            if not eligible:
                all_unsupported.append({"route": route, "pair": pair, **item})
        op_counts = Counter()
        for row in route_rows:
            cfg = row.get("configuration", {})
            op_counts[f"{_tree_op(cfg.get('front_network'))}::{_tree_op(cfg.get('tail_network'))}"] += 1
        eligible_pairs = {pair for pair, item in pair_status.items() if item["eligible_rows"] > 0}
        route_reports[route] = {
            "raw_rows": len(route_rows),
            "eligible_rows": sum(1 for row in route_rows if _eligible(row)),
            "invalid_or_unsupported_rows": sum(1 for row in route_rows if not _eligible(row)),
            "status_counts": dict(sorted(Counter(str(row.get("status")) for row in route_rows).items())),
            "split_counts": dict(sorted(Counter(str(row.get("split")) for row in route_rows).items())),
            "context_counts": dict(sorted(Counter(str(row.get("augmentation_context", "parent")) for row in route_rows).items())),
            "front_recipe_count": len({pair.split("::", 1)[0] for pair in pair_status if pair in pair_rows}),
            "tail_recipe_count": len({pair.split("::", 1)[1] for pair in pair_status if pair in pair_rows}),
            "front_recipe_expected": len(recipes),
            "tail_recipe_expected": len(recipes),
            "paired_recipe_count": len(pair_rows),
            "paired_recipe_expected": len(expected_pairs),
            "paired_recipe_missing": sorted(set(expected_pairs) - set(pair_rows)),
            "eligible_pair_count": len(eligible_pairs),
            "unsupported_pair_count": len(expected_pairs) - len(eligible_pairs),
            "module_operation_pair_counts": dict(sorted(op_counts.items())),
            "pair_status": pair_status,
            "stage_counts": dict(sorted(Counter(str(row.get("configuration", {}).get("stages")) for row in route_rows).items())),
        }
    return {
        "expected_exact_two_recipe_count_per_branch": len(recipes),
        "expected_exact_two_recipe_pair_count": len(expected_pairs),
        "expected_context_count_per_route": len(CONTEXTS),
        "expected_supplement_rows_per_route": len(CONTEXTS) * len(expected_pairs),
        "route_reports": route_reports,
        "potential_unsupported_pairs": all_unsupported,
        "potential_unsupported_pair_count": len(all_unsupported),
        "total_raw_rows": len(rows),
        "total_eligible_rows": sum(1 for row in rows if _eligible(row)),
    }


def _manifest(
    output: Path,
    source: Path,
    source_manifest: Mapping[str, Any],
    rows: Sequence[Mapping[str, Any]],
    designs: Sequence[Mapping[str, Any]],
    scope_hash: str,
    seed: int,
    workers: int,
    n_points: int,
    audit: Mapping[str, Any],
) -> dict[str, Any]:
    rows_path = output / "rows.jsonl"
    design_path = output / "design.jsonl"
    source_hashes = deepcopy(dict(source_manifest.get("source_hashes") or {}))
    provenance = deepcopy(dict(source_manifest.get("provenance") or {}))
    parent_catalog = deepcopy(dict(provenance.get("network_catalog") or {}))
    provenance["parent_filter"] = {
        "dataset_id": source_manifest.get("dataset_id"),
        "path": str(source.relative_to(ROOT)).replace("\\", "/"),
        "manifest_sha256": _sha256(source / "manifest.json"),
        "rows_sha256": source_manifest.get("rows_sha256"),
        "design_sha256": source_manifest.get("design_sha256"),
    }
    provenance["network_catalog"] = {
        "api": "powernext_v3.networks.enumerate_networks",
        "max_modules": 2,
        "recipe_count": 42,
        "module_count": 2,
        "root_operations": ["P", "S"],
        "fallback_single_resistor": False,
        "parent_catalog_max_modules_4": parent_catalog,
    }
    provenance["augmentation"] = {
        "tool": "tools/augment_exact2_dataset.py",
        "tool_sha256": _sha256(Path(__file__).resolve()),
        "seed": seed,
        "workers": workers,
        "n_points": n_points,
        "physics_only": True,
        "observed_data_used": False,
        "contexts": [{"name": name, "split": split} for name, split in CONTEXTS],
        "setup_groups_frozen_before_labels": True,
    }
    route_counts = Counter(_route(row) for row in rows)
    eligible_rows = [row for row in rows if _eligible(row)]
    route_eligible: dict[str, set[str]] = defaultdict(set)
    for row in eligible_rows:
        route_eligible[_route(row)].add(str(row.get("response_group_key", row.get("response_group_id", row.get("row_id")))))
    split_counts = Counter(str(row.get("split")) for row in rows)
    route_splits: dict[str, Counter[str]] = defaultdict(Counter)
    for row in rows:
        route_splits[_route(row)][str(row.get("split"))] += 1
    design_digest = _digest(list(designs))
    manifest: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "dataset_kind": "FILTERED_SUBSET_WITH_EXACT2_FULL_PAIR_AUGMENTATION",
        "status": "IN_PROGRESS",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dataset_id": f"networks_exact2_v5_aug1_{_digest({'parent': source_manifest.get('dataset_id'), 'design': design_digest})[:12]}",
        "scope_contract": SCOPE_CONTRACT,
        "exact_modules_per_branch": 2,
        "scope_filter": deepcopy(SCOPE_FILTER),
        "scope_filter_sha256": scope_hash,
        "parent_dataset_id": source_manifest.get("dataset_id"),
        "parent_path": str(source.relative_to(ROOT)).replace("\\", "/"),
        "parent_manifest_sha256": _sha256(source / "manifest.json"),
        "parent_rows_sha256": source_manifest.get("rows_sha256"),
        "parent_design_sha256": source_manifest.get("design_sha256"),
        "parent_design_file_sha256": source_manifest.get("design_file_sha256"),
        "source_hashes": source_hashes,
        "physics_source_fingerprint": source_manifest.get("physics_source_fingerprint"),
        "provenance": provenance,
        "row_count": len(rows),
        "rows_sha256": _sha256(rows_path) if rows_path.is_file() else None,
        "design_row_count": len(designs),
        "design_sha256": design_digest,
        "design_file_sha256": _sha256(design_path),
        "split_counts": dict(sorted(split_counts.items())),
        "split_route_counts": {route: dict(sorted(counts.items())) for route, counts in sorted(route_splits.items())},
        "route_request_counts": dict(sorted(route_counts.items())),
        "route_eligible_counts": {route: len(values) for route, values in sorted(route_eligible.items())},
        "regression_eligible_count": sum(len(values) for values in route_eligible.values()),
        "regression_eligible_row_count": len(eligible_rows),
        "coverage_audit": "coverage_audit.json",
        "split_rule": "Parent exact2 split labels are immutable; supplemental setup contexts are assigned train_a/train_b/train_c/validation/test before Physics labels.",
        "label_rule": "Only numeric_status=VALID and waveform_status=VALID_CLEAN_FULL_IMPULSE rows with complete metrics are regression eligible; invalid or unsupported rows retain null labels.",
        "waveform_policy": "none; worker arrays discarded after each result",
        "observed_data_used_for_training": False,
        "augmentation": {
            "seed": seed,
            "contexts": [{"name": name, "split": split} for name, split in CONTEXTS],
            "routes": [list(route) for route in ROUTES],
            "recipes_per_branch": 42,
            "pairs_per_route": 1764,
            "supplement_rows_per_route": 8820,
            "supplement_rows_total": 70_560,
            "workers": workers,
            "n_points": n_points,
            "bounded_inflight": max(2, workers * 2),
            "completion": "pending_audit",
        },
        "audit_summary": {
            "raw_retained_rows": audit["total_raw_rows"],
            "eligible_rows": audit["total_eligible_rows"],
            "potential_unsupported_pair_count": audit["potential_unsupported_pair_count"],
        },
    }
    return manifest


def augment_dataset(
    source: Path = DEFAULT_SOURCE,
    output: Path = DEFAULT_OUTPUT,
    *,
    seed: int = DEFAULT_SEED,
    workers: int = DEFAULT_WORKERS,
    n_points: int = DEFAULT_N_POINTS,
    heartbeat_every: int = 250,
) -> dict[str, Any]:
    source = source.resolve()
    output = output.resolve()
    if output.exists():
        raise FileExistsError(f"immutable augmentation destination already exists: {output}")
    parent_rows, parent_manifest = load_rows(source)
    design_path = source / "design.jsonl"
    if not design_path.is_file():
        raise FileNotFoundError(f"parent design.jsonl missing: {design_path}")
    parent_designs = [json.loads(line) for line in design_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if len(parent_designs) != len(parent_rows):
        # The R2 capacity design is larger than materialized rows, while the
        # exact2 filter design is expected to be one-to-one.
        by_id = {str(value.get("row_id")): value for value in parent_designs}
        parent_designs = [by_id[str(row["row_id"])] for row in parent_rows]
    scope_hash = _digest(SCOPE_FILTER)
    parent_rows_decorated = [_decorate_parent(row, scope_hash) for row in parent_rows]
    parent_designs_decorated = [_decorate_parent_design(design, scope_hash) for design in parent_designs]
    requests = _build_requests(seed, scope_hash, parent_rows_decorated)
    supplement_designs = [deepcopy(request) for request in requests]
    all_designs = parent_designs_decorated + supplement_designs
    expected_rows = len(parent_rows) + len(requests)
    output.mkdir(parents=True, exist_ok=False)
    rows_path = output / "rows.jsonl"
    design_file = output / "design.jsonl"
    with design_file.open("w", encoding="utf-8", newline="\n") as stream:
        for design in all_designs:
            stream.write(_line(design) + "\n")
    audit_placeholder = {"status": "IN_PROGRESS", "expected_rows": expected_rows, "expected_supplement_rows": len(requests)}
    _write_json(output / "coverage_audit.json", audit_placeholder)
    manifest = _manifest(output, source, parent_manifest, parent_rows_decorated, all_designs, scope_hash, seed, workers, n_points, audit_placeholder | {"total_raw_rows": expected_rows, "total_eligible_rows": 0, "potential_unsupported_pair_count": 0})
    manifest["rows_sha256"] = None
    manifest["status"] = "IN_PROGRESS"
    _write_json(output / "manifest.json", manifest)
    completed = 0
    started = time.perf_counter()
    rows: list[dict[str, Any]] = list(parent_rows_decorated)
    with rows_path.open("w", encoding="utf-8", newline="\n") as stream:
        for row in parent_rows_decorated:
            stream.write(_line(row) + "\n")
        stream.flush()
        worker_count = max(1, min(int(workers), os.cpu_count() or 1))
        inflight_limit = max(2, worker_count * 2)
        pending: dict[Any, int] = {}
        ready: dict[int, dict[str, Any]] = {}
        next_submit = 0
        next_write = 0
        try:
            with ProcessPoolExecutor(max_workers=worker_count) as executor:
                def submit_more() -> None:
                    nonlocal next_submit
                    while next_submit < len(requests) and len(pending) < inflight_limit:
                        future = executor.submit(_worker, (requests[next_submit], n_points))
                        pending[future] = next_submit
                        next_submit += 1

                submit_more()
                while pending:
                    done, _ = wait(tuple(pending), return_when=FIRST_COMPLETED)
                    for future in done:
                        index = pending.pop(future)
                        result, _arrays = future.result()
                        ready[index] = _decorate_simulation(result, requests[index], scope_hash)
                        submit_more()
                    while next_write in ready:
                        row = ready.pop(next_write)
                        rows.append(row)
                        stream.write(_line(row) + "\n")
                        completed += 1
                        next_write += 1
                        if completed % max(1, heartbeat_every) == 0:
                            stream.flush()
                            elapsed = time.perf_counter() - started
                            print(f"[{datetime.now(timezone.utc).isoformat(timespec='seconds')}] exact2-augment completed={completed}/{len(requests)} elapsed_s={elapsed:.1f}", flush=True)
                    submit_more()
                stream.flush()
        except Exception as exc:
            manifest.update({"status": "FAILED", "failed_at": datetime.now(timezone.utc).isoformat(), "failure": {"type": type(exc).__name__, "message": str(exc)}, "completed_supplement_rows": completed})
            _write_json(output / "manifest.json", manifest)
            _write_json(output / "progress.json", {"status": "FAILED", "completed": completed, "total": len(requests), "error": manifest["failure"]})
            raise
    if len(rows) != expected_rows:
        raise AssertionError(f"composite row count mismatch: {len(rows)} != {expected_rows}")
    # Explicit split integrity is checked across parent and supplement rows,
    # before any canonical deduplication.  This catches identity collisions
    # even when one of the rows is unsupported.
    eligible_rows = [row for row in rows if _eligible(row)]
    assignments = assign_splits(eligible_rows)
    canonical_rows, canonical_splits, dedup_report, _audit = _deduplicate_training_rows(eligible_rows, assignments)
    audit = _pair_report(rows)
    audit.update(
        {
            "status": "COMPLETE",
            "source_dataset_id": parent_manifest.get("dataset_id"),
            "source_manifest_sha256": _sha256(source / "manifest.json"),
            "scope_filter_sha256": scope_hash,
            "supplement_seed": seed,
            "supplement_contexts": [{"name": name, "split": split} for name, split in CONTEXTS],
            "supplement_requested_rows": len(requests),
            "supplement_completed_rows": completed,
            "post_write_validation": {
                "assign_splits": True,
                "split_collision_count": 0,
                "deduplication": True,
                "canonical_eligible_rows": len(canonical_rows),
                "canonical_deduplication": dedup_report,
                "eligible_split_counts": dict(sorted(Counter(canonical_splits).items())),
            },
        }
    )
    _write_json(output / "coverage_audit.json", audit)
    manifest = _manifest(output, source, parent_manifest, rows, all_designs, scope_hash, seed, workers, n_points, audit)
    manifest.update(
        {
            "status": "COMPLETE",
            "completed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "rows_sha256": _sha256(rows_path),
            "row_count": len(rows),
            "design_row_count": len(all_designs),
            "design_file_sha256": _sha256(design_file),
            "coverage_audit_sha256": _sha256(output / "coverage_audit.json"),
            "augmentation": dict(manifest.get("augmentation") or {}, completion="COMPLETE", completed_supplement_rows=completed),
        }
    )
    _write_json(output / "manifest.json", manifest)
    # Reopen from disk through the production loader.  This verifies hashes,
    # exact-two scope, source fingerprint, and the explicit split contract on
    # the artifact that will be handed to ML.
    loaded_rows, loaded_manifest = load_rows(output)
    loaded_eligible = [row for row in loaded_rows if _eligible(row)]
    loaded_assignments = assign_splits(loaded_eligible)
    _deduplicate_training_rows(loaded_eligible, loaded_assignments)
    manifest["post_write_validation"] = {
        "load_rows": True,
        "row_count": len(loaded_rows),
        "rows_sha256": loaded_manifest.get("rows_sha256"),
        "source_contract": True,
        "assign_splits": True,
        "deduplication": True,
        "split_collision_count": 0,
    }
    _write_json(output / "manifest.json", manifest)
    return {"manifest": manifest, "audit": audit}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    parser.add_argument("--n-points", type=int, default=DEFAULT_N_POINTS)
    parser.add_argument("--heartbeat", type=int, default=250)
    args = parser.parse_args(argv)
    result = augment_dataset(args.source, args.output, seed=args.seed, workers=args.workers, n_points=args.n_points, heartbeat_every=args.heartbeat)
    manifest = result["manifest"]
    audit = result["audit"]
    print(json.dumps({
        "dataset_id": manifest.get("dataset_id"),
        "output": str(args.output.resolve()),
        "rows": manifest.get("row_count"),
        "supplement_rows": manifest.get("augmentation", {}).get("completed_supplement_rows"),
        "eligible": manifest.get("regression_eligible_count"),
        "potential_unsupported_pairs": audit.get("potential_unsupported_pair_count"),
        "rows_sha256": manifest.get("rows_sha256"),
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
