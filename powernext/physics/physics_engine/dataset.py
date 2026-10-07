"""Small deterministic data-interface demonstration; no ML training."""
from __future__ import annotations
import argparse,hashlib,json
from pathlib import Path
from dataclasses import asdict
from .engine import Configuration,Setup,simulate
from .network import PhysicsError


def digest(obj):
    return hashlib.sha256(json.dumps(obj,sort_keys=True,allow_nan=False).encode()).hexdigest()

def generate(output:Path):
    output.mkdir(parents=True,exist_ok=True)
    rows=[]; count=0
    for mode,rf,rt,target in [('LI',30,180,1.4e6),('SI',3700,5000,1.3e6)]:
        for top in ['GSHUNT_v0','OSHUNT_v0']:
            for dut in [500e-12,850e-12]:
                setup=Setup(dut,500e-12,150e-12,18.5e-6,'ADDITIONAL_DISJOINT',setup_id=f'DEV_DUT_{dut:.12g}')
                # Both charge variants must remain in the same split family.
                for charge in [100e3,150e3]:
                    count+=1
                    c=Configuration(mode,10,charge,rf,rt,top)
                    name=f'case_{count:04d}'
                    result=simulate(c,setup,target_crest_V=target)
                    result.save(output/name)
                    d=result.metadata['derived']
                    physical={k:v for k,v in d.items() if k!='U0_V'}
                    physical.update(topology_id=top,L_H=setup.loop_inductance_H,profile_id=result.metadata['profile_id'])
                    rows.append(dict(row_id=name,status='SIMULATED',configuration=asdict(c),setup=asdict(setup),
                                     physical_shape_id=digest(physical),setup_family_id=setup.setup_id,
                                     evidence_domain=result.metadata['evidence_domain'],metadata_path=name+'.json',waveform_path=name+'.npz',
                                     numeric_status=result.metadata['numeric_status'],waveform_status=result.metadata['metrics']['waveform_status'],
                                     compliance_status=result.metadata['metrics']['compliance_status'],hardware_status=result.metadata['hardware_status']))
    invalid=[Configuration('LI',1,100e3,30,180,'GSHUNT_v0'),
             Configuration('LI',16,100e3,30,180,'GSHUNT_v0'),
             Configuration('LI',10,201e3,30,180,'GSHUNT_v0'),
             Configuration('LI',10,100e3,50,180,'GSHUNT_v0'),
             Configuration('LI',10,100e3,30,520,'GSHUNT_v0')]
    for idx,c in enumerate(invalid):
        try:
            simulate(c,setup)
            raise RuntimeError('Invalid-input fixture unexpectedly simulated.')
        except PhysicsError as exc:
            rows.append(dict(row_id=f'invalid_{idx:03d}',status='INVALID_INPUT',configuration=asdict(c),setup=asdict(setup),
                             reason_code=exc.code,message=str(exc),metadata_path=None,waveform_path=None,
                             evidence_domain='DEVELOPMENT_INVALID_INPUT_FIXTURE'))
    with (output/'rows.jsonl').open('w',encoding='utf-8') as f:
        for row in rows:f.write(json.dumps(row,allow_nan=False)+'\n')
    manifest=dict(schema_version='1.0.0',purpose='SMOKE_INTERFACE_NOT_FINAL_TRAINING_DATA',row_count=len(rows),
                  simulated_count=count,invalid_count=len(invalid),split_assigned=False,
                  group_rule='Reconcile physical_shape_id with setup_family_id before train/validation/test assignment; never split charge variants.',
                  hardware_verified=False,source='CPRI actual component values + declared development topology/setup assumptions')
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2))
    return manifest

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,default=Path('generated_data'))
    args=p.parse_args()
    print(json.dumps(generate(args.output),indent=2))
if __name__=='__main__':main()
