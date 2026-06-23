"""src/detectors/step_adjacent_ks.py
Step detector — adjacent KS test on hourly residuals + CUSUM (Page-Hinkley).
Per spec §6: streaming layer; PELT lives in batch (not in main pipeline).
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from scipy.stats import ks_2samp
from .base import BaseDetector, DetectorResult


class AdjacentKSStepDetector(BaseDetector):
    name = "adjacent_ks"

    def __init__(self, win_h: int = 24, alpha: float = 0.001,
                 neff_ratio: float = 1.0):
        super().__init__(win_h=win_h, alpha=alpha, neff_ratio=neff_ratio)
        self.win_h = win_h
        # KS critical at α (one-sample two-sample two-sided)
        # For two-sample: D_α ≈ c(α) · sqrt(2/n)
        self.c_alpha = {0.05: 1.36, 0.01: 1.63, 0.001: 1.95}.get(alpha, 1.95)
        self.ks_crit = self.c_alpha * np.sqrt(2.0 / win_h)
        # n_eff awareness (audit §3): the i.i.d. critical value assumes `win_h`
        # independent samples. On an autocorrelated residual the effective count
        # is win_h·neff_ratio, so a raw D is only as significant as
        # D·sqrt(neff_ratio) would be under i.i.d. We deflate the reported
        # statistic by that factor (rather than inflating ks_crit) so BOTH the
        # flag AND the continuous Q_step logistic — which maps raw_score — get
        # the correction consistently. neff_ratio=1 → unchanged (white input);
        # ≈0.01 (near-unit-root) → ~10× shrink; 0 (floor) → zeroed.
        self.neff_ratio = float(np.clip(neff_ratio, 0.0, 1.0))
        self._deflate = float(np.sqrt(self.neff_ratio))

    def score(self, series_hourly: pd.Series, **ctx) -> DetectorResult:
        """series_hourly: hourly whitened input (innovation for iid channels,
        residual for autocorr_aware) — see bridge_decomposition_11."""
        x = series_hourly.values
        n = len(x)
        ks_d = np.full(n, np.nan)
        for i in range(2 * self.win_h, n):
            s1 = x[i - 2 * self.win_h: i - self.win_h]
            s2 = x[i - self.win_h: i]
            s1 = s1[~np.isnan(s1)]
            s2 = s2[~np.isnan(s2)]
            if len(s1) >= max(8, self.win_h // 3) and len(s2) >= max(8, self.win_h // 3):
                D, _ = ks_2samp(s1, s2)
                ks_d[i] = D * self._deflate
        ks_series = pd.Series(ks_d, index=series_hourly.index, name="ks_d")
        flag = (ks_series > self.ks_crit).astype(np.int8)
        return DetectorResult(
            sensor_id=series_hourly.name, detector_name=self.name,
            timestamps=series_hourly.index, raw_score=ks_series, aux_flag=flag,
            metadata={"win_h": self.win_h, "alpha": self.params["alpha"],
                      "ks_crit": float(self.ks_crit),
                      "neff_ratio": self.neff_ratio,
                      "deflate_factor": self._deflate},
        )


class PageHinkleyDetector(BaseDetector):
    """Page-Hinkley test as auxiliary CUSUM-style step confirmer."""
    name = "page_hinkley"

    def __init__(self, delta: float = 0.5, lambd: float = 5.0):
        super().__init__(delta=delta, lambd=lambd)
        self.delta = delta
        self.lambd = lambd

    def score(self, series: pd.Series, **ctx) -> DetectorResult:
        x = series.values
        n = len(x)
        m = np.zeros(n); cumsum = 0.0; mn = 0.0
        flag = np.zeros(n, dtype=np.int8)
        score = np.zeros(n)
        # Use rolling mean as drift-free reference
        ref = pd.Series(x).expanding(min_periods=24).mean().values
        for i in range(n):
            if np.isnan(x[i]) or np.isnan(ref[i]):
                continue
            cumsum += (x[i] - ref[i] - self.delta)
            mn = min(mn, cumsum)
            ph = cumsum - mn
            score[i] = ph
            if ph > self.lambd:
                flag[i] = 1
                cumsum = 0.0; mn = 0.0   # reset after detection
        return DetectorResult(
            sensor_id=series.name, detector_name=self.name,
            timestamps=series.index,
            raw_score=pd.Series(score, index=series.index),
            aux_flag=pd.Series(flag, index=series.index),
            metadata={"delta": self.delta, "lambd": self.lambd},
        )
