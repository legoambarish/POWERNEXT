"""Non-unique double-exponential plotting reference, not a Physics label.

It matches the competition's nominal LI virtual-front/virtual-tail or SI
physical-peak/physical-tail definitions. All references start at firing t=0.
"""
from functools import lru_cache
import math
import numpy as np
from scipy.optimize import brentq


def _shape(log_ratio, mode):
    ratio = math.exp(log_ratio)
    peak_t = ratio * math.log(ratio) / (ratio - 1)
    def value(t):
        return math.exp(-t / ratio) - math.exp(-t)
    peak = value(peak_t)
    t30 = brentq(lambda t: value(t) - .3 * peak, 0, peak_t)
    t90 = brentq(lambda t: value(t) - .9 * peak, 0, peak_t)
    t50 = brentq(lambda t: value(t) - .5 * peak, peak_t, ratio * 20)
    origin = t30 - .5 * (t90 - t30)
    front = (t90 - t30) / .6 if mode == "LI" else peak_t
    tail = t50 - origin if mode == "LI" else t50
    return ratio, peak_t, peak, front, tail, origin


@lru_cache(maxsize=2)
def target_parameters(mode):
    if mode not in ("LI", "SI"):
        raise ValueError("Expected LI or SI")
    front, tail = (1.2e-6, 50e-6) if mode == "LI" else (250e-6, 2500e-6)
    def residual(log_ratio):
        shape = _shape(log_ratio, mode)
        return shape[4] / shape[3] - tail / front
    root = brentq(residual, math.log(1.001), math.log(1e6))
    ratio, peak_t, peak, unit_front, unit_tail, origin = _shape(root, mode)
    fast = front / unit_front
    return dict(mode=mode, family="NON_UNIQUE_DOUBLE_EXPONENTIAL_REFERENCE",
        fast_tau_s=fast, slow_tau_s=fast * ratio, unscaled_peak=peak,
        peak_time_s=peak_t * fast, virtual_origin_s=origin * fast,
        nominal_front_s=front, nominal_tail_s=tail,
        analytic_front_s=unit_front * fast, analytic_tail_s=unit_tail * fast,
        alignment="Physical firing t=0; no shift of simulated traces",
        qualification="Plotting reference only; three scalar requirements do not uniquely specify a waveform")


def target_voltage(time_s, mode, crest_V):
    p = target_parameters(mode)
    t = np.asarray(time_s, dtype=float)
    x = np.maximum(t, 0)
    y = (np.exp(-x / p["slow_tau_s"]) - np.exp(-x / p["fast_tau_s"]))
    return np.where(t >= 0, y * float(crest_V) / p["unscaled_peak"], 0.)
