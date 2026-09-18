from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .config import D4Config, PairConfig, load_config

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from shared_data_foundation.context import build_foundation, pair_support
from .scoring import (
    adjacent_ks_change_timeline,
    aggregate_scores,
    compare_change_points,
    compute_window_metrics,
    score_from_quantiles,
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _phase_labels(timestamps: pd.Series, cfg: D4Config) -> np.ndarray:
    ts = pd.to_datetime(timestamps)
    development_start = pd.Timestamp(cfg.phase_contract["development_start"])
    development_end = pd.Timestamp(cfg.phase_contract["development_end"])
    embargo_start = pd.Timestamp(cfg.phase_contract["embargo_start"])
    embargo_end = pd.Timestamp(cfg.phase_contract["embargo_end"])
    validation_start = pd.Timestamp(cfg.phase_contract["internal_validation_start"])
    validation_end = pd.Timestamp(cfg.phase_contract["internal_validation_end"])
    return np.select(
        [
            ts.between(development_start, development_end),
            ts.between(embargo_start, embargo_end),
            ts.between(validation_start, validation_end),
        ],
        ["development", "embargo", "internal_validation"],
        default="outside_registered_period",
    )


def _independent_block_count(
    frame: pd.DataFrame,
    block_days: int,
    *,
    anchor: pd.Timestamp | str | None = None,
) -> int:
    if frame.empty:
        return 0
    days = pd.to_datetime(frame["timestamp"]).dt.floor("D")
    block_anchor = days.min() if anchor is None else pd.Timestamp(anchor).floor("D")
    return int(((days - block_anchor).dt.days // int(block_days)).nunique())


def _mapping_id(row: dict[str, object]) -> str:
    bound_fields = {
        key: str(row[key])
        for key in (
            "variable", "regime_id", "subscore", "risk_metric",
            "q50", "q75", "q90", "q97_5", "fit_start", "fit_end",
            "common_support_policy", "distribution_component_version",
            "min_exact_independent_blocks", "support_admission_rule",
        )
    }
    digest = hashlib.sha256(
        json.dumps(bound_fields, sort_keys=True).encode("utf-8")
    ).hexdigest()[:12]
    return f"{row['variable']}-R{row['regime_id']}-{row['subscore']}-{digest}"


def _block_quantile_precision(
    frame: pd.DataFrame,
    value_column: str,
    *,
    block_days: int,
    repetitions: int,
    seed: int,
    anchor: pd.Timestamp | str,
) -> dict[str, float | str]:
    source = frame.loc[frame[value_column].notna(), ["timestamp", value_column]].copy()
    days = pd.to_datetime(source["timestamp"]).dt.floor("D")
    source["_block"] = (
        (days - pd.Timestamp(anchor).floor("D")).dt.days // int(block_days)
    )
    blocks = [group[value_column].to_numpy(dtype=float) for _, group in source.groupby("_block")]
    rng = np.random.Generator(np.random.PCG64(seed))
    draws = {0.90: np.empty(repetitions), 0.975: np.empty(repetitions)}
    for iteration in range(repetitions):
        sampled = rng.integers(0, len(blocks), len(blocks))
        values = np.concatenate([blocks[index] for index in sampled])
        for quantile in draws:
            draws[quantile][iteration] = np.quantile(values, quantile)
    output: dict[str, float | str] = {}
    relative_widths = []
    for quantile, label in ((0.90, "q90"), (0.975, "q97_5")):
        point = float(source[value_column].quantile(quantile))
        low, high = np.quantile(draws[quantile], [0.025, 0.975])
        relative_width = float((high - low) / max(abs(point), 1e-12))
        output[f"{label}_block_CI_low"] = float(low)
        output[f"{label}_block_CI_high"] = float(high)
        output[f"{label}_relative_CI_width"] = relative_width
        relative_widths.append(relative_width)
    output["percentile_precision_max_relative_CI_width"] = max(relative_widths)
    return output


def _load_interpretation(
    cfg: D4Config,
) -> tuple[pd.DataFrame, pd.DataFrame, str, str]:
    d1 = pd.read_excel(cfg.paths["interpretation_d1"], sheet_name="D1_total_hourly")
    d1["timestamp"] = pd.to_datetime(d1["timestamp"])
    d1 = d1.set_index("timestamp").sort_index()

    d2 = pd.read_excel(cfg.paths["interpretation_d2"], sheet_name="D2_scores")
    d2 = d2.rename(columns={d2.columns[0]: "timestamp"})
    d2["timestamp"] = pd.to_datetime(d2["timestamp"])
    d2["veto_flag"] = pd.to_numeric(d2["veto_flag"], errors="coerce").fillna(1).astype(int)
    d2_run = str(d2["run_id"].dropna().iloc[0])
    d2_calibration = str(d2["calibration_id"].dropna().iloc[0])
    return d1, d2, d2_run, d2_calibration


def _pair_metrics(
    residuals: pd.DataFrame,
    pair: PairConfig,
    cfg: D4Config,
) -> pd.DataFrame:
    interval = cfg.analysis_interval_minutes
    window_points = cfg.window_hours * 60 // interval
    step_points = cfg.step_hours * 60 // interval
    points_per_hour = 60 // interval
    target = residuals[pair.target].to_numpy(dtype=float)
    reference = residuals[pair.reference].to_numpy(dtype=float)
    end_positions = list(range(window_points, len(residuals) + 1, step_points))
    output_index = pd.DatetimeIndex(
        [residuals.index[end_pos - 1].floor("h") for end_pos in end_positions]
    )
    cp_kwargs = {
        "auxiliary_window_days": int(cfg.change_point["auxiliary_window_days"]),
        "adjacent_segment_hours": int(cfg.change_point["adjacent_segment_hours"]),
        "candidate_step_hours": int(cfg.change_point["candidate_step_hours"]),
        "ks_stat_min": float(cfg.change_point["ks_stat_min"]),
        "pvalue_max": float(cfg.change_point["pvalue_max"]),
        "min_valid_fraction": cfg.min_valid_fraction,
    }
    target_cp = adjacent_ks_change_timeline(
        residuals[pair.target].resample("1h").median(), output_index, **cp_kwargs
    )
    reference_cp = adjacent_ks_change_timeline(
        residuals[pair.reference].resample("1h").median(), output_index, **cp_kwargs
    )
    cp_evidence = compare_change_points(target_cp, reference_cp).reset_index(drop=True)
    rows: list[dict[str, object]] = []
    for row_no, end_pos in enumerate(end_positions):
        start_pos = end_pos - window_points
        metrics = compute_window_metrics(
            target[start_pos:end_pos],
            reference[start_pos:end_pos],
            deadband=cfg.deadband[pair.variable],
            points_per_hour=points_per_hour,
            min_common_hour_fraction=float(cfg.common_support["min_hour_fraction"]),
            distribution_weights={
                key: float(value) for key, value in cfg.distribution["weights"].items()
            },
        )
        row = asdict(metrics)
        row.pop("q_cp_rule")
        row.update(cp_evidence.iloc[row_no].to_dict())
        row.update(
            # Hour-start labels represent evidence available at the next hour.
            timestamp=residuals.index[end_pos - 1].floor("h"),
            pair_id=pair.pair_id,
            sensor_id=pair.target,
            pair_sensor_id=pair.reference,
            zone=pair.zone,
            variable=pair.variable,
            deadband_used=cfg.deadband[pair.variable],
        )
        rows.append(row)
    return pd.DataFrame(rows)


def _add_context(
    raw: pd.DataFrame,
    d1: pd.DataFrame,
    d2: pd.DataFrame,
    regime: pd.Series,
    cfg: D4Config,
) -> pd.DataFrame:
    parts: list[pd.DataFrame] = []
    d2_lookup = d2.set_index(["timestamp", "sensor_id"])
    for pair_id, frame in raw.groupby("pair_id", sort=False):
        frame = frame.copy()
        target = str(frame["sensor_id"].iloc[0])
        reference = str(frame["pair_sensor_id"].iloc[0])
        ts = pd.DatetimeIndex(frame["timestamp"])
        frame["D1_target"] = d1[target].reindex(ts).to_numpy()
        frame["D1_ref"] = d1[reference].reindex(ts).to_numpy()
        frame["regime_id"] = regime.reindex(ts).to_numpy()
        for role, sensor in (("target", target), ("ref", reference)):
            idx = pd.MultiIndex.from_arrays([ts, np.repeat(sensor, len(ts))])
            context = d2_lookup.reindex(idx)
            frame[f"D2_{role}_tag"] = context["usable_tag"].to_numpy()
            frame[f"D2_{role}_veto"] = context["veto_flag"].to_numpy()
            frame[f"D2_{role}"] = context["D2_total"].to_numpy()
            sensor_d2 = d2[d2["sensor_id"].eq(sensor)].set_index("timestamp").sort_index()
            continuous = (
                sensor_d2["veto_flag"].eq(0)
                .rolling(
                    int(cfg.benchmark["d2_continuity_hours"]),
                    min_periods=int(cfg.benchmark["d2_continuity_hours"]),
                )
                .sum()
                .eq(int(cfg.benchmark["d2_continuity_hours"]))
            )
            frame[f"D2_{role}_continuous_24h"] = continuous.reindex(ts).fillna(False).to_numpy()
        parts.append(frame)
    return pd.concat(parts, ignore_index=True)


def _fit_and_score(
    raw: pd.DataFrame,
    cfg: D4Config,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    frame = raw.copy()
    for name in ("D1_target", "D1_ref", "D2_target", "D2_ref",
                 "D2_target_veto", "D2_ref_veto"):
        if name not in frame:
            frame[name] = np.nan
    for name in ("D2_target_tag", "D2_ref_tag"):
        if name not in frame:
            frame[name] = "not_consumed_by_core"
    for name in ("D2_target_continuous_24h", "D2_ref_continuous_24h"):
        if name not in frame:
            frame[name] = False
    frame["phase_id"] = _phase_labels(frame["timestamp"], cfg)
    data_ok = (
        frame["valid_fraction_common"].ge(float(cfg.common_support["min_fraction"]))
        & frame["valid_fraction_common_hours"].ge(
            float(cfg.common_support["trend_min_common_hour_fraction"])
        )
    )
    neutral_support_ok = (
        frame["raw_common_fraction_24h"].ge(float(cfg.common_support["min_fraction"]))
        & frame["raw_supported_hours_fraction"].ge(float(cfg.common_support["trend_min_common_hour_fraction"]))
        & frame["raw_complete_window"].eq(True)
    )
    frame["neutral_support_ok"] = neutral_support_ok
    high_quality = (
        data_ok
        & neutral_support_ok
        & frame["context_24h_valid"].eq(True)
        & frame["window_purity"].ge(float(cfg.benchmark["context_min_purity"]))
        & frame["phase_id"].eq("development")
    )
    if cfg.benchmark["reference_route"] == "screened_sensitivity":
        high_quality &= (frame["D1_target"].ge(cfg.benchmark["screened_reference_min_score"])
                         & frame["D1_ref"].ge(cfg.benchmark["screened_reference_min_score"])
                         & frame["D2_target_continuous_24h"] & frame["D2_ref_continuous_24h"])
    frame["reference_eligible"] = high_quality
    benchmark = frame.loc[high_quality].copy()
    benchmark["D5_screen_pass"] = pd.NA
    benchmark["benchmark_status"] = str(cfg.benchmark["d5_screen_status"])
    benchmark["benchmark_source"] = (
        "development_neutral_raw_support_stable_frozen_context"
    )
    benchmark["inclusion_criteria"] = (
        "raw bilateral support for complete 24 h; frozen context purity>=configured value; "
        "common timestamp support>=0.80; common-hour support>=0.80; "
        "phase=development; D5 screen pending"
    )

    quantile_levels = np.asarray(cfg.benchmark["quantiles"], dtype=float)
    min_stratum = int(cfg.benchmark["min_stratum_windows"])
    min_variable = int(cfg.benchmark["min_variable_windows"])
    independent_block_days = int(cfg.benchmark["independent_block_days"])
    min_exact_blocks = int(cfg.benchmark["min_exact_independent_blocks"])
    precision_cfg = cfg.benchmark["percentile_precision"]
    precision_repetitions = int(precision_cfg["bootstrap_repetitions"])
    precision_limit = float(precision_cfg["relative_ci_width_diagnostic_limit"])
    risk_to_q = {
        "risk_dist": ("Q_dist", "production"),
        "risk_dist_w1": ("Q_dist_w1_candidate", "construct_ablation_only"),
        "risk_dist_ks": ("Q_dist_ks_candidate", "construct_ablation_only"),
        "risk_trend": ("Q_trend", "production"),
        "risk_var": ("Q_var", "production"),
    }
    param_rows: list[dict[str, object]] = []
    for q_column, _ in risk_to_q.values():
        frame[q_column] = np.nan

    group_keys = frame[["variable", "regime_id"]].dropna().drop_duplicates()
    for _, key in group_keys.iterrows():
        variable = str(key["variable"])
        regime_value = key["regime_id"]
        regime_mask = frame["regime_id"].eq(regime_value) if pd.notna(regime_value) else frame["regime_id"].isna()
        target_mask = frame["variable"].eq(variable) & regime_mask
        exact_pool = benchmark[
            benchmark["variable"].eq(variable) & benchmark["regime_id"].eq(regime_value)
        ]
        variable_pool = benchmark[benchmark["variable"].eq(variable)]
        block_anchor = pd.Timestamp(cfg.phase_contract["development_start"])
        exact_blocks = _independent_block_count(
            exact_pool, independent_block_days, anchor=block_anchor
        )
        variable_blocks = _independent_block_count(
            variable_pool, independent_block_days, anchor=block_anchor
        )
        if len(exact_pool) >= min_stratum and exact_blocks >= min_exact_blocks:
            calibration = exact_pool
            mapping_scope = "variable_regime_public"
            calibration_quality = "adequate"
            fallback_reason = "none"
        elif len(variable_pool) >= min_variable and variable_blocks >= min_exact_blocks:
            calibration = variable_pool
            mapping_scope = "variable_public_fallback"
            calibration_quality = "limited_regime_support"
            failures = []
            if len(exact_pool) < min_stratum:
                failures.append(f"exact_windows={len(exact_pool)}<{min_stratum}")
            if exact_blocks < min_exact_blocks:
                failures.append(
                    f"exact_independent_blocks={exact_blocks}<{min_exact_blocks}"
                )
            fallback_reason = "; ".join(failures)
        else:
            calibration = benchmark
            mapping_scope = "global_normalized_fallback"
            calibration_quality = "insufficient_variable_support"
            fallback_reason = (
                f"variable_windows={len(variable_pool)}<{min_variable} or "
                f"variable_independent_blocks={variable_blocks}<{min_exact_blocks}"
            )
        if calibration.empty:
            raise ValueError("No development reference windows satisfy the locked admission contract")
        for risk_column, (q_column, mapping_role) in risk_to_q.items():
            calibration_rows = calibration.loc[calibration[risk_column].notna()].copy()
            values = calibration_rows[risk_column].to_numpy(dtype=float)
            if len(values) < 4:
                raise ValueError(f"Insufficient calibration values for {variable}/{regime_value}/{q_column}")
            thresholds = np.quantile(values, quantile_levels)
            precision_seed = int(hashlib.sha256(
                f"{variable}|{regime_value}|{risk_column}|D4V151".encode("utf-8")
            ).hexdigest()[:8], 16)
            precision = _block_quantile_precision(
                calibration_rows, risk_column,
                block_days=independent_block_days,
                repetitions=precision_repetitions,
                seed=precision_seed,
                anchor=block_anchor,
            )
            exact_precision: dict[str, float | str] = {}
            exact_risk_rows = exact_pool.loc[exact_pool[risk_column].notna()].copy()
            if len(exact_risk_rows) >= 4 and exact_blocks >= 2:
                raw_exact_precision = _block_quantile_precision(
                    exact_risk_rows, risk_column,
                    block_days=independent_block_days,
                    repetitions=precision_repetitions,
                    seed=precision_seed + 1,
                    anchor=block_anchor,
                )
                exact_precision = {
                    f"exact_candidate_{key}": value
                    for key, value in raw_exact_precision.items()
                }
                exact_precision_grade = (
                    "supported"
                    if float(raw_exact_precision[
                        "percentile_precision_max_relative_CI_width"
                    ]) <= precision_limit
                    else "wide_interval"
                )
            else:
                exact_precision_grade = "insufficient_independent_support"
            precision_grade = (
                "supported"
                if float(precision["percentile_precision_max_relative_CI_width"])
                <= precision_limit
                else "wide_interval"
            )
            mapping_evidence_quality = (
                "fallback_limited_regime_support"
                if mapping_scope != "variable_regime_public"
                else (
                    "admitted_minimum_support_tail_precision_wide"
                    if precision_grade == "wide_interval"
                    else "admitted_supported_precision"
                )
            )
            frame.loc[target_mask, q_column] = score_from_quantiles(
                frame.loc[target_mask, risk_column].to_numpy(dtype=float), thresholds
            )
            param_row = {
                "variable": variable,
                "regime_id": regime_value,
                "subscore": q_column,
                "risk_metric": risk_column,
                "q50": thresholds[0],
                "q75": thresholds[1],
                "q90": thresholds[2],
                "q97_5": thresholds[3],
                "sample_size": len(values),
                "exact_stratum_size": len(exact_pool),
                "independent_blocks": _independent_block_count(
                    calibration_rows, independent_block_days, anchor=block_anchor
                ),
                "exact_independent_blocks": exact_blocks,
                "variable_independent_blocks": variable_blocks,
                "min_exact_independent_blocks": min_exact_blocks,
                "support_admission_rule": "minimum_windows_and_independent_7d_blocks",
                "fallback_reason": fallback_reason,
                "mapping_scope": mapping_scope,
                "calibration_quality": calibration_quality,
                "mapping_evidence_quality": mapping_evidence_quality,
                "percentile_precision_grade": precision_grade,
                "exact_candidate_percentile_precision_grade": exact_precision_grade,
                "percentile_precision_role": precision_cfg["admission_role"],
                "percentile_precision_bootstrap_repetitions": precision_repetitions,
                **precision,
                **exact_precision,
                "mapping_role": mapping_role,
                "fit_phase": "development",
                "fit_start": calibration_rows["timestamp"].min(),
                "fit_end": calibration_rows["timestamp"].max(),
                "configured_fit_start": pd.Timestamp(cfg.phase_contract["development_start"]),
                "configured_fit_end": pd.Timestamp(cfg.phase_contract["development_end"]),
                "common_support_policy": str(cfg.common_support["policy"]),
                "distribution_component_version": str(
                    cfg.distribution["component_version"]
                ),
                "benchmark_source": (
                    "development_neutral_raw_support_stable_context"
                ),
                "mapping_type": "public_quantile_by_variable_and_regime",
            }
            param_row["mapping_id"] = _mapping_id(param_row)
            param_rows.append(param_row)
    frame.loc[frame["deadband_active"], "Q_var"] = 5.0
    frame["D4_base"], frame["D4_raw"] = aggregate_scores(
        frame["Q_dist"].to_numpy(),
        frame["Q_trend"].to_numpy(),
        frame["Q_var"].to_numpy(),
        frame["Q_cp"].to_numpy(),
        weights=cfg.weights,
        lambda_blend=cfg.lambda_blend,
    )
    frame["usable_for_D4"] = data_ok & neutral_support_ok & frame["regime_id"].notna() & frame["D4_raw"].notna()
    frame["D4_total"] = frame["D4_raw"].where(frame["usable_for_D4"])

    frame["fuse_state"] = "retired_interpretation_only"
    frame["fuse_active"] = False
    frame["D4_after_D1"] = np.nan
    frame["D4_forDQR_provisional"] = frame["D4_total"]
    frame["D4_forDQR"] = np.nan
    frame["D4_forDQR_status"] = np.where(
        frame["usable_for_D4"],
        str(cfg.arbitration["provisional_status"]),
        "not_evaluable_raw_support_or_metric",
    )
    frame["D4_forDQR_is_final"] = False
    frame["D5_zone_consensus_label"] = "not_available"
    frame["D5_zone_consensus_strength"] = np.nan
    frame["usable_for_DQR"] = False

    evidence = frame[["Q_dist", "Q_trend", "Q_var", "Q_cp"]]
    frame["dominant_evidence"] = evidence.idxmin(axis=1).str.replace("Q_", "", regex=False)
    ordered = np.argsort(evidence.fillna(np.inf).to_numpy(dtype=float), axis=1)
    labels = np.array(["dist", "trend", "var", "cp"], dtype=object)
    frame["second_evidence"] = labels[ordered[:, 1]]
    gap = np.take_along_axis(evidence.fillna(np.inf).to_numpy(dtype=float), ordered[:, :2], axis=1)
    frame.loc[(gap[:, 1] - gap[:, 0]) < 0.5, "second_evidence"] = "mixed"
    consistent_min = float(cfg.classification["consistent_min"])
    asymmetry_max = float(cfg.classification["asymmetry_max"])
    frame["raw_status_label"] = np.select(
        [~frame["usable_for_D4"], frame["D4_raw"].lt(asymmetry_max),
         frame["D4_raw"].ge(consistent_min)],
        ["not_evaluable", "pair_asymmetry", "paired_consistent"],
        default="borderline",
    )
    frame["status_label"] = frame["raw_status_label"]
    frame["causal_attribution"] = np.where(
        frame["status_label"].eq("core_pending_external_D5_gate"),
        "pending_sensor_vs_process_adjudication",
        "external_D5_action_gate_required",
    )
    params = pd.DataFrame(param_rows)
    metadata = params.loc[params["mapping_role"].eq("production")].groupby(
        ["variable", "regime_id"], as_index=False
    ).agg(
        calibration_scope=("mapping_scope", lambda x: "|".join(sorted(set(x)))),
        calibration_quality=("calibration_quality", lambda x: "|".join(sorted(set(x)))),
        calibration_evidence_quality=("mapping_evidence_quality", lambda x: "|".join(sorted(set(x)))),
        calibration_independent_blocks=("independent_blocks", "min"),
        calibration_tail_precision_grade=("percentile_precision_grade", lambda x: "wide_interval" if "wide_interval" in set(x) else "supported"),
    )
    frame = frame.merge(metadata, on=["variable", "regime_id"], how="left", validate="many_to_one")
    return frame, params, benchmark


def _events(main: pd.DataFrame, min_hours: int) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    event_no = 1
    for pair_id, frame in main.sort_values("timestamp").groupby("pair_id"):
        active = frame["usable_for_D4"] & frame["D4_raw"].lt(3.0)
        groups = active.ne(active.shift(fill_value=False)).cumsum()
        for _, event in frame[active].groupby(groups[active]):
            duration = (event["timestamp"].max() - event["timestamp"].min()).total_seconds() / 3600 + 1
            if duration < min_hours:
                continue
            rows.append({
                "event_id": f"D4-EVT-{event_no:04d}", "pair_id": pair_id,
                "start_ts": event["timestamp"].min(), "end_ts": event["timestamp"].max(),
                "duration_h": duration, "min_D4_raw": event["D4_raw"].min(),
                "mean_D4_raw": event["D4_raw"].mean(),
                "min_D4_forDQR_provisional": event["D4_forDQR_provisional"].min(),
                "dominant_evidence": event["dominant_evidence"].mode().iloc[0],
                "D1_target_mean": event["D1_target"].mean(), "D1_ref_mean": event["D1_ref"].mean(),
                "D2_target_tag": event["D2_target_tag"].mode().iloc[0],
                "D2_ref_tag": event["D2_ref_tag"].mode().iloc[0],
                "D5_zone_consensus_summary": "external_D5_gate_not_applied_in_core",
                "causal_attribution": "pending_sensor_vs_process_adjudication",
            })
            event_no += 1
    return pd.DataFrame(rows)


def _profile(main: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    profile = main.groupby(["pair_id", "zone", "sensor_id", "pair_sensor_id"], as_index=False).agg(
        mean_D4_raw=("D4_total", "mean"), median_D4_raw=("D4_total", "median"),
        p05_D4_raw=("D4_total", lambda x: x.quantile(0.05)),
        mean_D4_provisional=("D4_forDQR_provisional", "mean"),
        evaluable_rate=("usable_for_D4", "mean"), deadband_rate=("deadband_active", "mean"),
        fuse_active_rate=("fuse_active", "mean"),
        mean_Q_dist=("Q_dist", "mean"), mean_Q_trend=("Q_trend", "mean"),
        mean_Q_var=("Q_var", "mean"), mean_Q_cp=("Q_cp", "mean"),
    )
    low_rate = main.groupby("pair_id").apply(
        lambda group: (
            group.loc[group["usable_for_D4"], "D4_raw"].lt(3.0).mean()
            if group["usable_for_D4"].any() else np.nan
        ),
        include_groups=False,
    )
    profile["low_score_rate"] = profile["pair_id"].map(low_rate)
    counts = events.groupby("pair_id").size().rename("n_events") if not events.empty else pd.Series(dtype=int)
    profile["n_events"] = profile["pair_id"].map(counts).fillna(0).astype(int)
    return profile


def _multiscale(main: pd.DataFrame) -> dict[str, pd.DataFrame]:
    source = main.set_index("timestamp")
    outputs: dict[str, pd.DataFrame] = {}
    for label, freq in (("daily", "1D"), ("weekly", "W-MON")):
        rows = []
        for pair_id, frame in source.groupby("pair_id"):
            raw = frame["D4_total"].resample(freq).agg(
                D4_raw_gate=lambda x: x.quantile(0.05),
                D4_raw_report=lambda x: x.quantile(0.25),
                D4_raw_mean="mean", D4_raw_median="median", n_windows="count",
            )
            provisional = frame["D4_forDQR_provisional"].resample(freq).agg(
                D4_provisional_gate=lambda x: x.quantile(0.05),
                D4_provisional_report=lambda x: x.quantile(0.25),
                D4_provisional_mean="mean",
            )
            agg = raw.join(provisional)
            agg["pair_id"] = pair_id
            agg["D4_forDQR_status"] = "core_pending_external_D5_gate"
            rows.append(agg.reset_index())
        outputs[label] = pd.concat(rows, ignore_index=True)
    return outputs


def _write_excel(path: Path, sheets: dict[str, pd.DataFrame]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for sheet_name, frame in sheets.items():
            frame.to_excel(writer, sheet_name=sheet_name[:31], index=False)


def run_pipeline(project_root: Path, d4_root: Path, *, include_interpretation: bool = True) -> dict[str, object]:
    config_path = d4_root / "configs" / "d4.yaml"
    cfg = load_config(config_path, project_root)
    output_dir = d4_root / "outputs" / "data"
    output_dir.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("D4V16_%Y%m%d_%H%M%S")

    residuals = pd.read_parquet(cfg.paths["residuals"])
    columns = sorted({p.target for p in cfg.pairs} | {p.reference for p in cfg.pairs})
    observations, context, context_asset = build_foundation(
        project_root, str(cfg.phase_contract["development_start"]),
        str(pd.Timestamp(cfg.phase_contract["development_end"]) + pd.Timedelta(seconds=1)),
    )
    frequency = f"{cfg.analysis_interval_minutes}min"
    raw_presence = observations[columns].notna().resample(frequency).mean()
    residuals = residuals[columns].where(observations[columns].notna()).resample(frequency).median()
    residuals = residuals.where(raw_presence.ge(float(cfg.common_support["min_fraction"])))
    raw = pd.concat([_pair_metrics(residuals, pair, cfg) for pair in cfg.pairs], ignore_index=True)
    raw = raw.merge(context, left_on="timestamp", right_index=True, validate="many_to_one")
    parts = []
    for pair in cfg.pairs:
        support = pair_support(observations, pair.target, pair.reference, cfg.window_hours)
        parts.append(raw.loc[raw["pair_id"].eq(pair.pair_id)].merge(
            support, left_on="timestamp", right_index=True, validate="one_to_one"))
    raw = pd.concat(parts, ignore_index=True)
    raw.to_parquet(output_dir / "D4_neutral_core_input.parquet", index=False)
    main, params, benchmark = _fit_and_score(raw, cfg)
    d2_run, d2_calibration = "not_consumed_by_core", "not_consumed_by_core"
    if include_interpretation and all(cfg.paths[k].exists() for k in ("interpretation_d1", "interpretation_d2")):
        d1, d2, d2_run, d2_calibration = _load_interpretation(cfg)
        main = _add_context(main, d1, d2, context["regime_id"], cfg)
    calibration_digest = hashlib.sha256(
        pd.util.hash_pandas_object(params.fillna("<NA>"), index=False).to_numpy().tobytes()
    ).hexdigest()
    calibration_id = f"D4CAL-V16-{calibration_digest[:12]}"
    main["run_id"] = run_id
    main["config_version"] = cfg.version
    main["calibration_id"] = calibration_id
    main["d2_run_id"] = d2_run
    events = _events(main, int(cfg.classification["event_min_hours"]))
    profile = _profile(main, events)
    multiscale = _multiscale(main)

    score_columns = [
        "calibration_scope", "calibration_quality", "calibration_evidence_quality",
        "calibration_independent_blocks", "calibration_tail_precision_grade",
        "reference_eligible", "neutral_support_ok", "raw_common_fraction_24h",
        "raw_supported_hours_fraction", "raw_complete_window", "window_purity",
        "context_24h_valid", "context_model_id", "available_at",
        "timestamp", "phase_id", "pair_id", "sensor_id", "pair_sensor_id", "zone", "variable", "regime_id",
        "Q_dist", "Q_trend", "Q_var", "Q_cp", "D4_base", "D4_raw", "D4_total",
        "D4_after_D1", "D4_forDQR_provisional", "D4_forDQR", "D4_forDQR_status",
        "D4_forDQR_is_final", "raw_status_label", "status_label", "causal_attribution",
        "fuse_state", "fuse_active", "dominant_evidence", "second_evidence",
        "deadband_active", "deadband_used", "D1_target", "D1_ref",
        "D5_zone_consensus_label", "D5_zone_consensus_strength",
        "D2_target", "D2_ref", "D2_target_tag", "D2_ref_tag", "D2_target_veto",
        "D2_ref_veto", "D2_target_continuous_24h", "D2_ref_continuous_24h",
        "valid_fraction_target", "valid_fraction_reference", "n_common", "n_common_hours",
        "valid_fraction_common", "valid_fraction_common_hours",
        "asymmetric_missing_fraction", "support_jaccard", "usable_for_D4",
        "usable_for_DQR", "run_id", "config_version", "calibration_id", "d2_run_id",
    ]
    raw_columns = [
        "timestamp", "phase_id", "pair_id", "d_w1", "d_ks", "beta_target", "beta_reference",
        "d_beta", "iqr_target", "iqr_reference", "d_var", "cp_time_target",
        "cp_time_reference", "cp_strength_target", "cp_strength_reference",
        "cp_age_target_h", "cp_age_reference_h", "d_cp", "cp_one_sided",
        "risk_dist", "risk_dist_w1", "risk_dist_ks", "risk_trend", "risk_var", "risk_cp", "Q_cp",
        "deadband_active", "n_target", "n_reference",
        "n_common", "n_common_hours", "valid_fraction_target", "valid_fraction_reference",
        "valid_fraction_common", "valid_fraction_common_hours", "asymmetric_missing_fraction",
        "support_jaccard",
    ]
    _write_excel(output_dir / "D4_main_scores.xlsx", {
        "main_scores": main[score_columns], "pair_profile": profile,
    })
    _write_excel(output_dir / "D4_detector_outputs_raw.xlsx", {"detector_outputs": main[raw_columns]})
    _write_excel(output_dir / "D4_mapping_params.xlsx", {
        "public_quantiles": params,
        "aggregation": pd.DataFrame([{"component": k, "weight": v} for k, v in cfg.weights.items()] +
                                    [{"component": "lambda_blend", "weight": cfg.lambda_blend}]),
        "deadband": pd.DataFrame([{"variable": k, "delta_phys": v} for k, v in cfg.deadband.items()]),
        "version": pd.DataFrame([{
            "config_version": cfg.version, "calibration_id": calibration_id, "run_id": run_id,
            "D5_status": "pending_not_available",
            "fit_period": (
                f"{cfg.phase_contract['development_start']} to "
                f"{cfg.phase_contract['development_end']}"
            ),
            "validation_period": (
                f"{cfg.phase_contract['internal_validation_start']} to "
                f"{cfg.phase_contract['internal_validation_end']}"
            ),
            "terminal_status": cfg.phase_contract["terminal_status"],
            "common_support_contract": cfg.common_support["policy"],
            "distribution_component_version": cfg.distribution["component_version"],
            "calibration_support_rule": "minimum_windows_and_independent_7d_blocks",
            "min_exact_independent_blocks": cfg.benchmark["min_exact_independent_blocks"],
            "percentile_precision_role": cfg.benchmark["percentile_precision"]["admission_role"],
        }]),
    })
    _write_excel(output_dir / "D4_pair_benchmark_library.xlsx", {
        "benchmark_windows": benchmark[[
            "timestamp", "phase_id", "pair_id", "variable", "regime_id", "D1_target", "D1_ref",
            "D2_target_tag", "D2_ref_tag", "D2_target_continuous_24h",
            "D2_ref_continuous_24h", "D5_screen_pass", "benchmark_status",
            "n_common", "valid_fraction_common", "valid_fraction_common_hours",
            "d_w1", "d_ks", "risk_dist_w1", "risk_dist_ks", "d_beta", "d_var",
            "benchmark_source", "inclusion_criteria",
        ]],
        "risk_quantiles": params,
    })
    _write_excel(output_dir / "D4_event_windows.xlsx", {"events": events})
    _write_excel(output_dir / "D4_pair_profile_summary.xlsx", {"pair_profile": profile})
    _write_excel(output_dir / "D4_multiscale_aggregates.xlsx", multiscale)
    boundary = pd.DataFrame([
        {"layer": "shared raw support", "effect": "gate D4 evaluability", "output": "usable_for_D4"},
        {"layer": "D1 interpretation", "effect": "post-score join only", "output": "D1_target;D1_ref"},
        {
            "layer": "D5 report/gate interface",
            "effect": "isolated from the core; no proxy generated",
            "output": "external_integration_only",
        },
    ])
    arbitration = main[[
        "timestamp", "pair_id", "D4_raw", "D1_target", "D1_ref", "fuse_state",
        "D4_after_D1", "D5_zone_consensus_label", "D4_forDQR_provisional",
        "D4_forDQR", "D4_forDQR_status", "D4_forDQR_is_final",
    ]]
    _write_excel(output_dir / "D4_arbitration_log.xlsx", {
        "arbitration_transitions": arbitration,
        "boundary_contract": boundary,
    })

    dependencies = []
    for name, path in cfg.paths.items():
        if name.startswith("interpretation_"):
            continue
        dependencies.append({
            "dependency": name, "path_role": path.name, "sha256": _sha256(path),
            "modified_utc": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
        })
    for name, path in (
        ("d4_config", config_path),
        ("d4_pipeline_code", Path(__file__)),
        ("d4_scoring_code", Path(__file__).with_name("scoring.py")),
        ("shared_context_code", project_root / "shared_data_foundation" / "context.py"),
    ):
        dependencies.append({
            "dependency": name, "path_role": path.name, "sha256": _sha256(path),
            "modified_utc": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
        })
    audit = pd.DataFrame([
        {"key": "run_id", "value": run_id}, {"key": "config_version", "value": cfg.version},
        {"key": "calibration_id", "value": calibration_id},
        {"key": "fit_phase", "value": "development"},
        {"key": "fit_start", "value": cfg.phase_contract["development_start"]},
        {"key": "fit_end", "value": cfg.phase_contract["development_end"]},
        {"key": "internal_validation_start", "value": cfg.phase_contract["internal_validation_start"]},
        {"key": "internal_validation_end", "value": cfg.phase_contract["internal_validation_end"]},
        {"key": "terminal_status", "value": cfg.phase_contract["terminal_status"]},
        {"key": "common_support_policy", "value": cfg.common_support["policy"]},
        {"key": "distribution_component_version", "value": cfg.distribution["component_version"]},
        {"key": "generated_utc", "value": datetime.now(timezone.utc).isoformat()},
        {"key": "d2_run_id", "value": d2_run}, {"key": "d2_calibration_id", "value": d2_calibration},
        {"key": "n_rows", "value": len(main)}, {"key": "n_pairs", "value": len(cfg.pairs)},
        {"key": "data_start", "value": residuals.index.min()},
        {"key": "data_end", "value": residuals.index.max()},
        {"key": "evaluable_rate_D4_raw", "value": float(main["usable_for_D4"].mean())},
        {"key": "D4_forDQR_status", "value": "provisional only; pending D5 arbitration"},
        {"key": "benchmark_D5_screen", "value": "pending; no D5 proxy generated"},
        {"key": "causal_claim", "value": "pair asymmetry only; sensor/process cause pending D5"},
    ])
    _write_excel(output_dir / "D4_audit_log.xlsx", {
        "run_manifest": audit, "dependencies": pd.DataFrame(dependencies),
        "boundary_contract": boundary,
    })
    manifest = {
        "run_id": run_id, "config_version": cfg.version,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "data_span": [str(residuals.index.min()), str(residuals.index.max())],
        "rows": len(main), "pairs": len(cfg.pairs), "d2_run_id": d2_run,
        "calibration_id": calibration_id,
        "phase_contract": cfg.phase_contract,
        "common_support_contract": cfg.common_support,
        "distribution_component_version": cfg.distribution["component_version"],
        "calibration_support_contract": {
            "min_stratum_windows": cfg.benchmark["min_stratum_windows"],
            "min_variable_windows": cfg.benchmark["min_variable_windows"],
            "independent_block_days": cfg.benchmark["independent_block_days"],
            "min_exact_independent_blocks": cfg.benchmark["min_exact_independent_blocks"],
            "percentile_precision": cfg.benchmark["percentile_precision"],
        },
        "terminal_status": cfg.phase_contract["terminal_status"],
        "dependencies": dependencies,
        "context_asset": context_asset,
        "reference_route": cfg.benchmark["reference_route"],
        "D1_D2_core_score_or_gate_inputs": False,
        "scientific_boundary": (
            "D4_raw uses neutral reference and raw observability; "
            "D1 is interpretation-only; the separate D5 report/gate interface "
            "cannot rewrite D4_raw."
        ),
        "benchmark_status": "core_complete_external_D5_gate_separate",
    }
    (output_dir / "D4_run_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    return {"config": cfg, "main": main, "raw": raw, "params": params,
            "benchmark": benchmark, "events": events, "profile": profile,
            "manifest": manifest}
