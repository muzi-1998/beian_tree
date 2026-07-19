from __future__ import annotations

import numpy as np
import pandas as pd

from src.baseline.local_baseline import (
    estimate_empirical_scale_floor,
    find_stable_window,
)


def test_stable_window_is_causal_and_rejects_internal_gap():
    index = pd.date_range("2025-01-01", periods=12, freq="h")
    clean = pd.Series(0.1, index=index)
    future_changed = clean.copy()
    future_changed.iloc[8:] = 100.0

    first = find_stable_window(clean, index[0], index[5], stable_h=4, scale_floor=0.05)
    second = find_stable_window(future_changed, index[0], index[5], stable_h=4, scale_floor=0.05)
    assert first == second
    assert first["end"] <= index[5]

    with_gap = clean.copy()
    with_gap.iloc[1] = np.nan
    assert find_stable_window(with_gap, index[0], index[3], stable_h=4, scale_floor=0.05) is None


def test_empirical_scale_floor_uses_only_calibration_prefix():
    index = pd.date_range("2025-01-01", periods=100, freq="h")
    base = pd.Series(np.tile([0.0, 0.1], 50), index=index)
    changed_future = base.copy()
    changed_future.iloc[50:] = np.linspace(0, 100, 50)
    first = estimate_empirical_scale_floor(base, calibration_h=48, rolling_h=12)
    second = estimate_empirical_scale_floor(changed_future, calibration_h=48, rolling_h=12)
    assert first == second
    assert first["scale_floor"] > 0
