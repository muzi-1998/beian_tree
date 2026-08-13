from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    precision_recall_curve,
    roc_auc_score,
    roc_curve,
)

from .config import D4Config, PairConfig
from .scoring import (
    adjacent_ks_change_timeline,
    aggregate_scores,
    compare_change_points,
    compute_window_metrics,
    score_from_quantiles,
)


INJECTIONS = ("unilateral_drift", "unilateral_step", "unilateral_freeze", "unilateral_spike")
DISTRIBUTION_CHALLENGES = (
    "distribution_location",
    "distribution_scale",
    "distribution_tail",
    "distribution_mixture",
)


def _cluster_bootstrap_interval(
    frame: pd.DataFrame,
    value_fn,
    rng: np.random.Generator,
    *,
    repetitions: int = 300,
) -> tuple[float, float]:
    grouped = [group for _, group in frame.groupby("window_id", sort=False)]
    values = []
    for _ in range(repetitions):
        sampled = rng.integers(0, len(grouped), size=len(grouped))
        draw = pd.concat([grouped[index] for index in sampled], ignore_index=True)
        values.append(float(value_fn(draw)))
    return tuple(np.quantile(values, [0.025, 0.975]))


def _inject(
    target: np.ndarray,
    reference: np.ndarray,
    kind: str,
    scale: float,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray]:
    t = target.copy()
    r = reference.copy()
    n = len(t)
    if kind == "unilateral_drift":
        t += np.linspace(0.0, 2.5 * scale, n)
    elif kind == "unilateral_step":
        t[n // 2 :] += 2.0 * scale
    elif kind == "unilateral_freeze":
        t[n // 2 :] = np.nanmedian(t[: n // 2])
    elif kind == "unilateral_spike":
        count = max(4, n // 20)
        index = rng.choice(n, size=count, replace=False)
        t[index] += rng.choice([-1.0, 1.0], size=count) * 5.0 * scale
    elif kind in {"synchronous_switch", "common_mode_drift"}:
        change = np.linspace(0.0, 2.5 * scale, n)
        t += change
        r += change
    elif kind == "common_unequal":
        change = np.linspace(0.0, 2.5 * scale, n)
        t += change
        r += 0.4 * change
    elif kind == "opposite_direction":
        change = np.linspace(0.0, 2.5 * scale, n)
        t += change
        r -= change
    elif kind == "distribution_location":
        t += 1.5 * scale
    elif kind == "distribution_scale":
        center = float(np.nanmedian(t))
        t = center + 1.8 * (t - center)
    elif kind == "distribution_tail":
        finite = np.flatnonzero(np.isfinite(t))
        count = max(4, int(np.ceil(0.10 * len(finite))))
        selected = rng.choice(finite, size=count, replace=False)
        t[selected] += 4.0 * scale
    elif kind == "distribution_mixture":
        finite = np.flatnonzero(np.isfinite(t))
        assignment = rng.choice([-1.0, 1.0], size=len(finite))
        t[finite] += assignment * 1.5 * scale
    else:
        raise ValueError(f"Unknown injection: {kind}")
    return t, r


def _thresholds(
    params: pd.DataFrame,
    variable: str,
    regime_id: float,
    q_name: str,
) -> np.ndarray:
    regime_match = params["regime_id"].eq(regime_id) if pd.notna(regime_id) else params["regime_id"].isna()
    row = params[
        params["variable"].eq(variable) & regime_match & params["subscore"].eq(q_name)
    ].iloc[0]
    return row[["q50", "q75", "q90", "q97_5"]].to_numpy(dtype=float)


def _score_window(
    target: np.ndarray,
    reference: np.ndarray,
    pair: PairConfig,
    cfg: D4Config,
    params: pd.DataFrame,
    regime_id: float,
    q_cp: float,
) -> dict[str, float]:
    metrics = compute_window_metrics(
        target, reference, deadband=cfg.deadband[pair.variable],
        points_per_hour=60 // cfg.analysis_interval_minutes,
        min_common_hour_fraction=float(cfg.common_support["min_hour_fraction"]),
        distribution_weights={
            key: float(value) for key, value in cfg.distribution["weights"].items()
        },
    )
    risks = {
        "Q_dist": metrics.risk_dist, "Q_trend": metrics.risk_trend,
        "Q_var": metrics.risk_var,
    }
    q = {
        name: float(score_from_quantiles(
            np.array([value]), _thresholds(params, pair.variable, regime_id, name)
        )[0])
        for name, value in risks.items()
    }
    q["Q_cp"] = float(q_cp)
    q_dist_w1 = float(score_from_quantiles(
        np.array([metrics.risk_dist_w1]),
        _thresholds(params, pair.variable, regime_id, "Q_dist_w1_candidate"),
    )[0])
    q_dist_ks = float(score_from_quantiles(
        np.array([metrics.risk_dist_ks]),
        _thresholds(params, pair.variable, regime_id, "Q_dist_ks_candidate"),
    )[0])
    q_var_without_deadband = q["Q_var"]
    if metrics.deadband_active:
        q["Q_var"] = 5.0
    base, raw = aggregate_scores(
        np.array([q["Q_dist"]]), np.array([q["Q_trend"]]),
        np.array([q["Q_var"]]), np.array([q["Q_cp"]]),
        weights=cfg.weights, lambda_blend=cfg.lambda_blend,
    )
    _, raw_w1 = aggregate_scores(
        np.array([q_dist_w1]), np.array([q["Q_trend"]]),
        np.array([q["Q_var"]]), np.array([q["Q_cp"]]),
        weights=cfg.weights, lambda_blend=cfg.lambda_blend,
    )
    _, raw_ks = aggregate_scores(
        np.array([q_dist_ks]), np.array([q["Q_trend"]]),
        np.array([q["Q_var"]]), np.array([q["Q_cp"]]),
        weights=cfg.weights, lambda_blend=cfg.lambda_blend,
    )
    return {
        **q, "Q_var_no_deadband": q_var_without_deadband,
        "Q_dist_w1_candidate": q_dist_w1,
        "Q_dist_ks_candidate": q_dist_ks,
        "D4_base": float(base[0]), "D4_raw": float(raw[0]),
        "D4_raw_full": float(raw[0]),
        "D4_raw_w1_only": float(raw_w1[0]),
        "D4_raw_ks_only": float(raw_ks[0]),
        "risk_dist_full": float(metrics.risk_dist),
        "risk_dist_w1": float(metrics.risk_dist_w1),
        "risk_dist_ks": float(metrics.risk_dist_ks),
        "deadband_active": float(metrics.deadband_active),
    }


def _distribution_internal_ablation(
    scores: pd.DataFrame,
    cfg: D4Config,
    rng: np.random.Generator,
    *,
    repetitions: int = 600,
) -> pd.DataFrame:
    score_columns = {
        "Full": "D4_raw_full",
        "W1-only": "D4_raw_w1_only",
        "KS-only": "D4_raw_ks_only",
    }
    baseline = scores[scores["injection"].eq("baseline")].sort_values("window_id")
    rows: list[dict[str, object]] = []
    for challenge in DISTRIBUTION_CHALLENGES:
        positive = scores[scores["injection"].eq(challenge)].sort_values("window_id")
        if not baseline["window_id"].reset_index(drop=True).equals(
            positive["window_id"].reset_index(drop=True)
        ):
            raise ValueError(f"Distribution challenge is not paired: {challenge}")
        n_clusters = len(baseline)
        labels = np.r_[np.zeros(n_clusters, dtype=int), np.ones(n_clusters, dtype=int)]
        point: dict[str, tuple[float, float]] = {}
        for condition, column in score_columns.items():
            risk = 5.0 - np.r_[baseline[column].to_numpy(), positive[column].to_numpy()]
            point[condition] = (
                float(roc_auc_score(labels, risk)),
                float(average_precision_score(labels, risk)),
            )
        for alternative in ("W1-only", "KS-only"):
            auc_draws = np.empty(repetitions)
            ap_draws = np.empty(repetitions)
            for iteration in range(repetitions):
                sampled = rng.integers(0, n_clusters, n_clusters)
                draw = np.r_[sampled, sampled + n_clusters]
                full_risk = 5.0 - np.r_[
                    baseline[score_columns["Full"]].to_numpy(),
                    positive[score_columns["Full"]].to_numpy(),
                ]
                alternative_risk = 5.0 - np.r_[
                    baseline[score_columns[alternative]].to_numpy(),
                    positive[score_columns[alternative]].to_numpy(),
                ]
                auc_draws[iteration] = (
                    roc_auc_score(labels[draw], full_risk[draw])
                    - roc_auc_score(labels[draw], alternative_risk[draw])
                )
                ap_draws[iteration] = (
                    average_precision_score(labels[draw], full_risk[draw])
                    - average_precision_score(labels[draw], alternative_risk[draw])
                )
            for metric, metric_index, draws in (
                ("delta_AUROC_full_minus_alternative", 0, auc_draws),
                ("delta_AUPRC_full_minus_alternative", 1, ap_draws),
            ):
                low, high = np.quantile(draws, [0.025, 0.975])
                rows.append({
                    "challenge": challenge,
                    "alternative": alternative,
                    "metric": metric,
                    "full_value": point["Full"][metric_index],
                    "alternative_value": point[alternative][metric_index],
                    "difference": point["Full"][metric_index] - point[alternative][metric_index],
                    "CI_low": float(low),
                    "CI_high": float(high),
                    "n_window_clusters": n_clusters,
                    "decision_scope": "internal_validation_construct_ablation",
                })

    common = scores[scores["injection"].eq("common_mode_drift")].sort_values("window_id")
    if not baseline["window_id"].reset_index(drop=True).equals(
        common["window_id"].reset_index(drop=True)
    ):
        raise ValueError("Common-mode control is not paired")
    threshold = float(cfg.classification["asymmetry_max"])
    eligible = np.ones(len(baseline), dtype=bool)
    for column in score_columns.values():
        eligible &= baseline[column].to_numpy(dtype=float) >= threshold
    for condition, column in score_columns.items():
        values = common[column].to_numpy(dtype=float)
        point_far = float((values[eligible] < threshold).mean())
        draws = np.empty(repetitions)
        eligible_index = np.flatnonzero(eligible)
        for iteration in range(repetitions):
            sampled = rng.choice(eligible_index, size=len(eligible_index), replace=True)
            draws[iteration] = float((values[sampled] < threshold).mean())
        low, high = np.quantile(draws, [0.025, 0.975])
        rows.append({
            "challenge": "equal_common_mode_control",
            "alternative": condition,
            "metric": "conditional_new_FAR_common_eligible_set",
            "full_value": np.nan,
            "alternative_value": point_far,
            "difference": np.nan,
            "CI_low": float(low),
            "CI_high": float(high),
            "n_window_clusters": int(eligible.sum()),
            "decision_scope": "internal_validation_negative_control",
        })
    return pd.DataFrame(rows)


def _ablation_score(frame: pd.DataFrame, condition: str, cfg: D4Config) -> np.ndarray:
    q_cols = ["Q_dist", "Q_trend", "Q_var", "Q_cp"]
    q = frame[q_cols].copy()
    weights = cfg.weights.copy()
    if condition == "no_deadband":
        q["Q_var"] = frame["Q_var_no_deadband"]
    elif condition.startswith("no_"):
        component = condition.removeprefix("no_")
        q = q.drop(columns=[f"Q_{component}"])
        weights.pop(component)
        total = sum(weights.values())
        weights = {key: value / total for key, value in weights.items()}
    matrix = q.to_numpy(dtype=float)
    ordered_weights = np.array([weights[col.removeprefix("Q_")] for col in q.columns])
    base = matrix @ ordered_weights
    return cfg.lambda_blend * base + (1.0 - cfg.lambda_blend) * matrix.min(axis=1)


def run_validation(
    cfg: D4Config,
    residual_path: Path,
    main: pd.DataFrame,
    params: pd.DataFrame,
    output_path: Path,
    *,
    windows_per_pair: int = 18,
) -> dict[str, pd.DataFrame]:
    residuals = pd.read_parquet(residual_path)
    residuals = residuals.resample(f"{cfg.analysis_interval_minutes}min").median()
    interval = cfg.analysis_interval_minutes
    window_points = cfg.window_hours * 60 // interval
    rng = np.random.default_rng(20260713)
    rows: list[dict[str, object]] = []

    for pair in cfg.pairs:
        candidates = main[
            (main["pair_id"] == pair.pair_id)
            & main["usable_for_D4"]
            & main["phase_id"].eq("internal_validation")
        ]["timestamp"].drop_duplicates()
        if len(candidates) > windows_per_pair:
            positions = np.linspace(0, len(candidates) - 1, windows_per_pair, dtype=int)
            candidates = candidates.iloc[positions]
        for window_no, timestamp in enumerate(candidates, 1):
            end_pos = residuals.index.searchsorted(pd.Timestamp(timestamp) + pd.Timedelta(hours=1))
            start_pos = end_pos - window_points
            auxiliary_points = int(cfg.change_point["auxiliary_window_days"]) * 24 * 60 // interval
            auxiliary_start = end_pos - auxiliary_points
            if start_pos < 0 or auxiliary_start < 0:
                continue
            target = residuals[pair.target].iloc[start_pos:end_pos].to_numpy(dtype=float)
            reference = residuals[pair.reference].iloc[start_pos:end_pos].to_numpy(dtype=float)
            target_aux = residuals[pair.target].iloc[auxiliary_start:end_pos].to_numpy(dtype=float)
            reference_aux = residuals[pair.reference].iloc[auxiliary_start:end_pos].to_numpy(dtype=float)
            auxiliary_index = residuals.index[auxiliary_start:end_pos]
            if min(np.isfinite(target).mean(), np.isfinite(reference).mean()) < cfg.min_valid_fraction:
                continue
            scale = max(
                float(np.nanquantile(target, 0.75) - np.nanquantile(target, 0.25)),
                float(np.nanquantile(reference, 0.75) - np.nanquantile(reference, 0.25)),
                cfg.deadband[pair.variable],
            )
            for injection in (
                "baseline", *INJECTIONS, *DISTRIBUTION_CHALLENGES,
                "synchronous_switch", "common_mode_drift",
                "common_unequal", "opposite_direction",
            ):
                if injection == "baseline":
                    t_inj, r_inj = target.copy(), reference.copy()
                    t_aux_inj, r_aux_inj = target_aux.copy(), reference_aux.copy()
                else:
                    t_inj, r_inj = _inject(target, reference, injection, scale, rng)
                    t_aux_inj, r_aux_inj = target_aux.copy(), reference_aux.copy()
                    t_aux_inj[-window_points:] = t_inj
                    r_aux_inj[-window_points:] = r_inj
                cp_kwargs = {
                    "auxiliary_window_days": int(cfg.change_point["auxiliary_window_days"]),
                    "adjacent_segment_hours": int(cfg.change_point["adjacent_segment_hours"]),
                    "candidate_step_hours": int(cfg.change_point["candidate_step_hours"]),
                    "ks_stat_min": float(cfg.change_point["ks_stat_min"]),
                    "pvalue_max": float(cfg.change_point["pvalue_max"]),
                    "min_valid_fraction": cfg.min_valid_fraction,
                }
                output_index = pd.DatetimeIndex([pd.Timestamp(timestamp)])
                target_cp = adjacent_ks_change_timeline(
                    pd.Series(t_aux_inj, index=auxiliary_index).resample("1h").median(),
                    output_index,
                    **cp_kwargs,
                )
                reference_cp = adjacent_ks_change_timeline(
                    pd.Series(r_aux_inj, index=auxiliary_index).resample("1h").median(),
                    output_index,
                    **cp_kwargs,
                )
                q_cp = float(compare_change_points(target_cp, reference_cp)["Q_cp"].iloc[0])
                regime_id = main.loc[
                    main["pair_id"].eq(pair.pair_id) & main["timestamp"].eq(timestamp),
                    "regime_id",
                ].iloc[0]
                score = _score_window(t_inj, r_inj, pair, cfg, params, regime_id, q_cp)
                rows.append({
                    "pair_id": pair.pair_id, "window_id": f"{pair.pair_id}-{window_no:02d}",
                    "timestamp": timestamp, "injection": injection,
                    "is_unilateral_fault": injection in (*INJECTIONS, *DISTRIBUTION_CHALLENGES),
                    "anomaly_score": 5.0 - score["D4_raw"], **score,
                })
    scores = pd.DataFrame(rows)

    summary_rows: list[dict[str, object]] = []
    curve_rows: list[dict[str, object]] = []
    baseline = scores[scores["injection"] == "baseline"]
    for injection in INJECTIONS:
        positive = scores[scores["injection"] == injection]
        combined = pd.concat([baseline, positive], ignore_index=True)
        y = combined["is_unilateral_fault"].astype(int).to_numpy()
        risk = combined["anomaly_score"].to_numpy(dtype=float)
        roc_auc = float(roc_auc_score(y, risk))
        ci_low, ci_high = _cluster_bootstrap_interval(
            combined,
            lambda draw: roc_auc_score(draw["is_unilateral_fault"].astype(int), draw["anomaly_score"]),
            rng,
        )
        fpr, tpr, roc_threshold = roc_curve(y, risk)
        precision, recall, pr_threshold = precision_recall_curve(y, risk)
        summary_rows.append({
            "validation": injection, "metric": "ROC_AUC", "value": roc_auc,
            "CI_low": ci_low, "CI_high": ci_high,
            "target": 0.70, "pass": roc_auc >= 0.70,
            "required_for_acceptance": injection != "unilateral_spike",
            "interpretation": (
                "secondary sensitivity only; isolated spikes remain a D1 responsibility"
                if injection == "unilateral_spike"
                else "internal chronological-holdout stress test"
            ),
        })
        for i in range(len(fpr)):
            curve_rows.append({"injection": injection, "curve": "ROC", "x": fpr[i], "y": tpr[i],
                               "threshold": roc_threshold[i]})
        for i in range(len(recall)):
            curve_rows.append({"injection": injection, "curve": "PR", "x": recall[i], "y": precision[i],
                               "threshold": pr_threshold[i] if i < len(pr_threshold) else np.nan})
    for injection in ("synchronous_switch", "common_mode_drift"):
        subset = scores[scores["injection"] == injection][["window_id", "D4_raw"]]
        paired = subset.merge(
            baseline[["window_id", "D4_raw"]], on="window_id", suffixes=("_injected", "_baseline")
        )
        paired = paired[paired["D4_raw_baseline"] >= cfg.classification["asymmetry_max"]]
        far = float((paired["D4_raw_injected"] < cfg.classification["asymmetry_max"]).mean())
        ci_low, ci_high = _cluster_bootstrap_interval(
            paired,
            lambda draw: (draw["D4_raw_injected"] < cfg.classification["asymmetry_max"]).mean(),
            rng,
        )
        summary_rows.append({
            "validation": injection, "metric": "new_false_alarm_rate", "value": far,
            "CI_low": ci_low, "CI_high": ci_high,
            "target": 0.10, "pass": far <= 0.10,
            "required_for_acceptance": True,
            "interpretation": "paired conditional FAR among windows that were non-alarming before injection",
        })

    common_change_rows: list[dict[str, object]] = []
    common_change_contract = {
        "common_mode_drift": (
            "common_equal", "negative_control", "conditional_false_alarm_rate"
        ),
        "common_unequal": (
            "common_unequal", "positive_asymmetry_stress_test", "conditional_response_rate"
        ),
        "opposite_direction": (
            "opposite_direction", "positive_asymmetry_stress_test", "conditional_response_rate"
        ),
    }
    threshold = float(cfg.classification["asymmetry_max"])
    baseline_contract = baseline[["window_id", "D4_raw"]].rename(
        columns={"D4_raw": "D4_raw_baseline"}
    )
    for injection, (scenario, role, metric) in common_change_contract.items():
        paired = scores[scores["injection"].eq(injection)][
            ["window_id", "D4_raw"]
        ].merge(baseline_contract, on="window_id", validate="one_to_one")
        paired = paired[paired["D4_raw_baseline"] >= threshold]
        estimate = float((paired["D4_raw"] < threshold).mean())
        ci_low, ci_high = _cluster_bootstrap_interval(
            paired,
            lambda draw: (draw["D4_raw"] < threshold).mean(),
            rng,
            repetitions=600,
        )
        common_change_rows.append({
            "scenario": scenario,
            "injection": injection,
            "role": role,
            "metric": metric,
            "estimate": estimate,
            "ci95_low": ci_low,
            "ci95_high": ci_high,
            "n_window_clusters": len(paired),
            "alarm_threshold": threshold,
            "acceptance_target": 0.10 if role == "negative_control" else np.nan,
            "pass": estimate <= 0.10 if role == "negative_control" else pd.NA,
            "claim_scope": (
                "equal change contributes to conditional FAR; unequal and opposite "
                "changes are positive asymmetry stress tests and never enter FAR"
            ),
        })

    ablation_rows: list[dict[str, object]] = []
    unilateral = scores[scores["injection"].isin(INJECTIONS)]
    validation_set = pd.concat([baseline, unilateral], ignore_index=True)
    labels = validation_set["is_unilateral_fault"].astype(int).to_numpy()
    sync = scores[scores["injection"] == "synchronous_switch"]
    for condition in ("full", "no_dist", "no_trend", "no_var", "no_cp", "no_deadband"):
        score = validation_set["D4_raw"].to_numpy() if condition == "full" else _ablation_score(validation_set, condition, cfg)
        sync_score = sync["D4_raw"].to_numpy() if condition == "full" else _ablation_score(sync, condition, cfg)
        baseline_score = baseline["D4_raw"].to_numpy() if condition == "full" else _ablation_score(baseline, condition, cfg)
        scored_validation = validation_set[["window_id", "is_unilateral_fault"]].copy()
        scored_validation["score"] = score
        auc_low, auc_high = _cluster_bootstrap_interval(
            scored_validation,
            lambda draw: roc_auc_score(draw["is_unilateral_fault"].astype(int), 5.0 - draw["score"]),
            rng,
        )
        scored_sync = sync[["window_id"]].copy()
        scored_sync["score"] = sync_score
        scored_sync["baseline_score"] = baseline_score
        scored_sync = scored_sync[
            scored_sync["baseline_score"] >= cfg.classification["asymmetry_max"]
        ]
        far_low, far_high = _cluster_bootstrap_interval(
            scored_sync,
            lambda draw: (draw["score"] < cfg.classification["asymmetry_max"]).mean(),
            rng,
        )
        ablation_rows.append({
            "condition": condition, "ROC_AUC": float(roc_auc_score(labels, 5.0 - score)),
            "AUC_CI_low": auc_low, "AUC_CI_high": auc_high,
            "synchronous_FAR": float(
                (scored_sync["score"] < cfg.classification["asymmetry_max"]).mean()
            ),
            "FAR_CI_low": far_low, "FAR_CI_high": far_high,
            "n_positive": int(labels.sum()), "n_negative": int((1 - labels).sum()),
        })
    outputs = {
        "summary": pd.DataFrame(summary_rows),
        "injection_scores": scores,
        "roc_pr_curves": pd.DataFrame(curve_rows),
        "ablation": pd.DataFrame(ablation_rows),
        "distribution_internal_ablation": _distribution_internal_ablation(scores, cfg, rng),
        "common_change_contract": pd.DataFrame(common_change_rows),
    }
    calibration_id = str(main["calibration_id"].dropna().iloc[0])
    for frame in outputs.values():
        frame["calibration_id"] = calibration_id
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        for name, frame in outputs.items():
            frame.to_excel(writer, sheet_name=name, index=False)
    return outputs
