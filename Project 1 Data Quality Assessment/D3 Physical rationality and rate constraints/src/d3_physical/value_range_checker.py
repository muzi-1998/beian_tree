"""Hard and operational soft-bound evidence on observed values only."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from src.d3_physical.threshold_store import ThresholdStore


@dataclass(frozen=True)
class ValueEvidence:
    sensor: str
    sensor_type: str
    hard_low: float
    hard_high: float
    soft_low: float
    soft_high: float
    hard_violation_count: int
    soft_violation_count: int
    hard_low_violation_count: int
    hard_high_violation_count: int
    soft_low_violation_count: int
    soft_high_violation_count: int
    n_samples: int
    hard_violation_rate: float
    soft_violation_rate: float
    hard_low_violation_rate: float
    hard_high_violation_rate: float
    soft_low_violation_rate: float
    soft_high_violation_rate: float
    max_violation_magnitude: float
    max_soft_low_exceedance: float
    max_soft_high_exceedance: float
    out_of_instrument: bool
    consecutive_hard_max_min: int
    threshold_scope: str


class ValueRangeChecker:
    def __init__(self, thresholds: ThresholdStore, instrument_low: float, instrument_high: float):
        self.thresholds = thresholds
        self.instrument_low = instrument_low
        self.instrument_high = instrument_high

    def check(self, x: np.ndarray, sensor: str, sensor_type: str) -> ValueEvidence:
        hard_low, hard_high = self.thresholds.hard_bounds(sensor_type, sensor)
        soft_low, soft_high = self.thresholds.soft_bounds(sensor_type, sensor)
        threshold_scope = "sensor_override" if (soft_low, soft_high) != self.thresholds.soft_bounds(sensor_type) else "sensor_type"
        valid = np.isfinite(x)
        clean = x[valid]
        if not len(clean):
            return ValueEvidence(
                sensor, sensor_type, hard_low, hard_high, soft_low, soft_high,
                0, 0, 0, 0, 0, 0, 0,
                np.nan, np.nan, np.nan, np.nan, np.nan, np.nan,
                np.nan, np.nan, np.nan, False, 0, threshold_scope,
            )

        hard_low_mask = clean < hard_low
        hard_high_mask = clean > hard_high
        soft_low_mask = clean < soft_low
        soft_high_mask = clean > soft_high
        hard = hard_low_mask | hard_high_mask
        soft = soft_low_mask | soft_high_mask
        hard_full = np.zeros(len(x), dtype=bool)
        hard_full[valid] = hard
        runs = self._run_lengths(hard_full)
        magnitude = np.maximum(hard_low - clean, 0.0) + np.maximum(clean - hard_high, 0.0)
        return ValueEvidence(
            sensor=sensor,
            sensor_type=sensor_type,
            hard_low=hard_low,
            hard_high=hard_high,
            soft_low=soft_low,
            soft_high=soft_high,
            hard_violation_count=int(hard.sum()),
            soft_violation_count=int(soft.sum()),
            hard_low_violation_count=int(hard_low_mask.sum()),
            hard_high_violation_count=int(hard_high_mask.sum()),
            soft_low_violation_count=int(soft_low_mask.sum()),
            soft_high_violation_count=int(soft_high_mask.sum()),
            n_samples=int(len(clean)),
            hard_violation_rate=float(hard.mean()),
            soft_violation_rate=float(soft.mean()),
            hard_low_violation_rate=float(hard_low_mask.mean()),
            hard_high_violation_rate=float(hard_high_mask.mean()),
            soft_low_violation_rate=float(soft_low_mask.mean()),
            soft_high_violation_rate=float(soft_high_mask.mean()),
            max_violation_magnitude=float(magnitude.max()),
            max_soft_low_exceedance=float(np.maximum(soft_low - clean, 0.0).max()),
            max_soft_high_exceedance=float(np.maximum(clean - soft_high, 0.0).max()),
            out_of_instrument=bool(((clean < self.instrument_low) | (clean > self.instrument_high)).any()),
            consecutive_hard_max_min=max(runs, default=0),
            threshold_scope=threshold_scope,
        )

    @staticmethod
    def _run_lengths(mask: np.ndarray) -> list[int]:
        runs, current = [], 0
        for value in mask:
            if value:
                current += 1
            elif current:
                runs.append(current)
                current = 0
        if current:
            runs.append(current)
        return runs
