"""Batch ML exploration without a physics simulation or recommendation.

Inputs are explicit what-if scenarios. Results never modify a requested load,
prune the final catalog, or authorize hardware. A final request must run the
exhaustive physics optimizer, including any scenario the surrogate dislikes.
"""
from pathlib import Path
import json,time
from powernext_integrity import artifact_bytes
import numpy as np
import pandas as pd
from .common import digest,file_hash
from .physics_adapter import load_adapter
from .registry import load_model_cached as load_model
from physics_engine.evaluator import LIMITS

def screen_batch(scenarios,registry,selection,adapter_name='provisional'):
    start=time.perf_counter()
    if not isinstance(scenarios,list) or not 1<=len(scenarios)<=4096:
        raise ValueError('Provide 1 through 4096 explicit scenarios')
    adapter=load_adapter(adapter_name); registry=Path(registry); selection=Path(selection)
    selection_hash=file_hash(selection); routes=json.loads(artifact_bytes(selection))
    rows=[]; groups={}; artifacts={}
    for i,request in enumerate(scenarios):
        row=dict(index=i,scenario_id=request.get('scenario_id',str(i)) if isinstance(request,dict) else str(i),
                 status='ABSTAIN',prediction=None,reason_codes=[],requires_physics_verification=True,
                 numerical_compliance_verified=False,eligible_for_hardware_recommendation=False)
        rows.append(row)
        try:
            if not isinstance(request,dict):raise ValueError('Scenario must be an object')
            c,s=adapter.validate(request['configuration'],request['setup'])
            target=request['target_crest_V']
            if type(target) not in (int,float) or not np.isfinite(target) or target<=0:raise ValueError('Invalid target')
            f=adapter.features(request['configuration'],request['setup'])
            route=f'{c.impulse_type}:{c.topology_id}'
            groups.setdefault(route,[]).append((i,c,s,target,f))
        except (ValueError,TypeError,KeyError) as exc:
            row['reason_codes']=[getattr(exc,'code','UNSUPPORTED_SCENARIO')]
    for route,group in groups.items():
        try:
            model_id=routes[route]
            if not isinstance(model_id,str) or Path(model_id).name!=model_id or model_id in ('.','..'):
                raise ValueError('Invalid model ID')
            folder=registry/model_id
            before={name:file_hash(folder/name) for name in ['model.joblib','card.json']}
            model,card=load_model(folder,adapter.provenance)
            mode,top=route.split(':')
            if card.get('domain')!='simulation' or card.get('mode')!=mode or card.get('topology_version')!=top or card.get('model_id')!=model_id:
                raise ValueError('Route mismatch')
            frame=pd.DataFrame([x[4] for x in group]); ood=model.ood(frame)
            pred=model.predict(frame); bounds=LIMITS[mode]
            artifacts[model_id]=before
            for j,(idx,c,s,target,_) in enumerate(group):
                row=rows[idx]
                if ood[j]:
                    row['reason_codes']=['OUTSIDE_TRAINING_SUPPORT'];continue
                gain,front,tail=pred[j]; crest=gain*c.stages*c.stage_charge_V
                energy=.5*.5e-6*c.stages*c.stage_charge_V**2
                if not np.isfinite(pred[j]).all() or min(pred[j])<=0 or .5*s.total_capacitance_F*crest**2>energy*(1+1e-9):
                    row['reason_codes']=['ML_PHYSICAL_BOUND_VIOLATION'];continue
                scalar=bool(.97*target<=crest<=1.03*target and bounds['front_s'][0]*1e6<=front<=bounds['front_s'][1]*1e6 and bounds['tail_s'][0]*1e6<=tail<=bounds['tail_s'][1]*1e6)
                row.update(status='ML_SCREEN_ONLY',prediction=dict(gain=float(gain),crest_V=float(crest),front_us=float(front),tail_us=float(tail)),
                           predicted_scalar_bands=scalar,model_id=model_id,
                           empirical_validation_error_p95=card['nominal_validation_absolute_error_p95'],
                           uncertainty_status=card['uncertainty_status'])
            if before!={name:file_hash(folder/name) for name in before}:raise ValueError('Model changed during batch')
        except (OSError,KeyError,ValueError,ArithmeticError) as exc:
            for idx,*_ in group:
                rows[idx].update(status='ABSTAIN',prediction=None,reason_codes=['MODEL_UNAVAILABLE_OR_INCOMPATIBLE'])
                rows[idx].pop('predicted_scalar_bands',None)
    if file_hash(selection)!=selection_hash:raise ValueError('Selection changed during batch')
    return dict(schema_version='ml_scenario_screen_v1',purpose='EXPLORATION_NOT_FINAL_RECOMMENDATION',
                provenance=adapter.provenance,model_artifacts=artifacts,selection_sha256=selection_hash,
                input_sha256=digest(scenarios),scenario_count=len(scenarios),physics_simulations=0,
                final_optimizer_pruning=False,hardware_verified=False,rows=rows,
                elapsed_ms=(time.perf_counter()-start)*1000,
                limitations=['Scalar surrogate cannot establish waveform quality or hardware feasibility.',
                             'Empirical error envelope is not a calibrated confidence interval.',
                             'Every final recommendation requires complete physics evaluation.'])
