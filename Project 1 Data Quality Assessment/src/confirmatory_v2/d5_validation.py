from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.metrics import average_precision_score, roc_auc_score, silhouette_score

from .common import (
    CONFIG_ROOT,
    PROJECT_ROOT,
    cluster_bootstrap_interval,
    event_jaccard,
    read_yaml,
    wilson_interval,
)


D5_ROOT = PROJECT_ROOT / "D5 Topological Role Consistency and Structural Representativeness"
D5_LOCAL = D5_ROOT / "outputs" / "local"


def _load_d5_refit_api() -> dict[str, object]:
    source_root = D5_ROOT / "src"
    if str(source_root) not in sys.path:
        sys.path.insert(0, str(source_root))
    from d5_common.config import load_yaml, resolve_paths  # type: ignore
    from d5_local.context import (  # type: ignore
        ContextPosteriorModel,
        GlobalProcessContextBuilder,
        RegimeHysteresisController,
    )
    from d5_local.contracts import TopologyRegistry  # type: ignore
    from d5_local.data import SnapshotBuilder  # type: ignore
    from d5_local.evidence import SpatialEvidenceEngine  # type: ignore
    from d5_local.templates import (  # type: ignore
        ORPDegradationPolicy,
        SpatialTemplateBuilder,
    )
    from d5_local.validation.runner import D5ValidationRunner  # type: ignore

    return {
        "load_yaml": load_yaml,
        "resolve_paths": resolve_paths,
        "ContextPosteriorModel": ContextPosteriorModel,
        "GlobalProcessContextBuilder": GlobalProcessContextBuilder,
        "RegimeHysteresisController": RegimeHysteresisController,
        "TopologyRegistry": TopologyRegistry,
        "SnapshotBuilder": SnapshotBuilder,
        "SpatialEvidenceEngine": SpatialEvidenceEngine,
        "ORPDegradationPolicy": ORPDegradationPolicy,
        "SpatialTemplateBuilder": SpatialTemplateBuilder,
        "D5ValidationRunner": D5ValidationRunner,
    }


def _select_training_k(
    features: pd.DataFrame,
    *,
    train_end: pd.Timestamp,
    design: dict,
    model_class,
    random_seed: int,
) -> tuple[int, list[dict[str, float | int]]]:
    training = features.loc[:train_end]
    maximum_rows = int(design["k_selection"]["maximum_rows"])
    if len(training) > maximum_rows:
        positions = np.linspace(0, len(training) - 1, maximum_rows, dtype=int)
        selection = training.iloc[positions]
    else:
        selection = training
    rows: list[dict[str, float | int]] = []
    for k in design["k_selection"]["candidates"]:
        model = model_class(n_regimes=int(k), random_seed=random_seed).fit(selection)
        result = model.predict(selection)
        clean = selection.fillna(model.fill_values)
        scaled = model.scaler.transform(clean)
        score = float(silhouette_score(scaled, result.map_regime))
        rows.append({"k": int(k), "silhouette": score, "n_rows": len(selection)})
    rows.sort(key=lambda row: (-float(row["silhouette"]), int(row["k"])))
    return int(rows[0]["k"]), rows


def _direct_regime_state(
    index: pd.DatetimeIndex,
    result,
    sensors: list[str],
) -> pd.DataFrame:
    frames = []
    for sensor in sensors:
        frames.append(
            pd.DataFrame(
                {
                    "timestamp": index,
                    "sensor_id": sensor,
                    "map_regime_id": result.map_regime,
                    "map_probability": result.map_probability,
                    "active_regime_id": result.map_regime,
                    "normalized_entropy": result.entropy,
                    "ood_distance": result.ood_distance,
                    "ood_threshold": result.ood_threshold,
                    "regime_state": "DirectMAP",
                    "posterior_gap": np.nan,
                }
            )
        )
    return pd.concat(frames, ignore_index=True)


def _fit_outer_regime(
    snapshots: pd.DataFrame,
    *,
    topology,
    variant: str,
    train_end: pd.Timestamp,
    design: dict,
    api: dict[str, object],
    config: dict,
    hysteresis_config: dict,
    windows: dict,
) -> tuple[pd.DataFrame, int, list[str], list[dict[str, float | int]]]:
    context_builder = api["GlobalProcessContextBuilder"](topology)
    features = context_builder.build(snapshots)
    if variant == "no_exogenous_context":
        features = features.drop(
            columns=[
                "QR_1",
                "QR_2",
                "QIR_1",
                "QIR_2",
                "sin_hour",
                "cos_hour",
            ]
        )
    if variant == "no_regime_conditioning":
        k = 1
        selection_audit = [
            {
                "k": 1,
                "silhouette": np.nan,
                "n_rows": int(len(features.loc[:train_end])),
            }
        ]
    else:
        k, selection_audit = _select_training_k(
            features,
            train_end=train_end,
            design=design,
            model_class=api["ContextPosteriorModel"],
            random_seed=int(config["random_seed"]),
        )
    if variant == "no_regime_conditioning":
        result = SimpleNamespace(
            map_regime=np.zeros(len(features), dtype=int),
            map_probability=np.ones(len(features), dtype=float),
            entropy=np.zeros(len(features), dtype=float),
            ood_distance=np.zeros(len(features), dtype=float),
            ood_threshold=np.inf,
        )
    else:
        model = api["ContextPosteriorModel"](
            n_regimes=k,
            random_seed=int(config["random_seed"]),
            likelihood_temperature_multiplier=float(
                config["posterior_temperature_multiplier"]
            ),
        ).fit(features.loc[:train_end])
        result = model.predict(features)
    if variant in {"no_hysteresis", "no_regime_conditioning"}:
        state = _direct_regime_state(
            snapshots.index,
            result,
            topology.node_ids(),
        )
    else:
        controller = api["RegimeHysteresisController"](hysteresis_config)
        state = pd.concat(
            [
                controller.replay(
                    snapshots.index,
                    result.probabilities,
                    result.entropy,
                    result.ood_distance,
                    result.ood_threshold,
                    sensor,
                    int(windows["snapshot_main_minutes"]),
                )
                for sensor in topology.node_ids()
            ],
            ignore_index=True,
        )
    return state, k, features.columns.tolist(), selection_audit


def _risk_references_from_training(
    engine,
    snapshots: pd.DataFrame,
    state: pd.DataFrame,
    templates: dict,
    *,
    topology,
    train_end: pd.Timestamp,
    windows: dict,
) -> dict[tuple[str, str, int | None, str | None], np.ndarray]:
    training_snapshots = snapshots.loc[:train_end]
    training_state = state[state["timestamp"].le(train_end)]
    evidence = engine.score(training_snapshots, training_state, templates)
    periods = int(
        int(windows["main_window_hours"])
        * 60
        / int(windows["snapshot_main_minutes"])
    )
    minimum = int(
        np.ceil(periods * float(windows["minimum_window_coverage"]))
    )
    state_hourly = training_state.loc[
        pd.DatetimeIndex(training_state["timestamp"]).minute == 0,
        ["timestamp", "sensor_id", "active_regime_id"],
    ]
    nodes = topology.nodes.set_index("sensor_id")
    output: dict[tuple[str, str, int | None, str | None], np.ndarray] = {}
    for risk in ["risk_profile", "risk_gradient", "risk_rank", "risk_rep"]:
        raw = getattr(evidence, risk)
        rolling = raw.rolling(periods, min_periods=minimum)
        hourly = 0.60 * rolling.median() + 0.40 * rolling.quantile(0.90)
        hourly = hourly.loc[hourly.index.minute == 0]
        long = (
            hourly.rename_axis("timestamp")
            .stack(future_stack=True)
            .rename("risk")
            .reset_index()
        )
        long.columns = ["timestamp", "sensor_id", "risk"]
        long["analyte"] = long["sensor_id"].map(nodes["analyte"])
        long["zone_id"] = long["sensor_id"].map(nodes["zone_id"])
        long = long.merge(
            state_hourly,
            on=["timestamp", "sensor_id"],
            how="left",
        )
        for analyte in ["DO", "ORP"]:
            analyte_frame = long[long["analyte"].eq(analyte)]
            output[(risk, analyte, None, None)] = analyte_frame[
                "risk"
            ].dropna().to_numpy(float)
            for regime, regime_frame in analyte_frame.groupby(
                "active_regime_id", dropna=True
            ):
                values = regime_frame["risk"].dropna()
                if len(values) >= 100:
                    output[(risk, analyte, int(regime), None)] = values.to_numpy(
                        float
                    )
                for zone, zone_frame in regime_frame.groupby("zone_id"):
                    values = zone_frame["risk"].dropna()
                    if len(values) >= 100:
                        output[
                            (risk, analyte, int(regime), str(zone))
                        ] = values.to_numpy(float)
    return output


def _fold_test_schedule(
    snapshots: pd.DataFrame,
    *,
    test_start: pd.Timestamp,
    test_end: pd.Timestamp,
    n_windows: int,
    topology,
) -> list[tuple[str, pd.Timestamp]]:
    last_start = min(test_end - pd.Timedelta(hours=24), snapshots.index.max())
    candidates = pd.date_range(test_start.ceil("D"), last_start.floor("D"), freq="24h")
    if not len(candidates):
        return []
    positions = np.linspace(0, len(candidates) - 1, n_windows, dtype=int)
    starts = candidates[positions]
    nodes = topology.nodes
    targets = {
        analyte: nodes.loc[nodes["analyte"].eq(analyte), "sensor_id"].tolist()
        for analyte in ["DO", "ORP"]
    }
    counts = {"DO": 0, "ORP": 0}
    schedule = []
    for index, start in enumerate(starts):
        analyte = "DO" if index % 2 == 0 else "ORP"
        target = targets[analyte][counts[analyte] % len(targets[analyte])]
        counts[analyte] += 1
        schedule.append((target, pd.Timestamp(start)))
    return schedule


def _outer_refit_ablation(
    sap: dict,
    design: dict,
    *,
    repetitions: int,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    api = _load_d5_refit_api()
    load_yaml = api["load_yaml"]
    paths = api["resolve_paths"]()
    common_root = D5_ROOT / "configs" / "common"
    local_root = D5_ROOT / "configs" / "local"
    config = load_yaml(local_root / "d5_local.yaml")
    windows = load_yaml(common_root / "windows.yaml")
    hysteresis = load_yaml(local_root / "hysteresis.yaml")
    aggregation = load_yaml(local_root / "aggregation.yaml")
    orp_config = load_yaml(local_root / "orp_degradation.yaml")
    topology = api["TopologyRegistry"].load(common_root)
    observations = pd.read_parquet(paths.canonical_observations)
    required = [*topology.node_ids(), "QR_1", "QR_2", "QIR_1", "QIR_2"]
    floor_sensors = topology.nodes.loc[
        topology.nodes["floor_flag"], "sensor_id"
    ].tolist()
    snapshots = api["SnapshotBuilder"](
        int(windows["snapshot_main_minutes"]),
        int(windows["snapshot_min_observations"]),
    ).build(observations[required], floor_sensors).values
    runner = api["D5ValidationRunner"](n_trials_per_scenario=1, random_seed=42)
    variants = design["structural_outer_refits"]
    trial_rows: list[dict[str, object]] = []
    metric_rows: list[dict[str, object]] = []
    registry_rows: list[dict[str, object]] = []
    for fold in sap["temporal_validation"]["outer_test_blocks"]:
        train_end = pd.Timestamp(fold["train_end"])
        test_start = pd.Timestamp(fold["test_start"])
        test_end = pd.Timestamp(fold["test_end"])
        schedule = _fold_test_schedule(
            snapshots,
            test_start=test_start,
            test_end=test_end,
            n_windows=int(design["test_windows_per_fold"]),
            topology=topology,
        )
        for variant in variants:
            state, k, features, k_audit = _fit_outer_regime(
                snapshots,
                topology=topology,
                variant=variant,
                train_end=train_end,
                design=design,
                api=api,
                config=config,
                hysteresis_config=hysteresis,
                windows=windows,
            )
            builder = api["SpatialTemplateBuilder"](
                topology,
                config["template_version"],
                api["ORPDegradationPolicy"](orp_config),
                aggregation["support_policy"],
            )
            templates, support = builder.build(snapshots, state, train_end)
            engine = api["SpatialEvidenceEngine"](topology)
            references = _risk_references_from_training(
                engine,
                snapshots,
                state,
                templates,
                topology=topology,
                train_end=train_end,
                windows=windows,
            )
            registry_rows.append(
                {
                    "blocked_fold": fold["fold_id"],
                    "variant": variant,
                    "train_end": train_end,
                    "test_start": test_start,
                    "test_end": test_end,
                    "selected_k": k,
                    "feature_names": json.dumps(features),
                    "k_selection_audit": json.dumps(k_audit),
                    "n_training_snapshots": int(
                        snapshots.index.to_series().le(train_end).sum()
                    ),
                    "n_templates": len(templates),
                    "n_family_L3": int(
                        support["support_level"].eq("L3").sum()
                    ),
                    "selection_scope": "training_only",
                    "test_labels_used_for_selection": False,
                }
            )
            nodes = topology.nodes.set_index("sensor_id")
            variant_trials = []
            for trial_no, (target, start) in enumerate(schedule, 1):
                end = start + pd.Timedelta(hours=23, minutes=50)
                frame = snapshots.loc[start:end].copy()
                state_window = state[state["timestamp"].isin(frame.index)]
                baseline, baseline_localization = runner._window_stat(
                    engine.score(frame, state_window, templates),
                    references,
                    state_window,
                )
                meta = nodes.loc[target]
                donors = nodes[
                    nodes["analyte"].eq(meta["analyte"])
                    & nodes["line_id"].eq(meta["line_id"])
                    & nodes.index.to_series().ne(target).to_numpy()
                ].index.tolist()
                donor = donors[trial_no % len(donors)]
                injected = frame.copy()
                target_values = frame[target].to_numpy(copy=True)
                injected[target] = frame[donor].to_numpy()
                injected[donor] = target_values
                injected_stat, injected_localization = runner._window_stat(
                    engine.score(injected, state_window, templates),
                    references,
                    state_window,
                )
                affected = [target, donor]
                delta = injected_localization - baseline_localization
                rank = int(
                    delta.rank(ascending=False, method="min").loc[affected].min()
                )
                record = {
                    "blocked_fold": fold["fold_id"],
                    "variant": variant,
                    "trial_id": (
                        f"D5-OUTER-{fold['fold_id']}-{variant}-{trial_no:02d}"
                    ),
                    "scenario": "channel_swap",
                    "start_ts": start,
                    "end_ts": start + pd.Timedelta(hours=24),
                    "target_sensor": target,
                    "donor_sensor": donor,
                    "affected_sensors": json.dumps(affected),
                    "baseline_statistic": float(baseline.loc[affected].max()),
                    "injected_statistic": float(injected_stat.loc[affected].max()),
                    "target_rank": rank,
                    "top1_hit": rank == 1,
                    "calibration_scope": (
                        "training_only_empirical_risk_reference"
                    ),
                    "templates_and_regimes_frozen_in_test": True,
                }
                trial_rows.append(record)
                variant_trials.append(record)
            frame = pd.DataFrame(variant_trials)
            if frame.empty:
                continue
            labels = np.r_[np.zeros(len(frame)), np.ones(len(frame))]
            scores = np.r_[
                frame["baseline_statistic"],
                frame["injected_statistic"],
            ]
            for metric, estimate in [
                ("AUROC", roc_auc_score(labels, scores)),
                ("AUPRC", average_precision_score(labels, scores)),
                ("Top1", frame["top1_hit"].mean()),
            ]:
                metric_rows.append(
                    {
                        "blocked_fold": fold["fold_id"],
                        "variant": variant,
                        "metric": metric,
                        "estimate": float(estimate),
                        "n_trials": len(frame),
                    }
                )
    fold_metrics = pd.DataFrame(metric_rows)
    summary_rows = []
    rng = np.random.default_rng(20260731)
    thresholds = {"AUROC": 0.90, "AUPRC": 0.80, "Top1": 0.80}
    for (variant, metric), frame in fold_metrics.groupby(
        ["variant", "metric"], sort=False
    ):
        low, high = cluster_bootstrap_interval(
            frame,
            lambda sample: float(sample["estimate"].mean()),
            cluster_columns=["blocked_fold"],
            repetitions=repetitions,
            rng=rng,
        )
        estimate = float(frame["estimate"].mean())
        summary_rows.append(
            {
                "variant": variant,
                "metric": metric,
                "estimate": estimate,
                "ci95_low": low,
                "ci95_high": high,
                "n_outer_folds": frame["blocked_fold"].nunique(),
                "threshold": thresholds[metric],
                "passed": estimate >= thresholds[metric],
                "analysis_unit": "blocked_future_month",
                "ci_method": "outer_fold_cluster_bootstrap",
            }
        )
    return (
        pd.DataFrame(trial_rows),
        fold_metrics,
        pd.DataFrame(summary_rows),
        pd.DataFrame(registry_rows),
    )


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


def _paired_outer_fold_deltas(
    fold_metrics: pd.DataFrame,
    *,
    reference_variant: str,
    metrics: list[str],
    repetitions: int,
    rng: np.random.Generator,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    reference = fold_metrics[
        fold_metrics["variant"].eq(reference_variant)
        & fold_metrics["metric"].isin(metrics)
    ][["blocked_fold", "metric", "estimate"]].rename(
        columns={"estimate": "reference_estimate"}
    )
    comparisons = []
    for variant in fold_metrics["variant"].drop_duplicates():
        if variant == reference_variant:
            continue
        ablation = fold_metrics[
            fold_metrics["variant"].eq(variant)
            & fold_metrics["metric"].isin(metrics)
        ][["blocked_fold", "metric", "estimate"]].rename(
            columns={"estimate": "ablation_estimate"}
        )
        paired = reference.merge(
            ablation,
            on=["blocked_fold", "metric"],
            how="inner",
            validate="one_to_one",
        )
        paired.insert(1, "reference_variant", reference_variant)
        paired.insert(2, "ablation_variant", variant)
        paired["delta_full_minus_ablation"] = (
            paired["reference_estimate"] - paired["ablation_estimate"]
        )
        comparisons.append(paired)
    deltas = pd.concat(comparisons, ignore_index=True)
    summary_rows = []
    for (variant, metric), frame in deltas.groupby(
        ["ablation_variant", "metric"],
        sort=False,
    ):
        low, high = cluster_bootstrap_interval(
            frame,
            lambda sample: float(
                sample["delta_full_minus_ablation"].mean()
            ),
            cluster_columns=["blocked_fold"],
            repetitions=repetitions,
            rng=rng,
        )
        summary_rows.append(
            {
                "reference_variant": reference_variant,
                "ablation_variant": variant,
                "metric": metric,
                "mean_delta_full_minus_ablation": float(
                    frame["delta_full_minus_ablation"].mean()
                ),
                "ci95_low": low,
                "ci95_high": high,
                "positive_gain_fold_fraction": float(
                    frame["delta_full_minus_ablation"].gt(0).mean()
                ),
                "n_outer_month_folds": int(frame["blocked_fold"].nunique()),
                "analysis_unit": "paired_blocked_future_month",
                "ci_method": "cluster_bootstrap_outer_month_fold",
                "production_model_changed": False,
            }
        )
    return deltas, pd.DataFrame(summary_rows)


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
    (
        outer_trials,
        outer_fold_metrics,
        outer_summary,
        outer_registry,
    ) = _outer_refit_ablation(
        sap,
        read_yaml(CONFIG_ROOT / "validation_design.yaml")["D5"],
        repetitions=repetitions,
    )
    paired_design = read_yaml(CONFIG_ROOT / "validation_design.yaml")["D5"][
        "paired_ablation_delta"
    ]
    paired_deltas, paired_delta_summary = _paired_outer_fold_deltas(
        outer_fold_metrics,
        reference_variant=paired_design["reference_variant"],
        metrics=list(paired_design["metrics"]),
        repetitions=repetitions,
        rng=rng,
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
        "D5_outer_refit_trials": outer_trials,
        "D5_outer_refit_fold_metrics": outer_fold_metrics,
        "D5_outer_refit_summary": outer_summary,
        "D5_outer_refit_model_registry": outer_registry,
        "D5_outer_refit_paired_deltas": paired_deltas,
        "D5_outer_refit_paired_delta_summary": paired_delta_summary,
        "D5_blocked_validation": blocked,
        "D5_support_funnel": support_funnel,
        "D5_coverage_by_month": coverage,
        "D5_acceptance": acceptance,
        "D5_negative_controls": negative,
    }
    for name, frame in outputs.items():
        frame.to_parquet(output_dir / f"{name}.parquet", index=False)
    return outputs
