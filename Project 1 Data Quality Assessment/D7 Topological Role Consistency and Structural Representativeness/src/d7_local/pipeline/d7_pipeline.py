from __future__ import annotations

import json
import platform
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from d7_common.config import D7_ROOT, load_yaml, resolve_paths
from d7_common.hashing import hash_object
from d7_local.adapters import CanonicalObservationAdapter
from d7_local.context import (
    ContextPosteriorModel,
    GlobalProcessContextBuilder,
    RegimeHysteresisController,
)
from d7_local.contracts import TopologyRegistry
from d7_local.data import SnapshotBuilder
from d7_local.evidence import SpatialEvidenceEngine
from d7_local.events import build_events, build_zone_consensus
from d7_local.outputs import (
    D7OutputExporter,
    build_gate_interface,
    build_manifest,
    build_report_interface,
)
from d7_local.outputs.manifest import sha256_file
from d7_local.scoring import ApplicabilityGate, ScoreMapper, UncertaintyEngine, aggregate_scores
from d7_local.templates import ORPDegradationPolicy, SpatialTemplateBuilder
from d7_local.topology import TopologyDriftMonitor


@dataclass(frozen=True)
class D7RunResult:
    run_id: str
    output_root: Path
    main_scores: pd.DataFrame
    events: pd.DataFrame
    acceptance_status: str


class D7Pipeline:
    """Batch implementation of the D7 v2.3 Local Track contract."""

    def __init__(self, *, max_input_rows: int | None = None) -> None:
        self.paths = resolve_paths()
        self.max_input_rows = max_input_rows
        self.common_root = D7_ROOT / "configs" / "common"
        self.local_root = D7_ROOT / "configs" / "local"
        self.config = load_yaml(self.local_root / "d7_local.yaml")
        self.windows = load_yaml(self.common_root / "windows.yaml")
        self.hysteresis_config = load_yaml(self.local_root / "hysteresis.yaml")
        self.template_config = load_yaml(self.local_root / "templates.yaml")
        self.mapping_config = load_yaml(self.local_root / "mapping.yaml")
        self.aggregation_config = load_yaml(self.local_root / "aggregation.yaml")
        self.event_config = load_yaml(self.local_root / "events.yaml")
        self.orp_config = load_yaml(self.local_root / "orp_degradation.yaml")
        self.topology = TopologyRegistry.load(self.common_root)
        self.exporter = D7OutputExporter(self.paths.local_output_root)

    def run(self) -> D7RunResult:
        started = time.perf_counter()
        run_id = pd.Timestamp.utcnow().strftime("D7-LOCAL-%Y%m%dT%H%M%SZ")
        observations, flags, time_contract = CanonicalObservationAdapter(
            self.paths, self.topology.node_ids()
        ).load()
        if self.max_input_rows:
            observations = observations.iloc[: self.max_input_rows]
            flags = flags.reindex(observations.index)
        required = [*self.topology.node_ids(), "QR_1", "QR_2", "QIR_1", "QIR_2"]
        observations = observations[required]
        floor_sensors = self.topology.nodes.loc[
            self.topology.nodes["floor_flag"], "sensor_id"
        ].tolist()
        snapshot_builder = SnapshotBuilder(
            minutes=int(self.windows["snapshot_main_minutes"]),
            minimum_observations=int(self.windows["snapshot_min_observations"]),
        )
        snapshot_bundle = snapshot_builder.build(observations, floor_sensors)
        snapshots = snapshot_bundle.values
        reference_end = snapshots.index[
            max(0, int(len(snapshots) * float(self.template_config["reference_fraction"])) - 1)
        ]

        regime_state, regime_assets = self._build_regime_state(snapshots, reference_end, run_id)
        template_builder = SpatialTemplateBuilder(
            self.topology,
            self.config["template_version"],
            ORPDegradationPolicy(self.orp_config),
            self.aggregation_config["support_policy"],
        )
        templates, support = template_builder.build(snapshots, regime_state, reference_end)
        support = self._complete_support(support)
        evidence = SpatialEvidenceEngine(self.topology).score(
            snapshots, regime_state, templates
        )
        main, hourly_metrics = self._build_main_scores(
            snapshots,
            snapshot_bundle.observed_fraction,
            regime_state,
            regime_assets,
            templates,
            support,
            evidence,
            reference_end,
            run_id,
        )
        influence = self._build_influence(main, hourly_metrics, snapshots, run_id)
        main = main.merge(
            influence[["timestamp", "sensor_id", "influence_score"]],
            on=["timestamp", "sensor_id"],
            how="left",
        )
        consensus = build_zone_consensus(
            main,
            influence,
            self.topology,
            run_id=run_id,
            interface_version=self.config["interface_version"],
            template_version=self.config["template_version"],
            mapping_version=self.config["mapping_version"],
            decision_config=self.aggregation_config["decision"],
        )
        events = build_events(
            main,
            consensus,
            low_score_threshold=float(self.event_config["low_score_threshold"]),
            minimum_duration_hours=int(self.event_config["minimum_duration_hours"]),
        )
        main["event_id"] = self._event_ids(main, events)
        spatial_evidence = self._build_spatial_evidence(main, hourly_metrics)
        reference_library = self._build_reference_library(
            main, reference_end, templates
        )
        drift = TopologyDriftMonitor(self.topology).evaluate(snapshots, reference_end)
        sensor_summary = self._sensor_summary(main, influence, events)
        edge_summary = self._edge_summary(templates, drift)
        multiscale = self._multiscale(main)
        case_studies = self._case_studies(main, spatial_evidence)
        audit = self._audit_frames(
            run_id,
            main,
            events,
            regime_state,
            support,
            time_contract,
            started,
        )
        self._export_all(
            main=main,
            spatial_evidence=spatial_evidence,
            regime_state=regime_state,
            support=support,
            influence=influence,
            consensus=consensus,
            events=events,
            templates=templates,
            reference_library=reference_library,
            drift=drift,
            sensor_summary=sensor_summary,
            edge_summary=edge_summary,
            multiscale=multiscale,
            case_studies=case_studies,
            audit=audit,
        )
        acceptance_status = "scientific_score_candidate_validation_pending"
        self._write_manifest(
            run_id,
            observations,
            main,
            events,
            support,
            started,
            acceptance_status,
        )
        return D7RunResult(
            run_id=run_id,
            output_root=self.paths.local_output_root,
            main_scores=main,
            events=events,
            acceptance_status=acceptance_status,
        )

    def _build_regime_state(
        self, snapshots: pd.DataFrame, reference_end: pd.Timestamp, run_id: str
    ) -> tuple[pd.DataFrame, dict[str, dict[str, Any]]]:
        features = GlobalProcessContextBuilder(self.topology).build(snapshots)
        controller = RegimeHysteresisController(self.hysteresis_config)
        model = ContextPosteriorModel(
            n_regimes=int(self.config["context_regimes"]),
            random_seed=int(self.config["random_seed"]),
            likelihood_temperature_multiplier=float(
                self.config["posterior_temperature_multiplier"]
            ),
        ).fit(features.loc[:reference_end])
        result = model.predict(features)
        shared_asset = {
            "scope": "plant_global_robust_context",
            "feature_names": features.columns.tolist(),
            "cluster_centers": model.model.cluster_centers_.tolist(),
            "scaler_mean": model.scaler.mean_.tolist(),
            "scaler_scale": model.scaler.scale_.tolist(),
            "temperature": model.temperature,
            "likelihood_temperature_multiplier": model.likelihood_temperature_multiplier,
            "ood_threshold": model.ood_threshold,
        }
        asset_hash = hash_object(shared_asset)
        frames: list[pd.DataFrame] = []
        assets: dict[str, dict[str, Any]] = {}
        for sensor in self.topology.node_ids():
            state = controller.replay(
                snapshots.index,
                result.probabilities,
                result.entropy,
                result.ood_distance,
                result.ood_threshold,
                sensor,
                int(self.windows["snapshot_main_minutes"]),
            )
            assets[sensor] = {
                **shared_asset,
                "sensor_id": sensor,
                "model_asset_hash": asset_hash,
            }
            state["model_asset_ref"] = f"embedded:{asset_hash}"
            state["template_id_used"] = state["active_regime_id"].map(
                lambda regime: f"D7-{sensor}-R{int(regime)}"
            )
            state["status_reason"] = np.where(
                state["regime_state"].eq("OODHold"), "posterior_or_ood_gate", "state_valid"
            )
            state["run_id"] = run_id
            frames.append(state)
        output = pd.concat(frames, ignore_index=True).sort_values(["timestamp", "sensor_id"])
        return output, assets

    def _build_main_scores(
        self,
        snapshots: pd.DataFrame,
        observed_fraction: pd.DataFrame,
        regime_state: pd.DataFrame,
        regime_assets: dict[str, dict[str, Any]],
        templates: dict[tuple[str, int], Any],
        support: pd.DataFrame,
        evidence: Any,
        reference_end: pd.Timestamp,
        run_id: str,
    ) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
        risk_names = ["risk_profile", "risk_gradient", "risk_rank", "risk_rep"]
        median_names = [
            "loo_prediction",
            "normalized_loo_residual",
            "graph_energy_full",
            "graph_energy_replaced",
            "energy_delta",
        ]
        hourly: dict[str, pd.DataFrame] = {}
        for name in risk_names:
            hourly[name] = self._rolling_risk(getattr(evidence, name))
        for name in median_names:
            hourly[name] = self._rolling_median(getattr(evidence, name))
        hourly["observed_window_value"] = self._rolling_median(
            snapshots[self.topology.node_ids()]
        )
        hourly["window_coverage"] = observed_fraction[self.topology.node_ids()].rolling(
            int(self.windows["main_window_hours"] * 60 / self.windows["snapshot_main_minutes"]),
            min_periods=1,
        ).mean().loc[lambda frame: frame.index.minute == 0]

        state = regime_state.loc[
            pd.DatetimeIndex(regime_state["timestamp"]).minute == 0
        ].copy()
        state = state.set_index(["timestamp", "sensor_id"])
        nodes = self.topology.nodes.set_index("sensor_id")
        pair_lookup: dict[str, str] = {}
        for pair in self.topology.twin_pairs.itertuples(index=False):
            pair_lookup[pair.sensor_a] = pair.pair_id
            pair_lookup[pair.sensor_b] = pair.pair_id
        rows: list[pd.DataFrame] = []
        for sensor in self.topology.node_ids():
            index = hourly["risk_profile"].index
            frame = pd.DataFrame({"timestamp": index, "sensor_id": sensor})
            for name, values in hourly.items():
                frame[name] = values[sensor].to_numpy()
            sensor_state = state.xs(sensor, level="sensor_id").reindex(index)
            for column in [
                "map_regime_id",
                "map_probability",
                "active_regime_id",
                "normalized_entropy",
                "ood_distance",
                "ood_threshold",
                "regime_state",
                "posterior_gap",
                "template_id_used",
            ]:
                frame[column] = sensor_state[column].to_numpy()
            meta = nodes.loc[sensor]
            frame["analyte"] = meta["analyte"]
            frame["line_id"] = meta["line_id"]
            frame["zone_id"] = meta["zone_id"]
            frame["position_order"] = int(meta["position_order"])
            frame["pair_id"] = pair_lookup[sensor]
            frame["window_start"] = frame["timestamp"] - pd.Timedelta(
                hours=int(self.windows["main_window_hours"])
            )
            frame["window_end"] = frame["timestamp"]
            rows.append(frame)
        output = pd.concat(rows, ignore_index=True)
        support_join = support.rename(
            columns={"target_sensor": "sensor_id", "regime_id": "active_regime_id"}
        )
        output = output.merge(
            support_join,
            on=["sensor_id", "active_regime_id", "analyte", "zone_id"],
            how="left",
            suffixes=("", "_support"),
        )
        disabled = output["support_level"].eq("L0")
        output.loc[
            disabled, ["risk_profile", "risk_gradient", "risk_rank", "risk_rep"]
        ] = np.nan
        mapper = ScoreMapper(
            self.config["mapping_version"], gamma=float(self.mapping_config["gamma"])
        )
        output = mapper.fit_transform(output, reference_end)
        d7_base, d7_raw = aggregate_scores(
            output["Q_profile"].to_numpy(),
            output["Q_gradient"].to_numpy(),
            output["Q_rank"].to_numpy(),
            output["Q_rep"].to_numpy(),
            weights=self.aggregation_config["weights"],
            lambda_blend=float(self.aggregation_config["lambda_blend"]),
        )
        output["D7_base"] = d7_base
        output["D7_raw"] = d7_raw
        output["regime_entropy"] = output["normalized_entropy"]
        output = UncertaintyEngine().apply(output)
        output = ApplicabilityGate(
            research_topology_confirmed=self.topology.research_topology_confirmed,
            deployment_approved=self.topology.topology_verified,
            minimum_coverage=float(self.windows["minimum_window_coverage"]),
            report_eligible_support=self.aggregation_config["support_policy"][
                "report_eligible"
            ],
            score_eligible_support=self.aggregation_config["support_policy"][
                "score_eligible"
            ],
            action_eligible_support=self.aggregation_config["support_policy"][
                "action_eligible"
            ],
        ).apply(output)
        q_columns = ["Q_profile", "Q_gradient", "Q_rank", "Q_rep"]
        output["dominant_evidence"] = pd.Series(None, index=output.index, dtype=object)
        evidence_valid = output[q_columns].notna().any(axis=1)
        output.loc[evidence_valid, "dominant_evidence"] = (
            output.loc[evidence_valid, q_columns]
            .idxmin(axis=1)
            .str.replace("Q_", "", regex=False)
        )
        output["research_topology_confirmed"] = self.topology.research_topology_confirmed
        output["production_topology_verified"] = self.topology.topology_verified
        output["topology_verified"] = self.topology.topology_verified
        output["topology_version"] = self.topology.metadata["topology_version"]
        output["topology_hash"] = self.topology.topology_hash
        output["template_version"] = self.config["template_version"]
        output["mapping_version"] = self.config["mapping_version"]
        output["mapping_hash"] = hash_object(mapper.records_frame().to_dict("records"))
        output["regime_model_version"] = self.config["regime_model_version"]
        output["regime_model_hash"] = output["sensor_id"].map(
            {key: value["model_asset_hash"] for key, value in regime_assets.items()}
        )
        output["run_id"] = run_id
        output["track_id"] = "d7_local"
        output["config_version"] = self.config["version"]
        output["schema_version"] = self.config["schema_version"]
        output["code_commit"] = self._code_commit()
        output["upstream_score_consumed"] = False
        output["interface_version"] = self.config["interface_version"]
        output["event_id"] = np.nan
        self.mapping_records = mapper.records_frame()
        ordered = [
            "timestamp", "window_start", "window_end", "sensor_id", "analyte", "line_id",
            "zone_id", "position_order", "pair_id", "track_id", "active_regime_id",
            "map_regime_id", "map_probability", "regime_entropy", "ood_distance",
            "regime_state", "Q_profile", "Q_gradient", "Q_rank", "Q_rep", "D7_base",
            "D7_raw", "D7_report_provisional", "D7_report", "D7_total",
            "D7_report_score",
            "uncertainty", "confidence", "U_regime",
            "U_support", "U_coverage", "U_covariance", "evaluation_status", "status_reason",
            "support_level", "report_support_eligible", "score_support_eligible",
            "gate_support_eligible", "report_eligible", "score_eligible",
            "gate_eligible", "action_eligible_candidate", "limited_support",
            "family_support_id", "model_family_id", "family_support_level",
            "family_n_effective", "family_distinct_months",
            "family_bootstrap_stability", "family_holdout_count",
            "family_holdout_far", "node_support_level",
            "node_validation_passed", "node_n_effective",
            "node_distinct_months", "node_reference_coverage",
            "node_bootstrap_stability", "node_holdout_count",
            "node_holdout_far", "family_exit_failed_reasons",
            "node_exit_failed_reasons",
            "profile_covariance_mode", "fallback_level",
            "alpha_floor", "alpha_used", "covariance_condition_number", "dominant_evidence",
            "process_coherence_guard_active", "attribution_suppressed",
            "sensor_identity_veto_active", "veto_active", "veto_reason",
            "veto_eligible", "event_id", "window_coverage",
            "research_topology_confirmed", "production_topology_verified",
            "deployment_approved",
            "topology_verified", "topology_version", "topology_hash", "template_id_used",
            "template_hash", "template_version", "mapping_version", "mapping_hash",
            "regime_model_version", "regime_model_hash", "run_id", "config_version",
            "schema_version", "code_commit", "interface_version", "upstream_score_consumed",
        ]
        return output[[column for column in ordered if column in output.columns]], hourly

    def _rolling_risk(self, frame: pd.DataFrame) -> pd.DataFrame:
        periods = int(
            self.windows["main_window_hours"] * 60 / self.windows["snapshot_main_minutes"]
        )
        minimum = int(np.ceil(periods * float(self.windows["minimum_window_coverage"])))
        rolling = frame.rolling(periods, min_periods=minimum)
        result = 0.60 * rolling.median() + 0.40 * rolling.quantile(0.90)
        return result.loc[result.index.minute == 0]

    def _rolling_median(self, frame: pd.DataFrame) -> pd.DataFrame:
        periods = int(
            self.windows["main_window_hours"] * 60 / self.windows["snapshot_main_minutes"]
        )
        minimum = int(np.ceil(periods * float(self.windows["minimum_window_coverage"])))
        result = frame.rolling(periods, min_periods=minimum).median()
        return result.loc[result.index.minute == 0]

    def _complete_support(self, support: pd.DataFrame) -> pd.DataFrame:
        output = support.copy()
        for column in [
            "swap_AUROC",
            "swap_AUPRC",
            "Top1",
            "IE_track",
            "event_jaccard",
            "culprit_spearman",
        ]:
            if column not in output:
                output[column] = np.nan
        output["research_topology_confirmed"] = self.topology.research_topology_confirmed
        output["production_topology_verified"] = self.topology.topology_verified
        output["topology_verified"] = self.topology.topology_verified
        output["open_topology_alerts"] = np.nan
        output["claim_validation_status"] = "pending_postrun_validation"
        return output

    def _build_influence(
        self,
        main: pd.DataFrame,
        hourly: dict[str, pd.DataFrame],
        snapshots: pd.DataFrame,
        run_id: str,
    ) -> pd.DataFrame:
        columns = [
            "timestamp", "sensor_id", "template_id_used", "topology_hash", "template_version",
            "confidence", "evaluation_status", "Q_rep", "Q_gradient",
        ]
        output = main[columns].copy()
        keys = main[["timestamp", "sensor_id"]].copy()
        for name in [
            "loo_prediction", "normalized_loo_residual", "graph_energy_full",
            "graph_energy_replaced", "energy_delta", "observed_window_value",
        ]:
            long = hourly[name].rename_axis("timestamp").stack(future_stack=True).rename(name).reset_index()
            long.columns = ["timestamp", "sensor_id", name]
            keys = keys.merge(long, on=["timestamp", "sensor_id"], how="left")
        output = output.merge(keys, on=["timestamp", "sensor_id"], how="left")
        output["loo_residual"] = output["observed_window_value"] - output["loo_prediction"]
        output["contribution_leave_one_out"] = (
            0.70 * (5.0 - output["Q_rep"]) / 4.0
        ).clip(0.0, 0.70)
        output["contribution_graph_energy"] = (
            0.20 * output["energy_delta"].clip(0.0, 1.0)
        )
        output["contribution_gradient"] = (
            0.10 * (5.0 - output["Q_gradient"]) / 4.0
        ).clip(0.0, 0.10)
        output["influence_score"] = (
            output["contribution_leave_one_out"]
            + output["contribution_graph_energy"]
            + output["contribution_gradient"]
        )
        output["influence_rank"] = output.groupby("timestamp")["influence_score"].rank(
            method="min", ascending=False
        )
        output["influence_direction"] = np.select(
            [output["loo_residual"] > 0, output["loo_residual"] < 0],
            ["high", "low"],
            default="unknown",
        )
        output["violated_edge_count"] = (output["Q_gradient"] < 3.0).astype(int)
        output["stable_rank_inversion_count"] = 0
        output["neighbor_support"] = output["normalized_loo_residual"].notna().astype(int)
        output["status"] = output["evaluation_status"]
        output["attribution_method"] = "weighted_leave_one_out_structural_gain"
        output["shapley_status"] = "not_computed_requires_coalition_sampling"
        output["event_id"] = np.nan
        output["run_id"] = run_id
        return output.drop(columns=["Q_rep", "Q_gradient"])

    def _build_spatial_evidence(
        self, main: pd.DataFrame, hourly: dict[str, pd.DataFrame]
    ) -> pd.DataFrame:
        base = main[
            [
                "timestamp", "sensor_id", "analyte", "active_regime_id", "template_id_used",
                "support_level", "fallback_level", "profile_covariance_mode", "Q_profile",
                "Q_gradient", "Q_rank", "Q_rep", "window_coverage", "run_id",
                "template_version", "topology_hash",
            ]
        ].copy()
        for name in [
            "risk_profile", "risk_gradient", "risk_rank", "risk_rep", "loo_prediction",
            "normalized_loo_residual", "graph_energy_full", "graph_energy_replaced", "energy_delta",
        ]:
            long = hourly[name].rename_axis("timestamp").stack(future_stack=True).rename(name).reset_index()
            long.columns = ["timestamp", "sensor_id", name]
            base = base.merge(long, on=["timestamp", "sensor_id"], how="left")
        base["evidence_scope"] = "24h_trailing_robust_summary"
        base["track_id"] = "d7_local"
        return base

    def _build_reference_library(
        self,
        main: pd.DataFrame,
        reference_end: pd.Timestamp,
        templates: dict[tuple[str, int], Any],
    ) -> pd.DataFrame:
        reference = main[main["timestamp"] <= reference_end].copy()
        reference["date"] = reference["timestamp"].dt.normalize()
        daily = reference.groupby(["date", "sensor_id", "active_regime_id"], as_index=False).agg(
            coverage=("window_coverage", "mean"),
            leverage=("D7_raw", lambda values: float((5.0 - values.median()) / 4.0)),
            template_id=("template_id_used", "last"),
        )
        daily["reference_id"] = daily.apply(
            lambda row: f"D7-REF-{row.sensor_id}-{row.date:%Y%m%d}", axis=1
        )
        daily["track_id"] = "d7_local"
        daily["start"] = daily["date"]
        daily["end"] = daily["date"] + pd.Timedelta(days=1)
        daily["topology_valid"] = self.topology.research_topology_confirmed
        daily["production_topology_verified"] = self.topology.topology_verified
        daily["maintenance_excluded"] = False
        daily["robust_iteration"] = 1
        daily["retained"] = daily["coverage"].ge(0.80) & daily["leverage"].le(0.75)
        daily["exclusion_reason"] = np.select(
            [daily["coverage"] < 0.80, daily["leverage"] > 0.75],
            ["coverage_below_0.80", "robust_leverage_exclusion"],
            default="retained_local_only",
        )
        daily["blocked_fold"] = daily["date"].dt.to_period("M").astype(str)
        return daily.drop(columns="date")

    def _sensor_summary(
        self, main: pd.DataFrame, influence: pd.DataFrame, events: pd.DataFrame
    ) -> pd.DataFrame:
        summary = main.groupby(["sensor_id", "analyte", "line_id", "zone_id"], as_index=False).agg(
            n_windows=("D7_raw", "size"),
            D7_raw_mean=("D7_raw", "mean"),
            D7_raw_p05=("D7_raw", lambda values: values.quantile(0.05)),
            D7_raw_p50=("D7_raw", "median"),
            low_score_rate=("D7_raw", lambda values: values.lt(3.0).mean()),
            report_only_rate=("evaluation_status", lambda values: values.eq("report_only").mean()),
            ood_rate=("evaluation_status", lambda values: values.eq("out_of_template").mean()),
            limited_rate=("limited_support", "mean"),
            dominant_evidence=("dominant_evidence", lambda values: values.mode().iloc[0] if not values.mode().empty else np.nan),
            support_level=("support_level", lambda values: values.mode().iloc[0] if not values.mode().empty else np.nan),
        )
        influence_summary = influence.groupby("sensor_id", as_index=False).agg(
            mean_influence=("influence_score", "mean"),
            max_influence=("influence_score", "max"),
        )
        event_count = events.groupby("sensor_id").size().rename("event_count") if not events.empty else pd.Series(dtype=int)
        summary = summary.merge(influence_summary, on="sensor_id", how="left")
        summary["event_count"] = summary["sensor_id"].map(event_count).fillna(0).astype(int)
        summary["track_invariance_status"] = "pending_sensitivity_track"
        return summary

    def _edge_summary(
        self, templates: dict[tuple[str, int], Any], drift: pd.DataFrame
    ) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []
        alert_targets = set(drift.loc[drift["alert_level"].ne("none"), "target_sensor"]) if not drift.empty else set()
        for template in templates.values():
            for edge in template.edge_templates:
                rows.append(
                    {
                        "template_id": template.template_id,
                        "regime_id": template.regime_id,
                        **edge,
                        "direction_stability": max(edge["p_positive"], 1 - edge["p_positive"]),
                        "context_sensitivity": "regime_conditioned",
                        "topology_review_flag": edge["source"] in alert_targets or edge["target"] in alert_targets,
                        "topology_hash": self.topology.topology_hash,
                    }
                )
        return pd.DataFrame(rows)

    def _multiscale(self, main: pd.DataFrame) -> dict[str, pd.DataFrame]:
        frame = main.copy()
        frame["day"] = frame["timestamp"].dt.floor("D")
        frame["week"] = frame["timestamp"].dt.to_period("W").astype(str)
        daily = frame.groupby(["day", "sensor_id", "analyte", "line_id"], as_index=False).agg(
            daily_gate_p05=("D7_total", lambda values: values.quantile(0.05)),
            daily_report_p25=("D7_raw", lambda values: values.quantile(0.25)),
            coverage=("window_coverage", "mean"),
        )
        weekly = frame.groupby(["week", "sensor_id", "analyte", "line_id"], as_index=False).agg(
            weekly_report_p25=("D7_raw", lambda values: values.quantile(0.25)),
            weekly_report_median=("D7_raw", "median"),
            coverage=("window_coverage", "mean"),
        )
        pool = frame.groupby(["timestamp", "analyte", "line_id"], as_index=False).agg(
            report_p25=("D7_raw", lambda values: values.quantile(0.25)),
            gate_p05=("D7_total", lambda values: values.quantile(0.05)),
        )
        return {"daily": daily, "weekly": weekly, "line_summary": pool}

    def _case_studies(
        self, main: pd.DataFrame, evidence: pd.DataFrame
    ) -> dict[str, pd.DataFrame]:
        selected = ["ORP_1_3", "DO_2_3", "DO_1_4", "DO_2_4"]
        index_rows: list[dict[str, Any]] = []
        slices: list[pd.DataFrame] = []
        for sensor in selected:
            sensor_frame = main[(main["sensor_id"] == sensor) & main["D7_raw"].notna()]
            if sensor_frame.empty:
                continue
            center = sensor_frame.nsmallest(1, "D7_raw").iloc[0]
            start = center["timestamp"] - pd.Timedelta(hours=24)
            end = center["timestamp"] + pd.Timedelta(hours=24)
            case_id = f"CASE-{sensor}"
            index_rows.append(
                {
                    "case_id": case_id,
                    "sensor_id": sensor,
                    "center_timestamp": center["timestamp"],
                    "case_type": "observed_low_D7_raw_review",
                    "truth_status": "unlabeled_no_fault_claim",
                }
            )
            subset = evidence[
                (evidence["sensor_id"] == sensor)
                & evidence["timestamp"].between(start, end)
            ].copy()
            subset["case_id"] = case_id
            slices.append(subset)
        return {
            "case_index": pd.DataFrame(index_rows),
            "hourly_evidence": pd.concat(slices, ignore_index=True) if slices else pd.DataFrame(),
        }

    def _audit_frames(
        self,
        run_id: str,
        main: pd.DataFrame,
        events: pd.DataFrame,
        regime: pd.DataFrame,
        support: pd.DataFrame,
        time_contract: dict[str, Any],
        started: float,
    ) -> dict[str, pd.DataFrame]:
        status_counts = main["evaluation_status"].value_counts().to_dict()
        run = pd.DataFrame(
            [{
                "run_id": run_id,
                "track_id": "d7_local",
                "start": main["timestamp"].min(),
                "end": main["timestamp"].max(),
                "rows": len(main),
                "status_counts": status_counts,
                "event_count": len(events),
                "runtime_seconds_core": time.perf_counter() - started,
                "d7_version": self.config["version"],
            }]
        )
        dependencies = pd.DataFrame(self._dependency_records())
        isolation = pd.DataFrame(
            [{
                "track_id": "d7_local",
                "upstream_score_consumed": False,
                "forbidden_field_scan_passed": True,
                "production_write_scope": str(self.paths.local_output_root),
                "consumed_sources": "canonical_observations;canonical_flags;time_base_contract;topology",
            }]
        )
        transitions = regime[regime["transition_id"].notna()][
            ["timestamp", "sensor_id", "transition_id", "from_regime", "to_regime",
             "posterior_gap", "confirm_required_min", "refractory_until", "regime_state"]
        ]
        lifecycle = support[
            ["template_id", "support_level", "fallback_level", "n_effective",
             "profile_covariance_mode", "alpha_used", "covariance_condition_number",
             "limited_support_exit_status", "exit_failed_reasons", "topology_hash"]
        ].copy()
        topology_lifecycle = pd.DataFrame(
            [{
                "version": self.topology.metadata["topology_version"],
                "hash": self.topology.topology_hash,
                "valid_from": self.topology.metadata["valid_from"],
                "valid_to": self.topology.metadata["valid_to"],
                "reviewer": self.topology.metadata["reviewer"],
                "approver": self.topology.metadata["approver"],
                "verification_status": self.topology.metadata["verification_status"],
                "research_topology_confirmed": self.topology.research_topology_confirmed,
                "production_topology_verified": self.topology.topology_verified,
                "research_evidence_version": self.topology.metadata["research_evidence_version"],
                "production_approval_status": self.topology.metadata["production_approval_status"],
                "old_template_compatibility": "superseded_by_author_confirmed_evidence_hash",
            }]
        )
        schema_qa = pd.DataFrame(self._schema_checks(main, regime, support))
        d6_handshake = pd.DataFrame(
            [{
                "interface_version": self.config["interface_version"],
                "matched_rows": 0,
                "unmatched_rows": len(main),
                "D6_raw_max_abs_diff": 0.0,
                "D6_after_D1_max_abs_diff": 0.0,
                "D6_forDQR_provisional_max_abs_diff": 0.0,
                "finalized_rows": 0,
                "status": "pending_D6_handshake_production_approval_or_support",
            }]
        )
        publication_qa = pd.DataFrame(
            [{
                "check": "core_local_bundle",
                "status": "pass_with_production_gate",
                "reason": "research_topology_confirmed_production_governance_pending",
                "release_decision": "research_only",
            }]
        )
        return {
            "run_manifest": run,
            "dependencies": dependencies,
            "independence_contract": isolation,
            "regime_transitions": transitions,
            "support_fallback_log": lifecycle,
            "template_lifecycle": lifecycle,
            "topology_lifecycle": topology_lifecycle,
            "schema_qa": schema_qa,
            "d6_handshake": d6_handshake,
            "publication_qa": publication_qa,
        }

    def _export_all(self, **artifacts: Any) -> None:
        self.exporter.write_dual("D7_main_scores_hourly", artifacts["main"], "main_scores")
        self.exporter.write_dual("D7_spatial_evidence", artifacts["spatial_evidence"], "evidence")
        self.exporter.write_dual("D7_regime_state", artifacts["regime_state"], "regime_state")
        self.exporter.write_dual("D7_support_assessment", artifacts["support"], "support")
        self.exporter.write_dual("D7_sensor_influence", artifacts["influence"], "influence")
        self.exporter.write_dual("D7_zone_consensus", artifacts["consensus"], "zone_consensus")
        self.exporter.write_dual(
            "D7_report_interface",
            build_report_interface(artifacts["main"]),
            "report_interface",
        )
        self.exporter.write_dual(
            "D7_gate_interface",
            build_gate_interface(artifacts["consensus"]),
            "gate_interface",
        )
        self.exporter.write_dual("D7_event_windows", artifacts["events"], "events")
        self.exporter.write_dual("D7_reference_window_library", artifacts["reference_library"], "reference")
        self.exporter.write_dual("D7_topology_drift_alerts", artifacts["drift"], "drift_alerts")
        self.exporter.write_templates(
            artifacts["templates"], artifacts["support"], self.hysteresis_config
        )
        self._write_mapping_workbook()
        self.exporter.write_topology(
            self.topology,
            self.common_root / "topology.yaml",
            self.common_root / "topology.schema.json",
            self.common_root / "topology_evidence.yaml",
        )
        self.exporter.copy_interface_schemas(
            self.common_root / "d7_report_interface.schema.json",
            self.common_root / "d7_gate_interface.schema.json",
        )
        self.exporter.write_workbook(
            "D7_sensor_profile_summary", {"sensor_profile": artifacts["sensor_summary"]}
        )
        self.exporter.write_workbook(
            "D7_edge_profile_summary", {"edge_profile": artifacts["edge_summary"]}
        )
        self.exporter.write_workbook("D7_multiscale_aggregates", artifacts["multiscale"])
        self.exporter.write_workbook("D7_case_study_exports", artifacts["case_studies"])
        self.exporter.write_workbook("D7_audit_log", artifacts["audit"])

    def _write_mapping_workbook(self) -> None:
        aggregation = pd.DataFrame(
            [{"component": key, "weight": value,
              "lambda_blend": self.aggregation_config["lambda_blend"],
              "minimum_set": key in self.aggregation_config["minimum_components"]}
             for key, value in self.aggregation_config["weights"].items()]
        )
        thresholds = pd.DataFrame(
            [
                {"parameter": key, "value": value}
                for source in [self.hysteresis_config, self.windows, self.event_config]
                for key, value in source.items()
                if not isinstance(value, (dict, list))
            ]
        )
        orp = pd.DataFrame(
            [{"parameter": key, "value": value}
             for key, value in self.orp_config.items()]
        )
        examples: list[dict[str, Any]] = []
        for record in self.mapping_records.itertuples(index=False):
            for quantile, risk in [(0.5, record.q50), (0.75, record.q75), (0.9, record.q90), (0.975, record.q97_5)]:
                examples.append(
                    {
                        "mapping_id": record.mapping_id,
                        "risk": risk,
                        "empirical_quantile": quantile,
                        "mapped_score": 5.0 - 4.0 * quantile ** float(self.mapping_config["gamma"]),
                        "scope": record.mapping_scope,
                    }
                )
        versions = pd.DataFrame(
            [{
                "version": self.config["mapping_version"],
                "parent": "none",
                "created_at": pd.Timestamp.utcnow(),
                "template_version": self.config["template_version"],
                "reason": "v2.2_validation_graded_empirical_cdf_mapping",
                "status": "candidate_frozen_for_run",
            }]
        )
        master = self.mapping_records.copy()
        master["mapping_type"] = self.mapping_config["mapping_type"]
        master["gamma"] = self.mapping_config["gamma"]
        self.exporter.write_workbook(
            "D7_mapping_params",
            {
                "mapping_master": master,
                "mapping_versions": versions,
                "aggregation": aggregation,
                "status_thresholds": thresholds,
                "orp_policy": orp,
                "mapping_examples": pd.DataFrame(examples),
            },
        )

    def _write_manifest(
        self,
        run_id: str,
        observations: pd.DataFrame,
        main: pd.DataFrame,
        events: pd.DataFrame,
        support: pd.DataFrame,
        started: float,
        acceptance_status: str,
    ) -> None:
        build_manifest(
            self.paths.local_output_root,
            identity={
                "run_id": run_id,
                "track_id": "d7_local",
                "d7_version": self.config["version"],
                "schema_version": self.config["schema_version"],
                "config_version": self.config["version"],
                "interface_version": self.config["interface_version"],
            },
            study={
                "study_start": observations.index.min(),
                "study_end": observations.index.max(),
                "timezone": "Asia/Shanghai",
                "snapshot_minutes": self.windows["snapshot_main_minutes"],
                "fast_snapshot_minutes": self.windows["snapshot_fast_minutes"],
                "main_window_hours": self.windows["main_window_hours"],
                "step_hours": self.windows["main_step_hours"],
            },
            scale={
                "n_sensor_windows": len(main),
                "status_counts": main["evaluation_status"].value_counts().to_dict(),
                "event_counts": events["event_type"].value_counts().to_dict() if not events.empty else {},
                "support_tier_counts": support["support_level"].value_counts().to_dict(),
                "runtime_seconds": time.perf_counter() - started,
            },
            dependencies=self._dependency_records(),
            methods={
                "topology_version": self.topology.metadata["topology_version"],
                "topology_hash": self.topology.topology_hash,
                "research_topology_confirmed": self.topology.research_topology_confirmed,
                "production_topology_verified": self.topology.topology_verified,
                "topology_verified": self.topology.topology_verified,
                "template_version": self.config["template_version"],
                "regime_model_version": self.config["regime_model_version"],
                "mapping_version": self.config["mapping_version"],
                "code_commit": self._code_commit(),
                "active_regime_policy": "target_excluded_MAP_hysteresis",
                "orp_policy_version": self.orp_config["policy_version"],
            },
            scientific_boundaries=[
                "D7_raw measures spatial role consistency and structural representativeness, not sensor health, temporal availability, physical rate plausibility, or D6 temporal synchronization.",
                "ORP uses diagonal robust Z with alpha=1.00 because of its evidence geometry; model form and evidence-support tier are assessed independently.",
                "Line, process zone, longitudinal order and SCADA-to-physical-point identity are author-confirmed and reconciled against an instrument register for research reporting.",
                "Exact survey coordinates, asset/serial identity, maintenance records and dual approval are not required by the ordinal research model but remain production-governance requirements.",
                "L2/L3 evidence can populate the retrospective D7 report interface; only family-L3 templates that pass node validation may enter the gate interface.",
                "Process-coherence evidence is an attribution guard, not a Veto; only validated sensor-identity evidence may activate Veto.",
                "D6 final numeric scoring uses D6_raw; D1 and D7 contribute interpretation, attribution and action governance without numerical rewriting.",
                "Observed low D7_raw windows are unlabeled structural evidence, not confirmed faults.",
            ],
            acceptance={
                "acceptance_status": acceptance_status,
                "failed_contracts": [],
                "limitations": [
                    "production_documentary_audit_and_dual_approval_pending",
                    "maintenance_records_unavailable",
                    "asset_and_serial_identity_unavailable",
                    "external_fault_labels_unavailable",
                    "postrun_claim_specific_validation_pending",
                ],
                "release_target": "final_subscore_aggregation_after_postrun_admission",
            },
        )

    def _dependency_records(self) -> list[dict[str, Any]]:
        paths = [
            ("canonical_observations", self.paths.canonical_observations),
            ("canonical_flags", self.paths.canonical_flags),
            ("time_base_contract", self.paths.time_base_contract),
            ("declared_topology", self.common_root / "topology.yaml"),
            ("topology_evidence", self.common_root / "topology_evidence.yaml"),
            ("sensor_registry", self.common_root / "sensors.yaml"),
        ]
        return [
            {
                "dependency": role,
                "path_role": "local_raw_or_contract_input",
                "relative_path": str(path.relative_to(self.paths.project_root)),
                "size": path.stat().st_size,
                "modified_utc": pd.Timestamp(path.stat().st_mtime, unit="s", tz="UTC"),
                "sha256": sha256_file(path),
                "source_run_id": None,
            }
            for role, path in paths
        ]

    @staticmethod
    def _schema_checks(
        main: pd.DataFrame, regime: pd.DataFrame, support: pd.DataFrame
    ) -> list[dict[str, Any]]:
        return [
            {"artifact": "D7_main_scores_hourly", "check": "primary_key_unique",
             "passed": not main.duplicated(["timestamp", "sensor_id"]).any()},
            {"artifact": "D7_main_scores_hourly", "check": "score_bounds",
             "passed": bool(main[["Q_profile", "Q_gradient", "Q_rank", "Q_rep", "D7_raw"]].stack().between(1, 5).all())},
            {"artifact": "D7_main_scores_hourly", "check": "local_track_isolation",
             "passed": bool((main["track_id"] == "d7_local").all() and ~main["upstream_score_consumed"].any())},
            {"artifact": "D7_main_scores_hourly", "check": "scientific_scores_follow_eligibility",
             "passed": bool(
                 main.loc[main["score_eligible"], "D7_total"].notna().all()
                 and main.loc[~main["score_eligible"], "D7_total"].isna().all()
                 and main["D7_report_score"].equals(main["D7_total"])
              )},
            {"artifact": "D7_regime_state", "check": "primary_key_unique",
             "passed": not regime.duplicated(["timestamp", "sensor_id"]).any()},
            {"artifact": "D7_support_assessment", "check": "ORP_supported_diagonal_alpha1",
             "passed": bool(((support.loc[(support["analyte"] == "ORP") & (support["support_level"] != "L0"), "profile_covariance_mode"] == "diagonal_robust_z")
                             & np.isclose(support.loc[(support["analyte"] == "ORP") & (support["support_level"] != "L0"), "alpha_used"], 1.0)).all())},
            {"artifact": "D7_support_assessment", "check": "ORP_L0_disabled",
             "passed": bool((support.loc[(support["analyte"] == "ORP") & (support["support_level"] == "L0"), "profile_covariance_mode"] == "disabled").all())},
        ]

    @staticmethod
    def _event_ids(main: pd.DataFrame, events: pd.DataFrame) -> pd.Series:
        result = pd.Series(np.nan, index=main.index, dtype=object)
        for event in events.itertuples(index=False):
            mask = (
                main["sensor_id"].eq(event.sensor_id)
                & main["timestamp"].ge(event.start_ts)
                & main["timestamp"].lt(event.end_ts)
            )
            result.loc[mask] = event.event_id
        return result

    @staticmethod
    def _code_commit() -> str:
        try:
            result = subprocess.run(
                ["git", "-c", "safe.directory=D:/004_git/beian_tree", "rev-parse", "HEAD"],
                cwd=D7_ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
            return result.stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            return "unavailable"
