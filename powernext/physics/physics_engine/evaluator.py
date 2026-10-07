"""Clean full-impulse evaluator, explicit legacy competition SI convention.

A PASS here is a numerical challenge-profile result, NOT IEC metrology
certification or authorization to operate a high-voltage generator.
Oscillatory/noisy/chopped curves are conservatively gated, not forced through
raw-peak thresholds. A validated IEC test-voltage-curve plugin is still needed.
"""
from __future__ import annotations
import numpy as np
from scipy.interpolate import PchipInterpolator
from scipy.optimize import brentq
from scipy.signal import find_peaks
from .network import PhysicsError

PROFILE_ID="CPRI_COMPETITION_LI_1p2_50_SI_Tp250_T2_2500_v1"
LIMITS={"LI":{"front_s":(0.84e-6,1.56e-6),"tail_s":(40e-6,60e-6),"nominal_s":(1.2e-6,50e-6)},
        "SI":{"front_s":(200e-6,300e-6),"tail_s":(1000e-6,4000e-6),"nominal_s":(250e-6,2500e-6)}}

def crossings(t,u,level,side):
    """Roots on every strictly crossing bracket. Exact sampled roots deduplicated."""
    interp=PchipInterpolator(t,u,extrapolate=False)
    roots=[]
    d=u-level
    for k in range(len(t)-1):
        qualifies=(u[k+1]>u[k]) if side=="rising" else (u[k+1]<u[k])
        if qualifies and d[k]*d[k+1] <= 0 and not (d[k]==0 and d[k+1]==0):
            r=brentq(lambda x:float(interp(x))-level,float(t[k]),float(t[k+1]),xtol=1e-16,rtol=1e-13)
            if not roots or abs(r-roots[-1])>1e-14: roots.append(float(r))
    return roots

def evaluate(t_s,voltage_V,impulse_type:str,polarity:int=1,*,beginning_s:float|None=0.0,baseline_V:float=0.0,
             target_crest_V:float|None=None,source_kind:str="simulation_clean",curve_id:str="raw_clean"):
    t=np.asarray(t_s,dtype=float); v=np.asarray(voltage_V,dtype=float)
    if impulse_type not in LIMITS: raise PhysicsError("INVALID_IMPULSE_TYPE",impulse_type)
    if polarity not in (-1,1): raise PhysicsError("INVALID_POLARITY","Use +1 or -1.")
    if t.ndim!=1 or v.shape!=t.shape or len(t)<8 or not np.all(np.isfinite(t)) or not np.all(np.isfinite(v)) or not np.isfinite(baseline_V):
        raise PhysicsError("INVALID_WAVEFORM_ARRAY","Finite, one-dimensional, equal-length arrays with at least 8 points required.")
    if np.any(np.diff(t)<=0): raise PhysicsError("TIME_NOT_STRICTLY_INCREASING","Do not silently sort/reorder measurements.")
    if target_crest_V is not None and (not np.isfinite(target_crest_V) or target_crest_V<=0):
        raise PhysicsError("INVALID_TARGET_CREST","Target must be positive magnitude in volts.")
    u=polarity*(v-baseline_V)
    k=int(np.argmax(u)); peak=float(u[k]); reasons=[]
    out={"profile_id":PROFILE_ID,"evaluation_curve_id":curve_id,"interpolation":"PCHIP",
         "standards_certified":False,"polarity":polarity,"baseline_V":float(baseline_V),
         "raw_crest_magnitude_V":peak,"raw_signed_crest_V":float(polarity*peak),
         "crest_magnitude_V":peak,"t_peak_s":float(t[k]),"T1_s":None,"Tp_s":None,"T2_s":None,
         "t30_s":None,"t90_s":None,"t50_falling_s":None,"virtual_origin_s":None,
         "beginning_s":beginning_s,"waveform_status":"VALID_CLEAN_FULL_IMPULSE",
         "compliance_status":"INDETERMINATE","reasons":reasons}
    if peak<=0 or k==0 or k==len(t)-1:
        reasons.append("PEAK_MISSING_OR_RECORD_TRUNCATED")
    if peak>0:
        # Numerical prominence threshold, not an IEC permissible overshoot limit.
        maxima,_=find_peaks(u,prominence=peak*1e-5)
        minima,_=find_peaks(-u,prominence=peak*1e-5)
        if len(maxima)>1 or len(minima)>0 or np.min(u)<-1e-4*peak:
            reasons.append("OSCILLATORY_OR_NOISY_REQUIRES_VALIDATED_EVALUATOR")
        if len(np.flatnonzero(u==peak))>1:
            reasons.append("FLAT_PEAK_AMBIGUOUS")
        if abs(u[0])>peak*1e-4:
            reasons.append("FRONT_TRUNCATED_OR_BASELINE_INVALID")
    if source_kind!="simulation_clean":
        reasons.append("MEASURED_DATA_REQUIRES_QUALIFIED_PREPROCESSING")
    if beginning_s is not None and (not np.isfinite(beginning_s) or beginning_s<t[0] or beginning_s>=t[k]):
        reasons.append("INVALID_IMPULSE_BEGINNING")
    if not reasons:
        r30=crossings(t,u,0.3*peak,"rising")
        r90=crossings(t,u,0.9*peak,"rising")
        f50=[x for x in crossings(t,u,0.5*peak,"falling") if x>t[k]]
        if len(r30)!=1 or len(r90)!=1 or len(f50)!=1:
            reasons.append("CROSSING_MISSING_OR_AMBIGUOUS")
        else:
            out.update(t30_s=r30[0],t90_s=r90[0],t50_falling_s=f50[0])
            if impulse_type=="LI":
                front=(r90[0]-r30[0])/0.6
                origin=r30[0]-0.3*front
                out.update(T1_s=front,virtual_origin_s=origin,T2_s=f50[0]-origin)
            elif beginning_s is None:
                reasons.append("SI_BEGINNING_UNKNOWN")
            else: out.update(Tp_s=float(t[k]-beginning_s),T2_s=f50[0]-beginning_s)
    if reasons:
        out["waveform_status"]="INDETERMINATE"
        return out
    limits=LIMITS[impulse_type]; front=out["T1_s"] if impulse_type=="LI" else out["Tp_s"]
    checks={"front_or_peak":limits["front_s"][0]<=front<=limits["front_s"][1],
            "tail":limits["tail_s"][0]<=out["T2_s"]<=limits["tail_s"][1],
            "crest":None if target_crest_V is None else .97*target_crest_V<=peak<=1.03*target_crest_V}
    dev={"front_or_peak_pct":100*(front/limits["nominal_s"][0]-1),
         "tail_pct":100*(out["T2_s"]/limits["nominal_s"][1]-1),
         "crest_pct":None if target_crest_V is None else 100*(peak/target_crest_V-1)}
    out.update(checks=checks,deviation_pct=dev,
               compliance_status="FAIL" if any(x is False for x in checks.values()) else ("PASS" if all(x is True for x in checks.values()) else "INDETERMINATE"))
    if target_crest_V is None: reasons.append("TARGET_CREST_NOT_SPECIFIED")
    return out
