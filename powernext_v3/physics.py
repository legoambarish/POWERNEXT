"""Profile-aware integration of the unchanged verified RLC graph and evaluator.

Two-terminal ideal resistor equivalents preserve external response, not mounting
approval. Continuous equivalent inputs are allowed for reference comparisons;
the optimizer separately requires recipes made from the six supplied parts.
"""
from __future__ import annotations
import copy
import hashlib
import json
from pathlib import Path
import numpy as np
from scipy.integrate import simpson
from physics_engine.engine import Setup, SimulationResult, sample_trajectory
from physics_engine.network import Network, Element, PhysicsError
from physics_engine.evaluator import evaluate
from .profiles import get_profile


def _finite(value, name, positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float, np.number)) or not np.isfinite(value) or (value <= 0 if positive else value < 0):
        raise PhysicsError("INVALID_PARAMETER", name)
    return float(value)


def _resolved(configuration):
    c = copy.deepcopy(configuration)
    for branch in ("front", "tail"):
        key = branch + "_per_stage_ohm"
        if c.get(branch + "_network") is not None:
            from .networks import equivalent_resistance, canonicalize
            tree = canonicalize(c[branch + "_network"])
            resistance = float(equivalent_resistance(tree))
            if key in c and not np.isclose(c[key], resistance, rtol=1e-12, atol=0):
                raise PhysicsError("RECIPE_EQUIVALENT_MISMATCH", branch)
            c[branch + "_network"] = tree
            c[key] = resistance
        _finite(c.get(key), key, positive=True)
    c.setdefault("polarity", 1)
    return c


def derive(configuration, setup, domain_id="cpri_0p5uf"):
    p = get_profile(domain_id)
    c = _resolved(configuration)
    if type(c.get("stages")) is not int or not p.stages_min <= c["stages"] <= p.stages_max:
        raise PhysicsError("STAGE_COUNT_LIMIT", "Active stages must be 2 through 15")
    if c.get("impulse_type") not in ("LI", "SI"):
        raise PhysicsError("INVALID_IMPULSE_TYPE", str(c.get("impulse_type")))
    if c.get("topology_id") not in ("GSHUNT_v0", "OSHUNT_v0"):
        raise PhysicsError("UNKNOWN_TOPOLOGY", str(c.get("topology_id")))
    if type(c["polarity"]) is not int or c["polarity"] not in (-1, 1):
        raise PhysicsError("INVALID_POLARITY", "Use +1 or -1")
    q = _finite(c.get("stage_charge_V"), "stage_charge_V", positive=True)
    n = c["stages"]
    if q > p.stage_charge_max_V or n*q > p.summed_charge_max_V:
        raise PhysicsError("STAGE_VOLTAGE_LIMIT", "Charge exceeds domain voltage limits")
    energy = .5*p.stage_capacitance_F*q*q
    if energy > p.stage_energy_max_J*(1+1e-12) or n*energy > p.total_energy_max_J*(1+1e-12):
        raise PhysicsError("STORED_ENERGY_LIMIT", "Charge exceeds domain energy limits")
    s = Setup(**setup)
    for name in ("dut_capacitance_F", "divider_capacitance_F", "stray_capacitance_F", "loop_inductance_H", "loop_resistance_ohm"):
        _finite(getattr(s, name), name)
    if s.basic_coverage_assumption not in ("ADDITIONAL_DISJOINT", "INCLUDED_IN_OTHER_COMPONENTS"):
        raise PhysicsError("CAPACITANCE_COVERAGE_UNRESOLVED", "Declare basic capacitance coverage")
    if s.total_capacitance_F <= 0:
        raise PhysicsError("ZERO_OUTPUT_CAPACITANCE", "Positive terminal capacitance required")
    if s.load_resistance_ohm is not None:
        _finite(s.load_resistance_ohm, "load_resistance_ohm", positive=True)
    if s.auxiliary_assumption != "UNCONFIRMED_AUXILIARY_BRANCHES_OMITTED":
        raise PhysicsError("AUXILIARY_TOPOLOGY_NOT_IMPLEMENTED", s.auxiliary_assumption)
    return c, s, dict(Cg_F=p.stage_capacitance_F/n, CL_F=s.total_capacitance_F,
        Rf_total_ohm=n*c["front_per_stage_ohm"]+s.loop_resistance_ohm,
        Rt_total_ohm=n*c["tail_per_stage_ohm"], U0_V=c["polarity"]*n*q,
        stage_capacitance_F=p.stage_capacitance_F, stage_energy_J=energy,
        profile=p.as_dict())


def build_network(configuration, setup, domain_id="cpri_0p5uf"):
    c, s, d = derive(configuration, setup, domain_id)
    elems = [Element("Cg", "C", "g", "0", d["Cg_F"]),
             Element("CL", "C", "o", "0", d["CL_F"]),
             Element("Rt", "R", "g" if c["topology_id"] == "GSHUNT_v0" else "o", "0", d["Rt_total_ohm"])]
    elems.append(Element("front_path", "RL", "g", "o", s.loop_inductance_H, d["Rf_total_ohm"]) if s.loop_inductance_H > 0
                 else Element("front_path", "R", "g", "o", d["Rf_total_ohm"]))
    if s.load_resistance_ohm is not None:
        elems.append(Element("load_leakage", "R", "o", "0", s.load_resistance_ohm))
    compiled = Network(["g", "o"], elems).compile({"g": d["U0_V"], "o": 0.})
    return compiled, c, s, d


def source_fingerprint():
    root = Path(__file__).resolve().parent
    legacy = root.parent / "powernext" / "physics" / "physics_engine"
    paths = [root / name for name in ("profiles.py", "physics.py", "networks.py")]
    paths += [legacy / name for name in ("network.py", "engine.py", "evaluator.py", "analytic.py")]
    hashes = {str(path.relative_to(root.parent)).replace("\\", "/"): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths if path.exists()}
    return dict(sha256=hashlib.sha256(json.dumps(hashes, sort_keys=True).encode()).hexdigest(), sources=hashes)


def simulate(configuration, setup, *, domain_id="cpri_0p5uf", target_crest_V=None,
             n_points=1600, solver="modal", t_end_s=None, rtol=1e-9, atol=1e-11):
    if type(n_points) is not int or n_points < 1000:
        raise ValueError("At least 1000 waveform samples required")
    cn, c, s, d = build_network(configuration, setup, domain_id)
    eig = np.linalg.eigvals(cn.A)
    if np.any(eig.real >= 0):
        raise PhysicsError("UNDECAYING_NETWORK", "No finite passive impulse established")
    tend = float(12/min(-eig.real)) if t_end_s is None else _finite(t_end_s, "t_end_s", True)
    if tend > .2:
        raise PhysicsError("TIME_DOMAIN_OUTSIDE_REFERENCE_SCOPE", "Record exceeds 200 ms")
    if solver not in ("modal", "Radau"):
        raise PhysicsError("UNKNOWN_SOLVER", str(solver))
    traj = cn.integrate_linear(tend, rtol=rtol, atol=atol) if solver == "modal" else cn.integrate(tend, rtol=rtol, atol=atol)
    t = sample_trajectory(traj, c["polarity"], n_points)
    v, i = traj.states(t)
    out = v[cn.net.index["o"]]
    metrics = evaluate(t, out, c["impulse_type"], c["polarity"], beginning_s=0., target_crest_V=target_crest_V)
    energy, power = traj.energy(t), traj.dissipated_power(t)
    loss = float(simpson(power, x=t))
    residual = float((energy[-1]+loss-cn.E0_J)/cn.E0_J)
    current = i[0] if i.shape[0] else (v[0]-v[1])/d["Rf_total_ohm"]
    branch_loss = {}
    for elem in cn.net.elements:
        if elem.kind == "R":
            drop = cn.net.incidence(elem.a, elem.b) @ v
            branch_loss[elem.name] = float(simpson(drop**2/elem.value, x=t))
        elif elem.kind == "RL":
            cur = i[cn.net.rl_names.index(elem.name)]
            branch_loss[elem.name] = float(simpson(cur**2*elem.series_r_ohm, x=t))
    inputs = dict(configuration=c, setup=copy.deepcopy(setup), domain_id=domain_id)
    reasons = ["TOPOLOGY_UNCONFIRMED", "MOUNTING_AND_INVENTORY_UNCONFIRMED", "COMPONENT_PULSE_RATINGS_UNKNOWN",
               "MIN_STAGE_CHARGE_UNKNOWN", "AUXILIARY_BRANCH_STATE_UNCONFIRMED"]
    m = dict(schema_version="physics_networks_v3", model_version="3.0.0", domain_id=domain_id,
        profile_id=get_profile(domain_id).profile_id, topology_id=c["topology_id"], inputs=inputs, derived=d,
        input_sha256=hashlib.sha256(json.dumps(inputs, sort_keys=True, allow_nan=False).encode()).hexdigest(),
        metrics=metrics, numeric_status="VALID" if abs(residual) < 1e-4 else "ENERGY_AUDIT_FAILED",
        evidence_domain="RESEARCH_SYNTHETIC" if get_profile(domain_id).research_only else "CPRI_PARAMETERS_PROVISIONAL_TOPOLOGY_SYNTHETIC",
        hardware_status="PROVISIONAL_NOT_VERIFIED", eligible_for_hardware_recommendation=False,
        hardware_reason_codes=reasons, stored_energy_J=cn.E0_J, remaining_energy_J=float(energy[-1]),
        integrated_loss_J=loss, energy_balance_relative_error=residual, branch_loss_J=branch_loss,
        voltage_gain=float(metrics["raw_crest_magnitude_V"]/abs(d["U0_V"])),
        front_current_peak_A=float(np.max(np.abs(current))), numerical_pass_is_not_IEC_certification=True,
        solver=dict(method=getattr(traj, "method", solver), requested_method=solver, rtol=rtol, atol=atol, t_end_s=tend, sample_count=len(t)),
        assumptions=["Ideal simultaneous complete erection and equal uniform stages.",
                     "Purely resistive two-terminal networks; unmodeled connection parasitics and pulse ratings.",
                     "Linear capacitive DUT; no breakdown, corona or measurement transfer function.",
                     "Topology is a declared reduced-circuit hypothesis, not confirmed laboratory mounting.",
                     "Research 3 uF ratings are hypothetical and are not actual CPRI ratings." if get_profile(domain_id).research_only else "Supplied 0.5 uF equipment limits apply."])
    return SimulationResult(m, dict(time_s=t, voltage_V=out, generator_voltage_V=v[0], front_current_A=current,
                                    stored_energy_J=energy, dissipated_power_W=power))


def scale_response(result, stage_charge_V, *, target_crest_V=None, polarity=None):
    """Exact linear amplitude scaling plus fresh conformity evaluation.

    Timing and numeric audit come from the original solved trajectory. This is
    not an ML waveform. The selected voltage is revalidated against the domain.
    """
    m = copy.deepcopy(result.metadata)
    c = m["inputs"]["configuration"]
    old_q, old_polarity = c["stage_charge_V"], c["polarity"]
    c["stage_charge_V"] = stage_charge_V
    c["polarity"] = old_polarity if polarity is None else polarity
    _, _, d = derive(c, m["inputs"]["setup"], m["domain_id"])
    factor = stage_charge_V/old_q
    signed = factor*c["polarity"]/old_polarity
    arrays = {k: np.array(v, copy=True) for k, v in result.arrays.items()}
    for key in ("voltage_V", "generator_voltage_V", "front_current_A"):
        arrays[key] *= signed
    for key in ("stored_energy_J", "dissipated_power_W"):
        arrays[key] *= factor**2
    m["derived"] = d
    m["metrics"] = evaluate(arrays["time_s"], arrays["voltage_V"], c["impulse_type"], c["polarity"], target_crest_V=target_crest_V)
    for key in ("stored_energy_J", "remaining_energy_J", "integrated_loss_J"):
        m[key] *= factor**2
    m["branch_loss_J"] = {k: v*factor**2 for k, v in m["branch_loss_J"].items()}
    m["front_current_peak_A"] *= factor
    m["input_sha256"] = hashlib.sha256(json.dumps(m["inputs"], sort_keys=True, allow_nan=False).encode()).hexdigest()
    m["response_reuse"] = dict(method="EXACT_LINEAR_AMPLITUDE_SCALING_FRESH_EVALUATION", reference_charge_V=old_q)
    return SimulationResult(m, arrays)

