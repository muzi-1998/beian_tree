from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.metrics import average_precision_score, roc_auc_score

from .common import CONFIG_ROOT, PROJECT_ROOT, read_yaml


D4_ROOT = PROJECT_ROOT / "D4 Parallel-redundancy Temporal Consistency"


def _load_d4_api():
    source_root = D4_ROOT / "src"
    if str(source_root) not in sys.path:
        sys.path.insert(0, str(source_root))
    from d4.config import load_config  # type: ignore
    from d4.scoring import (  # type: ignore
        adjacent_ks_change_timeline,
        compare_change_points,
    )
    from d4.validation import _score_window  # type: ignore

    return load_config, adjacent_ks_change_timeline, compare_change_points, _score_window


def _apply_scenario(
    target: np.ndarray,
    reference: np.ndarray,
    scenario: str,
    scale: float,
    interval_min: int,
) -> tuple[np.ndarray, np.ndarray, str]:
    target_out = target.copy()
    reference_out = reference.copy()
    n = len(target_out)
    midpoint = n // 2
    ramp = np.linspace(0.0, 2.5 * scale, n)
    side = "none"
    if scenario == "target_drift":
        target_out += ramp
        side = "target"
    elif scenario == "peer_drift":
        reference_out += ramp
        side = "peer"
    elif scenario == "target_step":
        target_out[midpoint:] += 2.0 * scale
        side = "target"
    elif scenario == "peer_step":
        reference_out[midpoint:] += 2.0 * scale
        side = "peer"
    elif scenario == "target_freeze":
        target_out[midpoint:] = np.nanmedian(target_out[:midpoint])
        side = "target"
    elif scenario == "peer_freeze":
        reference_out[midpoint:] = np.nanmedian(reference_out[:midpoint])
        side = "peer"
    elif scenario == "common_equal":
        target_out += ramp
        reference_out += ramp
    elif scenario == "common_unequal":
        target_out += ramp
        reference_out += 0.60 * ramp
    elif scenario == "opposite_direction":
        target_out += 0.80 * ramp
        reference_out -= 0.80 * ramp
    elif scenario.startswith("lag_"):
        lag_minutes = int(scenario.split("_", 1)[1])
        lag_points = int(np.ceil(lag_minutes / interval_min))
        target_out[midpoint:] += 2.0 * scale
        peer_start = min(n, midpoint + lag_points)
        reference_out[peer_start:] += 2.0 * scale
    elif scenario != "baseline":
        raise ValueError(f"Unknown D4 scenario: {scenario}")
    return target_out, reference_out, side


def _direction_statistic(target: np.ndarray, reference: np.ndarray) -> float:
    midpoint = len(target) // 2
    target_delta = np.nanmedian(target[midpoint:]) - np.nanmedian(target[:midpoint])
    reference_delta = np.nanmedian(reference[midpoint:]) - np.nanmedian(reference[:midpoint])
    return float(target_delta - reference_delta)


def _bootstrap_interval(
    frame: pd.DataFrame,
    statistic,
    *,
    reps: int = 2000,
    seed: int = 20260727,
) -> tuple[float, float]:
    if frame.empty:
        return np.nan, np.nan
    rng = np.random.default_rng(seed)
    estimates = np.empty(reps, dtype=float)
    for index in range(reps):
        sample = frame.iloc[rng.integers(0, len(frame), size=len(frame))]
        estimates[index] = statistic(sample)
    finite = estimates[np.isfinite(estimates)]
    if not len(finite):
        return np.nan, np.nan
    return tuple(np.quantile(finite, [0.025, 0.975]))


def _mechanism_trials() -> tuple[pd.DataFrame, object]:
    load_config, cp_timeline, compare_cp, score_window = _load_d4_api()
    cfg = load_config(D4_ROOT / "configs" / "d4.yaml", PROJECT_ROOT)
    data_dir = D4_ROOT / "outputs" / "data"
    main = pd.read_excel(data_dir / "D4_main_scores.xlsx", sheet_name="main_scores")
    main["timestamp"] = pd.to_datetime(main["timestamp"])
    params = pd.read_excel(data_dir / "D4_mapping_params.xlsx", sheet_name="public_quantiles")
    residuals = pd.read_parquet(cfg.paths["residuals"]).resample(
        f"{cfg.analysis_interval_minutes}min"
    ).median()
    design = read_yaml(CONFIG_ROOT / "validation_design.yaml")["D4"]
    scenarios = [
        "baseline",
        "target_drift",
        "peer_drift",
        "target_step",
        "peer_step",
        "target_freeze",
        "peer_freeze",
        "common_equal",
        "common_unequal",
        "opposite_direction",
        *[f"lag_{minutes}" for minutes in design["lag_minutes"]],
    ]
    rows = []
    interval = cfg.analysis_interval_minutes
    window_points = cfg.window_hours * 60 // interval
    auxiliary_points = int(cfg.change_point["auxiliary_window_days"]) * 24 * 60 // interval
    for pair in cfg.pairs:
        candidates = main[
            main["pair_id"].eq(pair.pair_id)
            & main["usable_for_D4"].fillna(False)
            & main["timestamp"].ge(main["timestamp"].quantile(0.70))
        ]["timestamp"].drop_duplicates()
        positions = np.linspace(
            0,
            max(0, len(candidates) - 1),
            min(int(design["windows_per_pair"]), len(candidates)),
            dtype=int,
        )
        candidates = candidates.iloc[positions]
        for window_number, timestamp in enumerate(candidates, 1):
            end_position = residuals.index.searchsorted(
                pd.Timestamp(timestamp) + pd.Timedelta(hours=1)
            )
            start_position = end_position - window_points
            auxiliary_start = end_position - auxiliary_points
            if start_position < 0 or auxiliary_start < 0:
                continue
            target = residuals[pair.target].iloc[start_position:end_position].to_numpy(float)
            reference = residuals[pair.reference].iloc[start_position:end_position].to_numpy(float)
            if min(np.isfinite(target).mean(), np.isfinite(reference).mean()) < cfg.min_valid_fraction:
                continue
            target_aux = residuals[pair.target].iloc[auxiliary_start:end_position].to_numpy(float)
            reference_aux = residuals[pair.reference].iloc[auxiliary_start:end_position].to_numpy(float)
            auxiliary_index = residuals.index[auxiliary_start:end_position]
            scale = max(
                float(np.nanquantile(target, 0.75) - np.nanquantile(target, 0.25)),
                float(np.nanquantile(reference, 0.75) - np.nanquantile(reference, 0.25)),
                cfg.deadband[pair.variable],
            )
            regime = main.loc[
                main["pair_id"].eq(pair.pair_id) & main["timestamp"].eq(timestamp),
                "regime_id",
            ].iloc[0]
            for scenario in scenarios:
                target_injected, reference_injected, true_side = _apply_scenario(
                    target,
                    reference,
                    scenario,
                    scale,
                    interval,
                )
                target_aux_injected = target_aux.copy()
                reference_aux_injected = reference_aux.copy()
                target_aux_injected[-window_points:] = target_injected
                reference_aux_injected[-window_points:] = reference_injected
                output_index = pd.DatetimeIndex([pd.Timestamp(timestamp)])
                cp_kwargs = {
                    "auxiliary_window_days": int(cfg.change_point["auxiliary_window_days"]),
                    "adjacent_segment_hours": int(cfg.change_point["adjacent_segment_hours"]),
                    "candidate_step_hours": int(cfg.change_point["candidate_step_hours"]),
                    "ks_stat_min": float(cfg.change_point["ks_stat_min"]),
                    "pvalue_max": float(cfg.change_point["pvalue_max"]),
                    "min_valid_fraction": cfg.min_valid_fraction,
                }
                target_cp = cp_timeline(
                    pd.Series(target_aux_injected, index=auxiliary_index)
                    .resample("1h")
                    .median(),
                    output_index,
                    **cp_kwargs,
                )
                reference_cp = cp_timeline(
                    pd.Series(reference_aux_injected, index=auxiliary_index)
                    .resample("1h")
                    .median(),
                    output_index,
                    **cp_kwargs,
                )
                q_cp = float(compare_cp(target_cp, reference_cp)["Q_cp"].iloc[0])
                score = score_window(
                    target_injected,
                    reference_injected,
                    pair,
                    cfg,
                    params,
                    regime,
                    q_cp,
                )
                direction = _direction_statistic(target_injected, reference_injected)
                predicted_side = "target" if direction > 0 else "peer"
                rows.append(
                    {
                        "window_id": f"{pair.pair_id}-{window_number:02d}",
                        "pair_id": pair.pair_id,
                        "variable": pair.variable,
                        "regime_id": regime,
                        "timestamp": timestamp,
                        "scenario": scenario,
                        "true_side": true_side,
                        "predicted_side": predicted_side,
                        "direction_correct": (
                            predicted_side == true_side if true_side != "none" else np.nan
                        ),
                        "direction_statistic": direction,
                        "D4_raw": score["D4_raw"],
                        "anomaly_score": 5.0 - score["D4_raw"],
                        "Q_cp": score["Q_cp"],
                    }
                )
    return pd.DataFrame(rows), cfg


def _mechanism_summary(trials: pd.DataFrame, threshold: float) -> pd.DataFrame:
    rows = []
    baseline = trials[trials["scenario"].eq("baseline")]
    for scenario in [
        "target_drift",
        "peer_drift",
        "target_step",
        "peer_step",
        "target_freeze",
        "peer_freeze",
    ]:
        positive = trials[trials["scenario"].eq(scenario)]
        merged = baseline[["window_id", "anomaly_score"]].merge(
            positive[["window_id", "anomaly_score", "direction_correct"]],
            on="window_id",
            suffixes=("_baseline", "_positive"),
        )
        labels = np.r_[np.zeros(len(merged)), np.ones(len(merged))]
        scores = np.r_[merged["anomaly_score_baseline"], merged["anomaly_score_positive"]]
        auc_stat = lambda sample: roc_auc_score(  # noqa: E731
            np.r_[np.zeros(len(sample)), np.ones(len(sample))],
            np.r_[sample["anomaly_score_baseline"], sample["anomaly_score_positive"]],
        )
        ap_stat = lambda sample: average_precision_score(  # noqa: E731
            np.r_[np.zeros(len(sample)), np.ones(len(sample))],
            np.r_[sample["anomaly_score_baseline"], sample["anomaly_score_positive"]],
        )
        auc_ci = _bootstrap_interval(merged, auc_stat)
        ap_ci = _bootstrap_interval(merged, ap_stat)
        rows.append(
            {
                "scenario": scenario,
                "metric": "AUROC",
                "estimate": float(roc_auc_score(labels, scores)),
                "ci95_low": auc_ci[0],
                "ci95_high": auc_ci[1],
                "n_independent_windows": len(merged),
                "analysis_unit": "pair_window",
            }
        )
        rows.append(
            {
                "scenario": scenario,
                "metric": "AUPRC",
                "estimate": float(average_precision_score(labels, scores)),
                "ci95_low": ap_ci[0],
                "ci95_high": ap_ci[1],
                "n_independent_windows": len(merged),
                "analysis_unit": "pair_window",
            }
        )
        if scenario.endswith(("drift", "step")):
            direction_ci = _bootstrap_interval(
                merged,
                lambda sample: float(sample["direction_correct"].mean()),
            )
            rows.append(
                {
                    "scenario": scenario,
                    "metric": "direction_accuracy",
                    "estimate": float(merged["direction_correct"].mean()),
                    "ci95_low": direction_ci[0],
                    "ci95_high": direction_ci[1],
                    "n_independent_windows": len(merged),
                    "analysis_unit": "pair_window",
                }
            )
    for scenario in ["common_equal", "common_unequal", "opposite_direction"]:
        scenario_frame = trials[trials["scenario"].eq(scenario)][["window_id", "D4_raw"]]
        merged = baseline[["window_id", "D4_raw"]].merge(
            scenario_frame,
            on="window_id",
            suffixes=("_baseline", "_scenario"),
        )
        eligible = merged["D4_raw_baseline"].ge(threshold)
        far = (
            merged.loc[eligible, "D4_raw_scenario"].lt(threshold).mean()
            if eligible.any()
            else np.nan
        )
        eligible_frame = merged.loc[eligible].copy()
        far_ci = _bootstrap_interval(
            eligible_frame,
            lambda sample: float(sample["D4_raw_scenario"].lt(threshold).mean()),
        )
        rows.append(
            {
                "scenario": scenario,
                "metric": (
                    "conditional_new_FAR"
                    if scenario == "common_equal"
                    else "asymmetry_detection_rate"
                ),
                "estimate": float(far),
                "ci95_low": far_ci[0],
                "ci95_high": far_ci[1],
                "n_independent_windows": int(eligible.sum()),
                "analysis_unit": "pair_window",
            }
        )
    lag = (
        trials[trials["scenario"].str.startswith("lag_")]
        .assign(lag_minutes=lambda frame: frame["scenario"].str.split("_").str[1].astype(int))
        .groupby("lag_minutes", as_index=False)
        .agg(mean_D4=("D4_raw", "mean"), mean_Qcp=("Q_cp", "mean"), n=("window_id", "size"))
    )
    rho = spearmanr(lag["lag_minutes"], 5.0 - lag["mean_D4"]).statistic
    rows.append(
        {
            "scenario": "change_point_lag",
            "metric": "severity_monotonic_spearman",
            "estimate": float(rho),
            "ci95_low": np.nan,
            "ci95_high": np.nan,
            "n_independent_windows": int(lag["n"].sum()),
            "analysis_unit": "lag_level_mean",
        }
    )
    return pd.DataFrame(rows)


def _orp_shrinkage_sensitivity() -> pd.DataFrame:
    benchmark = pd.read_excel(
        D4_ROOT / "outputs" / "data" / "D4_pair_benchmark_library.xlsx",
        sheet_name="benchmark_windows",
    )
    benchmark["timestamp"] = pd.to_datetime(benchmark["timestamp"])
    benchmark = benchmark[benchmark["variable"].eq("ORP")].copy()
    metric_map = {"Q_dist": "d_w1", "Q_trend": "d_beta", "Q_var": "d_var"}
    quantiles = [0.50, 0.75, 0.90, 0.975]
    rows = []
    for regime_id, local in benchmark.groupby("regime_id"):
        local = local.copy()
        local["week_block"] = (
            (local["timestamp"] - local["timestamp"].min()) / pd.Timedelta(days=7)
        ).astype(int)
        n_blocks = int(local["week_block"].nunique())
        for subscore, metric in metric_map.items():
            local_q = local[metric].quantile(quantiles).to_numpy(float)
            public_q = benchmark[metric].quantile(quantiles).to_numpy(float)
            for prior_blocks in (4, 8, 12):
                shrinkage_weight = n_blocks / (n_blocks + prior_blocks)
                shrunk = shrinkage_weight * local_q + (1.0 - shrinkage_weight) * public_q
                rows.append(
                    {
                        "variable": "ORP",
                        "regime_id": regime_id,
                        "subscore": subscore,
                        "n_windows": len(local),
                        "n_effective_7d_blocks": n_blocks,
                        "prior_strength_blocks": prior_blocks,
                        "lambda": shrinkage_weight,
                        "q50": shrunk[0],
                        "q75": shrunk[1],
                        "q90": shrunk[2],
                        "q97_5": shrunk[3],
                        "status": "sensitivity_only_pending_estimator_lock",
                    }
                )
    return pd.DataFrame(rows)


def run_d4_validation(output_dir: Path) -> dict[str, pd.DataFrame]:
    trials, cfg = _mechanism_trials()
    summary = _mechanism_summary(trials, float(cfg.classification["asymmetry_max"]))
    lag = (
        trials[trials["scenario"].str.startswith("lag_")]
        .assign(lag_minutes=lambda frame: frame["scenario"].str.split("_").str[1].astype(int))
        .groupby(["lag_minutes", "variable"], as_index=False)
        .agg(
            mean_D4=("D4_raw", "mean"),
            median_D4=("D4_raw", "median"),
            mean_Qcp=("Q_cp", "mean"),
            n_independent_windows=("window_id", "size"),
        )
    )
    shrinkage = _orp_shrinkage_sensitivity()
    outputs = {
        "D4_mechanism_trials": trials,
        "D4_mechanism_summary": summary,
        "D4_lag_response": lag,
        "D4_ORP_shrinkage_sensitivity": shrinkage,
    }
    for name, frame in outputs.items():
        frame.to_parquet(output_dir / f"{name}.parquet", index=False)
    return outputs
