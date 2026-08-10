"""Time-blocked audit for the frozen temperature-conditioned aerobic DO envelope."""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pandas as pd

from src.d3_physical.do_temperature_envelope import freshwater_do_saturation_mg_l


D1_SHEETS = ("D1_total_hourly", "Q_spike", "Q_step", "Q_freeze", "Q_regime")
ALLOWED_D2_TAGS = ("train_ok", "train_ok_with_operational_warning")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _wide_sheet(path: Path, sheet: str) -> pd.DataFrame:
    frame = pd.read_excel(path, sheet_name=sheet)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="raise")
    return frame.set_index("timestamp").sort_index()


def _quality_masks(root: Path, sensors: list[str]) -> tuple[dict[str, pd.Series], dict]:
    d1_path = root.parent / "D1 Sensor health" / "outputs" / "data" / "D1_main_scores_min.xlsx"
    d2_path = (
        root.parent
        / "D2 Temporal Continuity & Information Availability"
        / "artifacts"
        / "data"
        / "D2_main_scores_hourly.xlsx"
    )
    if not d1_path.exists() or not d2_path.exists():
        raise FileNotFoundError("Frozen D1/D2 release products are required for validation-only calibration audit")
    d1 = {sheet: _wide_sheet(d1_path, sheet) for sheet in D1_SHEETS}
    d2 = pd.read_excel(d2_path, sheet_name="D2_scores").rename(columns={"Unnamed: 0": "ts"})
    d2["ts"] = pd.to_datetime(d2["ts"], errors="raise")
    masks: dict[str, pd.Series] = {}
    for sensor in sensors:
        d1_mask = pd.concat(
            [d1[sheet][sensor].rename(sheet) for sheet in D1_SHEETS], axis=1
        ).ge(4.5).all(axis=1)
        sensor_d2 = d2.loc[d2["sensor_id"].eq(sensor)].set_index("ts").sort_index()
        d2_mask = sensor_d2["D2_Strict"].ge(4.5) & sensor_d2["usable_tag"].isin(ALLOWED_D2_TAGS)
        masks[sensor] = d1_mask & d2_mask.reindex(d1_mask.index).eq(True)
    return masks, {
        "d1_path": str(d1_path),
        "d1_sha256": _sha256(d1_path),
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
        item for item in sensor_meta
        if item["type"] == "DO" and item["process_zone"] == "aerobic"
    ]
    sensors = [item["id"] for item in aerobic]
    quality_masks, sources = _quality_masks(root, sensors)
    temperature_path = Path(temperature_minute.attrs["source_path"])
    sources["temperature_sha256"] = _sha256(temperature_path)
    if calibration["DO_hourly_statistic"] != "mean":
        raise ValueError("Frozen D3 temperature calibration requires hourly mean DO")
    hourly_do = frame[sensors].resample("1h").mean()
    minimum_minutes = int(calibration["minimum_valid_temperature_minutes_per_hour"])
    temperature_count = temperature_minute.resample("1h").count()
    temperature = temperature_minute.resample("1h").median().where(
        temperature_count >= minimum_minutes
    ).reindex(hourly_do.index)
    csat = pd.Series(
        freshwater_do_saturation_mg_l(temperature.to_numpy(dtype=float)),
        index=temperature.index,
        name="Csat_reference_mg_L",
    )
    phase = pd.Series(_phase(hourly_do.index, calibration), index=hourly_do.index)

    detail_rows = []
    for meta in aerobic:
        sensor = meta["id"]
        position = str(meta["position"])
        alpha = float(calibration["alpha_by_position"][position])
        observed = hourly_do[sensor]
        ratio = observed / csat
        high_quality = quality_masks[sensor].reindex(hourly_do.index).eq(True)
        detail_rows.append(
            pd.DataFrame(
                {
                    "ts": hourly_do.index,
                    "sensor_id": sensor,
                    "pool": meta["pool"],
                    "position": meta["position"],
                    "phase": phase.to_numpy(),
                    "DO_hourly_mean_mg_L": observed.to_numpy(),
                    "influent_temperature_C": temperature.to_numpy(),
                    "Csat_reference_mg_L": csat.to_numpy(),
                    "DO_over_Csat": ratio.to_numpy(),
                    "high_quality_filter_pass": high_quality.to_numpy(),
                    "frozen_alpha": alpha,
                    "dynamic_upper_mg_L": (alpha * csat).to_numpy(),
                    "dynamic_warning": (observed > alpha * csat).fillna(False).to_numpy(),
                }
            )
        )
    detail = pd.concat(detail_rows, ignore_index=True)

    registry_rows = []
    for position, group in detail.loc[
        detail["phase"].eq("calibration")
        & detail["high_quality_filter_pass"]
        & detail["DO_over_Csat"].notna()
    ].groupby("position"):
        ratios = group["DO_over_Csat"]
        median = float(ratios.median())
        mad_scale = float(1.4826 * (ratios - median).abs().median())
        p99 = float(ratios.quantile(0.99))
        recomputed = max(p99, median + 3.0 * mad_scale)
        frozen = float(calibration["alpha_by_position"][str(position)])
        support = int(calibration["calibration_support_sensor_hours"][str(position)])
        registry_rows.append(
            {
                "position": int(position),
                "sensor_ids": ",".join(sorted(group["sensor_id"].unique())),
                "n_calibration_sensor_hours": int(len(group)),
                "registered_support_sensor_hours": support,
                "minimum_support_sensor_hours": int(calibration["minimum_calibration_sensor_hours"]),
                "support_passed": int(len(group)) >= int(calibration["minimum_calibration_sensor_hours"]),
                "ratio_median": median,
                "ratio_mad_scale": mad_scale,
                "ratio_p99": p99,
                "recomputed_alpha": recomputed,
                "frozen_alpha": frozen,
                "absolute_difference": abs(recomputed - frozen),
                "registry_match": bool(np.isclose(recomputed, frozen, rtol=0.0, atol=1e-9)),
                "estimator": calibration["estimator"],
                "production_role": "frozen_operational_warning_only",
            }
        )
    registry = pd.DataFrame(registry_rows).sort_values("position")

    phase_rows = []
    for (sensor, phase_name), group in detail.loc[
        detail["phase"].isin(["calibration", "validation", "terminal_test"])
    ].groupby(["sensor_id", "phase"]):
        observed = group["DO_hourly_mean_mg_L"].notna() & group["influent_temperature_C"].notna()
        hq = observed & group["high_quality_filter_pass"]
        phase_rows.append(
            {
                "sensor_id": sensor,
                "phase": phase_name,
                "n_evaluable_hours": int(observed.sum()),
                "n_high_quality_hours": int(hq.sum()),
                "dynamic_warning_count_all": int(group.loc[observed, "dynamic_warning"].sum()),
                "dynamic_warning_count_high_quality": int(group.loc[hq, "dynamic_warning"].sum()),
                "dynamic_warning_rate_all": float(group.loc[observed, "dynamic_warning"].mean()),
                "dynamic_warning_rate_high_quality": (
                    float(group.loc[hq, "dynamic_warning"].mean()) if hq.any() else np.nan
                ),
                "median_dynamic_upper_mg_L": float(group.loc[observed, "dynamic_upper_mg_L"].median()),
                "p05_dynamic_upper_mg_L": float(group.loc[observed, "dynamic_upper_mg_L"].quantile(0.05)),
                "p95_dynamic_upper_mg_L": float(group.loc[observed, "dynamic_upper_mg_L"].quantile(0.95)),
                "score_role": (
                    "scored_operational_warning"
                    if str(int(group["position"].iloc[0])) in calibration["scored_positions"]
                    else "diagnostic_only"
                ),
            }
        )
    phase_validation = pd.DataFrame(phase_rows)

    sensitivity_rows = []
    for multiplier in (0.8, 0.9, 1.0, 1.1, 1.2):
        for (sensor, phase_name), group in detail.loc[
            detail["phase"].isin(["calibration", "validation", "terminal_test"])
        ].groupby(["sensor_id", "phase"]):
            observed = group["DO_hourly_mean_mg_L"].notna() & group["Csat_reference_mg_L"].notna()
            high_quality = observed & group["high_quality_filter_pass"]
            upper = multiplier * group["frozen_alpha"] * group["Csat_reference_mg_L"]
            warning = group["DO_hourly_mean_mg_L"] > upper
            position = str(int(group["position"].iloc[0]))
            sensitivity_rows.append(
                {
                    "sensor_id": sensor,
                    "position": int(position),
                    "phase": phase_name,
                    "alpha_multiplier": multiplier,
                    "n_evaluable_hours": int(observed.sum()),
                    "n_high_quality_hours": int(high_quality.sum()),
                    "warning_rate_all": float(warning[observed].mean()),
                    "warning_rate_high_quality": (
                        float(warning[high_quality].mean()) if high_quality.any() else np.nan
                    ),
                    "score_role": (
                        "scored_operational_warning"
                        if position in calibration["scored_positions"]
                        else "diagnostic_only"
                    ),
                }
            )
    alpha_sensitivity = pd.DataFrame(sensitivity_rows)

    study_hours = len(hourly_do)
    source_audit = pd.DataFrame(
        [
            {
                "temperature_source": temperature_path.name,
                "temperature_sha256": sources.get("temperature_sha256"),
                "temperature_start": temperature_minute.index.min(),
                "temperature_end": temperature_minute.index.max(),
                "temperature_rows": len(temperature_minute),
                "temperature_raw_missing": int(temperature_minute.attrs["raw_missing_count"]),
                "temperature_invalid_range": int(temperature_minute.attrs["invalid_range_count"]),
                "temperature_valid_min_C": float(temperature_minute.min()),
                "temperature_valid_max_C": float(temperature_minute.max()),
                "calibration_hour_min_valid_minutes": minimum_minutes,
                "study_hour_coverage": float(temperature.notna().sum() / study_hours),
                "alignment": "exact_minute_no_interpolation_no_extrapolation",
                "covariate_role": contract["covariate"],
                "interpretation": contract["interpretation"],
                "d1_sha256": sources["d1_sha256"],
                "d2_sha256": sources["d2_sha256"],
            }
        ]
    )
    exclusions = (
        detail.assign(
            exclusion=np.select(
                [
                    detail["influent_temperature_C"].isna(),
                    detail["DO_hourly_mean_mg_L"].isna(),
                    ~detail["high_quality_filter_pass"],
                ],
                ["temperature_unavailable", "DO_unavailable", "D1_D2_quality_filter_failed"],
                default="eligible",
            )
        )
        .groupby(["phase", "sensor_id", "exclusion"], as_index=False)
        .size()
        .rename(columns={"size": "n_sensor_hours"})
    )
    return {
        "source_audit": source_audit,
        "frozen_registry_check": registry,
        "phase_validation": phase_validation,
        "alpha_sensitivity": alpha_sensitivity,
        "exclusions": exclusions,
        "hourly_detail": detail,
    }, sources
