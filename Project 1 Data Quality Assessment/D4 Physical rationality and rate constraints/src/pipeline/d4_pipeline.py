"""Independent D4 physical-plausibility and rate-constraint pipeline."""

from __future__ import annotations

import json
from typing import Iterator

import numpy as np
import pandas as pd

from src.d4_physical.aggregator import D4Aggregator
from src.d4_physical.boundary_features import BoundaryFeatureExtractor
from src.d4_physical.rate_constraint_checker import RateConstraintChecker
from src.d4_physical.scorer import D4ScoreMapper
from src.d4_physical.threshold_store import ThresholdStore
from src.d4_physical.value_range_checker import ValueRangeChecker
from src.pipeline.rate_context import compute_rate_context
from src.version import MAPPING_VERSION, RATE_UTILS_VERSION, THRESHOLD_VERSION


class D4Pipeline:
    def __init__(
        self,
        df_main: pd.DataFrame,
        sensors: list[str],
        sensor_meta: list[dict],
        thresholds: ThresholdStore,
        configs: dict,
        run_id: str,
    ):
        self.df_main = df_main
        self.sensors = sensors
        self.sensor_meta = {item["id"]: item for item in sensor_meta}
        self.sensor_pool_map = {item["id"]: item["pool"] for item in sensor_meta}
        self.thresholds = thresholds
        self.configs = configs
        self.run_id = run_id

        bounds_cfg = configs["physical_bounds"]["sensors"]
        self.value_checkers = {
            sensor_type: ValueRangeChecker(
                thresholds,
                cfg["instrument_range_low"],
                cfg["instrument_range_high"],
            )
            for sensor_type, cfg in bounds_cfg.items()
        }
        self.rate_checker = RateConstraintChecker(thresholds, configs["rate_limits"])
        self.boundary_extractor = BoundaryFeatureExtractor(
            thresholds,
            sticking_relative_margin=configs["rules"]["boundary_sticking"]["threshold_relative_margin"],
        )
        self.scorer = D4ScoreMapper(configs["mapping"])
        self.aggregator = D4Aggregator(configs["rules"], configs["mapping"])

    def _iter_windows(self, window_min: int, stride_min: int) -> Iterator[tuple[pd.Timestamp, pd.DataFrame]]:
        if self.df_main.empty:
            return
        freq = pd.Timedelta(minutes=1)
        start = self.df_main.index[0]
        end_exclusive = self.df_main.index[-1] + freq
        anchor = start + pd.Timedelta(minutes=window_min)
        stride = pd.Timedelta(minutes=stride_min)
        window = pd.Timedelta(minutes=window_min)
        while anchor <= end_exclusive:
            mask = (self.df_main.index >= anchor - window) & (self.df_main.index < anchor)
            yield anchor, self.df_main.loc[mask]
            anchor += stride

    def run(self, window_min: int = 120, stride_min: int = 120, max_windows: int | None = None) -> dict:
        rows = {name: [] for name in ("main_scores", "value_bounds", "rate_constraint", "boundary_features", "events")}
        common_versions = json.dumps(
            {
                "rate": RATE_UTILS_VERSION,
                "benchmark": self.thresholds.benchmark.version,
            },
            sort_keys=True,
        )

        for window_index, (anchor_ts, window_df) in enumerate(self._iter_windows(window_min, stride_min)):
            rate_context = compute_rate_context(
                window_df,
                self.sensors,
                self.sensor_pool_map,
                self.configs["rate_limits"],
            )
            for sensor in self.sensors:
                if sensor not in window_df:
                    continue
                sensor_type = self.sensor_meta[sensor]["type"]
                values = window_df[sensor].to_numpy(dtype=float)
                value_evidence = self.value_checkers[sensor_type].check(values, sensor, sensor_type)
                neighbor_sync, parallel_sync = rate_context.get(sensor, (0.0, 0.0))
                rate_evidence = self.rate_checker.check(
                    values,
                    sensor,
                    sensor_type,
                    neighbor_sync_score=neighbor_sync,
                    parallel_sync_score=parallel_sync,
                )
                boundary = self.boundary_extractor.compute(values, sensor, sensor_type)
                sub = self.scorer.map(value_evidence, rate_evidence)
                result = self.aggregator.aggregate(
                    anchor_ts,
                    sensor,
                    sensor_type,
                    sub,
                    value_evidence,
                    rate_evidence,
                    expected_samples=len(window_df),
                )

                rows["main_scores"].append({
                    "ts": anchor_ts,
                    "window_min": window_min,
                    "stride_min": stride_min,
                    "sensor_id": sensor,
                    "Q_value_hard": result.Q_value_hard,
                    "Q_value_soft": result.Q_value_soft,
                    "Q_rate": result.Q_rate,
                    "D4_base": result.D4_base,
                    "D4_total": result.D4_total,
                    "evidence_status": result.evidence_status,
                    "n_expected": result.n_expected,
                    "n_observed": result.n_observed,
                    "observed_fraction": result.observed_fraction,
                    "dominant_physical_issue": result.dominant_physical_issue,
                    "veto_flag": result.veto_flag,
                    "veto_reason": result.veto_reason,
                    "process_coherent_shock": result.process_coherent_shock,
                    "boundary_diagnostic_only": True,
                    "threshold_version": THRESHOLD_VERSION,
                    "mapping_version": MAPPING_VERSION,
                    "run_id": self.run_id,
                    "common_layer_versions": common_versions,
                    "usable_tag": result.usable_tag,
                })
                rows["value_bounds"].append({
                    "ts": anchor_ts,
                    "sensor_id": sensor,
                    "n_samples": value_evidence.n_samples,
                    "hard_low": value_evidence.hard_low,
                    "hard_high": value_evidence.hard_high,
                    "soft_low": value_evidence.soft_low,
                    "soft_high": value_evidence.soft_high,
                    "hard_violation_count": value_evidence.hard_violation_count,
                    "soft_violation_count": value_evidence.soft_violation_count,
                    "hard_violation_rate": value_evidence.hard_violation_rate,
                    "soft_violation_rate": value_evidence.soft_violation_rate,
                    "max_violation_magnitude": value_evidence.max_violation_magnitude,
                    "out_of_instrument": value_evidence.out_of_instrument,
                    "consecutive_hard_max_min": value_evidence.consecutive_hard_max_min,
                    "threshold_version": THRESHOLD_VERSION,
                    "run_id": self.run_id,
                })
                rows["rate_constraint"].append({
                    "ts": anchor_ts,
                    "sensor_id": sensor,
                    "n_samples": rate_evidence.n_samples,
                    "rate_method": rate_evidence.rate_method,
                    "rate_utils_version": rate_evidence.rate_utils_version,
                    "rate_limit_soft": rate_evidence.rate_limit_soft,
                    "rate_limit_hard": rate_evidence.rate_limit_hard,
                    "rate_soft_violation_rate": rate_evidence.rate_soft_violation_rate,
                    "rate_hard_violation_rate": rate_evidence.rate_hard_violation_rate,
                    "rate_severity": rate_evidence.max_rate_severity,
                    "rate_hard_consec_max_min": rate_evidence.rate_hard_consec_max_min,
                    "neighbor_sync_score": rate_evidence.neighbor_sync_score,
                    "parallel_sync_score": rate_evidence.parallel_sync_score,
                    "process_coherent_shock": rate_evidence.shock_candidate,
                    "diagnostic_only_sync": True,
                    "rate_mapping_version": MAPPING_VERSION,
                    "run_id": self.run_id,
                })
                rows["boundary_features"].append({
                    "ts": anchor_ts,
                    "sensor_id": sensor,
                    "n_samples": boundary.n_samples,
                    "boundary_sticking_rate": boundary.boundary_sticking_rate,
                    "boundary_sticking_low_rate": boundary.boundary_sticking_low_rate,
                    "boundary_sticking_high_rate": boundary.boundary_sticking_high_rate,
                    "tail_rate_low": boundary.tail_rate_low,
                    "tail_rate_high": boundary.tail_rate_high,
                    "fixed_threshold_low_value": boundary.fixed_threshold_low_value,
                    "fixed_threshold_high_value": boundary.fixed_threshold_high_value,
                    "fixed_threshold_source_low": boundary.fixed_threshold_source_low,
                    "fixed_threshold_source_high": boundary.fixed_threshold_source_high,
                    "fixed_threshold_version": boundary.fixed_threshold_version,
                    "boundary_dominant_reason": boundary.boundary_dominant_reason,
                    "included_in_D4_score": False,
                    "run_id": self.run_id,
                })

                if result.evidence_status == "sufficient" and (result.D4_total < 3.0 or result.veto_flag):
                    if "instrument_range" in result.veto_reason:
                        event_type = "instrument_range"
                    elif "hard_violation" in result.veto_reason:
                        event_type = "hard_bound"
                    elif "rate_persistent" in result.veto_reason or result.dominant_physical_issue == "rate":
                        event_type = "rate_violation"
                    elif result.dominant_physical_issue == "soft_bound":
                        event_type = "soft_bound"
                    else:
                        event_type = "low_quality_window"
                    rows["events"].append({
                        "event_id": f"E{len(rows['events']):06d}",
                        "sensor_id": sensor,
                        "event_type": event_type,
                        "start_ts": anchor_ts - pd.Timedelta(minutes=window_min),
                        "end_ts": anchor_ts,
                        "duration_min": window_min,
                        "min_D4": result.D4_total,
                        "veto_triggered": result.veto_flag,
                        "veto_reason": result.veto_reason,
                        "process_coherent_shock": result.process_coherent_shock,
                        "review_priority": "high" if result.D4_total < 2.0 else "medium",
                        "run_id": self.run_id,
                    })

            if max_windows is not None and window_index + 1 >= max_windows:
                break

        return {name: pd.DataFrame(values) for name, values in rows.items()}
