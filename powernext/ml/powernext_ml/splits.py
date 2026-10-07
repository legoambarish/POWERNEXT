"""Input-only split construction with union of physical and nominal families."""
import numpy as np
import pandas as pd
from .common import digest


def connected_groups(frame, columns):
    parent=list(range(len(frame)))
    def find(i):
        while parent[i]!=i:
            parent[i]=parent[parent[i]];i=parent[i]
        return i
    for col in columns:
        seen={}
        for i,v in enumerate(frame[col].astype(str)):
            if v in seen:parent[find(i)]=find(seen[v])
            else:seen[v]=i
    sets={}
    for i in range(len(frame)):sets.setdefault(find(i),[]).append(str(frame.iloc[i].row_id))
    ids={k:digest(sorted(v)) for k,v in sets.items()}
    return np.array([ids[find(i)] for i in range(len(frame))])


def fraction(value,seed=20261002):
    return int(digest([seed,str(value)])[:13],16)/16**13


def make_splits(frame,domain):
    groups=frame.group_id.to_numpy()
    u=np.array([fraction(g) for g in groups])
    splits={"grouped_setup":np.where(u<.65,"train",np.where(u<.82,"validation","test"))}
    if domain=="legacy":
        splits["provided"]=frame.Split.map({"Train":"train","Validation":"validation","Hidden Test":"test"}).to_numpy()
        masks=dict(load_region=frame.Load_C_pF>=1100,inductance_region=frame.L_uH>=25,
                   stage_count=frame.Stages==frame.Stages.max(),resistor_recipe=frame.Front_R_Stage>=(60 if frame.Impulse_Type.iloc[0]=="Lightning" else 18000))
    else:
        masks=dict(load_region=frame.dut_nF>=5,inductance_region=frame.loop_uH>=50,
                   stage_count=frame.stages.isin([13,14,15]),resistor_recipe=frame.front_per_stage_ohm==5000)
    if domain=="simulation" and "tail_parallel" in frame and frame.tail_parallel.max()>0:
        masks["parallel_recipe_unseen"]=frame.tail_parallel==1
    for name,mask in masks.items():
        held=set(groups[np.asarray(mask)])
        test=np.array([g in held for g in groups])
        splits[name]=np.where(test,"test",np.where(u<.8,"train","validation"))
    for name,assignment in splits.items():
        if name!="provided":
            assert pd.DataFrame(dict(group=groups,split=assignment)).groupby("group").split.nunique().max()==1
        if any((assignment==part).sum()<7 for part in ["train","validation","test"]):
            raise ValueError(f"Insufficient coverage for {name}: {pd.Series(assignment).value_counts().to_dict()}")
    return splits
