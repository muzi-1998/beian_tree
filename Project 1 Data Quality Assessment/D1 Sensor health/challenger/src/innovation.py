from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


def robust_scale(values: pd.Series | np.ndarray) -> float:
    array = np.asarray(values, dtype=float)
    array = array[np.isfinite(array)]
    if not len(array):
        return np.nan
    center = float(np.median(array))
    scale = 1.4826 * float(np.median(np.abs(array - center)))
    if not np.isfinite(scale) or scale <= 1e-12:
        scale = float(np.std(array))
    return scale if np.isfinite(scale) and scale > 1e-12 else np.nan


def empirical_resolution(series: pd.Series) -> float:
    values = np.sort(series.dropna().unique())
    if len(values) < 2:
        return np.nan
    differences = np.diff(values)
    differences = differences[differences > 0]
    return float(np.quantile(differences, 0.1)) if len(differences) else np.nan


def minute_causal_innovation(
    series: pd.Series,
    *,
    location_window: int,
    scale_window: int,
    guard: int,
    min_location: int,
    min_scale: int,
    resolution_floor_multiplier: float,
    fixed_resolution: float | None = None,
    fixed_scale_floor: float | None = None,
) -> pd.DataFrame:
    """Past-only robust location/scale innovation for minute observations."""
    lagged = series.shift(guard)
    location = lagged.rolling(location_window, min_periods=min_location).median()
    lagged_deviation = (lagged - location).abs()
    scale = 1.4826 * lagged_deviation.rolling(
        scale_window,
        min_periods=min_scale,
    ).median()
    candidates = [1e-6]
    if fixed_resolution is not None and np.isfinite(fixed_resolution):
        candidates.append(float(resolution_floor_multiplier) * float(fixed_resolution))
    if fixed_scale_floor is not None and np.isfinite(fixed_scale_floor):
        candidates.append(float(fixed_scale_floor))
    scale_floor = float(max(candidates))
    effective_scale = scale.clip(lower=scale_floor)
    innovation = (series - location) / effective_scale
    return pd.DataFrame(
        {
            "innovation": innovation,
            "location": location,
            "scale": effective_scale,
            "scale_floor": scale_floor,
        },
        index=series.index,
    )


@dataclass(frozen=True)
class AR1InnovationModel:
    center: float
    phi: float
    scale: float

    def transform(self, series: pd.Series) -> pd.Series:
        centered = series.astype(float) - self.center
        innovation = centered - self.phi * centered.shift(1)
        return innovation / self.scale


def fit_ar1_innovation(
    series: pd.Series,
    eligible: pd.Series,
    *,
    phi_clip: float,
) -> AR1InnovationModel:
    clean = series.where(eligible.reindex(series.index).fillna(False)).dropna()
    if len(clean) < 72:
        raise ValueError(f"Insufficient clean history for {series.name}")
    center = float(clean.median())
    centered = clean - center
    paired = pd.concat([centered.rename("current"), centered.shift(1).rename("lag")], axis=1).dropna()
    denominator = float(np.square(paired["lag"]).sum())
    phi = float((paired["current"] * paired["lag"]).sum() / denominator) if denominator > 0 else 0.0
    phi = float(np.clip(phi, -phi_clip, phi_clip))
    residual = paired["current"] - phi * paired["lag"]
    scale = robust_scale(residual)
    if not np.isfinite(scale):
        raise ValueError(f"Nonfinite AR(1) innovation scale for {series.name}")
    return AR1InnovationModel(center=center, phi=phi, scale=scale)
