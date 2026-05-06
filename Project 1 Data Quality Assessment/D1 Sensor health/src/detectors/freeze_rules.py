"""src/detectors/freeze_rules.py
Freeze detector — composite rules per spec §8:
    (a) Run-length encoding of equal-or-near-equal consecutive values
    (b) Local low variance vs. historical reference σ
    (c) Unique-value ratio in a window
Each component returns its own raw metric; mapping layer combines them.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from .base import BaseDetector, DetectorResult


def _max_run_minutes(x: pd.Series, eps: float) -> pd.Series:
    """For each minute, the length of the current run of |Δx|<eps ending here."""
    diff = x.diff().abs()
    is_eq = (diff < eps).fillna(False)
    # Run-length: cumulative sum that resets to 0 at False
    grp = (~is_eq).cumsum()
    run = is_eq.groupby(grp).cumsum()
    return run.astype(int)


class CompositeFreezeDetector(BaseDetector):
    name = "freeze_composite"

    def __init__(self, eps: float = 1e-6,
                 low_var_window_min: int = 60,
                 ref_low_var_days: int = 30,
                 unique_window_min: int = 60):
        super().__init__(eps=eps,
                         low_var_window_min=low_var_window_min,
                         ref_low_var_days=ref_low_var_days,
                         unique_window_min=unique_window_min)
        self.eps = eps
        self.lv_win = low_var_window_min
        self.ref_days = ref_low_var_days
        self.uq_win = unique_window_min

    def score(self, series: pd.Series, **ctx) -> DetectorResult:
        # (a) RLE
        run = _max_run_minutes(series, self.eps)

        # (b) Low variance:  rolling 60-min std vs. p50 of monthly std
        roll_std = series.rolling(self.lv_win, min_periods=max(20, self.lv_win // 3)).std()
        # Reference: p50 of 30-day rolling std (skip leading NaNs)
        ref_std_window = series.rolling(self.ref_days * 24 * 60,
                                         min_periods=24 * 60).std()
        ref_p50 = ref_std_window.expanding().median()
        rel_var = (roll_std / ref_p50).fillna(1.0)
        # Cap and clip
        rel_var = rel_var.clip(0, 100)

        # (c) Unique ratio
        def _u(arr):
            arr = arr[~np.isnan(arr)]
            if len(arr) == 0:
                return np.nan
            return len(np.unique(np.round(arr, 6))) / len(arr)
        uq_ratio = series.rolling(self.uq_win, min_periods=20).apply(_u, raw=True)

        # Combine into multi-column "raw_score" frame
        meta_df = pd.DataFrame({
            "rle_run_min": run,
            "rel_var":     rel_var,
            "unique_ratio": uq_ratio,
        }, index=series.index)

        # aux_flag: any of three triggered
        flag = ((run >= 15) | (rel_var < 0.05) | (uq_ratio < 0.10)).astype(np.int8)

        # raw_score: maximum severity (1 - min(rel_var, ...)).  Used by mapper.
        # Here we pass meta_df via metadata so mapping layer can look it up.
        return DetectorResult(
            sensor_id=series.name, detector_name=self.name,
            timestamps=series.index,
            raw_score=run.astype(float),    # primary: RLE run length
            aux_flag=flag,
            metadata={"components": meta_df, "eps": self.eps},
        )
