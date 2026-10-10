"""Independent numerical and legacy-compatibility checks for profile integration."""
import unittest
import numpy as np
import powernext_v3
from powernext_v3.physics import simulate, scale_response, build_network, derive
from powernext_v3.profiles import get_profile
from physics_engine import Configuration, Setup, simulate as legacy_simulate
from physics_engine.analytic import voltage
from physics_engine.network import PhysicsError
from physics_engine.reference_cases import uniform_stage_chain

SETUP = dict(dut_capacitance_F=850e-12, divider_capacitance_F=500e-12,
             stray_capacitance_F=150e-12, loop_inductance_H=18.5e-6,
             basic_coverage_assumption="ADDITIONAL_DISJOINT")


def config(mode="LI", top="GSHUNT_v0", **changes):
    return dict(dict(impulse_type=mode, stages=9, stage_charge_V=150e3,
        front_per_stage_ohm=30 if mode=="LI" else 3700,
        tail_per_stage_ohm=180 if mode=="LI" else 5000,
        topology_id=top, polarity=1), **changes)


class ProfilesPhysicsTests(unittest.TestCase):
    def test_energy_domains_are_separate(self):
        for domain, expected in [("cpri_0p5uf",150000.),("research_3uf",900000.)]:
            cn, _, _, d = build_network(config(stages=15,stage_charge_V=200e3),SETUP,domain)
            self.assertAlmostEqual(cn.E0_J,expected,places=6)
            self.assertEqual(d["profile"]["research_only"],domain=="research_3uf")
        self.assertEqual(get_profile("research_3uf").stage_energy_max_J,60000.)
        with self.assertRaises(ValueError):get_profile("3uf")

    def test_legacy_single_response_preserved(self):
        for mode in ("LI","SI"):
            for top in ("GSHUNT_v0","OSHUNT_v0"):
                c=config(mode,top)
                old=legacy_simulate(Configuration(**c),Setup(**SETUP),solver="modal",n_points=1600)
                new=simulate(c,SETUP)
                for key in ("raw_crest_magnitude_V","T1_s","Tp_s","T2_s"):
                    a,b=old.metadata["metrics"][key],new.metadata["metrics"][key]
                    if a is None:self.assertIsNone(b)
                    else:self.assertAlmostEqual(a/b,1,places=10)
                self.assertEqual(old.metadata["numeric_status"],new.metadata["numeric_status"])

    def test_two_domains_zero_L_independent_analytic_both_topologies(self):
        for domain in ("cpri_0p5uf","research_3uf"):
            for top in ("GSHUNT_v0","OSHUNT_v0"):
                cn,_,_,d=build_network(config(top=top),dict(SETUP,loop_inductance_H=0),domain)
                t=np.r_[0,np.geomspace(1e-10,.003,500)]
                actual=cn.integrate_linear(.003).voltage("o",t)
                reference=voltage(t,d["Cg_F"],d["CL_F"],d["Rf_total_ohm"],d["Rt_total_ohm"],d["U0_V"],top)
                self.assertLess(np.max(abs(actual-reference))/d["U0_V"],2e-9)

    def test_general_equivalent_uniform_reduction_two_domains(self):
        # Independent multi-stage graph, with non-inventory equivalents from
        # ideal mixed sub-networks. This proves the declared GSHUNT slice model.
        for domain in ("cpri_0p5uf","research_3uf"):
            c=config(stages=4,front_per_stage_ohm=30+1/(1/46+1/180),tail_per_stage_ohm=1/(1/180+1/520))
            cn,_,_,d=build_network(c,SETUP,domain)
            chain=uniform_stage_chain(4,get_profile(domain).stage_capacitance_F,c["front_per_stage_ohm"],c["tail_per_stage_ohm"],d["CL_F"],SETUP["loop_inductance_H"],c["stage_charge_V"])
            t=np.geomspace(1e-9,.003,600)
            actual=cn.integrate_linear(.003).voltage("o",t)
            expected=chain.integrate(.003).voltage("o",t)
            self.assertLess(np.max(abs(actual-expected))/d["U0_V"],3e-8)
            self.assertAlmostEqual(cn.E0_J,chain.E0_J,places=6)

    def test_reused_charge_and_polarity_match_independent_solve(self):
        for domain in ("cpri_0p5uf","research_3uf"):
            base=simulate(config("SI"),SETUP,domain_id=domain)
            reused=scale_response(base,90000.,polarity=-1,target_crest_V=700000.)
            independent=simulate(config("SI",stage_charge_V=90000.,polarity=-1),SETUP,domain_id=domain,target_crest_V=700000.)
            for key in ("crest_magnitude_V","Tp_s","T2_s"):
                self.assertAlmostEqual(reused.metadata["metrics"][key]/independent.metadata["metrics"][key],1,places=9)
            self.assertEqual(reused.metadata["metrics"]["checks"],independent.metadata["metrics"]["checks"])
            self.assertAlmostEqual(reused.metadata["stored_energy_J"],independent.metadata["stored_energy_J"],places=6)
            self.assertEqual(base.metadata["inputs"]["configuration"]["stage_charge_V"],150000.)

    def test_known_constraints_are_enforced(self):
        for changes in (dict(stages=16),dict(stages=True),dict(stage_charge_V=200001),dict(polarity=True),dict(front_per_stage_ohm=-1)):
            with self.assertRaises(PhysicsError):derive(config(**changes),SETUP)
        with self.assertRaises(PhysicsError):derive(config(),dict(SETUP,dut_capacitance_F=float("nan")))

    def test_research_not_hardware_approved(self):
        result=simulate(config(),SETUP,domain_id="research_3uf")
        self.assertFalse(result.metadata["eligible_for_hardware_recommendation"])
        self.assertEqual(result.metadata["evidence_domain"],"RESEARCH_SYNTHETIC")
        self.assertTrue(result.metadata["numerical_pass_is_not_IEC_certification"])


if __name__=="__main__":unittest.main()
