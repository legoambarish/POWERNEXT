"""Exact amplitude optimization under a declared linear charge law."""
from dataclasses import dataclass
from decimal import Decimal, ROUND_FLOOR, ROUND_CEILING
import math


@dataclass(frozen=True)
class ChargePolicy:
    minimum_V: float | None
    maximum_V: float
    step_V: float | None = None
    origin_V: float = 0.0


def charge_policy(catalog, entry):
    p = catalog.limits
    n = entry["configuration"]["stages"]
    cs = catalog.capacitance_F
    upper = min(p["stage_charge_max"], p["summed_stage_charge_max"]/entry["series_sections"],
                math.sqrt(2*p["stored_energy_per_stage_rated"]/cs), math.sqrt(2*p["stored_energy_total_rated"]/(n*cs)))
    step = p.get("stage_charge_step")
    # The current profile has no known increment. A future profile must identify
    # the grid origin instead of silently assuming its offset.
    if step is not None and "stage_charge_step_origin" not in p:
        raise ValueError("A known charge increment requires its grid origin")
    return ChargePolicy(p.get("stage_charge_min_reliable"), upper, step, p.get("stage_charge_step_origin", 0.0))


def legal_interval(policy):
    if not math.isfinite(policy.maximum_V) or policy.maximum_V <= 0:
        return None
    lower = policy.minimum_V or 0.0
    if not math.isfinite(lower) or lower < 0 or lower > policy.maximum_V:
        return None
    if policy.step_V is None:
        return lower, policy.maximum_V
    if not math.isfinite(policy.step_V) or policy.step_V <= 0 or not math.isfinite(policy.origin_V):
        raise ValueError("Invalid charge grid")
    step, origin = Decimal(str(policy.step_V)), Decimal(str(policy.origin_V))
    kmin = max(int(((Decimal(str(lower))-origin)/step).to_integral_value(rounding=ROUND_CEILING)),
               int((-origin/step).to_integral_value(rounding=ROUND_FLOOR))+1)
    kmax = int(((Decimal(str(policy.maximum_V))-origin)/step).to_integral_value(rounding=ROUND_FLOOR))
    if kmin > kmax:
        return None
    return float(origin+kmin*step), float(origin+kmax*step)


def charge_choices(crest_per_stage_volt, target, tolerance, policy):
    if not math.isfinite(crest_per_stage_volt) or crest_per_stage_volt <= 0:
        raise ValueError("No valid amplitude gain")
    exact = target/crest_per_stage_volt
    legal = legal_interval(policy)
    band = [(1-tolerance)*exact, (1+tolerance)*exact]
    if legal is None:
        return dict(exact_stage_charge_V=exact, crest_band_stage_charge_V=band, choices_V=[], band_feasible=False)
    lo, hi = legal
    clipped = min(hi, max(lo, exact))
    if policy.step_V is None:
        values = [clipped]
        feasible = max(lo, band[0]) <= min(hi, band[1])
    else:
        step, origin = Decimal(str(policy.step_V)), Decimal(str(policy.origin_V))
        k = (Decimal(str(clipped))-origin)/step
        neighbors = (int(k.to_integral_value(rounding=ROUND_FLOOR)), int(k.to_integral_value(rounding=ROUND_CEILING)))
        values = sorted({min(hi, max(lo, float(origin+j*step))) for j in neighbors})
        feasible = any(band[0] <= v <= band[1] for v in values)
    return dict(exact_stage_charge_V=exact, crest_band_stage_charge_V=band, legal_charge_interval_V=list(legal),
        choices_V=values, band_feasible=bool(feasible), exact_target_within_continuous_limits=lo <= exact <= hi,
        selection_method="ANALYTIC_CLIP" if policy.step_V is None else "LEGAL_NEIGHBORS_OF_ANALYTIC_OPTIMUM",
        minimum_reliable_charge_known=policy.minimum_V is not None, increment_known=policy.step_V is not None)


def hardware_checks(catalog, entry, configuration, setup):
    p = catalog.limits
    n, charge = configuration["stages"], configuration["stage_charge_V"]
    e = .5*catalog.capacitance_F*charge*charge
    constraints = []
    def add(name, value, limit, ok):
        constraints.append(dict(constraint=name, value=value, limit=limit, status="PASS" if ok else "FAIL"))
    add("active_stages", n, [p["active_stages_min"],p["available_stages_max"]], type(n) is int and p["active_stages_min"] <= n <= p["available_stages_max"])
    add("stage_charge_V", charge, p["stage_charge_max"], math.isfinite(charge) and 0 < charge <= p["stage_charge_max"])
    add("summed_charge_V", charge*entry["series_sections"], p["summed_stage_charge_max"], charge*entry["series_sections"] <= p["summed_stage_charge_max"])
    add("stage_energy_J", e, p["stored_energy_per_stage_rated"], e <= p["stored_energy_per_stage_rated"])
    add("total_energy_J", n*e, p["stored_energy_total_rated"], n*e <= p["stored_energy_total_rated"])
    try:
        catalog.adapter.validate(configuration, setup)
        add("shared_configuration_validation", True, True, True)
    except (ValueError, TypeError) as exc:
        add("shared_configuration_validation", getattr(exc,"code",str(exc)), True, False)
    policy = charge_policy(catalog, entry)
    for name, value, ok in [("minimum_reliable_charge", policy.minimum_V, policy.minimum_V is None or charge >= policy.minimum_V),
                            ("charge_increment", policy.step_V, policy.step_V is None or abs((charge-policy.origin_V)/policy.step_V-round((charge-policy.origin_V)/policy.step_V)) <= 1e-9)]:
        constraints.append(dict(constraint=name, limit=value, value=charge, status="UNKNOWN" if value is None else ("PASS" if ok else "FAIL")))
    constraints.append(dict(constraint="component_placements_and_pulse_ratings", status="UNKNOWN", value=None, limit=None))
    return dict(declared_constraints_satisfied=all(c["status"] != "FAIL" for c in constraints), constraints=constraints,
        stage_energy_J=e, total_energy_J=n*e, summed_charge_V=charge*entry["series_sections"],
        hardware_verified=bool(catalog.profile["operational_gate"]["hardware_verified"]), operator_ready=False)
