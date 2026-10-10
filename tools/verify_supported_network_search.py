"""Bounded acceptance for the current two/three-module public search scope.

This uses frozen test requests and existing selected models. It performs no
training, dataset generation, or complete-catalog optimality claim.
"""
from pathlib import Path
import argparse
import hashlib
import json

from powernext_v3.benchmark import execution_contract, frozen_requests, log
from powernext_v3.networks import canonicalize
from powernext_v3.optimizer import recommend
from powernext_v3.physics import source_fingerprint


def leaves(tree):
    tree = canonicalize(tree)
    return 1 if tree["op"] == "R" else sum(leaves(child) for child in tree["children"])


def run(output, registry, selection, modules=3, physics_budget=256, pool_budget=65536):
    if modules not in (2, 3):
        raise ValueError("Only two/three-module acceptance is supported")
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    requests = frozen_requests("test", modules, 1)
    for request in requests:
        request.update(request_id=request["request_id"] + f"_{modules}_MODULE_ACCEPTANCE",
            stages=list(range(2, 16)), search_mode="adaptive", priority="combined",
            budget_seconds=180, max_ml_candidates=pool_budget,
            max_physics_evaluations=physics_budget)
    payload = json.dumps(requests, indent=2)
    (output / "requests.json").write_text(payload, encoding="utf-8")
    manifest = dict(schema_version="supported_network_search_acceptance_v3",
        status="IN_PROGRESS", purpose="test", max_modules=modules,
        physics=source_fingerprint(), execution_contract=execution_contract(),
        requests_sha256=hashlib.sha256(payload.encode()).hexdigest(),
        script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        timing_scope="Functional acceptance under current machine load; not an isolated speed benchmark",
        cases=[])
    for request in requests:
        log("Supported network acceptance: " + request["request_id"])
        result, _ = recommend(request, registry=registry, selection=selection,
            retain_waveforms=False, progress=log)
        search = result["search"]
        if search["effective_strategy"] != "combined" or search["ml_predicted_count"] <= 0:
            raise RuntimeError("Actual selected ML participation is required")
        best = result["best_configuration"]
        if best is not None and not best["compliant"]:
            raise RuntimeError("A failed candidate became a recommendation")
        for row in result["candidates"]:
            for branch in ("front_network", "tail_network"):
                if leaves(row["configuration"][branch]) > modules:
                    raise RuntimeError("Candidate exceeds supported module scope")
        path = output / (request["request_id"] + ".json")
        path.write_text(json.dumps(result, indent=2, allow_nan=False), encoding="utf-8")
        manifest["cases"].append(dict(path=path.name,
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            status=result["status"], search=search))
        (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    if source_fingerprint() != manifest["physics"] or execution_contract() != manifest["execution_contract"]:
        raise RuntimeError("Numerical execution contract changed during acceptance")
    manifest["status"] = "COMPLETE"
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument("--registry", default="powernext/ml/registry/networks_v3")
    parser.add_argument("--selection", default="powernext/ml/results/networks_v3/selected_models.json")
    parser.add_argument("--modules", type=int, choices=(2, 3), default=3)
    parser.add_argument("--physics-budget", type=int, default=256)
    parser.add_argument("--pool-budget", type=int, default=65536)
    args = parser.parse_args()
    run(args.output, args.registry, args.selection, args.modules, args.physics_budget, args.pool_budget)
