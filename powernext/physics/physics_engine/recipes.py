"""Versioned physical-component arrangements; none is CPRI approved connectivity."""
from collections import Counter
from .network import PhysicsError

PROFILE_ID = "CPRI_IVG_OCT04_2026_v2"
COMPONENTS = (30, 46, 180, 520, 3700, 5000)
SINGLE = "DEV_UNIFORM_SINGLE_v2"
PARALLEL = "HYP_LI_TAIL_180_PAR_520_v1"
LEGACY = "DEV_UNIFORM_SERIES_v1"

def resolve_recipe(c):
    if c.front_per_stage_ohm not in COMPONENTS or c.tail_per_stage_ohm not in COMPONENTS:
        raise PhysicsError("COMPONENT_NOT_CONFIRMED", "Use an actual confirmed discrete component value, not an equivalent resistance.")
    tails=[c.tail_per_stage_ohm]
    if c.recipe_id == SINGLE:
        description="one front and one tail component per active stage"
    elif c.recipe_id == PARALLEL:
        if c.impulse_type != "LI" or c.topology_id != "GSHUNT_v0" or c.tail_per_stage_ohm != 180:
            raise PhysicsError("RECIPE_DOMAIN_MISMATCH", "Parallel LI hypothesis requires GSHUNT and canonical tail component 180; second branch is explicitly 520 ohm.")
        tails=[180,520]
        description="one front component and separate 180 ohm / 520 ohm parallel tail branches per active stage"
    elif c.recipe_id == LEGACY:
        if c.front_per_stage_ohm not in (30,46,3700,5000) or c.tail_per_stage_ohm != (180 if c.impulse_type=='LI' else 5000):
            raise PhysicsError("LEGACY_RECIPE_DOMAIN_MISMATCH", "Historical recipe retains its original domain; choose the current recipe for newly confirmed values.")
        description="historical v1 uniform single-tail interpretation; retained only for reproduction"
    else:
        raise PhysicsError("UNKNOWN_TOPOLOGY_OR_RECIPE", c.recipe_id)
    counts=Counter([c.front_per_stage_ohm,*tails])
    return dict(id=c.recipe_id,status="PROVISIONAL_MODEL_ASSUMPTION",description=description,
                front_components_ohm=[c.front_per_stage_ohm],tail_components_ohm=tails,
                tail_connection="PARALLEL" if len(tails)>1 else "SINGLE",
                tail_equivalent_per_stage_ohm=1/sum(1/r for r in tails),
                bill_of_materials=[dict(component_ohm=r,required_count=count*c.stages,
                    count_status="REQUIRED_BY_HYPOTHESIS_AVAILABLE_QUANTITY_UNKNOWN") for r,count in sorted(counts.items())],
                hardware_approved=False)
