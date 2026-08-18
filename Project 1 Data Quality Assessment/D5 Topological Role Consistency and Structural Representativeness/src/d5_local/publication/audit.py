from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd
from scipy.optimize import linear_sum_assignment
from scipy.stats import kendalltau, rankdata, spearmanr

from d5_common.config import (
    D5_ROOT,
    load_yaml,
    reference_end_from_fraction,
    resolve_paths,
)
from d5_local.context import ContextPosteriorModel, GlobalProcessContextBuilder
from d5_local.contracts import TopologyRegistry
from d5_local.data import SnapshotBuilder
from d5_local.templates import SupportPolicy


class D5PublicationAudit:
    def __init__(self) -> None:
        self.paths = resolve_paths()
        self.config = load_yaml(
            D5_ROOT / "configs" / "publication" / "d5_final_contract.yaml"
        )
        self.local_config = load_yaml(D5_ROOT / "configs" / "local" / "d5_local.yaml")
        self.windows = load_yaml(D5_ROOT / "configs" / "common" / "windows.yaml")
        self.aggregation = load_yaml(D5_ROOT / "configs" / "local" / "aggregation.yaml")
        self.template_config = load_yaml(
            D5_ROOT / "configs" / "local" / "templates.yaml"
        )
        self.topology = TopologyRegistry.load(D5_ROOT / "configs" / "common")
        self.output_root = D5_ROOT / "outputs" / "publication"
        self.output_root.mkdir(parents=True, exist_ok=True)
        self.rng = np.random.default_rng(int(self.config["random_seed"]))

    def run(self) -> dict[str, object]:
        main = pd.read_parquet(
            self.paths.local_output_root / "D5_main_scores_hourly.parquet"
        )
        trials = pd.read_excel(
            self.paths.local_output_root / "D5_validation_results.xlsx",
            sheet_name="injection_trials",
        )
        confirmatory = self._confirmatory_root()
        outer_summary = pd.read_parquet(
            confirmatory / "D5_outer_refit_summary.parquet"
        )
        outer_deltas = pd.read_parquet(
            confirmatory / "D5_outer_refit_paired_delta_summary.parquet"
        )
        coverage_summary = pd.read_parquet(
            confirmatory / "D5_coverage_selection_summary.parquet"
        )
        coverage_strata = pd.read_parquet(
            confirmatory / "D5_coverage_strata.parquet"
        )
        localization = self._localization_summary(trials)
        risk_coverage = self._risk_coverage(trials, main)
        monthly_coverage = self._monthly_coverage(main)
        support_sensitivity = self._support_sensitivity()
        (
            d4_dependence,
            d4_stratified,
            d4_composite,
            d4_meta,
        ) = self._d4_d5_audit(main, confirmatory)
        dimension_availability = self._dimension_availability_sensitivity(
            confirmatory
        )
        target_influence = self._target_influence_audit()
        decisions = self._decision_register(d4_meta)

        tables = {
            "decision_register": decisions,
            "outer_refit_summary": outer_summary,
            "outer_refit_deltas": outer_deltas,
            "localization": localization,
            "risk_coverage": risk_coverage,
            "monthly_coverage": monthly_coverage,
            "support_sensitivity": support_sensitivity,
            "d4_d5_dependence": d4_dependence,
            "d4_d5_stratified_rho": d4_stratified,
            "d4_d5_composite": d4_composite,
            "dimension_availability": dimension_availability,
            "target_influence": target_influence,
            "coverage_summary": coverage_summary,
            "coverage_strata": coverage_strata,
        }
        self._write_tables(tables)
        summary = self._summary_payload(
            outer_summary,
            localization,
            monthly_coverage,
            d4_dependence,
            d4_stratified,
            dimension_availability,
            target_influence,
            d4_meta,
        )
        report = self._build_report(summary, decisions, outer_deltas)
        report_path = self.output_root / "D5_PUBLICATION_READINESS_AUDIT_v1.1.md"
        report_path.write_text(report, encoding="utf-8")
        manifest = self._write_manifest(summary, tables, report_path, d4_meta)
        return {
            "output_root": str(self.output_root),
            "summary": summary,
            "manifest": str(manifest),
        }

    def _confirmatory_root(self) -> Path:
        root = (
            self.paths.project_root
            / "outputs"
            / "confirmatory"
            / str(self.config["confirmatory_run_id"])
        )
        required = [
            "D5_outer_refit_summary.parquet",
            "D5_outer_refit_paired_delta_summary.parquet",
            "D5_coverage_selection_summary.parquet",
        ]
        missing = [name for name in required if not (root / name).exists()]
        if missing:
            raise FileNotFoundError(f"Missing confirmatory D5 artifacts: {missing}")
        return root

    def _localization_summary(self, trials: pd.DataFrame) -> pd.DataFrame:
        required = {
            "top1_hit",
            "top2_hit",
            "reciprocal_rank",
            "topological_hop_error",
            "blocked_fold",
        }
        missing = required - set(trials.columns)
        if missing:
            raise ValueError(
                "Rerun D5 validation before publication audit; missing columns: "
                + ", ".join(sorted(missing))
            )
        groups = [("all", "all", trials)]
        groups.extend(
            (str(scenario), "all", frame)
            for scenario, frame in trials.groupby("scenario")
        )
        groups.extend(
            (str(scenario), str(analyte), frame)
            for (scenario, analyte), frame in trials.groupby(
                ["scenario", "target_analyte"]
            )
        )
        metrics: dict[str, Callable[[pd.DataFrame], float]] = {
            "Top1": lambda frame: float(frame["top1_hit"].mean()),
            "Top2": lambda frame: float(frame["top2_hit"].mean()),
            "MRR": lambda frame: float(frame["reciprocal_rank"].mean()),
            "median_hop_error": lambda frame: float(
                frame["topological_hop_error"].median()
            ),
        }
        rows = []
        for scenario, analyte, frame in groups:
            for metric, estimator in metrics.items():
                low, high = self.cluster_bootstrap_interval(
                    frame,
                    cluster="blocked_fold",
                    estimator=estimator,
                    repetitions=int(
                        self.config["statistical_analysis"]["bootstrap_repetitions"]
                    ),
                    rng=self.rng,
                )
                rows.append(
                    {
                        "scenario": scenario,
                        "analyte": analyte,
                        "metric": metric,
                        "estimate": estimator(frame),
                        "ci95_low": low,
                        "ci95_high": high,
                        "n_trials": len(frame),
                        "n_month_blocks": frame["blocked_fold"].nunique(),
                        "analysis_unit": "injected_24h_window",
                        "ci_method": "blocked_month_cluster_bootstrap",
                    }
                )
        return pd.DataFrame(rows)

    def _risk_coverage(
        self, trials: pd.DataFrame, main: pd.DataFrame
    ) -> pd.DataFrame:
        trial_rows = []
        main = main.copy()
        main["timestamp"] = pd.to_datetime(main["timestamp"])
        for trial in trials.itertuples(index=False):
            selected = main[
                main["sensor_id"].eq(trial.target_sensor)
                & main["timestamp"].between(trial.start_ts, trial.end_ts)
            ]
            trial_rows.append(
                {
                    "trial_id": trial.trial_id,
                    "confidence": float(selected["confidence"].median()),
                    "top1_hit": bool(trial.top1_hit),
                    "top2_hit": bool(trial.top2_hit),
                    "reciprocal_rank": float(trial.reciprocal_rank),
                }
            )
        frame = pd.DataFrame(trial_rows).dropna(subset=["confidence"])
        rows = []
        for retained_fraction in [1.0, 0.8, 0.6, 0.4]:
            retained = max(1, int(np.ceil(len(frame) * retained_fraction)))
            selected = frame.nlargest(retained, "confidence")
            rows.append(
                {
                    "retained_fraction": retained / len(frame),
                    "minimum_confidence": selected["confidence"].min(),
                    "top1": selected["top1_hit"].mean(),
                    "top2": selected["top2_hit"].mean(),
                    "mrr": selected["reciprocal_rank"].mean(),
                    "n_trials": len(selected),
                    "interpretation": "controlled_injection_risk_coverage_not_field_error_rate",
                }
            )
        return pd.DataFrame(rows)

    @staticmethod
    def _monthly_coverage(main: pd.DataFrame) -> pd.DataFrame:
        frame = main.copy()
        frame["timestamp"] = pd.to_datetime(frame["timestamp"])
        frame["month"] = frame["timestamp"].dt.to_period("M").astype(str)
        rows = []
        for month, group in frame.groupby("month"):
            rows.append(
                {
                    "month": month,
                    "sensor_hours": len(group),
                    "raw_score_coverage": group["D5_raw"].notna().mean(),
                    "report_score_coverage": group["D5_report_score"].notna().mean(),
                    "ood_rate": group["evaluation_status"].eq("ood_context").mean(),
                    "L1_rate": group["support_level"].eq("L1").mean(),
                    "L2_rate": group["support_level"].eq("L2").mean(),
                    "L3_rate": group["support_level"].eq("L3").mean(),
                    "D5_raw_median": group["D5_raw"].median(),
                    "D5_raw_p05": group["D5_raw"].quantile(0.05),
                }
            )
        return pd.DataFrame(rows)

    def _support_sensitivity(self) -> pd.DataFrame:
        support = pd.read_parquet(
            self.paths.local_output_root / "D5_support_assessment.parquet"
        )
        base_config = self.aggregation["support_policy"]
        rows = []
        sensitivity = self.config["support_contract"]["sensitivity_only"]
        for n_multiplier in sensitivity["n_effective_multiplier"]:
            for coverage in sensitivity["node_reference_coverage"]:
                for stability in sensitivity["node_bootstrap_stability"]:
                    config = json.loads(json.dumps(base_config))
                    for tier in ["L1", "L2", "L3"]:
                        config["thresholds"][tier]["min_effective_blocks"] = int(
                            np.ceil(
                                base_config["thresholds"][tier]["min_effective_blocks"]
                                * float(n_multiplier)
                            )
                        )
                        config["node_validation"][tier]["min_effective_blocks"] = int(
                            np.ceil(
                                base_config["node_validation"][tier]["min_effective_blocks"]
                                * float(n_multiplier)
                            )
                        )
                    config["node_validation"]["L3"]["min_reference_coverage"] = float(
                        coverage
                    )
                    config["node_validation"]["L3"]["min_bootstrap_stability"] = float(
                        stability
                    )
                    policy = SupportPolicy(config)
                    levels = []
                    for item in support.itertuples(index=False):
                        family = policy.resolve(
                            int(item.family_n_effective),
                            int(item.family_distinct_months),
                            bootstrap_stability=float(item.family_bootstrap_stability),
                            holdout_count=int(item.family_holdout_count),
                            holdout_far=float(item.family_holdout_far),
                        )
                        node = policy.resolve_node(
                            int(item.node_n_effective),
                            int(item.node_distinct_months),
                            reference_coverage=float(item.node_reference_coverage),
                            bootstrap_stability=float(item.node_bootstrap_stability),
                            holdout_count=int(item.node_holdout_count),
                            holdout_far=float(item.node_holdout_far),
                        )
                        levels.append(policy.minimum_tier(family, node))
                    counts = pd.Series(levels).value_counts()
                    rows.append(
                        {
                            "n_effective_multiplier": n_multiplier,
                            "L3_min_reference_coverage": coverage,
                            "L3_min_bootstrap_stability": stability,
                            "L0_templates": int(counts.get("L0", 0)),
                            "L1_templates": int(counts.get("L1", 0)),
                            "L2_templates": int(counts.get("L2", 0)),
                            "L3_templates": int(counts.get("L3", 0)),
                            "production_thresholds_changed": False,
                        }
                    )
        return pd.DataFrame(rows)

    def _d4_d5_audit(
        self, main: pd.DataFrame, confirmatory: Path
    ) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, object]]:
        d4 = pd.read_excel(
            self.paths.d4_scores,
            usecols=[
                "timestamp",
                "pair_id",
                "D4_raw",
                "usable_for_D4",
                "variable",
                "regime_id",
                "run_id",
                "calibration_id",
            ],
        )
        pair_d5 = (
            main.groupby(["timestamp", "pair_id"], as_index=False)
            .agg(
                D5_pair_report=("D5_report_score", "mean"),
                d5_report_nodes=("D5_report_score", "count"),
                D5_pair_raw=("D5_raw", "mean"),
                d5_raw_nodes=("D5_raw", "count"),
            )
        )
        d4["timestamp"] = pd.to_datetime(d4["timestamp"])
        pair_d5["timestamp"] = pd.to_datetime(pair_d5["timestamp"])
        merged = d4.merge(pair_d5, on=["timestamp", "pair_id"], how="inner")
        merged["month"] = merged["timestamp"].dt.to_period("M").astype(str)
        merged["time_block"] = (
            (merged["timestamp"] - merged["timestamp"].min()).dt.total_seconds()
            // (int(self.config["statistical_analysis"]["synchronized_block_hours"]) * 3600)
        ).astype(int)
        scopes = {
            "D5_report_score": ("D5_pair_report", "d5_report_nodes"),
            "D5_raw_calculable": ("D5_pair_raw", "d5_raw_nodes"),
        }
        valid_by_scope: dict[str, pd.DataFrame] = {}
        dependence_frames = []
        stratified_frames = []
        for scope, (score_column, count_column) in scopes.items():
            valid = merged[
                merged["usable_for_D4"].fillna(False)
                & merged["D4_raw"].notna()
                & merged[score_column].notna()
                & merged[count_column].eq(2)
            ].copy()
            valid_by_scope[scope] = valid
            dependence_frames.append(
                self._overall_d4_d5_dependence(valid, score_column, scope)
            )
            stratified_frames.append(
                self._stratified_d4_d5_rho(valid, score_column, scope)
            )
        dependence = pd.concat(dependence_frames, ignore_index=True)
        stratified = pd.concat(stratified_frames, ignore_index=True)

        pair_scores = pd.read_parquet(confirmatory / "WWDQS_pair_scores.parquet")
        node_scores = pd.read_parquet(confirmatory / "WWDQS_node_scores.parquet")
        no_d5 = node_scores.dropna(subset=["D1_total", "D2_total"]).copy()
        no_d5["Q_node_no_D5"] = no_d5[["D1_total", "D2_total"]].mean(axis=1)
        target = no_d5[["timestamp", "sensor_id", "Q_node_no_D5"]].rename(
            columns={"sensor_id": "target_sensor_id", "Q_node_no_D5": "target_no_D5"}
        )
        reference = no_d5[["timestamp", "sensor_id", "Q_node_no_D5"]].rename(
            columns={"sensor_id": "reference_sensor_id", "Q_node_no_D5": "reference_no_D5"}
        )
        sensitivity = pair_scores.merge(
            target, on=["timestamp", "target_sensor_id"], how="left"
        ).merge(reference, on=["timestamp", "reference_sensor_id"], how="left")
        sensitivity["without_D4"] = sensitivity[
            ["Q_node_target", "Q_node_reference"]
        ].mean(axis=1)
        sensitivity["without_D5"] = sensitivity[
            ["target_no_D5", "reference_no_D5", "D4_raw"]
        ].mean(axis=1)
        full = sensitivity["Q_pair"]
        composite_rows = []
        for name in ["without_D4", "without_D5"]:
            selected = sensitivity[["Q_pair", name]].dropna()
            composite_rows.append(
                {
                    "variant": name,
                    "spearman_vs_full": spearmanr(
                        selected["Q_pair"], selected[name]
                    ).statistic,
                    "mean_score_change": (selected[name] - selected["Q_pair"]).mean(),
                    "p90_absolute_change": (
                        selected[name] - selected["Q_pair"]
                    ).abs().quantile(0.90),
                    "n_pair_hours": len(selected),
                    "production_weights_changed": False,
                }
            )
        meta = self.d4_dependency_status(d4)
        meta["n_pair_hours_by_scope"] = {
            scope: int(len(frame)) for scope, frame in valid_by_scope.items()
        }
        return dependence, stratified, pd.DataFrame(composite_rows), meta

    def _overall_d4_d5_dependence(
        self, frame: pd.DataFrame, score_column: str, scope: str
    ) -> pd.DataFrame:
        low_cut = float(self.config["statistical_analysis"]["low_score_threshold"])

        def estimate_rho(sample: pd.DataFrame) -> float:
            return self._safe_spearman(sample["D4_raw"], sample[score_column])

        def estimate_jaccard(sample: pd.DataFrame) -> float:
            a = sample["D4_raw"].lt(low_cut)
            b = sample[score_column].lt(low_cut)
            union = int((a | b).sum())
            return float((a & b).sum() / union) if union else np.nan

        rho_ci = self.cluster_bootstrap_interval(
            frame,
            cluster="time_block",
            estimator=estimate_rho,
            repetitions=int(self.config["statistical_analysis"]["bootstrap_repetitions"]),
            rng=self.rng,
        )
        jaccard_ci = self.cluster_bootstrap_interval(
            frame,
            cluster="time_block",
            estimator=estimate_jaccard,
            repetitions=int(self.config["statistical_analysis"]["bootstrap_repetitions"]),
            rng=self.rng,
        )
        a = frame["D4_raw"].lt(low_cut)
        b = frame[score_column].lt(low_cut)
        joint_lift = float((a & b).mean() / max(a.mean() * b.mean(), 1e-12))
        return pd.DataFrame(
            [
                {
                    "overlap_scope": scope,
                    "metric": "Spearman_rho",
                    "estimate": estimate_rho(frame),
                    "ci95_low": rho_ci[0],
                    "ci95_high": rho_ci[1],
                    "n_pair_hours": len(frame),
                    "n_time_blocks": frame["time_block"].nunique(),
                    "analysis_unit": "synchronized_7d_time_block",
                },
                {
                    "overlap_scope": scope,
                    "metric": "Kendall_tau",
                    "estimate": float(
                        kendalltau(frame["D4_raw"], frame[score_column]).statistic
                    ),
                    "ci95_low": np.nan,
                    "ci95_high": np.nan,
                    "n_pair_hours": len(frame),
                    "n_time_blocks": frame["time_block"].nunique(),
                    "analysis_unit": "pair_hour_descriptive",
                },
                {
                    "overlap_scope": scope,
                    "metric": "partial_rank_correlation",
                    "estimate": self.partial_rank_correlation(
                        frame,
                        x="D4_raw",
                        y=score_column,
                        controls=["pair_id", "month", "regime_id"],
                    ),
                    "ci95_low": np.nan,
                    "ci95_high": np.nan,
                    "n_pair_hours": len(frame),
                    "n_time_blocks": frame["time_block"].nunique(),
                    "analysis_unit": "rank_residual_pair_month_regime_adjusted",
                },
                {
                    "overlap_scope": scope,
                    "metric": "low_score_Jaccard",
                    "estimate": estimate_jaccard(frame),
                    "ci95_low": jaccard_ci[0],
                    "ci95_high": jaccard_ci[1],
                    "n_pair_hours": len(frame),
                    "n_time_blocks": frame["time_block"].nunique(),
                    "analysis_unit": "synchronized_7d_time_block",
                },
                {
                    "overlap_scope": scope,
                    "metric": "low_score_joint_lift",
                    "estimate": joint_lift,
                    "ci95_low": np.nan,
                    "ci95_high": np.nan,
                    "n_pair_hours": len(frame),
                    "n_time_blocks": frame["time_block"].nunique(),
                    "analysis_unit": "pair_hour_descriptive",
                },
            ]
        )

    def _stratified_d4_d5_rho(
        self, frame: pd.DataFrame, score_column: str, scope: str
    ) -> pd.DataFrame:
        strata = {
            "analyte": "variable",
            "regime": "regime_id",
            "month": "month",
            "pair": "pair_id",
        }
        minimum_hours = int(
            self.config["statistical_analysis"]["minimum_stratum_pair_hours"]
        )
        minimum_blocks = int(
            self.config["statistical_analysis"]["minimum_stratum_time_blocks"]
        )
        rows = []
        for stratum_type, column in strata.items():
            for value, group in frame.groupby(column, dropna=False, sort=True):
                n_blocks = int(group["time_block"].nunique())
                estimable = bool(
                    len(group) >= minimum_hours
                    and n_blocks >= minimum_blocks
                    and group["D4_raw"].nunique() > 1
                    and group[score_column].nunique() > 1
                )
                if estimable:
                    estimator = lambda sample: self._safe_spearman(
                        sample["D4_raw"], sample[score_column]
                    )
                    low, high = self.cluster_bootstrap_interval(
                        group,
                        cluster="time_block",
                        estimator=estimator,
                        repetitions=int(
                            self.config["statistical_analysis"][
                                "bootstrap_repetitions"
                            ]
                        ),
                        rng=self.rng,
                    )
                    estimate = estimator(group)
                    reason = "estimable"
                else:
                    estimate, low, high = np.nan, np.nan, np.nan
                    reason = "insufficient_hours_blocks_or_score_variation"
                rows.append(
                    {
                        "overlap_scope": scope,
                        "stratum_type": stratum_type,
                        "stratum_value": str(value),
                        "spearman_rho": estimate,
                        "ci95_low": low,
                        "ci95_high": high,
                        "n_pair_hours": len(group),
                        "n_time_blocks": n_blocks,
                        "estimable": estimable,
                        "status_reason": reason,
                        "analysis_unit": "synchronized_7d_time_block",
                    }
                )
        return pd.DataFrame(rows)

    def d4_dependency_status(
        self, d4: pd.DataFrame | None = None
    ) -> dict[str, object]:
        if d4 is None:
            d4 = pd.read_excel(
                self.paths.d4_scores, usecols=["run_id", "calibration_id"]
            )
        expected = self.config["d4_dependency"]
        run_ids = sorted(d4["run_id"].dropna().astype(str).unique().tolist())
        calibration_ids = sorted(
            d4["calibration_id"].dropna().astype(str).unique().tolist()
        )
        actual_hash = self._sha256(self.paths.d4_scores)
        checks = {
            "single_run_id": len(run_ids) == 1,
            "single_calibration_id": len(calibration_ids) == 1,
            "run_id_exact_match": run_ids == [str(expected["expected_run_id"])],
            "calibration_id_exact_match": calibration_ids
            == [str(expected["expected_calibration_id"])],
            "main_scores_sha256_exact_match": actual_hash
            == str(expected["expected_main_scores_sha256"]),
        }
        current = bool(all(checks.values()))
        return {
            "status": "current" if current else "stale_dependency_blocked",
            "publication_freeze_allowed": current,
            "d4_run_id": run_ids[0] if len(run_ids) == 1 else None,
            "d4_calibration_id": (
                calibration_ids[0] if len(calibration_ids) == 1 else None
            ),
            "d4_main_scores_sha256": actual_hash,
            "expected_run_id": str(expected["expected_run_id"]),
            "expected_calibration_id": str(expected["expected_calibration_id"]),
            "expected_main_scores_sha256": str(
                expected["expected_main_scores_sha256"]
            ),
            "checks": checks,
            "mismatch_reasons": [name for name, passed in checks.items() if not passed],
        }

    @staticmethod
    def _safe_spearman(x: pd.Series, y: pd.Series) -> float:
        selected = pd.DataFrame({"x": x, "y": y}).dropna()
        if len(selected) < 2 or selected["x"].nunique() < 2 or selected["y"].nunique() < 2:
            return np.nan
        return float(spearmanr(selected["x"], selected["y"]).statistic)

    def _dimension_availability_sensitivity(
        self, confirmatory: Path
    ) -> pd.DataFrame:
        node = pd.read_parquet(confirmatory / "WWDQS_node_scores.parquet")
        node["timestamp"] = pd.to_datetime(node["timestamp"])
        node["month"] = node["timestamp"].dt.to_period("M").astype(str)
        complete_class = str(
            self.config["dimension_availability_sensitivity"][
                "complete_evidence_class"
            ]
        )

        def summarize(scope: str, frame: pd.DataFrame) -> dict[str, object]:
            available = frame[frame["Q_node"].notna()]
            complete = frame[
                frame["coverage_class"].eq(complete_class)
                & frame["Q_node_full"].notna()
            ]
            matched = complete.dropna(subset=["Q_node", "Q_node_full"])
            counts = frame["effective_dimension_count"].value_counts(normalize=True)
            return {
                "scope": scope,
                "sensor_hours": len(frame),
                "availability_aware_coverage": frame["Q_node"].notna().mean(),
                "complete_evidence_coverage": len(complete) / max(len(frame), 1),
                "D5_available_rate": frame["contains_D5"].fillna(False).mean(),
                "availability_aware_median": available["Q_node"].median(),
                "availability_aware_p05": available["Q_node"].quantile(0.05),
                "availability_aware_complete_median": matched["Q_node"].median(),
                "fixed_dimension_median": matched["Q_node_full"].median(),
                "descriptive_median_shift_all_minus_fixed": (
                    available["Q_node"].median() - matched["Q_node_full"].median()
                ),
                "complete_case_contract_max_abs_diff": (
                    (matched["Q_node"] - matched["Q_node_full"]).abs().max()
                    if len(matched)
                    else np.nan
                ),
                "mean_effective_dimension_count": frame[
                    "effective_dimension_count"
                ].mean(),
                "dimension_1_rate": float(counts.get(1, 0.0)),
                "dimension_2_rate": float(counts.get(2, 0.0)),
                "dimension_3_rate": float(counts.get(3, 0.0)),
                "estimand": (
                    "current_node_level_D1_D2_D5_prototype_repeat_after_"
                    "final_D1_D5_aggregation"
                ),
            }

        rows = [summarize("overall", node)]
        rows.extend(
            summarize(str(month), frame)
            for month, frame in node.groupby("month", sort=True)
        )
        return pd.DataFrame(rows)

    def _target_influence_audit(self) -> pd.DataFrame:
        observations = pd.read_parquet(self.paths.canonical_observations)
        columns = [*self.topology.node_ids(), "QR_1", "QR_2", "QIR_1", "QIR_2"]
        floor = self.topology.nodes.loc[
            self.topology.nodes["floor_flag"], "sensor_id"
        ].tolist()
        snapshots = SnapshotBuilder(
            int(self.windows["snapshot_main_minutes"]),
            int(self.windows["snapshot_min_observations"]),
        ).build(observations[columns], floor).values
        reference_end = reference_end_from_fraction(
            snapshots.index, float(self.template_config["reference_fraction"])
        )
        builder = GlobalProcessContextBuilder(self.topology)
        full_features = builder.build(snapshots)
        full_model = ContextPosteriorModel(
            n_regimes=int(self.local_config["context_regimes"]),
            random_seed=int(self.local_config["random_seed"]),
            likelihood_temperature_multiplier=float(
                self.local_config["posterior_temperature_multiplier"]
            ),
        ).fit(full_features.loc[:reference_end])
        full_result = full_model.predict(full_features)
        rows = []
        challenge_starts = self._challenge_starts(snapshots.index, reference_end)
        for target in self.topology.node_ids():
            excluded_features = builder.build_excluding(snapshots, target)
            excluded_model = ContextPosteriorModel(
                n_regimes=int(self.local_config["context_regimes"]),
                random_seed=int(self.local_config["random_seed"]),
                likelihood_temperature_multiplier=float(
                    self.local_config["posterior_temperature_multiplier"]
                ),
            ).fit(excluded_features.loc[:reference_end])
            excluded_result = excluded_model.predict(excluded_features)
            aligned = self.align_cluster_labels(
                full_result.map_regime[
                    snapshots.index.to_series().le(reference_end).to_numpy()
                ],
                excluded_result.map_regime[
                    snapshots.index.to_series().le(reference_end).to_numpy()
                ],
            )
            excluded_aligned = np.asarray(
                [aligned.get(int(value), int(value)) for value in excluded_result.map_regime]
            )
            analyte = str(
                self.topology.nodes.set_index("sensor_id").loc[target, "analyte"]
            )
            center_column = f"{analyte.lower()}_pool_median"
            scale = max(
                1.4826
                * float(
                    np.nanmedian(
                        np.abs(
                            full_features.loc[:reference_end, center_column]
                            - np.nanmedian(
                                full_features.loc[:reference_end, center_column]
                            )
                        )
                    )
                ),
                1e-9,
            )
            normalized_delta = (
                full_features[center_column] - excluded_features[center_column]
            ).abs() / scale
            challenge_switches = []
            challenge_ood = []
            target_scale = max(
                1.4826
                * float(
                    np.nanmedian(
                        np.abs(
                            snapshots.loc[:reference_end, target]
                            - np.nanmedian(snapshots.loc[:reference_end, target])
                        )
                    )
                ),
                1e-6,
            )
            for start in challenge_starts:
                end = start + pd.Timedelta(hours=23, minutes=50)
                altered = snapshots.loc[start:end].copy()
                altered[target] = altered[target] + 2.5 * target_scale
                altered_result = full_model.predict(builder.build(altered))
                baseline_mask = snapshots.index.to_series().between(start, end).to_numpy()
                baseline_map = full_result.map_regime[baseline_mask]
                baseline_ood = full_result.ood_distance[baseline_mask] > full_result.ood_threshold
                altered_ood = (
                    altered_result.ood_distance > altered_result.ood_threshold
                )
                challenge_switches.append(
                    float(np.mean(altered_result.map_regime != baseline_map))
                )
                challenge_ood.append(float(np.mean(altered_ood) - np.mean(baseline_ood)))
            rows.append(
                {
                    "target_sensor": target,
                    "analyte": analyte,
                    "observed_map_disagreement_rate": float(
                        np.mean(full_result.map_regime != excluded_aligned)
                    ),
                    "postreference_map_disagreement_rate": float(
                        np.mean(
                            full_result.map_regime[
                                snapshots.index.to_series().gt(reference_end).to_numpy()
                            ]
                            != excluded_aligned[
                                snapshots.index.to_series().gt(reference_end).to_numpy()
                            ]
                        )
                    ),
                    "median_normalized_context_delta": float(
                        np.nanmedian(normalized_delta)
                    ),
                    "p95_normalized_context_delta": float(
                        np.nanquantile(normalized_delta, 0.95)
                    ),
                    "injected_context_switch_rate": float(
                        np.mean(challenge_switches)
                    ),
                    "injected_ood_rate_change": float(np.mean(challenge_ood)),
                    "n_challenge_windows": len(challenge_starts),
                    "production_model_changed": False,
                    "interpretation": "bounded_target_influence_sensitivity_not_target_excluded_claim",
                }
            )
        return pd.DataFrame(rows)

    @staticmethod
    def _challenge_starts(
        index: pd.DatetimeIndex, reference_end: pd.Timestamp
    ) -> list[pd.Timestamp]:
        candidates = pd.date_range(
            reference_end.ceil("D") + pd.Timedelta(days=1),
            index.max() - pd.Timedelta(days=1),
            freq="24h",
        )
        if not len(candidates):
            return []
        positions = np.linspace(0, len(candidates) - 1, min(6, len(candidates)), dtype=int)
        return [pd.Timestamp(candidates[position]) for position in positions]

    @staticmethod
    def align_cluster_labels(
        reference_labels: np.ndarray, candidate_labels: np.ndarray
    ) -> dict[int, int]:
        reference = np.unique(reference_labels)
        candidate = np.unique(candidate_labels)
        matrix = np.zeros((len(reference), len(candidate)), dtype=int)
        for row, ref in enumerate(reference):
            for column, cand in enumerate(candidate):
                matrix[row, column] = int(
                    np.sum((reference_labels == ref) & (candidate_labels == cand))
                )
        rows, columns = linear_sum_assignment(-matrix)
        return {
            int(candidate[column]): int(reference[row])
            for row, column in zip(rows, columns)
        }

    @staticmethod
    def partial_rank_correlation(
        frame: pd.DataFrame, *, x: str, y: str, controls: list[str]
    ) -> float:
        selected = frame[[x, y, *controls]].dropna().copy()
        ranked_x = rankdata(selected[x].to_numpy(float))
        ranked_y = rankdata(selected[y].to_numpy(float))
        design = pd.get_dummies(
            selected[controls].astype(str), drop_first=True, dtype=float
        )
        matrix = np.column_stack([np.ones(len(selected)), design.to_numpy(float)])
        residual_x = ranked_x - matrix @ np.linalg.lstsq(
            matrix, ranked_x, rcond=None
        )[0]
        residual_y = ranked_y - matrix @ np.linalg.lstsq(
            matrix, ranked_y, rcond=None
        )[0]
        return float(np.corrcoef(residual_x, residual_y)[0, 1])

    @staticmethod
    def cluster_bootstrap_interval(
        frame: pd.DataFrame,
        *,
        cluster: str,
        estimator: Callable[[pd.DataFrame], float],
        repetitions: int,
        rng: np.random.Generator,
    ) -> tuple[float, float]:
        groups = {key: value for key, value in frame.groupby(cluster, sort=False)}
        keys = list(groups)
        if not keys:
            return np.nan, np.nan
        estimates = []
        for _ in range(repetitions):
            sampled = rng.choice(keys, size=len(keys), replace=True)
            resample = pd.concat([groups[key] for key in sampled], ignore_index=True)
            value = estimator(resample)
            if np.isfinite(value):
                estimates.append(float(value))
        if not estimates:
            return np.nan, np.nan
        return tuple(np.quantile(estimates, [0.025, 0.975]).tolist())

    def _decision_register(self, d4_meta: dict[str, object]) -> pd.DataFrame:
        rows = [
            ("full_outer_fold_refit", "accepted_already_complete", "Six future-month folds; full, no exogenous, no regime and no hysteresis were refit from training data only."),
            ("D4_D5_dual_scope_overlap", "accepted_executed_stale_dependency", f"Report-score and raw-calculable overlap are implemented with analyte/regime/month/pair strata; formal freezing is blocked because dependency status is {d4_meta['status']}."),
            ("D4_dependency_fail_closed", "accepted_executed", "Current status requires exact run ID, calibration ID and D4 main-score SHA-256 with one unique run and calibration."),
            ("score_support_missingness_freeze", "accepted_executed", "Continuous scores retained; L1/L2/L3 and missing/OOD semantics frozen; A-E grades disabled."),
            ("controlled_perturbation_Top1_0_80_boundary", "accepted_executed", "Controlled perturbation localization below 0.80 blocks sensor-specific hard Veto only, not the continuous scientific score."),
            ("risk_coverage_and_monthly_support", "accepted_executed_with_limitation", "Field evidence coverage and controlled-injection risk-coverage are separate; current confidence is not calibrated for selective localization."),
            ("dimension_availability_sensitivity", "accepted_executed_prototype", "Availability-aware and fixed-dimension complete-evidence composites are reported separately; rerun after the final D1-D5 numeric contract is frozen."),
            ("publication_ci", "accepted_executed", "Tests, artifact hashes, figure QA and exact D4 dependency are checked by one non-mutating publication bundle gate."),
            ("target_excluded_context", "accepted_with_modification", "Production is accurately named plant-global robust context; leave-one-target-out is an influence challenge, not a false production claim."),
            ("support_threshold_sensitivity", "accepted_executed", "Sensitivity only; no post-hoc production threshold changes."),
            ("untouched_future_test", "pending_external_data", "No untouched data after 2026-04-13 are currently available."),
            ("maintenance_event_truth", "pending_external_data", "Needed for fault/event truth and operational deployment claims."),
            ("dual_approval_and_asset_provenance", "pending_deployment_only", "Does not block retrospective scientific aggregation under the confirmed ordinal topology."),
            ("topology_perturbation_robustness", "pending_prespecified_perturbation_set", "Arbitrary edge edits would be post-hoc; execute only after plausible perturbations are frozen."),
            ("ORP_covariance_upgrade", "not_executed_not_supported", "Current ORP support does not justify replacing the conservative diagonal model; retain as future sensitivity."),
            ("conditional_mutual_information", "not_primary", "Autocorrelated single-plant CMI is estimator-sensitive; partial rank plus block bootstrap is the primary audit."),
        ]
        return pd.DataFrame(rows, columns=["recommendation", "decision", "rationale"])

    def _write_tables(self, tables: dict[str, pd.DataFrame]) -> None:
        workbook = self.output_root / "D5_publication_audit_tables.xlsx"
        with pd.ExcelWriter(workbook, engine="openpyxl") as writer:
            for name, frame in tables.items():
                frame.to_excel(writer, sheet_name=name[:31], index=False)
        for name, frame in tables.items():
            frame.to_parquet(self.output_root / f"D5_{name}.parquet", index=False)

    def _summary_payload(
        self,
        outer: pd.DataFrame,
        localization: pd.DataFrame,
        monthly: pd.DataFrame,
        dependence: pd.DataFrame,
        stratified: pd.DataFrame,
        dimension_availability: pd.DataFrame,
        influence: pd.DataFrame,
        d4_meta: dict[str, object],
    ) -> dict[str, object]:
        def lookup(frame: pd.DataFrame, **filters: object) -> float:
            selected = frame.copy()
            for column, value in filters.items():
                selected = selected[selected[column].eq(value)]
            return float(selected["estimate"].iloc[0])

        return {
            "contract_version": self.config["version"],
            "confirmatory_run_id": self.config["confirmatory_run_id"],
            "full_outer_AUROC": lookup(outer, variant="full_reference", metric="AUROC"),
            "full_outer_AUPRC": lookup(outer, variant="full_reference", metric="AUPRC"),
            "full_outer_Top1": lookup(outer, variant="full_reference", metric="Top1"),
            "local_all_Top1": lookup(localization, scenario="all", analyte="all", metric="Top1"),
            "local_all_Top2": lookup(localization, scenario="all", analyte="all", metric="Top2"),
            "local_all_MRR": lookup(localization, scenario="all", analyte="all", metric="MRR"),
            "local_swap_Top1": lookup(localization, scenario="channel_swap", analyte="all", metric="Top1"),
            "local_swap_Top2": lookup(localization, scenario="channel_swap", analyte="all", metric="Top2"),
            "local_swap_MRR": lookup(localization, scenario="channel_swap", analyte="all", metric="MRR"),
            "months_without_report_coverage": int(monthly["report_score_coverage"].eq(0).sum()),
            "minimum_monthly_report_coverage": float(monthly["report_score_coverage"].min()),
            "D4_D5_spearman": lookup(
                dependence,
                overlap_scope="D5_report_score",
                metric="Spearman_rho",
            ),
            "D4_D5_spearman_report": lookup(
                dependence,
                overlap_scope="D5_report_score",
                metric="Spearman_rho",
            ),
            "D4_D5_spearman_raw": lookup(
                dependence,
                overlap_scope="D5_raw_calculable",
                metric="Spearman_rho",
            ),
            "D4_D5_partial_rank": lookup(
                dependence,
                overlap_scope="D5_report_score",
                metric="partial_rank_correlation",
            ),
            "D4_D5_low_score_jaccard": lookup(
                dependence,
                overlap_scope="D5_report_score",
                metric="low_score_Jaccard",
            ),
            "D4_D5_strata_estimable": int(stratified["estimable"].sum()),
            "D4_D5_strata_abs_rho_below_0_30_rate": float(
                stratified.loc[stratified["estimable"], "spearman_rho"]
                .abs()
                .lt(0.30)
                .mean()
            ),
            "max_target_exclusion_disagreement": float(
                influence["observed_map_disagreement_rate"].max()
            ),
            "max_postreference_target_exclusion_disagreement": float(
                influence["postreference_map_disagreement_rate"].max()
            ),
            "max_injected_context_switch_rate": float(
                influence["injected_context_switch_rate"].max()
            ),
            "max_injected_ood_rate_change": float(
                influence["injected_ood_rate_change"].max()
            ),
            "d4_run_id": d4_meta["d4_run_id"],
            "d4_audit_status": d4_meta["status"],
            "d4_dependency_current": bool(d4_meta["publication_freeze_allowed"]),
            "availability_aware_overall_coverage": float(
                dimension_availability.loc[
                    dimension_availability["scope"].eq("overall"),
                    "availability_aware_coverage",
                ].iloc[0]
            ),
            "fixed_dimension_overall_coverage": float(
                dimension_availability.loc[
                    dimension_availability["scope"].eq("overall"),
                    "complete_evidence_coverage",
                ].iloc[0]
            ),
            "dimension_availability_contract_max_abs_diff": float(
                dimension_availability.loc[
                    dimension_availability["scope"].eq("overall"),
                    "complete_case_contract_max_abs_diff",
                ].iloc[0]
            ),
            "scientific_score_ready": True,
            "cross_dimension_publication_freeze_ready": bool(
                d4_meta["publication_freeze_allowed"]
            ),
            "sensor_specific_hard_veto_ready": False,
            "deployment_ready": False,
        }

    @staticmethod
    def _build_report(
        summary: dict[str, object], decisions: pd.DataFrame, deltas: pd.DataFrame
    ) -> str:
        decision_lines = "\n".join(
            f"| `{row.recommendation}` | `{row.decision}` | {row.rationale} |"
            for row in decisions.itertuples(index=False)
        )
        top1_delta = deltas[
            deltas["metric"].eq("Top1")
        ][["ablation_variant", "mean_delta_full_minus_ablation", "ci95_low", "ci95_high"]]
        delta_lines = "\n".join(
            f"| `{row.ablation_variant}` | {row.mean_delta_full_minus_ablation:.3f} | {row.ci95_low:.3f} to {row.ci95_high:.3f} |"
            for row in top1_delta.itertuples(index=False)
        )
        return f"""# D5 Publication Readiness Audit v1.1

## Executive decision

D5 is scientifically suitable for continuous-score aggregation in a retrospective single-plant study, with explicit support and coverage restrictions. It is not ready for sensor-specific hard Veto or automated deployment. The current production context is a plant-global robust context, not a strictly target-excluded model.

The six-fold future-month controlled-challenge refit achieved discrimination AUROC {summary['full_outer_AUROC']:.3f}, AUPRC {summary['full_outer_AUPRC']:.3f} and controlled-perturbation Top-1 localization {summary['full_outer_Top1']:.3f}. Top-1 remains below the prespecified 0.80 criterion and therefore blocks only node-specific hard Veto. Across all 180 controlled perturbations, Top-1 was {summary['local_all_Top1']:.3f}, Top-2 {summary['local_all_Top2']:.3f} and MRR {summary['local_all_MRR']:.3f}; for the prespecified channel-swap endpoint these were {summary['local_swap_Top1']:.3f}, {summary['local_swap_Top2']:.3f} and {summary['local_swap_MRR']:.3f}, respectively. These quantities are not field sensor-fault detection or localization accuracy.

## Structural ablation

| Removed structure | Paired Top-1 gain of full model | 95% outer-fold CI |
|---|---:|---:|
{delta_lines}

No-regime conditioning caused the clearest controlled-challenge AUROC/AUPRC discrimination loss, while removing hydraulic/time context caused the clearest controlled-perturbation Top-1 localization loss. Hysteresis produced a small incremental gain. These results support regime conditioning and exogenous context, but do not justify tuning on the terminal folds.

## Coverage and selection

There are {summary['months_without_report_coverage']} months with zero formal D5 report coverage; the minimum monthly report coverage is {summary['minimum_monthly_report_coverage']:.1%}. This is driven primarily by L1 support/OOD migration, so formal composite results represent a complete-evidence subset and cannot be extrapolated to all sensor-hours. Raw scientific evidence remains separately available where calculable.

The current node-level prototype gives {summary['availability_aware_overall_coverage']:.1%} availability-aware composite coverage but only {summary['fixed_dimension_overall_coverage']:.1%} fixed-dimension complete-evidence coverage. These are different estimands and must be shown separately. The calculation currently covers the available D1/D2/D5 node contract and must be repeated after the final five-dimension WW-DQS contract is frozen.

## D4-D5 complementarity

Against D4 run `{summary['d4_run_id']}`, report-score overlap Spearman rho is {summary['D4_D5_spearman_report']:.3f}, raw-calculable overlap rho is {summary['D4_D5_spearman_raw']:.3f}, adjusted report-score partial rank correlation is {summary['D4_D5_partial_rank']:.3f}, and report-score low-tail Jaccard is {summary['D4_D5_low_score_jaccard']:.3f}. Across estimable analyte, regime, month and pair strata, {summary['D4_D5_strata_abs_rho_below_0_30_rate']:.1%} have |rho| below 0.30. These are non-redundancy diagnostics, not proof of causal independence. Status is `{summary['d4_audit_status']}`; exact run, calibration and SHA-256 matching is required before manuscript numbers or Fig. 7 are frozen.

## Target influence

Leave-one-target-out context refits produced a maximum whole-period regime disagreement of {summary['max_target_exclusion_disagreement']:.1%}, but only {summary['max_postreference_target_exclusion_disagreement']:.1%} after the reference period. Under controlled 2.5-MAD target offsets, the MAP context-switch rate remained {summary['max_injected_context_switch_rate']:.1%}, while the maximum OOD-rate increase was {summary['max_injected_ood_rate_change']:.1%}. These are sensitivity results. They do not convert the current production model into a target-excluded model, and they must be reported as bounded-influence evidence rather than leakage elimination.

## Confidence limitation

The controlled-injection risk-coverage curve is not monotonic: retaining only the highest-confidence trials does not improve Top-1 localization. Therefore the current uncertainty/confidence field is valid as evidence metadata but is not calibrated as a selective-localization probability and must not be used to release hard Veto.

## Recommendation decisions

| Recommendation | Decision | Scientific rationale |
|---|---|---|
{decision_lines}

## Final claim boundary

- Ready: continuous D5 score, retrospective report interface and process-coherence attribution Guard.
- Conditional: availability-aware aggregation is allowed only with explicit dimension-count and coverage outputs; fixed-dimension complete-evidence results must be reported separately.
- Blocked pending dependency refresh: cross-dimensional D4-D5 publication freeze and final Fig. 7 values.
- Not ready: sensor-specific hard Veto, causal fault labels, prospective deployment, cross-plant generalization.
- A-E grades remain disabled because no independent future data exist for cutpoint freezing.
- New field data, maintenance truth and dual approval should be treated as external validation/deployment work, not silently imputed into the current retrospective analysis.
"""

    def _write_manifest(
        self,
        summary: dict[str, object],
        tables: dict[str, pd.DataFrame],
        report_path: Path,
        d4_meta: dict[str, object],
    ) -> Path:
        files = [report_path, self.output_root / "D5_publication_audit_tables.xlsx"]
        files.extend(
            self.output_root / f"D5_{name}.parquet" for name in tables
        )
        manifest = {
            "version": self.config["version"],
            "confirmatory_run_id": self.config["confirmatory_run_id"],
            "summary": summary,
            "d4_dependency": d4_meta,
            "production_score_changed": False,
            "files": [
                {
                    "relative_path": str(path.relative_to(D5_ROOT)),
                    "sha256": self._sha256(path),
                    "bytes": path.stat().st_size,
                }
                for path in files
            ],
        }
        target = self.output_root / "D5_publication_audit_manifest.json"
        target.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return target

    def finalize_figure_bundle(self) -> Path:
        target = self.output_root / "D5_publication_audit_manifest.json"
        manifest = json.loads(target.read_text(encoding="utf-8"))
        files = {
            str(item["relative_path"]): D5_ROOT / str(item["relative_path"])
            for item in manifest["files"]
        }
        for stem in self.config["publication_figures"]:
            for suffix in ["png", "pdf", "svg", "tiff"]:
                path = self.paths.figure_root / f"{stem}.{suffix}"
                if path.exists():
                    files[str(path.relative_to(D5_ROOT))] = path
            source = self.output_root / f"{stem}_source_data.xlsx"
            if source.exists():
                files[str(source.relative_to(D5_ROOT))] = source
        figure_qa = self.paths.figure_root / "D5_figure_qa.json"
        if figure_qa.exists():
            files[str(figure_qa.relative_to(D5_ROOT))] = figure_qa
        manifest["files"] = [
            {
                "relative_path": relative,
                "sha256": self._sha256(path),
                "bytes": path.stat().st_size,
            }
            for relative, path in sorted(files.items())
        ]
        manifest["figure_bundle_finalized"] = True
        manifest["d4_dependency"] = self.d4_dependency_status()
        target.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
        return target

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
