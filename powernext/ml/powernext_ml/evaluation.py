import time
import numpy as np
from scipy.stats import rankdata
from .common import PHYSICS
from physics_engine.evaluator import LIMITS


def tolerances(frame,domain,mode):
    nominal=LIMITS[mode]["nominal_s"]
    ft=(LIMITS[mode]["front_s"][1]-LIMITS[mode]["front_s"][0])/2*1e6
    tt=(LIMITS[mode]["tail_s"][1]-LIMITS[mode]["tail_s"][0])/2*1e6
    if domain=="legacy":return np.column_stack([np.full(len(frame),ft),np.full(len(frame),tt),.03*frame.Test_kV.to_numpy()])
    return np.column_stack([.03*frame.gain.to_numpy(),np.full(len(frame),ft),np.full(len(frame),tt)])


def compliance(frame,pred,domain,mode,target_override=None):
    bounds=LIMITS[mode]
    front,tail=(pred[:,0],pred[:,1]) if domain=="legacy" else (pred[:,1],pred[:,2])
    shape=(front>=bounds["front_s"][0]*1e6)&(front<=bounds["front_s"][1]*1e6)&(tail>=bounds["tail_s"][0]*1e6)&(tail<=bounds["tail_s"][1]*1e6)
    crest=pred[:,2]*1000 if domain=="legacy" else pred[:,0]*frame.U0_V.to_numpy()
    target=(frame.Test_kV.to_numpy()*1000 if domain=="legacy" else frame.target_crest_V.to_numpy()) if target_override is None else target_override
    return shape & (crest>=.97*target)&(crest<=1.03*target),shape


def confusion(truth,pred):
    good=int(truth.sum());bad=int((~truth).sum())
    fa=int((~truth&pred).sum());fr=int((truth&~pred).sum())
    return dict(true_pass=good,true_fail=bad,false_accept=fa,false_reject=fr,false_accept_rate=fa/bad if bad else None,false_reject_rate=fr/good if good else None)


def metrics(frame,y,pred,domain,mode):
    if y.shape!=pred.shape or not np.isfinite(pred).all():raise ValueError("Invalid predictions")
    e=abs(y-pred);tol=tolerances(frame,domain,mode)
    names=["front_us","tail_us","crest_kV"] if domain=="legacy" else ["gain","front_us","tail_us"]
    out={n:dict(MAE=float(e[:,i].mean()),RMSE=float(np.sqrt(np.mean(e[:,i]**2))),P95_absolute_error=float(np.quantile(e[:,i],.95)),tolerance_normalized_MAE=float((e[:,i]/tol[:,i]).mean()),tolerance_normalized_P95=float(np.quantile(e[:,i]/tol[:,i],.95))) for i,n in enumerate(names)}
    if domain=="simulation":
        ce=e[:,0]*frame.U0_V.to_numpy()/1000
        out["crest_kV"]=dict(MAE=float(ce.mean()),RMSE=float(np.sqrt(np.mean(ce**2))),P95_absolute_error=float(np.quantile(ce,.95)))
    truth,shape_truth=compliance(frame,y,domain,mode);decision,shape_pred=compliance(frame,pred,domain,mode)
    out.update(n=len(y),selection_score=float((e/tol).mean()),full_compliance=confusion(truth,decision),shape_compliance=confusion(shape_truth,shape_pred),ranking_error=None,ranking_status="NOT_USED_FOR_FINAL_OPTIMIZER_RANKING_EXHAUSTIVE_PHYSICS")
    if domain=="simulation":
        probes=[]
        for ratio in [.96,.9701,1.,1.0299,1.04]:
            target=y[:,0]*frame.U0_V.to_numpy()/ratio
            t,_=compliance(frame,y,domain,mode,target);d,_=compliance(frame,pred,domain,mode,target)
            probes.append(dict(actual_crest_over_request=ratio,**confusion(t,d)))
        out["evaluation_only_crest_boundary_probes"]=probes
    return out


def latency(predict,frame,repeats=15):
    predict(frame.iloc[:1]);times=[]
    for _ in range(repeats):
        start=time.perf_counter();predict(frame.iloc[:1]);times.append((time.perf_counter()-start)*1000)
    return dict(single_median_ms=float(np.median(times)),single_p95_ms=float(np.quantile(times,.95)),repeats=repeats)


def bootstrap_score(frame,y,pred,domain,mode,repetitions=300):
    losses=(abs(y-pred)/tolerances(frame,domain,mode)).mean(axis=1)
    groups=frame.group_id.to_numpy();unique=np.unique(groups)
    # Resample complete groups, weighting groups equally in the interval.
    means=np.array([losses[groups==g].mean() for g in unique])
    rng=np.random.default_rng(741)
    boot=means[rng.integers(0,len(means),(repetitions,len(means)))].mean(axis=1)
    return dict(group_count=len(unique),group_equal_mean=float(means.mean()),interval_95=np.quantile(boot,[.025,.975]).tolist(),bootstrap_repetitions=repetitions)
