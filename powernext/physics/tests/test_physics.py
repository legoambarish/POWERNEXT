import unittest
import numpy as np
from scipy.linalg import expm
from scipy.optimize import root
from scipy.integrate import solve_ivp
from physics_engine import Configuration,Setup,simulate
from physics_engine.network import Network,Element,PhysicsError
from physics_engine.engine import build_network
from physics_engine.evaluator import evaluate,PROFILE_ID
from physics_engine.analytic import voltage,rates,double_exponential_metrics
from physics_engine.reference_cases import uniform_stage_chain

BASE_SETUP=Setup(850e-12,500e-12,150e-12,18.5e-6,"ADDITIONAL_DISJOINT")
def config(mode="LI",top="GSHUNT_v0",charge=150e3):
    return Configuration(mode,10,charge,30 if mode=="LI" else 3700,180 if mode=="LI" else 5000,top)

def mathematical_fixture(mode):
    target=np.array([1.2e-6,50e-6]) if mode=="LI" else np.array([250e-6,2500e-6])
    def unpack(x):
        a=np.exp(x[0]); return a,a+np.exp(x[1])
    def fun(x):
        a,b=unpack(x); m=double_exponential_metrics(a,b,mode)
        return np.log(np.array([m['front_or_peak_s'],m['T2_s']])/target)
    initial=[np.log(1.4e4),np.log(2.5e6)] if mode=="LI" else [np.log(320),np.log(16000)]
    sol=root(fun,initial)
    if not sol.success: raise RuntimeError(sol.message)
    a,b=unpack(sol.x); m=double_exponential_metrics(a,b,mode)
    t=np.unique(np.r_[0,np.geomspace(1e-11,20/a,8000),m['t_peak_s'],m['t30_s'],m['t90_s'],m['t50_s']])
    u=np.exp(-a*t)*(-np.expm1(-(b-a)*t))/m['coefficient_to_crest']
    return t,u,m

class TestPhysics(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.li=simulate(config(),BASE_SETUP,target_crest_V=1.4e6)
        cls.si=simulate(config("SI"),BASE_SETUP,target_crest_V=1.3e6)

    def test_01_energy_rating(self):
        c=Configuration("LI",15,200e3,30,180,"GSHUNT_v0")
        cn,d=build_network(c,BASE_SETUP)
        self.assertAlmostEqual(cn.E0_J,150000,places=7)
        self.assertAlmostEqual(d['Cg_F'],.5e-6/15,places=15)

    def test_02_rc_oracle_GSHUNT(self): self.check_rc("GSHUNT_v0")
    def test_03_rc_oracle_OSHUNT(self): self.check_rc("OSHUNT_v0")
    def check_rc(self,top):
        c=config(top=top); s=Setup(850e-12,500e-12,150e-12,0,"ADDITIONAL_DISJOINT")
        cn,d=build_network(c,s); tr=cn.integrate(.001)
        t=np.r_[0,np.geomspace(1e-10,.001,500)]
        expected=voltage(t,d['Cg_F'],d['CL_F'],d['Rf_total_ohm'],d['Rt_total_ohm'],d['U0_V'],top)
        self.assertLess(np.max(np.abs(tr.voltage('o',t)-expected))/np.max(expected),2e-8)

    def test_04_exponential_independent(self):
        cn,d=build_network(config(),BASE_SETUP); tr=cn.integrate(.001)
        for t in [0,1e-8,5e-7,2e-6,5e-5,.001]:
            exact=expm(cn.A*t)@cn.y0
            self.assertLess(np.linalg.norm(tr.y(t)-exact),2e-8)

    def test_05_direct_three_state_ODE(self):
        c=config(); cn,d=build_network(c,BASE_SETUP)
        cg,cl,rf,rt,U0=(d[x] for x in ['Cg_F','CL_F','Rf_total_ohm','Rt_total_ohm','U0_V'])
        L=BASE_SETUP.loop_inductance_H
        # Independently written dimensional ODE; LSODA vs graph-assembled Radau.
        def f(t,x):
            vg,vo,i=x
            return [-vg/(rt*cg)-i/cg,i/cl,(vg-vo-rf*i)/L]
        sol=solve_ivp(f,(0,.001),[U0,0,0],method='LSODA',rtol=2e-10,atol=1e-7,dense_output=True)
        t=np.geomspace(1e-9,.001,400); tr=cn.integrate(.001)
        self.assertLess(np.max(np.abs(sol.sol(t)[1]-tr.voltage('o',t)))/U0,1e-7)

    def test_06_energy_balance(self): self.assertLess(abs(self.li.metadata['energy_balance_relative_error']),1e-6)
    def test_07_passive_monotonic_energy(self): self.assertLess(self.li.metadata['max_energy_increase_fraction'],1e-9)
    def test_08_branch_losses_add(self): self.assertAlmostEqual(sum(self.li.metadata['branch_loss_J'].values())/self.li.metadata['integrated_loss_J'],1,places=12)

    def test_09_voltage_scaling(self):
        half=simulate(config(charge=75e3),BASE_SETUP,target_crest_V=.7e6)
        a=self.li.metadata; b=half.metadata
        self.assertAlmostEqual(a['voltage_gain'],b['voltage_gain'],places=10)
        self.assertAlmostEqual(a['metrics']['T1_s']/b['metrics']['T1_s'],1,places=9)
        self.assertAlmostEqual(a['stored_energy_J']/b['stored_energy_J'],4,places=9)

    def test_10_polarity(self):
        t=self.li.arrays['time_s']; v=self.li.arrays['voltage_V']
        m=evaluate(t,-v,'LI',-1,target_crest_V=1.4e6)
        self.assertAlmostEqual(m['T1_s'],self.li.metadata['metrics']['T1_s'],places=14)
        self.assertLess(m['raw_signed_crest_V'],0)

    def test_11_zero_inductance_is_exact_RC(self):
        s=Setup(850e-12,500e-12,150e-12,0,"ADDITIONAL_DISJOINT")
        cn,_=build_network(config(),s)
        self.assertEqual(cn.A.shape,(2,2)); self.assertEqual(len(cn.net.rl_names),0)

    def test_12_small_inductance_convergence(self):
        curves=[]
        for L in [1e-6,1e-8,0]:
            s=Setup(850e-12,500e-12,150e-12,L,"ADDITIONAL_DISJOINT")
            cn,_=build_network(config(),s); tr=cn.integrate(.0004)
            curves.append(tr.voltage('o',np.geomspace(1e-8,.0004,500)))
        self.assertLess(np.max(abs(curves[1]-curves[2])),np.max(abs(curves[0]-curves[2]))/30)

    def test_13_stage_graph_exact_symmetry(self):
        n=4; cs=.5e-6; rf=30; rt=180; cl=1.98e-9; L=18.5e-6; us=150e3
        chain=uniform_stage_chain(n,cs,rf,rt,cl,L,us)
        c=Configuration('LI',n,us,rf,rt,'GSHUNT_v0'); lump,_=build_network(c,BASE_SETUP)
        t=np.geomspace(1e-9,.001,600)
        a=chain.integrate(.001).voltage('o',t); b=lump.integrate(.001).voltage('o',t)
        self.assertLess(np.max(abs(a-b))/(n*us),3e-8)
        self.assertAlmostEqual(chain.E0_J,lump.E0_J,places=6)

    def test_14_LI_mathematical_reference(self): self.check_fixture('LI')
    def test_15_SI_mathematical_reference(self): self.check_fixture('SI')
    def check_fixture(self,mode):
        t,u,ref=mathematical_fixture(mode)
        m=evaluate(t,u,mode,target_crest_V=1)
        self.assertEqual(m['compliance_status'],'PASS')
        f=m['T1_s'] if mode=='LI' else m['Tp_s']
        self.assertLess(abs(f/ref['front_or_peak_s']-1),1e-8)
        self.assertLess(abs(m['T2_s']/ref['T2_s']-1),1e-8)

    def test_16_LI_not_time_to_peak(self):
        m=self.li.metadata['metrics']; self.assertGreater(abs(m['T1_s']/m['t_peak_s']-1),.1)
    def test_17_virtual_origin_identity(self):
        m=self.li.metadata['metrics']; self.assertAlmostEqual(m['virtual_origin_s'],m['t30_s']-.5*(m['t90_s']-m['t30_s']),places=15)
    def test_18_SI_not_LI_origin(self):
        m=self.si.metadata['metrics']; self.assertIsNone(m['virtual_origin_s']); self.assertAlmostEqual(m['T2_s'],m['t50_falling_s'],places=15)
    def test_19_actual_SI_tail_tolerance(self):
        self.assertTrue(self.si.metadata['metrics']['checks']['tail']); self.assertEqual(self.si.metadata['metrics']['compliance_status'],'PASS')
    def test_20_stage_min(self):
        with self.assertRaisesRegex(PhysicsError,'STAGE_COUNT_LIMIT'):
            simulate(Configuration('LI',1,100e3,30,180,'GSHUNT_v0'),BASE_SETUP)
    def test_21_stage_max(self):
        with self.assertRaisesRegex(PhysicsError,'STAGE_COUNT_LIMIT'):
            simulate(Configuration('LI',16,100e3,30,180,'GSHUNT_v0'),BASE_SETUP)
    def test_22_charge_limit(self):
        with self.assertRaisesRegex(PhysicsError,'STAGE_VOLTAGE_LIMIT'):
            simulate(config(charge=201e3),BASE_SETUP)
    def test_23_unconfirmed_tail_rejected(self):
        with self.assertRaisesRegex(PhysicsError,'COMPONENT_NOT_CONFIRMED'):
            simulate(Configuration('LI',10,100e3,30,521,'GSHUNT_v0'),BASE_SETUP)
    def test_24_arbitrary_resistor_rejected(self):
        with self.assertRaisesRegex(PhysicsError,'COMPONENT_NOT_CONFIRMED'):
            simulate(Configuration('LI',10,100e3,50,180,'GSHUNT_v0'),BASE_SETUP)
    def test_25_negative_capacitance(self):
        with self.assertRaisesRegex(PhysicsError,'INVALID_SETUP_PARAMETER'):
            simulate(config(),Setup(-1,0,0,0,'ADDITIONAL_DISJOINT'))
    def test_26_C_coverage_required(self):
        with self.assertRaisesRegex(PhysicsError,'CAPACITANCE_COVERAGE_UNRESOLVED'):
            simulate(config(),Setup(1e-9,0,0,0,'UNKNOWN'))
    def test_27_truncated_tail(self):
        t,u,ref=mathematical_fixture('LI'); mask=t<10e-6
        m=evaluate(t[mask],u[mask],'LI',target_crest_V=1)
        self.assertEqual(m['compliance_status'],'INDETERMINATE')
    def test_28_duplicate_time_rejected(self):
        with self.assertRaisesRegex(PhysicsError,'TIME_NOT_STRICTLY_INCREASING'):
            evaluate([0,1,2,3,3,4,5,6],[0,.1,.4,.8,1,.8,.4,.1],'LI')
    def test_29_noisy_curve_gated(self):
        t=np.linspace(0,.0003,20001); u=np.exp(-14000*t)-np.exp(-2.5e6*t)
        u+=.03*np.sin(2*np.pi*1e6*t)*np.exp(-t/15e-6)
        m=evaluate(t,u,'LI',target_crest_V=1)
        self.assertEqual(m['compliance_status'],'INDETERMINATE')
    def test_30_simulation_is_not_hardware_verified(self):
        self.assertFalse(self.si.metadata['eligible_for_hardware_recommendation'])
        self.assertFalse(self.si.metadata['metrics']['standards_certified'])
    def test_31_time_shift_invariance(self):
        t,u,ref=mathematical_fixture('SI'); shift=.001
        m=evaluate(t+shift,u,'SI',beginning_s=shift,target_crest_V=1)
        self.assertLess(abs(m['Tp_s']/ref['front_or_peak_s']-1),1e-9)
    def test_32_measured_record_not_auto_certified(self):
        t,u,ref=mathematical_fixture('SI')
        m=evaluate(t,u,'SI',source_kind='measured',target_crest_V=1)
        self.assertEqual(m['compliance_status'],'INDETERMINATE')
    def test_33_refinement(self):
        r=simulate(config(),BASE_SETUP,target_crest_V=1.4e6,rtol=1e-10,atol=1e-12,n_points=14000)
        for name in ['T1_s','T2_s','crest_magnitude_V']:
            self.assertLess(abs(r.metadata['metrics'][name]/self.li.metadata['metrics'][name]-1),2e-7)
    def test_34_capacitive_energy_bound(self):
        peak=self.li.metadata['metrics']['crest_magnitude_V']
        self.assertLessEqual(.5*BASE_SETUP.total_capacitance_F*peak**2,self.li.metadata['stored_energy_J']*(1+1e-10))

if __name__=='__main__': unittest.main(verbosity=2)
