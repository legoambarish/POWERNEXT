"""Run the sealed exact-two v5 full-catalog serving smoke benchmark.

The benchmark derives one fresh request per route from the sealed final-test
design, expands the uniform stage set to stages 2..15, scores all 42 x 42
exact-two front/tail recipe pairs with the selected v5 model, and verifies at
most 256 candidates with detailed Physics.  The request uses the optimizer's
bounded ``adaptive`` mode with a full ML-pool limit because ``complete`` mode
intentionally means complete Physics evaluation.  It does not write model
results, change selection, or use any output as training/selection input.

Run from the checkout root with the bundled runtime::

    runtime\\python.exe -B tools\\benchmark_exact2_v5_serving.py

The evidence file is written only after all eight routes pass.  A failed run
leaves an explicit ``FAILED`` evidence record with the completed-route list;
that record is never presented as a serving acceptance.
"""

from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import sys
import time
from typing import Any, Mapping, Sequence


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "powernext" / "ml" / "registry" / "networks_exact2_v5"
SELECTION = ROOT / "powernext" / "ml" / "results" / "networks_exact2_v5" / "selected_models.json"
SEALED_REQUESTS = ROOT / "evidence" / "exact2_v5" / "sealed_test_request_design.json"
DEFAULT_OUTPUT = ROOT / "evidence" / "exact2_v5" / "serving_benchmark.json"
ROUTES = tuple(
    f"{domain}:{mode}:{topology}"
    for domain in ("cpri_0p5uf", "research_3uf")
    for mode in ("LI", "SI")
    for topology in ("GSHUNT_v0", "OSHUNT_v0")
)
STAGES = tuple(range(2, 16))
RECIPES_PER_BRANCH = 42
CATALOG_COUNT = RECIPES_PER_BRANCH * RECIPES_PER_BRANCH * len(STAGES)
PHYSICS_BUDGET = 256
SCOPE_CONTRACT = "EXACT_MODULES_PER_BRANCH_V5"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def _route(request: Mapping[str, Any]) -> str:
    return f"{request.get('domain_id')}:{request.get('impulse_type')}:{request.get('topology_id')}"


def _leaf_count(tree: Any) -> int:
    if not isinstance(tree, Mapping):
        raise AssertionError("network tree is not an object")
    operation = tree.get("op")
    if operation == "R":
        if set(tree) != {"op", "ohm"}:
            raise AssertionError("resistor tree has unexpected fields")
        return 1
    if operation not in {"S", "P"}:
        raise AssertionError(f"invalid network operation: {operation!r}")
    children = tree.get("children")
    if not isinstance(children, list) or len(children) < 2:
        raise AssertionError("composite network tree has too few children")
    return sum(_leaf_count(child) for child in children)


def _load_sealed(path: Path) -> tuple[dict[str, Any], dict[str, str]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list) or len(raw) != len(ROUTES) * 2:
        raise AssertionError("sealed final-test design must contain two requests per route")
    by_route: dict[str, list[dict[str, Any]]] = {}
    for item in raw:
        if not isinstance(item, dict):
            raise AssertionError("sealed request is not an object")
        route = _route(item)
        by_route.setdefault(route, []).append(item)
    if set(by_route) != set(ROUTES) or any(len(items) != 2 for items in by_route.values()):
        raise AssertionError("sealed final-test design does not cover exactly two requests per route")
    selected: dict[str, dict[str, Any]] = {}
    source_ids: dict[str, str] = {}
    for route in ROUTES:
        items = by_route[route]
        # The frozen design uses ``_0`` and ``_1`` for its independent setup
        # cases.  Choose _0 deterministically without rewriting the source.
        item = next((candidate for candidate in items if str(candidate.get("request_id", "")).endswith("_0")), None)
        if item is None:
            item = sorted(items, key=lambda candidate: str(candidate.get("request_id", "")))[0]
        if item.get("min_modules") != 2 or item.get("max_modules") != 2:
            raise AssertionError(f"sealed request {route} is outside exact-two scope")
        selected[route] = copy.deepcopy(item)
        source_ids[route] = str(item.get("request_id"))
    return selected, source_ids


def _fresh_request(sealed: Mapping[str, Any], route: str) -> dict[str, Any]:
    request = copy.deepcopy(dict(sealed))
    request["request_id"] = f"EXACT2_V5_FRESH_FINAL_FULLCAT_{route.replace(':', '_')}"
    request["min_modules"] = 2
    request["max_modules"] = 2
    request["stages"] = list(STAGES)
    # ``complete`` is reserved for the full Physics oracle in the frozen
    # optimizer contract.  Adaptive mode with the exact catalog-sized ML
    # limit exhausts the model pool while retaining the explicit Physics cap.
    request["search_mode"] = "adaptive"
    request["priority"] = "combined"
    request["max_ml_candidates"] = CATALOG_COUNT
    request["max_physics_evaluations"] = PHYSICS_BUDGET
    # Preserve the sealed budget and setup, while making the serving limits
    # explicit in the derived request.
    request["alternatives"] = min(int(request.get("alternatives", 4)), 4)
    return request


def _assert_model_card(card: Mapping[str, Any], route: str, selected_id: str) -> None:
    if card.get("model_id") != selected_id:
        raise AssertionError(f"{route}: loaded model id does not match selected mapping")
    route_card = card.get("route")
    if not isinstance(route_card, Mapping):
        raise AssertionError(f"{route}: model card is missing route metadata")
    domain, mode, topology = route.split(":")
    expected = {"domain_id": domain, "mode": mode, "topology": topology}
    if any(route_card.get(key) != value for key, value in expected.items()):
        raise AssertionError(f"{route}: selected model card route mismatch")
    scope = card.get("provenance", {}).get("training_dataset_scope", {})
    if not isinstance(scope, Mapping) or scope.get("scope_contract") != SCOPE_CONTRACT or scope.get("exact_modules_per_branch") != 2:
        raise AssertionError(f"{route}: selected model does not carry exact-two scope provenance")


def _assert_result(result: Mapping[str, Any], route: str, selected_id: str) -> dict[str, Any]:
    if result.get("status") not in {"VERIFIED_COMPLIANT", "NO_COMPLIANT_CONFIGURATION_YET", "NO_COMPLIANT_CONFIGURATION_IN_DECLARED_CATALOG"}:
        raise AssertionError(f"{route}: unexpected result status {result.get('status')!r}")
    model = result.get("model")
    if not isinstance(model, Mapping):
        raise AssertionError(f"{route}: result did not use an ML model")
    _assert_model_card(model, route, selected_id)
    search = result.get("search")
    if not isinstance(search, Mapping):
        raise AssertionError(f"{route}: result has no search report")
    expected_counts = {
        "theoretical_recipe_configurations": CATALOG_COUNT,
        "distinct_response_candidates": CATALOG_COUNT,
        "ml_predicted_count": CATALOG_COUNT,
        "considered_count": CATALOG_COUNT,
        "physics_evaluated_count": PHYSICS_BUDGET,
    }
    for key, expected in expected_counts.items():
        if int(search.get(key, -1)) != expected:
            raise AssertionError(f"{route}: {key}={search.get(key)!r}, expected {expected}")
    if search.get("ml_pool_complete") is not True:
        raise AssertionError(f"{route}: ML pool was not complete")
    if search.get("catalog_complete") is not False:
        raise AssertionError(f"{route}: Physics budget unexpectedly claimed full catalog")
    candidates = result.get("candidates")
    if not isinstance(candidates, list) or len(candidates) != PHYSICS_BUDGET:
        raise AssertionError(f"{route}: candidate rows do not equal Physics budget")
    for candidate in candidates:
        configuration = candidate.get("configuration")
        if not isinstance(configuration, Mapping):
            raise AssertionError(f"{route}: candidate has no configuration")
        if _leaf_count(configuration.get("front_network")) != 2 or _leaf_count(configuration.get("tail_network")) != 2:
            raise AssertionError(f"{route}: candidate escaped exact-two front/tail scope")
    request = result.get("request")
    if not isinstance(request, Mapping) or list(request.get("stages", ())) != list(STAGES):
        raise AssertionError(f"{route}: result request does not cover stages 2..15")
    return {
        "route": route,
        "request_id": request.get("request_id"),
        "model_id": model.get("model_id"),
        "status": result.get("status"),
        "catalog_count": search.get("theoretical_recipe_configurations"),
        "distinct_response_candidates": search.get("distinct_response_candidates"),
        "ml_predicted_count": search.get("ml_predicted_count"),
        "physics_evaluated_count": search.get("physics_evaluated_count"),
        "passing_count": search.get("passing_count"),
        "unsupported_count": search.get("unsupported_count"),
        "catalog_complete": search.get("catalog_complete"),
        "ml_pool_complete": search.get("ml_pool_complete"),
        "effective_strategy": search.get("effective_strategy"),
        "total_seconds": search.get("total_seconds"),
        "scoring_seconds": search.get("scoring_seconds"),
        "verification_seconds": search.get("verification_seconds"),
        "best_candidate_id": (result.get("best_configuration") or {}).get("candidate_id"),
        "best_compliant": bool(result.get("best_configuration")),
    }


def run(*, output: Path = DEFAULT_OUTPUT, sealed_path: Path = SEALED_REQUESTS, registry: Path = REGISTRY, selection: Path = SELECTION) -> dict[str, Any]:
    started = time.perf_counter()
    sealed, source_ids = _load_sealed(sealed_path)
    selected_models = json.loads(selection.read_text(encoding="utf-8"))
    if not isinstance(selected_models, dict) or set(selected_models) != set(ROUTES):
        raise AssertionError("selected_models.json must contain exactly eight v5 routes")
    if len(set(selected_models.values())) != len(ROUTES):
        raise AssertionError("selected_models.json must contain eight distinct model IDs")
    evidence: dict[str, Any] = {
        "schema_version": "exact2_v5_full_catalog_serving_benchmark_v1",
        "status": "RUNNING",
        "scope": "EXACTLY_TWO_RESISTORS_EACH_FRONT_AND_TAIL_SERIES_OR_PARALLEL",
        "routes_expected": len(ROUTES),
        "stages": list(STAGES),
        "recipes_per_branch": RECIPES_PER_BRANCH,
        "theoretical_recipe_configurations_per_route": CATALOG_COUNT,
        "physics_budget_per_route": PHYSICS_BUDGET,
        "serving_search_mode": "adaptive_full_ml_pool_physics_bounded",
        "sealed_request_design": str(sealed_path.relative_to(ROOT)),
        "sealed_request_design_sha256": _sha256(sealed_path),
        "selection_path": str(selection.relative_to(ROOT)),
        "selection_sha256": _sha256(selection),
        "registry_path": str(registry.relative_to(ROOT)),
        "selected_models": selected_models,
        "sealed_source_request_ids": source_ids,
        "routes": [],
        "selection_used_for_training": False,
        "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    try:
        from powernext_v3.optimizer import recommend

        for index, route in enumerate(ROUTES, 1):
            request = _fresh_request(sealed[route], route)
            selected_id = selected_models[route]
            route_started = time.perf_counter()

            def progress(message: str, *, _route=route) -> None:
                print(f"[{datetime.now(timezone.utc).isoformat(timespec='seconds')}] {_route} {message}", flush=True)

            print(f"[{datetime.now(timezone.utc).isoformat(timespec='seconds')}] route {index}/{len(ROUTES)} start {route}", flush=True)
            result, _waveforms = recommend(
                request,
                registry=registry,
                selection=selection,
                progress=progress,
                retain_waveforms=False,
            )
            row = _assert_result(result, route, selected_id)
            row["elapsed_wall_seconds"] = time.perf_counter() - route_started
            evidence["routes"].append(row)
            print(f"[{datetime.now(timezone.utc).isoformat(timespec='seconds')}] {route} PASS", flush=True)
        evidence["status"] = "PASS"
    except BaseException as exc:
        evidence["status"] = "FAILED"
        evidence["failure"] = {"type": type(exc).__name__, "message": str(exc)}
        raise
    finally:
        evidence["completed_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        evidence["elapsed_wall_seconds"] = time.perf_counter() - started
        _write_json(output, evidence)
    return evidence


def main(argv: Sequence[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--sealed", type=Path, default=SEALED_REQUESTS)
    parser.add_argument("--registry", type=Path, default=REGISTRY)
    parser.add_argument("--selection", type=Path, default=SELECTION)
    args = parser.parse_args(argv)
    run(
        output=args.output,
        sealed_path=args.sealed,
        registry=args.registry,
        selection=args.selection,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
