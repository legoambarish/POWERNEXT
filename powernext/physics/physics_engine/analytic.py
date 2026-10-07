"""Independent two-capacitor RC oracle: scalar characteristic polynomial, no graph stamps."""
import numpy as np
from scipy.optimize import brentq

def rates(Cg,CL,Rf,Rt,tail_location="GSHUNT_v0"):
    if min(Cg,CL,Rf,Rt)<=0: raise ValueError("All RC parameters must be positive.")
    if tail_location=="GSHUNT_v0":
        a=1/(Rt*Cg)+1/(Rf*Cg)+1/(Rf*CL)
    elif tail_location=="OSHUNT_v0":
        a=1/(Rf*Cg)+1/(Rf*CL)+1/(Rt*CL)
    else: raise ValueError(tail_location)
    b=1/(Rf*Rt*Cg*CL)
    disc=a*a-4*b
    if disc<=0: raise ValueError("Distinct positive decay rates required by this reference formula.")
    beta=(a+np.sqrt(disc))/2
    alpha=b/beta       # stable: avoids subtracting nearly equal numbers
    return float(alpha),float(beta)

def voltage(t,Cg,CL,Rf,Rt,U0,tail_location="GSHUNT_v0"):
    alpha,beta=rates(Cg,CL,Rf,Rt,tail_location)
    t=np.asarray(t)
    return U0*np.exp(-alpha*t)*(-np.expm1(-(beta-alpha)*t))/(Rf*CL*(beta-alpha))

def double_exponential_metrics(alpha,beta,mode="LI"):
    if not 0<alpha<beta: raise ValueError("Need 0 < alpha < beta.")
    def f(t): return float(np.exp(-alpha*t)*(-np.expm1(-(beta-alpha)*t)))
    tp=float(np.log(beta/alpha)/(beta-alpha)); peak=f(tp)
    r30=brentq(lambda t:f(t)-.3*peak,0,tp,xtol=1e-17,rtol=1e-13)
    r90=brentq(lambda t:f(t)-.9*peak,0,tp,xtol=1e-17,rtol=1e-13)
    t50=brentq(lambda t:f(t)-.5*peak,tp,max(tp*2,20/alpha),xtol=1e-17,rtol=1e-13)
    T1=(r90-r30)/.6; origin=r30-.3*T1
    return dict(alpha_per_s=alpha,beta_per_s=beta,coefficient_to_crest=peak,t_peak_s=tp,
                t30_s=r30,t90_s=r90,t50_s=t50,T1_s=T1,virtual_origin_s=origin,
                front_or_peak_s=T1 if mode=="LI" else tp,T2_s=t50-origin if mode=="LI" else t50)
