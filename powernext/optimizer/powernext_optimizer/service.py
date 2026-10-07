"""Complete catalog search; no setup modification, learned pruning or topology choice."""
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict
import copy
from .common import RequestError, digest, log, PACKAGE, file_hash
from .catalog import Catalog, normalize_request
from .charge import charge_policy, legal_interval, charge_choices, hardware_checks
from .prediction import PredictionStack
from .assessment import parameter_score, changes, rank_rows, rank_key
from .storage import RecommendationResult

_STACK = None
_CATALOG = None


def _initialize(options):
    global _STACK, _CATALOG
    _STACK=PredictionStack(**options)
    _CATALOG=Catalog(options["adapter_name"])


def _worker(task):
    return evaluate_candidate(task[0],task[1],_CATALOG,_STACK)


def evaluate_candidate(request, entry, catalog, stack):
    c=dict(entry["configuration"],polarity=request["polarity"])
    policy=charge_policy(catalog,entry)
    interval=legal_interval(policy)
    base=dict(candidate_id=entry["candidate_id"],impulse_type=request["impulse_type"],
        equipment_profile_id=catalog.profile_id,topology_id=request["topology_id"],recipe_status=entry["recipe_status"],
        topology_status=catalog.adapter.provenance["topology_status"],front_recipe=entry["front_recipe"],tail_recipe=entry["tail_recipe"],
        component_bill_of_materials=entry.get("component_bill_of_materials",[]),
        exact_module_allocation=entry["exact_module_allocation"],allocation_status=entry["allocation_status"],
        charge_policy=asdict(policy),eligible_for_hardware_recommendation=False,standards_certified=False)
    if interval is None:
        return dict(base,configuration=dict(c,stage_charge_V=None),charge_solution={"choices_V":[]},
            hard_constraints=dict(declared_constraints_satisfied=False,constraints=[dict(constraint="charge_interval",status="FAIL")]),
            assessment=dict(evaluation_status="UNSUPPORTED",compliance_status="INDETERMINATE"),score=None,
            prediction=None,reason_codes=["NO_LEGAL_CHARGE"],warnings=["No legal charge interval"],changes_from_current=None),None
    reference_charge=interval[1]
    reference=stack.call(dict(c,stage_charge_V=reference_charge),request["setup"],None)
    metadata=reference.get("physics_reference")
    if not metadata:
        return dict(base,configuration=dict(c,stage_charge_V=reference_charge),charge_solution={"choices_V":[]},
            hard_constraints=hardware_checks(catalog,entry,dict(c,stage_charge_V=reference_charge),request["setup"]),
            assessment=dict(evaluation_status="UNSUPPORTED",compliance_status="INDETERMINATE"),score=None,
            prediction=reference,reason_codes=reference.get("reason_codes",["PHYSICS_UNAVAILABLE"]),warnings=[],changes_from_current=None),None
    k=metadata["metrics"]["raw_crest_magnitude_V"]/reference_charge
    solution=charge_choices(k,request["target_crest_V"],catalog.crest_tolerance,policy)
    options=[]
    for charge in solution["choices_V"]:
        configuration=dict(c,stage_charge_V=charge)
        hard=hardware_checks(catalog,entry,configuration,request["setup"])
        # Re-simulate the actual selected charge through the existing full stack.
        forecast=stack.call(configuration,request["setup"],request["target_crest_V"])
        waveform=forecast.pop("waveform_arrays",None)
        m=forecast.get("physics_reference")
        evaluable=bool(m and m["numeric_status"]=="VALID" and m["metrics"]["waveform_status"]=="VALID_CLEAN_FULL_IMPULSE")
        status=m["metrics"]["compliance_status"] if evaluable else "INDETERMINATE"
        score=parameter_score(m["metrics"],request["impulse_type"],request["target_crest_V"],catalog.crest_tolerance) if evaluable else None
        ml=forecast.get("ml_prediction")
        ml_score=parameter_score(ml,request["impulse_type"],request["target_crest_V"],catalog.crest_tolerance) if ml else None
        reasons=list(forecast.get("reason_codes",[]))
        warnings=list(request["assumptions"])
        if score:
            reasons += ["OUTSIDE_"+name.upper() for name,p in score["components"].items() if not p["within_limits"]]
        else:
            reasons.append("WAVEFORM_OR_NUMERIC_UNSUPPORTED")
        if not solution["band_feasible"]:
            reasons.append("CREST_BAND_UNREACHABLE_WITH_CHARGE_LIMITS")
        if not solution["exact_target_within_continuous_limits"]:
            warnings.append("Exact requested crest exceeds the continuous charge interval; the legal limit is tested against the full tolerance band.")
        if ml_score and score and ml_score["scalar_limits_pass"] != (status=="PASS"):
            reasons.append("ML_REFERENCE_COMPLIANCE_DISAGREEMENT")
        if not catalog.profile["operational_gate"]["hardware_verified"]:
            reasons.append("HARDWARE_NOT_VERIFIED")
        if policy.minimum_V is None:
            reasons.append("MINIMUM_RELIABLE_CHARGE_UNKNOWN")
        if policy.step_V is None:
            reasons.append("CHARGE_RESOLUTION_UNKNOWN_CONTINUOUS_ASSUMPTION")
        if m:
            reasons.extend(m["hardware_reason_codes"])
        row=dict(base,configuration=configuration,charge_solution=solution,hard_constraints=hard,
            assessment=dict(evaluation_status="EVALUABLE" if evaluable else "UNSUPPORTED",compliance_status=status,
                hardware_status=m["hardware_status"] if m else "UNKNOWN",prediction_status=forecast["status"],
                authoritative_curve="raw_clean",checks=m["metrics"].get("checks",{}) if m else {}),
            score=score,ml_score=ml_score,prediction=forecast,changes_from_current=changes(configuration,request["current_setting"]),
            assumptions=m["assumptions"] if m else [],reason_codes=sorted(set(reasons)),warnings=warnings)
        options.append((row,waveform))
    best=min(options,key=lambda pair:rank_key(pair[0]))
    best[0]["charge_neighbor_assessments"]=[dict(stage_charge_V=r["configuration"]["stage_charge_V"],compliance_status=r["assessment"]["compliance_status"],score=r["score"]) for r,_ in options]
    return best


def recommend(raw, *, workers=1, cache=None, registry=None, selection=None, adapter_name="provisional", history=None, progress=True):
    from . import __version__
    if type(workers) is not int or not 1 <= workers <= 16:
        raise ValueError("workers must be 1 through 16")
    catalog=Catalog(adapter_name)
    try:
        request=normalize_request(raw,catalog)
    except RequestError as exc:
        return RecommendationResult(dict(schema_version="recommendation_result_v1",optimizer_version=__version__,
            status="INVALID_REQUEST",reason_codes=[exc.code],detail=str(exc),best_configuration=None,
            ranked_alternatives=[],candidates=[],eligible_for_hardware_recommendation=False),{})
    stack=PredictionStack(registry,selection,cache,adapter_name)
    entries=catalog.entries_for_request(request)
    request_hash=digest(request)
    prior=history.lookup(request_hash,stack.fingerprint) if history else []
    rows=[];waves={}
    if progress:log(f"START complete search: {request['impulse_type']} {request['topology_id']}, {len(entries)} declared configurations")
    if workers==1:
        for index,entry in enumerate(entries):
            row,wave=evaluate_candidate(request,entry,catalog,stack)
            rows.append(row)
            if wave is not None:waves[row["candidate_id"]]=wave
            if progress and (index+1)%8==0:log(f"Evaluated {index+1}/{len(entries)} configurations")
    else:
        with ProcessPoolExecutor(max_workers=workers,initializer=_initialize,initargs=(stack.options(),)) as pool:
            futures=[pool.submit(_worker,(request,entry)) for entry in entries]
            for index,future in enumerate(as_completed(futures)):
                row,wave=future.result();rows.append(row)
                if wave is not None:waves[row["candidate_id"]]=wave
                if progress and (index+1)%8==0:log(f"Evaluated {index+1}/{len(entries)} configurations")
    rows=rank_rows(rows)
    passes=[r for r in rows if r["ranking_tier"]==0]
    usable=[r for r in rows if r["ranking_tier"]<=1]
    best=passes[0] if passes else None
    closest=next((r for r in rows if r["ranking_tier"]==1),None)
    alternatives=[r for r in usable if best is None or r["candidate_id"]!=best["candidate_id"]][:request["alternatives"]]
    reasons=[]
    if not entries:reasons.append("MISSING_APPROVED_RECIPE_INFORMATION" if request['catalog_scope']=='approved' else 'NO_AVAILABLE_RESISTOR_COMBINATION')
    if not passes and any(r["assessment"]["evaluation_status"]=="UNSUPPORTED" for r in rows):reasons.append("MODEL_OR_WAVEFORM_EVALUATION_LIMITATION")
    if not passes and any("CREST_BAND_UNREACHABLE_WITH_CHARGE_LIMITS" in r["reason_codes"] for r in rows):reasons.append("DECLARED_CHARGE_LIMIT_INFEASIBILITY_FOR_SOME_CANDIDATES")
    if not passes and usable:reasons.append("WAVEFORM_NONCOMPLIANCE_IN_DECLARED_CATALOG")
    if not catalog.profile["operational_gate"]["hardware_verified"]:reasons.append("MISSING_HARDWARE_CONFIRMATION")
    no_solution=None if passes else dict(message="NO COMPLIANT CONFIGURATION FOUND IN THE DECLARED CATALOG",categories=reasons,
        closest_candidate_id=closest["candidate_id"] if closest else None,
        limiting_parameters=[name for name,p in closest["score"]["components"].items() if not p["within_limits"]] if closest else [],
        scope="Only this catalog, fixed topology and declared setup; not proof of physical impossibility for actual CPRI hardware")
    payload=dict(schema_version="recommendation_result_v1",optimizer_version=__version__,request=request,request_sha256=request_hash,
        status="NUMERICALLY_COMPLIANT_PROVISIONAL" if passes else "NO_COMPLIANT_CONFIGURATION",
        eligible_for_hardware_recommendation=False,hardware_approval_status="NOT_ESTABLISHED",standards_certified=False,
        search=dict(strategy="EXHAUSTIVE_CATALOG_ANALYTIC_AMPLITUDE",catalog_count=len(entries),evaluated_count=len(rows),pruned_count=0,
            numeric_pass_count=len(passes),evaluable_count=len(usable),unsupported_count=sum(r["ranking_tier"]==2 for r in rows),
            approved_recipe_count=len(catalog.profile["topology"]["approved_recipes"]),catalog_sha256=digest(entries)),
        ranking_policy=dict(version="reference_conformity_v1",primary="Physics-reference compliance then J=eV^2+eFront^2+eTail^2",
            tie_breakers=["greater minimum normalized margin","fewer supplied current-setting hardware-field changes","lower stored energy","fewer stages","component values","stable ID"],
            ML_role="Trained residual estimate and separate score; batch scenario screening is available separately. No pruning or override of physics compliance."),
        provenance=stack.provenance,stack_sha256=stack.fingerprint,configuration_catalog=entries,
        optimizer_source_hashes={p.name:file_hash(p) for p in sorted((PACKAGE/'powernext_optimizer').glob('*.py'))},
        best_configuration=best,ranked_alternatives=alternatives,closest_noncompliant=closest,no_solution=no_solution,
        candidates=rows,reason_codes=reasons,previous_exact_case_matches=prior)
    payload["result_id"]="recommendation_"+digest(payload)[:24]
    if progress:log(f"END search: {len(rows)} evaluated, {len(passes)} numerical passes; hardware approval remains separate")
    return RecommendationResult(payload,waves)


def evaluate_sensitivity(request, configuration, scenarios, **stack_options):
    """Hold the selected setting fixed; named conditions are not optimization knobs."""
    catalog=Catalog(stack_options.get("adapter_name","provisional"))
    request=normalize_request(request,catalog)
    stack=PredictionStack(**stack_options)
    allowed={"dut_capacitance_F","divider_capacitance_F","stray_capacitance_F","loop_inductance_H","loop_resistance_ohm"}
    results=[]
    for scenario in scenarios:
        if not scenario.get("name") or not scenario.get("setup_changes") or set(scenario["setup_changes"])-allowed:
            raise ValueError("Sensitivity scenarios require a name and only explicit setup variations")
        varied=copy.deepcopy(request);varied["setup"].update(scenario["setup_changes"])
        varied=normalize_request(varied,catalog)
        prediction=stack.call(configuration,varied["setup"],varied["target_crest_V"])
        prediction.pop("waveform_arrays",None)
        results.append(dict(scenario=scenario,configuration=configuration,prediction=prediction))
    return dict(policy="FIXED_SETTING_DIAGNOSTIC_NO_NOMINAL_RERANK",scenarios=results)
