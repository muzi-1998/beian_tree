from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import auc, precision_recall_curve, roc_auc_score, roc_curve

from .config import D6Config, PairConfig
from .scoring import aggregate_scores, compute_window_metrics, score_from_quantiles


INJECTIONS = ("unilateral_drift", "unilateral_step", "unilateral_freeze", "unilateral_spike")


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
    else:
        raise ValueError(f"Unknown injection: {kind}")
    return t, r


def _thresholds(params: pd.DataFrame, pair_id: str, q_name: str) -> np.ndarray:
    row = params[(params["pair_id"] == pair_id) & (params["subscore"] == q_name)].iloc[0]
    return row[["q50", "q75", "q90", "q97_5"]].to_numpy(dtype=float)


def _score_window(
    target: np.ndarray,
    reference: np.ndarray,
    pair: PairConfig,
    cfg: D6Config,
    params: pd.DataFrame,
) -> dict[str, float]:
    metrics = compute_window_metrics(
        target, reference, deadband=cfg.deadband[pair.variable],
        points_per_hour=60 // cfg.analysis_interval_minutes,
    )
    risks = {
        "Q_dist": metrics.risk_dist, "Q_trend": metrics.risk_trend,
        "Q_var": metrics.risk_var, "Q_cp": metrics.risk_cp,
    }
    q = {
        name: float(score_from_quantiles(np.array([value]), _thresholds(params, pair.pair_id, name))[0])
        for name, value in risks.items()
    }
    q_var_without_deadband = q["Q_var"]
    if metrics.deadband_active:
        q["Q_var"] = 5.0
    base, raw = aggregate_scores(
        np.array([q["Q_dist"]]), np.array([q["Q_trend"]]),
        np.array([q["Q_var"]]), np.array([q["Q_cp"]]),
        weights=cfg.weights, lambda_blend=cfg.lambda_blend,
    )
    return {
        **q, "Q_var_no_deadband": q_var_without_deadband,
        "D6_base": float(base[0]), "D6_raw": float(raw[0]),
        "deadband_active": float(metrics.deadband_active),
    }


def _ablation_score(frame: pd.DataFrame, condition: str, cfg: D6Config) -> np.ndarray:
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
    cfg: D6Config,
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
            & main["usable_for_DQR"]
            & (main["timestamp"] >= main["timestamp"].quantile(0.70))
        ]["timestamp"].drop_duplicates()
        if len(candidates) > windows_per_pair:
            positions = np.linspace(0, len(candidates) - 1, windows_per_pair, dtype=int)
            candidates = candidates.iloc[positions]
        for window_no, timestamp in enumerate(candidates, 1):
            end_pos = residuals.index.searchsorted(pd.Timestamp(timestamp) + pd.Timedelta(hours=1))
            start_pos = end_pos - window_points
            if start_pos < 0:
                continue
            target = residuals[pair.target].iloc[start_pos:end_pos].to_numpy(dtype=float)
            reference = residuals[pair.reference].iloc[start_pos:end_pos].to_numpy(dtype=float)
            if min(np.isfinite(target).mean(), np.isfinite(reference).mean()) < cfg.min_valid_fraction:
                continue
            scale = max(
                float(np.nanquantile(target, 0.75) - np.nanquantile(target, 0.25)),
                float(np.nanquantile(reference, 0.75) - np.nanquantile(reference, 0.25)),
                cfg.deadband[pair.variable],
            )
            for injection in ("baseline", *INJECTIONS, "synchronous_switch", "common_mode_drift"):
                if injection == "baseline":
                    t_inj, r_inj = target, reference
                else:
                    t_inj, r_inj = _inject(target, reference, injection, scale, rng)
                score = _score_window(t_inj, r_inj, pair, cfg, params)
                rows.append({
                    "pair_id": pair.pair_id, "window_id": f"{pair.pair_id}-{window_no:02d}",
                    "timestamp": timestamp, "injection": injection,
                    "is_unilateral_fault": injection in INJECTIONS,
                    "anomaly_score": 5.0 - score["D6_raw"], **score,
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
        subset = scores[scores["injection"] == injection]
        far = float((subset["D6_raw"] < cfg.classification["asymmetry_max"]).mean())
        ci_low, ci_high = _cluster_bootstrap_interval(
            subset,
            lambda draw: (draw["D6_raw"] < cfg.classification["asymmetry_max"]).mean(),
            rng,
        )
        summary_rows.append({
            "validation": injection, "metric": "false_alarm_rate", "value": far,
            "CI_low": ci_low, "CI_high": ci_high,
            "target": 0.10, "pass": far <= 0.10,
            "required_for_acceptance": True,
            "interpretation": "symmetric pair change should not be attributed as pair asymmetry",
        })

    ablation_rows: list[dict[str, object]] = []
    unilateral = scores[scores["injection"].isin(INJECTIONS)]
    validation_set = pd.concat([baseline, unilateral], ignore_index=True)
    labels = validation_set["is_unilateral_fault"].astype(int).to_numpy()
    sync = scores[scores["injection"] == "synchronous_switch"]
    for condition in ("full", "no_dist", "no_trend", "no_var", "no_cp", "no_deadband"):
        score = validation_set["D6_raw"].to_numpy() if condition == "full" else _ablation_score(validation_set, condition, cfg)
        sync_score = sync["D6_raw"].to_numpy() if condition == "full" else _ablation_score(sync, condition, cfg)
        scored_validation = validation_set[["window_id", "is_unilateral_fault"]].copy()
        scored_validation["score"] = score
        auc_low, auc_high = _cluster_bootstrap_interval(
            scored_validation,
            lambda draw: roc_auc_score(draw["is_unilateral_fault"].astype(int), 5.0 - draw["score"]),
            rng,
        )
        scored_sync = sync[["window_id"]].copy()
        scored_sync["score"] = sync_score
        far_low, far_high = _cluster_bootstrap_interval(
            scored_sync,
            lambda draw: (draw["score"] < cfg.classification["asymmetry_max"]).mean(),
            rng,
        )
        ablation_rows.append({
            "condition": condition, "ROC_AUC": float(roc_auc_score(labels, 5.0 - score)),
            "AUC_CI_low": auc_low, "AUC_CI_high": auc_high,
            "synchronous_FAR": float((sync_score < cfg.classification["asymmetry_max"]).mean()),
            "FAR_CI_low": far_low, "FAR_CI_high": far_high,
            "n_positive": int(labels.sum()), "n_negative": int((1 - labels).sum()),
        })
    outputs = {
        "summary": pd.DataFrame(summary_rows),
        "injection_scores": scores,
        "roc_pr_curves": pd.DataFrame(curve_rows),
        "ablation": pd.DataFrame(ablation_rows),
    }
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        for name, frame in outputs.items():
            frame.to_excel(writer, sheet_name=name, index=False)
    return outputs
