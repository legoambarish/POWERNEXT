"""Integration surface: scalar ML predictions plus authoritative physics check."""
from pathlib import Path
import json
import time
from powernext_integrity import artifact_bytes
import numpy as np
import pandas as pd
from .physics_adapter import load_adapter
from .registry import load_model_cached as load_model
from physics_engine.network import PhysicsError


def predict(request,registry,selection=None,adapter_name="provisional"):
    start=time.perf_counter();adapter=load_adapter(adapter_name)
    response=dict(schema_version="ml_prediction_v1",provenance=adapter.provenance,ml_prediction=None,physics_reference=None,
                  selected_prediction=None,prediction_source=None,reason_codes=[],eligible_for_hardware_recommendation=False,
                  standards_certified=False,curve_metric_policy="ML scalars are separate estimates; the physics curve uses physics-evaluated metrics only")
    try:
        if not isinstance(request,dict):raise TypeError("Request must be an object")
        c,s=request["configuration"],request["setup"]
        adapter.validate(c,s)
        target=request.get("target_crest_V")
        if target is not None and (not np.isfinite(target) or target<=0):raise PhysicsError("INVALID_TARGET_CREST","Positive finite magnitude required")
    except (PhysicsError,TypeError,KeyError,ValueError) as exc:
        response.update(status="INVALID_INPUT",reason_codes=[getattr(exc,"code","REQUEST_SCHEMA_MISMATCH")]);return response
    # Always qualify the actual waveform before a compliance decision. A later
    # optimizer may use the learned surrogate for screening but must verify its
    # finalists with the same physics/evaluator.
    try:
        result=adapter.simulate(c,s,target_crest_V=request.get("target_crest_V"),n_points=1600)
    except PhysicsError as exc:
        response.update(status="PHYSICS_UNAVAILABLE",reason_codes=[exc.code]);return response
    m=result.metadata;response["physics_reference"]=m
    response["waveform_arrays"]= {k:v.tolist() for k,v in result.arrays.items() if k in ["time_s","voltage_V"]}
    reference=dict(gain=m["voltage_gain"],crest_V=m["metrics"]["crest_magnitude_V"],T1_s=m["metrics"]["T1_s"],Tp_s=m["metrics"]["Tp_s"],T2_s=m["metrics"]["T2_s"])
    response.update(selected_prediction=reference,prediction_source="PHYSICS",status="PHYSICS_FALLBACK")
    if m["numeric_status"]!="VALID" or m["metrics"]["waveform_status"]!="VALID_CLEAN_FULL_IMPULSE":
        response.update(status="ABSTAIN_UNSUPPORTED_WAVEFORM",selected_prediction=None,reason_codes=m["metrics"]["reasons"]+[m["numeric_status"]])
        return response
    registry=Path(registry)
    if selection is None:
        selection=registry/"selected_models.json"
    try:
        ids=json.loads(artifact_bytes(selection))
        model_id=ids[f"{c['impulse_type']}:{c['topology_id']}"]
        if not isinstance(model_id,str) or Path(model_id).name!=model_id or model_id in ('.','..'):
            raise ValueError("Invalid registry model ID")
        model,card=load_model(registry/model_id,adapter.provenance)
        if card.get('domain')!='simulation' or card.get('mode')!=c['impulse_type'] or card.get('topology_version')!=c['topology_id'] or card.get('model_id')!=model_id:
            raise ValueError("Selected model domain/mode/topology/identity mismatch")
        row=pd.DataFrame([adapter.features(c,s)])
        if bool(model.ood(row)[0]):
            response["reason_codes"].append("OUTSIDE_TRAINING_SUPPORT")
        else:
            gain,front,tail=model.predict(row)[0]
            crest=gain*c["stages"]*c["stage_charge_V"]
            p=dict(gain=float(gain),crest_V=float(crest),T1_s=float(front*1e-6) if c["impulse_type"]=="LI" else None,Tp_s=float(front*1e-6) if c["impulse_type"]=="SI" else None,T2_s=float(tail*1e-6))
            cl=m["derived"]["CL_F"]
            if not np.isfinite([gain,front,tail,crest]).all() or min(gain,front,tail)<=0 or .5*cl*crest**2>m["stored_energy_J"]*(1+1e-9):
                response["reason_codes"].append("ML_PHYSICAL_BOUND_VIOLATION")
            else:
                response.update(ml_prediction=p,model_id=card["model_id"],empirical_validation_error_p95=card["nominal_validation_absolute_error_p95"],uncertainty_status=card["uncertainty_status"])
                response.update(status="ML_WITH_PHYSICS_VERIFICATION",selected_prediction=p,prediction_source="ML")
    except (FileNotFoundError,KeyError,ValueError) as exc:
        response["reason_codes"].append("MODEL_UNAVAILABLE_OR_INCOMPATIBLE")
        response["model_detail"]=str(exc)
    response["authoritative_compliance_status"]=m["metrics"]["compliance_status"]
    response["end_to_end_ms"]=(time.perf_counter()-start)*1000
    return response
