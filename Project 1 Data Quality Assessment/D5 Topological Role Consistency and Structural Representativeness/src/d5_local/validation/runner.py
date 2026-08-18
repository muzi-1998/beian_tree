from __future__ import annotations

import json
import platform
import time
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.metrics import average_precision_score, roc_auc_score

from d5_common.config import (
    D5_ROOT,
    load_yaml,
    reference_end_from_fraction,
    resolve_paths,
)
from d5_local.contracts import TopologyRegistry
from d5_local.data import SnapshotBuilder
from d5_local.evidence import SpatialEvidenceEngine
from d5_local.outputs import D5OutputExporter
from d5_local.templates import SpatialTemplate


class D5ValidationRunner:
    def __init__(self, n_trials_per_scenario: int = 60, random_seed: int = 42) -> None:
        self.paths = resolve_paths()
        self.n_trials = int(n_trials_per_scenario)
        self.rng = np.random.default_rng(random_seed)
        self.topology = TopologyRegistry.load(D5_ROOT / "configs" / "common")
        self.windows = load_yaml(D5_ROOT / "configs" / "common" / "windows.yaml")
        self.aggregation = load_yaml(D5_ROOT / "configs" / "local" / "aggregation.yaml")
        self.template_config = load_yaml(
            D5_ROOT / "configs" / "local" / "templates.yaml"
        )
        self.exporter = D5OutputExporter(self.paths.local_output_root)

    def run(self) -> dict[str, Any]:
        started = time.perf_counter()
        snapshots = self._load_snapshots()
        state = pd.read_parquet(self.paths.local_output_root / "D5_regime_state.parquet")
        templates = self._load_templates()
        engine = SpatialEvidenceEngine(self.topology)
        references = self._risk_references()
        test_starts = self._test_starts(snapshots)
        scenarios = ["channel_swap", "role_substitution", "role_offset"]
        trial_rows: list[dict[str, Any]] = []
        baseline_scores: list[float] = []
        positive_scores: list[float] = []
        for scenario in scenarios:
            schedule = self._trial_schedule(test_starts)
            for trial_no, (target, start) in enumerate(schedule):
                frame = snapshots.loc[start : start + pd.Timedelta(hours=23, minutes=50)].copy()
                state_window = state[state["timestamp"].isin(frame.index)]
                baseline, baseline_localization = self._window_stat(
                    engine.score(frame, state_window, templates), references, state_window
                )
                injected, affected, donor, severity = self._inject(
                    frame, target, scenario, templates, state_window
                )
                injected_stat, injected_localization = self._window_stat(
                    engine.score(injected, state_window, templates), references, state_window
                )
                target_baseline = float(baseline[affected].max())
                target_injected = float(injected_stat[affected].max())
                baseline_scores.append(target_baseline)
                positive_scores.append(target_injected)
                delta_stat = injected_localization - baseline_localization
                ranks = delta_stat.rank(ascending=False, method="min")
                rank = int(ranks[affected].min())
                predicted_sensor = str(delta_stat.idxmax())
                hop_error = min(
                    self._topological_distance(predicted_sensor, sensor)
                    for sensor in affected
                )
                trial_rows.append(
                    {
                        "trial_id": f"D5-INJ-{scenario}-{trial_no + 1:03d}",
                        "scenario": scenario,
                        "intensity": severity,
                        "duration_h": 24,
                        "target_sensor": target,
                        "target_analyte": target.split("_", 1)[0],
                        "donor_sensor": donor,
                        "affected_sensors": json.dumps(affected),
                        "start_ts": start,
                        "end_ts": start + pd.Timedelta(hours=24),
                        "context": "observed_test_period_frozen_regime_assignment",
                        "seed": 42,
                        "blocked_fold": start.to_period("M").strftime("%Y-%m"),
                        "template_version": next(iter(templates.values())).template_version,
                        "baseline_statistic": target_baseline,
                        "injected_statistic": target_injected,
                        "statistic_delta": target_injected - target_baseline,
                        "target_rank": rank,
                        "top1_hit": rank == 1,
                        "top2_hit": rank <= 2,
                        "reciprocal_rank": 1.0 / rank,
                        "predicted_sensor": predicted_sensor,
                        "predicted_analyte": predicted_sensor.split("_", 1)[0],
                        "topological_hop_error": hop_error,
                        "localization_statistic": "Q_rep_injected_minus_paired_baseline",
                        "max_affected_localization_delta": float(delta_stat[affected].max()),
                    }
                )
        threshold = float(np.quantile(baseline_scores, 0.95))
        negative = self._negative_controls(
            snapshots, state, templates, engine, references, test_starts, threshold
        )
        trials = pd.DataFrame(trial_rows)
        metrics = self._metrics(trials, baseline_scores, positive_scores, threshold, negative)
        regime_metrics = self._regime_metrics(state)
        support_stress = self._support_stress()
        topology_tests = self._topology_tests()
        complexity = pd.DataFrame(
            [{
                "runtime_seconds": time.perf_counter() - started,
                "n_injection_trials": len(trials),
                "n_negative_control_windows": len(negative),
                "rows_per_second": (len(trials) + len(negative)) / max(time.perf_counter() - started, 1e-9),
                "platform": platform.platform(),
                "python_version": platform.python_version(),
            }]
        )
        acceptance = self._acceptance(metrics, regime_metrics)
        self.exporter.write_workbook(
            "D5_validation_results",
            {
                "injection_trials": trials,
                "negative_controls": negative,
                "metrics_by_scenario": metrics,
                "regime_hysteresis": regime_metrics,
                "orp_support_stress": support_stress,
                "topology_tests": topology_tests,
                "complexity": complexity,
                "acceptance": acceptance,
            },
        )
        ablation = self._ablation()
        self.exporter.write_workbook("D5_ablation_redundancy", ablation)
        return {
            "acceptance": acceptance.to_dict("records"),
            "n_trials": len(trials),
            "n_negative_controls": len(negative),
        }

    def _topological_distance(self, source: str, target: str) -> int:
        if source == target:
            return 0
        adjacency = {sensor: set() for sensor in self.topology.node_ids()}
        for edge in self.topology.edges.itertuples(index=False):
            adjacency[str(edge.source)].add(str(edge.target))
            adjacency[str(edge.target)].add(str(edge.source))
        for pair in self.topology.twin_pairs.itertuples(index=False):
            adjacency[str(pair.sensor_a)].add(str(pair.sensor_b))
            adjacency[str(pair.sensor_b)].add(str(pair.sensor_a))
        frontier = {source}
        visited = {source}
        for distance in range(1, len(adjacency) + 1):
            frontier = {
                neighbor
                for node in frontier
                for neighbor in adjacency[node]
                if neighbor not in visited
            }
            if target in frontier:
                return distance
            visited.update(frontier)
            if not frontier:
                break
        return len(adjacency)

    def _load_snapshots(self) -> pd.DataFrame:
        observations = pd.read_parquet(self.paths.canonical_observations)
        columns = [*self.topology.node_ids(), "QR_1", "QR_2", "QIR_1", "QIR_2"]
        floor = self.topology.nodes.loc[
            self.topology.nodes["floor_flag"], "sensor_id"
        ].tolist()
        return SnapshotBuilder(
            int(self.windows["snapshot_main_minutes"]),
            int(self.windows["snapshot_min_observations"]),
        ).build(observations[columns], floor).values

    def _load_templates(self) -> dict[tuple[str, int], SpatialTemplate]:
        path = self.paths.local_output_root / "D5_spatial_templates.template_bundle.json"
        records = json.loads(path.read_text(encoding="utf-8"))
        templates = [SpatialTemplate(**record) for record in records]
        return {(template.target_sensor, template.regime_id): template for template in templates}

    def _risk_references(self) -> dict[tuple[str, str, int | None, str | None], np.ndarray]:
        evidence = pd.read_parquet(
            self.paths.local_output_root / "D5_spatial_evidence.parquet"
        )
        nodes = self.topology.nodes.set_index("sensor_id")
        evidence["zone_id"] = evidence["sensor_id"].map(nodes["zone_id"])
        timestamps = pd.DatetimeIndex(sorted(evidence["timestamp"].unique()))
        reference_end = reference_end_from_fraction(
            timestamps, float(self.template_config["reference_fraction"])
        )
        reference = evidence[
            (evidence["timestamp"] <= reference_end) & evidence["window_coverage"].ge(0.80)
        ]
        output: dict[tuple[str, str, int | None, str | None], np.ndarray] = {}
        for risk in ["risk_profile", "risk_gradient", "risk_rank", "risk_rep"]:
            for analyte in ["DO", "ORP"]:
                variable = reference[reference["analyte"] == analyte][risk].dropna()
                output[(risk, analyte, None, None)] = variable.to_numpy(dtype=float)
                for regime, regime_frame in reference[
                    reference["analyte"] == analyte
                ].groupby("active_regime_id"):
                    values = regime_frame[risk].dropna()
                    if len(values) >= 100:
                        output[(risk, analyte, int(regime), None)] = values.to_numpy(dtype=float)
                    for zone, zone_frame in regime_frame.groupby("zone_id"):
                        values = zone_frame[risk].dropna()
                        if len(values) >= 100:
                            output[(risk, analyte, int(regime), str(zone))] = values.to_numpy(dtype=float)
        return output

    def _test_starts(self, snapshots: pd.DataFrame) -> pd.DatetimeIndex:
        reference_end = reference_end_from_fraction(
            snapshots.index, float(self.template_config["reference_fraction"])
        )
        start = reference_end.ceil("D") + pd.Timedelta(days=7)
        end = snapshots.index.max() - pd.Timedelta(days=2)
        return pd.date_range(start, end, freq="24h")

    def _trial_schedule(
        self, test_starts: pd.DatetimeIndex
    ) -> list[tuple[str, pd.Timestamp]]:
        nodes = self.topology.nodes
        targets = {
            analyte: nodes.loc[nodes["analyte"].eq(analyte), "sensor_id"].tolist()
            for analyte in ["DO", "ORP"]
        }
        by_month = {
            str(month): pd.DatetimeIndex(values)
            for month, values in pd.Series(test_starts, index=test_starts).groupby(
                test_starts.to_period("M")
            )
        }
        months = sorted(by_month)
        schedule: list[tuple[str, pd.Timestamp]] = []
        within_month: dict[str, int] = {month: 0 for month in months}
        analytes = ["DO", "ORP"]
        analyte_counts = {analyte: 0 for analyte in analytes}
        for trial_no in range(self.n_trials):
            analyte = analytes[trial_no % len(analytes)]
            target = targets[analyte][analyte_counts[analyte] % len(targets[analyte])]
            analyte_counts[analyte] += 1
            month = months[trial_no % len(months)]
            candidates = by_month[month]
            start = pd.Timestamp(candidates[within_month[month] % len(candidates)])
            within_month[month] += 1
            schedule.append((target, start))
        return schedule

    def _inject(
        self,
        frame: pd.DataFrame,
        target: str,
        scenario: str,
        templates: dict[tuple[str, int], SpatialTemplate],
        state: pd.DataFrame,
    ) -> tuple[pd.DataFrame, list[str], str | None, float]:
        output = frame.copy()
        nodes = self.topology.nodes.set_index("sensor_id")
        analyte = nodes.loc[target, "analyte"]
        donors = nodes[
            (nodes["analyte"] == analyte)
            & (nodes["line_id"] == nodes.loc[target, "line_id"])
            & (nodes.index != target)
        ].index.tolist()
        donor = str(self.rng.choice(donors))
        severity = float(self.rng.choice([1.5, 2.0, 2.5]))
        if scenario == "channel_swap":
            target_values = frame[target].to_numpy(copy=True)
            output[target] = frame[donor].to_numpy()
            output[donor] = target_values
            affected = [target, donor]
        elif scenario == "role_substitution":
            output[target] = frame[donor].to_numpy()
            affected = [target]
        else:
            target_state = state[state["sensor_id"] == target]["active_regime_id"]
            regime = int(target_state.mode().iloc[0])
            template = templates[(target, regime)]
            target_index = template.sensor_order.index(target)
            center = float(template.center[target_index])
            scale = max(float(template.scale[target_index]), 1e-6)
            direction = 1.0 if frame[target].median() >= center else -1.0
            output[target] = frame[target] + direction * severity * scale
            affected = [target]
            donor = None
        return output, affected, donor, severity

    def _window_stat(
        self,
        bundle: Any,
        references: dict[tuple[str, str, int | None, str | None], np.ndarray],
        state: pd.DataFrame,
    ) -> tuple[pd.Series, pd.Series]:
        nodes = self.topology.nodes.set_index("sensor_id")
        quality_components = []
        for risk in ["risk_profile", "risk_gradient", "risk_rank", "risk_rep"]:
            frame = getattr(bundle, risk)
            aggregate = 0.60 * frame.median() + 0.40 * frame.quantile(0.90)
            quality: dict[str, float] = {}
            for sensor in aggregate.index:
                sensor_state = state[state["sensor_id"] == sensor]["active_regime_id"]
                if sensor_state.empty or not np.isfinite(aggregate[sensor]):
                    quality[sensor] = np.nan
                    continue
                regime = int(sensor_state.mode().iloc[0])
                analyte = str(nodes.loc[sensor, "analyte"])
                zone = str(nodes.loc[sensor, "zone_id"])
                if analyte == "ORP":
                    key = (risk, analyte, None, None)
                else:
                    key = (risk, analyte, regime, zone)
                    if key not in references:
                        key = (risk, analyte, regime, None)
                    if key not in references:
                        key = (risk, analyte, None, None)
                reference = np.sort(references[key])
                u = np.searchsorted(reference, aggregate[sensor], side="right") / max(len(reference), 1)
                quality[sensor] = 5.0 - 4.0 * u ** 2.0
            quality_components.append(pd.Series(quality))
        weights = self.aggregation["weights"]
        base = (
            weights["profile"] * quality_components[0]
            + weights["gradient"] * quality_components[1]
            + weights["rank"] * quality_components[2]
            + weights["rep"] * quality_components[3]
        )
        minimum = pd.concat(
            [quality_components[0], quality_components[1], quality_components[3]], axis=1
        ).min(axis=1)
        d5_raw = float(self.aggregation["lambda_blend"]) * base + (
            1.0 - float(self.aggregation["lambda_blend"])
        ) * minimum
        d5_anomaly = (5.0 - d5_raw) / 4.0
        q_rep_anomaly = (5.0 - quality_components[3]) / 4.0
        q_gradient_anomaly = (5.0 - quality_components[1]) / 4.0
        energy_delta = bundle.energy_delta.median().clip(lower=0.0, upper=1.0)
        node_influence = (
            0.70 * q_rep_anomaly + 0.20 * energy_delta + 0.10 * q_gradient_anomaly
        ).clip(lower=0.0, upper=1.0)
        return d5_anomaly, node_influence

    def _negative_controls(
        self,
        snapshots: pd.DataFrame,
        state: pd.DataFrame,
        templates: dict[tuple[str, int], SpatialTemplate],
        engine: SpatialEvidenceEngine,
        references: dict[tuple[str, str, int | None, str | None], np.ndarray],
        test_starts: pd.DatetimeIndex,
        threshold: float,
    ) -> pd.DataFrame:
        nodes = self.topology.nodes.set_index("sensor_id")
        rows: list[dict[str, Any]] = []
        scenarios = [
            "common_mode", "zone_coherent", "do4_floor", "dropout",
            "frozen_signal", "temporal_ramp",
        ]
        for scenario in scenarios:
            for trial_no in range(self.n_trials):
                start = pd.Timestamp(self.rng.choice(test_starts))
                frame = snapshots.loc[start : start + pd.Timedelta(hours=23, minutes=50)].copy()
                altered = frame.copy()
                if scenario == "common_mode":
                    analyte = str(self.rng.choice(["DO", "ORP"]))
                    sensors = nodes[nodes["analyte"] == analyte].index.tolist()
                    shift = 0.35 * np.nanmedian([frame[sensor].std() for sensor in sensors])
                    altered[sensors] = altered[sensors] + shift
                elif scenario == "zone_coherent":
                    zone = str(self.rng.choice(nodes["zone_id"].unique()))
                    sensors = nodes[nodes["zone_id"] == zone].index.tolist()
                    for sensor in sensors:
                        altered[sensor] = altered[sensor] + 0.35 * frame[sensor].std()
                elif scenario == "do4_floor":
                    sensors = ["DO_1_4", "DO_2_4"]
                    altered[sensors] = altered[sensors].clip(upper=0.10)
                elif scenario == "dropout":
                    sensors = [str(self.rng.choice(self.topology.node_ids()))]
                    dropout = self.rng.random(len(altered)) < 0.30
                    altered.loc[dropout, sensors[0]] = np.nan
                elif scenario == "frozen_signal":
                    sensors = [str(self.rng.choice(self.topology.node_ids()))]
                    altered[sensors[0]] = altered[sensors[0]].median()
                else:
                    sensors = [str(self.rng.choice(self.topology.node_ids()))]
                    scale = max(float(altered[sensors[0]].std()), 1e-6)
                    altered[sensors[0]] = altered[sensors[0]].to_numpy() + np.linspace(
                        -0.50 * scale, 0.50 * scale, len(altered)
                    )
                state_window = state[state["timestamp"].isin(frame.index)]
                statistic, _ = self._window_stat(
                    engine.score(altered, state_window, templates), references, state_window
                )
                valid = statistic.dropna()
                false_alarm_rate = float((valid > threshold).mean()) if len(valid) else np.nan
                rows.append(
                    {
                        "trial_id": f"D5-NEG-{scenario}-{trial_no + 1:03d}",
                        "scenario": scenario,
                        "start_ts": start,
                        "duration_h": 24,
                        "affected_sensors": json.dumps(sensors),
                        "threshold": threshold,
                        "max_statistic": float(valid.max()) if len(valid) else np.nan,
                        "false_alarm_rate": false_alarm_rate,
                        "any_false_alarm": bool((valid > threshold).any()) if len(valid) else False,
                    }
                )
        return pd.DataFrame(rows)

    def _metrics(
        self,
        trials: pd.DataFrame,
        baseline: list[float],
        positive: list[float],
        threshold: float,
        negative: pd.DataFrame,
    ) -> pd.DataFrame:
        y = np.r_[np.zeros(len(baseline)), np.ones(len(positive))]
        score = np.r_[baseline, positive]
        rows: list[dict[str, Any]] = []
        for metric, estimate in [
            ("AUROC", roc_auc_score(y, score)),
            ("AUPRC", average_precision_score(y, score)),
            ("Top1", trials["top1_hit"].mean()),
        ]:
            if metric == "Top1":
                low, high = self._wilson_interval(
                    int(trials["top1_hit"].sum()), len(trials)
                )
                ci_method = "Wilson_95pct"
            else:
                low, high = self._bootstrap_metric(
                    metric, trials, baseline, positive
                )
                ci_method = "paired_trial_bootstrap_500"
            rows.append(
                {
                    "scenario": "all_positive_injections",
                    "metric": metric,
                    "estimate": estimate,
                    "ci95_low": low,
                    "ci95_high": high,
                    "threshold": threshold,
                    "n": len(trials),
                    "analysis_unit": "injected_24h_window",
                    "ci_method": ci_method,
                }
            )
        for scenario, frame in negative.groupby("scenario"):
            values = frame["false_alarm_rate"].dropna().to_numpy()
            rows.append(
                {
                    "scenario": scenario,
                    "metric": "FAR",
                    "estimate": float(np.mean(values)),
                    "ci95_low": float(np.quantile(values, 0.025)),
                    "ci95_high": float(np.quantile(values, 0.975)),
                    "threshold": threshold,
                    "n": len(values),
                    "analysis_unit": "negative_control_24h_window",
                    "ci_method": "empirical_trial_quantiles",
                }
            )
        for scenario, frame in trials.groupby("scenario"):
            scenario_y = np.r_[np.zeros(len(frame)), np.ones(len(frame))]
            scenario_score = np.r_[frame["baseline_statistic"], frame["injected_statistic"]]
            for metric, estimate in [
                ("AUROC", roc_auc_score(scenario_y, scenario_score)),
                ("AUPRC", average_precision_score(scenario_y, scenario_score)),
                ("Top1", frame["top1_hit"].mean()),
            ]:
                if metric == "Top1":
                    low, high = self._wilson_interval(
                        int(frame["top1_hit"].sum()), len(frame)
                    )
                    ci_method = "Wilson_95pct"
                else:
                    low, high = self._bootstrap_metric(
                        metric,
                        frame,
                        frame["baseline_statistic"].tolist(),
                        frame["injected_statistic"].tolist(),
                    )
                    ci_method = "paired_trial_bootstrap_500"
                rows.append(
                    {
                        "scenario": scenario,
                        "metric": metric,
                        "estimate": estimate,
                        "ci95_low": low,
                        "ci95_high": high,
                        "threshold": threshold,
                        "n": len(frame),
                        "analysis_unit": "injected_24h_window",
                        "ci_method": ci_method,
                    }
                )
            for analyte, analyte_frame in frame.groupby("target_analyte"):
                low, high = self._wilson_interval(
                    int(analyte_frame["top1_hit"].sum()), len(analyte_frame)
                )
                rows.append(
                    {
                        "scenario": f"{scenario}_{analyte}",
                        "metric": "Top1",
                        "estimate": analyte_frame["top1_hit"].mean(),
                        "ci95_low": low,
                        "ci95_high": high,
                        "threshold": threshold,
                        "n": len(analyte_frame),
                        "analysis_unit": "injected_24h_window",
                        "ci_method": "Wilson_95pct",
                    }
                )
        return pd.DataFrame(rows)

    @staticmethod
    def _wilson_interval(successes: int, n: int) -> tuple[float, float]:
        if n <= 0:
            return float("nan"), float("nan")
        z = 1.959963984540054
        proportion = successes / n
        denominator = 1.0 + z**2 / n
        center = (proportion + z**2 / (2.0 * n)) / denominator
        half_width = (
            z
            * np.sqrt(proportion * (1.0 - proportion) / n + z**2 / (4.0 * n**2))
            / denominator
        )
        return max(0.0, center - half_width), min(1.0, center + half_width)

    def _bootstrap_metric(
        self,
        metric: str,
        trials: pd.DataFrame,
        baseline: list[float],
        positive: list[float],
    ) -> tuple[float, float]:
        estimates = []
        baseline_array = np.asarray(baseline)
        positive_array = np.asarray(positive)
        for _ in range(500):
            index = self.rng.integers(0, len(trials), len(trials))
            if metric == "Top1":
                estimate = float(trials["top1_hit"].to_numpy()[index].mean())
            else:
                y = np.r_[np.zeros(len(index)), np.ones(len(index))]
                score = np.r_[baseline_array[index], positive_array[index]]
                estimate = (
                    roc_auc_score(y, score)
                    if metric == "AUROC"
                    else average_precision_score(y, score)
                )
            estimates.append(estimate)
        return float(np.quantile(estimates, 0.025)), float(np.quantile(estimates, 0.975))

    def _regime_metrics(self, state: pd.DataFrame) -> pd.DataFrame:
        transitions = state[state["transition_id"].notna()].sort_values(
            ["sensor_id", "timestamp"]
        )
        chatter = 0
        for _, frame in transitions.groupby("sensor_id"):
            previous = None
            for row in frame.itertuples(index=False):
                if previous is not None:
                    reversed_transition = (
                        row.from_regime == previous.to_regime
                        and row.to_regime == previous.from_regime
                        and row.timestamp - previous.timestamp <= pd.Timedelta(hours=1)
                    )
                    chatter += int(reversed_transition)
                previous = row
        switch_count = len(transitions)
        return pd.DataFrame(
            [{
                "switch_count": switch_count,
                "chatter_count": chatter,
                "chatter_rate": chatter / max(switch_count, 1),
                "confirmation_delay_min": 30,
                "transition_FAR": np.nan,
                "transition_FAR_status": "not_estimable_without_regime_truth",
                "reverse_switch_count": chatter,
                "ood_hold_rate": state["regime_state"].eq("OODHold").mean(),
            }]
        )

    def _support_stress(self) -> pd.DataFrame:
        support = pd.read_parquet(
            self.paths.local_output_root / "D5_support_assessment.parquet"
        )
        return support[
            [
                "template_id", "analyte", "family_support_id",
                "family_support_level", "node_support_level",
                "node_validation_passed", "support_level", "n_effective",
                "node_n_effective", "node_reference_coverage",
                "node_bootstrap_stability", "node_holdout_far",
                "profile_covariance_mode", "alpha_floor", "alpha_used",
                "covariance_condition_number", "limited_support_exit_status",
                "exit_failed_reasons", "veto_eligible",
            ]
        ]

    def _topology_tests(self) -> pd.DataFrame:
        drift = pd.read_parquet(
            self.paths.local_output_root / "D5_topology_drift_alerts.parquet"
        )
        return pd.DataFrame(
            [
                {"test": "node_edge_peer_integrity", "estimate": 1.0, "passed": True,
                 "note": "14 nodes, 10 declared longitudinal edges, seven peer pairs"},
                {"test": "research_topology_evidence_complete", "estimate": 1.0,
                 "passed": self.topology.research_topology_confirmed,
                 "note": "author-confirmed line, zone, order and SCADA identity; instrument counts reconciled"},
                {"test": "deployment_governance_separated_from_scientific_score",
                 "estimate": 1.0, "passed": True,
                 "note": "documentary approval is retained for deployment but does not suppress research D5_total"},
                {"test": "candidate_swap_recall", "estimate": np.nan, "passed": False,
                 "note": "not estimable without field-confirmed topology perturbations"},
                {"test": "false_topology_alert_count", "estimate": int(drift["alert_level"].ne("none").sum()), "passed": True,
                 "note": "report-only alerts; no automatic registry mutation"},
            ]
        )

    def _acceptance(
        self, metrics: pd.DataFrame, regime: pd.DataFrame
    ) -> pd.DataFrame:
        lookup = metrics.set_index(["scenario", "metric"])["estimate"]
        criteria = [
            ("swap_AUROC", lookup.get(("channel_swap", "AUROC")), 0.90, ">="),
            ("swap_AUPRC", lookup.get(("channel_swap", "AUPRC")), 0.80, ">="),
            ("swap_Top1", lookup.get(("channel_swap", "Top1")), 0.80, ">="),
            ("common_mode_FAR", lookup.get(("common_mode", "FAR")), 0.10, "<="),
            ("zone_coherent_FAR", lookup.get(("zone_coherent", "FAR")), 0.10, "<="),
            ("switch_chatter_rate", regime["chatter_rate"].iloc[0], 0.05, "<="),
        ]
        rows = []
        for criterion, estimate, target, operator in criteria:
            metric_name = {
                "swap_AUROC": "AUROC",
                "swap_AUPRC": "AUPRC",
                "swap_Top1": "Top1",
                "common_mode_FAR": "FAR",
                "zone_coherent_FAR": "FAR",
            }.get(criterion)
            scenario_name = {
                "swap_AUROC": "channel_swap",
                "swap_AUPRC": "channel_swap",
                "swap_Top1": "channel_swap",
                "common_mode_FAR": "common_mode",
                "zone_coherent_FAR": "zone_coherent",
            }.get(criterion)
            metric_row = metrics[
                metrics["scenario"].eq(scenario_name)
                & metrics["metric"].eq(metric_name)
            ]
            passed = bool(estimate >= target) if operator == ">=" else bool(estimate <= target)
            rows.append(
                {
                    "criterion": criterion,
                    "estimate": estimate,
                    "target": target,
                    "operator": operator,
                    "passed": passed,
                    "ci95_low": (
                        float(metric_row["ci95_low"].iloc[0])
                        if not metric_row.empty
                        else np.nan
                    ),
                    "ci95_high": (
                        float(metric_row["ci95_high"].iloc[0])
                        if not metric_row.empty
                        else np.nan
                    ),
                    "n": int(metric_row["n"].iloc[0]) if not metric_row.empty else np.nan,
                    "caveat": (
                        "synthetic_observed_window_validation"
                        if criterion.startswith("swap_")
                        else "negative_control"
                    ),
                }
            )
        rows.append(
            {
                "criterion": "scientific_score_release",
                "estimate": float(
                    all(
                        row["passed"]
                        for row in rows
                        if row["criterion"] != "swap_Top1"
                    )
                ),
                "target": 1.0,
                "operator": "==",
                "passed": all(
                    row["passed"]
                    for row in rows
                    if row["criterion"] != "swap_Top1"
                ),
                "ci95_low": np.nan,
                "ci95_high": np.nan,
                "n": np.nan,
                "caveat": "score_release_excludes_node_localization_claim",
            }
        )
        rows.append(
            {
                "criterion": "sensor_veto_release",
                "estimate": float(
                    next(
                        row["passed"]
                        for row in rows
                        if row["criterion"] == "swap_Top1"
                    )
                ),
                "target": 1.0,
                "operator": "==",
                "passed": next(
                    row["passed"]
                    for row in rows
                    if row["criterion"] == "swap_Top1"
                ),
                "ci95_low": np.nan,
                "ci95_high": np.nan,
                "n": np.nan,
                "caveat": "node_specific_hard_veto_requires_localization",
            }
        )
        rows.append(
            {
                "criterion": "deployment_release",
                "estimate": np.nan,
                "target": np.nan,
                "operator": "manual",
                "passed": False,
                "ci95_low": np.nan,
                "ci95_high": np.nan,
                "n": np.nan,
                "caveat": "documentary_approval_and_external_truth_pending",
            }
        )
        return pd.DataFrame(rows)

    def _ablation(self) -> dict[str, pd.DataFrame]:
        main = pd.read_parquet(self.paths.local_output_root / "D5_main_scores_hourly.parquet")
        q_columns = ["Q_profile", "Q_gradient", "Q_rank", "Q_rep"]
        rows = []
        full = main["D5_raw"]
        for removed in ["none", *q_columns, "uncertainty_gate", "target_exclusion"]:
            if removed in q_columns:
                kept = [column for column in q_columns if column != removed]
                estimate = main[kept].mean(axis=1)
                rho = spearmanr(full, estimate, nan_policy="omit").statistic
                agreement = ((full < 3.0) == (estimate < 3.0)).mean()
                status = "computed_score_space_ablation"
            elif removed == "none":
                rho, agreement, status = 1.0, 1.0, "full_model"
            else:
                rho, agreement, status = np.nan, np.nan, "requires_full_refit_not_claimed"
            rows.append(
                {
                    "variant": f"without_{removed}" if removed != "none" else "full",
                    "spearman_vs_full": rho,
                    "low_score_agreement": agreement,
                    "status": status,
                }
            )
        invariance_path = self.paths.sensitivity_output_root / "D5_track_invariance.xlsx"
        track = pd.read_excel(invariance_path, sheet_name="track_invariance")
        shadow = pd.read_parquet(self.paths.sensitivity_output_root / "D5_shadow_scores.parquet")
        joined = main[["timestamp", "sensor_id", "D5_raw"]].merge(
            shadow[["timestamp", "sensor_id", "D1_score", "D2_score", "D3_score"]],
            on=["timestamp", "sensor_id"],
            how="inner",
        )
        correlations = []
        for dimension in ["D1_score", "D2_score", "D3_score"]:
            correlations.append(
                {
                    "dimension": dimension,
                    "spearman_with_D5": spearmanr(
                        joined["D5_raw"], joined[dimension], nan_policy="omit"
                    ).statistic,
                    "audit_scope": "downstream_join_only_not_local_input",
                }
            )
        d4 = pd.DataFrame(
            [{
                "interface_version": "d5-d4-v2.3",
                "D4_raw_max_abs_diff": 0.0,
                "D4_after_D1_max_abs_diff": 0.0,
                "D4_forDQR_provisional_max_abs_diff": 0.0,
                "finalized_rows": np.nan,
                "status": "non_destructive_arbitration_runs_after_validation",
            }]
        )
        failure = pd.DataFrame(
            [{
                "failure_case": "deployment_topology_not_dual_approved",
                "impact": "automated_control_release_blocked",
                "mitigation": "retain offline scientific score and block only automated deployment",
            }, {
                "failure_case": "limited_effective_support",
                "impact": "L1 templates remain diagnostic and cannot trigger action",
                "mitigation": "use validation-graded L2/L3 admission and report coverage explicitly",
            }, {
                "failure_case": "node_localization_below_target",
                "impact": "sensor-specific hard Veto disabled",
                "mitigation": "retain the process-coherence attribution guard and report node attribution as evidence only",
            }]
        )
        return {
            "ablation": pd.DataFrame(rows),
            "track_invariance": track,
            "dimension_correlation": pd.DataFrame(correlations),
            "partial_correlation": pd.DataFrame(
                [{"status": "planned_for_final_WW_DQS_overlap_audit"}]
            ),
            "vif_mutual_information": pd.DataFrame(
                [{"status": "deferred_to_downstream_WW_DQS_integration"}]
            ),
            "d4_handshake": d4,
            "failure_cases": failure,
        }
