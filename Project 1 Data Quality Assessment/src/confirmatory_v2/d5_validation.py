from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.metrics import average_precision_score, roc_auc_score

from .common import CONFIG_ROOT, PROJECT_ROOT, event_jaccard, read_yaml, wilson_interval


D5_ROOT = PROJECT_ROOT / "D5 Topological Role Consistency and Structural Representativeness"
D5_LOCAL = D5_ROOT / "outputs" / "local"


def _monthly_component_ablation(
    main: pd.DataFrame,
    *,
    removed: str,
    repetitions: int,
    rng: np.random.Generator,
) -> dict[str, object]:
    q_columns = ["Q_profile", "Q_gradient", "Q_rank", "Q_rep"]
    kept = [column for column in q_columns if column != removed]
    frame = main[["timestamp", "D5_raw", *kept]].dropna().copy()
    frame["variant"] = frame[kept].mean(axis=1)
    frame["month"] = frame["timestamp"].dt.to_period("M").astype(str)
    monthly = []
    for month, group in frame.groupby("month"):
        monthly.append(
            {
                "month": month,
                "rho": float(spearmanr(group["D5_raw"], group["variant"]).statistic),
                "jaccard": event_jaccard(group["D5_raw"].lt(3.0), group["variant"].lt(3.0)),
                "mean_delta": float((group["variant"] - group["D5_raw"]).mean()),
            }
        )
    monthly_frame = pd.DataFrame(monthly)
    draws = {"rho": [], "jaccard": [], "mean_delta": []}
    for _ in range(repetitions):
        sampled = monthly_frame.iloc[
            rng.integers(0, len(monthly_frame), size=len(monthly_frame))
        ]
        for metric in draws:
            draws[metric].append(float(sampled[metric].mean()))
    return {
        "variant": f"without_{removed.removeprefix('Q_')}",
        "status": "computed_component_score_space_ablation",
        "spearman_vs_full": float(monthly_frame["rho"].mean()),
        "spearman_ci_low": float(np.quantile(draws["rho"], 0.025)),
        "spearman_ci_high": float(np.quantile(draws["rho"], 0.975)),
        "event_jaccard": float(monthly_frame["jaccard"].mean()),
        "jaccard_ci_low": float(np.quantile(draws["jaccard"], 0.025)),
        "jaccard_ci_high": float(np.quantile(draws["jaccard"], 0.975)),
        "mean_score_delta": float(monthly_frame["mean_delta"].mean()),
        "analysis_unit": "calendar_month",
        "n_independent_months": int(len(monthly_frame)),
    }


def _blocked_metrics(trials: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for fold, frame in trials.groupby("blocked_fold"):
        swap = frame[frame["scenario"].eq("channel_swap")].copy()
        if swap.empty:
            continue
        labels = np.r_[np.zeros(len(swap)), np.ones(len(swap))]
        scores = np.r_[swap["baseline_statistic"], swap["injected_statistic"]]
        top1 = int(swap["top1_hit"].sum())
        low, high = wilson_interval(top1, len(swap))
        rows.extend(
            [
                {
                    "blocked_fold": fold,
                    "metric": "AUROC",
                    "estimate": float(roc_auc_score(labels, scores)),
                    "ci_low": np.nan,
                    "ci_high": np.nan,
                    "n": len(swap),
                },
                {
                    "blocked_fold": fold,
                    "metric": "AUPRC",
                    "estimate": float(average_precision_score(labels, scores)),
                    "ci_low": np.nan,
                    "ci_high": np.nan,
                    "n": len(swap),
                },
                {
                    "blocked_fold": fold,
                    "metric": "Top1",
                    "estimate": top1 / len(swap),
                    "ci_low": low,
                    "ci_high": high,
                    "n": len(swap),
                },
            ]
        )
    return pd.DataFrame(rows)


def run_d5_validation(output_dir: Path) -> dict[str, pd.DataFrame]:
    main = pd.read_parquet(D5_LOCAL / "D5_main_scores_hourly.parquet")
    main["timestamp"] = pd.to_datetime(main["timestamp"])
    validation_path = D5_LOCAL / "D5_validation_results.xlsx"
    trials = pd.read_excel(validation_path, sheet_name="injection_trials")
    acceptance = pd.read_excel(validation_path, sheet_name="acceptance")
    negative = pd.read_excel(validation_path, sheet_name="negative_controls")
    support = pd.read_parquet(D5_LOCAL / "D5_support_assessment.parquet")
    sap = read_yaml(CONFIG_ROOT / "statistical_analysis_plan_v2.yaml")
    repetitions = int(sap["uncertainty"]["repetitions"])
    rng = np.random.default_rng(int(sap["uncertainty"]["seed"]))

    component_ablation = pd.DataFrame(
        [
            _monthly_component_ablation(
                main,
                removed=column,
                repetitions=repetitions,
                rng=rng,
            )
            for column in ["Q_profile", "Q_gradient", "Q_rank", "Q_rep"]
        ]
    )
    pending_ablation = pd.DataFrame(
        [
            {
                "variant": variant,
                "status": "pending_full_outer_fold_refit",
                "reason": (
                    "The variant changes regime/template estimation and cannot be "
                    "computed by algebraically perturbing released scores."
                ),
            }
            for variant in [
                "without_QR_QIR_context",
                "without_time_of_day",
                "without_MAP_hysteresis",
                "fixed_regime",
            ]
        ]
    )
    blocked = _blocked_metrics(trials)
    support_funnel = pd.DataFrame(
        [
            {
                "stage": "family_L3",
                "count": int(support["family_support_level"].eq("L3").sum()),
            },
            {
                "stage": "node_candidate",
                "count": int(
                    (
                        support["family_support_level"].eq("L3")
                        & support["node_support_level"].isin(["L2", "L3"])
                    ).sum()
                ),
            },
            {
                "stage": "final_node_L3",
                "count": int(support["support_level"].eq("L3").sum()),
            },
            {
                "stage": "sensor_veto_eligible",
                "count": int(support["veto_eligible"].fillna(False).sum()),
            },
        ]
    )
    coverage = (
        main.assign(month=main["timestamp"].dt.to_period("M").astype(str))
        .groupby(["month", "evaluation_status"], as_index=False)
        .size()
        .rename(columns={"size": "sensor_hours"})
    )
    totals = coverage.groupby("month")["sensor_hours"].transform("sum")
    coverage["fraction"] = coverage["sensor_hours"] / totals
    outputs = {
        "D5_component_ablation": component_ablation,
        "D5_pending_full_refit_ablation": pending_ablation,
        "D5_blocked_validation": blocked,
        "D5_support_funnel": support_funnel,
        "D5_coverage_by_month": coverage,
        "D5_acceptance": acceptance,
        "D5_negative_controls": negative,
    }
    for name, frame in outputs.items():
        frame.to_parquet(output_dir / f"{name}.parquet", index=False)
    return outputs

