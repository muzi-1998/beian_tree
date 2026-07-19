"""Causal local-baseline utilities for the D1 recovery state machine."""
from __future__ import annotations

from typing import Optional, Tuple

import numpy as np
import pandas as pd


def theil_sen_slope(
    y: np.ndarray,
    x: Optional[np.ndarray] = None,
    max_pairs: int = 200,
) -> float:
    """Return a deterministic robust median-of-slopes estimate."""
    n = len(y)
    if n < 3:
        return 0.0
    if x is None:
        x = np.arange(n, dtype=float)
    rng = np.random.RandomState(0)
    if n * (n - 1) // 2 > max_pairs:
        i = rng.randint(0, n, max_pairs)
        j = rng.randint(0, n, max_pairs)
        keep = i != j
        i, j = i[keep], j[keep]
    else:
        i, j = np.triu_indices(n, k=1)
    dx = x[j] - x[i]
    keep = dx != 0
    if not keep.any():
        return 0.0
    return float(np.median((y[j] - y[i])[keep] / dx[keep]))


def infer_quantisation_step(values: pd.Series, max_unique: int = 5000) -> float:
    """Estimate a robust lower quantisation step from calibration data."""
    x = np.asarray(values.dropna().values, dtype=float)
    if x.size < 3:
        return 0.0
    unique = np.unique(x)
    if unique.size > max_unique:
        positions = np.linspace(0, unique.size - 1, max_unique).astype(int)
        unique = unique[positions]
    diffs = np.diff(unique)
    diffs = diffs[np.isfinite(diffs) & (diffs > np.finfo(float).eps)]
    if diffs.size == 0:
        return 0.0
    return float(np.quantile(diffs, 0.10))


def estimate_empirical_scale_floor(
    resid: pd.Series,
    valid_mask: Optional[pd.Series] = None,
    calibration_h: int = 720,
    rolling_h: int = 24,
    noise_quantile: float = 0.25,
    resolution_multiplier: float = 1.0,
    epsilon: float = 1e-6,
) -> dict:
    """Estimate a frozen channel-specific residual scale from causal calibration data.

    The estimate uses only the first ``calibration_h`` observations. A low
    quantile of rolling MAD represents normal short-term noise, while the
    inferred quantisation step protects low-variance channels from unrealistically
    small z-score denominators.
    """
    calibration = resid.iloc[:calibration_h].astype(float)
    if valid_mask is not None:
        mask = valid_mask.reindex(calibration.index).fillna(False).astype(bool)
        calibration = calibration.where(mask)

    min_periods = max(6, rolling_h // 2)
    rolling_scale = calibration.rolling(rolling_h, min_periods=min_periods).apply(
        lambda x: 1.4826 * np.median(np.abs(x - np.median(x))), raw=True
    )
    positive = rolling_scale[np.isfinite(rolling_scale) & (rolling_scale > epsilon)]
    noise_floor = float(positive.quantile(noise_quantile)) if len(positive) else 0.0
    resolution = infer_quantisation_step(calibration)
    scale_floor = max(noise_floor, resolution_multiplier * resolution, epsilon)
    return {
        "scale_floor": float(scale_floor),
        "noise_floor": float(noise_floor),
        "resolution_estimate": float(resolution),
        "calibration_n": int(calibration.notna().sum()),
    }


def find_stable_window(
    resid: pd.Series,
    t_start: pd.Timestamp,
    t_end: pd.Timestamp,
    stable_h: int = 24,
    max_slope: float = 0.005,
    max_scale: Optional[float] = None,
    scale_floor: float = 1e-6,
) -> Optional[dict]:
    """Find the first complete, contiguous stable window in ``[start, end]``.

    ``t_end`` is expected to be the current state-machine timestamp. The
    function never reads observations after it, which makes the same code valid
    for batch replay and online execution.
    """
    if t_end < t_start:
        return None
    segment = resid.loc[t_start:t_end]
    if len(segment) < stable_h:
        return None
    expected_span = pd.Timedelta(hours=stable_h - 1)
    for i in range(0, len(segment) - stable_h + 1):
        window = segment.iloc[i : i + stable_h]
        if window.isna().any() or len(window) < stable_h:
            continue
        if window.index[-1] - window.index[0] != expected_span:
            continue
        values = window.to_numpy(dtype=float)
        center = float(np.median(values))
        raw_scale = float(1.4826 * np.median(np.abs(values - center)))
        effective_scale = max(raw_scale, scale_floor)
        if not np.isfinite(effective_scale):
            continue
        if max_scale is not None and effective_scale > max_scale:
            continue
        slope = theil_sen_slope(values)
        if abs(slope) > max_slope * effective_scale:
            continue
        return {
            "start": window.index[0],
            "end": window.index[-1],
            "center": center,
            "raw_scale": raw_scale,
            "scale": effective_scale,
            "scale_floor": float(scale_floor),
            "slope": slope,
        }
    return None


def robust_ewma_update(
    prev_center: float,
    prev_scale: float,
    x: float,
    rate: float = 0.05,
    scale_min: float = 1e-6,
) -> Tuple[float, float]:
    """Update a local baseline with bounded Huber-style influence."""
    effective_scale = max(prev_scale, scale_min)
    z = (x - prev_center) / effective_scale
    residual = float(np.clip(z, -3, 3)) * effective_scale
    new_center = prev_center + rate * residual
    new_scale = (1 - rate) * effective_scale + rate * abs(residual)
    return float(new_center), float(max(new_scale, scale_min))
