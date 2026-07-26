"""Physical rate-limit evidence using the gap-safe robust derivative."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.common.rate_utils import dx_dt_robust, RATE_UTILS_VERSION
from src.d3_physical.threshold_store import ThresholdStore


@dataclass
class RateEvidence:
    sensor: str
    sensor_type: str
    rate_method: str
    rate_utils_version: str
    rate_limit_soft: float
    rate_limit_hard: float
    n_rate_soft_violations: int
    n_rate_hard_violations: int
    n_samples: int
    rate_soft_violation_rate: float
    rate_hard_violation_rate: float
    max_rate_severity: float
    rate_hard_consec_max_min: int
    neighbor_sync_score: float
    parallel_sync_score: float
    shock_candidate: bool
    rate_series: np.ndarray


class RateConstraintChecker:
    def __init__(self, thresholds: ThresholdStore, rate_cfg: dict):
        self.thresholds = thresholds
        self.cfg = rate_cfg
        self.method = rate_cfg["rate_estimator"]["method"]
        self.smooth_window = rate_cfg["rate_estimator"]["smooth_window"]
        self.hampel_window = rate_cfg["rate_estimator"]["hampel_window"]
        self.hampel_n_sigmas = rate_cfg["rate_estimator"]["hampel_n_sigmas"]

    def check(self, x: np.ndarray, sensor: str, sensor_type: str,
              neighbor_sync_score: float = 0.0,
              parallel_sync_score: float = 0.0) -> RateEvidence:
        soft_lim, hard_lim = self.thresholds.rate_limits(sensor_type)
        rate, meta = dx_dt_robust(
            x,
            method=self.method,
            smooth_window=self.smooth_window,
            hampel_window=self.hampel_window,
            hampel_n_sigmas=self.hampel_n_sigmas,
        )
        rate_abs = np.abs(rate)
        rate_clean = rate_abs[~np.isnan(rate_abs)]
        n = len(rate_clean)
        if n == 0:
            return RateEvidence(
                sensor=sensor, sensor_type=sensor_type, rate_method=self.method,
                rate_utils_version=meta["version"],
                rate_limit_soft=soft_lim, rate_limit_hard=hard_lim,
                n_rate_soft_violations=0, n_rate_hard_violations=0,
                n_samples=0, rate_soft_violation_rate=np.nan, rate_hard_violation_rate=np.nan,
                max_rate_severity=np.nan, rate_hard_consec_max_min=0,
                neighbor_sync_score=neighbor_sync_score, parallel_sync_score=parallel_sync_score,
                shock_candidate=False, rate_series=rate,
            )
        soft_v = rate_clean > soft_lim
        hard_v = rate_clean > hard_lim
        # severity: rate / hard_limit
        severity = rate_clean / max(hard_lim, 1e-6)
        max_sev = float(severity.max())
        # Missing rate estimates interrupt runs; never compact across a gap.
        hard_full = np.zeros(len(rate_abs), dtype=bool)
        hard_full[np.isfinite(rate_abs)] = rate_abs[np.isfinite(rate_abs)] > hard_lim
        runs = []
        cur = 0
        for v in hard_full:
            if v:
                cur += 1
            else:
                if cur > 0:
                    runs.append(cur)
                cur = 0
        if cur > 0:
            runs.append(cur)
        consec_max = int(max(runs)) if runs else 0

        # shock candidate: high-magnitude rate AND high neighbor/parallel sync
        shock = bool(hard_v.any() and (neighbor_sync_score > 0.6 or parallel_sync_score > 0.6))

        return RateEvidence(
            sensor=sensor, sensor_type=sensor_type, rate_method=self.method,
            rate_utils_version=meta["version"],
            rate_limit_soft=soft_lim, rate_limit_hard=hard_lim,
            n_rate_soft_violations=int(soft_v.sum()),
            n_rate_hard_violations=int(hard_v.sum()),
            n_samples=int(n),
            rate_soft_violation_rate=float(soft_v.mean()),
            rate_hard_violation_rate=float(hard_v.mean()),
            max_rate_severity=max_sev,
            rate_hard_consec_max_min=consec_max,
            neighbor_sync_score=neighbor_sync_score,
            parallel_sync_score=parallel_sync_score,
            shock_candidate=shock,
            rate_series=rate,
        )
