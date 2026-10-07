"""Evaluator-consistent mathematical target; not an equipment prediction."""
from functools import lru_cache
import numpy as np
from scipy.optimize import root
from .analytic import double_exponential_metrics
from .evaluator import evaluate

@lru_cache(maxsize=2)
def _unit_target(mode):
    if mode not in ('LI','SI'): raise ValueError('Unknown impulse type')
    target=np.array([1.2e-6,50e-6] if mode=='LI' else [250e-6,2500e-6])
    def unpack(x):
        a=np.exp(x[0]); return a,a+np.exp(x[1])
    def fun(x):
        a,b=unpack(x); m=double_exponential_metrics(a,b,mode)
        return np.log(np.array([m['front_or_peak_s'],m['T2_s']])/target)
    guess=np.log([1.4e4,2.5e6] if mode=='LI' else [320,16000])
    sol=root(fun,guess)
    if not sol.success or np.max(np.abs(fun(sol.x)))>1e-9:
        raise ArithmeticError('Nominal target solve failed')
    a,b=unpack(sol.x); m=double_exponential_metrics(a,b,mode)
    t=np.unique(np.r_[0,np.geomspace(1e-11,20/a,4000),m['t_peak_s'],m['t30_s'],m['t90_s'],m['t50_s']])
    u=np.exp(-a*t)*(-np.expm1(-(b-a)*t))/m['coefficient_to_crest']
    met=evaluate(t,u,mode,target_crest_V=1)
    actual=np.array([met['T1_s'] if mode=='LI' else met['Tp_s'],met['T2_s']])
    if met['compliance_status']!='PASS' or np.max(abs(actual/target-1))>1e-7:
        raise ArithmeticError('Shared evaluator rejected target')
    t.flags.writeable=False; u.flags.writeable=False
    return t,u

def nominal_target(mode,crest_V,polarity=1):
    if not np.isfinite(crest_V) or crest_V<=0 or polarity not in (-1,1):
        raise ValueError('Positive crest and explicit polarity required')
    t,u=_unit_target(mode); v=polarity*crest_V*u
    return dict(time_s=t.tolist(),voltage_V=v.tolist(),
                metrics=evaluate(t,v,mode,polarity,target_crest_V=crest_V),
                label='Mathematical nominal target',evidence_domain='MATHEMATICAL_REFERENCE',
                hardware_prediction=False,alignment='Same ideal discharge beginning; LI T1 uses virtual origin')
