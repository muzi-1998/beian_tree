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
    soft_low: float | None
    soft_high: float | None
    effective_soft_low: float | None
    zero_equivalence_low: float | None
    hard_violation_count: int
    soft_violation_count: int
    hard_low_violation_count: int
    hard_high_violation_count: int
    soft_low_violation_count: int
    soft_high_violation_count: int
    physical_low_violation_count: int
    zero_equivalent_count: int
    zero_offset_warning_count: int
    severe_negative_count: int
    n_samples: int
    hard_violation_rate: float
    soft_violation_rate: float
    hard_low_violation_rate: float
    hard_high_violation_rate: float
    soft_low_violation_rate: float
    soft_high_violation_rate: float
    physical_low_violation_rate: float
    zero_equivalent_rate: float
    zero_offset_warning_rate: float
    severe_negative_rate: float
    max_violation_magnitude: float
    max_soft_low_exceedance: float
    max_soft_high_exceedance: float
    max_physical_low_exceedance: float
    out_of_instrument: bool
    consecutive_hard_max_min: int
    threshold_scope: str
    soft_sensitivity_anchor: str
    soft_high_mode: str
    soft_high_evaluable_count: int
    soft_high_evaluable_fraction: float
    soft_high_violation_rate_evaluable: float
    dynamic_soft_high_min: float
    dynamic_soft_high_median: float
    dynamic_soft_high_max: float
    soft_high_scored: bool


class ValueRangeChecker:
    def __init__(self, thresholds: ThresholdStore, instrument_low: float, instrument_high: float):
        self.thresholds = thresholds
        self.instrument_low = instrument_low
        self.instrument_high = instrument_high

    def check(
        self,
        x: np.ndarray,
        sensor: str,
        sensor_type: str,
        dynamic_soft_high: np.ndarray | None = None,
        soft_high_mode: str | None = None,
        score_soft_high: bool = True,
    ) -> ValueEvidence:
        hard_low, hard_high = self.thresholds.hard_bounds(sensor_type, sensor)
        soft_low, soft_high = self.thresholds.soft_bounds(sensor_type, sensor)
        zero_equivalence_low = self.thresholds.zero_equivalence_low(sensor)
        effective_soft_low = (
            zero_equivalence_low if zero_equivalence_low is not None else soft_low
        )
        threshold_scope = (
            "sensor_override"
            if (soft_low, soft_high) != self.thresholds.soft_bounds(sensor_type)
            or zero_equivalence_low is not None
            else "sensor_type"
        )
        sensitivity_anchor = self.thresholds.soft_sensitivity_anchor(sensor_type, sensor)
        if dynamic_soft_high is not None:
            dynamic_soft_high = np.asarray(dynamic_soft_high, dtype=float)
            if dynamic_soft_high.shape != np.asarray(x).shape:
                raise ValueError("dynamic_soft_high must have the same shape as x")
            active_high_mode = soft_high_mode or "dynamic"
        elif soft_high is not None:
            active_high_mode = soft_high_mode or "static"
        else:
            active_high_mode = "not_applicable"
        valid = np.isfinite(x)
        clean = x[valid]
        if not len(clean):
            return ValueEvidence(
                sensor=sensor,
                sensor_type=sensor_type,
                hard_low=hard_low,
                hard_high=hard_high,
                soft_low=soft_low,
                soft_high=soft_high,
                effective_soft_low=effective_soft_low,
                zero_equivalence_low=zero_equivalence_low,
                hard_violation_count=0,
                soft_violation_count=0,
                hard_low_violation_count=0,
                hard_high_violation_count=0,
                soft_low_violation_count=0,
                soft_high_violation_count=0,
                physical_low_violation_count=0,
                zero_equivalent_count=0,
                zero_offset_warning_count=0,
                severe_negative_count=0,
                n_samples=0,
                hard_violation_rate=np.nan,
                soft_violation_rate=np.nan,
                hard_low_violation_rate=np.nan,
                hard_high_violation_rate=np.nan,
                soft_low_violation_rate=np.nan,
                soft_high_violation_rate=np.nan,
                physical_low_violation_rate=np.nan,
                zero_equivalent_rate=np.nan,
                zero_offset_warning_rate=np.nan,
                severe_negative_rate=np.nan,
                max_violation_magnitude=np.nan,
                max_soft_low_exceedance=np.nan,
                max_soft_high_exceedance=np.nan,
                max_physical_low_exceedance=np.nan,
                out_of_instrument=False,
                consecutive_hard_max_min=0,
                threshold_scope=threshold_scope,
                soft_sensitivity_anchor=sensitivity_anchor,
                soft_high_mode=active_high_mode,
                soft_high_evaluable_count=0,
                soft_high_evaluable_fraction=np.nan,
                soft_high_violation_rate_evaluable=np.nan,
                dynamic_soft_high_min=np.nan,
                dynamic_soft_high_median=np.nan,
                dynamic_soft_high_max=np.nan,
                soft_high_scored=bool(score_soft_high and active_high_mode != "not_applicable"),
            )

        hard_low_mask = clean < hard_low
        hard_high_mask = clean > hard_high
        soft_low_mask = (
            clean < effective_soft_low
            if effective_soft_low is not None
            else np.zeros(len(clean), dtype=bool)
        )
        if dynamic_soft_high is not None:
            high_values = dynamic_soft_high[valid]
            high_evaluable = np.isfinite(high_values)
            soft_high_mask = high_evaluable & (clean > high_values)
            finite_high = high_values[high_evaluable]
        elif soft_high is not None:
            high_evaluable = np.ones(len(clean), dtype=bool)
            soft_high_mask = clean > soft_high
            finite_high = np.full(len(clean), soft_high, dtype=float)
        else:
            high_evaluable = np.zeros(len(clean), dtype=bool)
            soft_high_mask = np.zeros(len(clean), dtype=bool)
            finite_high = np.array([], dtype=float)
        physical_low_mask = (
            clean < soft_low
            if soft_low is not None
            else np.zeros(len(clean), dtype=bool)
        )
        if zero_equivalence_low is None:
            zero_equivalent_mask = np.zeros(len(clean), dtype=bool)
            zero_offset_mask = np.zeros(len(clean), dtype=bool)
            severe_negative_mask = np.zeros(len(clean), dtype=bool)
        else:
            zero_equivalent_mask = (clean >= zero_equivalence_low) & (clean < 0.0)
            zero_offset_mask = (clean >= hard_low) & (clean < zero_equivalence_low)
            severe_negative_mask = clean < hard_low
        hard = hard_low_mask | hard_high_mask
        soft = soft_low_mask | (soft_high_mask if score_soft_high else False)
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
            effective_soft_low=effective_soft_low,
            zero_equivalence_low=zero_equivalence_low,
            hard_violation_count=int(hard.sum()),
            soft_violation_count=int(soft.sum()),
            hard_low_violation_count=int(hard_low_mask.sum()),
            hard_high_violation_count=int(hard_high_mask.sum()),
            soft_low_violation_count=int(soft_low_mask.sum()),
            soft_high_violation_count=int(soft_high_mask.sum()),
            physical_low_violation_count=int(physical_low_mask.sum()),
            zero_equivalent_count=int(zero_equivalent_mask.sum()),
            zero_offset_warning_count=int(zero_offset_mask.sum()),
            severe_negative_count=int(severe_negative_mask.sum()),
            n_samples=int(len(clean)),
            hard_violation_rate=float(hard.mean()),
            soft_violation_rate=float(soft.mean()),
            hard_low_violation_rate=float(hard_low_mask.mean()),
            hard_high_violation_rate=float(hard_high_mask.mean()),
            soft_low_violation_rate=float(soft_low_mask.mean()),
            soft_high_violation_rate=float(soft_high_mask.mean()),
            physical_low_violation_rate=float(physical_low_mask.mean()),
            zero_equivalent_rate=float(zero_equivalent_mask.mean()),
            zero_offset_warning_rate=float(zero_offset_mask.mean()),
            severe_negative_rate=float(severe_negative_mask.mean()),
            max_violation_magnitude=float(magnitude.max()),
            max_soft_low_exceedance=(
                float(np.maximum(effective_soft_low - clean, 0.0).max())
                if effective_soft_low is not None
                else 0.0
            ),
            max_soft_high_exceedance=(
                float(np.maximum(clean[high_evaluable] - finite_high, 0.0).max())
                if high_evaluable.any()
                else np.nan
            ),
            max_physical_low_exceedance=(
                float(np.maximum(soft_low - clean, 0.0).max())
                if soft_low is not None
                else 0.0
            ),
            out_of_instrument=bool(((clean < self.instrument_low) | (clean > self.instrument_high)).any()),
            consecutive_hard_max_min=max(runs, default=0),
            threshold_scope=(
                "temperature_conditioned_position_template"
                if dynamic_soft_high is not None
                else threshold_scope
            ),
            soft_sensitivity_anchor=sensitivity_anchor,
            soft_high_mode=active_high_mode,
            soft_high_evaluable_count=int(high_evaluable.sum()),
            soft_high_evaluable_fraction=float(high_evaluable.mean()),
            soft_high_violation_rate_evaluable=(
                float(soft_high_mask[high_evaluable].mean())
                if high_evaluable.any()
                else np.nan
            ),
            dynamic_soft_high_min=float(finite_high.min()) if len(finite_high) else np.nan,
            dynamic_soft_high_median=float(np.median(finite_high)) if len(finite_high) else np.nan,
            dynamic_soft_high_max=float(finite_high.max()) if len(finite_high) else np.nan,
            soft_high_scored=bool(score_soft_high and active_high_mode != "not_applicable"),
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
