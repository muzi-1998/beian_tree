"""local_baseline.py — D1 v1.1 local baseline rebuild module.

Per Cooldown 修订 §八: After Refractory ends (and anomaly persists), system
must rebuild a local NEW baseline from a stable candidate window in
[t_event + after_min, t_event + after_max] hours.

Algorithm:
    1. Find first stable continuous window of length stable_h ∈ [24, 48] h
       inside [refractory_end, refractory_end + search_max] where:
       - residual variance is below 80th percentile of long-term residual MAD
       - Theil-Sen slope of residual is ≤ drift_slope_threshold
    2. Initialise (median, 1.4826*MAD) as the new local center & scale
    3. Online robust EWMA update with low rate to track slow drift inside
       the new steady state
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from typing import Optional, Tuple


def theil_sen_slope(y: np.ndarray, x: Optional[np.ndarray] = None,
                     max_pairs: int = 200) -> float:
    """Robust median-of-slopes (Theil-Sen estimator)."""
    n = len(y)
    if n < 3: return 0.0
    if x is None: x = np.arange(n, dtype=float)
    rng = np.random.RandomState(0)
    if n * (n - 1) // 2 > max_pairs:
        i = rng.randint(0, n, max_pairs)
        j = rng.randint(0, n, max_pairs)
        msk = i != j
        i, j = i[msk], j[msk]
    else:
        ii, jj = np.triu_indices(n, k=1)
        i, j = ii, jj
    dx = x[j] - x[i]
    dy = y[j] - y[i]
    valid = dx != 0
    if not valid.any(): return 0.0
    return float(np.median(dy[valid] / dx[valid]))


def find_stable_window(resid: pd.Series, t_start: pd.Timestamp,
                        t_end: pd.Timestamp,
                        stable_h: int = 24, max_slope: float = 0.005,
                        max_scale: float = 5.0) -> Optional[dict]:
    """Find first stable window in [t_start, t_end].

    Returns dict {start, end, center, scale, slope, scale_ok} or None.
    """
    seg = resid.loc[t_start:t_end].dropna()
    if len(seg) < stable_h: return None
    n = len(seg)
    step = max(1, stable_h // 6)
    for i in range(0, n - stable_h + 1, step):
        w = seg.iloc[i:i + stable_h]
        if len(w) < stable_h: continue
        center = float(np.median(w.values))
        scale = float(1.4826 * np.median(np.abs(w.values - center)))
        if scale > max_scale or scale <= 0: continue
        slope = theil_sen_slope(w.values)
        if abs(slope) > max_slope * max(scale, 1e-3): continue
        return {
            "start": w.index[0], "end": w.index[-1],
            "center": center, "scale": scale,
            "slope": slope, "scale_ok": True,
        }
    return None


def robust_ewma_update(prev_center: float, prev_scale: float, x: float,
                        rate: float = 0.05, scale_min: float = 1e-3) -> Tuple[float, float]:
    """Robust EWMA update for local baseline.
    
    Uses Huber-style influence (clip residuals to ±3·scale).
    """
    z = (x - prev_center) / max(prev_scale, scale_min)
    # Huber clip
    z_clip = float(np.clip(z, -3, 3))
    r = z_clip * prev_scale
    new_center = prev_center + rate * r
    # Update scale via abs deviation
    new_scale = (1 - rate) * prev_scale + rate * abs(r)
    return new_center, max(new_scale, scale_min)
