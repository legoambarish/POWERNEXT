"""Versioned, resumable design and simulation data for the v3 API.

The v3 data contract is intentionally independent of the legacy ML package.
Design rows are created from inputs only, grouped and split before a simulator
is called, and then enriched with physics labels.  A row that the simulator
cannot support is retained with null labels; it is never silently dropped.

The module does not run generation at import time.  The default command line
target is large enough for the approved Phase B screen (10,000 eligible
independent shapes per route, with a 30,000-per-route extension capacity), but
generation is always an explicit command and can be resumed from append-only
JSONL checkpoints.
"""
from __future__ import annotations

import argparse
from bisect import bisect_left
import copy
from collections import Counter, defaultdict
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from dataclasses import dataclass, replace
from datetime import datetime, timezone
import hashlib
import importlib
import json
import math
import os
from pathlib import Path
import random
import sys
import time
from functools import lru_cache
from fractions import Fraction
from typing import Any, Callable, Iterable, Iterator, Mapping, Sequence


SCHEMA_VERSION = "powernext_v3_dataset_1.0"
DESIGN_SCHEMA_VERSION = "powernext_v3_design_1.0"
DEFAULT_SEED = 20261010
DEFAULT_TARGET_PER_ROUTE = 10_000
DEFAULT_CAPACITY_PER_ROUTE = 30_000
DEFAULT_N_POINTS = 1_600
DEFAULT_WORKERS = max(1, min(4, (os.cpu_count() or 1)))
MAX_REPRESENTATIVE_WAVEFORMS_PER_ROUTE = 32
DOMAINS = ("cpri_0p5uf", "research_3uf")
MODES = ("LI", "SI")
TOPOLOGIES = ("GSHUNT_v0", "OSHUNT_v0")
ROUTES = tuple((domain, mode, topology) for domain in DOMAINS for mode in MODES for topology in TOPOLOGIES)
VALID_STATUSES = {"PENDING", "SIMULATED", "INVALID_OR_UNSUPPORTED", "ERROR"}


def _canonical(value: Any) -> Any:
    """Return JSON-stable values for hashes and manifests."""

    if isinstance(value, Mapping):
        return {str(k): _canonical(v) for k, v in sorted(value.items(), key=lambda item: str(item[0]))}
    if isinstance(value, (list, tuple)):
        return [_canonical(v) for v in value]
    if isinstance(value, float):
        if not math.isfinite(value):
            return str(value)
        # Preserve physically meaningful continuous values while avoiding
        # platform-dependent repr noise in group and input identities.
        return float(format(value, ".15g"))
    if hasattr(value, "item") and callable(value.item):
        try:
            return _canonical(value.item())
        except Exception:
            pass
    return value


def digest(value: Any) -> str:
    payload = json.dumps(_canonical(value), sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _json_dump(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False), encoding="utf-8")
    os.replace(temporary, path)


def _json_line(value: Any) -> str:
    return json.dumps(_canonical(value), sort_keys=True, separators=(",", ":"), allow_nan=False)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@dataclass(frozen=True)
class DatasetPlan:
    """Immutable generation settings recorded in ``manifest.json``."""

    target_per_route: int = DEFAULT_TARGET_PER_ROUTE
    learning_curve_capacity_per_route: int = DEFAULT_CAPACITY_PER_ROUTE
    seed: int = DEFAULT_SEED
    workers: int = DEFAULT_WORKERS
    n_points: int = DEFAULT_N_POINTS
    waveform_policy: str = "representative"
    heartbeat_every: int = 50
    active_per_route: int | None = None
    representative_waveforms_per_route: int = MAX_REPRESENTATIVE_WAVEFORMS_PER_ROUTE
    initial_attempts_per_route: int | None = None

    def __post_init__(self) -> None:
        if type(self.target_per_route) is not int or self.target_per_route < 1:
            raise ValueError("target_per_route must be a positive integer")
        if type(self.learning_curve_capacity_per_route) is not int or self.learning_curve_capacity_per_route < self.target_per_route:
            raise ValueError("learning_curve_capacity_per_route must be >= target_per_route")
        if type(self.n_points) is not int or self.n_points < 1_000:
            raise ValueError("n_points must be at least 1000")
        if self.waveform_policy not in {"none", "representative", "failure", "all"}:
            raise ValueError("waveform_policy must be none, representative, failure, or all")
        if type(self.workers) is not int or self.workers < 1:
            raise ValueError("workers must be a positive integer")
        if type(self.heartbeat_every) is not int or self.heartbeat_every < 1:
            raise ValueError("heartbeat_every must be a positive integer")
        if type(self.representative_waveforms_per_route) is not int or self.representative_waveforms_per_route < 1:
            raise ValueError("representative_waveforms_per_route must be a positive integer")
        initial = min(self.learning_curve_capacity_per_route, self.target_per_route + max(1, self.target_per_route // 5)) if self.initial_attempts_per_route is None else self.initial_attempts_per_route
        if type(initial) is not int or initial < self.target_per_route or initial > self.learning_curve_capacity_per_route:
            raise ValueError("initial_attempts_per_route must be between target_per_route and learning_curve_capacity_per_route")
        active = initial if self.active_per_route is None else self.active_per_route
        if type(active) is not int or active < self.target_per_route or active > self.learning_curve_capacity_per_route:
            raise ValueError("active_per_route must be between target_per_route and learning_curve_capacity_per_route")
        object.__setattr__(self, "active_per_route", active)
        object.__setattr__(self, "initial_attempts_per_route", initial)

    def as_dict(self) -> dict[str, Any]:
        return {
            "target_per_route": self.target_per_route,
            "learning_curve_capacity_per_route": self.learning_curve_capacity_per_route,
            "seed": self.seed,
            "workers": self.workers,
            "n_points": self.n_points,
            "waveform_policy": self.waveform_policy,
            "heartbeat_every": self.heartbeat_every,
            "active_per_route": self.active_per_route,
            "representative_waveforms_per_route": self.representative_waveforms_per_route,
            "initial_attempts_per_route": self.initial_attempts_per_route,
        }


def _profile(domain_id: str) -> Any:
    profiles = importlib.import_module("powernext_v3.profiles")
    return profiles.get_profile(domain_id)


def _network_catalog(max_modules: int = 4) -> list[dict[str, Any]]:
    """Read the networks worker's public API without depending on internals."""

    try:
        module = importlib.import_module("powernext_v3.networks")
        raw = module.enumerate_networks(max_modules=max_modules)
    except Exception as exc:
        raise RuntimeError("The v3 network catalogue is unavailable; refusing to substitute single-resistor recipes") from exc
    if isinstance(raw, Mapping):
        values: list[Any] = []
        for key, item in raw.items():
            if isinstance(item, Mapping):
                candidate = dict(item)
                candidate.setdefault("network_id", str(key))
                values.append(candidate)
            else:
                values.append({"network_id": str(key), "network": item})
        raw_values = values
    else:
        raw_values = list(raw) if isinstance(raw, Iterable) and not isinstance(raw, (str, bytes)) else []
    catalog: list[dict[str, Any]] = []
    for index, item in enumerate(raw_values):
        if isinstance(item, Mapping):
            record = dict(item)
        else:
            # The v3 networks worker returns immutable NetworkRecipe objects
            # through its public API.  Keep the integration at that public
            # surface rather than importing its private frozen-tree type.
            record = {
                "network": getattr(item, "tree", getattr(item, "canonical_tree", None)),
                "network_id": getattr(item, "id", getattr(item, "recipe_id", f"network_{index:04d}")),
                "equivalent_ohm": getattr(item, "equivalent_ohm", getattr(item, "equivalent_resistance", None)),
                "recipe_id": getattr(item, "recipe_id", getattr(item, "id", None)),
                "module_count": getattr(item, "module_count", None),
            }
        network = record.get("network", record.get("tree", record.get("recipe")))
        if network is None and "op" in record:
            network = record
        if network is None:
            raise RuntimeError(f"The v3 network catalogue returned an entry without a canonical tree at index {index}")
        family = str(record.get("family_id", record.get("network_id", record.get("id", f"network_{index:04d}"))))
        equivalent = record.get("equivalent_ohm", record.get("equivalent_resistance_ohm", record.get("ohm")))
        if hasattr(equivalent, "numerator") and hasattr(equivalent, "denominator"):
            equivalent = float(equivalent)
        topology = record.get("topology_id")
        catalog.append({
            "network_id": family,
            "family_id": family,
            "network": copy.deepcopy(network),
            "equivalent_ohm": equivalent,
            "topology_id": topology,
            "recipe_id": record.get("recipe_id", record.get("recipe")),
            "module_count": record.get("module_count"),
            "source": "powernext_v3.networks.enumerate_networks",
        })
    if not catalog:
        raise RuntimeError("The v3 network catalogue is empty; refusing to substitute single-resistor recipes")
    return catalog


def _tree_module_count(tree: Any) -> int | None:
    """Count resistor leaves in a public network tree."""

    if not isinstance(tree, Mapping):
        return None
    if tree.get("op") == "R":
        return 1
    children = tree.get("children")
    if tree.get("op") not in {"S", "P"} or not isinstance(children, Sequence):
        return None
    counts = [_tree_module_count(child) for child in children]
    if any(count is None for count in counts):
        return None
    return sum(int(count) for count in counts)


def _catalog_by_modules(catalog: Sequence[Mapping[str, Any]]) -> dict[int, list[dict[str, Any]]]:
    """Return deterministic module-count buckets for independent branch sampling."""

    buckets: dict[int, list[dict[str, Any]]] = {count: [] for count in range(1, 5)}
    for item in catalog:
        record = dict(item)
        count = record.get("module_count")
        if count is None:
            count = _tree_module_count(record.get("network"))
        try:
            count = int(count)
        except (TypeError, ValueError):
            continue
        if count not in buckets:
            continue
        record["module_count"] = count
        record["equivalent_ohm"] = _network_equivalent(record.get("network"), record.get("equivalent_ohm"))
        buckets[count].append(record)
    for values in buckets.values():
        values.sort(key=lambda item: (
            math.log(max(float(item.get("equivalent_ohm") or 1e-12), 1e-12)),
            str(item.get("network_id", "")),
        ))
    missing = [count for count, values in buckets.items() if not values]
    if missing:
        raise RuntimeError(f"The v3 network catalogue is missing module-count strata: {missing}")
    return buckets


def _network_for(catalog: Sequence[Mapping[str, Any]], index: int, branch: str, mode: str) -> Mapping[str, Any]:
    """Compatibility helper selecting one deterministic catalogue recipe."""

    if not catalog:
        raise RuntimeError("The v3 network catalogue is empty")
    item = catalog[index % len(catalog)]
    network = item.get("network")
    if isinstance(network, Mapping):
        return copy.deepcopy(network)
    raise RuntimeError(f"The v3 network catalogue entry {item.get('network_id', '<unknown>')} has no canonical tree")


def _select_network(
    buckets: Mapping[int, Sequence[Mapping[str, Any]]],
    *,
    desired_ohm: float,
    module_count: int,
    independent_index: int,
) -> tuple[dict[str, Any], Mapping[str, Any]]:
    """Select a recipe by log-resistance and module-count strata.

    Front and tail calls receive different deterministic indices.  The choice
    is therefore independent by branch while still covering all one through
    four-module strata and the broad resistance range.  A nearest equivalent
    search is used within a stratum so inverse-guided boundary and rare probes
    remain tied to their requested recipe family.
    """

    candidates = buckets.get(int(module_count), ())
    if not candidates:
        raise RuntimeError(f"The v3 network catalogue has no {module_count}-module recipe stratum")
    desired = max(float(desired_ohm), 1e-12)
    center = bisect_left(candidates, math.log(desired), key=lambda item: math.log(float(item["equivalent_ohm"])))
    # Buckets are already resistance-sorted. Only the local neighbours can be
    # among the nearest values; avoid sorting thousands of trees per request.
    nearby = [(i, candidates[i]) for i in range(max(0, center-8), min(len(candidates), center+8))]
    ranked = sorted(
        nearby,
        key=lambda pair: (
            abs(math.log(max(float(pair[1].get("equivalent_ohm") or 1e-12), 1e-12) / desired)),
            (pair[0] - independent_index) % len(candidates),
        ),
    )
    # Select one of the nearest few values using the independent branch index;
    # this avoids repeating the same recipe forever when the catalogue has
    # several exact or near-equivalent trees.
    shortlist = ranked[: min(2 if module_count==1 else 4, len(ranked))]
    item = dict(shortlist[independent_index % len(shortlist)][1])
    network = item.get("network")
    if not isinstance(network, Mapping):
        raise RuntimeError(f"The v3 network catalogue entry {item.get('network_id', '<unknown>')} has no canonical tree")
    return copy.deepcopy(dict(network)), item


def _equivalent_from_tree(tree: Any) -> float | None:
    """Best-effort equivalent for design rows; physics remains authoritative."""

    if not isinstance(tree, Mapping):
        return None
    op = tree.get("op")
    if op == "R":
        try:
            return float(tree["ohm"])
        except (TypeError, ValueError, KeyError):
            return None
    children = tree.get("children")
    if op not in {"S", "P"} or not isinstance(children, Sequence) or not children:
        return None
    values = [_equivalent_from_tree(child) for child in children]
    if any(value is None or value <= 0 for value in values):
        return None
    if op == "S":
        return float(sum(values))
    return float(1.0 / sum(1.0 / value for value in values))


def _network_equivalent(network: Mapping[str, Any] | None, fallback: float) -> float:
    value = _equivalent_from_tree(network)
    return fallback if value is None else value


def _network_exact_key(network: Any, fallback: Any) -> Any:
    """Use the networks worker's exact Fraction grouping when available."""

    if network is not None:
        try:
            module = importlib.import_module("powernext_v3.networks")
            exact = module.equivalent_resistance(module.canonicalize(network))
            if hasattr(exact, "numerator") and hasattr(exact, "denominator"):
                return f"{exact.numerator}/{exact.denominator}"
            return format(float(exact), ".15g")
        except Exception:
            pass
    value = _finite_or_none(fallback)
    return None if value is None else format(value, ".15g")


def _finite_or_none(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _setup_for(
    rng: random.Random,
    family_index: int,
    *,
    boundary: bool = False,
    boundary_variant: str = "low",
) -> tuple[dict[str, Any], str]:
    """Create a fixed setup family; setup families are split atomically."""

    family_id = f"V3_SETUP_{family_index:05d}"
    if boundary:
        if boundary_variant == "high":
            dut_nF, divider_nF, stray_nF, loop_uH, loop_r = 12.0, 2.0, 1.5, 120.0, 20.0
        elif boundary_variant == "low":
            dut_nF, divider_nF, stray_nF, loop_uH, loop_r = 0.08, 0.05, 0.0, 0.0, 0.0
        else:
            raise ValueError("boundary_variant must be low or high")
    elif family_index % 5 == 0:
        dut_nF, divider_nF, stray_nF, loop_uH, loop_r = 10.0, 3.0, 1.0, 120.0, 20.0
    else:
        dut_nF = rng.uniform(0.08, 12.0)
        divider_nF = rng.uniform(0.02, 2.0)
        stray_nF = rng.uniform(0.0, 1.5)
        loop_uH = rng.uniform(0.0, 120.0)
        loop_r = rng.uniform(0.0, 20.0)
    setup = {
        "dut_capacitance_F": dut_nF * 1e-9,
        "divider_capacitance_F": divider_nF * 1e-9,
        "stray_capacitance_F": stray_nF * 1e-9,
        "loop_inductance_H": loop_uH * 1e-6,
        "basic_coverage_assumption": "ADDITIONAL_DISJOINT" if family_index % 2 == 0 else "INCLUDED_IN_OTHER_COMPONENTS",
        "loop_resistance_ohm": loop_r,
        "load_resistance_ohm": None,
        "setup_id": family_id,
        "auxiliary_assumption": "UNCONFIRMED_AUXILIARY_BRANCHES_OMITTED",
    }
    return setup, family_id


def _input_shape_identity(request: Mapping[str, Any]) -> str:
    """Identity of a response shape, excluding amplitude and polarity.

    Stage charge and polarity are exact linear amplitude transformations.  The
    partition of terminal capacitance is similarly excluded in favour of its
    total, while loop and leakage parameters stay in the shape.  This is an
    input-only identity and therefore cannot leak a simulator label into the
    split.
    """

    configuration = dict(request["configuration"])
    setup = dict(request["setup"])
    domain_id = request.get("domain_id")
    profile = _profile(str(domain_id))
    stages = int(configuration.get("stages"))
    # Derive the graph quantities used by physics.py.  This deliberately
    # collapses raw partitions and recipe-tree spellings to the actual linear
    # response identity; stage charge and polarity are exact amplitude changes.
    stage_capacitance = float(getattr(profile, "stage_capacitance_F"))
    c_g = stage_capacitance / stages
    cap_total = sum(float(setup.get(name, 0.0) or 0.0) for name in ("dut_capacitance_F", "divider_capacitance_F", "stray_capacitance_F"))
    if setup.get("basic_coverage_assumption") == "ADDITIONAL_DISJOINT":
        cap_total += 480e-12
    front_value = _finite_or_none(configuration.get("front_per_stage_ohm")) or 0.0
    tail_value = _finite_or_none(configuration.get("tail_per_stage_ohm")) or 0.0
    loop_r = _finite_or_none(setup.get("loop_resistance_ohm", 0.0)) or 0.0
    # Keep only the normalized reduced-graph quantities in the response key.
    # The graph assumption itself is intentionally absent once it has been
    # represented by CL; raw recipe trees and redundant configuration fields
    # cannot create a second group for the same response shape.
    shape = {
        "domain_id": domain_id,
        "mode": request.get("mode", configuration.get("impulse_type")),
        "topology_id": request.get("topology_id", configuration.get("topology_id")),
        "Cg_F": float(format(c_g, ".15g")),
        "CL_F": float(format(cap_total, ".15g")),
        "Rf_total_ohm": float(format(stages * front_value + loop_r, ".15g")),
        "Rt_total_ohm": float(format(stages * tail_value, ".15g")),
        "loop_inductance_H": setup.get("loop_inductance_H"),
        "leak_resistance_ohm": setup.get("load_resistance_ohm"),
    }
    return digest(shape)


def _setup_family_identity(request: Mapping[str, Any]) -> str:
    """Normalize a fixed setup so aliases cannot leak across a split."""

    setup = dict(request.get("setup", {}))
    cap_total = sum(float(setup.get(name, 0.0) or 0.0) for name in ("dut_capacitance_F", "divider_capacitance_F", "stray_capacitance_F"))
    if setup.get("basic_coverage_assumption") == "ADDITIONAL_DISJOINT":
        cap_total += 480e-12
    return digest({
        "CL_F": float(format(cap_total, ".15g")),
        "loop_inductance_H": setup.get("loop_inductance_H"),
        "loop_resistance_ohm": setup.get("loop_resistance_ohm", 0.0),
        "load_resistance_ohm": setup.get("load_resistance_ohm"),
    })


def _response_group_identity(request: Mapping[str, Any]) -> str:
    return _input_shape_identity(request)


def _stable_split(group_id: str) -> str:
    # The first byte is enough for a stable, balanced split; cryptographic hash
    # avoids dependence on Python's process-randomized hash seed.
    bucket = int(hashlib.sha256(group_id.encode("ascii")).hexdigest()[:8], 16) / 0xFFFFFFFF
    return "train" if bucket < 0.70 else ("validation" if bucket < 0.85 else "test")


def _union_find_groups(requests: Sequence[Mapping[str, Any]]) -> list[str]:
    """Join response equivalents and fixed setup families before labels."""

    parent = list(range(len(requests)))

    def find(item: int) -> int:
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    def union(left: int, right: int) -> None:
        root_left, root_right = find(left), find(right)
        if root_left != root_right:
            parent[root_right] = root_left

    seen_shape: dict[str, int] = {}
    seen_family: dict[str, int] = {}
    for index, request in enumerate(requests):
        shape = str(request.get("response_group_key") or request.get("response_group_id") or _response_group_identity(request))
        family = str(request.get("setup_family_key") or _setup_family_identity(request))
        if shape in seen_shape:
            union(index, seen_shape[shape])
        else:
            seen_shape[shape] = index
        if family in seen_family:
            union(index, seen_family[family])
        else:
            seen_family[family] = index
    members: dict[int, list[str]] = defaultdict(list)
    for index, request in enumerate(requests):
        members[find(index)].append(str(request.get("row_id", index)))
    ids = {root: digest(sorted(rows)) for root, rows in members.items()}
    return [ids[find(index)] for index in range(len(requests))]


def assign_groups_and_splits(requests: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Freeze grouping and split assignments using only design inputs."""

    prepared: list[dict[str, Any]] = []
    for index, original in enumerate(requests):
        request = copy.deepcopy(dict(original))
        request.setdefault("row_id", f"v3_case_{index:08d}")
        request.setdefault("domain_id", request.get("configuration", {}).get("domain_id", DOMAINS[0]))
        request.setdefault("mode", request.get("configuration", {}).get("impulse_type"))
        request.setdefault("topology_id", request.get("configuration", {}).get("topology_id"))
        request.setdefault("setup_family_id", request.get("setup", {}).get("setup_id", "UNSPECIFIED"))
        request["response_group_key"] = _response_group_identity(request)
        request["response_group_id"] = request["response_group_key"]
        request["setup_family_key"] = _setup_family_identity(request)
        prepared.append(request)
    groups = _union_find_groups(prepared)
    for request, group_id in zip(prepared, groups):
        request["group_id"] = group_id
        request["split"] = _stable_split(group_id)
        request["split_frozen"] = True
        request["split_audit"] = {
            "response_group_key": request["response_group_key"],
            "setup_family_key": request["setup_family_key"],
            "group_id": group_id,
            "split": request["split"],
            "frozen_before_labels": True,
        }
    return prepared


def _route_key(request: Mapping[str, Any]) -> str:
    return f"{request.get('domain_id')}::{request.get('mode')}::{request.get('topology_id')}"


def _route_stage_limits(
    values: Mapping[str, int] | None,
    *,
    default: int,
    minimum: int = 1,
    capacity: int,
    base: Mapping[str, int] | None = None,
) -> dict[str, int]:
    """Normalize optional per-route active prefixes.

    ``values`` is a patch over ``base``.  This lets a sparse route resume
    extend one route in a frozen design while leaving all other routes at
    their current learning-curve stage.  Route keys are the persisted
    ``domain::mode::topology`` strings, so the manifest is unambiguous and
    easy to audit from another process.
    """

    route_keys = {"::".join(route) for route in ROUTES}
    try:
        normalized = {key: int(default) for key in sorted(route_keys)}
        if base is not None:
            for raw_key, raw_value in base.items():
                key = str(raw_key)
                if key not in route_keys:
                    raise ValueError(f"Unknown route stage key: {key}")
                normalized[key] = int(raw_value)
        if values is not None:
            for raw_key, raw_value in values.items():
                key = str(raw_key)
                if key not in route_keys:
                    raise ValueError(f"Unknown route stage key: {key}")
                normalized[key] = int(raw_value)
    except (AttributeError, TypeError, ValueError) as exc:
        if isinstance(exc, ValueError):
            raise
        raise ValueError("route_stage_limits must be a mapping of route keys to integer prefixes") from exc
    for key, limit in normalized.items():
        if limit < int(minimum) or limit > int(capacity):
            raise ValueError(f"route stage for {key} must be between {minimum} and {capacity}")
    return normalized


def _default_stage_values(profile: Any) -> list[int]:
    lo, hi = int(getattr(profile, "stages_min", 2)), int(getattr(profile, "stages_max", 15))
    # The design contract covers the complete approved stage domain.  The
    # sampler below walks this list with step five, coprime to 14, so each
    # route visits every stage before repeating.
    return list(range(lo, hi + 1))


@lru_cache(maxsize=2)
def _phase_a_rare_reference(mode: str) -> dict[str, Any]:
    """Load the reviewed Phase A rare-pass fixture without editing it."""

    filename = "LI_rare_timing_pass_recommendation.json" if mode == "LI" else "SI_recommendation.json"
    path = Path(__file__).resolve().parents[1] / "powernext" / "optimizer" / "examples" / filename
    data = json.loads(path.read_text(encoding="utf-8"))
    request = data.get("request", {})
    best = data.get("best_configuration") or {}
    configuration = dict(best.get("configuration") or {})
    if mode == "LI":
        # The recommendation is the reviewed N=7, Rf=30, Rt=180 pass.
        expected = {"stages": 7, "front_per_stage_ohm": 30, "tail_per_stage_ohm": 180}
    else:
        # The SI base recommendation is the reviewed N=9, Rf=3700, Rt=5000 pass.
        expected = {"stages": 9, "front_per_stage_ohm": 3700, "tail_per_stage_ohm": 5000}
    configuration.update(expected)
    configuration["impulse_type"] = mode
    configuration.setdefault("polarity", 1)
    configuration.setdefault("stage_charge_V", 150_000.0)
    setup = dict(request.get("setup") or data.get("setup") or {})
    return {
        "configuration": configuration,
        "setup": setup,
        "target_crest_V": float(request.get("target_crest_V") or (1_000_000.0 if mode == "LI" else 1_300_000.0)),
        "source_path": path.relative_to(Path(__file__).resolve().parents[1]).as_posix(),
        "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _rare_setup(reference: Mapping[str, Any], mode: str, offset: int, route_index: int) -> tuple[dict[str, Any], str]:
    """Return the actual rare-pass setup and bounded C/L neighbours."""

    setup = copy.deepcopy(dict(reference["setup"]))
    if offset:
        # Small bounded perturbations retain the Phase A operating region while
        # exercising capacitance and inductance sensitivity independently.
        cap_scale = (0.95, 1.05, 1.10, 0.90)[(offset + route_index) % 4]
        divider_scale = (1.05, 0.95, 1.10, 0.90)[(offset * 2 + route_index) % 4]
        stray_scale = (1.10, 0.90, 1.05, 0.95)[(offset + 2 * route_index) % 4]
        inductance_scale = (0.90, 1.10, 0.85, 1.15)[(offset + route_index) % 4]
        setup["dut_capacitance_F"] = float(setup.get("dut_capacitance_F", 0.0)) * cap_scale
        setup["divider_capacitance_F"] = float(setup.get("divider_capacitance_F", 0.0)) * divider_scale
        setup["stray_capacitance_F"] = float(setup.get("stray_capacitance_F", 0.0)) * stray_scale
        setup["loop_inductance_H"] = float(setup.get("loop_inductance_H", 0.0)) * inductance_scale
        setup["loop_resistance_ohm"] = float(setup.get("loop_resistance_ohm", 0.0)) * (0.8 + 0.1 * ((offset + route_index) % 5))
        setup["setup_id"] = f"PHASE_A_RARE_{mode}_{route_index}_{offset}"
    else:
        setup["setup_id"] = str(setup.get("setup_id") or f"PHASE_A_RARE_{mode}_BASE")
    return setup, f"PHASE_A_RARE_{mode}_{route_index}_{offset}"


def _rare_spec(reference: Mapping[str, Any], mode: str, offset: int) -> tuple[int, float, float, float]:
    base = reference["configuration"]
    if mode == "LI":
        nearby = ((7, 30.0, 180.0, float(base.get("stage_charge_V", 137_978.31708404465))),
                  (6, 46.0, 180.0, 130_000.0),
                  (8, 30.0, 520.0, 145_000.0),
                  (7, 46.0, 180.0, 155_000.0))
    else:
        nearby = ((9, 3700.0, 5000.0, float(base.get("stage_charge_V", 164_366.29423280785))),
                  (8, 3700.0, 5000.0, 150_000.0),
                  (10, 5000.0, 5000.0, 175_000.0),
                  (9, 3700.0, 3700.0, 165_000.0))
    return nearby[offset % len(nearby)]


def iter_design_requests(*, target_per_route: int = DEFAULT_TARGET_PER_ROUTE, seed: int = DEFAULT_SEED, learning_curve_capacity_per_route: int | None = None) -> Iterator[dict[str, Any]]:
    """Yield deterministic, input-only requests for every approved route.

    The generator deliberately does not call the physics API.  This makes the
    design, split freeze, and restart manifest cheap to inspect before a large
    simulation run is authorized.
    """

    if type(target_per_route) is not int or target_per_route < 1:
        raise ValueError("target_per_route must be a positive integer")
    capacity = target_per_route if learning_curve_capacity_per_route is None else learning_curve_capacity_per_route
    if type(capacity) is not int or capacity < target_per_route:
        raise ValueError("learning_curve_capacity_per_route must be >= target_per_route")
    catalog = _network_catalog(4)
    catalog_buckets = _catalog_by_modules(catalog)
    rng = random.Random(seed)
    row_index = 0
    for route_index, (domain_id, mode, topology_id) in enumerate(ROUTES):
        profile = _profile(domain_id)
        stage_values = _default_stage_values(profile)
        setup_cache: dict[tuple[int, bool, str], tuple[dict[str, Any], str]] = {}

        def get_setup(local_index: int, *, boundary: bool = False, boundary_variant: str = "low") -> tuple[dict[str, Any], str]:
            # A fixed setup family intentionally serves several configurations
            # so the family-aware split has a meaningful held-out unit.  Each
            # family is generated once from a local deterministic stream and
            # then copied into every request that belongs to it.
            slot = local_index if boundary else local_index // 8
            key = (slot, boundary, boundary_variant)
            if key not in setup_cache:
                family_seed = seed + route_index * 1_000_003 + slot * 9_973 + (1 if boundary else 0)
                setup_cache[key] = _setup_for(random.Random(family_seed), route_index * 100_000 + slot, boundary=boundary, boundary_variant=boundary_variant)
            return copy.deepcopy(setup_cache[key][0]), setup_cache[key][1]

        rare_reference = _phase_a_rare_reference(mode)

        for local_index in range(capacity):
            # The first target rows form the initial screen.  Remaining rows
            # are a deterministic extension for the learning curve.
            case_mod = local_index % 32
            if case_mod == 0:
                kind = "boundary_low_capacitance"
                stages = stage_values[0]
                charge = 20_000.0
                front = 30.0 if mode == "LI" else 3_700.0
                tail = 180.0 if mode == "LI" else 5_000.0
                setup, family_id = get_setup(local_index, boundary=True, boundary_variant="low")
                boundary_variant = "low"
            elif case_mod == 1:
                kind = "boundary_high_capacitance"
                stages = stage_values[-1]
                charge = float(getattr(profile, "stage_charge_max_V", 200_000.0))
                front = 5_000.0 if mode == "SI" else 520.0
                tail = 5_000.0 if mode == "SI" else 520.0
                setup, family_id = get_setup(local_index, boundary=True, boundary_variant="high")
                boundary_variant = "high"
            elif case_mod in (2, 3, 4) and local_index < 256:
                kind = "rare_feasible_neighborhood"
                rare_offset = (local_index // 32) * 3 + case_mod - 2
                stages, front, tail, charge = _rare_spec(rare_reference, mode, rare_offset)
                setup, family_id = _rare_setup(rare_reference, mode, rare_offset, route_index)
                # Keep deliberately related perturbations together. These are
                # prior known regression regions, not an unseen benchmark.
                family_id = f"KNOWN_PHASE_A_{mode}_NEIGHBORHOOD"
                if rare_offset:
                    rare_rng = random.Random(seed + route_index*100003 + rare_offset*1009)
                    for key in ("dut_capacitance_F", "divider_capacitance_F", "stray_capacitance_F", "loop_inductance_H"):
                        setup[key] *= rare_rng.uniform(.97, 1.03)
                boundary_variant = None
            else:
                kind = "broad_log_resistance" if case_mod % 2 else "inverse_guided_probe"
                stages = stage_values[(local_index * 5 + route_index) % len(stage_values)]
                charge = float(rng.choice([40_000, 60_000, 80_000, 100_000, 120_000, 150_000, 180_000, 200_000]))
                setup, family_id = get_setup(local_index)
                if kind == "broad_log_resistance":
                    front = math.exp(rng.uniform(math.log(7.5), math.log(20000.)))
                    tail = math.exp(rng.uniform(math.log(7.5), math.log(20000.)))
                else:
                    # Approximate inverse estimates guide input coverage only.
                    # They are never labels or proof of waveform compliance.
                    cl = sum(setup[key] for key in ("dut_capacitance_F", "divider_capacitance_F", "stray_capacitance_F"))
                    if setup["basic_coverage_assumption"] == "ADDITIONAL_DISJOINT":
                        cl += float(profile.basic_load_capacitance_F)
                    cg = float(profile.stage_capacitance_F) / stages
                    front_target = rng.choice([.84, 1.2, 1.56])*1e-6 if mode=="LI" else rng.choice([200.,250.,300.])*1e-6
                    tail_target = rng.choice([40.,50.,60.])*1e-6 if mode=="LI" else rng.choice([1000.,2500.,4000.])*1e-6
                    front = max(7.5,front_target/(1.67*cl*stages)-setup.get("loop_resistance_ohm",0.)/stages)
                    tail = tail_target/(.693*(cg+cl)*stages)
                    front *= math.exp(rng.uniform(-.9,.9))
                    tail *= math.exp(rng.uniform(-.5,.5))
                boundary_variant = None
            # Front and tail are independently stratified by module count and
            # log-resistance.  Their indices deliberately use different
            # coprime strides so pairs are not adjacent catalogue entries.
            if kind == "rare_feasible_neighborhood":
                front_modules = tail_modules = 1
            else:
                front_modules = rng.randint(1,4)
                tail_modules = rng.randint(1,4)
            front_network, front_record = _select_network(
                catalog_buckets,
                desired_ohm=front,
                module_count=front_modules,
                independent_index=(0 if kind == "rare_feasible_neighborhood" else local_index * 17 + route_index * 19 + 1),
            )
            tail_network, tail_record = _select_network(
                catalog_buckets,
                desired_ohm=tail,
                module_count=tail_modules,
                independent_index=(0 if kind == "rare_feasible_neighborhood" else local_index * 23 + route_index * 29 + 7),
            )
            front_equivalent = _network_equivalent(front_network, front)
            tail_equivalent = _network_equivalent(tail_network, tail)
            # Numeric equivalents are authoritative in the request so the
            # physics API can reject any inconsistent or unsupported recipe.
            configuration = {
                "impulse_type": mode,
                "stages": int(stages),
                "stage_charge_V": float(charge),
                "front_per_stage_ohm": float(front_equivalent),
                "tail_per_stage_ohm": float(tail_equivalent),
                "topology_id": topology_id,
                "polarity": 1 if local_index % 2 == 0 else -1,
                "front_network": front_network,
                "tail_network": tail_network,
            }
            target_grid = [50_000.0, 75_000.0, 100_000.0, 150_000.0, 250_000.0, 400_000.0, 600_000.0, 800_000.0, 1_000_000.0, 1_300_000.0, 1_400_000.0, 1_600_000.0, 1_800_000.0, 2_000_000.0, 2_200_000.0, 2_400_000.0]
            target = target_grid[(local_index * 11 + route_index * 13 + (0 if mode == "LI" else 5)) % len(target_grid)]
            # Keep targets independent of labels, with a few out-of-domain
            # requests retained as explicit invalid/unsupported fixtures.
            if case_mod == 31:
                target = 5_000_000.0
                kind = "infeasible_target_boundary"
            request = {
                "row_id": f"v3_case_{row_index:08d}",
                "domain_id": domain_id,
                "mode": mode,
                "topology_id": topology_id,
                "configuration": configuration,
                "setup": setup,
                "setup_family_id": family_id,
                "case_kind": kind,
                "target_crest_V": target,
                "requested_front_per_stage_ohm": float(front),
                "requested_tail_per_stage_ohm": float(tail),
                "actual_front_per_stage_ohm": float(front_equivalent),
                "actual_tail_per_stage_ohm": float(tail_equivalent),
                "recipe_family": f"front_modules_{front_record.get('module_count') or front_modules}_tail_modules_{tail_record.get('module_count') or tail_modules}",
                "recipe_family_index": 1 + (local_index % 4),
                "front_network_family_id": str(front_record.get("family_id", front_record.get("network_id", "front"))),
                "tail_network_family_id": str(tail_record.get("family_id", tail_record.get("network_id", "tail"))),
                "front_network_module_count": front_record.get("module_count", front_modules),
                "tail_network_module_count": tail_record.get("module_count", tail_modules),
                "boundary_capacitance_variant": boundary_variant,
                "rare_reference": ({
                    "source_path": rare_reference["source_path"],
                    "source_sha256": rare_reference["source_sha256"],
                    "base_configuration": rare_reference["configuration"],
                } if kind == "rare_feasible_neighborhood" else None),
                "learning_curve_stage": (
                    target_per_route
                    if local_index < target_per_route
                    else min(target_per_route * 2, capacity)
                    if local_index < target_per_route * 2
                    else capacity
                ),
                "design_local_index": local_index,
                "design_seed": seed,
                "design_route_index": route_index,
            }
            yield request
            row_index += 1


def design_requests(*, target_per_route: int = DEFAULT_TARGET_PER_ROUTE, seed: int = DEFAULT_SEED, learning_curve_capacity_per_route: int | None = None, freeze_splits: bool = True) -> list[dict[str, Any]]:
    requests = list(iter_design_requests(target_per_route=target_per_route, seed=seed, learning_curve_capacity_per_route=learning_curve_capacity_per_route))
    return assign_groups_and_splits(requests) if freeze_splits else requests


def _count_routes(requests: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for request in requests:
        counts[_route_key(request)] += 1
    return dict(sorted(counts.items()))


@lru_cache(maxsize=1)
def _provenance() -> dict[str, Any]:
    result: dict[str, Any] = {"dataset_module": SCHEMA_VERSION}
    try:
        physics = importlib.import_module("powernext_v3.physics")
        fingerprint = physics.source_fingerprint() if hasattr(physics, "source_fingerprint") else None
        result["physics_source_fingerprint"] = fingerprint
        result["physics_module"] = getattr(physics, "__version__", "unknown")
    except Exception as exc:
        result["physics_api_status"] = "UNAVAILABLE"
        result["physics_api_error"] = f"{type(exc).__name__}: {exc}"
    try:
        profiles = importlib.import_module("powernext_v3.profiles")
        result["profiles_module"] = getattr(profiles, "__file__", None)
        result["profile_ids"] = {domain: getattr(profiles.get_profile(domain), "profile_id", None) for domain in DOMAINS}
    except Exception as exc:
        result["profiles_api_status"] = "UNAVAILABLE"
        result["profiles_api_error"] = f"{type(exc).__name__}: {exc}"
    try:
        networks = importlib.import_module("powernext_v3.networks")
        result["networks_module"] = getattr(networks, "__file__", None)
        if hasattr(networks, "enumerate_networks"):
            recipes = tuple(networks.enumerate_networks(max_modules=4))
            module_counts = Counter(int(getattr(recipe, "module_count")) for recipe in recipes if getattr(recipe, "module_count", None) is not None)
            result["network_catalog"] = {
                "api": "powernext_v3.networks.enumerate_networks",
                "max_modules": 4,
                "recipe_count": len(recipes),
                "module_counts": dict(sorted(module_counts.items())),
                "fallback_single_resistor": False,
            }
    except Exception as exc:
        result["networks_api_status"] = "UNAVAILABLE"
        result["networks_api_error"] = f"{type(exc).__name__}: {exc}"
    return result


def api_status() -> dict[str, Any]:
    """Return a read-only readiness snapshot for the v3 collaborators."""

    status: dict[str, Any] = {"schema_version": SCHEMA_VERSION, "checked_at": _utc_now(), "routes": [list(route) for route in ROUTES]}
    for name, required in (("profiles", ("get_profile",)), ("physics", ("simulate",)), ("networks", ("enumerate_networks",))):
        try:
            module = importlib.import_module(f"powernext_v3.{name}")
            status[name] = {"available": all(hasattr(module, attr) for attr in required), "module": getattr(module, "__file__", None), "missing": [attr for attr in required if not hasattr(module, attr)]}
        except Exception as exc:
            status[name] = {"available": False, "error": f"{type(exc).__name__}: {exc}"}
    try:
        features = importlib.import_module("powernext_v3.features")
        status["features"] = {"available": hasattr(features, "feature_rows"), "module": getattr(features, "__file__", None)}
    except Exception as exc:
        status["features"] = {"available": False, "error": f"{type(exc).__name__}: {exc}"}
    status["ready_for_small_fixture"] = bool(status.get("profiles", {}).get("available") and status.get("physics", {}).get("available"))
    status["ready_for_generation"] = all(status.get(name, {}).get("available") for name in ("profiles", "physics", "networks", "features"))
    return status


@lru_cache(maxsize=1)
def _source_hashes() -> dict[str, str]:
    result: dict[str, str] = {}
    for module_name in ("profiles", "physics", "networks", "features", "dataset"):
        try:
            module = importlib.import_module(f"powernext_v3.{module_name}")
            path = Path(module.__file__ or "")
            if path.exists():
                result[f"powernext_v3/{module_name}.py"] = hashlib.sha256(path.read_bytes()).hexdigest()
        except Exception:
            continue
    return result


def _ensure_api_ready() -> None:
    status = api_status()
    missing = [name for name in ("profiles", "physics", "networks", "features") if not status.get(name, {}).get("available")]
    if missing:
        raise RuntimeError("v3 generation APIs are not ready; generation was not launched (missing: " + ", ".join(missing) + ")")


def _request_input_hash(request: Mapping[str, Any]) -> str:
    return digest({key: request.get(key) for key in ("domain_id", "mode", "topology_id", "configuration", "setup", "setup_family_id", "case_kind", "target_crest_V")})


def _extract_metric(metrics: Mapping[str, Any], metadata: Mapping[str, Any], names: Sequence[str], *, scale: float = 1.0) -> float | None:
    for name in names:
        value = metrics.get(name, metadata.get(name))
        if isinstance(value, (int, float)) and math.isfinite(float(value)):
            return float(value) * scale
    return None


def _extract_result(result: Any, request: Mapping[str, Any], elapsed: float) -> tuple[dict[str, Any], dict[str, Any] | None]:
    metadata = dict(getattr(result, "metadata", {}) or {})
    arrays = getattr(result, "arrays", None)
    metrics = metadata.get("metrics", {}) if isinstance(metadata.get("metrics", {}), Mapping) else {}
    mode = request["mode"]
    gain = _extract_metric(metrics, metadata, ("gain", "voltage_gain"))
    if gain is None:
        gain = _extract_metric({}, metadata.get("derived", {}) if isinstance(metadata.get("derived"), Mapping) else {}, ("gain", "voltage_gain"))
    if gain is None:
        gain = _extract_metric({}, metadata, ("voltage_gain",))
    front = _extract_metric(metrics, metadata, (("T1_s", "front_us") if mode == "LI" else ("Tp_s", "front_us")), scale=1e6 if "front_us" not in metrics else 1.0)
    tail = _extract_metric(metrics, metadata, (("T2_s", "tail_us")), scale=1e6 if "tail_us" not in metrics else 1.0)
    crest = _extract_metric(metrics, metadata, ("crest_magnitude_V", "raw_crest_magnitude_V", "crest_V"))
    numeric_status = metadata.get("numeric_status")
    waveform_status = metrics.get("waveform_status", metadata.get("waveform_status"))
    # A complete pair of explicit simulator status markers is required.  A
    # missing status is an audit failure, even when scalar-looking metrics are
    # present, so an incomplete adapter cannot silently become training data.
    valid = numeric_status == "VALID" and waveform_status == "VALID_CLEAN_FULL_IMPULSE"
    labels_valid = valid and gain is not None and front is not None and tail is not None
    compact_metrics = {
        "gain": gain,
        "front_us": front,
        "tail_us": tail,
        "crest_V": crest,
        "numeric_status": numeric_status,
        "waveform_status": waveform_status,
        "compliance_status": metrics.get("compliance_status", metadata.get("compliance_status")),
        "energy_balance_relative_error": metadata.get("energy_balance_relative_error"),
        "simulation_seconds": elapsed,
    }
    row = {
        "status": "SIMULATED",
        "regression_eligible": bool(labels_valid),
        "gain": gain if labels_valid else None,
        "front_us": front if labels_valid else None,
        "tail_us": tail if labels_valid else None,
        "metrics": compact_metrics,
        "simulation_metadata": {
            "schema_version": metadata.get("schema_version"),
            "model_version": metadata.get("model_version"),
            "input_sha256": metadata.get("input_sha256"),
            "evidence_domain": metadata.get("evidence_domain"),
            "profile_id": metadata.get("profile_id"),
            "physics_domain_id": metadata.get("domain_id", request.get("domain_id")),
        },
    }
    return row, arrays if isinstance(arrays, Mapping) else None


def _simulate_request(request: Mapping[str, Any], n_points: int) -> tuple[dict[str, Any], dict[str, Any] | None]:
    started = time.perf_counter()
    base = {
        "row_id": request["row_id"],
        "domain_id": request["domain_id"],
        "mode": request["mode"],
        "topology": request["topology_id"],
        "topology_id": request["topology_id"],
        "configuration": copy.deepcopy(request["configuration"]),
        "setup": copy.deepcopy(request["setup"]),
        "target_crest_V": request.get("target_crest_V"),
        "setup_family_id": request.get("setup_family_id"),
        "case_kind": request.get("case_kind"),
        "group_id": request.get("group_id"),
        "response_group_id": request.get("response_group_id"),
        "response_group_key": request.get("response_group_key", request.get("response_group_id")),
        "setup_family_key": request.get("setup_family_key"),
        "split": request.get("split"),
        "split_frozen": True,
        "split_audit": copy.deepcopy(request.get("split_audit")),
        "input_sha256": _request_input_hash(request),
        "regression_eligible": False,
        "gain": None,
        "front_us": None,
        "tail_us": None,
        "features": None,
        "metrics": {},
        "provenance": _provenance(),
        "waveform_path": None,
        "waveform_sha256": None,
        "error": None,
    }
    target = request.get("target_crest_V")
    if isinstance(target, (int, float)) and (float(target) < 50_000.0 or float(target) > 2_400_000.0):
        # Keep explicit out-of-design target probes as auditable unsupported
        # rows.  They must never become labels merely because the reduced
        # physics graph can numerically integrate them.
        base.update({
            "status": "INVALID_OR_UNSUPPORTED",
            "error": {"type": "DesignDomainError", "code": "TARGET_OUTSIDE_PHASE_B_RANGE", "message": "target_crest_V must be between 50 kV and 2.4 MV"},
            "metrics": {"numeric_status": None, "waveform_status": None, "target_range_status": "OUTSIDE_PHASE_B_RANGE", "simulation_seconds": 0.0},
        })
        return base, None
    features = importlib.import_module("powernext_v3.features")
    feature_rows = getattr(features, "feature_rows")
    try:
        computed = feature_rows([request["configuration"]], request["setup"], request["domain_id"])
        base["features"] = computed[0] if computed else None
    except (ValueError, KeyError, TypeError) as feature_exc:
        # Malformed design inputs are retained as non-eligible rows.  Other
        # feature failures propagate so a broken API cannot be marked complete.
        base["features"] = None
        base["feature_error"] = {"type": type(feature_exc).__name__, "message": str(feature_exc)}
    physics = importlib.import_module("powernext_v3.physics")
    try:
        result = physics.simulate(request["configuration"], request["setup"], domain_id=request["domain_id"], target_crest_V=request.get("target_crest_V"), n_points=n_points, solver="modal")
    except Exception as exc:
        # PhysicsError and explicitly unsupported graph cases are data: retain
        # the input row with null labels.  Every other exception propagates to
        # the parent process, which marks the manifest FAILED.
        code = getattr(exc, "code", None)
        if not code:
            raise
        base.update({"status": "INVALID_OR_UNSUPPORTED", "error": {"type": type(exc).__name__, "code": code, "message": str(exc)}, "metrics": {"simulation_seconds": time.perf_counter() - started, "numeric_status": None, "waveform_status": None}})
        return base, None
    enriched, arrays = _extract_result(result, request, time.perf_counter() - started)
    if base.get("features") is None:
        enriched["regression_eligible"] = False
        enriched["gain"] = None
        enriched["front_us"] = None
        enriched["tail_us"] = None
    base.update(enriched)
    return base, arrays


def _save_waveform(output: Path, row: dict[str, Any], arrays: Mapping[str, Any]) -> None:
    waveform_dir = output / "waveforms"
    waveform_dir.mkdir(parents=True, exist_ok=True)
    stem = waveform_dir / str(row["row_id"])
    import numpy as np
    np.savez_compressed(str(stem) + ".npz", **{str(k): np.asarray(v) for k, v in arrays.items()})
    path = Path(str(stem) + ".npz")
    row["waveform_path"] = path.relative_to(output).as_posix()
    row["waveform_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()


def _existing_rows(path: Path) -> dict[str, dict[str, Any]]:
    rows_path = path / "rows.jsonl"
    if not rows_path.exists():
        return {}
    rows: dict[str, dict[str, Any]] = {}
    with rows_path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid rows.jsonl at line {line_number}") from exc
            row_id = row.get("row_id")
            if not row_id:
                raise ValueError(f"Missing row_id at line {line_number}")
            rows[str(row_id)] = row
    return rows


def _manifest_for(
    requests: Sequence[Mapping[str, Any]],
    plan: DatasetPlan,
    route_stage_limits: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    limits = _route_stage_limits(
        route_stage_limits,
        default=int(plan.active_per_route or plan.initial_attempts_per_route or plan.target_per_route),
        minimum=plan.target_per_route,
        capacity=plan.learning_curve_capacity_per_route,
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "design_schema_version": DESIGN_SCHEMA_VERSION,
        "dataset_id": "v3_" + digest({"seed": plan.seed, "requests": [request.get("row_id") for request in requests], "plan": plan.as_dict(), "route_stage_limits": limits})[:20],
        "purpose": "PHASE_B_INDEPENDENT_SIMULATION_DATA",
        "status": "IN_PROGRESS",
        "created_at": _utc_now(),
        "plan": plan.as_dict(),
        "routes": [list(route) for route in ROUTES],
        "route_request_counts": _count_routes(requests),
        "active_route_request_counts": _count_routes(request for request in requests if int(request.get("design_local_index", 0)) < limits[_route_key(request)]),
        "active_per_route": plan.active_per_route,
        "route_stage_limits": limits,
        "initial_target_per_route": plan.target_per_route,
        "learning_curve_capacity_per_route": plan.learning_curve_capacity_per_route,
        "initial_attempts_per_route": plan.initial_attempts_per_route,
        "learning_curve_stages": [plan.target_per_route, min(plan.target_per_route * 2, plan.learning_curve_capacity_per_route), plan.learning_curve_capacity_per_route],
        "eligible_route_gate": {"target_per_route": plan.target_per_route, "adequate": None, "shortfall_by_route": None, "capacity_extension_available": any(limit < plan.learning_curve_capacity_per_route for limit in limits.values())},
        "design_sha256": digest(requests),
        "source_hashes": _source_hashes(),
        "provenance": _provenance(),
        "split_rule": "Input-only connected components over normalized response_group_key and normalized setup_family_key; frozen before labels/enrichment.",
        "label_rule": "Only numeric_status=VALID and waveform_status=VALID_CLEAN_FULL_IMPULSE rows with complete metrics are regression eligible; invalid or unsupported rows retain null labels.",
        "waveform_policy": plan.waveform_policy,
        "observed_data_used_for_training": False,
    }


def _write_design(path: Path, requests: Sequence[Mapping[str, Any]], manifest: Mapping[str, Any]) -> None:
    path.mkdir(parents=True, exist_ok=True)
    design_path = path / "design.jsonl"
    if design_path.exists():
        existing_hash = hashlib.sha256(design_path.read_bytes()).hexdigest()
        expected = str(manifest.get("design_file_sha256", existing_hash))
        if expected != existing_hash:
            raise FileExistsError("Immutable design.jsonl already exists with different content")
        return
    temporary = design_path.with_suffix(".jsonl.tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        for request in requests:
            stream.write(_json_line(request) + "\n")
    os.replace(temporary, design_path)
    if isinstance(manifest, dict):
        manifest["design_file_sha256"] = hashlib.sha256(design_path.read_bytes()).hexdigest()


def _route_eligible_counts(rows: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    # A repeated amplitude/polarity/recipe row can be a valid simulation while
    # still representing the same independent response shape.  Route gates
    # therefore count unique normalized response keys; row-level counts remain
    # available in the manifest for audit and learning-curve diagnostics.
    shapes: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        if row.get("regression_eligible"):
            route = f"{row.get('domain_id')}::{row.get('mode')}::{row.get('topology_id', row.get('topology'))}"
            shape = row.get("response_group_key", row.get("response_group_id"))
            if shape is None:
                shape = row.get("input_sha256", row.get("row_id"))
            shapes[route].add(str(shape))
    return {route: len(values) for route, values in sorted(shapes.items())}


def generate_dataset(output: str | Path, *, target_per_route: int = DEFAULT_TARGET_PER_ROUTE, learning_curve_capacity_per_route: int = DEFAULT_CAPACITY_PER_ROUTE, stage_per_route: int | None = None, initial_attempts_per_route: int | None = None, route_stage_limits: Mapping[str, int] | None = None, seed: int = DEFAULT_SEED, workers: int = DEFAULT_WORKERS, n_points: int = DEFAULT_N_POINTS, waveform_policy: str = "representative", heartbeat_every: int = 50, representative_waveforms_per_route: int = MAX_REPRESENTATIVE_WAVEFORMS_PER_ROUTE, progress_callback: Callable[[dict[str, Any]], None] | None = None) -> dict[str, Any]:
    """Generate or resume an immutable append-only v3 dataset.

    Existing completed rows are never recomputed or overwritten.  A matching
    in-progress manifest can be resumed; a destination with incompatible
    design settings is rejected before a simulator is started.
    """

    _ensure_api_ready()
    if stage_per_route is not None and route_stage_limits is not None:
        raise ValueError("stage_per_route and route_stage_limits are mutually exclusive")
    plan = DatasetPlan(
        target_per_route=target_per_route,
        learning_curve_capacity_per_route=learning_curve_capacity_per_route,
        seed=seed,
        workers=max(1, min(int(workers), os.cpu_count() or 1)),
        n_points=n_points,
        waveform_policy=waveform_policy,
        heartbeat_every=heartbeat_every,
        active_per_route=stage_per_route,
        representative_waveforms_per_route=representative_waveforms_per_route,
        initial_attempts_per_route=initial_attempts_per_route,
    )
    output_path = Path(output)
    requests = design_requests(target_per_route=plan.target_per_route, seed=plan.seed, learning_curve_capacity_per_route=plan.learning_curve_capacity_per_route)
    requested_limits = _route_stage_limits(
        route_stage_limits,
        default=int(plan.active_per_route or plan.initial_attempts_per_route or plan.target_per_route),
        minimum=plan.target_per_route,
        capacity=plan.learning_curve_capacity_per_route,
    )
    if route_stage_limits is not None:
        plan = replace(plan, active_per_route=max(requested_limits.values()))
    expected = _manifest_for(requests, plan, requested_limits)
    output_path.mkdir(parents=True, exist_ok=True)
    manifest_path = output_path / "manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        existing_plan = dict(manifest.get("plan", {}))
        existing_active = int(existing_plan.get("active_per_route", existing_plan.get("target_per_route", plan.target_per_route)))
        existing_limits = _route_stage_limits(
            manifest.get("route_stage_limits"),
            default=existing_active,
            minimum=plan.target_per_route,
            capacity=plan.learning_curve_capacity_per_route,
        )
        # Omitting --stage-per-route on a resume means "continue the current
        # frozen prefix".  An explicit smaller stage remains an error.
        if stage_per_route is None and route_stage_limits is None:
            plan = replace(plan, active_per_route=max(existing_limits.values()))
            requested_limits = existing_limits
            expected = _manifest_for(requests, plan, requested_limits)
        elif route_stage_limits is not None:
            requested_limits = _route_stage_limits(
                route_stage_limits,
                default=int(plan.active_per_route or plan.initial_attempts_per_route or plan.target_per_route),
                minimum=plan.target_per_route,
                capacity=plan.learning_curve_capacity_per_route,
                base=existing_limits,
            )
            plan = replace(plan, active_per_route=max(requested_limits.values()))
            expected = _manifest_for(requests, plan, requested_limits)
        else:
            requested_limits = _route_stage_limits(
                None,
                default=int(plan.active_per_route or plan.initial_attempts_per_route or plan.target_per_route),
                minimum=plan.target_per_route,
                capacity=plan.learning_curve_capacity_per_route,
            )
            expected = _manifest_for(requests, plan, requested_limits)
        for key in ("schema_version", "design_sha256"):
            if manifest.get(key) != expected.get(key):
                raise ValueError(f"Existing dataset is immutable and does not match requested {key}")
        if manifest.get("source_hashes") != expected.get("source_hashes"):
            raise ValueError("Existing dataset is immutable and its source hashes do not match the current APIs")
        for key in ("target_per_route", "learning_curve_capacity_per_route", "seed", "n_points", "waveform_policy", "representative_waveforms_per_route", "initial_attempts_per_route"):
            if existing_plan.get(key) != expected["plan"].get(key):
                raise ValueError(f"Existing dataset is immutable and does not match requested plan field {key}")
        if any(requested_limits[key] < existing_limits[key] for key in requested_limits):
            raise ValueError("An immutable dataset cannot move a route's active learning-curve stage backwards")
        if any(requested_limits[key] > existing_limits[key] for key in requested_limits):
            manifest["plan"] = expected["plan"]
            manifest["active_per_route"] = expected["active_per_route"]
            manifest["plan"]["active_per_route"] = expected["plan"]["active_per_route"]
            manifest["active_route_request_counts"] = expected["active_route_request_counts"]
            manifest["route_stage_limits"] = expected["route_stage_limits"]
            manifest["learning_curve_stages"] = expected["learning_curve_stages"]
    else:
        manifest = expected
    # Persist the normalized route map on every resume, including an old
    # manifest created before sparse route staging was introduced.  The map
    # is audit metadata and does not alter the frozen design or existing rows.
    manifest["route_stage_limits"] = dict(requested_limits)
    manifest["active_per_route"] = plan.active_per_route
    manifest["active_route_request_counts"] = expected["active_route_request_counts"]
    _write_design(output_path, requests, manifest)
    manifest["status"] = "IN_PROGRESS"
    _json_dump(manifest_path, manifest)
    existing = _existing_rows(output_path)
    active_requests = [request for request in requests if int(request.get("design_local_index", 0)) < requested_limits[_route_key(request)]]
    request_by_id = {request["row_id"]: request for request in active_requests}
    unknown = set(existing) - set(request_by_id)
    if unknown:
        raise ValueError(f"Existing rows are not part of the frozen design: {sorted(unknown)[:3]}")
    pending = [request for request in active_requests if request["row_id"] not in existing]
    rows_path = output_path / "rows.jsonl"
    output_path.joinpath("progress.json").write_text("", encoding="utf-8") if rows_path.exists() and rows_path.stat().st_size == 0 else None
    waveform_counts_by_route: Counter[str] = Counter()
    waveform_strata: set[str] = set()
    for saved in existing.values():
        if not saved.get("waveform_path"):
            continue
        route = f"{saved.get('domain_id')}::{saved.get('mode')}::{saved.get('topology_id', saved.get('topology'))}"
        waveform_counts_by_route[route] += 1
        waveform_strata.add(f"{route}::{saved.get('case_kind', 'unknown')}")
    eligible = [row for row in existing.values() if row.get("regression_eligible")]
    completed = len(existing)
    total = len(active_requests)
    active_limits = dict(requested_limits)

    def completion_status() -> str:
        if completed < total:
            return "IN_PROGRESS"
        return "FULL_DESIGN_COMPLETE" if all(limit >= plan.learning_curve_capacity_per_route for limit in active_limits.values()) else "STAGE_COMPLETE"

    def heartbeat(force: bool = False) -> None:
        if not force and completed % plan.heartbeat_every:
            return
        payload = {"dataset_id": manifest["dataset_id"], "timestamp": _utc_now(), "completed": completed, "total": total, "pending": total - completed, "regression_eligible": sum(_route_eligible_counts(existing.values()).values()), "regression_eligible_rows": len(eligible), "route_eligible_counts": _route_eligible_counts(existing.values()), "status": completion_status()}
        _json_dump(output_path / "progress.json", payload)
        if progress_callback:
            progress_callback(payload)
        print(f"[{payload['timestamp']}] v3 dataset {completed}/{total}; eligible={len(eligible)}", flush=True)

    heartbeat(force=True)
    executor: ProcessPoolExecutor | None = None
    try:
        if pending:
            worker_count = plan.workers
            with rows_path.open("a", encoding="utf-8", newline="\n") as stream:
                def consume(request: Mapping[str, Any], result: tuple[dict[str, Any], dict[str, Any] | None]) -> None:
                    nonlocal completed
                    row, arrays = result
                    route = f"{row.get('domain_id')}::{row.get('mode')}::{row.get('topology_id', row.get('topology'))}"
                    stratum = f"{route}::{row.get('case_kind', 'unknown')}"
                    route_limit = plan.representative_waveforms_per_route
                    should_save = bool(arrays) and plan.waveform_policy == "all"
                    if arrays and plan.waveform_policy == "representative":
                        # At most a bounded number per route; save the first
                        # member of each case stratum to preserve coverage.
                        should_save = (
                            waveform_counts_by_route[route] < route_limit
                            and (stratum not in waveform_strata or waveform_counts_by_route[route] < min(route_limit, 8))
                        )
                    if arrays and plan.waveform_policy == "failure" and row.get("status") != "SIMULATED":
                        should_save = True
                    if should_save:
                        _save_waveform(output_path, row, arrays or {})
                        waveform_counts_by_route[route] += 1
                        waveform_strata.add(stratum)
                    stream.write(_json_line(row) + "\n")
                    stream.flush()
                    existing[str(row["row_id"])] = row
                    completed += 1
                    if row.get("regression_eligible"):
                        eligible.append(row)
                    heartbeat()

                if worker_count == 1:
                    for request in pending:
                        consume(request, _simulate_request(request, plan.n_points))
                else:
                    # ``executor.map`` can enqueue the whole 240k design and
                    # retain completed waveform arrays.  Keep only two worker
                    # batches in flight and release each result immediately.
                    executor = ProcessPoolExecutor(max_workers=worker_count)
                    pending_index = 0
                    next_to_write = 0
                    inflight: dict[Any, tuple[int, Mapping[str, Any]]] = {}
                    completed_results: dict[int, tuple[Mapping[str, Any], tuple[dict[str, Any], dict[str, Any] | None]]] = {}

                    def submit_next() -> bool:
                        nonlocal pending_index
                        if pending_index >= len(pending):
                            return False
                        request = pending[pending_index]
                        inflight[executor.submit(_simulate_request, request, plan.n_points)] = (pending_index, request)
                        pending_index += 1
                        return True

                    for _ in range(min(len(pending), worker_count * 2)):
                        submit_next()
                    while inflight:
                        done, _ = wait(tuple(inflight), return_when=FIRST_COMPLETED)
                        for future in done:
                            index, request = inflight.pop(future)
                            # Hold at most the bounded inflight batch, then
                            # emit strictly in frozen design order so a retry
                            # produces the same append-only rows hash.
                            completed_results[index] = (request, future.result())
                            submit_next()
                        while next_to_write in completed_results:
                            request, result = completed_results.pop(next_to_write)
                            consume(request, result)
                            next_to_write += 1
    except Exception as exc:
        manifest.update({
            "status": "FAILED",
            "failed_at": _utc_now(),
            "failure": {"type": type(exc).__name__, "message": str(exc)},
            "completed_rows": len(existing),
            "row_count": len(existing),
        })
        _json_dump(manifest_path, manifest)
        _json_dump(output_path / "progress.json", {
            "dataset_id": manifest["dataset_id"],
            "timestamp": _utc_now(),
            "completed": completed,
            "total": total,
            "pending": total - completed,
            "status": "FAILED",
            "failure": manifest["failure"],
        })
        raise
    finally:
        if executor is not None:
            executor.shutdown(wait=True)
    heartbeat(force=True)
    rows = list(existing.values())
    route_counts = _route_eligible_counts(rows)
    shortfall = {
        f"{domain}::{mode}::{topology}": max(0, plan.target_per_route - route_counts.get(f"{domain}::{mode}::{topology}", 0))
        for domain, mode, topology in ROUTES
    }
    manifest.pop("failure", None)
    manifest.pop("failed_at", None)
    manifest.update({
        "status": completion_status(),
        "completed_rows": len(existing),
        "row_count": len(existing),
        "regression_eligible_count": sum(route_counts.values()),
        "regression_eligible_row_count": len(eligible),
        "route_eligible_counts": route_counts,
        "eligible_route_gate": {"target_per_route": plan.target_per_route, "shortfall_by_route": shortfall, "adequate": not any(shortfall.values()), "capacity_extension_available": any(limit < plan.learning_curve_capacity_per_route for limit in active_limits.values())},
        "route_stage_limits": active_limits,
        "status_counts": dict(sorted(Counter(str(row.get("status")) for row in rows).items())),
        "split_counts": dict(sorted(Counter(str(row.get("split")) for row in rows).items())),
        "rows_sha256": hashlib.sha256(rows_path.read_bytes()).hexdigest() if rows_path.exists() else None,
        "waveform_counts_by_route": dict(sorted(waveform_counts_by_route.items())),
        "waveform_representative_limit_per_route": plan.representative_waveforms_per_route,
        "completed_at": _utc_now() if len(existing) == total else None,
    })
    _json_dump(manifest_path, manifest)
    return manifest


# Short aliases used by callers familiar with the legacy generator.
generate = generate_dataset
design = design_requests


def _load_design(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def _parse_route_stage_limits(values: Sequence[str]) -> dict[str, int]:
    """Parse repeatable CLI values of the form ``domain::mode::topology=N``."""

    parsed: dict[str, int] = {}
    for value in values:
        route, separator, raw_limit = str(value).rpartition("=")
        if not separator or not route:
            raise ValueError(f"Invalid --route-stage-limit value {value!r}; expected route=N")
        try:
            parsed[route] = int(raw_limit)
        except ValueError as exc:
            raise ValueError(f"Invalid route stage prefix {raw_limit!r} in {value!r}") from exc
    return parsed


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    status = sub.add_parser("status", help="Inspect v3 API readiness")
    design_parser = sub.add_parser("design", help="Write input-only frozen design rows")
    design_parser.add_argument("--output", type=Path, required=True)
    design_parser.add_argument("--target-per-route", type=int, default=DEFAULT_TARGET_PER_ROUTE)
    design_parser.add_argument("--capacity-per-route", type=int, default=DEFAULT_CAPACITY_PER_ROUTE)
    design_parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    generate_parser = sub.add_parser("generate", help="Generate or resume physics-labelled rows")
    generate_parser.add_argument("--output", type=Path, required=True)
    generate_parser.add_argument("--target-per-route", type=int, default=DEFAULT_TARGET_PER_ROUTE)
    generate_parser.add_argument("--capacity-per-route", type=int, default=DEFAULT_CAPACITY_PER_ROUTE)
    generate_parser.add_argument("--stage-per-route", type=int, default=None, help="Active frozen-design prefix per route; defaults to the initial attempt stage")
    generate_parser.add_argument("--route-stage-limit", action="append", default=[], metavar="ROUTE=N", help="Extend selected frozen route prefixes without re-running other routes; repeatable")
    generate_parser.add_argument("--initial-attempts-per-route", type=int, default=None, help="Initial frozen-design prefix; defaults to target plus 20 percent")
    generate_parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    generate_parser.add_argument("--workers", type=int, default=DEFAULT_WORKERS)
    generate_parser.add_argument("--n-points", type=int, default=DEFAULT_N_POINTS)
    generate_parser.add_argument("--waveform-policy", choices=("none", "representative", "failure", "all"), default="representative")
    generate_parser.add_argument("--representative-waveforms-per-route", type=int, default=MAX_REPRESENTATIVE_WAVEFORMS_PER_ROUTE)
    generate_parser.add_argument("--heartbeat-every", type=int, default=50)
    args = parser.parse_args(argv)
    if args.command == "status":
        print(json.dumps(api_status(), indent=2, sort_keys=True))
        return 0
    if args.command == "design":
        requests = design_requests(target_per_route=args.target_per_route, seed=args.seed, learning_curve_capacity_per_route=args.capacity_per_route)
        plan = DatasetPlan(args.target_per_route, args.capacity_per_route, args.seed)
        manifest = _manifest_for(requests, plan)
        args.output.mkdir(parents=True, exist_ok=True)
        _write_design(args.output, requests, manifest)
        _json_dump(args.output / "manifest.json", manifest)
        print(json.dumps({"dataset_id": manifest["dataset_id"], "rows": len(requests), "routes": manifest["route_request_counts"]}, indent=2, sort_keys=True))
        return 0
    route_stage_limits = _parse_route_stage_limits(args.route_stage_limit)
    manifest = generate_dataset(args.output, target_per_route=args.target_per_route, learning_curve_capacity_per_route=args.capacity_per_route, stage_per_route=args.stage_per_route, initial_attempts_per_route=args.initial_attempts_per_route, route_stage_limits=route_stage_limits or None, seed=args.seed, workers=args.workers, n_points=args.n_points, waveform_policy=args.waveform_policy, heartbeat_every=args.heartbeat_every, representative_waveforms_per_route=args.representative_waveforms_per_route)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
