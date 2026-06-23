"""src/detectors/pelt_batch.py
PELT (Pruned Exact Linear Time) change-point detection for batch calibration.

Reference: Killick et al. (2012) "Optimal detection of changepoints with a
linear computational cost". Output: precise change-point timestamps for the
last 24-48 h, written to the state-blackboard for streaming consumption.

This module is invoked OFFLINE (every 1-6 h, not per-min) per spec §6.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from typing import List, Dict


def _l2_cost(seg: np.ndarray) -> float:
    """Cost = sum of squared deviations from segment mean."""
    if len(seg) < 2:
        return 0.0
    return float(np.sum((seg - np.mean(seg)) ** 2))


def pelt_l2(x: np.ndarray, penalty: float, min_seg: int = 12) -> List[int]:
    """PELT with L2 cost. Returns sorted list of change-point indices.

    Parameters
    ----------
    x : 1-D residual array (NaN-free).
    penalty : segmentation penalty (BIC-like: log(n) * var(x)).
    min_seg : minimum segment length (hours).

    Returns
    -------
    cp : list of internal change-point indices (i.e. excluding 0 and n).
    """
    n = len(x)
    if n < 2 * min_seg:
        return []

    # F[t] = best cost for segmentation up to t
    F = np.full(n + 1, np.inf)
    F[0] = -penalty
    cp_at = [[] for _ in range(n + 1)]
    candidates = [0]

    for t in range(min_seg, n + 1):
        best = np.inf
        best_s = -1
        new_candidates = []
        for s in candidates:
            if t - s < min_seg:
                new_candidates.append(s)
                continue
            cost = F[s] + _l2_cost(x[s:t]) + penalty
            if cost < best:
                best = cost
                best_s = s
            # Pruning: keep only candidates that could still be optimal
            if F[s] + _l2_cost(x[s:t]) <= F[t] + 1e-9:
                new_candidates.append(s)
        F[t] = best
        cp_at[t] = list(cp_at[best_s]) + ([best_s] if best_s > 0 else [])
        # Update candidate pool
        candidates = new_candidates + [t - min_seg + 1] if (t - min_seg + 1) > 0 else new_candidates

    return sorted(set(cp_at[n]))


class PELTBatchCalibrator:
    """Batch calibrator: refine step locations from past 24-48h residuals.

    Run-mode: invoked every batch cycle (e.g. every 6 h). Detects precise
    change-points in residual time-series and writes them to the blackboard
    as 'pelt_step_window' flags. Streaming layer reads these to mask drift
    cooldown more precisely (instead of relying solely on adjacent KS).
    """

    def __init__(self, lookback_hours: int = 48, min_seg_hours: int = 6,
                 penalty_factor: float = 1.5, neff_ratio: float = 1.0):
        self.lookback = lookback_hours
        self.min_seg = min_seg_hours
        self.penalty_factor = penalty_factor
        # n_eff awareness (audit §3): the BIC-style penalty log(n)·var(x) assumes
        # n independent samples. On an autocorrelated residual var(x) over-counts
        # information and PELT over-segments. Inflate the penalty by 1/neff_ratio
        # so the effective sample size is n·neff_ratio. neff_ratio=1 → unchanged
        # (white input); ≈0.01 (near-unit-root) → ~100× penalty (≈no spurious CPs);
        # 0 (floor) → penalty=∞ (no CPs; freeze owns the channel).
        self.neff_ratio = float(min(max(neff_ratio, 0.0), 1.0))

    def calibrate_one(self, resid_h: pd.Series, end_time: pd.Timestamp = None
                       ) -> List[Dict]:
        """Run PELT on the last `lookback` hours ending at `end_time`."""
        if end_time is None:
            end_time = resid_h.index[-1]
        start_time = end_time - pd.Timedelta(hours=self.lookback)
        seg = resid_h.loc[start_time:end_time].dropna()
        if len(seg) < self.min_seg * 2:
            return []
        x = seg.values
        # Penalty: BIC-style, inflated by 1/neff_ratio for autocorrelation.
        if self.neff_ratio <= 0.0:
            return []   # floor channel — excluded from change-point scoring
        penalty = self.penalty_factor * np.log(len(x)) * np.var(x) / self.neff_ratio
        cps = pelt_l2(x, penalty=penalty, min_seg=self.min_seg)
        events = []
        for cp in cps:
            cp_time = seg.index[cp]
            # Reaching window: ±min_seg around the cp
            ws = max(0, cp - self.min_seg)
            we = min(len(seg), cp + self.min_seg)
            events.append({
                "sensor_id": resid_h.name,
                "flag_name": "pelt_step",
                "value": {
                    "cp_index": int(cp),
                    "before_mean": float(np.mean(x[ws:cp])),
                    "after_mean":  float(np.mean(x[cp:we])),
                    "magnitude":   float(abs(np.mean(x[cp:we]) - np.mean(x[ws:cp]))),
                    "n_before": cp - ws, "n_after": we - cp,
                },
                "start_time": cp_time,
                "expire_at": cp_time + pd.Timedelta(hours=self.min_seg),
                "source": "batch_pelt",
            })
        return events

    def calibrate_full_history(self, resid_h: pd.DataFrame,
                                stride_h: int = 24) -> List[Dict]:
        """Walk over the whole history applying PELT on rolling windows."""
        all_events = []
        idx = resid_h.index
        for col in resid_h.columns:
            ser = resid_h[col]
            # Walk by stride_h
            for end_idx in range(self.lookback, len(idx), stride_h):
                end_time = idx[end_idx]
                events = self.calibrate_one(ser, end_time=end_time)
                all_events.extend(events)
        return all_events
