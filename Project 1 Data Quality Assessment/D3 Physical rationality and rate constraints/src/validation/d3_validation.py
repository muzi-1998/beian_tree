"""Generate D3 v2.6 boundary, persistence, and construct-validity evidence."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.d3_physical.rate_constraint_checker import RateConstraintChecker
from src.d3_physical.scorer import logistic_zero_anchored
from src.pipeline.rate_context import compute_rate_context
from src.validation.do_temperature_validation import build_temperature_envelope_audit
from src.validation.interval_scaling import (
    INTERVAL_SCALING_VERSION,
    interval_warning_mask,
    scale_interval,
)


def _persistent_rate_scores(evidence, mapping_cfg: dict) -> tuple[float, float, float]:
    mapping = mapping_cfg["Q_persistent_rate"]
    q_soft_only = logistic_zero_anchored(
        evidence.rate_soft_only_violation_rate,
        mapping["soft_only"]["x0"],
        mapping["soft_only"]["k"],
    )
    q_hard = logistic_zero_anchored(
        evidence.rate_hard_violation_rate,
        mapping["hard"]["x0"],
        mapping["hard"]["k"],
    )
    weights = mapping["component_weights"]
    combined = weights["soft_only"] * q_soft_only + weights["hard"] * q_hard
    return float(q_soft_only), float(q_hard), float(combined)


def _legacy_v23_rate_score(rate: float, rules_cfg: dict) -> float:
    """Reconstruct v2.3 Q_rate from all hard point violations."""
    config = rules_cfg.get("legacy_v2_3_rate_mapping", {"x0": 0.05, "k": 20.0})
    return logistic_zero_anchored(rate, float(config["x0"]), float(config["k"]))


def _operational_envelope_family(sensor: str) -> str:
    if sensor.startswith("DO_") and not sensor.endswith("_4"):
        return "aerobic_do"
    if sensor.startswith("ORP_"):
        return "orp"
    return "dedicated_route"


def _longest_true_run(mask: pd.Series) -> int:
    longest = current = 0
    for value in mask.fillna(False).astype(bool):
        current = current + 1 if value else 0
        longest = max(longest, current)
    return int(longest)


def _season(index: pd.DatetimeIndex) -> np.ndarray:
    month = index.month
    return np.select(
        [np.isin(month, [12, 1, 2]), np.isin(month, [6, 7, 8])],
        ["winter", "summer"],
        default="transition",
    )


def _event_jaccard(left: pd.Series, right: pd.Series) -> float:
    a = left.fillna(False).astype(bool).to_numpy()
    b = right.fillna(False).astype(bool).to_numpy()
    union = np.logical_or(a, b).sum()
    return float(np.logical_and(a, b).sum() / union) if union else 1.0


def _sample_windows(frame: pd.DataFrame, per_month: int = 4) -> list[tuple[pd.Timestamp, pd.DataFrame]]:
    selected: list[tuple[pd.Timestamp, pd.DataFrame]] = []
    months = frame.index.to_period("M")
    for month in months.unique():
        month_index = frame.index[months == month]
        eligible = month_index[month_index >= month_index.min() + pd.Timedelta(minutes=120)]
        if not len(eligible):
            continue
        positions = np.linspace(0, len(eligible) - 1, min(per_month, len(eligible)), dtype=int)
        for position in np.unique(positions):
            anchor = eligible[position]
            window = frame.loc[
                (frame.index >= anchor - pd.Timedelta(minutes=120)) & (frame.index < anchor)
            ]
            if len(window) == 120:
                selected.append((anchor, window))
    return selected


def _operational_diagnostics(
    frame: pd.DataFrame,
    sensor_meta: list[dict],
    physical_cfg: dict,
    results: dict,
) -> dict[str, pd.DataFrame]:
    value = results["value_bounds"]
    directional = (
        value.groupby("sensor_id", as_index=False)
        .agg(
            n_windows=("ts", "size"),
            soft_low_window_rate=("soft_low_violation_rate", lambda x: float(x.gt(0).mean())),
            soft_high_window_rate=("soft_high_violation_rate", lambda x: float(x.gt(0).mean())),
            mean_soft_low_rate=("soft_low_violation_rate", "mean"),
            mean_soft_high_rate=("soft_high_violation_rate", "mean"),
            max_soft_low_exceedance=("max_soft_low_exceedance", "max"),
            max_soft_high_exceedance=("max_soft_high_exceedance", "max"),
            physical_low_window_rate=("physical_low_violation_rate", lambda x: float(x.gt(0).mean())),
            zero_equivalent_window_rate=("zero_equivalent_rate", lambda x: float(x.gt(0).mean())),
            zero_offset_warning_window_rate=(
                "zero_offset_warning_rate", lambda x: float(x.gt(0).mean())
            ),
            severe_negative_window_rate=("severe_negative_rate", lambda x: float(x.gt(0).mean())),
            soft_low=("soft_low", "first"),
            soft_high=("soft_high", "first"),
            effective_soft_low=("effective_soft_low", "first"),
            zero_equivalence_low=("zero_equivalence_low", "first"),
            threshold_scope=("threshold_scope", "first"),
            soft_sensitivity_anchor=("soft_sensitivity_anchor", "first"),
        )
    )
    metadata = pd.DataFrame(sensor_meta).rename(columns={"id": "sensor_id"})
    directional = directional.merge(metadata, on="sensor_id", how="left")

    do_rows = []
    orp_rows = []
    season_labels = _season(frame.index)
    for sensor in frame.columns:
        values = frame[sensor]
        for season_name in ("summer", "transition", "winter"):
            sample = values[season_labels == season_name].dropna()
            if not len(sample):
                continue
            family = _operational_envelope_family(sensor)
            if family == "aerobic_do":
                meta = next(item for item in sensor_meta if item["id"] == sensor)
                do_rows.append(
                    {
                        "sensor_id": sensor,
                        "process_zone": meta["process_zone"],
                        "position": meta["position"],
                        "season": season_name,
                        "n": len(sample),
                        "p95": float(sample.quantile(0.95)),
                        "p99": float(sample.quantile(0.99)),
                        "maximum": float(sample.max()),
                        "distribution_role": "raw_context_only_temperature_envelope_audited_separately",
                    }
                )
            elif family == "orp":
                median = float(sample.median())
                mad_scale = float(1.4826 * (sample - median).abs().median())
                meta = next(item for item in sensor_meta if item["id"] == sensor)
                orp_rows.append(
                    {
                        "sensor_id": sensor,
                        "process_zone": meta["process_zone"],
                        "position": meta["position"],
                        "season": season_name,
                        "n": len(sample),
                        "median": median,
                        "mad_scale": mad_scale,
                        "robust_low_k3": median - 3.0 * mad_scale,
                        "robust_high_k3": median + 3.0 * mad_scale,
                        "p01": float(sample.quantile(0.01)),
                        "p99": float(sample.quantile(0.99)),
                        "below_minus_400_rate": float(sample.lt(-400.0).mean()),
                        "above_200_rate": float(sample.gt(200.0).mean()),
                        "envelope_role": "diagnostic_only_pending_site_review",
                    }
                )

    deadband_rows = []
    deadbands = physical_cfg["operational_envelope_contract"]["do4_zero_equivalence"][
        "sensitivity_values_mg_L"
    ]
    for sensor in ("DO_1_4", "DO_2_4"):
        values = frame[sensor].dropna()
        for deadband in deadbands:
            deadband_rows.append(
                {
                    "sensor_id": sensor,
                    "zero_equivalence_low_mg_L": float(deadband),
                    "n_observed": len(values),
                    "negative_value_rate": float(values.lt(0.0).mean()),
                    "zero_offset_warning_rate": float(values.lt(float(deadband)).mean()),
                    "minimum_observed": float(values.min()),
                    "role": "sensitivity_not_final_manufacturer_lock",
                }
            )

    monthly_rows = []
    for sensor in ("DO_1_4", "DO_2_4"):
        values = frame[sensor]
        for month, sample in values.groupby(values.index.to_period("M")):
            observed = sample.dropna()
            negative = observed[observed < 0.0]
            monthly_rows.append(
                {
                    "sensor_id": sensor,
                    "month": str(month),
                    "n_observed": int(len(observed)),
                    "negative_rate": float(observed.lt(0.0).mean()) if len(observed) else np.nan,
                    "negative_median": float(negative.median()) if len(negative) else np.nan,
                    "p01": float(observed.quantile(0.01)) if len(observed) else np.nan,
                    "minimum": float(observed.min()) if len(observed) else np.nan,
                    "longest_negative_run_min": _longest_true_run(sample.lt(0.0)),
                    "zero_equivalent_rate": (
                        float(((observed >= -0.05) & (observed < 0.0)).mean())
                        if len(observed) else np.nan
                    ),
                    "zero_offset_warning_rate": (
                        float(((observed >= -0.2) & (observed < -0.05)).mean())
                        if len(observed) else np.nan
                    ),
                    "severe_negative_rate": (
                        float(observed.lt(-0.2).mean()) if len(observed) else np.nan
                    ),
                }
            )

    parallel_rows = []
    paired = frame[["DO_1_4", "DO_2_4"]]
    for month, sample in paired.groupby(paired.index.to_period("M")):
        complete = sample.dropna()
        if complete.empty:
            continue
        negative_1 = complete["DO_1_4"] < 0.0
        negative_2 = complete["DO_2_4"] < 0.0
        zero_1 = complete["DO_1_4"].between(-0.05, 0.0, inclusive="left")
        zero_2 = complete["DO_2_4"].between(-0.05, 0.0, inclusive="left")
        parallel_rows.append(
            {
                "month": str(month),
                "n_paired": int(len(complete)),
                "DO_1_4_median": float(complete["DO_1_4"].median()),
                "DO_2_4_median": float(complete["DO_2_4"].median()),
                "negative_jaccard": _event_jaccard(negative_1, negative_2),
                "zero_equivalent_jaccard": _event_jaccard(zero_1, zero_2),
                "negative_rate_DO_1_4": float(negative_1.mean()),
                "negative_rate_DO_2_4": float(negative_2.mean()),
                "interpretation": "parallel_line_diagnostic_not_cross_sensor_scoring",
            }
        )
    return {
        "directional_window_burden": directional,
        "DO_seasonal_raw_distribution": pd.DataFrame(do_rows),
        "ORP_position_season_envelope": pd.DataFrame(orp_rows),
        "DO4_zero_eq_sensitivity": pd.DataFrame(deadband_rows),
        "DO4_monthly_zero_stability": pd.DataFrame(monthly_rows),
        "DO4_parallel_line_diagnostic": pd.DataFrame(parallel_rows),
    }


def _do4_zero_views(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for sensor in ("DO_1_4", "DO_2_4"):
        raw = frame[sensor]
        rows.append(
            pd.DataFrame(
                {
                    "timestamp": frame.index,
                    "sensor_id": sensor,
                    "DO_raw": raw.to_numpy(),
                    "DO_zero_equivalent_flag": raw.between(-0.05, 0.0, inclusive="left").to_numpy(),
                    "DO_zero_offset_warning_flag": raw.between(-0.2, -0.05, inclusive="left").to_numpy(),
                    "DO_severe_negative_flag": raw.lt(-0.2).to_numpy(),
                    "DO_physicalized": raw.clip(lower=0.0).to_numpy(),
                    "DO_physicalized_role": "downstream_process_calculation_only_not_D3_scoring",
                    "process_zone": "post_anoxic",
                }
            )
        )
    return pd.concat(rows, ignore_index=True)


def _wide_score_sheet(path: Path, sheet: str, value_name: str) -> pd.DataFrame:
    source = pd.read_excel(path, sheet_name=sheet)
    source["timestamp"] = pd.to_datetime(source["timestamp"]).dt.floor("h")
    return source.melt(
        id_vars="timestamp", var_name="sensor_id", value_name=value_name
    ).groupby(["timestamp", "sensor_id"], as_index=False)[value_name].min()


def _do4_candidate_upper_template(frame: pd.DataFrame, root: Path) -> pd.DataFrame:
    """Estimate validation-only DO4 candidates without changing production D3."""
    d1_path = root.parent / "D1 Sensor health" / "outputs" / "data" / "D1_main_scores_min.xlsx"
    d2_path = (
        root.parent
        / "D2 Temporal Continuity & Information Availability"
        / "artifacts"
        / "data"
        / "D2_main_scores_hourly.xlsx"
    )
    if not d1_path.exists() or not d2_path.exists():
        return pd.DataFrame(
            [{"status": "not_estimable_missing_frozen_D1_or_D2_release"}]
        )

    score_tables = [
        _wide_score_sheet(d1_path, sheet, name)
        for sheet, name in (
            ("D1_total_hourly", "D1_total"),
            ("Q_spike", "Q_spike"),
            ("Q_step", "Q_step"),
            ("Q_freeze", "Q_freeze"),
        )
    ]
    d1 = score_tables[0]
    for table in score_tables[1:]:
        d1 = d1.merge(table, on=["timestamp", "sensor_id"], how="inner")

    d2 = pd.read_excel(d2_path, sheet_name="D2_scores")
    timestamp_column = "timestamp" if "timestamp" in d2 else "Unnamed: 0"
    d2 = d2.rename(columns={timestamp_column: "timestamp"})
    d2["timestamp"] = pd.to_datetime(d2["timestamp"]).dt.floor("h")
    d2 = d2[["timestamp", "sensor_id", "D2_Strict", "usable_tag"]]
    d2 = d2.groupby(["timestamp", "sensor_id"], as_index=False).agg(
        D2_Strict=("D2_Strict", "min"),
        usable_tag=("usable_tag", "first"),
    )

    hourly = (
        frame[["DO_1_4", "DO_2_4"]]
        .resample("h")
        .median()
        .rename_axis("timestamp")
        .reset_index()
        .melt(id_vars="timestamp", var_name="sensor_id", value_name="DO_raw")
    )
    joined = hourly.merge(d1, on=["timestamp", "sensor_id"], how="left").merge(
        d2, on=["timestamp", "sensor_id"], how="left"
    )
    high_quality = (
        joined[["D1_total", "Q_spike", "Q_step", "Q_freeze", "D2_Strict"]]
        .ge(4.5)
        .all(axis=1)
        & joined["usable_tag"].isin(["train_ok", "train_ok_with_operational_warning"])
        & joined["DO_raw"].notna()
    )
    joined = joined[high_quality].copy()
    split = frame.index.min() + 0.70 * (frame.index.max() - frame.index.min())
    rows = []
    for sensor in ("DO_1_4", "DO_2_4"):
        sensor_data = joined[joined["sensor_id"] == sensor]
        calibration = sensor_data.loc[sensor_data["timestamp"] <= split, "DO_raw"]
        validation = sensor_data.loc[sensor_data["timestamp"] > split, "DO_raw"]
        if calibration.empty:
            rows.append(
                {
                    "sensor_id": sensor,
                    "status": "not_estimable_no_calibration_support",
                    "production_role": "disabled",
                }
            )
            continue
        median = float(calibration.median())
        mad_scale = float(1.4826 * (calibration - median).abs().median())
        p99 = float(calibration.quantile(0.99))
        candidate = float(max(p99, median + 3.0 * mad_scale))
        support_ok = len(calibration) >= 720 and len(validation) >= 168
        rows.append(
            {
                "sensor_id": sensor,
                "split_timestamp": split,
                "calibration_hours": int(len(calibration)),
                "validation_hours": int(len(validation)),
                "calibration_median_mg_L": median,
                "calibration_MAD_scale_mg_L": mad_scale,
                "calibration_p99_mg_L": p99,
                "candidate_upper_mg_L": candidate,
                "validation_warning_rate": (
                    float(validation.gt(candidate).mean()) if len(validation) else np.nan
                ),
                "validation_p99_mg_L": (
                    float(validation.quantile(0.99)) if len(validation) else np.nan
                ),
                "support_passed": support_ok,
                "status": (
                    "validation_candidate_support_passed"
                    if support_ok
                    else "insufficient_independent_support"
                ),
                "production_role": "disabled_not_consumed_by_D3_score",
                "calibration_filter": "D1_total,Q_spike,Q_step,Q_freeze,D2_Strict>=4.5",
                "D1_source_sha256": hashlib.sha256(d1_path.read_bytes()).hexdigest(),
                "D2_source_sha256": hashlib.sha256(d2_path.read_bytes()).hexdigest(),
            }
        )
    return pd.DataFrame(rows)


class _ScaledRateThresholds:
    def __init__(self, base, multiplier: float):
        self.base = base
        self.multiplier = multiplier

    def rate_limits(self, sensor_type: str) -> tuple[float, float]:
        soft, hard = self.base.rate_limits(sensor_type)
        return soft * self.multiplier, hard * self.multiplier


def _threshold_sensitivity(
    frame: pd.DataFrame,
    sensors: list[str],
    sensor_meta: list[dict],
    thresholds,
    physical_cfg: dict,
    rate_cfg: dict,
    mapping_cfg: dict,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    windows = _sample_windows(frame, per_month=4)
    pool_map = {item["id"]: item["pool"] for item in sensor_meta}
    multipliers = [0.8, 0.9, 1.0, 1.1, 1.2]
    boundary_rows = []
    rate_rows = []
    for multiplier in multipliers:
        scaled_rate_cfg = deepcopy(rate_cfg)
        for definition in scaled_rate_cfg["rate_limits"].values():
            definition["rate_soft"] *= multiplier
            definition["rate_hard"] *= multiplier
        rate_checker = RateConstraintChecker(
            _ScaledRateThresholds(thresholds, multiplier), scaled_rate_cfg
        )
        for anchor, window in windows:
            context = compute_rate_context(window, sensors, pool_map, scaled_rate_cfg)
            for sensor in sensors:
                sensor_type = sensor.split("_", 1)[0]
                values = window[sensor].to_numpy(dtype=float)
                finite = values[np.isfinite(values)]
                if len(finite):
                    physical_low, base_high = thresholds.soft_bounds(sensor_type, sensor)
                    zero_equivalence_low = thresholds.zero_equivalence_low(sensor)
                    effective_low = (
                        zero_equivalence_low
                        if zero_equivalence_low is not None
                        else physical_low
                    )
                    anchor_rule = thresholds.soft_sensitivity_anchor(sensor_type, sensor)
                    if base_high is None and anchor_rule != "none":
                        # Aerobic DO alpha sensitivity is evaluated in the
                        # temperature-specific audit, not as a static interval.
                        continue
                    low, high = scale_interval(
                        effective_low,
                        base_high,
                        multiplier,
                        anchor=anchor_rule,
                    )
                    warning_mask = interval_warning_mask(finite, low, high)
                    boundary_rows.append(
                        {
                            "timestamp": anchor,
                            "sensor_id": sensor,
                            "multiplier": multiplier,
                            "physical_soft_low": physical_low,
                            "zero_equivalence_low": zero_equivalence_low,
                            "effective_soft_low": low,
                            "soft_high": high,
                            "sensitivity_anchor": anchor_rule,
                            "sensitivity_code_version": INTERVAL_SCALING_VERSION,
                            "warning": bool(warning_mask.any()),
                            "violation_fraction": float(warning_mask.mean()),
                        }
                    )
                rate_context = context[sensor]
                evidence = rate_checker.check(
                    values,
                    sensor,
                    sensor_type,
                    neighbor_sync_score=rate_context.neighbor_sync_score,
                    parallel_sync_score=rate_context.parallel_sync_score,
                    process_coherent_mask=rate_context.coherent_mask,
                    precomputed_rate=rate_context.rate_series,
                )
                q_soft_only, q_hard, q_combined = _persistent_rate_scores(
                    evidence, mapping_cfg
                )
                weights = mapping_cfg["Q_persistent_rate"]["component_weights"]
                rate_rows.append(
                    {
                        "timestamp": anchor,
                        "sensor_id": sensor,
                        "multiplier": multiplier,
                        "persistent_event": (
                            evidence.rate_soft_only_violation_rate > 0
                            or evidence.rate_hard_violation_rate > 0
                        ),
                        "persistent_soft_only_fraction": evidence.rate_soft_only_violation_rate,
                        "persistent_hard_fraction": evidence.rate_hard_violation_rate,
                        "persistent_fraction": (
                            weights["soft_only"] * evidence.rate_soft_only_violation_rate
                            + weights["hard"] * evidence.rate_hard_violation_rate
                        ),
                        "point_fraction": evidence.rate_hard_point_violation_rate,
                        "Q_persistent_rate_soft_only": q_soft_only,
                        "Q_persistent_rate_hard": q_hard,
                        "Q_persistent_rate": q_combined,
                        "sensitivity_code_version": INTERVAL_SCALING_VERSION,
                    }
                )

    def summarize(frame_long: pd.DataFrame, event_column: str, burden_column: str) -> pd.DataFrame:
        baseline = frame_long[frame_long["multiplier"] == 1.0][
            ["timestamp", "sensor_id", event_column]
        ].rename(columns={event_column: "baseline_event"})
        rows = []
        for multiplier, variant in frame_long.groupby("multiplier"):
            merged = variant.merge(baseline, on=["timestamp", "sensor_id"], how="inner")
            rows.append(
                {
                    "multiplier": multiplier,
                    "n_sampled_sensor_windows": len(merged),
                    "baseline_events": int(merged["baseline_event"].sum()),
                    "variant_events": int(merged[event_column].sum()),
                    "event_jaccard": _event_jaccard(merged["baseline_event"], merged[event_column]),
                    "mean_variant_burden": float(merged[burden_column].mean()),
                    "sampling_role": "stratified_monthly_sensitivity_not_threshold_optimization",
                }
            )
        return pd.DataFrame(rows)

    boundary_long = pd.DataFrame(boundary_rows)
    rate_long = pd.DataFrame(rate_rows)
    boundary_summary = summarize(boundary_long, "warning", "violation_fraction")
    boundary_summary["parameter"] = "operational_soft_envelope_width"
    rate_summary = summarize(rate_long, "persistent_event", "persistent_fraction")
    rate_summary["parameter"] = "persistent_rate_limit"
    return pd.concat([boundary_summary, rate_summary], ignore_index=True), pd.concat(
        [
            boundary_long.assign(parameter="operational_soft_envelope_width"),
            rate_long.assign(parameter="persistent_rate_limit"),
        ],
        ignore_index=True,
        sort=False,
    )


def _rate_challenge_matrix(rate_checker: RateConstraintChecker, mapping_cfg: dict) -> pd.DataFrame:
    base = 2.0 + 0.01 * np.sin(np.arange(120) / 8.0)
    scenarios: list[tuple[str, np.ndarray, np.ndarray | None, str]] = []

    single = base.copy()
    single[60] += 3.0
    scenarios.append(("single_point_spike", single, None, "D1_spike"))
    two = base.copy()
    two[60:62] += 3.0
    scenarios.append(("two_minute_spike", two, None, "D1_spike"))
    block = base.copy()
    block[60:65] += 3.0
    scenarios.append(("five_minute_block", block, None, "D1_spike_with_D3_diagnostic"))
    soft_ramp = base.copy()
    soft_ramp[50:56] = soft_ramp[49] + np.arange(1, 7) * 0.30
    soft_ramp[56:] = soft_ramp[55]
    scenarios.append(("five_minute_soft_ramp", soft_ramp, None, "D3_soft_persistent_rate"))
    ramp = base.copy()
    ramp[50:81] = ramp[49] + np.arange(1, 32) * 0.6
    ramp[81:] = ramp[80]
    scenarios.append(("thirty_minute_ramp", ramp, None, "D3_persistent_rate"))
    step = base.copy()
    step[60:] += 3.0
    scenarios.append(("permanent_step", step, None, "D1_step"))
    coherent = ramp.copy()
    scenarios.append(
        ("multi_sensor_coherent_ramp", coherent, np.ones(len(coherent), dtype=bool), "process_guard")
    )
    missing = base.copy()
    missing[50:60] = np.nan
    missing[60:] += 3.0
    scenarios.append(("missing_recovery_jump", missing, None, "D2_continuity"))

    rows = []
    for name, values, guard, expected_owner in scenarios:
        evidence = rate_checker.check(
            values,
            "DO_1_1",
            "DO",
            process_coherent_mask=guard,
        )
        q_soft_only, q_hard, score = _persistent_rate_scores(evidence, mapping_cfg)
        rows.append(
            {
                "scenario": name,
                "expected_primary_owner": expected_owner,
                "point_hard_rate": evidence.rate_hard_point_violation_rate,
                "persistent_soft_only_rate": evidence.rate_soft_only_violation_rate,
                "persistent_hard_rate": evidence.rate_hard_violation_rate,
                "longest_unguarded_same_sign_run_min": evidence.rate_hard_consec_max_min,
                "longest_raw_same_sign_run_min": evidence.rate_hard_consec_raw_max_min,
                "impulse_return_events": evidence.impulse_return_event_count,
                "process_guarded_points": evidence.process_coherence_guarded_points,
                "Q_persistent_rate_soft_only": q_soft_only,
                "Q_persistent_rate_hard": q_hard,
                "Q_persistent_rate": score,
                "D3_persistent_event": (
                    evidence.rate_soft_only_violation_rate > 0
                    or evidence.rate_hard_violation_rate > 0
                ),
            }
        )
    return pd.DataFrame(rows)


def _rate_dose_response(rate_checker: RateConstraintChecker, mapping_cfg: dict) -> pd.DataFrame:
    rows = []
    for rate_magnitude in (12.5, 20.0, 25.0, 30.0, 37.5):
        for duration in (2, 5, 10, 15, 30):
            values = np.full(120, -200.0)
            start = 40
            values[start:start + duration] = -200.0 + np.arange(1, duration + 1) * rate_magnitude
            values[start + duration:] = values[start + duration - 1]
            evidence = rate_checker.check(values, "ORP_1_1", "ORP")
            q_soft_only, q_hard, q_combined = _persistent_rate_scores(
                evidence, mapping_cfg
            )
            rows.append(
                {
                    "rate_magnitude_mV_L_min": rate_magnitude,
                    "hard_threshold_multiple": rate_magnitude / 25.0,
                    "duration_min": duration,
                    "point_hard_rate": evidence.rate_hard_point_violation_rate,
                    "persistent_soft_only_rate": evidence.rate_soft_only_violation_rate,
                    "persistent_hard_rate": evidence.rate_hard_violation_rate,
                    "D3_persistent_event": (
                        evidence.rate_soft_only_violation_rate > 0
                        or evidence.rate_hard_violation_rate > 0
                    ),
                    "Q_persistent_rate_soft_only": q_soft_only,
                    "Q_persistent_rate_hard": q_hard,
                    "Q_persistent_rate": q_combined,
                    "role": "controlled_dose_response_not_threshold_optimization",
                }
            )
    return pd.DataFrame(rows)


def _d1_d3_overlap(results: dict, d1_scores_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    if not d1_scores_path.exists():
        return pd.DataFrame(), pd.DataFrame()
    d3_scores = results["main_scores"][
        ["ts", "sensor_id", "Q_persistent_rate"]
    ].copy()
    d3_rate = results["rate_constraint"][
        [
            "ts",
            "sensor_id",
            "rate_soft_only_violation_rate",
            "rate_hard_violation_rate",
        ]
    ]
    d3_scores = d3_scores.merge(d3_rate, on=["ts", "sensor_id"], how="left")
    study_start = pd.Timestamp(d3_scores["ts"].min()).floor("D")
    long_frames = []
    for sheet in ("Q_spike", "Q_step"):
        source = pd.read_excel(d1_scores_path, sheet_name=sheet)
        source["timestamp"] = pd.to_datetime(source["timestamp"])
        long = source.melt(id_vars="timestamp", var_name="sensor_id", value_name="D1_score")
        elapsed = (long["timestamp"] - study_start) // pd.Timedelta(hours=2)
        long["ts"] = study_start + (elapsed + 1) * pd.Timedelta(hours=2)
        reduced = long.groupby(["ts", "sensor_id"], as_index=False)["D1_score"].min()
        reduced["D1_construct"] = sheet
        long_frames.append(reduced)
    aligned = pd.concat(long_frames, ignore_index=True).merge(
        d3_scores, on=["ts", "sensor_id"], how="inner"
    )
    aligned["D1_loss"] = 5.0 - aligned["D1_score"]
    aligned["D3_persistent_rate_loss"] = 5.0 - aligned["Q_persistent_rate"]
    aligned["D1_event"] = aligned["D1_score"] < 3.0
    aligned["D3_event"] = (
        aligned["rate_soft_only_violation_rate"].gt(0)
        | aligned["rate_hard_violation_rate"].gt(0)
    )
    aligned["analyte"] = aligned["sensor_id"].str.split("_").str[0]

    summaries = []
    for construct, construct_frame in aligned.groupby("D1_construct"):
        groups = [("overall", "all", construct_frame)]
        groups += [("analyte", name, group) for name, group in construct_frame.groupby("analyte")]
        groups += [("sensor", name, group) for name, group in construct_frame.groupby("sensor_id")]
        for level, name, group in groups:
            d1_n = int(group["D1_event"].sum())
            d3_n = int(group["D3_event"].sum())
            both = int((group["D1_event"] & group["D3_event"]).sum())
            estimable = group["D1_loss"].nunique() > 1 and group["D3_persistent_rate_loss"].nunique() > 1
            summaries.append(
                {
                    "D1_construct": construct,
                    "stratum_level": level,
                    "stratum": name,
                    "n_windows": len(group),
                    "spearman_loss": (
                        group["D1_loss"].corr(group["D3_persistent_rate_loss"], method="spearman")
                        if estimable else np.nan
                    ),
                    "spearman_status": "estimated" if estimable else "not_estimable_constant_input",
                    "event_jaccard": _event_jaccard(group["D1_event"], group["D3_event"]),
                    "P_D3_given_D1": both / d1_n if d1_n else np.nan,
                    "P_D1_given_D3": both / d3_n if d3_n else np.nan,
                    "D1_events": d1_n,
                    "D3_events": d3_n,
                    "matched_events": both,
                    "interpretation": "empirical_overlap_not_shared_injection_performance",
                }
            )
    return pd.DataFrame(summaries), aligned


def _weight_contract_sensitivity(
    results: dict, rules_cfg: dict
) -> tuple[pd.DataFrame, pd.DataFrame]:
    scores = results["main_scores"].copy()
    value = results["value_bounds"][[
        "ts",
        "sensor_id",
        "hard_violation_rate",
        "consecutive_hard_max_min",
        "out_of_instrument",
    ]]
    rate = results["rate_constraint"][[
        "ts",
        "sensor_id",
        "rate_hard_point_violation_rate",
        "rate_hard_consec_max_min",
    ]]
    detail = scores.merge(value, on=["ts", "sensor_id"], how="left").merge(
        rate, on=["ts", "sensor_id"], how="left"
    )
    sufficient = detail["evidence_status"].eq("sufficient")
    detail["Q_rate_v2_3_point"] = detail["rate_hard_point_violation_rate"].map(
        lambda value: _legacy_v23_rate_score(value, rules_cfg)
    )
    old_values = detail[["Q_value_hard", "Q_value_soft", "Q_rate_v2_3_point"]]
    old_base = (
        0.50 * old_values["Q_value_hard"]
        + 0.20 * old_values["Q_value_soft"]
        + 0.30 * old_values["Q_rate_v2_3_point"]
    )
    old_pre = 0.75 * old_base + 0.25 * old_values.min(axis=1)
    v1 = rules_cfg["veto"]["veto_1"]
    v2 = rules_cfg["veto"]["veto_2"]
    v3 = rules_cfg["veto"]["veto_3"]

    def apply_caps(pre: pd.Series) -> pd.Series:
        total = pre.copy()
        total = total.mask(
            detail["hard_violation_rate"].gt(v1["trigger"]["hard_violation_rate_gt"])
            | detail["consecutive_hard_max_min"].gt(v1["trigger"]["OR_consecutive_min_gt"]),
            np.minimum(total, float(v1["cap"])),
        )
        total = total.mask(
            detail["out_of_instrument"].fillna(False),
            np.minimum(total, float(v2["cap"])),
        )
        total = total.mask(
            detail["rate_hard_consec_max_min"].gt(
                v3["trigger"]["rate_hard_violation_min_gt"]
            ),
            np.minimum(total, float(v3["cap"])),
        )
        return total

    old_total = apply_caps(old_pre)
    candidate_base = (
        0.45 * detail["Q_value_hard"]
        + 0.35 * detail["Q_value_soft"]
        + 0.20 * detail["Q_persistent_rate"]
    )
    candidate_pre = 0.75 * candidate_base + 0.25 * detail[
        ["Q_value_hard", "Q_value_soft", "Q_persistent_rate"]
    ].min(axis=1)
    candidate_total = apply_caps(candidate_pre)
    detail["D3_v2_3_reconstructed"] = np.where(
        sufficient, np.clip(old_total, 1.0, 5.0), np.nan
    )
    detail["D3_v2_4_current"] = detail["D3_total"]
    detail["D3_candidate_045_035_020"] = np.where(
        sufficient, np.clip(candidate_total, 1.0, 5.0), np.nan
    )
    detail["delta_v2_4_minus_v2_3"] = (
        detail["D3_v2_4_current"] - detail["D3_v2_3_reconstructed"]
    )
    detail["low_v2_3"] = detail["D3_v2_3_reconstructed"] < 3.0
    detail["low_v2_4"] = detail["D3_v2_4_current"] < 3.0
    detail["low_candidate"] = detail["D3_candidate_045_035_020"] < 3.0

    evaluated = detail[sufficient].copy()
    sensor_summary = evaluated.groupby("sensor_id", as_index=False).agg(
        median_v2_3=("D3_v2_3_reconstructed", "median"),
        median_v2_4=("D3_v2_4_current", "median"),
        median_candidate=("D3_candidate_045_035_020", "median"),
        mean_v2_3=("D3_v2_3_reconstructed", "mean"),
        mean_v2_4=("D3_v2_4_current", "mean"),
        mean_candidate=("D3_candidate_045_035_020", "mean"),
        mean_delta=("delta_v2_4_minus_v2_3", "mean"),
        low_windows_v2_3=("low_v2_3", "sum"),
        low_windows_v2_4=("low_v2_4", "sum"),
        low_windows_candidate=("low_candidate", "sum"),
    )
    rows = []
    for comparison, variant_score, variant_low in (
        ("v2.4_rate_construct_vs_v2.3", "D3_v2_4_current", "low_v2_4"),
        ("candidate_0.45_0.35_0.20_vs_v2.3", "D3_candidate_045_035_020", "low_candidate"),
    ):
        delta = evaluated[variant_score] - evaluated["D3_v2_3_reconstructed"]
        rows.append({
            "comparison": comparison,
            "stratum": "overall",
            "n_windows": int(len(evaluated)),
            "median_delta": float(delta.median()),
            "p05_delta": float(delta.quantile(0.05)),
            "p95_delta": float(delta.quantile(0.95)),
            "low_event_jaccard": _event_jaccard(
                evaluated["low_v2_3"], evaluated[variant_low]
            ),
            "sensor_rank_spearman": sensor_summary["mean_v2_3"].corr(
                sensor_summary[
                    "mean_v2_4" if variant_score == "D3_v2_4_current" else "mean_candidate"
                ],
                method="spearman",
            ),
            "production_status": (
                "accepted_rate_construct_only"
                if variant_score == "D3_v2_4_current"
                else "sensitivity_only_not_promoted"
            ),
            "interpretation": "prespecified_weight_contract_sensitivity_not_optimization",
        })
    return pd.DataFrame(rows), sensor_summary


def run_validation(
    *,
    frame: pd.DataFrame,
    results: dict,
    sensors: list[str],
    sensor_meta: list[dict],
    thresholds,
    configs: dict,
    root: Path,
    temperature_minute: pd.Series,
) -> dict[str, Path]:
    output = root / "outputs" / "validation"
    output.mkdir(parents=True, exist_ok=True)
    operational = _operational_diagnostics(
        frame, sensor_meta, configs["physical_bounds"], results
    )
    do4_views = _do4_zero_views(frame)
    do4_candidate = _do4_candidate_upper_template(frame, root)
    operational["DO4_upper_candidate"] = do4_candidate
    temperature_audit, _ = build_temperature_envelope_audit(
        frame=frame,
        temperature_minute=temperature_minute,
        sensor_meta=sensor_meta,
        physical_cfg=configs["physical_bounds"],
        root=root,
    )
    temperature_path = output / "D3_temperature_conditioned_DO_upper.xlsx"
    with pd.ExcelWriter(temperature_path) as writer:
        for sheet in (
            "source_audit",
            "saturation_reference_check",
            "frozen_registry_check",
            "phase_validation",
            "cross_line_transfer",
            "alpha_sensitivity",
            "exclusions",
        ):
            temperature_audit[sheet].to_excel(writer, sheet_name=sheet[:31], index=False)
    temperature_detail_path = output / "D3_temperature_conditioned_DO_upper.parquet"
    temperature_audit["minute_detail"].to_parquet(temperature_detail_path, index=False)
    sensitivity_summary, sensitivity_detail = _threshold_sensitivity(
        frame,
        sensors,
        sensor_meta,
        thresholds,
        configs["physical_bounds"],
        configs["rate_limits"],
        configs["mapping"],
    )
    challenge = _rate_challenge_matrix(
        RateConstraintChecker(thresholds, configs["rate_limits"]), configs["mapping"]
    )
    dose_response = _rate_dose_response(
        RateConstraintChecker(thresholds, configs["rate_limits"]), configs["mapping"]
    )
    d1_path = root.parent / "D1 Sensor health" / "outputs" / "data" / "D1_main_scores_min.xlsx"
    overlap_summary, overlap_aligned = _d1_d3_overlap(results, d1_path)
    weight_summary, weight_by_sensor = _weight_contract_sensitivity(
        results, configs["rules"]
    )

    operational_path = output / "D3_operational_envelope_diagnostics.xlsx"
    with pd.ExcelWriter(operational_path) as writer:
        for sheet, table in operational.items():
            table.to_excel(writer, sheet_name=sheet[:31], index=False)
    sensitivity_path = output / "D3_threshold_sensitivity.xlsx"
    with pd.ExcelWriter(sensitivity_path) as writer:
        sensitivity_summary.to_excel(writer, sheet_name="summary", index=False)
        sensitivity_detail.to_excel(writer, sheet_name="sampled_windows", index=False)
    challenge_path = output / "D3_rate_construct_validation.xlsx"
    with pd.ExcelWriter(challenge_path) as writer:
        challenge.to_excel(writer, sheet_name="challenge_matrix", index=False)
        dose_response.to_excel(writer, sheet_name="rate_dose_response", index=False)
        overlap_summary.to_excel(writer, sheet_name="D1_D3_overlap_summary", index=False)
        overlap_aligned.to_excel(writer, sheet_name="aligned_evidence", index=False)
    weight_path = output / "D3_weight_contract_sensitivity.xlsx"
    with pd.ExcelWriter(weight_path) as writer:
        weight_summary.to_excel(writer, sheet_name="summary", index=False)
        weight_by_sensor.to_excel(writer, sheet_name="by_sensor", index=False)
    do4_views_path = output / "D3_DO4_zero_equivalence_views.parquet"
    do4_views.to_parquet(do4_views_path, index=False)

    source = pd.concat(
        [
            operational["directional_window_burden"].assign(table="directional_window_burden"),
            operational["DO4_zero_eq_sensitivity"].assign(
                table="DO4_zero_eq_sensitivity"
            ),
            operational["DO4_monthly_zero_stability"].assign(
                table="DO4_monthly_zero_stability"
            ),
            operational["DO4_upper_candidate"].assign(table="DO4_upper_candidate"),
            sensitivity_summary.assign(table="threshold_sensitivity"),
            challenge.assign(table="rate_challenge_matrix"),
            dose_response.assign(table="rate_dose_response"),
            overlap_summary.assign(table="D1_D3_overlap_summary"),
            weight_summary.assign(table="weight_contract_sensitivity"),
        ],
        ignore_index=True,
        sort=False,
    )
    source_path = output / "D3_boundary_rate_validation_source.parquet"
    source.to_parquet(source_path, index=False)

    d1_sha = hashlib.sha256(d1_path.read_bytes()).hexdigest() if d1_path.exists() else None
    summary = {
        "validation_version": "v2.6.0",
        "interval_sensitivity_version": INTERVAL_SCALING_VERSION,
        "rate_challenge_scenarios": int(len(challenge)),
        "rate_challenge_expected_matches": int(
            (
                challenge["D3_persistent_event"]
                == challenge["expected_primary_owner"].isin(
                    ["D3_persistent_rate", "D3_soft_persistent_rate"]
                )
            ).sum()
        ),
        "threshold_sensitivity_rows": int(len(sensitivity_summary)),
        "empirical_D1_D3_overlap_rows": int(len(overlap_aligned)),
        "D1_score_source_sha256": d1_sha,
        "temperature_registry_all_match": bool(
            temperature_audit["frozen_registry_check"]["registry_match"].all()
        ),
        "temperature_study_minute_coverage": float(
            temperature_audit["source_audit"].iloc[0]["study_minute_coverage"]
        ),
        "locked_conclusions": [
            "DO4 physical soft lower bound remains 0 mg/L; -0.05 mg/L is a separate provisional zero-equivalence tolerance.",
            "DO4 production upper warning is disabled pending a time-blocked post-anoxic template lock.",
            "D3 rate evidence combines mutually exclusive 3-9 min soft-only and >=10 min hard-persistent episodes.",
            "Coherent multi-sensor shocks are guarded as process attribution, not vetoed.",
            "Instrument-range failure is separated from provisional operating warnings.",
            "ORP sensitivity changes interval width around a fixed center through one canonical implementation.",
            "Aerobic DO upper warnings use a frozen longitudinal-position template conditioned on a minute influent-temperature proxy.",
            "Calibration, validation, and production scoring use the same minute-level DO/Csat estimand with calendar-day cluster bootstrap uncertainty.",
            "The validation-only benchmark filter includes the frozen D1 Q_drift component; no independent D1 saturation/floor sheet exists to add.",
            "Positions 1-2 are scored operational warnings; position 3 remains diagnostic-only after failed temporal transfer.",
            "Cross-line leave-one-line-out transfer is diagnostic and reveals directional asymmetry rather than being used to widen the pooled template.",
            "Terminal-test exceedances remain locked forward-test evidence and never trigger retrospective alpha refitting.",
            "Missing temperature is not extrapolated and is reported as unevaluated upper-envelope evidence.",
            "Benson-Krause freshwater solubility is used only as a USGS-traceable monotonic temperature normalizer.",
        ],
        "pending_external_evidence": [
            "in_basin_temperature_pressure_salinity_for_thermodynamic_DO_saturation_interpretation",
            "manufacturer_accuracy_or_zero_oxygen_calibration_for_final_DO4_deadband",
            "independent_support_for_DO_2_4_post_anoxic_upper_template",
            "site_reviewed_ORP_position_regime_envelopes",
            "maintenance_labels_and_independent_event_adjudication",
            "full_shared_raw_domain_D1_D3_injection_pipeline",
        ],
    }
    summary_path = output / "D3_validation_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return {
        "operational": operational_path,
        "sensitivity": sensitivity_path,
        "construct": challenge_path,
        "weight_contract": weight_path,
        "do4_zero_views": do4_views_path,
        "source": source_path,
        "summary": summary_path,
        "temperature_contract": temperature_path,
        "temperature_detail": temperature_detail_path,
    }
