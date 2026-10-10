"""Frozen request oracles and measured search comparisons, distinct from training.

Validation oracles may select models. Final benchmark requests use another seed
and never modify a selection. Counts describe the declared benchmark catalogs.
"""
from __future__ import annotations
import argparse
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
import numpy as np
from . import ROOT
from .optimizer import recommend, _scalar_scores, load_predictor
from .physics import source_fingerprint
from .profiles import get_profile
from .catalog import Catalog


def execution_contract():
    """Bind oracle labels/indexing/scoring and their numerical runtime."""
    from .registry import runtime_versions
    runtime=runtime_versions()
    return dict(sources={name:hashlib.sha256((ROOT/"powernext_v3"/name).read_bytes()).hexdigest()
        for name in ("optimizer.py","catalog.py","features.py","benchmark.py")},
        runtime={name:runtime[name] for name in ("python","numpy","scipy")})


def log(message):
    print(f"[{datetime.now(timezone.utc).isoformat()}] {message}",flush=True)


def frozen_requests(purpose="validation", max_modules=2, cases_per_route=2, seed=None):
    if purpose not in ("validation","test"):raise ValueError("Unknown benchmark partition")
    rng=np.random.default_rng((20261101 if purpose=="validation" else 20261102) if seed is None else seed)
    identity_prefix=f"FROZEN_{purpose}" if seed is None else f"FROZEN_{purpose}_seed{seed}"
    requests=[]
    for domain in ("cpri_0p5uf","research_3uf"):
        for mode in ("LI","SI"):
            for top in ("GSHUNT_v0","OSHUNT_v0"):
                for k in range(cases_per_route):
                    # Input-only design, frozen before any candidate is simulated.
                    setup=dict(dut_capacitance_F=float(rng.uniform(.35,1.6)*1e-9),divider_capacitance_F=float(rng.uniform(.25,.65)*1e-9),
                        stray_capacitance_F=float(rng.uniform(.04,.3)*1e-9),loop_inductance_H=float(rng.uniform(5,75)*1e-6),
                        loop_resistance_ohm=float(rng.uniform(0,5)),basic_coverage_assumption="ADDITIONAL_DISJOINT",
                        setup_id=f"{identity_prefix}_{domain}_{mode}_{top}_{k}")
                    requests.append(dict(schema_version="network_request_v3",request_id=setup["setup_id"],domain_id=domain,
                        impulse_type=mode,topology_id=top,setup=setup,target_crest_V=float(rng.choice([750000.,1000000.,1300000.,1550000.])),
                        stages=[6,9,12],min_modules=2,max_modules=max_modules,search_mode="complete",priority="complete_physics",budget_seconds=7200,
                        alternatives=4,max_ml_candidates=100000,max_physics_evaluations=100000))
    return requests


def _oracle_task(request):
    result,_=recommend(request,retain_waveforms=False)
    if not result["search"]["catalog_complete"]:raise RuntimeError("Oracle did not complete declared catalog")
    rows=[]
    for row in result["candidates"]:
        m=row.get("physics")
        metrics=m["metrics"] if m else {}
        rows.append(dict(catalog_index=row["catalog_index"],configuration=row["configuration"],
            compliant=row["compliant"],score=row["score"],verification_status=row["verification_status"],
            gain=m["voltage_gain"] if m else None,
            front_us=None if not metrics.get("T1_s" if request["impulse_type"]=="LI" else "Tp_s") else metrics["T1_s" if request["impulse_type"]=="LI" else "Tp_s"]*1e6,
            tail_us=None if not metrics.get("T2_s") else metrics["T2_s"]*1e6,
            reason_codes=row["reason_codes"]))
    rows.sort(key=lambda row: row["catalog_index"])
    return dict(request=result["request"],search=result["search"],candidates=rows)


def generate_oracles(output,purpose="validation",max_modules=2,cases_per_route=2,workers=4,seed=None):
    output=Path(output)
    requests=frozen_requests(purpose,max_modules,cases_per_route,seed=seed)
    output.mkdir(parents=True,exist_ok=False)
    (output/"requests.json").write_text(json.dumps(requests,indent=2),encoding="utf-8")
    fingerprint=source_fingerprint()
    contract=execution_contract()
    manifest=dict(schema_version="optimization_oracles_v3",purpose=purpose,status="IN_PROGRESS",
        physics=fingerprint,execution_contract=contract,request_seed=seed,
        requests_sha256=hashlib.sha256((output/"requests.json").read_bytes()).hexdigest(),cases=[])
    (output/"manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    log(f"Generating {len(requests)} complete declared-catalog {purpose} oracles with {workers} workers")
    with ProcessPoolExecutor(max_workers=workers) as pool:
        futures=[pool.submit(_oracle_task,q) for q in requests]
        while futures:
            pending=[]
            for future in futures:
                if not future.done():pending.append(future);continue
                case=future.result()
                name=case["request"]["request_id"]+".json"
                path=output/name
                path.write_text(json.dumps(case,separators=(",",":"),allow_nan=False),encoding="utf-8")
                manifest["cases"].append(dict(path=name,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                    route=f"{case['request']['domain_id']}:{case['request']['impulse_type']}:{case['request']['topology_id']}",
                    candidates=len(case["candidates"]),passes=case["search"]["passing_count"],unsupported=case["search"]["unsupported_count"]))
                (output/"manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
                log(f"Oracle {name}: {len(case['candidates'])} candidates, {case['search']['passing_count']} passing")
            futures=pending
            if futures:
                log(f"Oracle jobs live: {len(futures)} remaining")
                time.sleep(15)
    if source_fingerprint()!=fingerprint:raise RuntimeError("Physics source changed during oracle generation")
    if execution_contract()!=contract:raise RuntimeError("Oracle execution contract changed during generation")
    manifest["status"]="COMPLETE"
    manifest["cases"].sort(key=lambda c:c["path"])
    (output/"manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    return manifest


class OracleValidation:
    """Fitted-model hook for independent request-level model selection."""
    def __init__(self,directory):
        self.directory=Path(directory)
        self.manifest=json.loads((self.directory/"manifest.json").read_text())
        if self.manifest["purpose"]!="validation" or self.manifest["status"]!="COMPLETE":raise ValueError("Require complete validation-only oracles")
        if self.manifest["physics"]!=source_fingerprint():raise ValueError("Oracle Physics sources differ")
        if self.manifest.get("execution_contract")!=execution_contract():
            raise ValueError("Oracle execution contract missing or incompatible; preserve historical evidence and regenerate a new oracle version")
        requests_bytes=(self.directory/"requests.json").read_bytes()
        if hashlib.sha256(requests_bytes).hexdigest()!=self.manifest["requests_sha256"]:
            raise ValueError("Frozen oracle requests changed")
        self.cache={}

    def __call__(self,model,validation_rows=None):
        from .features import feature_matrix
        route=f"{model.domain_id}:{model.mode}:{model.topology}"
        results=[]
        for record in self.manifest["cases"]:
            if record["route"]!=route:continue
            name=record["path"]
            if name not in self.cache:
                content=(self.directory/name).read_bytes()
                if hashlib.sha256(content).hexdigest()!=record["sha256"]:raise ValueError("Oracle changed")
                case=json.loads(content);q=case["request"]
                # Historical stored rows are Physics-ranked. Never allow that
                # answer order to become the tie-breaker for equal ML scores.
                rows=sorted(case["candidates"],key=lambda row: row["catalog_index"])
                case["candidates"]=rows
                configs=[r["configuration"] for r in rows]
                catalog=Catalog(q["max_modules"],q["stages"],min_modules=q.get("min_modules",2))
                if case.get("search",{}).get("catalog_sha256")!=catalog.identity:
                    raise ValueError("Oracle catalog identity differs")
                if [r["catalog_index"] for r in rows]!=list(range(catalog.count)):
                    raise ValueError("Oracle does not cover its complete declared catalog exactly once")
                expected_n,expected_f,expected_t=catalog.decode(np.arange(catalog.count))
                if not (np.array_equal(expected_n,[c["stages"] for c in configs]) and
                    np.allclose(expected_f,[c["front_per_stage_ohm"] for c in configs],rtol=1e-12,atol=0) and
                    np.allclose(expected_t,[c["tail_per_stage_ohm"] for c in configs],rtol=1e-12,atol=0)):
                    raise ValueError("Oracle configurations disagree with catalog indices")
                n=np.array([c["stages"] for c in configs])
                features=feature_matrix(n,[c["front_per_stage_ohm"] for c in configs],[c["tail_per_stage_ohm"] for c in configs],
                    q["setup"],q["domain_id"],q["impulse_type"],q["topology_id"])
                self.cache[name]=(case,features,n)
            case,features,n=self.cache[name]
            start=time.perf_counter();pred=model.predict(features);predict_seconds=time.perf_counter()-start
            scores=_scalar_scores(pred,n,case["request"],get_profile(model.domain_id))
            order=np.argsort(scores,kind="stable")
            truth_pass=np.array([r["compliant"] for r in case["candidates"]],bool)
            hits=np.flatnonzero(truth_pass[order])
            best=min((r["score"]["J"] for r in case["candidates"] if r["compliant"]),default=None)
            reg={}
            for k in (1,3,5,10,25,50,100):
                subset=[case["candidates"][int(i)] for i in order[:k] if truth_pass[int(i)]]
                reg[str(k)]=None if best is None or not subset else min(r["score"]["J"] for r in subset)-best
            results.append(dict(request_id=case["request"]["request_id"],candidate_count=len(order),feasible_count=int(truth_pass.sum()),
                first_feasible_rank=int(hits[0]+1) if len(hits) else None,
                hit_at_k={str(k):bool(truth_pass[order[:k]].any()) for k in (1,3,5,10,25,50,100)},
                regret_at_k=reg,predict_seconds=predict_seconds,
                candidates_per_second=len(order)/predict_seconds))
        feasible=[r for r in results if r["feasible_count"]]
        missing=sum(not r["hit_at_k"]["5"] for r in feasible)
        regrets=[r["regret_at_k"]["25"] for r in feasible if r["regret_at_k"]["25"] is not None]
        return dict(status="COMPLETE_INDEPENDENT_PHYSICS_ORACLE_VALIDATION" if results else "UNAVAILABLE_NO_ROUTE_ORACLES",
            request_count=len(results),feasible_request_count=len(feasible),missed_feasible_at_5=missing,
            feasible_hit_at_5=None if not feasible else 1-missing/len(feasible),
            mean_regret_at_25=None if not regrets else float(np.mean(regrets)),
            retention=None if not feasible else 1-missing/len(feasible),cases=results)


def _peak_memory_bytes():
    """OS process peak, including native arrays; cumulative high-water mark."""
    import os
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        class MemoryCounters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
                (name, ctypes.c_size_t) for name in ("PeakWorkingSetSize", "WorkingSetSize",
                    "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage",
                    "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]
        data = MemoryCounters(); data.cb = ctypes.sizeof(data)
        get_process = ctypes.windll.kernel32.GetCurrentProcess
        get_process.restype = wintypes.HANDLE
        query = ctypes.windll.psapi.GetProcessMemoryInfo
        query.argtypes = [wintypes.HANDLE, ctypes.POINTER(MemoryCounters), wintypes.DWORD]
        if not query(get_process(), ctypes.byref(data), data.cb):
            return None
        return int(data.PeakWorkingSetSize)
    import resource
    return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024)


def run_policy_benchmarks(output, registry=None, selection=None, cases_per_route=2,
                          max_modules=2, physics_budget=256, pool_budget=65536, seed=None):
    """Sequential timed runs on frozen test requests, never a selection hook.

    All policies share each request's exact declared catalog. Adaptive policies
    have a fixed verification budget. Full Physics is optimized by linear reuse.
    Model loading is measured separately; controller times use a loaded model.
    Peak process memory is a cumulative native OS high-water mark, not a delta.
    """
    output = Path(output); output.mkdir(parents=True, exist_ok=False)
    requests = frozen_requests("test", max_modules, cases_per_route,seed=seed)
    # The known rare-LI regression is named separately from unseen test cases.
    rare_path = ROOT / "powernext/optimizer/examples/LI_rare_timing_pass_recommendation.json"
    rare = json.loads(rare_path.read_text(encoding="utf-8"))["request"]
    requests.append(dict(schema_version="network_request_v3", request_id="KNOWN_RARE_LI_SETUP_EXACT2",
        domain_id="cpri_0p5uf", impulse_type="LI", topology_id="GSHUNT_v0",
        setup=rare["setup"], target_crest_V=1000000., min_modules=2, max_modules=2,
        search_mode="complete", priority="complete_physics", budget_seconds=7200,
        alternatives=4, max_ml_candidates=pool_budget, max_physics_evaluations=physics_budget))
    (output / "requests.json").write_text(json.dumps(requests, indent=2), encoding="utf-8")
    pinned = source_fingerprint()
    manifest = dict(schema_version="search_policy_benchmark_v3", purpose="test", status="IN_PROGRESS",
        physics=pinned, execution_contract=execution_contract(), request_seed=seed, requests_sha256=hashlib.sha256((output/"requests.json").read_bytes()).hexdigest(),
        timing_protocol="Sequential policies in declared order after explicit shared catalog/feature/model warm-up; loaded-model search latency; first-route/reused-route loading separately labeled; not cold application startup; no concurrent benchmark workers",
        memory_protocol="Cumulative OS process peak working set including native arrays; not per-policy incremental allocation",
        physics_budget=physics_budget, pool_budget=pool_budget, cases=[])
    manifest_path=output/"manifest.json"
    manifest_path.write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    seen_routes=set()
    for q in requests:
        log(f"Benchmark starting {q['request_id']}")
        load_start=time.perf_counter()
        model,card=load_predictor(q,registry,selection)
        load_seconds=time.perf_counter()-load_start
        route=(q["domain_id"],q["impulse_type"],q["topology_id"])
        load_state="ROUTE_PREVIOUSLY_LOADED" if route in seen_routes else "FIRST_REQUEST_FOR_ROUTE"
        seen_routes.add(route)
        # Pay shared import/catalog construction and initial native prediction
        # setup before any timed policy, instead of favoring later policies.
        from .features import feature_matrix
        warm_start=time.perf_counter()
        warm_catalog=Catalog(q["max_modules"],q.get("stages"),min_modules=q.get("min_modules",2))
        warm_n,warm_f,warm_t=warm_catalog.decode(np.arange(min(32,warm_catalog.count)))
        warm_x=feature_matrix(warm_n,warm_f,warm_t,q["setup"],*route)
        model.predict(warm_x);model.ood(warm_x)
        warm_seconds=time.perf_counter()-warm_start
        policies=[]; oracle_passes=None; oracle_best=None
        for policy in ("complete_physics","analytical","ml","combined"):
            request=dict(q, priority=policy, search_mode="complete" if policy=="complete_physics" else "adaptive",
                max_ml_candidates=pool_budget, max_physics_evaluations=physics_budget)
            result,_=recommend(request,model=model if policy in ("ml","combined") else None,
                model_card=card if policy in ("ml","combined") else None,retain_waveforms=False,
                progress=lambda message: log(f"{q['request_id']} {policy}: {message}") if "Physics verified" in message else None)
            if result["search"]["effective_strategy"]!=policy:
                raise RuntimeError(f"Benchmark policy unexpectedly fell back: {policy}")
            passed={r["catalog_index"] for r in result["candidates"] if r["compliant"]}
            best=result["best_configuration"]
            best_j=None if best is None else best["score"]["J"]
            if policy=="complete_physics":
                if not result["search"]["catalog_complete"]:raise RuntimeError("Benchmark reference incomplete")
                oracle_passes=passed;oracle_best=best_j
            if not passed.issubset(oracle_passes):raise RuntimeError("Adaptive Physics passes disagree with complete reference")
            metrics=dict(policy=policy,status=result["status"],search=result["search"],best_objective=best_j,
                best_candidate_id=None if best is None else best["candidate_id"],
                best_configuration=None if best is None else best["configuration"],
                oracle_feasible_count=len(oracle_passes),feasible_candidates_found=len(passed),
                feasible_candidate_retention=None if not oracle_passes else len(passed)/len(oracle_passes),
                feasible_request_retained=None if not oracle_passes else bool(passed),
                missed_feasible_request=bool(oracle_passes and not passed),
                regret=None if best_j is None or oracle_best is None else best_j-oracle_best,
                process_peak_memory_bytes=_peak_memory_bytes(),
                model_loading_seconds=load_seconds if policy in ("ml","combined") else 0,
                model_loading_cache_context=load_state,shared_warmup_seconds=warm_seconds,
                model_loading_shared_between_ml_and_combined=True,
                ml_candidates_per_scoring_second=None if not result["search"]["ml_predicted_count"] else
                    result["search"]["ml_predicted_count"]/max(result["search"]["scoring_seconds"],1e-12))
            policies.append(metrics)
            log(f"Benchmark {q['request_id']} {policy}: {len(passed)} passes, {result['search']['total_seconds']:.3f}s")
        case=dict(request=q,model=card,policies=policies)
        path=output/(q["request_id"]+".json")
        path.write_text(json.dumps(case,indent=2,allow_nan=False),encoding="utf-8")
        manifest["cases"].append(dict(path=path.name,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            route=f"{q['domain_id']}:{q['impulse_type']}:{q['topology_id']}",known_regression=q["request_id"].startswith("KNOWN_")))
        manifest_path.write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    if source_fingerprint()!=pinned:raise RuntimeError("Physics changed during benchmarks")
    if execution_contract()!=manifest["execution_contract"]:raise RuntimeError("Benchmark execution contract changed")
    manifest["status"]="COMPLETE"
    manifest_path.write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    write_policy_report(output)
    return manifest


def write_policy_report(directory):
    directory=Path(directory)
    manifest=json.loads((directory/"manifest.json").read_text(encoding="utf-8"))
    if manifest.get("status")!="COMPLETE" or manifest.get("purpose")!="test":
        raise ValueError("Only completed final benchmark evidence can be summarized")
    cases=[]
    for record in manifest["cases"]:
        content=(directory/record["path"]).read_bytes()
        if hashlib.sha256(content).hexdigest()!=record["sha256"]:raise ValueError("Benchmark case changed")
        cases.append(json.loads(content))
    def number(value):return "unavailable" if value is None else f"{value:.4g}"
    lines=["# Four-policy search benchmark", "", "These are measured runs over identical declared catalogs for each fixed request. "
        "Final test requests use a separate input seed from model selection. The known rare-LI regression is labeled separately.", "",
        "The complete reference reuses linear waveform scaling. Adaptive policies have the recorded candidate-pool and Physics budgets; "
        "they do not establish a global optimum. All reported passing candidates were verified by the detailed simulator.", "",
        "Timing protocol: "+manifest["timing_protocol"]+".", "", "Memory protocol: "+manifest["memory_protocol"]+".", "",
        "| Request | Policy | First pass, s | Four passes, s | Total, s | Physics calls | ML predictions | Passes found/reference | Best J | Regret |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for case in cases:
        for row in case["policies"]:
            s=row["search"]
            lines.append(f"| {case['request']['request_id']} | {row['policy']} | {number(s['time_to_first_pass_seconds'])} | "
                f"{number(s['time_to_alternatives_seconds'])} | {number(s['total_seconds'])} | {s['physics_evaluated_count']} | "
                f"{s['ml_predicted_count']} | {row['feasible_candidates_found']}/{row['oracle_feasible_count']} | "
                f"{number(row['best_objective'])} | {number(row['regret'])} |")
    lines += ["", "## Paired discovery outcomes", "", "A missing pass time is not zero. Ratios below use only cases where both policies found a pass; "
        "missed feasible requests are listed separately to avoid hiding failures. A ratio above one means the adaptive policy reached its first pass sooner.", "",
        "| Policy | Feasible test requests | Missed feasible requests | Paired first-pass timings | Median complete/adaptive time ratio |",
        "|---|---:|---:|---:|---:|"]
    unseen=[case for case in cases if not case["request"]["request_id"].startswith("KNOWN_")]
    for policy in ("analytical","ml","combined"):
        rows=[next(row for row in case["policies"] if row["policy"]==policy) for case in unseen]
        feasible=sum(row["oracle_feasible_count"]>0 for row in rows)
        missed=sum(row["missed_feasible_request"] for row in rows)
        ratios=[]
        for case,row in zip(unseen,rows):
            base=case["policies"][0]["search"]["time_to_first_pass_seconds"]
            adaptive=row["search"]["time_to_first_pass_seconds"]
            if base is not None and adaptive is not None and adaptive>0:ratios.append(base/adaptive)
        lines.append(f"| {policy} | {feasible} | {missed} | {len(ratios)} | {number(float(np.median(ratios)) if ratios else None)} |")
    lines += ["", "Per-case JSON includes OOD and unsupported counts, complete/partial coverage, model-loading time, "
        "scoring throughput and process peak memory. These results describe this runtime, input set and declared catalog; "
        "they establish no general speedup over every electrical setup or four-module search. No real-hardware validation is claimed.", ""]
    (directory/"report.md").write_text("\n".join(lines),encoding="utf-8")


def run_four_module_smoke(output, registry=None, selection=None, physics_budget=256, pool_budget=65536):
    """Exercise actual trained routing against the full declared four-module catalog.

    This is bounded acceptance evidence, without a complete-reference regret or
    optimality claim. Requests are frozen before evaluation and never select models.
    """
    output=Path(output); output.mkdir(parents=True,exist_ok=False)
    requests=frozen_requests("test",4,1)
    for q in requests:
        q.update(request_id=q["request_id"]+"_FOUR_MODULE",stages=list(range(2,16)),
            search_mode="adaptive",priority="combined",budget_seconds=180,
            max_ml_candidates=pool_budget,max_physics_evaluations=physics_budget)
    payload=json.dumps(requests,indent=2)
    (output/"requests.json").write_text(payload,encoding="utf-8")
    manifest=dict(schema_version="four_module_acceptance_v3",status="IN_PROGRESS",purpose="test",
        physics=source_fingerprint(),execution_contract=execution_contract(),requests_sha256=hashlib.sha256(payload.encode()).hexdigest(),cases=[])
    for q in requests:
        log("Four-module acceptance "+q["request_id"])
        result,_=recommend(q,registry=registry,selection=selection,retain_waveforms=False)
        search=result["search"]
        if search["effective_strategy"]!="combined" or search["ml_predicted_count"]<=0:
            raise RuntimeError("Four-module acceptance requires the actual selected ML model")
        if any(not r["compliant"] for r in [result["best_configuration"]] if r):
            raise RuntimeError("A failed configuration was selected")
        path=output/(q["request_id"]+".json")
        path.write_text(json.dumps(result,indent=2,allow_nan=False),encoding="utf-8")
        manifest["cases"].append(dict(path=path.name,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            status=result["status"],search=search,process_peak_memory_bytes=_peak_memory_bytes()))
        (output/"manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
        log(f"Four-module result {result['status']}: {search['ml_predicted_count']} ML predictions, {search['physics_evaluated_count']} Physics evaluations")
    if source_fingerprint()!=manifest["physics"]:raise RuntimeError("Physics changed during acceptance")
    if execution_contract()!=manifest["execution_contract"]:raise RuntimeError("Acceptance execution contract changed")
    manifest["status"]="COMPLETE"
    (output/"manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
    return manifest


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("command",choices=["oracles","policies"])
    parser.add_argument("--output",required=True)
    parser.add_argument("--purpose",choices=["validation","test"],default="validation")
    parser.add_argument("--max-modules",type=int,choices=[2],default=2)
    parser.add_argument("--cases-per-route",type=int,default=2)
    parser.add_argument("--workers",type=int,default=4)
    parser.add_argument("--seed",type=int,help="Freeze a new independent request design; omit to reproduce the historical design")
    parser.add_argument("--registry")
    parser.add_argument("--selection")
    parser.add_argument("--physics-budget",type=int,default=256)
    parser.add_argument("--pool-budget",type=int,default=65536)
    args=parser.parse_args()
    if args.command=="oracles":
        generate_oracles(args.output,args.purpose,args.max_modules,args.cases_per_route,args.workers,args.seed)
    elif args.command=="policies":
        run_policy_benchmarks(args.output,args.registry,args.selection,args.cases_per_route,
            args.max_modules,args.physics_budget,args.pool_budget,args.seed)
    else:
        run_four_module_smoke(args.output,args.registry,args.selection,args.physics_budget,args.pool_budget)


if __name__=="__main__":main()
