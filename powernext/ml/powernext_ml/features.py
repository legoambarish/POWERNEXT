"""No target crest, row ID, observed outputs, residuals or status features."""
import numpy as np

SIM_DIRECT = ["tail_parallel","stages", "front_per_stage_ohm", "tail_per_stage_ohm", "dut_nF", "divider_nF", "stray_nF", "basic_additional_nF", "loop_uH", "loop_ohm", "Cg_nF", "CL_nF", "Rf_ohm", "Rt_ohm"]
SIM_GUIDED = SIM_DIRECT + ["CL_over_Cg", "Rf_CL_us", "Rt_Cg_us", "LC_us", "zero_L", "baseline_gain", "baseline_front_us", "baseline_tail_us"]
LEGACY_DIRECT = ["Stages", "Charge_kV_Stage", "Front_R_Stage", "Tail_R_Stage", "Load_C_pF", "Divider_C_pF", "Stray_C_pF", "L_uH", "Efficiency"]
LEGACY_BASE = ["Physics_FrontPeak_us", "Physics_Tail_us", "Physics_Crest_kV"]
LEGACY_GUIDED = LEGACY_DIRECT + LEGACY_BASE
SIM_TARGETS = ["gain", "front_us", "tail_us"]
LEGACY_TARGETS = ["Observed_FrontPeak_us", "Observed_Tail_us", "Observed_Crest_kV"]


def feature_columns(domain, formulation):
    if domain == "legacy":
        return LEGACY_DIRECT if formulation == "direct" else LEGACY_GUIDED
    if domain == "simulation":
        return SIM_DIRECT if formulation == "direct" else SIM_GUIDED
    raise ValueError(domain)


def baseline(frame, domain):
    cols = LEGACY_BASE if domain == "legacy" else ["baseline_gain", "baseline_front_us", "baseline_tail_us"]
    values = frame[cols].to_numpy(float)
    if not np.isfinite(values).all() or (values<=0).any():
        raise ValueError("Invalid deployment-time baseline")
    return values


def labels(frame, domain):
    return frame[LEGACY_TARGETS if domain=="legacy" else SIM_TARGETS].to_numpy(float)
