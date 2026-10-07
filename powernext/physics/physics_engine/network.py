"""Passive, source-free, linear RLC graph after ideal erection.

Capacitance is stamped between named nodes. Series RL branches have current
states. Capacitance-null algebraic nodes are eliminated only when the
resulting algebraic conductance block is nonsingular (index-one systems).
No fictitious capacitance/inductance is inserted to make a model solvable.
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from numpy.typing import NDArray
from scipy.linalg import eigh, solve
from scipy.integrate import solve_ivp

Array = NDArray[np.float64]

class PhysicsError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"{code}: {message}")

@dataclass(frozen=True)
class Element:
    name: str
    kind: str                     # C, R, or RL
    a: str
    b: str
    value: float                  # F, ohm, or H
    series_r_ohm: float = 0.0     # only for RL

class Network:
    def __init__(self, nodes: list[str], elements: list[Element]):
        if len(set(nodes)) != len(nodes) or "0" in nodes:
            raise PhysicsError("INVALID_NODES", "Nodes must be unique; ground '0' is implicit.")
        if len({e.name for e in elements}) != len(elements):
            raise PhysicsError("DUPLICATE_ELEMENT", "Element names must be unique.")
        self.nodes, self.elements = list(nodes), list(elements)
        self.index = {n: k for k,n in enumerate(nodes)}
        n=len(nodes)
        self.C=np.zeros((n,n)); self.G=np.zeros((n,n))
        bs=[]; ls=[]; rs=[]; self.rl_names=[]
        for e in elements:
            if e.a == e.b or not np.isfinite(e.value) or e.value <= 0:
                raise PhysicsError("INVALID_ELEMENT", f"Bad endpoints/value for {e.name}.")
            b=self.incidence(e.a,e.b)
            if e.kind == "C": self.C += e.value*np.outer(b,b)
            elif e.kind == "R": self.G += np.outer(b,b)/e.value
            elif e.kind == "RL":
                if not np.isfinite(e.series_r_ohm) or e.series_r_ohm < 0:
                    raise PhysicsError("INVALID_ELEMENT", f"Bad series resistance for {e.name}.")
                bs.append(b); ls.append(e.value); rs.append(e.series_r_ohm); self.rl_names.append(e.name)
            else: raise PhysicsError("UNSUPPORTED_ELEMENT", e.kind)
        self.B=np.column_stack(bs) if bs else np.zeros((n,0))
        self.L=np.diag(ls); self.RL=np.diag(rs)

    def incidence(self,a:str,b:str)->Array:
        z=np.zeros(len(self.nodes))
        for node,sign in [(a,1),(b,-1)]:
            if node != "0":
                if node not in self.index: raise PhysicsError("UNKNOWN_NODE", node)
                z[self.index[node]] += sign
        return z

    def compile(self, initial_v_V: dict[str,float], initial_i_A: dict[str,float]|None=None)->"CompiledNetwork":
        return CompiledNetwork(self,initial_v_V,initial_i_A or {})

class CompiledNetwork:
    def __init__(self, net: Network, initial_v:dict[str,float], initial_i:dict[str,float]):
        self.net=net
        if set(initial_v) != set(net.nodes):
            raise PhysicsError("INITIAL_STATE_MISSING", "Specify a voltage for every nonground node.")
        if set(initial_i)-set(net.rl_names): raise PhysicsError("UNKNOWN_CURRENT_STATE", str(initial_i))
        v0=np.array([initial_v[n] for n in net.nodes],float)
        i0=np.array([initial_i.get(n,0.0) for n in net.rl_names],float)
        if not np.all(np.isfinite(v0)) or not np.all(np.isfinite(i0)):
            raise PhysicsError("NONFINITE_INITIAL_STATE", "Initial values must be finite.")
        # Determine exact graph rank: each capacitive component not connected to
        # ground has one common-mode null coordinate, including isolated nodes.
        vertices=["0"]+net.nodes
        parent={n:n for n in vertices}
        def find(x):
            while parent[x]!=x:
                parent[x]=parent[parent[x]]; x=parent[x]
            return x
        def union(a,b): parent[find(a)]=find(b)
        for e in net.elements:
            if e.kind=="C": union(e.a,e.b)
        floating={find(n) for n in net.nodes if find(n)!=find("0")}
        rank=len(net.nodes)-len(floating)
        if rank==0 and len(i0)==0: raise PhysicsError("NO_DYNAMIC_STORAGE", "Circuit has no dynamic state.")
        c_scale=max(float(np.max(np.abs(net.C))),1e-30)
        eig,Q=eigh(net.C/c_scale)
        nd=rank
        Qd=Q[:,len(Q)-nd:] if nd else np.zeros((len(Q),0))
        Qa=Q[:,:len(Q)-nd]
        cd=eig[len(eig)-nd:]*c_scale if nd else np.empty(0)
        if nd and (np.min(cd)<=0 or np.min(cd)/np.max(cd)<1e-13):
            raise PhysicsError("CAPACITANCE_ILL_CONDITIONED", "Rescale/refine the circuit; no small capacitor is silently removed.")
        Gdd=Qd.T@net.G@Qd; Gda=Qd.T@net.G@Qa
        Gaa=Qa.T@net.G@Qa; Gad=Gda.T
        Bd=Qd.T@net.B; Ba=Qa.T@net.B
        if Qa.shape[1]:
            ge=np.linalg.eigvalsh(Gaa)
            if ge[-1]<=0 or ge[0] <= max(1e-30,1e-12*ge[-1]):
                raise PhysicsError("DAE_INDEX_UNSUPPORTED", "Algebraic block is singular/ill-conditioned; use a general DAE solver or correct topology.")
            H=-solve(Gaa,np.hstack([Gad,Ba]),assume_a="pos")
        else: H=np.zeros((0,nd+len(i0)))
        # v = P z, z = [capacitive coordinates, inductor currents].
        P=np.hstack([Qd,np.zeros((len(net.nodes),len(i0)))])+Qa@H
        J=np.hstack([np.zeros((len(i0),nd)),np.eye(len(i0))])
        Ftop=-Qd.T@net.G@P-Bd@J
        Fbot=net.B.T@P-net.RL@J
        F=np.vstack([Ftop,Fbot])
        e=np.concatenate([cd,np.diag(net.L)])
        if np.any(e<=0): raise PhysicsError("INVALID_STORAGE_MATRIX", "Dynamic storage must be positive.")
        self.sqrt_e=np.sqrt(e); self.P=P; self.J=J; self.F=F; self.e=e
        self.z0=np.concatenate([Qd.T@v0,i0])
        v_cons=P@self.z0
        # Null-space nodal potentials may jump at ideal switching; capacitor
        # voltages/charge and inductor current are preserved by this projection.
        self.initial_algebraic_adjustment_V=float(np.max(np.abs(v_cons-v0)))
        self.E0_J=float(0.5*np.dot(e,self.z0*self.z0))
        if self.E0_J<=0: raise PhysicsError("ZERO_INITIAL_ENERGY", "An impulse requires stored energy.")
        self.scale=np.sqrt(2*self.E0_J)
        self.A=(F/self.sqrt_e[:,None])/self.sqrt_e[None,:]
        self.y0=self.sqrt_e*self.z0/self.scale
        sym=(self.A+self.A.T)/2
        if np.max(np.linalg.eigvalsh(sym)) > 1e-8*max(1.0,np.linalg.norm(self.A,2)):
            raise PhysicsError("NONPASSIVE_ASSEMBLY", "Energy-scaled system is not dissipative.")

    def states(self,y:Array)->tuple[Array,Array]:
        y=np.asarray(y)
        z=(self.scale/self.sqrt_e)[:,None]*y if y.ndim==2 else self.scale*y/self.sqrt_e
        return self.P@z,self.J@z

    def integrate(self,t_end_s:float, *,rtol:float=1e-9,atol:float=1e-11,max_step_s:float|None=None):
        if not np.isfinite(t_end_s) or t_end_s<=0: raise PhysicsError("INVALID_TIME_WINDOW", "t_end must be positive.")
        tunit=t_end_s/10
        sol=solve_ivp(lambda s,y:tunit*(self.A@y),(0,t_end_s/tunit),self.y0,
                      method="Radau",jac=tunit*self.A,rtol=rtol,atol=atol,dense_output=True,
                      max_step=(max_step_s or t_end_s/200)/tunit)
        if not sol.success: raise PhysicsError("SOLVER_FAILED",sol.message)
        return Trajectory(self,sol,tunit,t_end_s)

    def integrate_linear(self,t_end_s:float,*,rtol:float=1e-9,atol:float=1e-11):
        """Exact modal solution of the fixed linear graph, with Radau fallback.

        This is numerical acceleration, not a learned approximation. An ill-
        conditioned modal basis is rejected rather than silently regularized.
        """
        if not np.isfinite(t_end_s) or t_end_s<=0:
            raise PhysicsError("INVALID_TIME_WINDOW", "t_end must be positive.")
        try:
            return ModalTrajectory(self,t_end_s)
        except (np.linalg.LinAlgError,ArithmeticError):
            result=self.integrate(t_end_s,rtol=rtol,atol=atol)
            result.method="Radau_modal_fallback"
            return result

class Trajectory:
    def __init__(self,compiled:CompiledNetwork,sol,tunit:float,t_end:float):
        self.compiled,self.sol,self.tunit,self.t_end=compiled,sol,tunit,t_end
    def y(self,t): return self.sol.sol(np.asarray(t)/self.tunit)
    def states(self,t): return self.compiled.states(self.y(t))
    def voltage(self,node:str,t):
        if node=="0": return np.zeros_like(np.asarray(t),dtype=float)
        return self.states(t)[0][self.compiled.net.index[node]]
    def voltage_derivative(self,node:str,t):
        c=self.compiled
        dy=c.A@self.y(t)
        return c.states(dy)[0][c.net.index[node]]
    def energy(self,t): return self.compiled.E0_J*np.sum(self.y(t)**2,axis=0)
    def dissipated_power(self,t):
        v,i=self.states(t); net=self.compiled.net
        if v.ndim==1: return float(v@net.G@v+i@net.RL@i)
        return np.einsum('it,ij,jt->t',v,net.G,v)+np.einsum('it,ij,jt->t',i,net.RL,i)

class ModalTrajectory(Trajectory):
    def __init__(self,compiled,t_end):
        self.compiled,self.t_end=compiled,t_end
        self.method="linear_modal_v1"
        self.values,self.vectors=np.linalg.eig(compiled.A)
        if np.linalg.cond(self.vectors)>1e6:
            raise ArithmeticError("Ill-conditioned modal basis")
        residual=np.linalg.norm(compiled.A@self.vectors-self.vectors*self.values)
        if residual>1e-10*max(1.,np.linalg.norm(compiled.A)):
            raise ArithmeticError("Modal residual")
        self.weights=np.linalg.solve(self.vectors,compiled.y0)
        if np.linalg.norm(self.vectors@self.weights-compiled.y0)>1e-10:
            raise ArithmeticError("Modal initial state")
        # Checking at multiple times catches a non-real reconstruction before
        # returning a trajectory. Complex conjugate eigenpairs are legitimate.
        self.y(np.array([0.,t_end*1e-8,t_end*.1,t_end]))

    def y(self,t):
        t=np.asarray(t)
        z=self.vectors@(self.weights[:,None]*np.exp(self.values[:,None]*t[None,:])) if t.ndim else self.vectors@(self.weights*np.exp(self.values*t))
        if np.max(np.abs(np.imag(z)))>1e-9*max(1.,float(np.max(np.abs(z)))):
            raise ArithmeticError("Non-real modal reconstruction")
        return np.real(z)
