"""ML-prioritized, Physics-verified bounded network optimization.

The candidate pool and the Physics verification can both be partial. Counts and
termination reasons describe each separately. Predicted failure is never a
permanent exclusion, and a failed candidate is never a recommendation.
"""
from __future__ import annotations
import copy
import hashlib
import itertools
import json
import math
import time
from pathlib import Path
import numpy as np
from physics_engine.network import PhysicsError
from physics_engine.evaluator import LIMITS
from powernext_optimizer.assessment import parameter_score
from . import ROOT
from .catalog import Catalog
from .physics import derive, simulate, scale_response, source_fingerprint
from .profiles import get_profile

REGISTRY = ROOT / "powernext/ml/registry/networks_v3"
SELECTION = ROOT / "powernext/ml/results/networks_v3/selected_models.json"


def _digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,allow_nan=False,separators=(",",":")).encode()).hexdigest()


def normalize_request(raw):
    if not isinstance(raw,dict):raise ValueError("Request must be an object")
    allowed={"schema_version","request_id","domain_id","impulse_type","topology_id","target_crest_V","setup","polarity",
        "max_modules","stages","search_mode","priority","max_ml_candidates","max_physics_evaluations","budget_seconds",
        "alternatives","inventory","assumptions","charge_min_V","charge_step_V","charge_grid_origin_V"}
    unknown=set(raw)-allowed
    if unknown:raise ValueError("Unknown request fields: "+", ".join(sorted(unknown)))
    q=copy.deepcopy(raw)
    q.setdefault("schema_version","network_request_v3")
    if q["schema_version"]!="network_request_v3":raise ValueError("Expected network_request_v3")
    q.setdefault("request_id","NETWORK_SEARCH")
    q.setdefault("domain_id","cpri_0p5uf")
    q.setdefault("topology_id","GSHUNT_v0")
    q.setdefault("polarity",1)
    q.setdefault("max_modules",4)
    q.setdefault("search_mode","adaptive")
    q.setdefault("priority","combined")
    q.setdefault("max_ml_candidates",65536)
    q.setdefault("max_physics_evaluations",512)
    q.setdefault("budget_seconds",90.)
    q.setdefault("alternatives",4)
    q.setdefault("assumptions",[])
    q.setdefault("inventory",None)
    if q["search_mode"] not in ("adaptive","complete"):raise ValueError("Choose adaptive or complete search")
    if q["priority"] not in ("complete_physics","analytical","ml","combined"):raise ValueError("Invalid priority policy")
    for name,lo,hi in (("max_modules",1,4),("max_ml_candidates",1,2000000),("max_physics_evaluations",1,1000000),("alternatives",1,20)):
        if type(q[name]) is not int or not lo<=q[name]<=hi:raise ValueError(f"{name} must be an integer in [{lo}, {hi}]")
    target=q.get("target_crest_V")
    if type(target) not in (int,float) or not math.isfinite(target) or not 50000<=target<=2400000:
        raise ValueError("Explicit requested impulse crest must be 50–2400 kV; equipment class is a separate quantity")
    if type(q["budget_seconds"]) not in (int,float) or not math.isfinite(q["budget_seconds"]) or not .1<=q["budget_seconds"]<=86400:
        raise ValueError("budget_seconds must be finite in [0.1, 86400]")
    if not isinstance(q["request_id"],str) or len(q["request_id"])>200:raise ValueError("Invalid request_id")
    if not isinstance(q["assumptions"],list) or any(not isinstance(x,str) for x in q["assumptions"]):raise ValueError("Assumptions must be text list")
    p=get_profile(q["domain_id"])
    catalog=Catalog(q["max_modules"],q.get("stages"))
    q["stages"]=list(catalog.stages)
    probe=dict(impulse_type=q.get("impulse_type"),stages=catalog.stages[0],stage_charge_V=100000.,
        front_per_stage_ohm=30.,tail_per_stage_ohm=180.,topology_id=q["topology_id"],polarity=q["polarity"])
    derive(probe,q.get("setup",{}),q["domain_id"])
    if q["inventory"] is not None:
        if not isinstance(q["inventory"],dict):raise ValueError("Inventory must be an explicit part-to-count mapping or null")
        catalog.physical(0,q["inventory"])
    for key in ("charge_min_V","charge_step_V","charge_grid_origin_V"):
        value=q.get(key)
        if value is not None and (type(value) not in (int,float) or not math.isfinite(value) or value<0 or (key=="charge_step_V" and value==0)):
            raise ValueError(key+" must be a valid explicit charging constraint")
    if q.get("charge_min_V",0)>p.stage_charge_max_V:raise ValueError("Charging minimum exceeds domain maximum")
    return q,catalog


def _charge_max(stages,p):
    return min(p.stage_charge_max_V,p.summed_charge_max_V/stages,
        math.sqrt(2*p.stage_energy_max_J/p.stage_capacitance_F),
        math.sqrt(2*p.total_energy_max_J/(stages*p.stage_capacitance_F)))


def _charge_choices(gain,n,q,p):
    high=_charge_max(n,p)
    low=q.get("charge_min_V") or 0.
    ideal=q["target_crest_V"]/(n*gain) if gain>0 else high
    clipped=min(high,max(low,ideal))
    step=q.get("charge_step_V")
    if step is None:return [clipped] if clipped>0 else []
    origin=q.get("charge_grid_origin_V") or 0.
    first=math.ceil((low-origin)/step)
    if origin+first*step<=0:first+=1
    last=math.floor((high-origin)/step)
    if last<first:return []
    at=(ideal-origin)/step
    return sorted({origin+min(last,max(first,k))*step for k in (math.floor(at),math.ceil(at))})


def _scalar_scores(pred,stages,q,p):
    pred=np.asarray(pred,float)
    g,front,tail=pred.T
    caps=np.array([_charge_max(int(n),p) for n in stages])
    charge=np.minimum(caps,q["target_crest_V"]/np.maximum(g*stages,1e-30))
    if q.get("charge_min_V") is not None:charge=np.maximum(charge,q["charge_min_V"])
    crest=g*stages*charge
    nominal=LIMITS[q["impulse_type"]]["nominal_s"]
    widths=[(LIMITS[q["impulse_type"]][k][1]-LIMITS[q["impulse_type"]][k][0])*5e5 for k in ("front_s","tail_s")]
    score=((crest-q["target_crest_V"])/(.03*q["target_crest_V"]))**2
    score+=((front-nominal[0]*1e6)/widths[0])**2+((tail-nominal[1]*1e6)/widths[1])**2
    return np.where(np.isfinite(score),score,np.inf)


def load_predictor(request, registry=None, selection=None):
    from .registry import load_model_cached
    route=f"{request['domain_id']}:{request['impulse_type']}:{request['topology_id']}"
    selection=Path(selection or SELECTION)
    mapping=json.loads(selection.read_text(encoding="utf-8"))
    identifier=mapping[route]
    if not isinstance(identifier,str) or Path(identifier).name!=identifier:raise ValueError("Invalid model identifier")
    expected=dict(domain_id=request["domain_id"],mode=request["impulse_type"],topology=request["topology_id"])
    model,card=load_model_cached(Path(registry or REGISTRY)/identifier,expected_route=expected)
    return model,card


def _order_pool(ids,ml_score,analytic_score,ood,policy):
    ml_order=np.argsort(ml_score,kind="stable")
    analytic_order=np.argsort(analytic_score,kind="stable")
    if policy=="complete_physics":return list(range(len(ids)))
    if policy=="analytical":return analytic_order.tolist()
    if policy=="ml":return ml_order.tolist()
    # Interleaving remains active throughout the search, not just the first five.
    # It preserves analytical and global diversity when ML is confidently wrong.
    diverse=np.arange(len(ids))
    outside=np.flatnonzero(ood)
    seen=set();order=[];positions=[0,0,0,0]
    streams=[ml_order,analytic_order,diverse,outside]
    schedule=(0,0,0,1,3,0,1,2)
    while len(order)<len(ids):
        before=len(order)
        for stream in schedule:
            values=streams[stream]
            while positions[stream]<len(values) and int(values[positions[stream]]) in seen:positions[stream]+=1
            if positions[stream]<len(values):
                value=int(values[positions[stream]]);positions[stream]+=1
                seen.add(value);order.append(value)
        if len(order)==before:break
    return order


def _rank(row):
    return (0 if row["compliant"] else 1 if row.get("score") else 2,
        round(row["score"]["J"],12) if row.get("score") else math.inf,
        -round(row["score"]["minimum_margin"],12) if row.get("score") else math.inf,
        row.get("stored_energy_J") or math.inf,row["configuration"]["stages"],
        row["configuration"]["front_per_stage_ohm"],row["configuration"]["tail_per_stage_ohm"],row["candidate_id"])


def verify_candidate(index,catalog,q,p,ml_prediction=None,ml_ood=None):
    entry=catalog.physical(int(index),q["inventory"])
    n=entry["stages"]
    c=dict(impulse_type=q["impulse_type"],stages=n,stage_charge_V=_charge_max(n,p),
        front_per_stage_ohm=float(entry["front"].equivalent_ohm),tail_per_stage_ohm=float(entry["tail"].equivalent_ohm),
        front_network=entry["front"].tree,tail_network=entry["tail"].tree,topology_id=q["topology_id"],polarity=q["polarity"])
    row=dict(candidate_id=entry["candidate_id"],catalog_index=int(index),configuration=c,
        front_recipe=entry["front"].as_dict(),tail_recipe=entry["tail"].as_dict(),
        component_bill_of_materials=entry["bill_of_materials"],physical_alternative_count=entry["physical_alternative_count"],
        front_physical_alternatives=entry["front_physical_alternatives"],tail_physical_alternatives=entry["tail_physical_alternatives"],
        known_constraints_valid=entry["known_inventory_valid"],compliant=False,score=None,physics=None,
        ml_prediction=None if ml_prediction is None else dict(zip(("gain","front_us","tail_us"),map(float,ml_prediction))),
        ml_ood=None if ml_ood is None else bool(ml_ood),hardware_status="HARDWARE_UNVERIFIED",eligible_for_hardware_recommendation=False,
        reason_codes=[],verification_status="NOT_EVALUATED",stored_energy_J=None)
    if not entry["known_inventory_valid"]:
        row.update(verification_status="KNOWN_INVENTORY_CONSTRAINT_FAILED",reason_codes=["INSUFFICIENT_COMPONENT_QUANTITIES"])
        return row,None,0
    try:
        reference=simulate(c,q["setup"],domain_id=q["domain_id"],n_points=1600)
        gain=reference.metadata["voltage_gain"]
        choices=_charge_choices(gain,n,q,p)
        results=[]
        for charge in choices:
            actual=scale_response(reference,charge,target_crest_V=q["target_crest_V"])
            m=actual.metadata
            valid=m["numeric_status"]=="VALID" and m["metrics"]["waveform_status"]=="VALID_CLEAN_FULL_IMPULSE"
            score=parameter_score(m["metrics"],q["impulse_type"],q["target_crest_V"],.03) if valid else None
            item=copy.deepcopy(row)
            item.update(configuration=m["inputs"]["configuration"],physics=m,score=score,
                compliant=bool(valid and m["metrics"]["compliance_status"]=="PASS"),
                verification_status="PHYSICS_VERIFIED" if valid else "PHYSICS_UNSUPPORTED",
                stored_energy_J=m["stored_energy_J"],reason_codes=list(m["metrics"]["reasons"]))
            if score:item["reason_codes"] += ["OUTSIDE_"+key for key,value in score["components"].items() if not value["within_limits"]]
            results.append((item,actual))
        if not results:
            row.update(verification_status="NO_LEGAL_CHARGE",reason_codes=["NO_LEGAL_CHARGE"])
            return row,None,1
        best=min(results,key=lambda pair:_rank(pair[0]))
        best[0]["charge_neighbors_V"]=choices
        return best[0],best[1],1
    except PhysicsError as exc:
        row.update(verification_status="PHYSICS_UNSUPPORTED",reason_codes=[exc.code])
        return row,None,1


def recommend(raw, *, model=None, model_card=None, registry=None, selection=None, progress=None):
    start=time.perf_counter()
    q,catalog=normalize_request(raw)
    p=get_profile(q["domain_id"])
    def report(message):
        if progress:progress(message)
    full=q["search_mode"]=="complete" or catalog.count<=588
    policy=q["priority"]
    model_error=None
    if model is None and policy in ("ml","combined"):
        try:model,model_card=load_predictor(q,registry,selection)
        except (OSError,ValueError,KeyError,RuntimeError) as exc:model_error=str(exc)
    if model is not None:
        if (model.domain_id,model.mode,model.topology)!=(q["domain_id"],q["impulse_type"],q["topology_id"]):
            raise ValueError("Model route does not match fixed request")
    else:
        if policy in ("ml","combined"):policy="analytical"
    if q["setup"].get("load_resistance_ohm") is not None:
        model=None
        model_error="Optional load leakage is supported by Physics but not the trained L0 feature contract"
        policy="complete_physics"
    from .features import feature_matrix
    pool_limit=catalog.count if full else min(catalog.count,q["max_ml_candidates"])
    # Complete Physics is streamed separately: it never builds a millions-row pool.
    if q["search_mode"]=="complete" and catalog.count>q["max_ml_candidates"]:
        policy="complete_physics"
    pool_ids=[];ml_scores=[];analytic_scores=[];predictions=[];outside=[]
    scoring_seconds=0.;ml_count=0
    if policy!="complete_physics":
        iterator=range(catalog.count) if full else catalog.progressive_ids(q["setup"],q["domain_id"],q["impulse_type"])
        for ids in catalog.batches(itertools.islice(iterator,pool_limit)):
            batch_start=time.perf_counter()
            n,rf,rt=catalog.decode(ids)
            features=feature_matrix(n,rf,rt,q["setup"],q["domain_id"],q["impulse_type"],q["topology_id"])
            baseline=features[:,-3:]
            a=_scalar_scores(baseline,n,q,p)
            if model is None:
                pred=baseline;ood=np.ones(len(ids),dtype=bool)
            else:
                pred=model.predict(features);ood=model.ood(features);ml_count+=len(ids)
            score=_scalar_scores(pred,n,q,p)
            pool_ids.extend(ids.tolist());ml_scores.extend(score.tolist());analytic_scores.extend(a.tolist())
            predictions.extend(pred.tolist());outside.extend(ood.tolist())
            scoring_seconds+=time.perf_counter()-batch_start
            report(f"Scored {len(pool_ids):,} / {catalog.count:,} response candidates; {ml_count:,} ML predictions")
            if not full and time.perf_counter()-start>=q["budget_seconds"]*.55:break
        positions=_order_pool(pool_ids,np.asarray(ml_scores),np.asarray(analytic_scores),np.asarray(outside),policy)
        ordered=((pool_ids[pos],predictions[pos] if model else None,outside[pos] if model else None) for pos in positions)
    else:
        iterator=range(catalog.count) if full else catalog.progressive_ids(q["setup"],q["domain_id"],q["impulse_type"])
        ordered=((idx,None,None) for idx in iterator)
    rows=[];waveforms={};physics_calls=0;first_pass=None;alternatives_time=None;stop="CANDIDATE_POOL_EXHAUSTED"
    max_checks=catalog.count if full else min(q["max_physics_evaluations"],len(pool_ids) if pool_ids else catalog.count)
    for index,pred,ood in ordered:
        if len(rows)>=max_checks:stop="PHYSICS_EVALUATION_BUDGET";break
        if rows and time.perf_counter()-start>=q["budget_seconds"]:stop="TIME_BUDGET";break
        row,wave,calls=verify_candidate(index,catalog,q,p,pred,ood)
        physics_calls+=calls
        rows.append(row)
        if wave is not None:waveforms[row["candidate_id"]]=wave.arrays
        pass_count=sum(r["compliant"] for r in rows)
        elapsed=time.perf_counter()-start
        if row["compliant"] and first_pass is None:first_pass=elapsed
        if pass_count>=q["alternatives"] and alternatives_time is None:alternatives_time=elapsed
        if len(rows)<=5 or len(rows)%25==0:
            report(f"Physics verified {len(rows):,}; passing {pass_count}; elapsed {elapsed:.1f}s")
    rows.sort(key=_rank)
    for rank,row in enumerate(rows,1):row["rank"]=rank
    passed=[r for r in rows if r["compliant"]]
    failed=[r for r in rows if not r["compliant"]]
    complete=len(rows)==catalog.count
    unsupported=sum(r["verification_status"]=="PHYSICS_UNSUPPORTED" for r in rows)
    status="VERIFIED_COMPLIANT" if passed else "NO_COMPLIANT_CONFIGURATION_IN_DECLARED_CATALOG" if complete else "NO_COMPLIANT_CONFIGURATION_YET"
    elapsed=time.perf_counter()-start
    result=dict(schema_version="network_result_v3",optimizer_version="3.0.0",request=q,request_sha256=_digest(q),
        status=status,best_configuration=passed[0] if passed else None,ranked_alternatives=passed[1:q["alternatives"]],
        failed_alternatives=failed[:q["alternatives"]],closest_noncompliant=failed[0] if failed else None,candidates=rows,
        profile=p.as_dict(),model=model_card,model_fallback_reason=model_error,
        search=dict(**catalog.info(),requested_strategy=q["priority"],effective_strategy=policy,
            catalog_complete=complete,ml_pool_complete=len(pool_ids)==catalog.count if pool_ids else False,
            considered_count=len(pool_ids) if pool_ids else len(rows),ml_predicted_count=ml_count,
            physics_evaluated_count=physics_calls,evaluated_or_legally_excluded_count=len(rows),passing_count=len(passed),
            unsupported_count=unsupported,known_constraint_excluded_count=sum(not r["known_constraints_valid"] for r in rows),
            ml_ood_count=sum(outside) if model else None,termination_reason="DECLARED_CATALOG_COMPLETED" if complete else stop,
            time_to_first_pass_seconds=first_pass,time_to_alternatives_seconds=alternatives_time,
            total_seconds=elapsed,scoring_seconds=scoring_seconds,verification_seconds=elapsed-scoring_seconds,
            optimality="COMPLETE_DECLARED_MODEL_CATALOG" if complete and not unsupported else "BEST_VERIFIED_EVALUATED_SUBSET",
            candidate_order_policy="DETERMINISTIC_PROGRESSIVE_GUIDES_AND_FULL_CYCLE_COVERAGE_v3"),
        ranking_policy="PHYSICS_PASS_THEN_TOLERANCE_NORMALIZED_J_MARGIN_ENERGY_STAGE_RESISTANCE_STABLE_ID_v3",
        physics_provenance=source_fingerprint(),eligible_for_hardware_recommendation=False,standards_certified=False,
        limitations=["Uniform ideal two-terminal resistor networks; mounting and pulse ratings unverified.",
            "ML ranks candidates; only detailed Physics qualifies numerical waveform conformity.",
            "Unverified or unsupported candidates prevent unrestricted no-solution or global-optimum claims.",
            "Failed alternatives are NOT RECOMMENDED."])
    return result,waveforms


def save_result(result,waveforms,directory):
    path=Path(directory)
    path.mkdir(parents=True,exist_ok=False)
    (path/"waveforms").mkdir()
    for row in result["candidates"]:
        arrays=waveforms.get(row["candidate_id"])
        if arrays is None:continue
        target=path/"waveforms"/(row["candidate_id"]+".npz")
        np.savez_compressed(target,**arrays)
        row["waveform_reference"]=dict(path="waveforms/"+target.name,sha256=hashlib.sha256(target.read_bytes()).hexdigest())
    (path/"result.json").write_text(json.dumps(result,indent=2,allow_nan=False),encoding="utf-8")
    (path/"request.json").write_text(json.dumps(result["request"],indent=2,allow_nan=False),encoding="utf-8")
    return path/"result.json"
