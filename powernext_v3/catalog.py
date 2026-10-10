"""Compact deterministic indexing of the complete four-module network catalog.

Only ~4,000 resistance groups are materialized. The >200 million possible
front/tail/stage combinations are integer indices, streamed in bounded batches.
Electrical equivalence never discards physical recipes or their inventory needs.
"""
from __future__ import annotations
import hashlib
import itertools
import json
import math
import numpy as np
from .networks import enumerate_networks, electrical_groups, combined_bom
from .profiles import get_profile

GRAMMAR_ID = "UNIFORM_SERIES_PARALLEL_1_TO_4_MODULES_v3"


class Catalog:
    def __init__(self, max_modules=2, stages=None, min_modules=1):
        if type(min_modules) is not int or type(max_modules) is not int or not 1 <= min_modules <= max_modules <= 4:
            raise ValueError("Module bounds must satisfy 1 <= minimum <= maximum <= 4")
        self.min_modules = min_modules
        self.max_modules = max_modules
        self.recipes = tuple(r for r in enumerate_networks(max_modules) if r.module_count >= min_modules)
        self.groups = {value: tuple(r for r in recipes if r.module_count >= min_modules)
                       for value, recipes in electrical_groups(max_modules).items()
                       if any(r.module_count >= min_modules for r in recipes)}
        self.exact_values = tuple(self.groups)
        self.values = np.array([float(x) for x in self.exact_values])
        self.width = len(self.values)
        self.stages = tuple(range(2,16)) if stages is None else tuple(stages)
        if not self.stages or len(set(self.stages)) != len(self.stages) or any(type(n) is not int or n<2 or n>15 for n in self.stages):
            raise ValueError("Declared stages must be distinct integers from 2 through 15")
        self.stages = tuple(sorted(self.stages))
        self.count = len(self.stages)*self.width**2
        self.recipe_count = len(self.stages)*len(self.recipes)**2
        self.identity = hashlib.sha256(json.dumps(dict(grammar=GRAMMAR_ID, min_modules=min_modules, max_modules=max_modules,
            stages=self.stages, values=[str(x) for x in self.exact_values], recipes=[r.id for r in self.recipes]),sort_keys=True).encode()).hexdigest()

    def info(self):
        return dict(grammar_id=GRAMMAR_ID, min_modules_per_branch=self.min_modules, max_modules_per_branch=self.max_modules,
                    network_scope="EXACTLY_TWO_SERIES_OR_PARALLEL" if self.min_modules == self.max_modules == 2 else "HISTORICAL_BOUNDED_CATALOG",
                    uniform_stages=True, recipes_per_branch=len(self.recipes), distinct_resistances_per_branch=self.width,
                    theoretical_recipe_configurations=self.recipe_count, distinct_response_candidates=self.count,
                    stages=list(self.stages), catalog_sha256=self.identity,
                    hardware_inventory_status="UNKNOWN_UNLESS_EXPLICITLY_SUPPLIED")

    def decode(self, ids):
        ids = np.asarray(ids,dtype=np.int64)
        if np.any(ids<0) or np.any(ids>=self.count):raise ValueError("Candidate index outside declared catalog")
        stage_index = ids//(self.width*self.width)
        f = (ids//self.width)%self.width
        t = ids%self.width
        return np.asarray(self.stages)[stage_index],self.values[f],self.values[t]

    def encode(self, stage_index, front_index, tail_index):
        return int((stage_index*self.width+front_index)*self.width+tail_index)

    def physical(self, index, inventory=None):
        if type(index) is not int or not 0<=index<self.count:raise ValueError("Invalid candidate index")
        k,rem=divmod(index,self.width*self.width)
        f,t=divmod(rem,self.width)
        fronts,tails=self.groups[self.exact_values[f]],self.groups[self.exact_values[t]]
        n=self.stages[k]
        # JSON object keys arrive as strings; normalize explicitly, never infer stock.
        stock=None if inventory is None else {int(key):value for key,value in inventory.items()}
        choices=[]
        for front,tail in itertools.product(fronts,tails):
            bom=combined_bom(front,tail,n,stock)
            legal=not any(row["availability_status"]=="INSUFFICIENT" for row in bom["bill_of_materials"])
            choices.append((not legal,front.module_count+tail.module_count,front.id,tail.id,front,tail,bom))
        choice=min(choices,key=lambda item:item[:4])
        _,_,_,_,front,tail,bom=choice
        return dict(index=index,candidate_id=f"net_{self.identity[:12]}_{index}",stages=n,
            front=front,tail=tail,bill_of_materials=bom["bill_of_materials"],known_inventory_valid=not choice[0],
            physical_alternative_count=len(fronts)*len(tails),
            front_physical_alternatives=[r.as_dict() for r in fronts],tail_physical_alternatives=[r.as_dict() for r in tails])

    def progressive_ids(self, setup, domain_id, mode):
        """Deterministic prioritized coverage, eventually visits every group.

        The guide changes ordering only. A bounded consumer must report partial
        catalog coverage. No candidate is analytically declared infeasible here.
        """
        p=get_profile(domain_id)
        cl=sum(setup[x] for x in ("dut_capacitance_F","divider_capacitance_F","stray_capacitance_F"))
        cl+=p.basic_load_capacitance_F if setup["basic_coverage_assumption"]=="ADDITIONAL_DISJOINT" else 0
        nominal_front,nominal_tail=(1.2e-6,50e-6) if mode=="LI" else (250e-6,2500e-6)
        seen=set()
        def unique(value):
            if value in seen:return False
            seen.add(value);return True
        # Preserve all single-part choices in the large search's candidate pool.
        singles=[i for i,x in enumerate(self.exact_values) if any(r.module_count==1 for r in self.groups[x])]
        for k in range(len(self.stages)):
            for f,t in itertools.product(singles,repeat=2):
                idx=self.encode(k,f,t)
                if unique(idx):yield idx
        # Log-distance neighborhoods around two independent rough inverse guides;
        # not a waveform-conformity proof, and never an exclusion filter.
        neighborhoods=[]
        for k,n in enumerate(self.stages):
            cg=p.stage_capacitance_F/n
            ideal_f=max(1e-6,nominal_front/(1.67*cl*n)-setup.get("loop_resistance_ohm",0)/n)
            ideal_t=nominal_tail/(.693*(cg+cl)*n)
            fs=np.argsort(abs(np.log(self.values/ideal_f)),kind="stable")
            ts=np.argsort(abs(np.log(self.values/ideal_t)),kind="stable")
            neighborhoods.append((k,fs,ts))
        # Progressive square shells interleave all stage counts and broad regions.
        for radius in (4,8,16,32):
            for k,fs,ts in neighborhoods:
                for f,t in itertools.product(fs[:radius],ts[:radius]):
                    idx=self.encode(k,int(f),int(t))
                    if unique(idx):yield idx
        coarse=np.unique(np.rint(np.linspace(0,self.width-1,min(24,self.width))).astype(int))
        for k in range(len(self.stages)):
            for f,t in itertools.product(coarse,repeat=2):
                idx=self.encode(k,int(f),int(t))
                if unique(idx):yield idx
        # A full-cycle affine permutation covers the rest without a giant array.
        step=max(1,int(self.count*.6180339887498949))
        while math.gcd(step,self.count)!=1:step+=1
        offset=int(self.identity[:16],16)%self.count
        # The early visited set is bounded by the guide; no new entries are added
        # during the permutation because the permutation itself has no repeats.
        for j in range(self.count):
            idx=(offset+j*step)%self.count
            if idx not in seen:yield idx

    def batches(self, ids, size=4096):
        iterator=iter(ids)
        while True:
            batch=list(itertools.islice(iterator,size))
            if not batch:return
            yield np.asarray(batch,dtype=np.int64)
