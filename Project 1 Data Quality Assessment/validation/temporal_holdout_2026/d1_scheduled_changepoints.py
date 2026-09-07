"""Calendar-independent scheduled candidate runs, without input-end flushes.

Legacy binseg statistic, penalty, window and valid-observation stride are retained.
This is a schedule correction candidate, not a change from binseg to true PELT.
"""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from runtime import PROJECT, DIMENSIONS

sys.path.insert(0, str(PROJECT / DIMENSIONS["D1"]))
from src.state.auxiliary_modules import binseg_l2


def scheduled_candidates(series: pd.Series, *, neff_ratio: float, lookback: int = 720,
                         stride: int = 336, min_seg: int = 12,
                         penalty_factor: float = 2.5, max_cps: int = 20) -> list[dict]:
    if (not isinstance(series.index, pd.DatetimeIndex) or not series.index.is_unique
            or not series.index.is_monotonic_increasing):
        raise ValueError("Candidate evidence clock must be unique and increasing")
    if not np.isfinite(neff_ratio) or not 0 <= neff_ratio <= 1:
        raise ValueError("Invalid frozen effective sample ratio")
    if min(lookback, stride, min_seg) <= 0 or lookback < 2*min_seg:
        raise ValueError("Invalid frozen scheduling/window contract")
    valid = series.dropna()
    if np.isinf(valid.to_numpy()).any():
        raise ValueError("Infinite change-point input")
    if neff_ratio == 0:
        return []
    events = []
    for end in range(lookback, len(valid) + 1, stride):
        segment = valid.iloc[end-lookback:end]
        x = segment.to_numpy()
        if np.var(x) < 1e-10:
            continue
        penalty = penalty_factor*np.log(len(x))*np.var(x)/neff_ratio
        for cp in binseg_l2(x, penalty, min_seg=min_seg, max_cps=max_cps):
            timestamp = segment.index[cp]
            if any(abs(timestamp-e["timestamp"]) < pd.Timedelta(hours=1) for e in events):
                continue
            before = float(np.mean(x[max(0, cp-min_seg):cp]))
            after = float(np.mean(x[cp:min(len(x), cp+min_seg)]))
            events.append({"timestamp": timestamp, "available_at": segment.index[-1],
                           "magnitude": abs(after-before), "signed_magnitude": after-before,
                           "before_mean": before, "after_mean": after})
    return events
