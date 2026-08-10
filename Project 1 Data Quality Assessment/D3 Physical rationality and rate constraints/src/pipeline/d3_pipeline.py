"""Independent D3 physical-plausibility and rate-constraint pipeline."""

from __future__ import annotations

import json
from typing import Iterator

import numpy as np
import pandas as pd

from src.d3_physical.aggregator import D3Aggregator
from src.d3_physical.boundary_features import BoundaryFeatureExtractor
from src.d3_physical.do_temperature_envelope import temperature_conditioned_upper
from src.d3_physical.rate_constraint_checker import RateConstraintChecker
from src.d3_physical.scorer import D3ScoreMapper
from src.d3_physical.threshold_store import ThresholdStore
from src.d3_physical.value_range_checker import ValueRangeChecker
from src.pipeline.rate_context import compute_rate_context
from src.version import MAPPING_VERSION, RATE_UTILS_VERSION, THRESHOLD_VERSION


class D3Pipeline:
    def __init__(
        self,
        df_main: pd.DataFrame,
        sensors: list[str],
        sensor_meta: list[dict],
        thresholds: ThresholdStore,
        configs: dict,
        run_id: str,
        temperature_c: pd.Series | None = None,
    ):
        self.df_main = df_main
        self.sensors = sensors
        self.sensor_meta = {item["id"]: item for item in sensor_meta}
        self.sensor_pool_map = {item["id"]: item["pool"] for item in sensor_meta}
        self.thresholds = thresholds
        self.configs = configs
        self.run_id = run_id
        self.temperature_c = (
            temperature_c.reindex(df_main.index)
            if temperature_c is not None
            else pd.Series(np.nan, index=df_main.index, name="influent_temperature_C")
        )
        self.do_temperature_contract = configs["physical_bounds"][
            "operational_envelope_contract"
        ]["aerobic_do_temperature_conditioned_upper"]

        bounds_cfg = configs["physical_bounds"]["sensors"]
        self.value_checkers = {
            sensor_type: ValueRangeChecker(
                thresholds,
                cfg["instrument_veto_range_low"],
                cfg["instrument_veto_range_high"],
            )
            for sensor_type, cfg in bounds_cfg.items()
        }
        self.rate_checker = RateConstraintChecker(thresholds, configs["rate_limits"])
        self.boundary_extractor = BoundaryFeatureExtractor(
            thresholds,
            sticking_relative_margin=configs["rules"]["boundary_sticking"]["threshold_relative_margin"],
        )
        self.scorer = D3ScoreMapper(configs["mapping"])
        self.aggregator = D3Aggregator(configs["rules"], configs["mapping"])

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
                temperature_values = self.temperature_c.reindex(window_df.index).to_numpy(dtype=float)
                dynamic_upper, upper_status = temperature_conditioned_upper(
                    temperature_values,
                    self.sensor_meta[sensor],
                    self.do_temperature_contract,
                )
                position = str(self.sensor_meta[sensor]["position"])
                score_dynamic_upper = (
                    dynamic_upper is not None
                    and position
                    in self.do_temperature_contract["calibration"]["scored_positions"]
                )
                include_soft_high_in_score = (
                    score_dynamic_upper if dynamic_upper is not None else True
                )
                if dynamic_upper is not None and upper_status in {
                    "evaluated",
                    "partially_evaluated",
                }:
                    upper_status = f"{upper_status}_{'scored' if score_dynamic_upper else 'diagnostic_only'}"
                value_evidence = self.value_checkers[sensor_type].check(
                    values,
                    sensor,
                    sensor_type,
                    dynamic_soft_high=dynamic_upper,
                    soft_high_mode=(
                        "temperature_conditioned_influent_proxy"
                        if dynamic_upper is not None
                        else None
                    ),
                    score_soft_high=include_soft_high_in_score,
                )
                context = rate_context[sensor]
                rate_evidence = self.rate_checker.check(
                    values,
                    sensor,
                    sensor_type,
                    neighbor_sync_score=context.neighbor_sync_score,
                    parallel_sync_score=context.parallel_sync_score,
                    process_coherent_mask=context.coherent_mask,
                    precomputed_rate=context.rate_series,
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
                    "Q_persistent_rate": result.Q_persistent_rate,
                    "Q_persistent_rate_soft_only": result.Q_persistent_rate_soft_only,
                    "Q_persistent_rate_hard": result.Q_persistent_rate_hard,
                    "Q_rate": result.Q_rate,
                    "Q_rate_alias_status": "deprecated_alias_of_Q_persistent_rate",
                    "D3_base": result.D3_base,
                    "D3_total": result.D3_total,
                    "evidence_status": result.evidence_status,
                    "n_expected": result.n_expected,
                    "n_observed": result.n_observed,
                    "observed_fraction": result.observed_fraction,
                    "temperature_upper_status": upper_status,
                    "temperature_upper_evaluable_fraction": value_evidence.soft_high_evaluable_fraction,
                    "D3_evidence_scope": (
                        "full_temperature_conditioned_scored"
                        if upper_status == "evaluated_scored"
                        else "partial_temperature_conditioned_scored"
                        if upper_status == "partially_evaluated_scored"
                        else "temperature_conditioned_diagnostic_only"
                        if upper_status == "evaluated_diagnostic_only"
                        else "partial_temperature_conditioned_diagnostic_only"
                        if upper_status == "partially_evaluated_diagnostic_only"
                        else "partial_temperature_unavailable"
                        if upper_status == "temperature_unavailable"
                        else "not_applicable"
                    ),
                    "dominant_physical_issue": result.dominant_physical_issue,
                    "veto_flag": result.veto_flag,
                    "veto_reason": result.veto_reason,
                    "data_veto_flag": result.data_veto_flag,
                    "operational_warning_flag": result.operational_warning_flag,
                    "D3_gate_status": result.D3_gate_status,
                    "process_coherent_shock": result.process_coherent_shock,
                    "process_coherence_role": "attribution_guard_not_veto",
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
                    "effective_soft_low": value_evidence.effective_soft_low,
                    "zero_equivalence_low": value_evidence.zero_equivalence_low,
                    "hard_violation_count": value_evidence.hard_violation_count,
                    "soft_violation_count": value_evidence.soft_violation_count,
                    "hard_low_violation_count": value_evidence.hard_low_violation_count,
                    "hard_high_violation_count": value_evidence.hard_high_violation_count,
                    "soft_low_violation_count": value_evidence.soft_low_violation_count,
                    "soft_high_violation_count": value_evidence.soft_high_violation_count,
                    "physical_low_violation_count": value_evidence.physical_low_violation_count,
                    "zero_equivalent_count": value_evidence.zero_equivalent_count,
                    "zero_offset_warning_count": value_evidence.zero_offset_warning_count,
                    "severe_negative_count": value_evidence.severe_negative_count,
                    "hard_violation_rate": value_evidence.hard_violation_rate,
                    "soft_violation_rate": value_evidence.soft_violation_rate,
                    "hard_low_violation_rate": value_evidence.hard_low_violation_rate,
                    "hard_high_violation_rate": value_evidence.hard_high_violation_rate,
                    "soft_low_violation_rate": value_evidence.soft_low_violation_rate,
                    "soft_high_violation_rate": value_evidence.soft_high_violation_rate,
                    "soft_high_violation_rate_evaluable": value_evidence.soft_high_violation_rate_evaluable,
                    "soft_high_evaluable_count": value_evidence.soft_high_evaluable_count,
                    "soft_high_evaluable_fraction": value_evidence.soft_high_evaluable_fraction,
                    "soft_high_mode": value_evidence.soft_high_mode,
                    "dynamic_soft_high_min": value_evidence.dynamic_soft_high_min,
                    "dynamic_soft_high_median": value_evidence.dynamic_soft_high_median,
                    "dynamic_soft_high_max": value_evidence.dynamic_soft_high_max,
                    "soft_high_scored": value_evidence.soft_high_scored,
                    "temperature_upper_diagnostic_warning": bool(
                        value_evidence.soft_high_violation_count > 0
                    ),
                    "physical_low_violation_rate": value_evidence.physical_low_violation_rate,
                    "zero_equivalent_rate": value_evidence.zero_equivalent_rate,
                    "zero_offset_warning_rate": value_evidence.zero_offset_warning_rate,
                    "severe_negative_rate": value_evidence.severe_negative_rate,
                    "max_violation_magnitude": value_evidence.max_violation_magnitude,
                    "max_soft_low_exceedance": value_evidence.max_soft_low_exceedance,
                    "max_soft_high_exceedance": value_evidence.max_soft_high_exceedance,
                    "max_physical_low_exceedance": value_evidence.max_physical_low_exceedance,
                    "out_of_instrument": value_evidence.out_of_instrument,
                    "consecutive_hard_max_min": value_evidence.consecutive_hard_max_min,
                    "threshold_scope": value_evidence.threshold_scope,
                    "soft_sensitivity_anchor": value_evidence.soft_sensitivity_anchor,
                    "operational_threshold_status": (
                        "frozen_site_calibrated_temperature_conditioned_warning"
                        if value_evidence.soft_high_mode == "temperature_conditioned_influent_proxy"
                        else "provisional_expert_prior"
                    ),
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
                    "rate_soft_point_violation_rate": rate_evidence.rate_soft_point_violation_rate,
                    "rate_hard_point_violation_rate": rate_evidence.rate_hard_point_violation_rate,
                    "rate_soft_violation_rate": rate_evidence.rate_soft_violation_rate,
                    "rate_soft_only_violation_rate": rate_evidence.rate_soft_only_violation_rate,
                    "rate_hard_violation_rate": rate_evidence.rate_hard_violation_rate,
                    "rate_severity": rate_evidence.max_rate_severity,
                    "rate_hard_consec_max_min": rate_evidence.rate_hard_consec_max_min,
                    "rate_hard_consec_raw_max_min": rate_evidence.rate_hard_consec_raw_max_min,
                    "persistent_rate_event_count": rate_evidence.persistent_rate_event_count,
                    "persistent_soft_only_event_count": rate_evidence.persistent_soft_only_event_count,
                    "persistent_hard_event_count": rate_evidence.persistent_hard_event_count,
                    "impulse_return_event_count": rate_evidence.impulse_return_event_count,
                    "impulse_return_excluded_fraction": rate_evidence.impulse_return_excluded_fraction,
                    "process_coherence_guarded_fraction": rate_evidence.process_coherence_guarded_fraction,
                    "process_coherence_guarded_points": rate_evidence.process_coherence_guarded_points,
                    "neighbor_sync_score": rate_evidence.neighbor_sync_score,
                    "parallel_sync_score": rate_evidence.parallel_sync_score,
                    "process_coherent_shock": rate_evidence.shock_candidate,
                    "process_coherence_role": "attribution_guard_not_veto",
                    "rate_construct": "mutually_exclusive_soft_only_and_hard_persistent_rate",
                    "rate_threshold_status": "provisional_expert_prior",
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
                    "included_in_D3_score": False,
                    "run_id": self.run_id,
                })

                if result.evidence_status == "sufficient" and (
                    result.D3_total < 3.0
                    or result.veto_flag
                    or result.process_coherent_shock
                    or rate_evidence.rate_soft_only_violation_rate > 0
                    or rate_evidence.rate_hard_violation_rate > 0
                ):
                    if "instrument_range" in result.veto_reason:
                        event_type = "instrument_range"
                    elif "hard_violation" in result.veto_reason:
                        event_type = "hard_bound"
                    elif rate_evidence.rate_hard_violation_rate > 0:
                        event_type = "persistent_rate_hard"
                    elif rate_evidence.rate_soft_only_violation_rate > 0:
                        event_type = "persistent_rate_soft_only"
                    elif result.dominant_physical_issue == "soft_bound":
                        event_type = "soft_bound"
                    elif result.process_coherent_shock:
                        event_type = "process_coherent_shock"
                    else:
                        event_type = "low_quality_window"
                    rows["events"].append({
                        "event_id": f"E{len(rows['events']):06d}",
                        "sensor_id": sensor,
                        "event_type": event_type,
                        "start_ts": anchor_ts - pd.Timedelta(minutes=window_min),
                        "end_ts": anchor_ts,
                        "duration_min": window_min,
                        "min_D3": result.D3_total,
                        "veto_triggered": result.veto_flag,
                        "veto_reason": result.veto_reason,
                        "process_coherent_shock": result.process_coherent_shock,
                        "review_priority": (
                            "high"
                            if result.D3_total < 2.0
                            else "low"
                            if event_type == "persistent_rate_soft_only"
                            else "medium"
                        ),
                        "run_id": self.run_id,
                    })

            if max_windows is not None and window_index + 1 >= max_windows:
                break

        return {name: pd.DataFrame(values) for name, values in rows.items()}
