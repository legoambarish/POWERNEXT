"""Read constraints from the shared profile; never invent component inventory."""
from dataclasses import asdict
import itertools
import math
from .common import digest, RequestError
from powernext_ml.physics_adapter import load_adapter
from physics_engine import Setup,Configuration
from physics_engine.recipes import SINGLE,PARALLEL,resolve_recipe
from physics_engine.evaluator import LIMITS, PROFILE_ID


class Catalog:
    def __init__(self, adapter_name="provisional"):
        self.adapter_name = adapter_name
        self.adapter = load_adapter(adapter_name)
        self.profile = self.adapter.profile
        self.profile_id = self.profile["profile_id"]
        self.limits = {k: v["value"] for k, v in self.profile["limits"].items()}
        self.capacitance_F = self.profile["capacitors"]["stage_impulse_capacitance"]["value"]
        self.crest_tolerance = self.profile["waveform_profile"]["crest_relative_tolerance"]["value"]
        if self.profile["waveform_profile"]["id"] != PROFILE_ID:
            raise RequestError("EVALUATOR_PROFILE_MISMATCH", "Install a compatible evaluator before using this profile")
        # Cross-check the shared evaluator against its source, not a new set of limits.
        for mode in LIMITS:
            p = self.profile["waveform_profile"][mode]
            field = "T1" if mode == "LI" else "Tp"
            for key, term in [("front_s", field), ("tail_s", "T2")]:
                value = p[term + "_target"]["value"]
                tol = p[term + "_relative_tolerance"]["value"]
                expected = (value * (1-tol), value * (1+tol))
                if any(not math.isclose(a, b, rel_tol=1e-14) for a, b in zip(expected, LIMITS[mode][key])):
                    raise RequestError("EVALUATOR_LIMIT_MISMATCH", mode)

    def entries(self, mode, topology, scope="development", recipe_ids=None):
        if hasattr(self.adapter, "optimizer_catalog"):
            entries = self.adapter.optimizer_catalog(mode, topology, scope)
            self._validate_entries(entries, mode, topology)
            return sorted(entries, key=lambda e: e["candidate_id"])
        if scope == "approved":
            if self.profile["topology"]["approved_recipes"]:
                raise RequestError("CATALOG_ADAPTER_REQUIRED", "Approved placements must be explicitly compiled")
            return []
        recipes = self.profile["topology"]["development_recipes"]
        selected=set(recipe_ids) if recipe_ids is not None else {r["id"] for r in recipes if r.get("default_enabled",False)}
        entries = []
        for recipe in recipes:
            if recipe["id"] not in selected or mode not in recipe["allowed_impulse_types"] or topology not in recipe["allowed_topologies"]:
                continue
            if recipe["id"] not in (SINGLE,PARALLEL):
                raise RequestError("CATALOG_ADAPTER_REQUIRED", "Do not guess a connection mapping")
            tails=[180] if recipe["id"]==PARALLEL else self.adapter.tails[mode]
            for n, front, tail in itertools.product(self.adapter.stages, self.adapter.fronts, tails):
                c = dict(impulse_type=mode, stages=n, front_per_stage_ohm=front,
                         tail_per_stage_ohm=tail, topology_id=topology, recipe_id=recipe["id"])
                physical=resolve_recipe(Configuration(**c,stage_charge_V=100000))
                eq=physical["tail_equivalent_per_stage_ohm"]
                entries.append(dict(candidate_id="cfg_" + digest(c)[:16], configuration=c,
                    series_sections=n, amplitude_law="LINEAR_EQUAL_STAGE_CHARGE",
                    recipe_status=recipe["status"], exact_module_allocation=None,
                    allocation_status="UNKNOWN_CPRI_PLACEMENTS", recipe_source=recipe,
                    component_bill_of_materials=physical["bill_of_materials"],
                    front_recipe=dict(recipe_id=recipe["id"], per_stage_ohm=front, assumed_total_ohm=n*front,component_values_ohm=[front],connection="SINGLE"),
                    tail_recipe=dict(recipe_id=recipe["id"], per_stage_ohm=eq, equivalent_per_stage_ohm=eq, assumed_total_ohm=n*eq,component_values_ohm=physical["tail_components_ohm"],connection=physical["tail_connection"])))
        self._validate_entries(entries, mode, topology)
        return sorted(entries, key=lambda e: e["candidate_id"])

    def _validate_entries(self, entries, mode, topology):
        if len({e["candidate_id"] for e in entries}) != len(entries):
            raise RequestError("DUPLICATE_CATALOG_ENTRY", "Candidate identity must be unique")
        for e in entries:
            if e["configuration"]["impulse_type"] != mode or e["configuration"]["topology_id"] != topology:
                raise RequestError("CATALOG_SCOPE_MISMATCH", e["candidate_id"])
            if e["amplitude_law"] != "LINEAR_EQUAL_STAGE_CHARGE":
                raise RequestError("AMPLITUDE_LAW_UNSUPPORTED", "A nonlinear adapter needs a separately validated charge solver")
            if type(e["series_sections"]) is not int or e["series_sections"] <= 0:
                raise RequestError("INVALID_SERIES_SECTIONS", e["candidate_id"])

    def entries_for_request(self,request):
        entries=self.entries(request['impulse_type'],request['topology_id'],request['catalog_scope'],request.get('recipe_ids'))
        return [e for e in entries if all(key not in request or set(e[field].get('component_values_ohm',[e['configuration'][fallback]]))<=set(request[key])
            for key,field,fallback in [('available_front_per_stage_ohm','front_recipe','front_per_stage_ohm'),('available_tail_per_stage_ohm','tail_recipe','tail_per_stage_ohm')])]


def normalize_request(raw, catalog):
    if not isinstance(raw, dict):
        raise RequestError("REQUEST_SCHEMA", "A JSON object is required")
    allowed = {"schema_version", "request_id", "impulse_type", "target_crest_V", "equipment_profile_id",
               "topology_id", "setup", "polarity", "catalog_scope", "alternatives", "assumptions", "current_setting",
               "available_front_per_stage_ohm","available_tail_per_stage_ohm","recipe_ids"}
    extra = set(raw) - allowed
    if extra:
        raise RequestError("UNKNOWN_REQUEST_FIELDS", str(sorted(extra)))
    needed = {"impulse_type", "target_crest_V", "equipment_profile_id", "topology_id", "setup"}
    if not needed <= raw.keys():
        raise RequestError("MISSING_REQUEST_FIELDS", str(sorted(needed-raw.keys())))
    if raw.get("schema_version", "test_request_v1") != "test_request_v1":
        raise RequestError("REQUEST_VERSION", "Unsupported schema")
    mode = raw["impulse_type"]
    if not isinstance(mode, str) or mode not in LIMITS:
        raise RequestError("INVALID_IMPULSE_TYPE", str(mode))
    target = raw["target_crest_V"]
    if type(target) not in (int, float) or not math.isfinite(target) or target <= 0:
        raise RequestError("INVALID_TARGET_CREST", "Positive finite volts required")
    if raw["equipment_profile_id"] != catalog.profile_id:
        raise RequestError("PROFILE_MISMATCH", "Request must identify the loaded equipment profile")
    if raw["topology_id"] not in catalog.adapter.topologies:
        raise RequestError("UNKNOWN_TOPOLOGY", "Topology is an input, never an optimization variable")
    if not catalog.limits["requested_output_crest_min_approx"] <= target <= catalog.limits["requested_output_crest_max_approx"]:
        raise RequestError("REQUEST_OUTSIDE_DECLARED_DOMAIN", "Target lies outside the versioned request domain")
    polarity = raw.get("polarity", 1)
    if type(polarity) is not int or polarity not in (-1, 1):
        raise RequestError("INVALID_POLARITY", "+1 or -1 required")
    scope = raw.get("catalog_scope", "development")
    if scope not in ("development", "approved"):
        raise RequestError("INVALID_CATALOG_SCOPE", str(scope))
    number = raw.get("alternatives", 4)
    if type(number) is not int or not 1 <= number <= 20:
        raise RequestError("INVALID_ALTERNATIVE_COUNT", "Use 1 through 20")
    assumptions = raw.get("assumptions", [])
    if not isinstance(assumptions, list) or any(not isinstance(x, str) for x in assumptions):
        raise RequestError("INVALID_ASSUMPTIONS", "Provide a list of explicit assumptions")
    try:
        setup = asdict(Setup(**raw["setup"]))
        for key in ["dut_capacitance_F", "divider_capacitance_F", "stray_capacitance_F", "loop_inductance_H", "loop_resistance_ohm"]:
            if type(setup[key]) not in (int, float):
                raise TypeError(f"{key} must be numeric")
        sample = catalog.entries(mode, raw["topology_id"], "development")[0]["configuration"]
        catalog.adapter.validate(dict(sample, stage_charge_V=catalog.limits["stage_charge_max"], polarity=polarity), setup)
    except (TypeError, ValueError, IndexError) as exc:
        raise RequestError(getattr(exc, "code", "INVALID_SETUP"), str(exc)) from exc
    current = raw.get("current_setting")
    if current is not None:
        keys = {"stages", "stage_charge_V", "front_per_stage_ohm", "tail_per_stage_ohm", "recipe_id"}
        if not isinstance(current, dict) or set(current) != keys:
            raise RequestError("CURRENT_SETTING_SCHEMA", "Provide all five actual setting fields")
        if type(current["stages"]) is not int or any(type(current[k]) not in (int, float) or not math.isfinite(current[k]) or current[k] <= 0 for k in keys-{"recipe_id"}):
            raise RequestError("CURRENT_SETTING_SCHEMA", "Finite positive setting values required")
        if not isinstance(current["recipe_id"], str):
            raise RequestError("CURRENT_SETTING_SCHEMA", "Recipe ID must be a string")
    valid_recipes={r['id'] for r in catalog.profile['topology']['development_recipes'] if mode in r.get('allowed_impulse_types',[mode]) and raw['topology_id'] in r.get('allowed_topologies',[raw['topology_id']])}
    recipe_ids=raw.get('recipe_ids',[r['id'] for r in catalog.profile['topology']['development_recipes'] if r.get('default_enabled',r['id']==getattr(catalog.adapter,'recipe',None)) and r['id'] in valid_recipes])
    if not isinstance(recipe_ids,list) or any(not isinstance(r,str) or r not in valid_recipes for r in recipe_ids) or len(set(recipe_ids))!=len(recipe_ids):
        raise RequestError('INVALID_RECIPE_SELECTION','Select explicitly documented recipes supported for this impulse and topology')
    availability={}
    for key,confirmed in [('available_front_per_stage_ohm',catalog.adapter.fronts),('available_tail_per_stage_ohm',catalog.adapter.tails[mode])]:
        if key not in raw:continue
        values=raw[key]
        if not isinstance(values,list) or any(type(v) not in (int,float) or not math.isfinite(v) or v not in confirmed for v in values) or len(set(values))!=len(values):
            raise RequestError('INVALID_RESISTOR_AVAILABILITY','Use unique confirmed per-stage values; an empty list explicitly means none available')
        availability[key]=sorted(values)
    return dict(schema_version="test_request_v1", request_id=raw.get("request_id", "UNNAMED_REQUEST"),
        impulse_type=mode, target_crest_V=float(target), equipment_profile_id=catalog.profile_id,
        topology_id=raw["topology_id"], setup=setup, polarity=polarity, catalog_scope=scope,
        alternatives=number, assumptions=assumptions, current_setting=current,recipe_ids=sorted(recipe_ids),**availability)
