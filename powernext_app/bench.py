"""Isolated ideal low-voltage RC bench calculation. No CPRI hardware profile."""
import numpy as np
from physics_engine.analytic import rates,double_exponential_metrics
from physics_engine.evaluator import evaluate

def predict_bench(parameters):
    keys={'charge_V','generator_C_F','load_C_F','front_R_ohm','tail_R_ohm'}
    if not isinstance(parameters,dict) or set(parameters)!=keys:raise ValueError('Supply all five bench circuit values')
    if any(type(v) not in (int,float) or not np.isfinite(v) or v<=0 for v in parameters.values()):raise ValueError('Bench values must be positive and finite')
    q,cg,cl,rf,rt=[parameters[k] for k in ['charge_V','generator_C_F','load_C_F','front_R_ohm','tail_R_ohm']]
    energy=.5*cg*q*q
    if q>50 or energy>.05:raise ValueError('Isolated bench calculation is limited to 50 V and 50 mJ stored energy')
    alpha,beta=rates(cg,cl,rf,rt,'OSHUNT_v0');m=double_exponential_metrics(alpha,beta,'SI')
    peak=np.log(beta/alpha)/(beta-alpha);end=12/alpha
    t=np.unique(np.r_[0,np.geomspace(max(peak*1e-5,1e-15),end,3000),peak])
    v=q/(rf*cl*(beta-alpha))*(np.exp(-alpha*t)-np.exp(-beta*t))
    metrics=evaluate(t,v,'SI',1,beginning_s=0,source_kind='simulation_clean',curve_id='bench_ideal_RC')
    li=evaluate(t,v,'LI',1,beginning_s=0,source_kind='simulation_clean',curve_id='bench_ideal_RC')
    metrics['T1_s']=li.get('T1_s');metrics['compliance_status']='NOT_APPLICABLE_BENCH'
    return dict(profile_id='ISOLATED_BENCH_RC_v1',topology='Output-shunt ideal two-capacitor RC; no spark gaps, no ML and no CPRI parameter substitution',parameters=parameters,
                stored_energy_J=energy,time_s=t.tolist(),voltage_V=v.tolist(),metrics=metrics,hardware_built=False,experimentally_validated=False,standards_certified=False)

def compare_bench(parameters,raw,source_filename):
    import io,csv,hashlib
    if not isinstance(raw,str) or len(raw)>10_000_000:raise ValueError('Bench CSV must be text under 10 MB')
    reader=csv.DictReader(io.StringIO(raw))
    if reader.fieldnames!=['time_s','voltage_V']:raise ValueError('Use exactly time_s,voltage_V columns with SI units')
    values=np.asarray([[float(r['time_s']),float(r['voltage_V'])] for r in reader])
    if values.ndim!=2 or len(values)<8 or not np.isfinite(values).all() or np.any(np.diff(values[:,0])<=0):raise ValueError('At least eight finite, ordered samples required')
    p=predict_bench(parameters);t,v=values.T;overlap=(t>=p['time_s'][0])&(t<=p['time_s'][-1]);n=int(overlap.sum())
    diagnostics=evaluate(t,v,'SI',1,beginning_s=0,source_kind='simulation_clean',curve_id='bench_import_clean_assumption')
    diagnostics['compliance_status']='NOT_QUALIFIED';diagnostics['source_kind']='unqualified_bench_import'
    return dict(schema_version='bench_comparison_v1',source_kind='USER_DECLARED_BENCH_TRACE_UNAUTHENTICATED',source_filename=source_filename,raw_csv=raw,raw_sha256=hashlib.sha256(raw.encode()).hexdigest(),time_s=t.tolist(),voltage_V=v.tolist(),diagnostics=diagnostics,prediction=p,overlap_samples=n,rmse_V=float(np.sqrt(np.mean((v[overlap]-np.interp(t[overlap],p['time_s'],p['voltage_V']))**2))) if n>=8 else None,calibration_fitted=False,alignment='Explicit SI units, zero beginning and baseline; no scale or time fit',standards_certified=False)
