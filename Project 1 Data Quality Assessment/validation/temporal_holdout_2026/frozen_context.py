"""Predict-only context model; parameters are plain, portable JSON arrays."""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class FrozenContext:
    feature_names: tuple[str, ...]
    fill_values: np.ndarray
    mean: np.ndarray
    scale: np.ndarray
    centers: np.ndarray
    temperature: float
    temperature_multiplier: float
    ood_threshold: float

    @classmethod
    def from_dict(cls, value: dict) -> "FrozenContext":
        obj = cls(tuple(value["feature_names"]), np.array(value["fill_values"]),
                  np.array(value["scaler_mean"]), np.array(value["scaler_scale"]),
                  np.array(value["cluster_centers"]), float(value["temperature"]),
                  float(value["likelihood_temperature_multiplier"]),
                  float(value["ood_threshold"]))
        n = len(obj.feature_names)
        if any(a.shape != (n,) or not np.isfinite(a).all()
               for a in (obj.fill_values, obj.mean, obj.scale)):
            raise ValueError("Incomplete or nonfinite frozen scaling/imputation assets")
        if (obj.scale <= 0).any() or obj.centers.ndim != 2 or obj.centers.shape[1] != n:
            raise ValueError("Invalid frozen context dimensions")
        if not np.isfinite(obj.centers).all() or obj.temperature <= 0:
            raise ValueError("Invalid frozen centers/temperature")
        return obj

    def predict(self, features: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        if list(features.columns) != list(self.feature_names):
            raise ValueError("Feature order differs from the frozen model contract")
        values = features.to_numpy(dtype=float)
        if np.isinf(values).any():
            raise ValueError("Infinite context inputs require explicit source exclusion")
        values = np.where(np.isnan(values), self.fill_values, values)
        scaled = (values - self.mean) / self.scale
        distances = np.sqrt(((scaled[:, None, :] - self.centers[None, :, :]) ** 2).sum(2))
        shifted = distances - distances.min(axis=1, keepdims=True)
        likelihood = np.exp(-shifted / max(self.temperature * self.temperature_multiplier, 1e-6))
        return likelihood / likelihood.sum(1, keepdims=True), distances.min(1)
