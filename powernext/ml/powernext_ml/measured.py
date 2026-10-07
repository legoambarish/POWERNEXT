"""Strict future measured-data ingestion. No synthetic-to-measured conversion."""
from pathlib import Path
import json
import shutil
from datetime import datetime
import numpy as np
import pandas as pd
from .common import digest,file_hash,write_json
from physics_engine.evaluator import evaluate

TIME_UNITS={"s":1.,"us":1e-6,"ns":1e-9}
VOLTAGE_UNITS={"V":1.,"kV":1000.}

def trace_diagnostics(t,v,meta):
    """Clean-curve mathematical diagnostics, never qualified measured labels.

    The shared evaluator's measured gate remains unchanged. A second explicit
    clean-curve assumption allows useful timing extraction without asserting
    that preprocessing, instruments, or standards qualification were verified.
    """
    c=meta['configuration'];m=meta['measurement']
    clean=evaluate(t,v,c['impulse_type'],m['polarity'],beginning_s=m['beginning_s'],baseline_V=m['baseline_V'],source_kind='simulation_clean',curve_id='import_clean_assumption_diagnostic')
    keys=['crest_magnitude_V','T1_s','Tp_s','T2_s','t_peak_s','t30_s','t90_s','t50_falling_s','virtual_origin_s','beginning_s']
    diagnostic=dict(status='UNQUALIFIED_CLEAN_TRACE_DIAGNOSTIC' if clean['waveform_status']=='VALID_CLEAN_FULL_IMPULSE' else 'UNSUPPORTED_TRACE',
                    metrics={k:clean.get(k) for k in keys},reason_codes=clean['reasons'],
                    assumption='Treat the declared baseline and beginning as correct and the unmodified curve as clean. No filtering, fitting or time alignment.',
                    compliance_status='NOT_QUALIFIED',regression_eligible=False,standards_certified=False)
    comparison=dict(status='UNAVAILABLE',reason=None,calibration_fitted=False,hardware_verified=False)
    try:
        from .physics_adapter import load_adapter
        adapter=load_adapter();prediction=adapter.simulate(c,meta['setup'],n_points=2000)
        w=prediction.arrays;pt=w['time_s']+m['beginning_s'];pv=w['voltage_V']
        pm=prediction.metadata['metrics']
        overlap=(t>=pt[0])&(t<=pt[-1]);n=int(overlap.sum())
        delta={k:(diagnostic['metrics'][k]-pm[k]) if diagnostic['metrics'].get(k) is not None and pm.get(k) is not None else None for k in ['crest_magnitude_V','T1_s','Tp_s','T2_s']}
        rmse=float(np.sqrt(np.mean(((v[overlap]-m['baseline_V'])-np.interp(t[overlap],pt,pv))**2))) if n>=8 else None
        comparison.update(status='PROVISIONAL_MODEL_COMPARISON',physics_provenance=adapter.provenance,
                          configuration=c,setup=meta['setup'],metrics=pm,diagnostic_minus_prediction=delta,
                          voltage_rmse_V=rmse,overlap_samples=n,alignment='Declared beginning only; no optimized time/voltage fit. Declared baseline subtracted for residual.',
                          waveform=dict(time_s=pt.tolist(),voltage_V=(pv+m['baseline_V']).tolist(),metrics=pm))
    except (ValueError,TypeError,KeyError,ArithmeticError) as exc:comparison['reason']=str(exc)
    return diagnostic,comparison


def ingest_measurement(raw_csv,metadata_path,output):
    """Archive original raw export and metadata; explicit conversion into SI.

    Independently supplied analyzer labels remain separate from this release's
    unqualified measured evaluator. Input qualification is evidence, not a flag
    invented by the importer.
    """
    meta=json.loads(Path(metadata_path).read_text(encoding="utf-8"))
    if not isinstance(meta,dict):raise ValueError("Measured metadata must be an object")
    required=["shot_id","setup_id","shot_series_id","acquisition_time_utc","source_organization","configuration","setup","measurement","provenance"]
    if any(k not in meta or meta[k] in [None,""] for k in required):raise ValueError("Incomplete measured metadata")
    for key in ['configuration','setup','measurement','provenance']:
        if not isinstance(meta[key],dict):raise ValueError(f"{key} must be an object")
    for key in ['shot_id','setup_id','shot_series_id','acquisition_time_utc']:
        if not isinstance(meta[key],str) or not meta[key].strip():raise ValueError(f"Invalid {key}")
    try:
        acquired=datetime.fromisoformat(meta['acquisition_time_utc'].replace('Z','+00:00'))
        if acquired.utcoffset() is None or acquired.utcoffset().total_seconds()!=0:raise ValueError()
    except (ValueError,TypeError):raise ValueError("Acquisition time must be an ISO UTC timestamp")
    kind=meta['provenance'].get('evidence_kind')
    domains={'ACTUAL_LABORATORY_EXPORT':'CPRI_MEASURED_CLAIMED','BENCH_EXPERIMENT':'BENCH_MEASURED_UNVERIFIED','SYNTHETIC_TEST':'SYNTHETIC_IMPORT'}
    if kind not in domains:raise ValueError('Declare ACTUAL_LABORATORY_EXPORT, BENCH_EXPERIMENT, or SYNTHETIC_TEST')
    if kind=='ACTUAL_LABORATORY_EXPORT' and meta['source_organization']!='CPRI':raise ValueError('CPRI export must declare CPRI as source; use BENCH_EXPERIMENT for other experiments')
    if not isinstance(meta['source_organization'],str) or not meta['source_organization'].strip():raise ValueError('Source organization required')
    measurement=meta["measurement"]
    needed=["time_column","voltage_column","time_unit","voltage_unit","voltage_scale_to_DUT","divider_id","digitizer_id","channel_id","measurement_plane","baseline_V","beginning_s","polarity","calibration_reference"]
    if any(k not in measurement for k in needed):raise ValueError("Incomplete measurement chain metadata")
    for key in ['divider_id','digitizer_id','channel_id','measurement_plane','calibration_reference','time_column','voltage_column']:
        if not isinstance(measurement[key],str) or not measurement[key].strip():raise ValueError("Missing instrument/channel/calibration identity")
    scale=measurement["voltage_scale_to_DUT"]
    if type(scale) not in (int,float) or not np.isfinite(scale) or scale<=0:raise ValueError("Invalid voltage scale")
    if type(measurement['polarity']) is not int or measurement['polarity'] not in (-1,1):raise ValueError('Invalid polarity')
    for key in ['baseline_V','beginning_s']:
        if type(measurement[key]) not in (int,float) or not np.isfinite(measurement[key]):raise ValueError(f'Invalid {key}')
    # Validate known units before arithmetic. Never guess scope scaling.
    ts=TIME_UNITS[measurement["time_unit"]];vs=VOLTAGE_UNITS[measurement["voltage_unit"]]
    data=pd.read_csv(raw_csv)
    t=data[measurement["time_column"]].to_numpy(float)*ts
    v=data[measurement["voltage_column"]].to_numpy(float)*vs*scale
    if not np.isfinite(t).all() or not np.isfinite(v).all() or len(t)<8 or (np.diff(t)<=0).any():raise ValueError("Invalid raw waveform; never sorted or repaired")
    c=meta["configuration"]
    for key in ["impulse_type","stages","stage_charge_V","front_per_stage_ohm","tail_per_stage_ohm","recipe_id","topology_id"]:
        if key not in c or c[key] is None:raise ValueError(f"Missing actual setting: {key}")
    if c['impulse_type'] not in ('LI','SI') or type(c['stages']) is not int or c['stages']<1:raise ValueError('Invalid measured impulse/stages')
    for key in ['stage_charge_V','front_per_stage_ohm','tail_per_stage_ohm']:
        if type(c[key]) not in (int,float) or not np.isfinite(c[key]) or c[key]<=0:raise ValueError(f'Invalid measured setting: {key}')
    for key in ['recipe_id','topology_id']:
        if not isinstance(c[key],str) or not c[key].strip():raise ValueError(f'Invalid {key}')
    for key in ['dut_capacitance_F','divider_capacitance_F','stray_capacitance_F','loop_inductance_H']:
        value=meta['setup'].get(key)
        if type(value) not in (int,float) or not np.isfinite(value) or value<0:raise ValueError(f'Invalid measured setup: {key}')
    # Preserve later topology IDs and true settings; never force a measured shot
    # through today's provisional convenience catalog.
    met=evaluate(t,v,c["impulse_type"],measurement["polarity"],beginning_s=measurement["beginning_s"],baseline_V=measurement["baseline_V"],source_kind="measured",curve_id="raw_measured_DUT")
    analyzer=meta.get("analyzer_labels")
    qualified=False
    if analyzer:
        if not isinstance(analyzer,dict):raise ValueError('Analyzer labels must be an object')
        applicable="T1_s" if c["impulse_type"]=="LI" else "Tp_s"
        for key in ["crest_V",applicable,"T2_s"]:
            if not isinstance(analyzer.get(key),(int,float)) or not np.isfinite(analyzer[key]) or analyzer[key]<=0:raise ValueError("Invalid analyzer metric")
        wrong="Tp_s" if applicable=="T1_s" else "T1_s"
        if analyzer.get(wrong) is not None:raise ValueError("Wrong impulse timing definition")
        # Uploaded claims are not an independent qualification decision. This
        # release has no verified analyzer/evaluation-curve review workflow.
    diagnostics,comparison=trace_diagnostics(t,v,meta)
    record=dict(schema_version="measured_import_v3",evidence_domain=domains[kind],metadata=meta,raw_sha256=file_hash(raw_csv),metadata_sha256=file_hash(metadata_path),
                local_evaluation=met,analyzer_labels=analyzer,regression_eligible=qualified,split_group=digest(meta["setup_id"]),
                clean_trace_diagnostics=diagnostics,predicted_comparison=comparison,
                calibration_status="NOT_FITTED",physical_profile_verified=False,
                qualification_status='PENDING_INDEPENDENT_REVIEW',source_identity_policy='USER_SUPPLIED_NOT_AUTHENTICATED',
                qualification_reason_codes=['ANALYZER_CLAIMS_NOT_INDEPENDENTLY_VERIFIED','MEASURED_EVALUATOR_NOT_QUALIFIED'])
    output=Path(output)
    if output.exists():raise FileExistsError("Measured archives are immutable")
    output.mkdir(parents=True)
    shutil.copyfile(raw_csv,output/"raw_export.csv");shutil.copyfile(metadata_path,output/"source_metadata.json")
    np.savez_compressed(output/"waveform_SI.npz",time_s=t,voltage_V=v)
    write_json(output/"record.json",record)
    return record


def adaptation_readiness(records):
    """No training occurs here; grouped empirical calibration must satisfy gates."""
    if any(r['evidence_domain'] not in ('CPRI_MEASURED','CPRI_MEASURED_CLAIMED') for r in records):raise ValueError("Do not mix synthetic and measured evidence")
    reasons=[]
    if not records:reasons.append("NO_REAL_DATA")
    if any(not r["regression_eligible"] for r in records):reasons.append("UNQUALIFIED_MEASURED_LABELS")
    if any(not r["physical_profile_verified"] for r in records):reasons.append("UNVERIFIED_PHYSICAL_PROFILE")
    if any(r.get('source_identity_policy')!='INDEPENDENTLY_AUTHENTICATED' for r in records):reasons.append('UNAUTHENTICATED_SOURCE')
    setups={r["metadata"]["setup_id"] for r in records}
    if len(setups)<10:reasons.append("FEWER_THAN_10_INDEPENDENT_SETUPS_DEVELOPMENT_GATE")
    return dict(ready=not reasons,reason_codes=reasons,setup_count=len(setups),record_count=len(records),synthetic_mixing_allowed=False)
