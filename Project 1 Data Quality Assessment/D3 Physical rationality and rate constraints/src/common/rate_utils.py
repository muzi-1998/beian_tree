"""Gap-safe robust rate estimator used by D3."""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.version import RATE_UTILS_VERSION


def _hampel_filter(x: np.ndarray, window: int = 7, n_sigmas: float = 3.0) -> np.ndarray:
    """In-place Hampel outlier replacement with rolling median."""
    x = x.copy().astype(float)
    if len(x) < window:
        return x
    s = pd.Series(x)
    med = s.rolling(window, center=True, min_periods=1).median()
    mad = (s - med).abs().rolling(window, center=True, min_periods=1).median()
    threshold = 1.4826 * mad * n_sigmas
    mask = (s - med).abs() > threshold
    s[mask] = med[mask]
    return s.to_numpy()


def _theil_sen_slope(y: np.ndarray, dt_min: float = 1.0) -> float:
    """Theil-Sen median slope estimator, robust to outliers."""
    n = len(y)
    if n < 2:
        return 0.0
    # subsample for speed when n large
    if n > 31:
        idx = np.linspace(0, n - 1, 31, dtype=int)
        y = y[idx]
        n = len(y)
    slopes = []
    for i in range(n):
        for j in range(i + 1, n):
            slopes.append((y[j] - y[i]) / ((j - i) * dt_min))
    return float(np.median(slopes)) if slopes else 0.0


def _rolling_theil_sen(clean: np.ndarray, window: int, dt_min: float) -> np.ndarray:
    """Vectorized interior Theil-Sen slopes with exact edge behavior."""
    local = np.full(len(clean), np.nan, dtype=float)
    half = window // 2
    if len(clean) >= window:
        windows = np.lib.stride_tricks.sliding_window_view(clean, window)
        left, right = np.triu_indices(window, k=1)
        slopes = (windows[:, right] - windows[:, left]) / (
            (right - left)[None, :] * dt_min
        )
        local[half:half + len(windows)] = np.median(slopes, axis=1)
    edge_indices = list(range(min(half, len(clean))))
    edge_indices += list(range(max(half, len(clean) - half), len(clean)))
    for index in sorted(set(edge_indices)):
        low = max(0, index - half)
        high = min(len(clean), index + half + 1)
        if high - low >= 2:
            local[index] = _theil_sen_slope(clean[low:high], dt_min=dt_min)
    return local


def dx_dt_robust(
    x: np.ndarray | pd.Series,
    method: str = "theil_sen",
    smooth_window: int = 5,
    hampel_window: int = 7,
    hampel_n_sigmas: float = 3.0,
    dt_min: float = 1.0,
) -> tuple[np.ndarray, dict]:
    """
    Compute robust rate of change without bridging missing-data gaps.

    Returns
    -------
    rate : np.ndarray, same length as x
        Robust rate estimate at each timestep, in units of x / minute.
    meta : dict
        Includes version, method, n, n_valid, smooth_window.
    """
    if isinstance(x, pd.Series):
        x_arr = x.to_numpy(dtype=float)
    else:
        x_arr = np.asarray(x, dtype=float)

    n = len(x_arr)
    rate = np.full(n, np.nan, dtype=float)
    valid = np.isfinite(x_arr)
    if not valid.any():
        return rate, {
            "version": RATE_UTILS_VERSION,
            "method": method,
            "n": n,
            "n_valid": 0,
            "smooth_window": smooth_window,
        }
    starts = np.flatnonzero(valid & np.r_[True, ~valid[:-1]])
    ends = np.flatnonzero(valid & np.r_[~valid[1:], True]) + 1
    w = max(3, smooth_window)
    half = w // 2
    for start, end in zip(starts, ends):
        segment = x_arr[start:end]
        if len(segment) < 2:
            continue
        clean = _hampel_filter(segment, window=hampel_window, n_sigmas=hampel_n_sigmas)
        local = np.full(len(clean), np.nan, dtype=float)
        if method == "diff":
            local[1:] = np.diff(clean) / dt_min
        elif method in {"rolling_linear", "theil_sen"}:
            if method == "theil_sen":
                local = _rolling_theil_sen(clean, w, dt_min)
            else:
                for i in range(len(clean)):
                    lo = max(0, i - half)
                    hi = min(len(clean), i + half + 1)
                    y = clean[lo:hi]
                    if len(y) < 2:
                        continue
                    t = np.arange(len(y)) * dt_min
                    local[i] = np.polyfit(t, y, 1)[0]
        else:
            raise ValueError(f"Unknown rate method: {method}")
        rate[start:end] = local

    meta = {
        "version": RATE_UTILS_VERSION,
        "method": method,
        "n": n,
        "n_valid": int(valid.sum()),
        "n_runs": int(len(starts)),
        "smooth_window": smooth_window,
    }
    return rate, meta


def change_point_magnitude(x: np.ndarray, half_window: int = 30) -> np.ndarray:
    """
    Adjacent-window mean difference, a primitive used in step detection
    sensor diagnostics and D3 physical-jump detection.
    """
    n = len(x)
    out = np.zeros(n)
    s = np.asarray(x, dtype=float)
    for i in range(half_window, n - half_window):
        left = s[i - half_window:i]
        right = s[i:i + half_window]
        if np.isfinite(left).all() and np.isfinite(right).all():
            out[i] = abs(np.mean(right) - np.mean(left))
        else:
            out[i] = np.nan
    return out
