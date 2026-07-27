"""Non-scoring boundary diagnostics with fixed benchmark thresholds."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from src.d3_physical.threshold_store import ThresholdStore


@dataclass
class BoundaryEvidence:
    sensor: str
    sensor_type: str
    boundary_sticking_rate: float
    boundary_sticking_low_rate: float
    boundary_sticking_high_rate: float
    tail_rate_low: float
    tail_rate_high: float
    fixed_threshold_low_value: float
    fixed_threshold_high_value: float
    fixed_threshold_source_low: str
    fixed_threshold_source_high: str
    fixed_threshold_version: str
    fixed_threshold_benchmark_window_ids_low: str
    fixed_threshold_benchmark_window_ids_high: str
    boundary_dominant_reason: str
    n_samples: int


class BoundaryFeatureExtractor:
    """
    Boundary behavior: sticking + tail. The strict interface ensures the
    only allowed source of tail thresholds is the ThresholdStore.
    """

    def __init__(self, thresholds: ThresholdStore, sticking_relative_margin: float = 0.05):
        self.thresholds = thresholds
        self.sticking_relative_margin = sticking_relative_margin

    def compute(self, x: np.ndarray, sensor: str, sensor_type: str) -> BoundaryEvidence:
        x_clean = x[~np.isnan(x)]
        n = len(x_clean)
        if n == 0:
            ft_lo = self.thresholds.get_fixed_tail_threshold(sensor, "low")
            ft_hi = self.thresholds.get_fixed_tail_threshold(sensor, "high")
            return self._empty(sensor, sensor_type, ft_lo, ft_hi)

        # sticking: within sticking_relative_margin of hard bounds
        hard_low, hard_high = self.thresholds.hard_bounds(sensor_type)
        rng = hard_high - hard_low
        margin = self.sticking_relative_margin * rng
        sticking_low = (x_clean <= (hard_low + margin)).mean()
        sticking_high = (x_clean >= (hard_high - margin)).mean()
        sticking_total = max(sticking_low, sticking_high)

        # Tail rates use fixed benchmark thresholds and remain diagnostic-only.
        ft_lo = self.thresholds.get_fixed_tail_threshold(sensor, "low")
        ft_hi = self.thresholds.get_fixed_tail_threshold(sensor, "high")
        tail_lo = float((x_clean < ft_lo.value).mean())
        tail_hi = float((x_clean > ft_hi.value).mean())

        # dominant reason
        reasons = {
            "low_sticking": sticking_low,
            "high_sticking": sticking_high,
            "tail_low": tail_lo,
            "tail_high": tail_hi,
        }
        dominant = max(reasons, key=reasons.get)
        if reasons[dominant] < 0.001:
            dominant = "none"

        return BoundaryEvidence(
            sensor=sensor, sensor_type=sensor_type,
            boundary_sticking_rate=float(sticking_total),
            boundary_sticking_low_rate=float(sticking_low),
            boundary_sticking_high_rate=float(sticking_high),
            tail_rate_low=tail_lo,
            tail_rate_high=tail_hi,
            fixed_threshold_low_value=ft_lo.value,
            fixed_threshold_high_value=ft_hi.value,
            fixed_threshold_source_low=ft_lo.source,
            fixed_threshold_source_high=ft_hi.source,
            fixed_threshold_version=ft_lo.version,
            fixed_threshold_benchmark_window_ids_low=",".join(ft_lo.benchmark_window_ids[:3]) + "...",
            fixed_threshold_benchmark_window_ids_high=",".join(ft_hi.benchmark_window_ids[:3]) + "...",
            boundary_dominant_reason=dominant,
            n_samples=int(n),
        )

    @staticmethod
    def _empty(sensor, sensor_type, ft_lo, ft_hi):
        return BoundaryEvidence(
            sensor=sensor, sensor_type=sensor_type,
            boundary_sticking_rate=np.nan, boundary_sticking_low_rate=np.nan,
            boundary_sticking_high_rate=np.nan, tail_rate_low=np.nan, tail_rate_high=np.nan,
            fixed_threshold_low_value=ft_lo.value, fixed_threshold_high_value=ft_hi.value,
            fixed_threshold_source_low=ft_lo.source, fixed_threshold_source_high=ft_hi.source,
            fixed_threshold_version=ft_lo.version,
            fixed_threshold_benchmark_window_ids_low="", fixed_threshold_benchmark_window_ids_high="",
            boundary_dominant_reason="none", n_samples=0,
        )
