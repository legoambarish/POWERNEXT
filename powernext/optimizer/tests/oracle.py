"""Independent enumeration and continuous-charge oracle.

Deliberately does not import optimizer catalog, charge, scoring, or ranking code.
The authoritative forward simulator is shared; this verifies inverse logic,
not an independently confirmed hardware circuit.
"""
import hashlib
import json
import math
from pathlib import Path
import sys

from powernext_config import PHYSICS
sys.path.insert(0,str(PHYSICS))
from physics_engine import Configuration,Setup,simulate


def oracle(raw):
    profile=json.loads((PHYSICS/"CPRI_EQUIPMENT_PROFILE.json").read_text())
    limits={k:v["value"] for k,v in profile["limits"].items()}
    mode=raw["impulse_type"];top=raw["topology_id"]
    waveform=profile["waveform_profile"][mode]
    front_name="T1" if mode=="LI" else "Tp"
    nominal=[raw["target_crest_V"],waveform[front_name+"_target"]["value"],waveform["T2_target"]["value"]]
    widths=[nominal[0]*profile["waveform_profile"]["crest_relative_tolerance"]["value"],nominal[1]*waveform[front_name+"_relative_tolerance"]["value"],nominal[2]*waveform["T2_relative_tolerance"]["value"]]
    rows=[]
    if raw.get('catalog_scope')=='approved':return rows
    tails=profile["resistors"]["LI_tail_per_stage_confirmed" if mode=="LI" else "SI_tail_per_stage"]
    selected=raw.get('recipe_ids',['DEV_UNIFORM_SINGLE_v2'])
    recipes=[]
    if 'DEV_UNIFORM_SINGLE_v2' in selected:
        recipes.extend((x['value'],'DEV_UNIFORM_SINGLE_v2',[x['value']]) for x in tails)
    if 'HYP_LI_TAIL_180_PAR_520_v1' in selected:
        assert mode=='LI' and top=='GSHUNT_v0'
        recipes.append((180,'HYP_LI_TAIL_180_PAR_520_v1',[180,520]))
    for n in range(limits["active_stages_min"],limits["available_stages_max"]+1):
        for rf in profile["resistors"]["front_per_stage"]:
            for tail,recipe,components in recipes:
                if 'available_front_per_stage_ohm' in raw and rf['value'] not in raw['available_front_per_stage_ohm']:continue
                if 'available_tail_per_stage_ohm' in raw and not set(components)<=set(raw['available_tail_per_stage_ohm']):continue
                c=dict(impulse_type=mode,stages=n,front_per_stage_ohm=rf["value"],tail_per_stage_ohm=tail,topology_id=top,recipe_id=recipe)
                ident="cfg_"+hashlib.sha256(json.dumps(c,sort_keys=True,separators=(",",":"),allow_nan=False).encode()).hexdigest()[:16]
                cs=profile["capacitors"]["stage_impulse_capacitance"]["value"]
                upper=min(limits["stage_charge_max"],limits["summed_stage_charge_max"]/n,math.sqrt(2*limits["stored_energy_per_stage_rated"]/cs),math.sqrt(2*limits["stored_energy_total_rated"]/(n*cs)))
                c["polarity"]=raw.get("polarity",1)
                first=simulate(Configuration(**c,stage_charge_V=upper),Setup(**raw["setup"]),solver='modal',n_points=2000)
                amplitude=first.metadata["metrics"]["raw_crest_magnitude_V"]/upper
                exact=raw["target_crest_V"]/amplitude
                # Continuous convex error minimum is either exact or a bound.
                possibilities={upper,min(upper,max(limits["stage_charge_min_reliable"] or 0,exact))}
                if limits["stage_charge_min_reliable"]:possibilities.add(limits["stage_charge_min_reliable"])
                choices=[]
                for charge in sorted(possibilities):
                    r=simulate(Configuration(**c,stage_charge_V=charge),Setup(**raw["setup"]),target_crest_V=raw["target_crest_V"],solver='modal',n_points=2000)
                    m=r.metadata["metrics"]
                    valid=r.metadata["numeric_status"]=="VALID" and m["waveform_status"]=="VALID_CLEAN_FULL_IMPULSE"
                    score=margin=None
                    if valid:
                        numbers=[m["crest_magnitude_V"],m[front_name+"_s"],m["T2_s"]]
                        errors=[(a-b)/w for a,b,w in zip(numbers,nominal,widths)]
                        score=sum(x*x for x in errors)
                        margin=min(1-abs(x) for x in errors)
                    tier=(0 if m["compliance_status"]=="PASS" else 1) if valid else 2
                    current=raw.get("current_setting")
                    changed=sum(current[k]!=c[k] for k in ["stages","front_per_stage_ohm","tail_per_stage_ohm","recipe_id"]) if current else 0
                    key=(tier,round(score,12) if score is not None else float("inf"),-round(margin,12) if margin is not None else float("inf"),changed,n*.5*cs*charge**2,n,rf["value"],tail,ident)
                    choices.append(dict(candidate_id=ident,key=key,score=score,stage_charge_V=charge,compliance_status=m["compliance_status"],metrics=m))
                rows.append(min(choices,key=lambda x:x["key"]))
    return sorted(rows,key=lambda x:x["key"])
