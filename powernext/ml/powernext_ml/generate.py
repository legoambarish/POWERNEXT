"""Reproducible development dataset built exclusively through simulate()."""
from __future__ import annotations
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
from pathlib import Path
import json
import time
import numpy as np
from scipy.stats import qmc
from .common import digest, file_hash, write_json, log, source_hashes, runtime_versions
from .physics_adapter import load_adapter
from physics_engine import Configuration, Setup
from physics_engine.network import PhysicsError


def design(adapter, samples_per_stratum=12, seed=20261002):
    if hasattr(adapter,"design_requests"):
        requests=adapter.design_requests(samples_per_stratum=samples_per_stratum,seed=seed)
        if not requests:raise ValueError("Adapter returned an empty approved design")
        for i,r in enumerate(requests):
            if not {"configuration","setup","setup_family_id","case_kind","target_crest_V"}<=r.keys():
                raise ValueError("Adapter design violates request envelope")
            r["row_id"]=f"case_{i:06d}"
        return requests
    requests=[]
    rng=np.random.default_rng(seed)
    count=len(adapter.stages)*len(adapter.fronts)*2*samples_per_stratum
    latin=qmc.LatinHypercube(d=6,seed=seed).random(count)
    idx=0
    for mode in ["LI","SI"]:
        for n in adapter.stages:
            for rf in adapter.fronts:
                for j in range(samples_per_stratum):
                    z=latin[idx]; idx+=1
                    s=Setup(float(10**(-10+2*z[0])),float(10**(-10+np.log10(20)*z[1])),
                            0. if j==0 else float(z[2]*1e-9),
                            0. if j==0 else float(10**(-7+3*z[3])),
                            "ADDITIONAL_DISJOINT" if j%2==0 else "INCLUDED_IN_OTHER_COMPONENTS",
                            loop_resistance_ohm=0. if j%3==0 else float(.1+19.9*z[4]),
                            setup_id=f"DEV_{mode}_N{n}_R{rf}_{j}")
                    charge=float(20000+180000*z[5])
                    if j==0: charge=20000.
                    if j==1: charge=200000.
                    for top in adapter.topologies:
                        c=Configuration(mode,n,charge,rf,adapter.tails[mode][0],top,recipe_id=adapter.recipe)
                        requests.append(dict(configuration=asdict(c),setup=asdict(s),setup_family_id=s.setup_id,case_kind="space_filling",target_crest_V=float(rng.uniform(50000,2400000))))
    # Predeclared targeted front/peak boundary probes from an independent RC
    # solve. Final labels ALWAYS come from RLC simulate, never this root-finder.
    from scipy.optimize import brentq
    for mode,rf,bounds in [("LI",30,[.84,1.56]),("SI",3700,[200,300])]:
        for top in adapter.topologies:
            c=Configuration(mode,10,150000,rf,adapter.tails[mode][0],top,recipe_id=adapter.recipe)
            for bound in bounds:
                for delta in [-.01,0,.01]:
                    def f(dut):
                        s=Setup(dut,100e-12,0,0,"INCLUDED_IN_OTHER_COMPONENTS")
                        return adapter.features(asdict(c),asdict(s))["baseline_front_us"]-bound*(1+delta)
                    try: dut=brentq(f,1e-11,1e-7,xtol=1e-19)
                    except ValueError: continue
                    family=f"BOUNDARY_{mode}_{top}_{bound}_{delta}"
                    s=Setup(dut,100e-12,0,0,"INCLUDED_IN_OTHER_COMPONENTS",setup_id=family)
                    requests.append(dict(configuration=asdict(c),setup=asdict(s),setup_family_id=family,case_kind="front_boundary",target_crest_V=1300000.))
    # Fixed integration fixtures, plus true charge/polarity variants. They are
    # grouped by normalized physical equivalence and nominal family.
    for mode,rf,target in [("LI",30,1400000.),("SI",3700,1300000.)]:
        for top in adapter.topologies:
            family=f"REFERENCE_{mode}_{top}"
            s=Setup(850e-12,500e-12,150e-12,18.5e-6,"ADDITIONAL_DISJOINT",setup_id=family)
            for charge,polarity in [(150000.,1),(75000.,1),(150000.,-1)]:
                c=Configuration(mode,10,charge,rf,adapter.tails[mode][0],top,polarity,adapter.recipe)
                requests.append(dict(configuration=asdict(c),setup=asdict(s),setup_family_id=family,case_kind="scaling_fixture",target_crest_V=target*charge/150000))
    ref=dict(requests[-1])
    ref["configuration"]=asdict(Configuration("LI",10,100000,30,180,adapter.topologies[0],recipe_id=adapter.recipe))
    for key,value in [("stages",1),("stages",16),("stage_charge_V",201000),("front_per_stage_ohm",50),("tail_per_stage_ohm",520)]:
        r=json.loads(json.dumps(ref));r["configuration"][key]=value;r["case_kind"]="invalid_input";requests.append(r)
    for key,value in [("dut_capacitance_F",-1e-9),("basic_coverage_assumption","UNKNOWN")]:
        r=json.loads(json.dumps(ref));r["setup"][key]=value;r["case_kind"]="invalid_input";requests.append(r)
    r=json.loads(json.dumps(ref));r.update(case_kind="infeasible_target",target_crest_V=5000000.);requests.append(r)
    r=json.loads(json.dumps(ref));r.update(case_kind="truncated_record",solver_overrides={"t_end_s":1e-6});requests.append(r)
    for i,r in enumerate(requests): r["row_id"]=f"case_{i:06d}"
    return requests


def run_case(task):
    request, directory, adapter_name, n_points=task
    adapter=load_adapter(adapter_name)
    start=time.perf_counter()
    row=dict(request, **adapter.provenance, topology_version=request["configuration"]["topology_id"], simulator_options=dict(n_points=n_points,rtol=1e-9,atol=1e-11,**request.get("solver_overrides",{})), regression_eligible=False,
             gain=None,front_us=None,tail_us=None,crest_V=None,T1_s=None,Tp_s=None,T2_s=None,
             waveform_path=None,metadata_path=None,features=None,reason_codes=[],numeric_status=None,waveform_status=None,compliance_status="INDETERMINATE")
    try:
        row["physical_shape_id"]=adapter.shape_identity(row["configuration"],row["setup"])
        row["features"]=adapter.features(row["configuration"],row["setup"])
        result=adapter.simulate(row["configuration"],row["setup"],target_crest_V=row["target_crest_V"],**row["simulator_options"])
        prefix=Path(directory)/"waveforms"/row["row_id"]
        result.save(prefix)
        m=result.metadata;met=m["metrics"]
        row.update(status="SIMULATED",numeric_status=m["numeric_status"],waveform_status=met["waveform_status"],compliance_status=met["compliance_status"],
                   hardware_status=m["hardware_status"],eligible_for_hardware_recommendation=False,
                   metadata_path=f"waveforms/{row['row_id']}.json",waveform_path=f"waveforms/{row['row_id']}.npz",
                   metadata_sha256=file_hash(str(prefix)+".json"),waveform_sha256=file_hash(str(prefix)+".npz"),
                   reason_codes=met["reasons"],energy_balance_relative_error=m["energy_balance_relative_error"])
        if m["numeric_status"]=="VALID" and met["waveform_status"]=="VALID_CLEAN_FULL_IMPULSE":
            row.update(regression_eligible=True,gain=met["crest_magnitude_V"]/abs(m["derived"]["U0_V"]),
                       front_us=(met["T1_s"] if row["configuration"]["impulse_type"]=="LI" else met["Tp_s"])*1e6,
                       tail_us=met["T2_s"]*1e6,crest_V=met["crest_magnitude_V"],T1_s=met["T1_s"],Tp_s=met["Tp_s"],T2_s=met["T2_s"])
    except PhysicsError as exc:
        row.update(status="INVALID_OR_UNSUPPORTED",reason_codes=[exc.code],physical_shape_id=row.get("physical_shape_id",digest(request)))
    # Unexpected exceptions propagate and abort generation. Never count software
    # faults as ordinary physical failures.
    row["simulation_seconds"]=time.perf_counter()-start
    return row


def generate(output, samples_per_stratum=12, seed=20261002, workers=4, n_points=1600, adapter_name="provisional"):
    output=Path(output)
    if output.exists(): raise FileExistsError(f"Immutable dataset destination exists: {output}")
    adapter=load_adapter(adapter_name)
    requests=design(adapter,samples_per_stratum,seed)
    output.mkdir(parents=True)
    settings=dict(samples_per_stratum=samples_per_stratum,seed=seed,n_points=n_points,adapter=adapter_name)
    manifest=dict(schema_version="ml_dataset_v1",purpose="DEVELOPMENT_NOT_PRODUCTION_FREEZE",**adapter.provenance,
                  settings=settings,source_hashes=source_hashes(),runtime=runtime_versions(),design_sha256=digest(requests),status="IN_PROGRESS")
    manifest["dataset_id"]="sim_"+digest(manifest)[:16]
    write_json(output/"manifest.json",manifest)
    write_json(output/"design.json",requests)
    log(f"Generating {len(requests)} cases using {workers} workers; {manifest['dataset_id']}")
    rows=[]
    tasks=((r,str(output),adapter_name,n_points) for r in requests)
    with ProcessPoolExecutor(max_workers=workers) as pool, (output/"rows.jsonl").open("w",encoding="utf-8") as stream:
        for i,row in enumerate(pool.map(run_case,tasks,chunksize=4),1):
            row["dataset_id"]=manifest["dataset_id"]
            stream.write(json.dumps(row,allow_nan=False)+"\n");stream.flush();rows.append(row)
            if i%40==0 or i==len(requests): log(f"Generated {i}/{len(requests)}; regression-eligible {sum(r['regression_eligible'] for r in rows)}")
    from collections import Counter
    manifest.update(status="COMPLETE",row_count=len(rows),regression_eligible_count=sum(r["regression_eligible"] for r in rows),
                    status_counts=dict(Counter(r["status"] for r in rows)),waveform_counts=dict(Counter(str(r["waveform_status"]) for r in rows)),
                    compliance_counts=dict(Counter(r["compliance_status"] for r in rows)),rows_sha256=file_hash(output/"rows.jsonl"))
    write_json(output/"manifest.json",manifest)
    return manifest
