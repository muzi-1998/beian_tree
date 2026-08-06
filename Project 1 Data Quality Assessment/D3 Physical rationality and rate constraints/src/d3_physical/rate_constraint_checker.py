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
    n_rate_soft_point_violations: int
    n_rate_hard_point_violations: int
    n_rate_soft_violations: int
    n_rate_hard_violations: int
    n_samples: int
    rate_soft_point_violation_rate: float
    rate_hard_point_violation_rate: float
    rate_soft_violation_rate: float
    rate_hard_violation_rate: float
    max_rate_severity: float
    rate_hard_consec_max_min: int
    rate_hard_consec_raw_max_min: int
    persistent_rate_event_count: int
    impulse_return_event_count: int
    impulse_return_excluded_fraction: float
    process_coherence_guarded_fraction: float
    process_coherence_guarded_points: int
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
        persistence = rate_cfg["persistence"]
        self.soft_same_sign_min = int(persistence["soft_same_sign_min"])
        self.hard_same_sign_min = int(persistence["hard_same_sign_min"])
        impulse = rate_cfg.get("impulse_return", {})
        self.impulse_enabled = bool(impulse.get("enabled", False))
        self.impulse_max_return = int(impulse.get("max_return_min", 3))
        self.impulse_tolerance = impulse.get("baseline_tolerance", {})

    @staticmethod
    def _persistent_mask(
        rate: np.ndarray,
        limit: float,
        minimum_duration: int,
        excluded: np.ndarray,
    ) -> tuple[np.ndarray, int, int]:
        active = np.isfinite(rate) & (np.abs(rate) > limit) & ~excluded
        signs = np.sign(rate)
        persistent = np.zeros(len(rate), dtype=bool)
        max_run = 0
        event_count = 0
        start = None
        run_sign = 0.0
        for index in range(len(rate) + 1):
            is_active = index < len(rate) and active[index]
            sign = signs[index] if is_active else 0.0
            if is_active and start is None:
                start = index
                run_sign = sign
            elif is_active and sign != run_sign:
                length = index - start
                max_run = max(max_run, length)
                if length >= minimum_duration:
                    persistent[start:index] = True
                    event_count += 1
                start = index
                run_sign = sign
            elif not is_active and start is not None:
                length = index - start
                max_run = max(max_run, length)
                if length >= minimum_duration:
                    persistent[start:index] = True
                    event_count += 1
                start = None
                run_sign = 0.0
        return persistent, int(max_run), int(event_count)

    def _impulse_return_mask(
        self, x: np.ndarray, hard_limit: float, sensor_type: str
    ) -> tuple[np.ndarray, int]:
        mask = np.zeros(len(x), dtype=bool)
        if not self.impulse_enabled or len(x) < 3:
            return mask, 0
        tolerance = float(self.impulse_tolerance.get(sensor_type, 0.0))
        diff = np.full(len(x), np.nan, dtype=float)
        finite_pair = np.isfinite(x[1:]) & np.isfinite(x[:-1])
        finite_indices = np.flatnonzero(finite_pair) + 1
        diff[finite_indices] = np.diff(x)[finite_pair]
        count = 0
        index = 1
        while index < len(x):
            first = diff[index]
            if not np.isfinite(first) or abs(first) <= hard_limit:
                index += 1
                continue
            baseline = x[index - 1]
            matched = None
            for end in range(index + 1, min(len(x), index + self.impulse_max_return + 1)):
                second = diff[end]
                if (
                    np.isfinite(second)
                    and np.sign(second) == -np.sign(first)
                    and abs(second) > hard_limit
                    and np.isfinite(x[end])
                    and abs(x[end] - baseline) <= tolerance
                ):
                    matched = end
                    break
            if matched is None:
                index += 1
                continue
            mask[max(0, index - 2):min(len(x), matched + 3)] = True
            count += 1
            index = matched + 1
        return mask, count

    def check(self, x: np.ndarray, sensor: str, sensor_type: str,
              neighbor_sync_score: float = 0.0,
              parallel_sync_score: float = 0.0,
              process_coherent_mask: np.ndarray | None = None,
              precomputed_rate: np.ndarray | None = None) -> RateEvidence:
        soft_lim, hard_lim = self.thresholds.rate_limits(sensor_type)
        if precomputed_rate is None:
            rate, meta = dx_dt_robust(
                x,
                method=self.method,
                smooth_window=self.smooth_window,
                hampel_window=self.hampel_window,
                hampel_n_sigmas=self.hampel_n_sigmas,
            )
        else:
            rate = np.asarray(precomputed_rate, dtype=float)
            if len(rate) != len(x):
                raise ValueError("precomputed_rate must match the observation-series length")
            meta = {"version": RATE_UTILS_VERSION}
        rate_abs = np.abs(rate)
        rate_clean = rate_abs[~np.isnan(rate_abs)]
        n = len(rate_clean)
        coherent_mask = (
            np.asarray(process_coherent_mask, dtype=bool)
            if process_coherent_mask is not None
            else np.zeros(len(rate), dtype=bool)
        )
        if len(coherent_mask) != len(rate):
            raise ValueError("process_coherent_mask must match the rate-series length")
        if n == 0:
            return RateEvidence(
                sensor=sensor, sensor_type=sensor_type, rate_method=self.method,
                rate_utils_version=meta["version"],
                rate_limit_soft=soft_lim, rate_limit_hard=hard_lim,
                n_rate_soft_point_violations=0, n_rate_hard_point_violations=0,
                n_rate_soft_violations=0, n_rate_hard_violations=0,
                n_samples=0, rate_soft_point_violation_rate=np.nan,
                rate_hard_point_violation_rate=np.nan,
                rate_soft_violation_rate=np.nan, rate_hard_violation_rate=np.nan,
                max_rate_severity=np.nan, rate_hard_consec_max_min=0,
                rate_hard_consec_raw_max_min=0, persistent_rate_event_count=0,
                impulse_return_event_count=0, impulse_return_excluded_fraction=0.0,
                process_coherence_guarded_fraction=0.0,
                process_coherence_guarded_points=0,
                neighbor_sync_score=neighbor_sync_score, parallel_sync_score=parallel_sync_score,
                shock_candidate=False, rate_series=rate,
            )
        soft_point = np.isfinite(rate) & (rate_abs > soft_lim)
        hard_point = np.isfinite(rate) & (rate_abs > hard_lim)
        impulse_mask, impulse_events = self._impulse_return_mask(x, hard_lim, sensor_type)
        _, raw_hard_max, _ = self._persistent_mask(
            rate, hard_lim, self.hard_same_sign_min, impulse_mask
        )
        guarded_mask = impulse_mask | coherent_mask
        soft_persistent, _, soft_events = self._persistent_mask(
            rate, soft_lim, self.soft_same_sign_min, guarded_mask
        )
        hard_persistent, hard_max, _ = self._persistent_mask(
            rate, hard_lim, self.hard_same_sign_min, guarded_mask
        )
        # severity: rate / hard_limit
        severity = rate_clean / max(hard_lim, 1e-6)
        max_sev = float(severity.max())
        shock = bool((hard_point & coherent_mask).any())
        coherent_hard = hard_point & coherent_mask
        hard_point_count = int(hard_point.sum())

        return RateEvidence(
            sensor=sensor, sensor_type=sensor_type, rate_method=self.method,
            rate_utils_version=meta["version"],
            rate_limit_soft=soft_lim, rate_limit_hard=hard_lim,
            n_rate_soft_point_violations=int(soft_point.sum()),
            n_rate_hard_point_violations=hard_point_count,
            n_rate_soft_violations=int(soft_persistent.sum()),
            n_rate_hard_violations=int(hard_persistent.sum()),
            n_samples=int(n),
            rate_soft_point_violation_rate=float(soft_point.sum() / n),
            rate_hard_point_violation_rate=float(hard_point_count / n),
            rate_soft_violation_rate=float(soft_persistent.sum() / n),
            rate_hard_violation_rate=float(hard_persistent.sum() / n),
            max_rate_severity=max_sev,
            rate_hard_consec_max_min=hard_max,
            rate_hard_consec_raw_max_min=raw_hard_max,
            # Hard-persistent events are a subset of soft-persistent events;
            # counting both would duplicate the same physical episode.
            persistent_rate_event_count=int(soft_events),
            impulse_return_event_count=impulse_events,
            impulse_return_excluded_fraction=float((impulse_mask & np.isfinite(rate)).sum() / n),
            process_coherence_guarded_fraction=float(coherent_hard.sum() / max(hard_point_count, 1)),
            process_coherence_guarded_points=int(coherent_hard.sum()),
            neighbor_sync_score=neighbor_sync_score,
            parallel_sync_score=parallel_sync_score,
            shock_candidate=shock,
            rate_series=rate,
        )
