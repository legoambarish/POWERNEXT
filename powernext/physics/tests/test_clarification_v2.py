import unittest
from dataclasses import replace
import numpy as np
from scipy.linalg import expm
from scipy.integrate import solve_ivp
from physics_engine import Configuration,Setup,simulate
from physics_engine.engine import build_network
from physics_engine.recipes import COMPONENTS,SINGLE,PARALLEL,resolve_recipe
from physics_engine.network import PhysicsError
from physics_engine.reference_cases import uniform_stage_chain

SETUP=Setup(850e-12,500e-12,150e-12,18.5e-6,'ADDITIONAL_DISJOINT')
BASE=Configuration('LI',9,184238.3311,30,180,'GSHUNT_v0',recipe_id=PARALLEL)

class TestClarification(unittest.TestCase):
    def test_shared_evaluator_nominal_targets(self):
        from physics_engine.target import nominal_target
        for mode,front,tail in [('LI',1.2e-6,50e-6),('SI',250e-6,2500e-6)]:
            r=nominal_target(mode,1550e3,-1); m=r['metrics']
            self.assertEqual(m['compliance_status'],'PASS')
            self.assertLess(abs((m['T1_s'] if mode=='LI' else m['Tp_s'])/front-1),1e-7)
            self.assertLess(abs(m['T2_s']/tail-1),1e-7)
            self.assertFalse(r['hardware_prediction'])

    def test_roundoff_stationary_bracket_at_zero_current(self):
        c=Configuration('LI',2,200e3,30,30,'GSHUNT_v0')
        r=simulate(c,SETUP,solver='modal',n_points=1600)
        ref=simulate(c,SETUP,solver='Radau',n_points=7000)
        self.assertLess(abs(r.metadata['voltage_gain']/ref.metadata['voltage_gain']-1),1e-7)

    def test_all_six_components_in_both_positions_and_modes(self):
        for mode in ['LI','SI']:
            for front in COMPONENTS:
                for tail in COMPONENTS:
                    c=replace(BASE,impulse_type=mode,front_per_stage_ohm=front,tail_per_stage_ohm=tail,recipe_id=SINGLE)
                    _,d=build_network(c,SETUP)
                    self.assertAlmostEqual(d['Rt_total_ohm'],9*tail,places=8)

    def test_two_physical_branches_not_fictitious_component(self):
        cn,d=build_network(BASE,SETUP)
        self.assertEqual([e.value for e in cn.net.elements if e.name.startswith('Rt_')],[9*180,9*520])
        self.assertAlmostEqual(d['Rt_total_ohm'],9*180*520/(180+520),places=10)
        self.assertEqual(resolve_recipe(BASE)['bill_of_materials'],[
            dict(component_ohm=r,required_count=9,count_status='REQUIRED_BY_HYPOTHESIS_AVAILABLE_QUANTITY_UNKNOWN') for r in [30,180,520]])

    def test_component_quantity_combines_front_and_tail(self):
        rec=resolve_recipe(replace(BASE,front_per_stage_ohm=180))
        self.assertEqual(next(x['required_count'] for x in rec['bill_of_materials'] if x['component_ohm']==180),18)

    def test_equivalent_resistor_input_is_rejected(self):
        with self.assertRaisesRegex(PhysicsError,'COMPONENT_NOT_CONFIRMED'):
            build_network(replace(BASE,tail_per_stage_ohm=180*520/700),SETUP)

    def test_recipe_does_not_silently_expand_domain(self):
        for c in [replace(BASE,impulse_type='SI'),replace(BASE,topology_id='OSHUNT_v0'),replace(BASE,tail_per_stage_ohm=520)]:
            with self.assertRaisesRegex(PhysicsError,'RECIPE_DOMAIN_MISMATCH'): build_network(c,SETUP)

    def test_full_stage_graph_independent_parallel_branches(self):
        for n in [2,9,15]:
            c=replace(BASE,stages=n)
            cn,d=build_network(c,SETUP)
            chain=uniform_stage_chain(n,.5e-6,30,180,SETUP.total_capacitance_F,SETUP.loop_inductance_H,c.stage_charge_V,parallel_tail=520)
            times=np.geomspace(1e-9,.001,500)
            actual=chain.integrate(.001).voltage('o',times)
            expected=cn.integrate_linear(.001).voltage('o',times)
            self.assertLess(np.max(np.abs(actual-expected))/(n*c.stage_charge_V),4e-8)
            self.assertAlmostEqual(chain.E0_J/cn.E0_J,1,places=11)

    def test_modal_against_radau_and_expm(self):
        for mode,front,tail,top,L in [('LI',30,180,'GSHUNT_v0',18.5e-6),('LI',46,520,'OSHUNT_v0',80e-6),('SI',3700,5000,'GSHUNT_v0',0),('SI',5000,30,'OSHUNT_v0',1e-10)]:
            c=replace(BASE,impulse_type=mode,front_per_stage_ohm=front,tail_per_stage_ohm=tail,topology_id=top,recipe_id=SINGLE)
            cn,_=build_network(c,replace(SETUP,loop_inductance_H=L))
            end=12/min(-np.linalg.eigvals(cn.A).real)
            a,b=cn.integrate_linear(end),cn.integrate(end)
            times=np.geomspace(end*1e-9,end,300)
            self.assertLess(np.max(np.abs(a.y(times)-b.y(times))),1e-7)
            for t in [0,end*1e-6,end*.01,end]:
                # Tiny-L matrices are stiff: expm roundoff is checked at a
                # separately justified 2e-6 absolute energy-state tolerance.
                self.assertLess(np.max(np.abs(a.y(t)-expm(cn.A*t)@cn.y0)),2e-6)

    def test_parallel_independent_dimensional_lsoda(self):
        cn,d=build_network(BASE,SETUP)
        def rhs(t,x):
            vg,vo,i=x
            return [-vg/(9*180*d['Cg_F'])-vg/(9*520*d['Cg_F'])-i/d['Cg_F'],i/d['CL_F'],(vg-vo-d['Rf_total_ohm']*i)/SETUP.loop_inductance_H]
        sol=solve_ivp(rhs,(0,.001),[d['U0_V'],0,0],method='LSODA',rtol=2e-10,atol=1e-7,dense_output=True)
        t=np.geomspace(1e-9,.001,500)
        self.assertTrue(sol.success)
        self.assertLess(np.max(abs(sol.sol(t)[1]-cn.integrate_linear(.001).voltage('o',t)))/d['U0_V'],1e-7)

    def test_fixed_load_1550kv_conditional_pass_and_negative_controls(self):
        r=simulate(BASE,SETUP,target_crest_V=1550e3,solver='modal')
        self.assertEqual(r.metadata['metrics']['compliance_status'],'PASS')
        self.assertAlmostEqual(r.metadata['metrics']['T1_s']*1e6,1.29689,places=4)
        self.assertAlmostEqual(r.metadata['metrics']['T2_s']*1e6,50.90867,places=4)
        self.assertFalse(r.metadata['eligible_for_hardware_recommendation'])
        for tail in [180,520]:
            rr=simulate(replace(BASE,tail_per_stage_ohm=tail,recipe_id=SINGLE),SETUP,target_crest_V=1550e3,solver='modal')
            self.assertEqual(rr.metadata['metrics']['compliance_status'],'FAIL')

    def test_parallel_energy_and_stress_accounting(self):
        r=simulate(BASE,SETUP,solver='modal')
        self.assertLess(abs(r.metadata['energy_balance_relative_error']),1e-6)
        self.assertLess(r.metadata['max_energy_increase_fraction'],1e-9)
        a,b=r.metadata['tail_stress_proxies']
        self.assertAlmostEqual(a['current_peak_per_branch_A']/b['current_peak_per_branch_A'],520/180,places=10)
        self.assertAlmostEqual(sum(r.metadata['branch_loss_J'].values()),r.metadata['integrated_loss_J'],places=6)

    def test_parallel_refinement_polarity_and_linear_charge(self):
        a=simulate(BASE,SETUP,solver='modal',n_points=1600)
        b=simulate(replace(BASE,stage_charge_V=BASE.stage_charge_V/2,polarity=-1),SETUP,solver='Radau',n_points=12000,rtol=1e-10,atol=1e-12)
        for k in ['T1_s','T2_s']: self.assertLess(abs(a.metadata['metrics'][k]/b.metadata['metrics'][k]-1),2e-7)
        self.assertAlmostEqual(a.metadata['voltage_gain'],b.metadata['voltage_gain'],places=8)

if __name__=='__main__': unittest.main(verbosity=2)
