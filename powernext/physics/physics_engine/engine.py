"""Reference simulate(configuration, setup): CPRI component values, provisional connectivity."""
from __future__ import annotations
from dataclasses import dataclass,asdict
import hashlib,json
import numpy as np
from scipy.optimize import brentq
from scipy.integrate import simpson
from .network import Network,Element,PhysicsError
from .evaluator import evaluate
from .recipes import resolve_recipe, PROFILE_ID

@dataclass(frozen=True)
class Configuration:
    impulse_type: str
    stages: int
    stage_charge_V: float
    front_per_stage_ohm: float
    tail_per_stage_ohm: float
    topology_id: str              # GSHUNT_v0 or OSHUNT_v0, BOTH provisional
    polarity: int = 1
    recipe_id: str = "DEV_UNIFORM_SINGLE_v2"

@dataclass(frozen=True)
class Setup:
    dut_capacitance_F: float
    divider_capacitance_F: float
    stray_capacitance_F: float
    loop_inductance_H: float
    basic_coverage_assumption: str # ADDITIONAL_DISJOINT or INCLUDED_IN_OTHER_COMPONENTS
    loop_resistance_ohm: float = 0.0
    load_resistance_ohm: float|None = None
    setup_id: str = "DEVELOPMENT_SETUP"
    auxiliary_assumption: str = "UNCONFIRMED_AUXILIARY_BRANCHES_OMITTED"

    @property
    def total_capacitance_F(self):
        return self.dut_capacitance_F+self.divider_capacitance_F+self.stray_capacitance_F+(480e-12 if self.basic_coverage_assumption=="ADDITIONAL_DISJOINT" else 0.0)

class SimulationResult:
    def __init__(self,metadata,arrays): self.metadata,self.arrays=metadata,arrays
    def save(self,path_prefix):
        from pathlib import Path
        p=Path(path_prefix); p.parent.mkdir(parents=True,exist_ok=True)
        np.savez_compressed(str(p)+".npz",**self.arrays)
        Path(str(p)+".json").write_text(json.dumps(self.metadata,indent=2,allow_nan=False),encoding="utf-8")

def validate(c:Configuration,s:Setup):
    if type(c.stages) is not int or not 2<=c.stages<=15: raise PhysicsError("STAGE_COUNT_LIMIT","CPRI request domain is 2 through 15 active stages.")
    if c.impulse_type not in ("LI","SI"): raise PhysicsError("INVALID_IMPULSE_TYPE",c.impulse_type)
    if not np.isfinite(c.stage_charge_V) or not 0<c.stage_charge_V<=200e3: raise PhysicsError("STAGE_VOLTAGE_LIMIT","Stage-charge magnitude must be positive and at most 200 kV.")
    if c.polarity not in (-1,1): raise PhysicsError("INVALID_POLARITY","Use +1/-1 separately from charge magnitude.")
    if c.topology_id not in ("GSHUNT_v0","OSHUNT_v0"):
        raise PhysicsError("UNKNOWN_TOPOLOGY_OR_RECIPE", "Select an explicit provisional topology.")
    resolve_recipe(c)
    for name in ["dut_capacitance_F","divider_capacitance_F","stray_capacitance_F","loop_inductance_H","loop_resistance_ohm"]:
        x=getattr(s,name)
        if not np.isfinite(x) or x<0: raise PhysicsError("INVALID_SETUP_PARAMETER",name)
    if s.basic_coverage_assumption not in ("ADDITIONAL_DISJOINT","INCLUDED_IN_OTHER_COMPONENTS"):
        raise PhysicsError("CAPACITANCE_COVERAGE_UNRESOLVED","Explicitly declare the development coverage scenario.")
    if s.total_capacitance_F<=0: raise PhysicsError("ZERO_OUTPUT_CAPACITANCE","Total modeled output capacitance must be positive.")
    if s.load_resistance_ohm is not None and (not np.isfinite(s.load_resistance_ohm) or s.load_resistance_ohm<=0):
        raise PhysicsError("INVALID_SETUP_PARAMETER","load_resistance_ohm")
    if s.auxiliary_assumption!="UNCONFIRMED_AUXILIARY_BRANCHES_OMITTED":
        raise PhysicsError("AUXILIARY_TOPOLOGY_NOT_IMPLEMENTED","Use the graph API to specify actual branch endpoints and firing states.")

def build_network(c:Configuration,s:Setup):
    validate(c,s)
    Cg=.5e-6/c.stages; U0=c.polarity*c.stages*c.stage_charge_V
    Rf=c.stages*c.front_per_stage_ohm+s.loop_resistance_ohm
    recipe=resolve_recipe(c)
    Rt=c.stages*recipe["tail_equivalent_per_stage_ohm"]
    elems=[Element("Cg","C","g","0",Cg),Element("CL","C","o","0",s.total_capacitance_F),
           *[Element("Rt" if len(recipe["tail_components_ohm"])==1 else f"Rt_{r:g}",
                     "R","g" if c.topology_id=="GSHUNT_v0" else "o","0",c.stages*r)
             for r in recipe["tail_components_ohm"]]]
    if s.loop_inductance_H>0: elems.append(Element("front_path","RL","g","o",s.loop_inductance_H,Rf))
    else: elems.append(Element("front_path","R","g","o",Rf))
    if s.load_resistance_ohm is not None: elems.append(Element("load_leakage","R","o","0",s.load_resistance_ohm))
    net=Network(["g","o"],elems)
    return net.compile({"g":U0,"o":0.0}),dict(Cg_F=Cg,CL_F=s.total_capacitance_F,Rf_total_ohm=Rf,Rt_total_ohm=Rt,U0_V=U0,recipe=recipe)

def sample_trajectory(traj,polarity:int,n_points:int=7000):
    # Log mesh resolves front and tail; actual stationary points and fractional
    # roots are inserted so exported samples and reported parameters agree.
    t=np.unique(np.r_[0.0,np.geomspace(traj.t_end*1e-9,traj.t_end,n_points)])
    d=polarity*traj.voltage_derivative("o",t)
    ext=[]
    for k in np.flatnonzero(d[:-1]*d[1:]<0):
        f=lambda x:polarity*float(traj.voltage_derivative("o",x))
        # At the exact zero-current initial condition, vector/scalar BLAS
        # cancellation can disagree at roundoff level. Recheck the actual
        # scalar function's bracket; never invent a root to satisfy brentq.
        if f(t[k])*f(t[k+1])<0:
            ext.append(brentq(f,t[k],t[k+1],xtol=1e-16,rtol=1e-13))
    t=np.unique(np.r_[t,ext]); u=polarity*traj.voltage("o",t)
    peak=float(np.max(u)); roots=[]
    for level in [.3*peak,.9*peak,.5*peak]:
        z=u-level
        for k in np.flatnonzero(z[:-1]*z[1:]<0):
            f=lambda x:polarity*float(traj.voltage("o",x))-level
            if f(t[k])*f(t[k+1])<0:
                roots.append(brentq(f,t[k],t[k+1],xtol=1e-16,rtol=1e-13))
    return np.unique(np.r_[t,roots])

def simulate(configuration:Configuration,setup:Setup,*,target_crest_V:float|None=None,
             t_end_s:float|None=None,rtol:float=1e-9,atol:float=1e-11,n_points:int=7000,solver:str="Radau")->SimulationResult:
    c,s=configuration,setup
    cn,der=build_network(c,s)
    # 12 slow modal time constants provide a decay record rather than assuming
    # all LI/SI circuits necessarily have the target tail time.
    eig=np.linalg.eigvals(cn.A)
    if np.any(eig.real>=0): raise PhysicsError("UNDECAYING_NETWORK","No finite passive impulse record established.")
    default_end=12.0/min(-eig.real)
    tend=default_end if t_end_s is None else t_end_s
    if tend>0.2: raise PhysicsError("TIME_DOMAIN_OUTSIDE_REFERENCE_SCOPE","This release limits a record to 200 ms; do not silently truncate.")
    if solver not in ("Radau", "modal"):
        raise PhysicsError("UNKNOWN_SOLVER", solver)
    traj=cn.integrate_linear(tend,rtol=rtol,atol=atol) if solver=="modal" else cn.integrate(tend,rtol=rtol,atol=atol)
    t=sample_trajectory(traj,c.polarity,n_points)
    v,i=traj.states(t); out=v[cn.net.index["o"]]
    met=evaluate(t,out,c.impulse_type,c.polarity,beginning_s=0.0,target_crest_V=target_crest_V)
    W=traj.energy(t); p=traj.dissipated_power(t); diss=float(simpson(p,x=t))
    Eres=float((W[-1]+diss-cn.E0_J)/cn.E0_J)
    front_current=i[0] if i.shape[0] else (v[0]-v[1])/der["Rf_total_ohm"]
    # Per-branch energy for the reduced network; NOT a claim of equal stress
    # sharing in an unverified multi-stage CPRI hardware arrangement.
    loss={}
    for elem in cn.net.elements:
        if elem.kind=="R":
            drop=cn.net.incidence(elem.a,elem.b)@v
            loss[elem.name]=float(simpson(drop**2/elem.value,x=t))
        elif elem.kind=="RL":
            cur=i[cn.net.rl_names.index(elem.name)]
            loss[elem.name]=float(simpson(cur**2*elem.series_r_ohm,x=t))
    inputs={"configuration":asdict(c),"setup":asdict(s)}
    hash_=hashlib.sha256(json.dumps(inputs,sort_keys=True,allow_nan=False).encode()).hexdigest()
    assumptions=["Ideal simultaneous complete erection; equal initial stage charge.",
                 f"Explicit {c.recipe_id}: {der['recipe']['description']}; unconfirmed CPRI connection and quantities.",
                 "Linear capacitive DUT; divider loading at DUT node; no flashover/corona/measurement transfer function.",
                 f"480 pF coverage scenario: {s.basic_coverage_assumption}.",
                 "Charging, potential and discharge branches omitted only as an explicit development scenario.",
                 "Minimum reliable stage charge and pulse/component ratings are unknown."]
    metadata={"schema_version":"2.0.0","model_version":"0.2.0","profile_id":PROFILE_ID,
              "topology_id":c.topology_id,"recipe_id":c.recipe_id,"evidence_domain":"PROVISIONAL_TOPOLOGY_SYNTHETIC",
              "input_sha256":hash_,"inputs":inputs,"derived":der,"metrics":met,"assumptions":assumptions,
              "solver":{"method":getattr(traj,"method","Radau"),"requested_method":solver,"rtol":rtol,"atol":atol,"t_end_s":float(tend),"sample_count":len(t)},
              "numeric_status":"VALID" if abs(Eres)<1e-4 else "ENERGY_AUDIT_FAILED",
              "hardware_status":"PROVISIONAL_NOT_VERIFIED","eligible_for_hardware_recommendation":False,
              "hardware_reason_codes":["TOPOLOGY_UNCONFIRMED","RECIPE_UNCONFIRMED","AUXILIARY_BRANCH_STATE_UNCONFIRMED","BASIC_CAPACITANCE_COVERAGE_ASSUMED","MIN_STAGE_CHARGE_UNKNOWN","COMPONENT_PULSE_RATINGS_UNKNOWN","COMPONENT_QUANTITIES_AND_SLOTS_UNKNOWN"],
              "request_range_status":None if target_crest_V is None else ("WITHIN_REQUEST_DOMAIN" if 50e3<=target_crest_V<=2400e3 else "OUTSIDE_CPRI_REQUEST_DOMAIN"),
              "stored_energy_J":cn.E0_J,"remaining_energy_J":float(W[-1]),"integrated_loss_J":diss,
              "energy_balance_relative_error":Eres,"branch_loss_J":loss,
              "max_energy_increase_fraction":float(max(0,np.max(np.diff(W)))/cn.E0_J),
              "voltage_gain":float(met["raw_crest_magnitude_V"]/abs(der["U0_V"])),
              "front_current_peak_A":float(np.max(np.abs(front_current))),
              "component_bill_of_materials":der["recipe"]["bill_of_materials"],
              "tail_stress_proxies":[{
                  "component_ohm":r,"assumed_count":c.stages,
                  "voltage_peak_per_component_V":float(np.max(np.abs(v[0 if c.topology_id=="GSHUNT_v0" else 1]))/c.stages),
                  "current_peak_per_branch_A":float(np.max(np.abs(v[0 if c.topology_id=="GSHUNT_v0" else 1]))/(c.stages*r)),
                  "energy_per_component_J":loss["Rt" if len(der["recipe"]["tail_components_ohm"])==1 else f"Rt_{r:g}"]/c.stages,
                  "status":"IDEAL_UNIFORM_SHARING_PROXY_NOT_RATING_APPROVAL"}
                  for r in der["recipe"]["tail_components_ohm"]],
              "numerical_pass_is_not_IEC_certification":True}
    return SimulationResult(metadata,{"time_s":t,"voltage_V":out,"generator_voltage_V":v[0],
                                     "front_current_A":front_current,"stored_energy_J":W,"dissipated_power_W":p})
