"""Generate D3 v2.3 boundary, persistence, and construct-validity evidence."""

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
            soft_low=("soft_low", "first"),
            soft_high=("soft_high", "first"),
            threshold_scope=("threshold_scope", "first"),
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
            if sensor.startswith("DO_"):
                do_rows.append(
                    {
                        "sensor_id": sensor,
                        "season": season_name,
                        "n": len(sample),
                        "p95": float(sample.quantile(0.95)),
                        "p99": float(sample.quantile(0.99)),
                        "maximum": float(sample.max()),
                        "above_8_rate": float(sample.gt(8.0).mean()),
                        "upper_bound_role": "diagnostic_pending_temperature_pressure_salinity",
                    }
                )
            else:
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
    deadbands = physical_cfg["operational_envelope_contract"]["do4_zero_deadband"][
        "sensitivity_values_mg_L"
    ]
    for sensor in ("DO_1_4", "DO_2_4"):
        values = frame[sensor].dropna()
        for deadband in deadbands:
            deadband_rows.append(
                {
                    "sensor_id": sensor,
                    "zero_deadband_low_mg_L": float(deadband),
                    "n_observed": len(values),
                    "negative_value_rate": float(values.lt(0.0).mean()),
                    "soft_low_violation_rate": float(values.lt(float(deadband)).mean()),
                    "minimum_observed": float(values.min()),
                    "role": "sensitivity_not_final_manufacturer_lock",
                }
            )
    return {
        "directional_window_burden": directional,
        "DO_seasonal_high_tail": pd.DataFrame(do_rows),
        "ORP_position_season_envelope": pd.DataFrame(orp_rows),
        "DO4_zero_deadband_sensitivity": pd.DataFrame(deadband_rows),
    }


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
) -> tuple[pd.DataFrame, pd.DataFrame]:
    windows = _sample_windows(frame, per_month=4)
    pool_map = {item["id"]: item["pool"] for item in sensor_meta}
    overrides = physical_cfg.get("sensor_overrides", {})
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
                    base_bounds = physical_cfg["sensors"][sensor_type]
                    if sensor_type == "DO":
                        low = float(overrides.get(sensor, {}).get("soft_low", base_bounds["soft_low"]))
                        high = float(base_bounds["soft_high"]) * multiplier
                    else:
                        center = 0.5 * (base_bounds["soft_low"] + base_bounds["soft_high"])
                        half_width = 0.5 * (base_bounds["soft_high"] - base_bounds["soft_low"]) * multiplier
                        low, high = center - half_width, center + half_width
                    boundary_rows.append(
                        {
                            "timestamp": anchor,
                            "sensor_id": sensor,
                            "multiplier": multiplier,
                            "soft_low": low,
                            "soft_high": high,
                            "warning": bool(((finite < low) | (finite > high)).any()),
                            "violation_fraction": float(((finite < low) | (finite > high)).mean()),
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
                rate_rows.append(
                    {
                        "timestamp": anchor,
                        "sensor_id": sensor,
                        "multiplier": multiplier,
                        "persistent_event": evidence.rate_hard_violation_rate > 0,
                        "persistent_fraction": evidence.rate_hard_violation_rate,
                        "point_fraction": evidence.rate_hard_point_violation_rate,
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

    mapping = mapping_cfg["Q_persistent_rate"]
    rows = []
    for name, values, guard, expected_owner in scenarios:
        evidence = rate_checker.check(
            values,
            "DO_1_1",
            "DO",
            process_coherent_mask=guard,
        )
        score = logistic_zero_anchored(
            evidence.rate_hard_violation_rate, mapping["x0"], mapping["k"]
        )
        rows.append(
            {
                "scenario": name,
                "expected_primary_owner": expected_owner,
                "point_hard_rate": evidence.rate_hard_point_violation_rate,
                "persistent_hard_rate": evidence.rate_hard_violation_rate,
                "longest_unguarded_same_sign_run_min": evidence.rate_hard_consec_max_min,
                "longest_raw_same_sign_run_min": evidence.rate_hard_consec_raw_max_min,
                "impulse_return_events": evidence.impulse_return_event_count,
                "process_guarded_points": evidence.process_coherence_guarded_points,
                "Q_persistent_rate": score,
                "D3_persistent_event": evidence.rate_hard_violation_rate > 0,
            }
        )
    return pd.DataFrame(rows)


def _rate_dose_response(rate_checker: RateConstraintChecker, mapping_cfg: dict) -> pd.DataFrame:
    mapping = mapping_cfg["Q_persistent_rate"]
    rows = []
    for rate_magnitude in (12.5, 20.0, 25.0, 30.0, 37.5):
        for duration in (2, 5, 10, 15, 30):
            values = np.full(120, -200.0)
            start = 40
            values[start:start + duration] = -200.0 + np.arange(1, duration + 1) * rate_magnitude
            values[start + duration:] = values[start + duration - 1]
            evidence = rate_checker.check(values, "ORP_1_1", "ORP")
            rows.append(
                {
                    "rate_magnitude_mV_L_min": rate_magnitude,
                    "hard_threshold_multiple": rate_magnitude / 25.0,
                    "duration_min": duration,
                    "point_hard_rate": evidence.rate_hard_point_violation_rate,
                    "persistent_hard_rate": evidence.rate_hard_violation_rate,
                    "D3_persistent_event": evidence.rate_hard_violation_rate > 0,
                    "Q_persistent_rate": logistic_zero_anchored(
                        evidence.rate_hard_violation_rate, mapping["x0"], mapping["k"]
                    ),
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
        ["ts", "sensor_id", "rate_hard_violation_rate"]
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
    aligned["D3_event"] = aligned["rate_hard_violation_rate"] > 0
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


def run_validation(
    *,
    frame: pd.DataFrame,
    results: dict,
    sensors: list[str],
    sensor_meta: list[dict],
    thresholds,
    configs: dict,
    root: Path,
) -> dict[str, Path]:
    output = root / "outputs" / "validation"
    output.mkdir(parents=True, exist_ok=True)
    operational = _operational_diagnostics(
        frame, sensor_meta, configs["physical_bounds"], results
    )
    sensitivity_summary, sensitivity_detail = _threshold_sensitivity(
        frame,
        sensors,
        sensor_meta,
        thresholds,
        configs["physical_bounds"],
        configs["rate_limits"],
    )
    challenge = _rate_challenge_matrix(
        RateConstraintChecker(thresholds, configs["rate_limits"]), configs["mapping"]
    )
    dose_response = _rate_dose_response(
        RateConstraintChecker(thresholds, configs["rate_limits"]), configs["mapping"]
    )
    d1_path = root.parent / "D1 Sensor health" / "outputs" / "data" / "D1_main_scores_min.xlsx"
    overlap_summary, overlap_aligned = _d1_d3_overlap(results, d1_path)

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

    source = pd.concat(
        [
            operational["directional_window_burden"].assign(table="directional_window_burden"),
            operational["DO4_zero_deadband_sensitivity"].assign(table="DO4_zero_deadband_sensitivity"),
            sensitivity_summary.assign(table="threshold_sensitivity"),
            challenge.assign(table="rate_challenge_matrix"),
            dose_response.assign(table="rate_dose_response"),
            overlap_summary.assign(table="D1_D3_overlap_summary"),
        ],
        ignore_index=True,
        sort=False,
    )
    source_path = output / "D3_boundary_rate_validation_source.parquet"
    source.to_parquet(source_path, index=False)

    d1_sha = hashlib.sha256(d1_path.read_bytes()).hexdigest() if d1_path.exists() else None
    summary = {
        "validation_version": "v2.3.0",
        "rate_challenge_scenarios": int(len(challenge)),
        "rate_challenge_expected_matches": int(
            (
                challenge["D3_persistent_event"]
                == challenge["expected_primary_owner"].eq("D3_persistent_rate")
            ).sum()
        ),
        "threshold_sensitivity_rows": int(len(sensitivity_summary)),
        "empirical_D1_D3_overlap_rows": int(len(overlap_aligned)),
        "D1_score_source_sha256": d1_sha,
        "locked_conclusions": [
            "DO4 resolution-scale negative values are exempted by a provisional -0.05 mg/L zero deadband.",
            "D3 rate evidence requires same-sign persistence and excludes 1-3 min impulse-return morphology.",
            "Coherent multi-sensor shocks are guarded as process attribution, not vetoed.",
            "Instrument-range failure is separated from provisional operating warnings.",
        ],
        "pending_external_evidence": [
            "temperature_pressure_salinity_for_dynamic_DO_saturation_bound",
            "manufacturer_accuracy_or_zero_oxygen_calibration_for_final_DO4_deadband",
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
        "source": source_path,
        "summary": summary_path,
    }
