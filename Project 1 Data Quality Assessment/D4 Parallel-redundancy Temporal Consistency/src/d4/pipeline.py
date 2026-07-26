from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .config import D4Config, PairConfig, load_config
from .scoring import (
    adjacent_ks_change_timeline,
    aggregate_scores,
    apply_d1_fuse,
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


def _load_context(
    cfg: D4Config,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, str, str]:
    d1 = pd.read_excel(cfg.paths["d1_scores"], sheet_name="D1_total_hourly")
    d1["timestamp"] = pd.to_datetime(d1["timestamp"])
    d1 = d1.set_index("timestamp").sort_index()

    regime_frame = pd.read_excel(cfg.paths["regime_templates"], sheet_name="regime_labels_hourly")
    if len(regime_frame) != len(d1):
        raise ValueError("D1 regime labels must align one-to-one with D1 hourly scores")
    if "timestamp" not in regime_frame.columns:
        raise ValueError("D1 regime labels require an explicit timestamp column")
    regime_timestamps = pd.DatetimeIndex(pd.to_datetime(regime_frame["timestamp"]))
    if not regime_timestamps.equals(pd.DatetimeIndex(d1.index)):
        raise ValueError("D1 regime-label timestamps do not match D1 hourly scores")
    regime = pd.Series(
        regime_frame["regime_id"].to_numpy(), index=d1.index, name="regime_id"
    )

    d2 = pd.read_excel(cfg.paths["d2_scores"], sheet_name="D2_scores")
    d2 = d2.rename(columns={d2.columns[0]: "timestamp"})
    d2["timestamp"] = pd.to_datetime(d2["timestamp"])
    d2["veto_flag"] = pd.to_numeric(d2["veto_flag"], errors="coerce").fillna(1).astype(int)
    d2_run = str(d2["run_id"].dropna().iloc[0])
    d2_calibration = str(d2["calibration_id"].dropna().iloc[0])
    return d1, d2, regime, d2_run, d2_calibration


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
        )
        row = asdict(metrics)
        row.pop("q_cp_rule")
        row.update(cp_evidence.iloc[row_no].to_dict())
        row.update(
            # The 23:00 D2 row represents the completed 23:00-23:59 hour.
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
    data_ok = (
        frame["valid_fraction_target"].ge(cfg.min_valid_fraction)
        & frame["valid_fraction_reference"].ge(cfg.min_valid_fraction)
    )
    d2_ok = frame["D2_target_veto"].eq(0) & frame["D2_ref_veto"].eq(0)
    high_quality = (
        data_ok
        & frame["D1_target"].ge(float(cfg.benchmark["d1_min_score"]))
        & frame["D1_ref"].ge(float(cfg.benchmark["d1_min_score"]))
        & frame["D2_target_continuous_24h"]
        & frame["D2_ref_continuous_24h"]
    )
    benchmark = frame.loc[high_quality].copy()
    benchmark["D5_screen_pass"] = pd.NA
    benchmark["benchmark_status"] = str(cfg.benchmark["d5_screen_status"])
    benchmark["benchmark_source"] = (
        "v1.2_D1ge4.5_D2continuous24h_external_D5_gate"
    )
    benchmark["inclusion_criteria"] = (
        "D1_target>=4.5; D1_ref>=4.5; bilateral D2 usable for 24 h; "
        "data completeness>=0.80; D5 screen pending"
    )

    quantile_levels = np.asarray(cfg.benchmark["quantiles"], dtype=float)
    min_stratum = int(cfg.benchmark["min_stratum_windows"])
    min_variable = int(cfg.benchmark["min_variable_windows"])
    risk_to_q = {
        "risk_dist": "Q_dist",
        "risk_trend": "Q_trend",
        "risk_var": "Q_var",
    }
    param_rows: list[dict[str, object]] = []
    for q_column in risk_to_q.values():
        frame[q_column] = np.nan

    group_keys = frame[["variable", "regime_id"]].drop_duplicates()
    for _, key in group_keys.iterrows():
        variable = str(key["variable"])
        regime_value = key["regime_id"]
        regime_mask = frame["regime_id"].eq(regime_value) if pd.notna(regime_value) else frame["regime_id"].isna()
        target_mask = frame["variable"].eq(variable) & regime_mask
        exact_pool = benchmark[
            benchmark["variable"].eq(variable) & benchmark["regime_id"].eq(regime_value)
        ]
        variable_pool = benchmark[benchmark["variable"].eq(variable)]
        if len(exact_pool) >= min_stratum:
            calibration = exact_pool
            mapping_scope = "variable_regime_public"
            calibration_quality = "adequate"
        elif len(variable_pool) >= min_variable:
            calibration = variable_pool
            mapping_scope = "variable_public_fallback"
            calibration_quality = "limited_regime_support"
        else:
            calibration = benchmark
            mapping_scope = "global_normalized_fallback"
            calibration_quality = "insufficient_variable_support"
        if calibration.empty:
            raise ValueError("No v1.2 high-quality benchmark windows are available")
        for risk_column, q_column in risk_to_q.items():
            values = calibration[risk_column].dropna().to_numpy(dtype=float)
            if len(values) < 4:
                raise ValueError(f"Insufficient calibration values for {variable}/{regime_value}/{q_column}")
            thresholds = np.quantile(values, quantile_levels)
            frame.loc[target_mask, q_column] = score_from_quantiles(
                frame.loc[target_mask, risk_column].to_numpy(dtype=float), thresholds
            )
            param_rows.append({
                "mapping_id": f"{variable}-R{regime_value}-{q_column}",
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
                "mapping_scope": mapping_scope,
                "calibration_quality": calibration_quality,
                "benchmark_source": "v1.2_high_quality_public_external_D5_gate",
                "mapping_type": "public_quantile_by_variable_and_regime",
            })
    frame.loc[frame["deadband_active"], "Q_var"] = 5.0
    frame["D4_base"], frame["D4_raw"] = aggregate_scores(
        frame["Q_dist"].to_numpy(),
        frame["Q_trend"].to_numpy(),
        frame["Q_var"].to_numpy(),
        frame["Q_cp"].to_numpy(),
        weights=cfg.weights,
        lambda_blend=cfg.lambda_blend,
    )
    frame["usable_for_D4"] = data_ok & d2_ok & frame["D4_raw"].notna()
    frame["D4_total"] = frame["D4_raw"].where(frame["usable_for_D4"])

    d1_available = frame["D1_target"].notna() & frame["D1_ref"].notna()
    after_d1, fuse_state = apply_d1_fuse(
        frame["D4_raw"].to_numpy(),
        frame["D1_target"].to_numpy(),
        frame["D1_ref"].to_numpy(),
        frame["usable_for_D4"].to_numpy(),
        unreliable_below=float(cfg.arbitration["d1_unreliable_below"]),
    )
    frame["fuse_state"] = fuse_state
    frame["fuse_active"] = frame["fuse_state"].ne("valid_pair")
    frame["D4_after_D1"] = after_d1
    frame["D4_forDQR_provisional"] = after_d1
    frame["D4_forDQR"] = np.nan
    frame["D4_forDQR_status"] = np.where(
        frame["usable_for_D4"] & d1_available,
        str(cfg.arbitration["provisional_status"]),
        "not_evaluable_or_D1_missing",
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
    frame["status_label"] = np.select(
        [~frame["usable_for_D4"], frame["D4_after_D1"].ge(consistent_min),
         frame["fuse_active"]],
        ["not_evaluable", "paired_consistent", "ambiguous_asymmetry"],
        default="core_pending_external_D5_gate",
    )
    frame["causal_attribution"] = np.where(
        frame["status_label"].eq("core_pending_external_D5_gate"),
        "pending_sensor_vs_process_adjudication",
        "external_D5_action_gate_required",
    )
    return frame, pd.DataFrame(param_rows), benchmark


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


def run_pipeline(project_root: Path, d4_root: Path) -> dict[str, object]:
    config_path = d4_root / "configs" / "d4.yaml"
    cfg = load_config(config_path, project_root)
    output_dir = d4_root / "outputs" / "data"
    output_dir.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("D4V14_%Y%m%d_%H%M%S")

    residuals = pd.read_parquet(cfg.paths["residuals"])
    columns = sorted({p.target for p in cfg.pairs} | {p.reference for p in cfg.pairs})
    residuals = residuals[columns].resample(f"{cfg.analysis_interval_minutes}min").median()
    d1, d2, regime, d2_run, d2_calibration = _load_context(cfg)
    raw = pd.concat([_pair_metrics(residuals, pair, cfg) for pair in cfg.pairs], ignore_index=True)
    raw = _add_context(raw, d1, d2, regime, cfg)
    main, params, benchmark = _fit_and_score(raw, cfg)
    calibration_digest = hashlib.sha256(
        pd.util.hash_pandas_object(params.fillna("<NA>"), index=False).to_numpy().tobytes()
    ).hexdigest()
    calibration_id = f"D4CAL-V14-{calibration_digest[:12]}"
    main["run_id"] = run_id
    main["config_version"] = cfg.version
    main["calibration_id"] = calibration_id
    main["d2_run_id"] = d2_run
    events = _events(main, int(cfg.classification["event_min_hours"]))
    profile = _profile(main, events)
    multiscale = _multiscale(main)

    score_columns = [
        "timestamp", "pair_id", "sensor_id", "pair_sensor_id", "zone", "variable", "regime_id",
        "Q_dist", "Q_trend", "Q_var", "Q_cp", "D4_base", "D4_raw", "D4_total",
        "D4_after_D1", "D4_forDQR_provisional", "D4_forDQR", "D4_forDQR_status",
        "D4_forDQR_is_final", "raw_status_label", "status_label", "causal_attribution",
        "fuse_state", "fuse_active", "dominant_evidence", "second_evidence",
        "deadband_active", "deadband_used", "D1_target", "D1_ref",
        "D5_zone_consensus_label", "D5_zone_consensus_strength",
        "D2_target", "D2_ref", "D2_target_tag", "D2_ref_tag", "D2_target_veto",
        "D2_ref_veto", "D2_target_continuous_24h", "D2_ref_continuous_24h",
        "valid_fraction_target", "valid_fraction_reference", "usable_for_D4",
        "usable_for_DQR", "run_id", "config_version", "calibration_id", "d2_run_id",
    ]
    raw_columns = [
        "timestamp", "pair_id", "d_w1", "d_ks", "beta_target", "beta_reference",
        "d_beta", "iqr_target", "iqr_reference", "d_var", "cp_time_target",
        "cp_time_reference", "cp_strength_target", "cp_strength_reference",
        "cp_age_target_h", "cp_age_reference_h", "d_cp", "cp_one_sided",
        "risk_dist", "risk_trend", "risk_var", "risk_cp", "Q_cp",
        "deadband_active", "n_target", "n_reference",
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
        }]),
    })
    _write_excel(output_dir / "D4_pair_benchmark_library.xlsx", {
        "benchmark_windows": benchmark[[
            "timestamp", "pair_id", "variable", "regime_id", "D1_target", "D1_ref",
            "D2_target_tag", "D2_ref_tag", "D2_target_continuous_24h",
            "D2_ref_continuous_24h", "D5_screen_pass", "benchmark_status",
            "d_w1", "d_ks", "d_beta", "d_var", "benchmark_source", "inclusion_criteria",
        ]],
        "risk_quantiles": params,
    })
    _write_excel(output_dir / "D4_event_windows.xlsx", {"events": events})
    _write_excel(output_dir / "D4_pair_profile_summary.xlsx", {"pair_profile": profile})
    _write_excel(output_dir / "D4_multiscale_aggregates.xlsx", multiscale)
    boundary = pd.DataFrame([
        {"layer": "D2 continuity", "effect": "gate D4 evaluability", "output": "usable_for_D4"},
        {"layer": "D1 bilateral fuse", "effect": "true v1.2 fuse", "output": "D4_after_D1"},
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
        dependencies.append({
            "dependency": name, "path_role": path.name, "sha256": _sha256(path),
            "modified_utc": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
        })
    for name, path in (
        ("d4_config", config_path),
        ("d4_pipeline_code", Path(__file__)),
        ("d4_scoring_code", Path(__file__).with_name("scoring.py")),
    ):
        dependencies.append({
            "dependency": name, "path_role": path.name, "sha256": _sha256(path),
            "modified_utc": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
        })
    audit = pd.DataFrame([
        {"key": "run_id", "value": run_id}, {"key": "config_version", "value": cfg.version},
        {"key": "calibration_id", "value": calibration_id},
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
        "dependencies": dependencies,
        "scientific_boundary": (
            "D4_raw is the independent numeric dimension. D2 gates observability; "
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
