"""Adapter owns profile resolution; the original physics package is immutable.

A later confirmed adapter implements this same interface. Its graph and evidence
must be independently reviewed; setting a boolean cannot promote this adapter.
"""
from __future__ import annotations
import importlib
import json
from dataclasses import asdict
import numpy as np
from .common import PHYSICS, digest, file_hash
from physics_engine import Configuration, Setup, simulate, __version__ as physics_version
from physics_engine.engine import validate
from physics_engine.recipes import COMPONENTS,SINGLE,PARALLEL,resolve_recipe
from physics_engine.evaluator import LIMITS, PROFILE_ID
from physics_engine.network import PhysicsError
from physics_engine.analytic import rates, double_exponential_metrics


class ProvisionalAdapter:
    def __init__(self):
        self.profile = json.loads((PHYSICS / "CPRI_EQUIPMENT_PROFILE.json").read_text(encoding="utf-8"))
        p = self.profile
        # Fail closed if source profile and immutable reference backend diverge.
        assert p["capacitors"]["stage_impulse_capacitance"]["value"] == .5e-6
        assert p["capacitors"]["basic_load_capacitance"]["value"] == 480e-12
        assert p["limits"]["active_stages_min"]["value"] == 2
        assert p["limits"]["available_stages_max"]["value"] == 15
        assert p["limits"]["stage_charge_max"]["value"] == 200000
        assert not p["operational_gate"]["hardware_verified"]
        assert not p["topology"]["approved_recipes"]
        self.stages = list(range(2, 16))
        self.fronts = [x["value"] for x in p["resistors"]["front_per_stage"]]
        assert self.fronts == list(COMPONENTS)
        self.tails = {"LI": [x["value"] for x in p["resistors"]["LI_tail_per_stage_confirmed"]], "SI": [x["value"] for x in p["resistors"]["SI_tail_per_stage"]]}
        assert self.tails == {"LI": list(COMPONENTS), "SI": list(COMPONENTS)}
        self.topologies = p["topology"]["development_topologies"]
        self.recipe = p["topology"]["development_recipes"][0]["id"]
        self.provenance = dict(
            equipment_profile_version=p["profile_id"], equipment_profile_sha256=file_hash(PHYSICS / "CPRI_EQUIPMENT_PROFILE.json"),
            simulator_version=physics_version,
            simulator_sha256=digest({f.name: file_hash(f) for f in sorted((PHYSICS / "physics_engine").glob("*.py"))}),
            evaluator_version="physics_clean_evaluator_0.1.0",
            evaluator_sha256=file_hash(PHYSICS / "physics_engine" / "evaluator.py"),
            waveform_profile_id=PROFILE_ID, recipe_version="OCT04_EXPLICIT_RECIPE_CATALOG_v2",
            topology_spec_sha256=file_hash(PHYSICS / "CIRCUIT_TOPOLOGY_SPEC.md"),
            topology_status="PROVISIONAL_TOPOLOGY", evidence_domain="PROVISIONAL_TOPOLOGY_SYNTHETIC",
            hardware_verified=False, baseline_version="independent_RC_L0_v1",
            baseline_sha256=file_hash(PHYSICS / "physics_engine" / "analytic.py"),
            adapter_version="provisional_adapter_v2",
        )

    def design_requests(self, samples_per_stratum=8, seed=20261004):
        from .design_v2 import design_requests
        return design_requests(self,samples_per_stratum,seed)

    def validate(self, configuration, setup):
        c, s = Configuration(**configuration), Setup(**setup)
        validate(c, s)
        return c, s

    def simulate(self, configuration, setup, **options):
        c, s = self.validate(configuration, setup)
        if "n_points" in options and (type(options["n_points"]) is not int or options["n_points"] < 1000):
            raise ValueError("Require at least 1000 output samples")
        options.setdefault("solver","modal")
        return simulate(c, s, **options)

    def shape_identity(self, configuration, setup):
        c, s = self.validate(configuration, setup)
        # Canonical reduced dynamics; amplitude, polarity, request and partition
        # of terminal capacitance cannot create separate train/test groups.
        values = dict(Cg_F=.5e-6/c.stages, CL_F=s.total_capacitance_F,
                      Rf_ohm=c.stages*c.front_per_stage_ohm+s.loop_resistance_ohm,
                      Rt_ohm=c.stages*resolve_recipe(c)["tail_equivalent_per_stage_ohm"], L_H=s.loop_inductance_H,
                      load_conductance_S=0 if s.load_resistance_ohm is None else 1/s.load_resistance_ohm,
                      topology_id=c.topology_id, provenance=self.provenance)
        # Suppress only insignificant representation differences, not near cases.
        return digest({k: format(v, ".13g") if isinstance(v, float) else v for k,v in values.items()})

    def features(self, configuration, setup):
        c, s = self.validate(configuration, setup)
        if s.load_resistance_ohm is not None:
            raise ValueError("RC baseline v1 has no leakage branch; use physics fallback")
        cg, cl = .5e-6/c.stages, s.total_capacitance_F
        rf, rt = c.stages*c.front_per_stage_ohm+s.loop_resistance_ohm, c.stages*resolve_recipe(c)["tail_equivalent_per_stage_ohm"]
        ceq = cg*cl/(cg+cl)
        alpha, beta = rates(cg, cl, rf, rt, c.topology_id)
        m = double_exponential_metrics(alpha, beta, c.impulse_type)
        gain = m["coefficient_to_crest"]/(rf*cl*(beta-alpha))
        # Inputs are conveniently rescaled for numerical learning; public API SI.
        f = dict(tail_parallel=int(c.recipe_id==PARALLEL),stages=c.stages, front_per_stage_ohm=c.front_per_stage_ohm, tail_per_stage_ohm=c.tail_per_stage_ohm,
                 dut_nF=s.dut_capacitance_F*1e9, divider_nF=s.divider_capacitance_F*1e9,
                 stray_nF=s.stray_capacitance_F*1e9, basic_additional_nF=.48 if s.basic_coverage_assumption=="ADDITIONAL_DISJOINT" else 0.,
                 loop_uH=s.loop_inductance_H*1e6, loop_ohm=s.loop_resistance_ohm,
                 Cg_nF=cg*1e9, CL_nF=cl*1e9, Rf_ohm=rf, Rt_ohm=rt,
                 CL_over_Cg=cl/cg, Rf_CL_us=rf*cl*1e6, Rt_Cg_us=rt*cg*1e6,
                 LC_us=float(np.sqrt(s.loop_inductance_H*ceq)*1e6), zero_L=int(s.loop_inductance_H==0),
                 baseline_gain=gain, baseline_front_us=m["front_or_peak_s"]*1e6, baseline_tail_us=m["T2_s"]*1e6)
        return f


def load_adapter(name="provisional"):
    if name == "provisional":
        return ProvisionalAdapter()
    module, cls = name.split(":")
    adapter = getattr(importlib.import_module(module), cls)()
    required = {"equipment_profile_version", "equipment_profile_sha256", "simulator_version", "simulator_sha256", "evaluator_version", "evaluator_sha256", "waveform_profile_id", "recipe_version", "topology_spec_sha256", "topology_status", "evidence_domain", "hardware_verified", "baseline_version", "baseline_sha256", "adapter_version"}
    if not required <= adapter.provenance.keys():
        raise ValueError("Incomplete adapter provenance")
    if adapter.provenance["topology_status"] == "VERIFIED_PROFILE":
        evidence = adapter.provenance.get("verification_evidence", [])
        if not evidence or not adapter.provenance["hardware_verified"]:
            raise ValueError("Verified adapter requires confirmation evidence")
        for e in evidence:
            if file_hash(e["path"]) != e["sha256"]:
                raise ValueError("Verification source hash mismatch")
    return adapter
