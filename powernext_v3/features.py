"""Feature construction and the independent L0 physics baseline for ML v3.

The v3 model is deliberately route specific.  A route is the product of an
evidence domain, impulse mode, and reduced network topology; those values are
stored as row metadata and are not encoded as feature columns.  Charge,
requested crest, polarity, and recipe identifiers are also excluded because
they either scale a linear response or describe a component arrangement rather
than the reduced network response.

``feature_matrix`` is the hot path used by catalog inference.  Its baseline is
the same two-capacitor L0 oracle used by the legacy adapter, but the three
fractional crossing times are solved in vectorized bisection batches instead of
calling a scalar root solver once per row.
"""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, is_dataclass
from typing import Any

import numpy as np

try:  # The profile module has no heavy dependencies and is safe at import time.
    from .profiles import get_profile
except ImportError:  # pragma: no cover - useful when executed as a loose module.
    from profiles import get_profile


# Public schema.  Keep all physical inputs in engineering units that are easy
# to inspect in JSON (nF, uH, ohm, and us).  The final three columns are the
# exact L0 response and are therefore available to both formulations.
BASE_FEATURE_COLUMNS = (
    "stages",
    "front_per_stage_ohm",
    "tail_per_stage_ohm",
    "dut_nF",
    "divider_nF",
    "stray_nF",
    "basic_additional_nF",
    "loop_uH",
    "loop_ohm",
    "load_kohm",
    "Cg_nF",
    "CL_nF",
    "Rf_ohm",
    "Rt_ohm",
    "CL_over_Cg",
    "Rf_CL_us",
    "Rt_Cg_us",
    "LC_us",
    "zero_L",
)

BASELINE_COLUMNS = ("baseline_gain", "baseline_front_us", "baseline_tail_us")
FEATURE_COLUMNS = BASE_FEATURE_COLUMNS + BASELINE_COLUMNS

# The two names make downstream code explicit without duplicating the schema.
PHYSICS_FEATURE_COLUMNS = FEATURE_COLUMNS
L0_BASELINE_COLUMNS = BASELINE_COLUMNS
BASELINE_FEATURE_COLUMNS = BASELINE_COLUMNS

TARGET_COLUMNS = ("gain", "front_us", "tail_us")
ROUTE_DOMAINS = ("cpri_0p5uf", "research_3uf")
MODES = ("LI", "SI")
TOPOLOGIES = ("GSHUNT_v0", "OSHUNT_v0")


def feature_columns(formulation: str | None = None) -> tuple[str, ...]:
    """Return the immutable v3 order for either approved formulation."""

    if formulation is not None and formulation not in ("physics_guided", "residual"):
        raise ValueError(f"Unknown v3 formulation {formulation}")
    return FEATURE_COLUMNS


def baseline(features: Any) -> np.ndarray:
    """Extract ``gain/front_us/tail_us`` L0 columns from a feature matrix."""

    if isinstance(features, Mapping):
        return np.asarray([[features[name] for name in BASELINE_COLUMNS]], dtype=float)
    arr = np.asarray(features, dtype=float)
    if arr.ndim == 1:
        arr = arr.reshape(1, -1)
    if arr.ndim != 2 or arr.shape[1] != len(FEATURE_COLUMNS):
        raise ValueError(f"Expected N x {len(FEATURE_COLUMNS)} feature matrix")
    return arr[:, -len(BASELINE_COLUMNS):]


def _mapping(value: Any) -> Mapping[str, Any]:
    """Return a read-only-ish mapping for dicts and legacy dataclasses."""

    if isinstance(value, Mapping):
        return value
    if is_dataclass(value):
        return asdict(value)
    if hasattr(value, "__dict__"):
        return vars(value)
    raise TypeError(f"Expected a mapping or dataclass, got {type(value).__name__}")


def _value(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _as_float_array(value: Any, name: str, *, positive: bool = False) -> np.ndarray:
    arr = np.asarray(value, dtype=float)
    if arr.ndim == 0:
        arr = arr.reshape(1)
    if not np.isfinite(arr).all() or (arr <= 0 if positive else arr < 0).any():
        sign = "positive" if positive else "non-negative"
        raise ValueError(f"{name} must contain finite {sign} values")
    return arr


def _broadcast_inputs(stages: Any, front_ohm: Any, tail_ohm: Any) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    n, f, t = np.broadcast_arrays(
        _as_float_array(stages, "stages", positive=True),
        _as_float_array(front_ohm, "front_ohm", positive=True),
        _as_float_array(tail_ohm, "tail_ohm", positive=True),
    )
    # Stage counts are categorical physical values.  A float such as 2.5 is
    # almost certainly a caller error and must not silently alter Cg.
    if np.any(np.abs(n - np.rint(n)) > 1e-10):
        raise ValueError("stages must be integer-valued")
    return np.rint(n).astype(np.int64), f.astype(float), t.astype(float)


def _setup_values(setup: Any) -> dict[str, float]:
    """Normalize a legacy SI-unit Setup object or its JSON dictionary."""

    names = (
        "dut_capacitance_F",
        "divider_capacitance_F",
        "stray_capacitance_F",
        "loop_inductance_H",
        "loop_resistance_ohm",
    )
    out: dict[str, float] = {}
    for name in names:
        raw = _value(setup, name, 0.0)
        if raw is None:
            raw = 0.0
        try:
            out[name] = float(raw)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid setup field {name}") from exc
        if not np.isfinite(out[name]) or out[name] < 0:
            raise ValueError(f"Invalid setup field {name}")

    coverage = _value(setup, "basic_coverage_assumption", "ADDITIONAL_DISJOINT")
    if coverage not in ("ADDITIONAL_DISJOINT", "INCLUDED_IN_OTHER_COMPONENTS"):
        raise ValueError("basic_coverage_assumption must be explicit")
    out["basic_additional_F"] = 480e-12 if coverage == "ADDITIONAL_DISJOINT" else 0.0

    load = _value(setup, "load_resistance_ohm", None)
    if load is not None:
        # The exact legacy L0 oracle has no leakage branch.  Refusing this
        # optional physics field is safer than presenting a baseline that
        # silently ignores a meaningful load; a future route can add a distinct
        # oracle and feature version explicitly.
        load_value = float(load)
        if not np.isfinite(load_value) or load_value <= 0:
            raise ValueError("load_resistance_ohm must be positive when supplied")
        raise ValueError("L0 feature baseline does not support load_resistance_ohm; use the physics route")
    out["load_resistance_ohm"] = 0.0
    return out


def _network_equivalent(tree: Any) -> float | None:
    """Resolve an optional front/tail network tree if v3 networks are loaded.

    Feature construction remains usable before ``powernext_v3.networks`` is
    imported.  A tree is an input description, never an identity feature.
    """

    if tree is None:
        return None
    try:
        from .networks import equivalent_resistance, canonicalize

        return float(equivalent_resistance(canonicalize(tree)))
    except (ImportError, AttributeError):  # pragma: no cover - optional route.
        pass
    if isinstance(tree, Mapping):
        # A compact equivalent node is useful for fixtures and is unambiguous.
        for key in ("equivalent_resistance_ohm", "equivalent_ohm", "resistance_ohm"):
            if key in tree:
                return float(tree[key])
    return None


def _config_resistance(configuration: Any, name: str) -> float:
    raw = _value(configuration, name, None)
    tree = _value(configuration, name.removesuffix("_per_stage_ohm") + "_network", None)
    equivalent = _network_equivalent(tree)
    if raw is None:
        raw = equivalent
    elif equivalent is not None and not np.isclose(float(raw), equivalent, rtol=1e-12, atol=0.0):
        raise ValueError(f"{name} disagrees with its network equivalent")
    if raw is None:
        raise ValueError(f"Missing {name}")
    value = float(raw)
    if not np.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def _root_rising(alpha: np.ndarray, beta: np.ndarray, peak_t: np.ndarray, level: np.ndarray) -> np.ndarray:
    """Batched rising root for exp(-alpha*t)(1-exp(-delta*t)) == level."""

    delta = beta - alpha
    lo = np.zeros_like(alpha)
    hi = peak_t.copy()
    for _ in range(72):
        mid = (lo + hi) * 0.5
        value = np.exp(-alpha * mid) * (-np.expm1(-delta * mid))
        lo = np.where(value < level, mid, lo)
        hi = np.where(value < level, hi, mid)
    return (lo + hi) * 0.5


def _root_falling(alpha: np.ndarray, beta: np.ndarray, peak_t: np.ndarray, level: np.ndarray) -> np.ndarray:
    """Batched falling root with a finite, vectorized upper-bound search."""

    delta = beta - alpha
    lo = peak_t.copy()
    hi = np.maximum(peak_t * 2.0, 20.0 / alpha)
    for _ in range(16):
        value = np.exp(-alpha * hi) * (-np.expm1(-delta * hi))
        needs_more = value > level
        if not np.any(needs_more):
            break
        hi = np.where(needs_more, hi * 2.0, hi)
    value_hi = np.exp(-alpha * hi) * (-np.expm1(-delta * hi))
    if np.any(value_hi > level):
        raise ValueError("Unable to bracket vectorized L0 falling roots")
    for _ in range(72):
        mid = (lo + hi) * 0.5
        value = np.exp(-alpha * mid) * (-np.expm1(-delta * mid))
        lo = np.where(value > level, mid, lo)
        hi = np.where(value > level, hi, mid)
    return (lo + hi) * 0.5


def _l0_baseline(cg: np.ndarray, cl: float, rf: np.ndarray, rt: np.ndarray, mode: str, topology: str) -> np.ndarray:
    """Return gain/front/tail for the exact legacy two-capacitor L0 oracle."""

    if topology == "GSHUNT_v0":
        a = 1.0 / (rt * cg) + 1.0 / (rf * cg) + 1.0 / (rf * cl)
    elif topology == "OSHUNT_v0":
        a = 1.0 / (rf * cg) + 1.0 / (rf * cl) + 1.0 / (rt * cl)
    else:
        raise ValueError(f"Unknown topology {topology}")
    b = 1.0 / (rf * rt * cg * cl)
    disc = a * a - 4.0 * b
    if np.any(disc <= 0):
        raise ValueError("L0 reference requires distinct positive decay rates")
    beta = (a + np.sqrt(disc)) * 0.5
    alpha = b / beta  # stable near the equal-rate limit
    delta = beta - alpha
    if np.any(~np.isfinite(delta) | (delta <= 0)):
        raise ValueError("Invalid L0 decay rates")

    peak_t = np.log(beta / alpha) / delta
    peak = np.exp(-alpha * peak_t) * (-np.expm1(-delta * peak_t))
    gain = peak / (rf * cl * delta)
    t30 = _root_rising(alpha, beta, peak_t, 0.3 * peak)
    t90 = _root_rising(alpha, beta, peak_t, 0.9 * peak)
    t50 = _root_falling(alpha, beta, peak_t, 0.5 * peak)
    if mode == "LI":
        front = (t90 - t30) / 0.6
        tail = t50 - (t30 - 0.3 * front)
    elif mode == "SI":
        front = peak_t
        tail = t50
    else:
        raise ValueError(f"Unknown impulse mode {mode}")
    result = np.column_stack((gain, front * 1e6, tail * 1e6))
    if not np.isfinite(result).all() or (result <= 0).any():
        raise ValueError("Non-positive L0 baseline")
    return result


def feature_matrix(
    stages: Any,
    front_ohm: Any,
    tail_ohm: Any,
    setup: Any,
    domain_id: str,
    mode: str,
    topology: str,
) -> np.ndarray:
    """Build an ``N x len(FEATURE_COLUMNS)`` matrix for a route.

    ``stages``, ``front_ohm``, and ``tail_ohm`` may be scalars or broadcastable
    arrays.  The setup is shared by the batch, as it is for a catalog request.
    All resistor arguments are per-stage equivalent values; component recipe
    identities are intentionally not accepted here.
    """

    if domain_id not in ROUTE_DOMAINS:
        raise ValueError(f"Unknown domain_id {domain_id}")
    if mode not in MODES:
        raise ValueError(f"Unknown mode {mode}")
    if topology not in TOPOLOGIES:
        raise ValueError(f"Unknown topology {topology}")
    profile = get_profile(domain_id)
    n, front, tail = _broadcast_inputs(stages, front_ohm, tail_ohm)
    s = _setup_values(setup)
    if np.any(n < profile.stages_min) or np.any(n > profile.stages_max):
        raise ValueError("stages outside the selected profile domain")

    dut = s["dut_capacitance_F"]
    divider = s["divider_capacitance_F"]
    stray = s["stray_capacitance_F"]
    basic = s["basic_additional_F"]
    cl = dut + divider + stray + basic
    if cl <= 0:
        raise ValueError("total output capacitance must be positive")
    loop_l = s["loop_inductance_H"]
    loop_r = s["loop_resistance_ohm"]
    cg = profile.stage_capacitance_F / n.astype(float)
    rf = n * front + loop_r
    rt = n * tail
    baseline = _l0_baseline(cg, cl, rf, rt, mode, topology)

    ceq = cg * cl / (cg + cl)
    base = np.column_stack(
        (
            n,
            front,
            tail,
            np.full(n.shape, dut * 1e9),
            np.full(n.shape, divider * 1e9),
            np.full(n.shape, stray * 1e9),
            np.full(n.shape, basic * 1e9),
            np.full(n.shape, loop_l * 1e6),
            np.full(n.shape, loop_r),
            np.full(n.shape, s["load_resistance_ohm"] / 1000.0),
            cg * 1e9,
            np.full(n.shape, cl * 1e9),
            rf,
            rt,
            cl / cg,
            rf * cl * 1e6,
            rt * cg * 1e6,
            np.sqrt(loop_l * ceq) * 1e6,
            np.full(n.shape, float(loop_l == 0.0)),
        )
    )
    return np.column_stack((base, baseline))


def feature_rows(configurations: Sequence[Any], setup: Any, domain_id: str) -> list[dict[str, float]]:
    """Return JSON-friendly feature dictionaries for configuration requests."""

    if isinstance(configurations, Mapping) or not isinstance(configurations, Sequence):
        configurations = [configurations]
    if not configurations:
        return []
    configs = [_mapping(c) for c in configurations]
    setups = setup if isinstance(setup, Sequence) and not isinstance(setup, (str, bytes, Mapping)) else None
    if setups is not None and len(setups) != len(configs):
        raise ValueError("A setup sequence must have one entry per configuration")
    values = []
    for i, c in enumerate(configs):
        s = setups[i] if setups is not None else setup
        matrix = feature_matrix(
            c.get("stages"),
            _config_resistance(c, "front_per_stage_ohm"),
            _config_resistance(c, "tail_per_stage_ohm"),
            s,
            domain_id,
            c.get("impulse_type"),
            c.get("topology_id"),
        )
        values.append(dict(zip(FEATURE_COLUMNS, matrix[0].tolist())))
    return values


def feature_dict_from_array(features: np.ndarray) -> list[dict[str, float]]:
    """Convert a model input matrix to feature dictionaries for diagnostics."""

    arr = np.asarray(features, dtype=float)
    if arr.ndim == 1:
        arr = arr.reshape(1, -1)
    if arr.ndim != 2 or arr.shape[1] != len(FEATURE_COLUMNS):
        raise ValueError(f"Expected N x {len(FEATURE_COLUMNS)} feature matrix")
    return [dict(zip(FEATURE_COLUMNS, row.tolist())) for row in arr]
