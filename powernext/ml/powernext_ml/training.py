from pathlib import Path
import json
import time
import numpy as np
import pandas as pd
from .common import digest,file_hash,write_json,log
from .features import labels,baseline
from .splits import connected_groups,make_splits
from .models import ParameterModel
from .evaluation import metrics,latency,bootstrap_score
from .registry import register


def load_frame(domain,path):
    path=Path(path)
    if domain=="legacy":
        frame=pd.read_csv(path)
        frame["row_id"]=frame.ID.astype(str)
        # Conservative coarse setup families for new evaluations. Original
        # provided split is retained only as a historical comparison.
        frame["physical_shape_id"]=[digest([str(r.Impulse_Type),int(r.Stages),float(r.Front_R_Stage),float(r.Tail_R_Stage),round((r.Load_C_pF+r.Divider_C_pF+r.Stray_C_pF)/50),round(r.L_uH/2)]) for r in frame.itertuples()]
        frame["setup_family_id"]=frame.physical_shape_id
        frame["mode"]=frame.Impulse_Type.map({"Lightning":"LI","Switching":"SI"})
        frame["topology_version"]="LEGACY_FORMULAS_3uF"
        provenance=dict(evidence_domain="LEGACY_SYNTHETIC_3uF",topology_status="LEGACY_NOT_CPRI",dataset_sha256=file_hash(path))
    else:
        manifest=json.loads((path/"manifest.json").read_text())
        if manifest["status"]!="COMPLETE" or file_hash(path/"rows.jsonl")!=manifest["rows_sha256"]:raise ValueError("Incomplete or altered simulation dataset")
        rows=[json.loads(l) for l in (path/"rows.jsonl").read_text().splitlines()]
        provenance={k:rows[0][k] for k in ["equipment_profile_version","equipment_profile_sha256","simulator_version","simulator_sha256","evaluator_version","evaluator_sha256","waveform_profile_id","recipe_version","topology_spec_sha256","topology_status","evidence_domain","hardware_verified","baseline_version","baseline_sha256","adapter_version"]}
        values=[]
        for r in rows:
            if any(r[k]!=v for k,v in provenance.items()):raise ValueError("Mixed provenance in dataset")
            if not r["regression_eligible"]:continue
            c=r["configuration"]
            values.append(dict(**r["features"],**{k:r[k] for k in ["row_id","physical_shape_id","setup_family_id","topology_version","target_crest_V","gain","front_us","tail_us","dataset_id","case_kind"]},recipe_id=c["recipe_id"],mode=c["impulse_type"],U0_V=c["stages"]*c["stage_charge_V"]))
        frame=pd.DataFrame(values)
    frame["group_id"]=connected_groups(frame,["physical_shape_id","setup_family_id"])
    return frame,provenance


def benchmark(domain,path,output,registry):
    output=Path(output)
    if output.exists():raise FileExistsError(f"Use a fresh versioned benchmark directory: {output}")
    output.mkdir(parents=True)
    frame,provenance=load_frame(domain,path)
    dataset_hash=file_hash(Path(path)/"rows.jsonl" if domain=="simulation" else path)
    all_results=[];all_predictions=[];selections=[];split_records=[]
    active={}
    for (mode,top),group in frame.groupby(["mode","topology_version"]):
        group=group.reset_index(drop=True)
        splits=make_splits(group,domain)
        for protocol,assignment in splits.items():
            split_records.extend(dict(row_id=str(row.row_id),mode=mode,topology=top,protocol=protocol,split=assignment[i],group_id=row.group_id) for i,row in group.iterrows())
        main="grouped_setup"
        assignment=splits[main]
        train=group[assignment=="train"];val=group[assignment=="validation"];test=group[assignment=="test"]
        candidates=[]
        for formulation in ["direct","physics_guided","residual"]:
            for family in ["knn","extra_trees","hist_gradient_boosting"]:
                start=time.perf_counter();model=ParameterModel(domain,formulation,family).fit(train)
                fit_seconds=time.perf_counter()-start
                val_metrics=metrics(val,labels(val,domain),model.predict(val),domain,mode)
                candidates.append((val_metrics["selection_score"],formulation,family,model,fit_seconds,val_metrics))
                log(f"{domain} {mode} {top}: fitted {formulation}/{family}; validation tolerance score {val_metrics['selection_score']:.4g}")
        best=min(candidates,key=lambda x:x[0])
        selection=dict(mode=mode,topology=top,protocol=main,formulation=best[1],family=best[2],validation_score=best[0],selection_rule="minimum validation mean absolute error normalized by challenge half-widths; no test-based selection",train_rows=train.row_id.tolist(),validation_rows=val.row_id.tolist(),test_rows=test.row_id.tolist())
        # Persist choice before reading any candidate test predictions.
        write_json(output/f"selection_{mode}_{top}.json",selection);selections.append(selection)
        for _,formulation,family,model,fit_s,val_metrics in candidates:
            pred=model.predict(test);m=metrics(test,labels(test,domain),pred,domain,mode)
            record=dict(mode=mode,topology=top,protocol=main,model=family,formulation=formulation,selected=(formulation==best[1] and family==best[2]),fit_seconds=fit_s,validation=val_metrics,test=m,latency=latency(model.predict,test),ood_count=int(model.ood(test).sum()))
            all_results.append(record)
            truth_batch=labels(test,domain); ood_batch=model.ood(test)
            for i,(_,r) in enumerate(test.iterrows()):all_predictions.append(dict(mode=mode,topology=top,protocol=main,model=family,formulation=formulation,row_id=r.row_id,truth=truth_batch[i].tolist(),prediction=pred[i].tolist(),ood=bool(ood_batch[i])))
        model=best[3]
        card=register(model,dict(provenance=provenance,dataset_sha256=dataset_hash,mode=mode,topology_version=top,selection=selection,
                                 test_metrics=metrics(test,labels(test,domain),model.predict(test),domain,mode),test_group_bootstrap=bootstrap_score(test,labels(test,domain),model.predict(test),domain,mode),
                                 nominal_validation_absolute_error_p95=np.quantile(abs(labels(val,domain)-model.predict(val)),.95,axis=0).tolist(),uncertainty_status="EMPIRICAL_ERROR_ENVELOPE_NOT_CALIBRATED_CONFIDENCE",deployment_status="DEVELOPMENT_SCREENING_ONLY"),registry)
        active[f"{mode}:{top}"]=card["model_id"]
        # Same heldout protocol for all nine formulations above. Selected recipe
        # is fixed before separate covariate-shift tests; refit only their train.
        for protocol,assignment in splits.items():
            tr=group[assignment=="train"];te=group[assignment=="test"]
            if protocol!=main:
                shifted=ParameterModel(domain,best[1],best[2]).fit(tr)
                p=shifted.predict(te)
                ood=shifted.ood(te)
                m=metrics(te,labels(te,domain),p,domain,mode)
                subgroup={label:metrics(te[mask],labels(te[mask],domain),p[mask],domain,mode) if mask.any() else None for label,mask in [("inside_training_support",~ood),("outside_training_support",ood)]}
                all_results.append(dict(mode=mode,topology=top,protocol=protocol,model=best[2],formulation=best[1],selected=True,test=m,n_train=len(tr),ood_count=int(ood.sum()),ood_metrics=subgroup))
            all_results.append(dict(mode=mode,topology=top,protocol=protocol,model="physics_only",formulation="baseline",selected=False,test=metrics(te,labels(te,domain),baseline(te,domain),domain,mode)))
    write_json(output/"results.json",all_results)
    write_json(output/"selections.json",selections)
    write_json(output/"predictions.json",all_predictions)
    pd.DataFrame(split_records).to_csv(output/"split_assignments.csv",index=False)
    # This file belongs to this benchmark run, never a mutable global alias.
    write_json(output/"selected_models.json",active)
    write_json(output/"run_manifest.json",dict(domain=domain,dataset_sha256=dataset_hash,provenance=provenance,results_sha256=file_hash(output/"results.json"),split_sha256=file_hash(output/"split_assignments.csv"),selection_count=len(selections)))
    log(f"Benchmark complete: {len(all_results)} model/protocol records, {len(selections)} registered models")
    return all_results
