from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from .config import D6Config, PairConfig, load_config
from .scoring import aggregate_scores, compute_window_metrics, score_from_quantiles


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_context(cfg: D6Config) -> tuple[pd.DataFrame, pd.DataFrame, str, str]:
    d1 = pd.read_excel(cfg.paths["d1_scores"], sheet_name="D1_total_hourly")
    d1["timestamp"] = pd.to_datetime(d1["timestamp"])
    d1 = d1.set_index("timestamp").sort_index()

    d2 = pd.read_excel(cfg.paths["d2_scores"], sheet_name="D2_scores")
    d2 = d2.rename(columns={d2.columns[0]: "timestamp"})
    d2["timestamp"] = pd.to_datetime(d2["timestamp"])
    d2["veto_flag"] = pd.to_numeric(d2["veto_flag"], errors="coerce").fillna(1).astype(int)
    d2_run = str(d2["run_id"].dropna().iloc[0])
    d2_calibration = str(d2["calibration_id"].dropna().iloc[0])
    return d1, d2, d2_run, d2_calibration


def _pair_metrics(
    residuals: pd.DataFrame,
    pair: PairConfig,
    cfg: D6Config,
) -> pd.DataFrame:
    interval = cfg.analysis_interval_minutes
    window_points = cfg.window_hours * 60 // interval
    step_points = cfg.step_hours * 60 // interval
    points_per_hour = 60 // interval
    target = residuals[pair.target].to_numpy(dtype=float)
    reference = residuals[pair.reference].to_numpy(dtype=float)
    rows: list[dict[str, object]] = []
    for end_pos in range(window_points, len(residuals) + 1, step_points):
        start_pos = end_pos - window_points
        metrics = compute_window_metrics(
            target[start_pos:end_pos],
            reference[start_pos:end_pos],
            deadband=cfg.deadband[pair.variable],
            points_per_hour=points_per_hour,
        )
        row = asdict(metrics)
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


def _add_context(raw: pd.DataFrame, d1: pd.DataFrame, d2: pd.DataFrame) -> pd.DataFrame:
    parts: list[pd.DataFrame] = []
    d2_lookup = d2.set_index(["timestamp", "sensor_id"])
    for pair_id, frame in raw.groupby("pair_id", sort=False):
        frame = frame.copy()
        target = str(frame["sensor_id"].iloc[0])
        reference = str(frame["pair_sensor_id"].iloc[0])
        ts = pd.DatetimeIndex(frame["timestamp"])
        frame["D1_target"] = d1[target].reindex(ts).to_numpy()
        frame["D1_ref"] = d1[reference].reindex(ts).to_numpy()
        for role, sensor in (("target", target), ("ref", reference)):
            idx = pd.MultiIndex.from_arrays([ts, np.repeat(sensor, len(ts))])
            context = d2_lookup.reindex(idx)
            frame[f"D2_{role}_tag"] = context["usable_tag"].to_numpy()
            frame[f"D2_{role}_veto"] = context["veto_flag"].to_numpy()
            frame[f"D2_{role}"] = context["D2_total"].to_numpy()
        parts.append(frame)
    return pd.concat(parts, ignore_index=True)


def _fit_and_score(raw: pd.DataFrame, cfg: D6Config) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    frames: list[pd.DataFrame] = []
    param_rows: list[dict[str, object]] = []
    benchmark_rows: list[pd.DataFrame] = []
    quantile_levels = np.asarray(cfg.benchmark["quantiles"], dtype=float)
    minimum = int(cfg.benchmark["min_windows_per_pair"])
    risk_to_q = {
        "risk_dist": "Q_dist", "risk_trend": "Q_trend",
        "risk_var": "Q_var", "risk_cp": "Q_cp",
    }
    for pair_id, frame in raw.groupby("pair_id", sort=False):
        frame = frame.copy()
        calibration_end = frame["timestamp"].quantile(0.70)
        calibration_period = frame["timestamp"] < calibration_end
        data_ok = (
            (frame["valid_fraction_target"] >= cfg.min_valid_fraction)
            & (frame["valid_fraction_reference"] >= cfg.min_valid_fraction)
        )
        d2_ok = frame["D2_target_veto"].eq(0) & frame["D2_ref_veto"].eq(0)
        benchmark_mask = data_ok & d2_ok & calibration_period
        if int(benchmark_mask.sum()) < minimum:
            raise ValueError(f"{pair_id} has fewer than {minimum} calibration windows")
        source = "first70pct_D2_nonveto"
        benchmark = frame.loc[benchmark_mask].copy()
        benchmark["benchmark_source"] = source
        benchmark_rows.append(benchmark)
        for risk_column, q_column in risk_to_q.items():
            values = benchmark[risk_column].dropna().to_numpy(dtype=float)
            thresholds = np.quantile(values, quantile_levels)
            frame[q_column] = score_from_quantiles(frame[risk_column].to_numpy(), thresholds)
            if q_column == "Q_var":
                frame.loc[frame["deadband_active"], q_column] = 5.0
            param_rows.append({
                "pair_id": pair_id,
                "subscore": q_column,
                "risk_metric": risk_column,
                "q50": thresholds[0], "q75": thresholds[1],
                "q90": thresholds[2], "q97_5": thresholds[3],
                "sample_size": len(values),
                "benchmark_source": source,
                "calibration_end_exclusive": calibration_end,
                "mapping_type": "pair_specific_quantile",
            })
        frame["D6_base"], frame["D6_raw"] = aggregate_scores(
            frame["Q_dist"].to_numpy(), frame["Q_trend"].to_numpy(),
            frame["Q_var"].to_numpy(), frame["Q_cp"].to_numpy(),
            weights=cfg.weights, lambda_blend=cfg.lambda_blend,
        )
        frame["usable_for_DQR"] = data_ok & d2_ok & frame["D6_raw"].notna()
        frame["D6_total"] = frame["D6_raw"].where(frame["usable_for_DQR"])
        frame["D6_forDQR"] = frame["D6_total"]
        evidence = frame[["Q_dist", "Q_trend", "Q_var", "Q_cp"]]
        frame["dominant_evidence"] = evidence.idxmin(axis=1).str.replace("Q_", "", regex=False)
        ordered = np.argsort(evidence.to_numpy(dtype=float), axis=1)
        labels = np.array(["dist", "trend", "var", "cp"], dtype=object)
        frame["second_evidence"] = labels[ordered[:, 1]]
        gap = np.take_along_axis(evidence.to_numpy(dtype=float), ordered[:, :2], axis=1)
        frame.loc[(gap[:, 1] - gap[:, 0]) < 0.5, "second_evidence"] = "mixed"
        consistent_min = float(cfg.classification["consistent_min"])
        asymmetry_max = float(cfg.classification["asymmetry_max"])
        frame["status_label"] = np.select(
            [~frame["usable_for_DQR"], frame["D6_raw"] < asymmetry_max,
             frame["D6_raw"] >= consistent_min],
            ["not_evaluable", "pair_asymmetry", "paired_consistent"],
            default="borderline",
        )
        frame["causal_attribution"] = np.where(
            frame["status_label"].eq("pair_asymmetry"),
            "unresolved_sensor_or_process_cause", "not_applicable",
        )
        frames.append(frame)
    return (
        pd.concat(frames, ignore_index=True),
        pd.DataFrame(param_rows),
        pd.concat(benchmark_rows, ignore_index=True),
    )


def _events(main: pd.DataFrame, min_hours: int) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    event_no = 1
    for pair_id, frame in main.sort_values("timestamp").groupby("pair_id"):
        active = frame["status_label"].eq("pair_asymmetry")
        groups = active.ne(active.shift(fill_value=False)).cumsum()
        for _, event in frame[active].groupby(groups[active]):
            duration = (event["timestamp"].max() - event["timestamp"].min()).total_seconds() / 3600 + 1
            if duration < min_hours:
                continue
            rows.append({
                "event_id": f"D6-EVT-{event_no:04d}", "pair_id": pair_id,
                "start_ts": event["timestamp"].min(), "end_ts": event["timestamp"].max(),
                "duration_h": duration, "min_D6_raw": event["D6_raw"].min(),
                "mean_D6_raw": event["D6_raw"].mean(),
                "dominant_evidence": event["dominant_evidence"].mode().iloc[0],
                "D1_target_mean": event["D1_target"].mean(), "D1_ref_mean": event["D1_ref"].mean(),
                "D2_target_tag": event["D2_target_tag"].mode().iloc[0],
                "D2_ref_tag": event["D2_ref_tag"].mode().iloc[0],
                "causal_attribution": "unresolved_sensor_or_process_cause",
            })
            event_no += 1
    return pd.DataFrame(rows)


def _profile(main: pd.DataFrame, events: pd.DataFrame) -> pd.DataFrame:
    profile = main.groupby(["pair_id", "zone", "sensor_id", "pair_sensor_id"], as_index=False).agg(
        mean_D6=("D6_total", "mean"), median_D6=("D6_total", "median"),
        p05_D6=("D6_total", lambda x: x.quantile(0.05)),
        low_score_rate=("status_label", lambda x: x.eq("pair_asymmetry").mean()),
        evaluable_rate=("usable_for_DQR", "mean"), deadband_rate=("deadband_active", "mean"),
        mean_Q_dist=("Q_dist", "mean"), mean_Q_trend=("Q_trend", "mean"),
        mean_Q_var=("Q_var", "mean"), mean_Q_cp=("Q_cp", "mean"),
    )
    counts = events.groupby("pair_id").size().rename("n_events") if not events.empty else pd.Series(dtype=int)
    profile["n_events"] = profile["pair_id"].map(counts).fillna(0).astype(int)
    return profile


def _multiscale(main: pd.DataFrame) -> dict[str, pd.DataFrame]:
    source = main.set_index("timestamp")
    outputs: dict[str, pd.DataFrame] = {}
    for label, freq in (("daily", "1D"), ("weekly", "W-MON")):
        rows = []
        for pair_id, frame in source.groupby("pair_id"):
            agg = frame["D6_total"].resample(freq).agg(
                D6_gate=lambda x: x.quantile(0.05),
                D6_report=lambda x: x.quantile(0.25),
                D6_mean="mean", D6_median="median", n_windows="count",
            )
            agg["pair_id"] = pair_id
            rows.append(agg.reset_index())
        outputs[label] = pd.concat(rows, ignore_index=True)
    return outputs


def _write_excel(path: Path, sheets: dict[str, pd.DataFrame]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for sheet_name, frame in sheets.items():
            frame.to_excel(writer, sheet_name=sheet_name[:31], index=False)


def run_pipeline(project_root: Path, d6_root: Path) -> dict[str, object]:
    config_path = d6_root / "configs" / "d6.yaml"
    cfg = load_config(config_path, project_root)
    output_dir = d6_root / "outputs" / "data"
    output_dir.mkdir(parents=True, exist_ok=True)
    run_id = datetime.now(timezone.utc).strftime("D6V13_%Y%m%d_%H%M%S")

    residuals = pd.read_parquet(cfg.paths["residuals"])
    columns = sorted({p.target for p in cfg.pairs} | {p.reference for p in cfg.pairs})
    residuals = residuals[columns].resample(f"{cfg.analysis_interval_minutes}min").median()
    d1, d2, d2_run, d2_calibration = _load_context(cfg)
    raw = pd.concat([_pair_metrics(residuals, pair, cfg) for pair in cfg.pairs], ignore_index=True)
    raw = _add_context(raw, d1, d2)
    main, params, benchmark = _fit_and_score(raw, cfg)
    main["run_id"] = run_id
    main["config_version"] = cfg.version
    main["d2_run_id"] = d2_run
    events = _events(main, int(cfg.classification["event_min_hours"]))
    profile = _profile(main, events)
    multiscale = _multiscale(main)

    score_columns = [
        "timestamp", "pair_id", "sensor_id", "pair_sensor_id", "zone", "variable",
        "Q_dist", "Q_trend", "Q_var", "Q_cp", "D6_base", "D6_raw", "D6_total",
        "D6_forDQR", "status_label", "causal_attribution", "dominant_evidence",
        "second_evidence", "deadband_active", "deadband_used", "D1_target", "D1_ref",
        "D2_target", "D2_ref", "D2_target_tag", "D2_ref_tag", "D2_target_veto",
        "D2_ref_veto", "valid_fraction_target", "valid_fraction_reference",
        "usable_for_DQR", "run_id", "config_version", "d2_run_id",
    ]
    raw_columns = [
        "timestamp", "pair_id", "d_w1", "d_ks", "beta_target", "beta_reference",
        "d_beta", "iqr_target", "iqr_reference", "d_var", "cp_shift_target",
        "cp_shift_reference", "d_cp", "risk_dist", "risk_trend", "risk_var",
        "risk_cp", "deadband_active", "n_target", "n_reference",
    ]
    _write_excel(output_dir / "D6_main_scores.xlsx", {
        "main_scores": main[score_columns], "pair_profile": profile,
    })
    _write_excel(output_dir / "D6_detector_outputs_raw.xlsx", {"detector_outputs": main[raw_columns]})
    _write_excel(output_dir / "D6_mapping_params.xlsx", {
        "pair_quantiles": params,
        "aggregation": pd.DataFrame([{"component": k, "weight": v} for k, v in cfg.weights.items()] +
                                    [{"component": "lambda_blend", "weight": cfg.lambda_blend}]),
        "deadband": pd.DataFrame([{"variable": k, "delta_phys": v} for k, v in cfg.deadband.items()]),
        "version": pd.DataFrame([{"config_version": cfg.version, "run_id": run_id}]),
    })
    _write_excel(output_dir / "D6_pair_benchmark_library.xlsx", {
        "benchmark_windows": benchmark[["timestamp", "pair_id", "D1_target", "D1_ref",
                                          "D2_target_tag", "D2_ref_tag", "benchmark_source"]],
        "risk_quantiles": params,
    })
    _write_excel(output_dir / "D6_event_windows.xlsx", {"events": events})
    _write_excel(output_dir / "D6_pair_profile_summary.xlsx", {"pair_profile": profile})
    _write_excel(output_dir / "D6_multiscale_aggregates.xlsx", multiscale)
    boundary = pd.DataFrame([
        {"rule": "D2 continuity", "effect": "evaluation gate only", "score_changed": False},
        {"rule": "D1 sensor health", "effect": "interpretation context only", "score_changed": False},
        {"rule": "D7 spatial consensus", "effect": "not available; reserved for DQR evidence fusion", "score_changed": False},
    ])
    _write_excel(output_dir / "D6_arbitration_log.xlsx", {"boundary_contract": boundary})

    dependencies = []
    for name, path in cfg.paths.items():
        dependencies.append({
            "dependency": name, "path_role": path.name, "sha256": _sha256(path),
            "modified_utc": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
        })
    audit = pd.DataFrame([
        {"key": "run_id", "value": run_id}, {"key": "config_version", "value": cfg.version},
        {"key": "generated_utc", "value": datetime.now(timezone.utc).isoformat()},
        {"key": "d2_run_id", "value": d2_run}, {"key": "d2_calibration_id", "value": d2_calibration},
        {"key": "n_rows", "value": len(main)}, {"key": "n_pairs", "value": len(cfg.pairs)},
        {"key": "data_start", "value": residuals.index.min()},
        {"key": "data_end", "value": residuals.index.max()},
        {"key": "evaluable_rate", "value": float(main["usable_for_DQR"].mean())},
        {"key": "causal_claim", "value": "pair asymmetry only; sensor/process cause unresolved"},
    ])
    _write_excel(output_dir / "D6_audit_log.xlsx", {
        "run_manifest": audit, "dependencies": pd.DataFrame(dependencies),
        "boundary_contract": boundary,
    })
    manifest = {
        "run_id": run_id, "config_version": cfg.version,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "data_span": [str(residuals.index.min()), str(residuals.index.max())],
        "rows": len(main), "pairs": len(cfg.pairs), "d2_run_id": d2_run,
        "dependencies": dependencies,
        "scientific_boundary": "D6 score is independent; D2 gates evaluability; D1/D7 do not modify the score.",
    }
    (output_dir / "D6_run_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    return {"config": cfg, "main": main, "raw": raw, "params": params,
            "benchmark": benchmark, "events": events, "profile": profile,
            "manifest": manifest}
