"""Minute-resolved audit for frozen temperature-conditioned aerobic DO envelopes."""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pandas as pd

from src.d3_physical.do_temperature_envelope import freshwater_do_saturation_mg_l


D1_SHEETS = (
    "D1_total_hourly",
    "Q_spike",
    "Q_step",
    "Q_drift",
    "Q_freeze",
    "Q_regime",
)
ALLOWED_D2_TAGS = ("train_ok", "train_ok_with_operational_warning")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _wide_sheet(path: Path, sheet: str) -> pd.DataFrame:
    frame = pd.read_excel(path, sheet_name=sheet)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="raise")
    return frame.set_index("timestamp").sort_index()


def _quality_masks(root: Path, sensors: list[str]) -> tuple[dict[str, pd.Series], dict]:
    """Build validation-only hourly masks from frozen D1 and D2 releases."""
    d1_path = root.parent / "D1 Sensor health" / "outputs" / "data" / "D1_main_scores_min.xlsx"
    d2_path = (
        root.parent
        / "D2 Temporal Continuity & Information Availability"
        / "artifacts"
        / "data"
        / "D2_main_scores_hourly.xlsx"
    )
    if not d1_path.exists() or not d2_path.exists():
        raise FileNotFoundError(
            "Frozen D1/D2 release products are required for validation-only calibration audit"
        )
    d1 = {sheet: _wide_sheet(d1_path, sheet) for sheet in D1_SHEETS}
    d2 = pd.read_excel(d2_path, sheet_name="D2_scores").rename(columns={"Unnamed: 0": "ts"})
    d2["ts"] = pd.to_datetime(d2["ts"], errors="raise")
    masks: dict[str, pd.Series] = {}
    for sensor in sensors:
        d1_mask = pd.concat(
            [d1[sheet][sensor].rename(sheet) for sheet in D1_SHEETS], axis=1
        ).ge(4.5).all(axis=1)
        sensor_d2 = d2.loc[d2["sensor_id"].eq(sensor)].set_index("ts").sort_index()
        d2_mask = sensor_d2["D2_Strict"].ge(4.5) & sensor_d2["usable_tag"].isin(
            ALLOWED_D2_TAGS
        )
        masks[sensor] = d1_mask & d2_mask.reindex(d1_mask.index).eq(True)
    return masks, {
        "d1_path": str(d1_path),
        "d1_sha256": _sha256(d1_path),
        "d1_filter_sheets": ",".join(D1_SHEETS),
        "d1_optional_saturation_floor_filter": "unavailable_in_frozen_release_not_imputed",
        "d2_path": str(d2_path),
        "d2_sha256": _sha256(d2_path),
    }


def _phase(index: pd.DatetimeIndex, calibration: dict) -> np.ndarray:
    return np.select(
        [
            (index >= pd.Timestamp(calibration["start"]))
            & (index < pd.Timestamp(calibration["end_exclusive"])),
            (index >= pd.Timestamp(calibration["validation_start"]))
            & (index < pd.Timestamp(calibration["validation_end_exclusive"])),
            (index >= pd.Timestamp(calibration["terminal_start"]))
            & (index < pd.Timestamp(calibration["terminal_end_exclusive"])),
        ],
        ["calibration", "validation", "terminal_test"],
        default="outside_prespecified_period",
    )


def _minute_mask(hourly_mask: pd.Series, minute_index: pd.DatetimeIndex) -> np.ndarray:
    return hourly_mask.reindex(minute_index.floor("h")).eq(True).to_numpy(dtype=bool)


def _alpha_estimator(values: np.ndarray) -> tuple[float, float, float, float]:
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if not len(values):
        return np.nan, np.nan, np.nan, np.nan
    median = float(np.median(values))
    mad_scale = float(1.4826 * np.median(np.abs(values - median)))
    p99 = float(np.quantile(values, 0.99))
    return max(p99, median + 3.0 * mad_scale), median, mad_scale, p99


def _cluster_bootstrap_alpha(
    values: pd.Series,
    clusters: pd.Series,
    *,
    replicates: int,
    seed: int,
) -> tuple[float, float]:
    table = pd.DataFrame({"value": values, "cluster": clusters}).dropna()
    arrays = [group["value"].to_numpy(dtype=float) for _, group in table.groupby("cluster")]
    if len(arrays) < 2:
        return np.nan, np.nan
    rng = np.random.default_rng(seed)
    estimates = np.empty(replicates, dtype=float)
    for index in range(replicates):
        selected = rng.integers(0, len(arrays), size=len(arrays))
        sample = np.concatenate([arrays[item] for item in selected])
        estimates[index] = _alpha_estimator(sample)[0]
    return tuple(np.quantile(estimates, [0.025, 0.975]))


def _cluster_rate_ci(
    outcome: pd.Series,
    eligible: pd.Series,
    clusters: pd.Series,
    *,
    replicates: int,
    seed: int,
) -> tuple[float, float]:
    table = pd.DataFrame(
        {
            "outcome": outcome.astype(float),
            "eligible": eligible.astype(bool),
            "cluster": clusters,
        }
    )
    table = table.loc[table["eligible"]].dropna(subset=["cluster"])
    grouped = table.groupby("cluster")["outcome"].agg(["sum", "count"])
    if len(grouped) < 2 or grouped["count"].sum() == 0:
        return np.nan, np.nan
    values = grouped[["sum", "count"]].to_numpy(dtype=float)
    rng = np.random.default_rng(seed)
    estimates = np.empty(replicates, dtype=float)
    for index in range(replicates):
        selected = values[rng.integers(0, len(values), size=len(values))]
        estimates[index] = selected[:, 0].sum() / selected[:, 1].sum()
    return tuple(np.quantile(estimates, [0.025, 0.975]))


def _window_metrics(
    group: pd.DataFrame,
    *,
    window_cfg: dict,
    replicates: int,
    seed: int,
    include_ci: bool = True,
) -> dict:
    minutes = int(window_cfg["minutes"])
    minimum = int(window_cfg["minimum_high_quality_minutes"])
    threshold = float(window_cfg["warning_if_exceedance_rate_gt"])
    indexed = group.set_index("ts").sort_index()
    window = pd.DataFrame(
        {
            "n_high_quality": indexed["high_quality_evaluable"].astype(int),
            "n_warning": (
                indexed["dynamic_warning"] & indexed["high_quality_evaluable"]
            ).astype(int),
        }
    ).resample(f"{minutes}min").sum()
    eligible = window["n_high_quality"].ge(minimum)
    warning = (window["n_warning"] / window["n_high_quality"]).gt(threshold) & eligible
    rate = float(warning[eligible].mean()) if eligible.any() else np.nan
    ci_low, ci_high = (
        _cluster_rate_ci(
            warning,
            eligible,
            pd.Series(window.index.date, index=window.index),
            replicates=replicates,
            seed=seed,
        )
        if include_ci
        else (np.nan, np.nan)
    )
    return {
        "n_2h_windows": int(eligible.sum()),
        "n_2h_warning_windows": int(warning[eligible].sum()),
        "warning_2h_window_rate_high_quality": rate,
        "warning_2h_window_rate_ci_low": ci_low,
        "warning_2h_window_rate_ci_high": ci_high,
    }


def _phase_summary(
    detail: pd.DataFrame,
    calibration: dict,
    *,
    seed_offset: int = 0,
    include_ci: bool = True,
) -> pd.DataFrame:
    bootstrap = calibration["bootstrap"]
    replicates = int(bootstrap["replicates"])
    seed = int(bootstrap["seed"]) + seed_offset
    criterion = float(calibration["validation_window"]["warning_if_exceedance_rate_gt"])
    rows = []
    phases = ("calibration", "validation", "terminal_test")
    for row_index, ((sensor, phase_name), group) in enumerate(
        detail.loc[detail["phase"].isin(phases)].groupby(["sensor_id", "phase"])
    ):
        evaluable = group["upper_evaluable"]
        high_quality = group["high_quality_evaluable"]
        warning = group["dynamic_warning"]
        minute_rate = float(warning[high_quality].mean()) if high_quality.any() else np.nan
        minute_ci = (
            _cluster_rate_ci(
                warning,
                high_quality,
                pd.Series(pd.to_datetime(group["ts"]).dt.date, index=group.index),
                replicates=replicates,
                seed=seed + row_index,
            )
            if include_ci
            else (np.nan, np.nan)
        )
        window_metrics = _window_metrics(
            group,
            window_cfg=calibration["validation_window"],
            replicates=replicates,
            seed=seed + 100 + row_index,
            include_ci=include_ci,
        )
        position = str(int(group["position"].iloc[0]))
        minute_pass = bool(np.isfinite(minute_rate) and minute_rate <= criterion)
        window_pass = bool(
            np.isfinite(window_metrics["warning_2h_window_rate_high_quality"])
            and window_metrics["warning_2h_window_rate_high_quality"] <= criterion
        )
        rows.append(
            {
                "sensor_id": sensor,
                "phase": phase_name,
                "n_evaluable_minutes": int(evaluable.sum()),
                "n_high_quality_minutes": int(high_quality.sum()),
                "dynamic_warning_count_all": int(warning[evaluable].sum()),
                "dynamic_warning_count_high_quality": int(warning[high_quality].sum()),
                "dynamic_warning_rate_all": (
                    float(warning[evaluable].mean()) if evaluable.any() else np.nan
                ),
                "dynamic_warning_rate_high_quality": minute_rate,
                "dynamic_warning_rate_hq_ci_low": minute_ci[0],
                "dynamic_warning_rate_hq_ci_high": minute_ci[1],
                **window_metrics,
                "minute_criterion_pass": minute_pass,
                "window_criterion_pass": window_pass,
                "joint_threshold_pass": minute_pass and window_pass,
                "promotion_assessment": (
                    "pass"
                    if phase_name == "validation" and minute_pass and window_pass
                    else "fail"
                    if phase_name == "validation"
                    else "locked_forward_test_not_used_for_selection"
                    if phase_name == "terminal_test"
                    else "calibration_diagnostic_not_promotion"
                ),
                "median_dynamic_upper_mg_L": float(
                    group.loc[evaluable, "dynamic_upper_mg_L"].median()
                ),
                "p05_dynamic_upper_mg_L": float(
                    group.loc[evaluable, "dynamic_upper_mg_L"].quantile(0.05)
                ),
                "p95_dynamic_upper_mg_L": float(
                    group.loc[evaluable, "dynamic_upper_mg_L"].quantile(0.95)
                ),
                "score_role": (
                    "scored_operational_warning"
                    if position in calibration["scored_positions"]
                    else "diagnostic_only"
                ),
            }
        )
    return pd.DataFrame(rows)


def _alpha_uncertainty_scenarios(
    detail: pd.DataFrame,
    registry: pd.DataFrame,
    calibration: dict,
) -> pd.DataFrame:
    """Propagate the frozen alpha interval endpoints to warning burden."""
    scenario_columns = {
        "bootstrap_lower": "alpha_cluster_bootstrap_ci_low",
        "point_estimate": "frozen_alpha",
        "bootstrap_upper": "alpha_cluster_bootstrap_ci_high",
    }
    rows = []
    for scenario_index, (scenario, column) in enumerate(scenario_columns.items()):
        alpha_by_position = registry.set_index("position")[column].to_dict()
        scenario_detail = detail.copy()
        scenario_detail["scenario_alpha"] = scenario_detail["position"].map(
            alpha_by_position
        )
        scenario_detail["dynamic_upper_mg_L"] = (
            scenario_detail["scenario_alpha"]
            * scenario_detail["Csat_reference_mg_L"]
        )
        scenario_detail["dynamic_warning"] = (
            scenario_detail["DO_minute_mg_L"]
            > scenario_detail["dynamic_upper_mg_L"]
        ).fillna(False)
        summary = _phase_summary(
            scenario_detail,
            calibration,
            seed_offset=2000 + 100 * scenario_index,
            include_ci=False,
        )
        summary.insert(2, "alpha_scenario", scenario)
        summary.insert(
            3,
            "alpha_value",
            summary["sensor_id"].str.rsplit("_", n=1).str[-1].astype(int).map(
                alpha_by_position
            ),
        )
        summary["sensitivity_role"] = (
            "bootstrap_interval_propagation_not_production_parameter_selection"
        )
        rows.append(summary)
    return pd.concat(rows, ignore_index=True)


def _envelope_model_comparison(
    detail: pd.DataFrame,
    calibration: dict,
) -> pd.DataFrame:
    """Compare the frozen dynamic envelope with the historical fixed 8 mg/L rule."""
    rows = []
    for model, upper in (
        ("temperature_conditioned", detail["dynamic_upper_mg_L"]),
        ("fixed_8_mg_L", pd.Series(8.0, index=detail.index)),
    ):
        model_detail = detail.copy()
        model_detail["dynamic_upper_mg_L"] = upper
        model_detail["dynamic_warning"] = (
            model_detail["DO_minute_mg_L"] > model_detail["dynamic_upper_mg_L"]
        ).fillna(False)
        summary = _phase_summary(
            model_detail,
            calibration,
            seed_offset=3000 + len(rows) * 100,
            include_ci=False,
        )
        summary.insert(2, "envelope_model", model)
        summary["comparison_role"] = (
            "prespecified_method_comparison_not_threshold_selection"
        )
        rows.append(summary)
    return pd.concat(rows, ignore_index=True)


def _leave_one_line_out(detail: pd.DataFrame, calibration: dict) -> pd.DataFrame:
    rows = []
    criterion = float(calibration["validation_window"]["warning_if_exceedance_rate_gt"])
    for position in (1, 2, 3):
        for source_line, target_line in ((1, 2), (2, 1)):
            source_sensor = f"DO_{source_line}_{position}"
            target_sensor = f"DO_{target_line}_{position}"
            source = detail.loc[
                detail["sensor_id"].eq(source_sensor)
                & detail["phase"].eq("calibration")
                & detail["high_quality_evaluable"]
            ]
            alpha = _alpha_estimator(source["DO_over_Csat"].to_numpy(dtype=float))[0]
            for phase_name in ("validation", "terminal_test"):
                target = detail.loc[
                    detail["sensor_id"].eq(target_sensor)
                    & detail["phase"].eq(phase_name)
                ].copy()
                target["dynamic_warning"] = (
                    target["DO_minute_mg_L"] > alpha * target["Csat_reference_mg_L"]
                ).fillna(False)
                high_quality = target["high_quality_evaluable"]
                minute_rate = (
                    float(target.loc[high_quality, "dynamic_warning"].mean())
                    if high_quality.any()
                    else np.nan
                )
                window = _window_metrics(
                    target,
                    window_cfg=calibration["validation_window"],
                    replicates=int(calibration["bootstrap"]["replicates"]),
                    seed=int(calibration["bootstrap"]["seed"]) + 500 + len(rows),
                )
                rows.append(
                    {
                        "position": position,
                        "source_sensor": source_sensor,
                        "target_sensor": target_sensor,
                        "phase": phase_name,
                        "source_calibration_minutes": int(len(source)),
                        "source_only_alpha": alpha,
                        "target_high_quality_minutes": int(high_quality.sum()),
                        "target_minute_warning_rate": minute_rate,
                        **window,
                        "minute_criterion_pass": bool(
                            np.isfinite(minute_rate) and minute_rate <= criterion
                        ),
                        "window_criterion_pass": bool(
                            np.isfinite(window["warning_2h_window_rate_high_quality"])
                            and window["warning_2h_window_rate_high_quality"] <= criterion
                        ),
                        "role": "diagnostic_cross_line_transfer_not_used_for_tuning",
                    }
                )
    return pd.DataFrame(rows)


def build_temperature_envelope_audit(
    *,
    frame: pd.DataFrame,
    temperature_minute: pd.Series,
    sensor_meta: list[dict],
    physical_cfg: dict,
    root: Path,
) -> tuple[dict[str, pd.DataFrame], dict]:
    contract = physical_cfg["operational_envelope_contract"][
        "aerobic_do_temperature_conditioned_upper"
    ]
    calibration = contract["calibration"]
    aerobic = [
        item
        for item in sensor_meta
        if item["type"] == "DO" and item["process_zone"] == "aerobic"
    ]
    sensors = [item["id"] for item in aerobic]
    quality_masks, sources = _quality_masks(root, sensors)
    temperature_path = Path(temperature_minute.attrs["source_path"])
    sources["temperature_sha256"] = _sha256(temperature_path)

    temperature = temperature_minute.reindex(frame.index)
    csat = pd.Series(
        freshwater_do_saturation_mg_l(temperature.to_numpy(dtype=float)),
        index=frame.index,
        name="Csat_reference_mg_L",
    )
    phase = _phase(frame.index, calibration)
    detail_rows = []
    for meta in aerobic:
        sensor = meta["id"]
        position = str(meta["position"])
        alpha = float(calibration["alpha_by_position"][position])
        observed = frame[sensor]
        high_quality = _minute_mask(quality_masks[sensor], frame.index)
        evaluable = observed.notna().to_numpy() & temperature.notna().to_numpy()
        ratio = observed / csat
        upper = alpha * csat
        warning = (observed > upper).fillna(False)
        detail_rows.append(
            pd.DataFrame(
                {
                    "ts": frame.index,
                    "sensor_id": sensor,
                    "pool": meta["pool"],
                    "position": meta["position"],
                    "phase": phase,
                    "DO_minute_mg_L": observed.to_numpy(dtype=float),
                    "influent_temperature_C": temperature.to_numpy(dtype=float),
                    "Csat_reference_mg_L": csat.to_numpy(dtype=float),
                    "DO_over_Csat": ratio.to_numpy(dtype=float),
                    "high_quality_filter_pass": high_quality,
                    "upper_evaluable": evaluable,
                    "high_quality_evaluable": high_quality & evaluable,
                    "frozen_alpha": alpha,
                    "dynamic_upper_mg_L": upper.to_numpy(dtype=float),
                    "dynamic_warning": warning.to_numpy(dtype=bool),
                }
            )
        )
    detail = pd.concat(detail_rows, ignore_index=True)

    bootstrap = calibration["bootstrap"]
    registry_rows = []
    eligible_calibration = detail.loc[
        detail["phase"].eq("calibration")
        & detail["high_quality_evaluable"]
        & detail["DO_over_Csat"].notna()
    ]
    for position, group in eligible_calibration.groupby("position"):
        recomputed, median, mad_scale, p99 = _alpha_estimator(
            group["DO_over_Csat"].to_numpy(dtype=float)
        )
        ci_low, ci_high = _cluster_bootstrap_alpha(
            group["DO_over_Csat"],
            pd.to_datetime(group["ts"]).dt.date,
            replicates=int(bootstrap["replicates"]),
            seed=int(bootstrap["seed"]) + int(position),
        )
        frozen = float(calibration["alpha_by_position"][str(position)])
        support = int(calibration["calibration_support_sensor_minutes"][str(position)])
        minimum = int(calibration["minimum_calibration_sensor_minutes"])
        registry_rows.append(
            {
                "position": int(position),
                "sensor_ids": ",".join(sorted(group["sensor_id"].unique())),
                "n_calibration_sensor_minutes": int(len(group)),
                "registered_support_sensor_minutes": support,
                "minimum_support_sensor_minutes": minimum,
                "support_passed": int(len(group)) >= minimum,
                "ratio_median": median,
                "ratio_mad_scale": mad_scale,
                "ratio_p99": p99,
                "recomputed_alpha": recomputed,
                "alpha_cluster_bootstrap_ci_low": ci_low,
                "alpha_cluster_bootstrap_ci_high": ci_high,
                "bootstrap_cluster": bootstrap["cluster"],
                "bootstrap_replicates": int(bootstrap["replicates"]),
                "frozen_alpha": frozen,
                "absolute_difference": abs(recomputed - frozen),
                "registry_match": bool(np.isclose(recomputed, frozen, rtol=0.0, atol=1e-9)),
                "estimator": calibration["estimator"],
                "production_role": "frozen_operational_warning_only",
            }
        )
    registry = pd.DataFrame(registry_rows).sort_values("position")
    phase_validation = _phase_summary(detail, calibration)
    alpha_uncertainty = _alpha_uncertainty_scenarios(detail, registry, calibration)
    envelope_comparison = _envelope_model_comparison(detail, calibration)

    sensitivity_rows = []
    for multiplier in (0.8, 0.9, 1.0, 1.1, 1.2):
        sensitivity_detail = detail.copy()
        sensitivity_detail["dynamic_warning"] = (
            sensitivity_detail["DO_minute_mg_L"]
            > multiplier
            * sensitivity_detail["frozen_alpha"]
            * sensitivity_detail["Csat_reference_mg_L"]
        ).fillna(False)
        summary = _phase_summary(
            sensitivity_detail,
            calibration,
            seed_offset=1000 + int(multiplier * 100),
            include_ci=False,
        )
        summary.insert(2, "alpha_multiplier", multiplier)
        sensitivity_rows.append(summary)
    alpha_sensitivity = pd.concat(sensitivity_rows, ignore_index=True)
    cross_line = _leave_one_line_out(detail, calibration)

    study_temperature = temperature.reindex(frame.index)
    hourly_count = study_temperature.resample("1h").count()
    source_audit = pd.DataFrame(
        [
            {
                "temperature_source": temperature_path.name,
                "temperature_sha256": sources["temperature_sha256"],
                "temperature_start": temperature_minute.index.min(),
                "temperature_end": temperature_minute.index.max(),
                "temperature_rows": len(temperature_minute),
                "temperature_raw_missing": int(temperature_minute.attrs["raw_missing_count"]),
                "temperature_invalid_range": int(temperature_minute.attrs["invalid_range_count"]),
                "temperature_valid_min_C": float(temperature_minute.min()),
                "temperature_valid_max_C": float(temperature_minute.max()),
                "study_minute_coverage": float(study_temperature.notna().mean()),
                "study_hour_with_30min_coverage": float(hourly_count.ge(30).mean()),
                "alignment": "exact_minute_no_interpolation_no_extrapolation",
                "calibration_resolution": calibration["resolution"],
                "covariate_role": contract["covariate"],
                "interpretation": contract["interpretation"],
                "saturation_equation": contract["saturation_reference"]["equation"],
                "saturation_authority": contract["saturation_reference"]["authority"],
                "saturation_reference_url": contract["saturation_reference"]["reference_url"],
                "d1_filter_sheets": sources["d1_filter_sheets"],
                "d1_optional_saturation_floor_filter": sources[
                    "d1_optional_saturation_floor_filter"
                ],
                "d1_sha256": sources["d1_sha256"],
                "d2_sha256": sources["d2_sha256"],
            }
        ]
    )
    reference_temperature = np.array([0.0, 15.0, 20.0, 30.0, 40.0])
    saturation_reference_check = pd.DataFrame(
        {
            "temperature_C": reference_temperature,
            "Benson_Krause_Csat_mg_L": freshwater_do_saturation_mg_l(
                reference_temperature
            ),
            "medium": "freshwater",
            "pressure_atm": 1.0,
            "role": "temperature_normalizer_only",
        }
    )
    exclusions = (
        detail.assign(
            exclusion=np.select(
                [
                    detail["influent_temperature_C"].isna(),
                    detail["DO_minute_mg_L"].isna(),
                    ~detail["high_quality_filter_pass"],
                ],
                ["temperature_unavailable", "DO_unavailable", "D1_D2_quality_filter_failed"],
                default="eligible",
            )
        )
        .groupby(["phase", "sensor_id", "exclusion"], as_index=False)
        .size()
        .rename(columns={"size": "n_sensor_minutes"})
    )
    return {
        "source_audit": source_audit,
        "saturation_reference_check": saturation_reference_check,
        "frozen_registry_check": registry,
        "phase_validation": phase_validation,
        "cross_line_transfer": cross_line,
        "alpha_sensitivity": alpha_sensitivity,
        "alpha_CI_scenarios": alpha_uncertainty,
        "envelope_comparison": envelope_comparison,
        "exclusions": exclusions,
        "minute_detail": detail,
    }, sources
