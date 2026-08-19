from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from d5_common.config import D5_ROOT, load_yaml, resolve_paths
from d5_common.hashing import hash_object


class D5PlotDataBuilder:
    COLUMNS = [
        "figure_id", "panel", "record_type", "x", "x_numeric", "y", "value",
        "value_low", "value_high", "target", "group", "sensor_id", "analyte",
        "context", "event_id", "annotation", "order", "template_version",
        "topology_version", "topology_hash", "source_run_id", "source_hash",
    ]

    def __init__(self) -> None:
        self.paths = resolve_paths()
        self.paths.plot_data_root.mkdir(parents=True, exist_ok=True)
        self.main = pd.read_parquet(
            self.paths.local_output_root / "D5_main_scores_hourly.parquet"
        )
        self.influence = pd.read_parquet(
            self.paths.local_output_root / "D5_sensor_influence.parquet"
        )
        self.consensus = pd.read_parquet(
            self.paths.local_output_root / "D5_zone_consensus.parquet"
        )
        self.events = pd.read_parquet(
            self.paths.local_output_root / "D5_event_windows.parquet"
        )
        self.support = pd.read_parquet(
            self.paths.local_output_root / "D5_support_assessment.parquet"
        )
        self.report_interface = pd.read_parquet(
            self.paths.local_output_root / "D5_report_interface.parquet"
        )
        self.gate_interface = pd.read_parquet(
            self.paths.local_output_root / "D5_gate_interface.parquet"
        )
        d4_final_path = (
            self.paths.project_root
            / "D4 Parallel-redundancy Temporal Consistency"
            / "outputs"
            / "integration"
            / "D4_D5_final_arbitration.parquet"
        )
        if not d4_final_path.exists():
            raise FileNotFoundError(
                "Run D4-D5 readiness before building D5 plot data: "
                f"{d4_final_path}"
            )
        self.d4_final = pd.read_parquet(d4_final_path)
        self.regime = pd.read_parquet(
            self.paths.local_output_root / "D5_regime_state.parquet"
        )
        self.drift = pd.read_parquet(
            self.paths.local_output_root / "D5_topology_drift_alerts.parquet"
        )
        self.topology = load_yaml(D5_ROOT / "configs" / "common" / "topology.yaml")
        self.sensors = pd.DataFrame(
            load_yaml(D5_ROOT / "configs" / "common" / "sensors.yaml")["nodes"]
        )
        self.manifest = json.loads(
            (self.paths.local_output_root / "D5_run_manifest.json").read_text(encoding="utf-8")
        )
        self.meta = {
            "template_version": self.main["template_version"].iloc[0],
            "topology_version": self.main["topology_version"].iloc[0],
            "topology_hash": self.main["topology_hash"].iloc[0],
            "source_run_id": self.main["run_id"].iloc[0],
            "source_hash": hash_object(self.manifest),
        }

    def build(self) -> pd.DataFrame:
        rows: list[dict[str, Any]] = []
        self._figure_1(rows)
        self._figure_2(rows)
        self._figure_3(rows)
        self._figure_4(rows)
        self._figure_5(rows)
        output = pd.DataFrame(rows)
        for column in self.COLUMNS:
            if column not in output:
                output[column] = np.nan
        output = output[self.COLUMNS]
        parquet = self.paths.plot_data_root / "D5_plot_data.parquet"
        csv = self.paths.plot_data_root / "D5_plot_data.csv"
        output.to_parquet(parquet, index=False)
        output.to_csv(csv, index=False, encoding="utf-8-sig")
        metadata = {
            "generated_utc": pd.Timestamp.utcnow().isoformat(),
            "rows": len(output),
            "figure_ids": sorted(output["figure_id"].unique()),
            "source_run_id": self.meta["source_run_id"],
            "source_hash": self.meta["source_hash"],
            "plot_data_hash": hash_object(output.fillna("NA").to_dict("records")),
            "business_metrics_recomputed_by_figure_script": False,
        }
        (self.paths.plot_data_root / "D5_plot_data_manifest.json").write_text(
            json.dumps(metadata, indent=2, ensure_ascii=True), encoding="utf-8"
        )
        return output

    def _add(self, rows: list[dict[str, Any]], **record: Any) -> None:
        rows.append({**self.meta, **record})

    def _figure_1(self, rows: list[dict[str, Any]]) -> None:
        for node in self.sensors.itertuples(index=False):
            self._add(
                rows,
                figure_id="FigD5_1_framework",
                panel="a",
                record_type="node",
                x=node.sensor_id,
                x_numeric=float(node.coordinate[0]),
                y=str(node.coordinate[1]),
                value=float(node.coordinate[1]),
                group=node.analyte,
                sensor_id=node.sensor_id,
                analyte=node.analyte,
                context=node.zone_id,
                annotation=node.role,
                order=node.position_order,
            )
        coordinates = self.sensors.set_index("sensor_id")["coordinate"].to_dict()
        for edge in self.topology["edges"]:
            for order, sensor in enumerate([edge["source"], edge["target"]]):
                coordinate = coordinates[sensor]
                self._add(
                    rows,
                    figure_id="FigD5_1_framework",
                    panel="a",
                    record_type="edge",
                    x=edge["edge_id"],
                    x_numeric=float(coordinate[0]),
                    y=str(coordinate[1]),
                    value=float(coordinate[1]),
                    group=edge["edge_id"],
                    sensor_id=sensor,
                    context=edge["edge_type"],
                    annotation=edge["direction"],
                    order=order,
                )
        for pair in self.topology["twin_pairs"]:
            for order, sensor in enumerate([pair["sensor_a"], pair["sensor_b"]]):
                coordinate = coordinates[sensor]
                self._add(
                    rows,
                    figure_id="FigD5_1_framework",
                    panel="a",
                    record_type="edge",
                    x=pair["pair_id"],
                    x_numeric=float(coordinate[0]),
                    y=str(coordinate[1]),
                    value=float(coordinate[1]),
                    group=pair["pair_id"],
                    sensor_id=sensor,
                    context="parallel_peer",
                    annotation="bidirectional_peer",
                    order=order,
                )

        status_order = [
            "evaluable",
            "limited_support",
            "out_of_template",
            "not_evaluable",
        ]
        for analyte in ["DO", "ORP", "All"]:
            frame = self.main if analyte == "All" else self.main[self.main["analyte"].eq(analyte)]
            fractions = frame["evaluation_status"].value_counts(normalize=True)
            for order, name in enumerate(status_order):
                value = float(fractions.get(name, 0.0))
                self._add(
                    rows,
                    figure_id="FigD5_1_framework",
                    panel="b",
                    record_type="status_rate",
                    x=analyte,
                    x_numeric=["DO", "ORP", "All"].index(analyte),
                    y=name,
                    value=value,
                    group=name,
                    analyte=analyte,
                    annotation=f"{value:.1%}",
                    order=order,
                )

        stages = [
            ("Global context", "QR/QIR + time-of-day", "context"),
            ("Regime state", "Frozen regime assignment", "regime"),
            ("Role template", "Longitudinal + peer structure", "template"),
            ("Four evidence scores", "Profile / gradient / rank / representation", "evidence"),
            ("D5 raw", "Continuous structural score", "score"),
            ("Report or abstain", "Support- and OOD-aware interface", "report"),
        ]
        for order, (label, annotation, group) in enumerate(stages):
            self._add(
                rows,
                figure_id="FigD5_1_framework",
                panel="c",
                record_type="method_stage",
                x=label,
                x_numeric=order,
                y="method_pipeline",
                value=float(order),
                group=group,
                annotation=annotation,
                order=order,
            )

    def _figure_2(self, rows: list[dict[str, Any]]) -> None:
        daily = self.main.copy()
        daily["date"] = daily["timestamp"].dt.floor("D")
        daily["report_eligible_numeric"] = daily["D5_report_score"].notna().astype(float)
        daily["ood_numeric"] = daily["evaluation_status"].eq("out_of_template").astype(float)
        daily["l1_numeric"] = daily["support_level"].eq("L1").astype(float)
        daily = daily.groupby(["date", "sensor_id", "analyte"], as_index=False).agg(
            D5_raw=("D5_raw", lambda values: values.quantile(0.25)),
            report_eligible_rate=("report_eligible_numeric", "mean"),
            ood_rate=("ood_numeric", "mean"),
            l1_rate=("l1_numeric", "mean"),
        )
        sensor_order = self.sensors.sort_values(["analyte", "line_id", "position_order"])["sensor_id"].tolist()
        for record in daily.itertuples(index=False):
            for record_type, value in [
                ("daily_p25", record.D5_raw),
                ("report_eligible_rate", record.report_eligible_rate),
                ("ood_rate", record.ood_rate),
                ("l1_rate", record.l1_rate),
            ]:
                self._add(
                    rows,
                    figure_id="FigD5_2_spatiotemporal",
                    panel="a",
                    record_type=record_type,
                    x=record.date.isoformat(),
                    x_numeric=float(record.date.value / 1e9),
                    y=record.sensor_id,
                    value=float(value) if np.isfinite(value) else np.nan,
                    group=record.analyte,
                    sensor_id=record.sensor_id,
                    analyte=record.analyte,
                    order=sensor_order.index(record.sensor_id),
                )
        for event in self.events.sort_values(["min_D5_raw", "duration_h"]).head(3).itertuples(index=False):
            self._add(
                rows,
                figure_id="FigD5_2_spatiotemporal",
                panel="a",
                record_type="case_window",
                x=pd.Timestamp(event.start_ts).isoformat(),
                x_numeric=float(pd.Timestamp(event.start_ts).value / 1e9),
                y=event.sensor_id,
                value=float(pd.Timestamp(event.end_ts).value / 1e9),
                group=event.event_type,
                sensor_id=event.sensor_id,
                event_id=event.event_id,
                annotation="unlabeled candidate",
            )

        distribution = self.main.dropna(subset=["D5_raw"])
        sensor_stats = distribution.groupby(
            ["sensor_id", "analyte", "line_id", "position_order"], as_index=False
        ).agg(
            median=("D5_raw", "median"),
            q25=("D5_raw", lambda values: values.quantile(0.25)),
            q75=("D5_raw", lambda values: values.quantile(0.75)),
            low_fraction=("D5_raw", lambda values: values.lt(3.0).mean()),
            n_hours=("D5_raw", "size"),
        ).sort_values(["analyte", "position_order", "line_id"])
        for order, record in enumerate(sensor_stats.itertuples(index=False)):
            self._add(
                rows,
                figure_id="FigD5_2_spatiotemporal",
                panel="b",
                record_type="sensor_score_summary",
                x=record.sensor_id,
                x_numeric=float(order),
                y="D5_raw",
                value=float(record.median),
                value_low=float(record.q25),
                value_high=float(record.q75),
                target=float(record.low_fraction),
                group=record.analyte,
                sensor_id=record.sensor_id,
                analyte=record.analyte,
                annotation=f"n={record.n_hours:,}",
                order=order,
            )

        monthly = self.main.copy()
        monthly["month"] = monthly["timestamp"].dt.to_period("M").astype(str)
        monthly = monthly.groupby("month", as_index=False).agg(
            report_coverage=("D5_report_score", lambda values: values.notna().mean()),
            ood_rate=("evaluation_status", lambda values: values.eq("out_of_template").mean()),
            l1_rate=("support_level", lambda values: values.eq("L1").mean()),
        )
        for record in monthly.itertuples(index=False):
            for metric, value in [
                ("Report coverage", record.report_coverage),
                ("OOD", record.ood_rate),
                ("L1 support", record.l1_rate),
            ]:
                self._add(
                    rows,
                    figure_id="FigD5_2_spatiotemporal",
                    panel="c",
                    record_type="monthly_evidence_coverage",
                    x=record.month,
                    y=metric,
                    value=float(value),
                    group=metric,
                    annotation="same contract as FigD5_6c",
                )

    def _figure_3(self, rows: list[dict[str, Any]]) -> None:
        if self.events.empty:
            return
        event = self.events.sort_values(["min_D5_raw", "duration_h"]).iloc[0]
        start = pd.Timestamp(event["start_ts"]) - pd.Timedelta(hours=24)
        end = pd.Timestamp(event["end_ts"]) + pd.Timedelta(hours=24)
        case = self.main[
            (self.main["sensor_id"] == event["sensor_id"])
            & self.main["timestamp"].between(start, end)
        ]
        for record in case.itertuples(index=False):
            for metric in ["D5_raw", "Q_profile", "Q_gradient", "Q_rank", "Q_rep"]:
                self._add(
                    rows,
                    figure_id="FigD5_3_evidence",
                    panel="a",
                    record_type="case_timeseries",
                    x=record.timestamp.isoformat(),
                    x_numeric=float(record.timestamp.value / 1e9),
                    y=metric,
                    value=float(getattr(record, metric)) if np.isfinite(getattr(record, metric)) else np.nan,
                    group=metric,
                    sensor_id=record.sensor_id,
                    analyte=record.analyte,
                    event_id=event["event_id"],
                    annotation="unlabeled structural evidence",
                )
            self._add(
                rows,
                figure_id="FigD5_3_evidence",
                panel="a",
                record_type="regime_strip",
                x=record.timestamp.isoformat(),
                x_numeric=float(record.timestamp.value / 1e9),
                y=record.regime_state,
                value=float(record.active_regime_id),
                group=record.regime_state,
                sensor_id=record.sensor_id,
                event_id=event["event_id"],
            )

        topology_pairs = self.topology["twin_pairs"]
        target_sensor = str(event["sensor_id"])
        peer_sensor = next(
            (
                pair["sensor_b"] if pair["sensor_a"] == target_sensor else pair["sensor_a"]
                for pair in topology_pairs
                if target_sensor in {pair["sensor_a"], pair["sensor_b"]}
            ),
            None,
        )
        target_meta = self.sensors.set_index("sensor_id").loc[target_sensor]
        neighbors = self.sensors[
            self.sensors["analyte"].eq(target_meta["analyte"])
            & self.sensors["line_id"].eq(target_meta["line_id"])
            & self.sensors["sensor_id"].ne(target_sensor)
        ].copy()
        neighbors["distance"] = (neighbors["position_order"] - target_meta["position_order"]).abs()
        neighbor_sensor = neighbors.sort_values(["distance", "position_order"])["sensor_id"].iloc[0]
        raw_sensors = [target_sensor, peer_sensor, neighbor_sensor]
        raw = pd.read_parquet(self.paths.canonical_observations, columns=raw_sensors)
        raw = raw.loc[start:end].resample("1h").median()
        role_by_sensor = {
            target_sensor: "Target",
            peer_sensor: "Parallel peer",
            neighbor_sensor: "Same-line neighbor",
        }
        for timestamp_raw, values in raw.iterrows():
            for sensor in raw_sensors:
                value = values[sensor]
                self._add(
                    rows,
                    figure_id="FigD5_3_evidence",
                    panel="a",
                    record_type="raw_timeseries",
                    x=timestamp_raw.isoformat(),
                    x_numeric=float(timestamp_raw.value / 1e9),
                    y=sensor,
                    value=float(value) if np.isfinite(value) else np.nan,
                    group=role_by_sensor[sensor],
                    sensor_id=sensor,
                    analyte=target_meta["analyte"],
                    event_id=event["event_id"],
                )
        self._add(
            rows,
            figure_id="FigD5_3_evidence",
            panel="a",
            record_type="event_window",
            x=pd.Timestamp(event["start_ts"]).isoformat(),
            x_numeric=float(pd.Timestamp(event["start_ts"]).value / 1e9),
            y=target_sensor,
            value=float(pd.Timestamp(event["end_ts"]).value / 1e9),
            group="unlabeled candidate",
            sensor_id=target_sensor,
            event_id=event["event_id"],
        )

        center = pd.Timestamp(event["start_ts"]) + (
            pd.Timestamp(event["end_ts"]) - pd.Timestamp(event["start_ts"])
        ) / 2
        center_row = case.iloc[(case["timestamp"] - center).abs().argsort()[:1]]
        template_id = str(center_row["template_id_used"].iloc[0])
        template_book = self.paths.local_output_root / "D5_spatial_templates.xlsx"
        profile_centers = pd.read_excel(template_book, sheet_name="profile_centers")
        target_reference = profile_centers[
            profile_centers["template_id"].eq(template_id)
            & profile_centers["node_id"].eq(target_sensor)
        ]
        if not target_reference.empty:
            reference = target_reference.iloc[0]
            self._add(
                rows,
                figure_id="FigD5_3_evidence",
                panel="a",
                record_type="raw_reference",
                x=start.isoformat(),
                x_numeric=float(start.value / 1e9),
                y=target_sensor,
                value=float(reference["center"]),
                value_low=float(reference["center"] - reference["scale"]),
                value_high=float(reference["center"] + reference["scale"]),
                group="Role-template reference",
                sensor_id=target_sensor,
                event_id=event["event_id"],
                annotation=template_id,
            )
        timestamp = self.influence.iloc[
            (self.influence["timestamp"] - center).abs().argsort()[:1]
        ]["timestamp"].iloc[0]
        ranking = self.influence[self.influence["timestamp"] == timestamp].sort_values(
            "influence_score", ascending=False
        )
        for order, record in enumerate(ranking.itertuples(index=False)):
            for component, label in [
                ("contribution_leave_one_out", "Leave-one-out"),
                ("contribution_graph_energy", "Graph energy"),
                ("contribution_gradient", "Gradient"),
            ]:
                self._add(
                    rows,
                    figure_id="FigD5_3_evidence",
                    panel="b",
                    record_type="influence_component",
                    x=record.sensor_id,
                    x_numeric=order,
                    y="influence_score",
                    value=float(getattr(record, component)),
                    group=label,
                    sensor_id=record.sensor_id,
                    context=(
                        "target" if record.sensor_id == event["sensor_id"] else "other"
                    ),
                    event_id=event["event_id"],
                    annotation=record.attribution_method,
                    order=order,
                )
        nearest_influence = self.influence.iloc[
            (self.influence["timestamp"] - center).abs().argsort()[: len(self.sensors)]
        ]
        nearest_timestamp = nearest_influence["timestamp"].mode().iloc[0]
        nearest_influence = self.influence[self.influence["timestamp"].eq(nearest_timestamp)]
        coordinates = self.sensors.set_index("sensor_id")["coordinate"].to_dict()
        for record in nearest_influence.itertuples(index=False):
            coordinate = coordinates[record.sensor_id]
            self._add(
                rows,
                figure_id="FigD5_3_evidence",
                panel="c",
                record_type="topology_node",
                x=record.sensor_id,
                x_numeric=float(coordinate[0]),
                y=str(coordinate[1]),
                value=float(record.influence_score) if np.isfinite(record.influence_score) else 0.0,
                group="target" if record.sensor_id == target_sensor else "other",
                sensor_id=record.sensor_id,
                event_id=event["event_id"],
                annotation="normalized diagnostic contribution",
            )

        gradient_templates = pd.read_excel(template_book, sheet_name="gradient_templates")
        gradient_templates = gradient_templates[gradient_templates["template_id"].eq(template_id)]
        center_lookup = profile_centers[profile_centers["template_id"].eq(template_id)].set_index("node_id")
        edge_specs = list(self.topology["edges"]) + [
            {
                "edge_id": pair["pair_id"],
                "source": pair["sensor_a"],
                "target": pair["sensor_b"],
                "edge_type": "parallel_peer",
            }
            for pair in self.topology["twin_pairs"]
        ]
        full_raw = pd.read_parquet(self.paths.canonical_observations)
        full_center = full_raw.loc[start:end].resample("1h").median()
        full_values = full_center.iloc[
            (full_center.index - nearest_timestamp).to_series().abs().argsort()[:1]
        ].iloc[0]
        for edge in edge_specs:
            source_sensor = edge["source"]
            target_edge = edge["target"]
            if source_sensor not in full_values or target_edge not in full_values:
                continue
            observed_delta = float(full_values[target_edge] - full_values[source_sensor])
            if edge["edge_type"] == "longitudinal":
                reference = gradient_templates[gradient_templates["edge_id"].eq(edge["edge_id"])]
                if reference.empty:
                    continue
                expected_delta = float(reference["median"].iloc[0])
                scale = max(float(reference["scale"].iloc[0]), 1e-6)
            else:
                if source_sensor not in center_lookup.index or target_edge not in center_lookup.index:
                    continue
                expected_delta = float(
                    center_lookup.loc[target_edge, "center"] - center_lookup.loc[source_sensor, "center"]
                )
                scale = max(
                    float(
                        np.hypot(
                            center_lookup.loc[target_edge, "scale"],
                            center_lookup.loc[source_sensor, "scale"],
                        )
                    ),
                    1e-6,
                )
            residual = abs(observed_delta - expected_delta) / scale
            for order, sensor in enumerate([source_sensor, target_edge]):
                coordinate = coordinates[sensor]
                self._add(
                    rows,
                    figure_id="FigD5_3_evidence",
                    panel="c",
                    record_type="topology_edge",
                    x=edge["edge_id"],
                    x_numeric=float(coordinate[0]),
                    y=str(coordinate[1]),
                    value=float(residual),
                    group=edge["edge_type"],
                    sensor_id=sensor,
                    event_id=event["event_id"],
                    annotation="standardized edge residual",
                    order=order,
                )

    def _figure_4(self, rows: list[dict[str, Any]]) -> None:
        workbook = self.paths.local_output_root / "D5_validation_results.xlsx"
        acceptance = pd.read_excel(workbook, sheet_name="acceptance")
        metrics = pd.read_excel(workbook, sheet_name="metrics_by_scenario")
        negative = metrics[metrics["metric"] == "FAR"]
        top1 = metrics[
            (metrics["metric"] == "Top1")
            & metrics["scenario"].isin(["channel_swap", "role_offset", "role_substitution"])
        ]
        release_metrics = acceptance[
            acceptance["criterion"].isin(
                [
                    "swap_AUROC",
                    "swap_AUPRC",
                    "swap_Top1",
                    "common_mode_FAR",
                    "zone_coherent_FAR",
                    "switch_chatter_rate",
                ]
            )
        ]
        for order, record in enumerate(release_metrics.itertuples(index=False)):
            self._add(
                rows,
                figure_id="FigD5_4_validation",
                panel="a",
                record_type="acceptance_metric",
                x=record.criterion,
                x_numeric=order,
                y="estimate",
                value=float(record.estimate),
                value_low=float(record.ci95_low) if np.isfinite(record.ci95_low) else np.nan,
                value_high=float(record.ci95_high) if np.isfinite(record.ci95_high) else np.nan,
                target=float(record.target),
                group="pass" if record.passed else "fail",
                annotation=f"target {record.operator} {record.target:.2f}; n={record.n:g}",
                order=order,
            )
        for order, record in enumerate(top1.itertuples(index=False)):
            self._add(
                rows,
                figure_id="FigD5_4_validation",
                panel="b",
                record_type="top1_by_scenario",
                x=record.scenario,
                x_numeric=order,
                y="Top-1",
                value=float(record.estimate),
                value_low=float(record.ci95_low),
                value_high=float(record.ci95_high),
                target=0.80,
                group="pass" if record.estimate >= 0.80 else "fail",
                annotation=f"n={record.n:g}; {record.ci_method}",
                order=order,
            )
        for order, record in enumerate(negative.itertuples(index=False)):
            self._add(
                rows,
                figure_id="FigD5_4_validation",
                panel="c",
                record_type="negative_far",
                x=record.scenario,
                x_numeric=order,
                y="FAR",
                value=float(record.estimate),
                value_low=float(record.ci95_low),
                value_high=float(record.ci95_high),
                target=0.10,
                group="pass" if record.estimate <= 0.10 else "fail",
                order=order,
            )
        invariance = pd.read_excel(
            self.paths.sensitivity_output_root / "D5_track_invariance.xlsx",
            sheet_name="track_invariance",
        )
        targets = {"IE_track": 0.20, "event_jaccard": 0.80, "culprit_spearman": 0.80}
        for order, record in enumerate(invariance.itertuples(index=False)):
            if record.metric == "FAR_delta":
                continue
            self._add(
                rows,
                figure_id="FigD5_4_validation",
                panel="d",
                record_type="track_invariance",
                x=record.metric,
                x_numeric=order,
                y="estimate",
                value=float(record.estimate),
                target=targets[record.metric],
                group="pass" if record.passed else "fail",
                annotation=record.criterion,
                order=order,
            )

    def _figure_5(self, rows: list[dict[str, Any]]) -> None:
        for source, column in [
            ("Family support", "family_support_level"),
            ("Validated node", "support_level"),
        ]:
            counts = self.support.groupby(["analyte", column]).size()
            for order, ((analyte, level), value) in enumerate(counts.items()):
                self._add(
                    rows,
                    figure_id="FigD5_5_governance",
                    panel="a",
                    record_type="hierarchical_support_count",
                    x=analyte,
                    x_numeric=order,
                    y=source,
                    value=float(value),
                    group=level,
                    analyte=analyte,
                    context=source,
                    order=order,
                )

        family_l3 = self.support[
            self.support["family_support_level"].eq("L3")
        ].sort_values("target_sensor")
        for order, record in enumerate(family_l3.itertuples(index=False)):
            for metric, value, target in [
                (
                    "Bootstrap stability",
                    record.node_bootstrap_stability,
                    0.80,
                ),
                ("Holdout FAR", record.node_holdout_far, 0.15),
            ]:
                self._add(
                    rows,
                    figure_id="FigD5_5_governance",
                    panel="b",
                    record_type="node_validation",
                    x=record.target_sensor,
                    x_numeric=order,
                    y=metric,
                    value=float(value),
                    target=target,
                    group=metric,
                    sensor_id=record.target_sensor,
                    analyte=record.analyte,
                    context=record.support_level,
                    annotation=(
                        "Final L3"
                        if record.support_level == "L3"
                        else "Node validation downgrade"
                    ),
                    order=order,
                )

        interface_metrics = [
            (
                "Report score",
                int(self.report_interface["D5_report_score"].notna().sum()),
                len(self.report_interface),
                "report",
            ),
            (
                "Action-ready gate",
                int(self.gate_interface["d5_action_ready"].sum()),
                len(self.gate_interface),
                "gate",
            ),
            (
                "Process Guard active",
                int(
                    self.gate_interface[
                        "process_coherence_guard_active"
                    ].sum()
                ),
                len(self.gate_interface),
                "guard",
            ),
            (
                "Sensor Veto active",
                int(self.gate_interface["sensor_identity_veto_active"].sum()),
                len(self.gate_interface),
                "veto",
            ),
        ]
        for order, (label, count, total, group) in enumerate(interface_metrics):
            self._add(
                rows,
                figure_id="FigD5_5_governance",
                panel="c",
                record_type="interface_coverage",
                x=label,
                x_numeric=order,
                y="row fraction",
                value=float(count / total) if total else 0.0,
                group=group,
                annotation=f"{count:,}/{total:,}",
                order=order,
            )

        identity = self.d4_final.loc[
            self.d4_final["finalization_allowed"].fillna(False)
            & self.d4_final["D4_raw"].notna()
            & self.d4_final["D4_forDQR"].notna(),
            ["D4_raw", "D4_forDQR"],
        ].copy()
        if identity.empty:
            raise RuntimeError(
                "No finalized D4 rows are available for the independence audit"
            )
        max_delta = float(
            (identity["D4_forDQR"] - identity["D4_raw"]).abs().max()
        )
        audit_note = f"n={len(identity):,}; max |delta|={max_delta:.3g}"
        for order, record in enumerate(identity.itertuples(index=False)):
            self._add(
                rows,
                figure_id="FigD5_5_governance",
                panel="d",
                record_type="d4_numeric_independence",
                x=f"row_{order}",
                x_numeric=float(record.D4_raw),
                y="D4_forDQR",
                value=float(record.D4_forDQR),
                target=0.0,
                group="identity",
                annotation=audit_note if order == 0 else "",
                order=order,
            )
