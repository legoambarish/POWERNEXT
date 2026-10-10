"""Route-specific v3 regressors with bounded prediction and OOD gates."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import asdict, is_dataclass
from typing import Any

import numpy as np
from sklearn.ensemble import ExtraTreesRegressor, HistGradientBoostingRegressor
from sklearn.multioutput import MultiOutputRegressor
from sklearn.neighbors import NearestNeighbors
from sklearn.preprocessing import StandardScaler

from .features import BASELINE_COLUMNS, FEATURE_COLUMNS, TARGET_COLUMNS


FORMULATIONS = ("physics_guided", "residual")
FAMILIES = ("extra_trees", "hist_gradient_boosting")
DOMAINS = ("cpri_0p5uf", "research_3uf")
MODES = ("LI", "SI")
TOPOLOGIES = ("GSHUNT_v0", "OSHUNT_v0")


def _mapping(value: Any) -> Mapping[str, Any]:
    if isinstance(value, Mapping):
        return value
    if is_dataclass(value):
        return asdict(value)
    if hasattr(value, "__dict__"):
        return vars(value)
    raise TypeError(f"Expected row mapping, got {type(value).__name__}")


def _rows_list(rows: Any) -> list[Mapping[str, Any]]:
    if rows is None:
        return []
    # Avoid making pandas a hard dependency for inference.  DataFrame.to_dict
    # is used when training receives the natural tabular representation.
    if hasattr(rows, "to_dict") and getattr(rows, "columns", None) is not None:
        return [dict(r) for r in rows.to_dict(orient="records")]
    if isinstance(rows, Mapping):
        return [rows]
    if isinstance(rows, np.ndarray):
        return [{"features": row} for row in rows]
    if isinstance(rows, Sequence):
        return [_mapping(r) for r in rows]
    raise TypeError(f"Unsupported rows type {type(rows).__name__}")


def _feature_array(rows: Any, columns: tuple[str, ...] = FEATURE_COLUMNS) -> np.ndarray:
    if isinstance(rows, np.ndarray):
        arr = np.asarray(rows, dtype=float)
    elif hasattr(rows, "to_numpy") and getattr(rows, "columns", None) is not None:
        frame = rows
        if set(columns) <= set(frame.columns):
            arr = frame.loc[:, list(columns)].to_numpy(dtype=float)
        elif "features" in frame.columns:
            return _feature_array(frame.to_dict(orient="records"), columns)
        else:
            missing = sorted(set(columns) - set(frame.columns))
            raise ValueError(f"Missing feature columns: {missing}")
    else:
        records = _rows_list(rows)
        values = []
        for row in records:
            nested = row.get("features", row)
            if isinstance(nested, Mapping):
                missing = [c for c in columns if c not in nested]
                if missing:
                    raise ValueError(f"Missing feature columns: {missing}")
                values.append([nested[c] for c in columns])
            else:
                values.append(nested)
        arr = np.asarray(values, dtype=float)
    if arr.ndim == 1:
        arr = arr.reshape(1, -1)
    if arr.ndim != 2 or arr.shape[1] != len(columns):
        raise ValueError(f"Expected N x {len(columns)} features")
    return arr


def _labels(rows: Any) -> np.ndarray:
    records = _rows_list(rows)
    values = []
    for row in records:
        if all(k in row for k in TARGET_COLUMNS):
            values.append([row[k] for k in TARGET_COLUMNS])
        elif "target" in row and isinstance(row["target"], Mapping):
            values.append([row["target"][k] for k in TARGET_COLUMNS])
        else:
            raise ValueError("Training rows require gain, front_us, and tail_us")
    y = np.asarray(values, dtype=float)
    if y.ndim != 2 or y.shape[1] != 3 or not np.isfinite(y).all() or (y <= 0).any():
        raise ValueError("Training targets must be finite and positive")
    return y


def _route_fields(row: Mapping[str, Any]) -> tuple[Any, Any, Any]:
    return row.get("domain_id"), row.get("mode", row.get("impulse_type")), row.get("topology", row.get("topology_id"))


class NetworkModel:
    """A bounded positive regressor for one explicit v3 network route.

    Models never infer across domain, mode, or topology.  Calling ``fit`` with
    rows carrying a different route raises a compatibility error.  The OOD
    gate uses continuous feature ranges plus a nearest-neighbour distance in
    the transformed training space; it intentionally does not reject every
    resistor value that was not an exact training value.
    """

    def __init__(self, domain_id: str, mode: str, topology: str, formulation: str, family: str, *, random_state: int = 90210):
        if domain_id not in DOMAINS:
            raise ValueError(f"Unknown domain_id {domain_id}")
        if mode not in MODES:
            raise ValueError(f"Unknown mode {mode}")
        if topology not in TOPOLOGIES:
            raise ValueError(f"Unknown topology {topology}")
        if formulation not in FORMULATIONS:
            raise ValueError(f"v3 only permits {FORMULATIONS}")
        if family not in FAMILIES:
            raise ValueError(f"v3 only permits {FAMILIES}")
        self.domain_id = domain_id
        self.mode = mode
        self.topology = topology
        self.formulation = formulation
        self.family = family
        self.random_state = int(random_state)
        self.columns = tuple(FEATURE_COLUMNS)
        self.feature_order = tuple(FEATURE_COLUMNS)
        self.route_id = f"{domain_id}:{mode}:{topology}"
        self.fitted = False

    @property
    def domain(self) -> str:
        """Compatibility spelling used by a few legacy callers."""

        return self.domain_id

    def _validate_route(self, rows: Any) -> None:
        for row in _rows_list(rows):
            domain, mode, topology = _route_fields(row)
            if domain is not None and domain != self.domain_id:
                raise ValueError(f"Model route {self.route_id} cannot fit domain {domain}")
            if mode is not None and mode != self.mode:
                raise ValueError(f"Model route {self.route_id} cannot fit mode {mode}")
            if topology is not None and topology != self.topology:
                raise ValueError(f"Model route {self.route_id} cannot fit topology {topology}")

    def _estimator(self, n_rows: int):
        if self.family == "extra_trees":
            return ExtraTreesRegressor(
                n_estimators=128,
                min_samples_leaf=1 if n_rows < 12 else 2,
                max_features=1.0,
                random_state=self.random_state,
                n_jobs=1,
            )
        leaf = max(1, min(10, n_rows // 5))
        base = HistGradientBoostingRegressor(
            max_iter=180,
            max_leaf_nodes=min(15, max(3, n_rows)),
            min_samples_leaf=leaf,
            l2_regularization=1.0,
            learning_rate=0.06,
            early_stopping=False,
            random_state=self.random_state,
        )
        return MultiOutputRegressor(base, n_jobs=1)

    def fit(self, rows: Any) -> "NetworkModel":
        self._validate_route(rows)
        x = _feature_array(rows, self.columns)
        y = _labels(rows)
        if len(x) != len(y):
            raise ValueError("Feature and target row counts differ")
        if not np.isfinite(x).all() or (x < 0).any():
            raise ValueError("Features must be finite and non-negative")
        baseline = x[:, [self.columns.index(c) for c in BASELINE_COLUMNS]]
        if not np.isfinite(baseline).all() or (baseline <= 0).any():
            raise ValueError("Positive L0 baselines are required")
        if len(x) == 0:
            raise ValueError("Cannot fit an empty dataset")
        # Log coordinates handle the several orders of magnitude in C/L/R
        # while preserving the zero-inductance indicator exactly.
        self.x_scaler = StandardScaler().fit(np.log1p(x))
        z = self.x_scaler.transform(np.log1p(x))
        if self.formulation == "residual":
            target = np.log(y / baseline)
        else:  # physics_guided: physical baseline is input context; learn y.
            target = np.log(y)
        self.y_scaler = StandardScaler().fit(target)
        self.estimator = self._estimator(len(x))
        self.estimator.fit(z, self.y_scaler.transform(target))
        self.minimum = np.min(x, axis=0)
        self.maximum = np.max(x, axis=0)
        self.training_count = len(x)
        self.training_feature_mean = np.mean(x, axis=0)
        if len(z) >= 2:
            self.neighbors = NearestNeighbors(n_neighbors=2).fit(z)
            distances = self.neighbors.kneighbors(z, n_neighbors=2, return_distance=True)[0][:, 1]
            observed = float(np.quantile(distances, 0.99))
            # A floor prevents tiny fixture sets or repeated physical points
            # from making every continuous interpolation OOD.
            self.ood_radius = max(observed * 1.5, 0.10 * np.sqrt(z.shape[1]))
        else:
            self.neighbors = NearestNeighbors(n_neighbors=1).fit(z)
            self.ood_radius = float("inf")
        self.fitted = True
        return self

    def _check_features(self, features: Any) -> tuple[np.ndarray, bool]:
        if not self.fitted:
            raise RuntimeError("Model must be fit or loaded before inference")
        x = _feature_array(features, self.columns)
        if not np.isfinite(x).all() or (x < 0).any():
            raise ValueError("Features must be finite and non-negative")
        return x, x.shape[0] == 1 and np.asarray(features).ndim == 1 if isinstance(features, np.ndarray) else False

    def predict(self, features: np.ndarray) -> np.ndarray:
        """Predict ``gain, front_us, tail_us`` as an ``N x 3`` array."""

        x, _ = self._check_features(features)
        z = self.x_scaler.transform(np.log1p(x))
        transformed = np.asarray(self.estimator.predict(z), dtype=float)
        if transformed.ndim == 1:
            transformed = transformed.reshape(-1, 3)
        raw = self.y_scaler.inverse_transform(transformed)
        with np.errstate(over="raise", invalid="raise"):
            pred = np.exp(np.clip(raw, -60.0, 60.0))
        if self.formulation == "residual":
            baseline = x[:, [self.columns.index(c) for c in BASELINE_COLUMNS]]
            pred *= baseline
        if pred.shape != (len(x), 3) or not np.isfinite(pred).all() or (pred <= 0).any():
            raise ValueError("Model produced invalid predictions")
        return pred

    def ood(self, features: np.ndarray) -> np.ndarray:
        """Return a meaningful continuous support/distance OOD mask."""

        x, _ = self._check_features(features)
        span = np.maximum(self.maximum - self.minimum, 1e-12)
        # A five percent support slack admits an unseen equivalent resistor
        # between trained values while still rejecting genuine extrapolation.
        slack = np.maximum(0.05 * span, 1e-10 * np.maximum(1.0, np.abs(self.maximum)))
        outside = ((x < self.minimum - slack) | (x > self.maximum + slack)).any(axis=1)
        z = self.x_scaler.transform(np.log1p(x))
        distance = self.neighbors.kneighbors(z, n_neighbors=1, return_distance=True)[0][:, 0]
        return np.asarray(outside | (distance > self.ood_radius), dtype=bool)

    def route_card(self) -> dict[str, Any]:
        return dict(
            route_id=self.route_id,
            domain_id=self.domain_id,
            domain=self.domain_id,
            mode=self.mode,
            topology=self.topology,
            topology_id=self.topology,
            formulation=self.formulation,
            family=self.family,
            feature_order=list(self.feature_order),
            baseline_columns=list(BASELINE_COLUMNS),
        )


# Explicit name for callers that do not want a generic "network" term.
V3Model = NetworkModel
ParameterModel = NetworkModel


def make_candidates(domain_id: str, mode: str, topology: str) -> list[NetworkModel]:
    """Return exactly the four approved Phase B candidates for one route."""

    return [
        NetworkModel(domain_id, mode, topology, formulation, family)
        for formulation in FORMULATIONS
        for family in FAMILIES
    ]


__all__ = [
    "FORMULATIONS",
    "FAMILIES",
    "NetworkModel",
    "V3Model",
    "ParameterModel",
    "make_candidates",
]
