"""Ranking arithmetic; waveform definitions and validity come from Physics."""
import math
from physics_engine.evaluator import LIMITS


def parameter_score(parameters, mode, target, crest_tolerance):
    limits = LIMITS[mode]
    front_name = "T1_s" if mode == "LI" else "Tp_s"
    values = [parameters.get("crest_V", parameters.get("crest_magnitude_V")), parameters.get(front_name), parameters.get("T2_s")]
    if any(v is None or not math.isfinite(v) or v <= 0 for v in values):
        return None
    nominals = [target, *limits["nominal_s"]]
    widths = [crest_tolerance*target, (limits["front_s"][1]-limits["front_s"][0])/2, (limits["tail_s"][1]-limits["tail_s"][0])/2]
    bounds = [(target*(1-crest_tolerance), target*(1+crest_tolerance)), limits["front_s"], limits["tail_s"]]
    parts = {}
    for name, value, nominal, width, (lo, hi) in zip(["crest", front_name, "T2_s"], values, nominals, widths, bounds):
        error = (value-nominal)/width
        parts[name] = dict(value=value, target=nominal, limits=[lo,hi], normalized_deviation=error,
                           squared_contribution=error*error, deviation_pct=100*(value/nominal-1),
                           normalized_margin=min((value-lo)/width,(hi-value)/width), within_limits=bool(lo <= value <= hi))
    return dict(J=sum(x["squared_contribution"] for x in parts.values()), components=parts,
                minimum_margin=min(x["normalized_margin"] for x in parts.values()),
                scalar_limits_pass=all(x["within_limits"] for x in parts.values()))


def changes(configuration, current):
    if current is None:
        return None
    return [dict(field=k, before=current[k], after=configuration[k]) for k in current if current[k] != configuration[k]]


def rank_key(row):
    if not row["hard_constraints"]["declared_constraints_satisfied"]:
        tier = 3
    elif row["assessment"]["evaluation_status"] != "EVALUABLE":
        tier = 2
    else:
        tier = 0 if row["assessment"]["compliance_status"] == "PASS" else 1
    score = row.get("score")
    changed = row.get("changes_from_current")
    hardware_changes = sum(x["field"] != "stage_charge_V" for x in changed) if changed is not None else 0
    return (tier, round(score["J"],12) if score else float("inf"),
            -round(score["minimum_margin"],12) if score else float("inf"), hardware_changes,
            row["hard_constraints"].get("total_energy_J",float("inf")), row["configuration"]["stages"],
            row["configuration"]["front_per_stage_ohm"], row["configuration"]["tail_per_stage_ohm"], row["candidate_id"])


def rank_rows(rows):
    rows = sorted(rows, key=rank_key)
    for index, row in enumerate(rows):
        row["rank"] = index+1
        row["ranking_tier"] = rank_key(row)[0]
        if index == 0:
            row["ranking_reason"] = "First under the declared lexicographic ordering; inspect compliance before using the setting."
        else:
            previous = rows[index-1]
            names = ["validity/compliance tier", "reference waveform J", "minimum compliance margin", "changed hardware fields", "stored energy", "active stages", "front value", "tail value", "stable candidate ID"]
            a,b=rank_key(previous),rank_key(row)
            decisive=next((name for name,x,y in zip(names,a,b) if x!=y),"identical ranking keys")
            row["ranking_reason"] = f"Follows {previous['candidate_id']} by {decisive}."
        row["ranking_components"] = dict(primary_curve="authoritative_physics_reference", score_rounding_for_order_only=12,
            hardware_changes=None if row.get("changes_from_current") is None else sum(x["field"]!="stage_charge_V" for x in row["changes_from_current"]))
    return rows
