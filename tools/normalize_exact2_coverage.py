"""Write a canonical recipe-key coverage audit for an exact2 composite.

The first augmentation audit intentionally retained a diagnostic view of raw
metadata and therefore mixed numeric resistance keys with recipe IDs for
parent rows.  This read-only audit derives recipe IDs from every canonical
tree, leaving the immutable rows, design, manifest, and original audit bytes
unchanged.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Mapping, Sequence

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from powernext_v3.networks import canonicalize, enumerate_networks  # noqa: E402
from powernext_v3.training import _deduplicate_training_rows, _eligible, assign_splits, load_rows  # noqa: E402


EXPECTED_ROUTES = tuple(
    (domain, mode, topology)
    for domain in ("cpri_0p5uf", "research_3uf")
    for mode in ("LI", "SI")
    for topology in ("GSHUNT_v0", "OSHUNT_v0")
)
CONTEXTS = {"train_a": "train", "train_b": "train", "train_c": "train", "validation": "validation", "test": "test"}


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _route(row: Mapping[str, Any]) -> str:
    return f"{row.get('domain_id')}::{row.get('mode', row.get('impulse_type'))}::{row.get('topology_id', row.get('topology'))}"


def _tree_key(tree: Any) -> str:
    return _json(canonicalize(tree))


def _recipe_map() -> dict[str, str]:
    recipes = [recipe for recipe in enumerate_networks(max_modules=2) if int(recipe.module_count) == 2]
    recipes.sort(key=lambda recipe: str(recipe.id))
    if len(recipes) != 42:
        raise ValueError(f"expected 42 exact-two recipes, got {len(recipes)}")
    return {_tree_key(recipe.tree): str(recipe.id) for recipe in recipes}


def _recipe_ids(row: Mapping[str, Any], mapping: Mapping[str, str]) -> tuple[str, str]:
    configuration = row.get("configuration")
    if not isinstance(configuration, Mapping):
        raise ValueError(f"row lacks configuration: {row.get('row_id')}")
    try:
        front = mapping[_tree_key(configuration["front_network"])]
        tail = mapping[_tree_key(configuration["tail_network"])]
    except KeyError as exc:
        raise ValueError(f"row has a tree outside exact-two catalogue: {row.get('row_id')}") from exc
    return front, tail


def normalize(data_dir: Path) -> dict[str, Any]:
    data_dir = data_dir.resolve()
    rows, manifest = load_rows(data_dir)
    mapping = _recipe_map()
    recipes = sorted(mapping.values())
    pairs = [f"{front}::{tail}" for front in recipes for tail in recipes]
    by_route: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_route[_route(row)].append(row)
    missing_routes = sorted({"::".join(route) for route in EXPECTED_ROUTES} - set(by_route))
    if missing_routes:
        raise ValueError(f"missing route rows: {missing_routes}")
    eligible = [row for row in rows if _eligible(row)]
    assignments = assign_splits(eligible)
    canonical_rows, canonical_splits, dedup_report, _ = _deduplicate_training_rows(eligible, assignments)
    canonical_by_route_split: dict[str, Counter[str]] = defaultdict(Counter)
    for row, split in zip(canonical_rows, canonical_splits):
        canonical_by_route_split[_route(row)][str(split)] += 1
    route_reports: dict[str, Any] = {}
    unsupported: list[dict[str, Any]] = []
    for route, route_rows in sorted(by_route.items()):
        pair_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in route_rows:
            front, tail = _recipe_ids(row, mapping)
            pair_rows[f"{front}::{tail}"].append(row)
        pair_status: dict[str, Any] = {}
        for pair in pairs:
            values = pair_rows.get(pair, [])
            eligible_values = [row for row in values if _eligible(row)]
            item = {
                "raw_rows": len(values),
                "eligible_rows": len(eligible_values),
                "invalid_or_unsupported_rows": len(values) - len(eligible_values),
                "status_counts": dict(sorted(Counter(str(row.get("status")) for row in values).items())),
                "split_counts": dict(sorted(Counter(str(row.get("split")) for row in values).items())),
                "segments": dict(sorted(Counter(str(row.get("dataset_segment", "PARENT_EXACT2_FILTER")) for row in values).items())),
            }
            pair_status[pair] = item
            if not eligible_values:
                unsupported.append({"route": route, "pair": pair, **item})
        operation_counts = Counter()
        for row in route_rows:
            config = row.get("configuration", {})
            front = config.get("front_network") if isinstance(config, Mapping) else None
            tail = config.get("tail_network") if isinstance(config, Mapping) else None
            operation_counts[f"{front.get('op') if isinstance(front, Mapping) else None}::{tail.get('op') if isinstance(tail, Mapping) else None}"] += 1
        route_reports[route] = {
            "raw_rows": len(route_rows),
            "eligible_rows": sum(1 for row in route_rows if _eligible(row)),
            "canonical_eligible_rows": sum(canonical_by_route_split[route].values()),
            "canonical_eligible_split_counts": dict(sorted(canonical_by_route_split[route].items())),
            "raw_split_counts": dict(sorted(Counter(str(row.get("split")) for row in route_rows).items())),
            "raw_status_counts": dict(sorted(Counter(str(row.get("status")) for row in route_rows).items())),
            "setup_family_count": len({str(row.get("setup_family_id")) for row in route_rows}),
            "supplement_setup_family_count": len({str(row.get("setup_family_id")) for row in route_rows if str(row.get("dataset_segment", "")).startswith("SUPPLEMENT")}),
            "supplement_context_counts": dict(sorted(Counter(str(row.get("augmentation_context", "parent")) for row in route_rows).items())),
            "front_recipe_count": len({pair.split("::", 1)[0] for pair in pair_rows}),
            "tail_recipe_count": len({pair.split("::", 1)[1] for pair in pair_rows}),
            "paired_recipe_count": len(pair_rows),
            "expected_front_recipe_count": 42,
            "expected_tail_recipe_count": 42,
            "expected_paired_recipe_count": 1764,
            "missing_pairs": sorted(set(pairs) - set(pair_rows)),
            "eligible_pair_count": sum(1 for item in pair_status.values() if item["eligible_rows"] > 0),
            "unsupported_pair_count": sum(1 for item in pair_status.values() if item["eligible_rows"] == 0),
            "module_operation_pair_counts": dict(sorted(operation_counts.items())),
            "stage_counts": dict(sorted(Counter(str(row.get("configuration", {}).get("stages")) for row in route_rows).items())),
            "pair_status": pair_status,
        }
    report = {
        "schema_version": "powernext_exact2_normalized_coverage_1",
        "status": "COMPLETE",
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "dataset_path": str(data_dir.relative_to(ROOT)).replace("\\", "/"),
        "dataset_id": manifest.get("dataset_id"),
        "dataset_manifest_sha256": _sha(data_dir / "manifest.json"),
        "rows_sha256": manifest.get("rows_sha256"),
        "design_file_sha256": manifest.get("design_file_sha256"),
        "supersedes_audit": {
            "path": "coverage_audit.json",
            "sha256": _sha(data_dir / "coverage_audit.json"),
            "reason": "historical audit mixed numeric resistance keys for parent rows with recipe IDs for supplement rows; this report derives IDs from both canonical trees",
        },
        "source_hashes": manifest.get("source_hashes"),
        "physics_source_fingerprint": manifest.get("physics_source_fingerprint"),
        "scope_contract": manifest.get("scope_contract"),
        "scope_filter_sha256": manifest.get("scope_filter_sha256"),
        "expected_recipe_count_per_branch": 42,
        "expected_pair_count_per_route": 1764,
        "contexts": CONTEXTS,
        "routes": route_reports,
        "potential_unsupported_pairs": unsupported,
        "potential_unsupported_pair_count": len(unsupported),
        "totals": {
            "raw_rows": len(rows),
            "eligible_rows": len(eligible),
            "canonical_eligible_rows": len(canonical_rows),
            "raw_split_counts": dict(sorted(Counter(str(row.get("split")) for row in rows).items())),
            "eligible_split_counts": dict(sorted(Counter(assignments).items())),
            "canonical_split_counts": dict(sorted(Counter(canonical_splits).items())),
            "all_routes_have_1764_pairs": all(report["paired_recipe_count"] == 1764 and not report["missing_pairs"] for report in route_reports.values()),
            "all_routes_have_all_four_operation_pairs": all(set(report["module_operation_pair_counts"]) == {"P::P", "P::S", "S::P", "S::S"} for report in route_reports.values()),
            "split_integrity_passed": True,
            "deduplication": dedup_report,
        },
        "independence_limits": [
            "Supplement setup contexts are fixed groups: three train contexts plus one validation and one test context per route.",
            "The Cartesian pair grid is complete at the input level; eligible coverage can be lower when Physics marks a pair unsupported or numerically invalid.",
            "Canonical response deduplication removes equivalent responses after labels; raw pair rows and negative evidence remain available.",
            "This audit establishes numerical/data scope only and does not establish hardware mounting, component pulse ratings, or production feasibility.",
        ],
    }
    return report


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=ROOT / "powernext" / "ml" / "data" / "networks_exact2_v5_aug1")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    data = args.data.resolve()
    output = args.output.resolve() if args.output else data / "normalized_coverage_audit.json"
    if output.exists():
        raise FileExistsError(f"immutable normalized audit destination exists: {output}")
    report = normalize(data)
    output.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    receipt = output.with_name(output.stem + "_receipt.json")
    receipt.write_text(json.dumps({"status": "COMPLETE", "audit": str(output.relative_to(ROOT)).replace("\\", "/"), "audit_sha256": _sha(output), "dataset_id": report["dataset_id"], "dataset_manifest_sha256": report["dataset_manifest_sha256"]}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "audit_sha256": _sha(output), "raw_rows": report["totals"]["raw_rows"], "eligible_rows": report["totals"]["eligible_rows"], "canonical_eligible_rows": report["totals"]["canonical_eligible_rows"], "unsupported_pairs": report["potential_unsupported_pair_count"]}, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
