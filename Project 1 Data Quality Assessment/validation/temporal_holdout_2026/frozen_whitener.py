"""Stateful predictor reproducing the historical batch filter's missing contract."""
from __future__ import annotations

from copy import deepcopy

import numpy as np
from scipy.signal import lfilter


class FrozenWhitener:
    def __init__(self, asset: dict, state: dict | None = None):
        self.asset = deepcopy(asset)
        self.route = asset["route"]
        self.b = np.r_[1.0, -np.asarray(asset.get("ar", []), dtype=float)]
        self.a = np.r_[1.0, np.asarray(asset.get("ma", []), dtype=float)]
        self.garch = asset.get("garch")
        self.zi = np.zeros(max(len(self.b), len(self.a)) - 1)
        self.alpha = np.atleast_1d(np.asarray((self.garch or {}).get("alpha", []), dtype=float))
        self.beta = np.atleast_1d(np.asarray((self.garch or {}).get("beta", []), dtype=float))
        initial = float(asset.get("initial_variance", 1.0))
        self.e2 = np.zeros(len(self.alpha))
        self.s2 = np.full(len(self.beta), initial)
        if state is not None:
            for name in ("zi", "e2", "s2"):
                current = getattr(self, name)
                value = np.asarray(state[name], dtype=float)
                if value.shape != current.shape or not np.isfinite(value).all():
                    raise ValueError("Incompatible or nonfinite filter checkpoint")
                setattr(self, name, value.copy())

    def checkpoint(self) -> dict:
        return {name: getattr(self, name).tolist() for name in ("zi", "e2", "s2")}

    def transform(self, residual: np.ndarray) -> np.ndarray:
        values = np.asarray(residual, dtype=float)
        if values.ndim != 1 or np.isinf(values).any():
            raise ValueError("Expected finite-or-missing one-dimensional residuals")
        if not len(values):
            return values.copy()
        if self.route in {"robust_z", "floor"}:
            return (values - self.asset["center"]) / self.asset["scale"]
        if self.route != "arma":
            raise ValueError(f"Unknown frozen route: {self.route}")
        missing = np.isnan(values)
        centered = values - self.asset["intercept"]
        eta, self.zi = lfilter(self.b, self.a, np.where(missing, 0, centered), zi=self.zi)
        if self.garch:
            variance = np.empty(len(values))
            for i in range(len(values)):
                value = max(float(self.garch["omega"]) + float(self.alpha @ self.e2)
                            + float(self.beta @ self.s2), 1e-12)
                variance[i] = value
                if len(self.e2):
                    self.e2 = np.r_[0.0 if missing[i] else eta[i] ** 2, self.e2[:-1]]
                if len(self.s2):
                    self.s2 = np.r_[value, self.s2[:-1]]
        else:
            variance = float(self.asset["fixed_non_garch_variance"])
            if not np.isfinite(variance) or variance <= 0:
                raise ValueError("Fixed historical scaling variance is unavailable")
        out = eta / np.sqrt(variance)
        out[missing] = np.nan
        return out
