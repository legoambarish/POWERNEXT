"""Predeclared input design for the October 4 component/recipe catalog.

No simulation outcomes are used to choose the grouped split or repair labels.
The targeted region deliberately probes expected LI feasibility and neighboring
failures; independent random strata cover the wider inventory.
"""
import json
from dataclasses import asdict
import numpy as np
from scipy.stats import qmc
from scipy.optimize import brentq
from physics_engine import Configuration,Setup
from physics_engine.recipes import COMPONENTS,SINGLE,PARALLEL

def design_requests(adapter,samples_per_stratum=8,seed=20261004):
    if type(samples_per_stratum) is not int or samples_per_stratum<2:
        raise ValueError('At least two samples per stratum')
    rng=np.random.default_rng(seed); requests=[]
    combinations=[(mode,top,n,rf,rt,SINGLE) for mode in ['LI','SI'] for top in adapter.topologies for n in adapter.stages for rf in COMPONENTS for rt in COMPONENTS]
    combinations += [('LI','GSHUNT_v0',n,rf,180,PARALLEL) for n in adapter.stages for rf in COMPONENTS]
    latin=qmc.LatinHypercube(d=6,seed=seed).random(len(combinations)*samples_per_stratum)
    def add(c,s,family,kind,target=1550e3,**kw):
        requests.append(dict(configuration=asdict(c),setup=asdict(s),setup_family_id=family,case_kind=kind,target_crest_V=target,**kw))
    for k,(mode,top,n,rf,rt,recipe) in enumerate(combinations):
        for j in range(samples_per_stratum):
            z=latin[k*samples_per_stratum+j]; family=f'V2_SPACE_{k}_{j}'
            s=Setup(float(10**(-10+2*z[0])),float(10**(-10+np.log10(20)*z[1])),
                    0. if j==0 else float(z[2]*1e-9),0. if j==0 else float(10**(-7+3*z[3])),
                    'ADDITIONAL_DISJOINT' if j%2==0 else 'INCLUDED_IN_OTHER_COMPONENTS',
                    loop_resistance_ohm=0. if j%3==0 else float(.1+19.9*z[4]),setup_id=family)
            q=20000. if j==0 else (200000. if j==1 else float(20000+180000*z[5]))
            add(Configuration(mode,n,q,rf,rt,top,recipe_id=recipe),s,family,'space_filling',float(rng.uniform(50e3,2400e3)))
    # Fixed in advance: LI near the expected useful load region and matched
    # single-tail controls. All recipes for one setup remain in one group.
    for n in range(6,12):
        for rf in [30,46]:
            for j in range(24):
                family=f'V2_LI_NEIGHBORHOOD_{n}_{rf}_{j}'
                s=Setup(float(rng.uniform(.2,1.8)*1e-9),float(rng.uniform(.3,.8)*1e-9),float(rng.uniform(0,.3)*1e-9),float(rng.uniform(1,45)*1e-6),'ADDITIONAL_DISJOINT',setup_id=family)
                for rt,recipe in [(180,SINGLE),(520,SINGLE),(180,PARALLEL)]:
                    add(Configuration('LI',n,150e3,rf,rt,'GSHUNT_v0',recipe_id=recipe),s,family,'LI_boundary_neighborhood')
    # SI useful-region probes with held-together topology pairs.
    for n in range(3,16):
        for rf in [3700,5000]:
            for j in range(12):
                family=f'V2_SI_NEIGHBORHOOD_{n}_{rf}_{j}'
                s=Setup(float(rng.uniform(.2,3)*1e-9),float(rng.uniform(.1,1)*1e-9),float(rng.uniform(0,.5)*1e-9),float(rng.uniform(0,80)*1e-6),'ADDITIONAL_DISJOINT',setup_id=family)
                for top in adapter.topologies:
                    add(Configuration('SI',n,150e3,rf,5000,top,recipe_id=SINGLE),s,family,'SI_boundary_neighborhood',1300e3)
    # Independent analytic front-boundary input solve; final labels still RLC.
    for mode,rf,rt,recipe,bounds in [('LI',30,180,PARALLEL,[.84,1.56]),('SI',3700,5000,SINGLE,[200,300])]:
        for n in [6,10,14]:
            for bound in bounds:
                for offset in [-.02,0,.02]:
                    c=Configuration(mode,n,150e3,rf,rt,'GSHUNT_v0',recipe_id=recipe)
                    def fun(dut):
                        s=Setup(dut,100e-12,0,0,'INCLUDED_IN_OTHER_COMPONENTS')
                        return adapter.features(asdict(c),asdict(s))['baseline_front_us']-bound*(1+offset)
                    dut=brentq(fun,1e-11,1e-7,xtol=1e-19)
                    family=f'V2_FRONT_BOUND_{mode}_{n}_{bound}_{offset}'
                    s=Setup(dut,100e-12,0,0,'INCLUDED_IN_OTHER_COMPONENTS',setup_id=family)
                    add(c,s,family,'front_boundary')
    for mode,rf,rt,recipe in [('LI',30,180,PARALLEL),('SI',3700,5000,SINGLE)]:
        family=f'V2_SCALING_{mode}'
        s=Setup(850e-12,500e-12,150e-12,18.5e-6,'ADDITIONAL_DISJOINT',setup_id=family)
        for q,pol in [(150e3,1),(75e3,1),(150e3,-1)]:
            add(Configuration(mode,9,q,rf,rt,'GSHUNT_v0',pol,recipe),s,family,'scaling_fixture',1550e3*q/150e3)
    ref=json.loads(json.dumps(requests[-1])); ref['configuration'].update(impulse_type='LI',front_per_stage_ohm=30,tail_per_stage_ohm=180,recipe_id=SINGLE)
    for key,value in [('stages',1),('stages',16),('stage_charge_V',201000),('front_per_stage_ohm',50),('tail_per_stage_ohm',521)]:
        r=json.loads(json.dumps(ref));r['configuration'][key]=value;r['case_kind']='invalid_input';requests.append(r)
    for key,value in [('dut_capacitance_F',-1e-9),('basic_coverage_assumption','UNKNOWN')]:
        r=json.loads(json.dumps(ref));r['setup'][key]=value;r['case_kind']='invalid_input';requests.append(r)
    r=json.loads(json.dumps(ref));r.update(case_kind='infeasible_target',target_crest_V=5000000.);requests.append(r)
    r=json.loads(json.dumps(ref));r.update(case_kind='truncated_record',solver_overrides={'t_end_s':1e-6});requests.append(r)
    return requests
