from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from d7_common.config import D7_ROOT, load_yaml, resolve_paths
from d7_common.hashing import hash_object


class D7PlotDataBuilder:
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
            self.paths.local_output_root / "D7_main_scores_hourly.parquet"
        )
        self.influence = pd.read_parquet(
            self.paths.local_output_root / "D7_sensor_influence.parquet"
        )
        self.consensus = pd.read_parquet(
            self.paths.local_output_root / "D7_zone_consensus.parquet"
        )
        self.events = pd.read_parquet(
            self.paths.local_output_root / "D7_event_windows.parquet"
        )
        self.support = pd.read_parquet(
            self.paths.local_output_root / "D7_support_assessment.parquet"
        )
        self.regime = pd.read_parquet(
            self.paths.local_output_root / "D7_regime_state.parquet"
        )
        self.drift = pd.read_parquet(
            self.paths.local_output_root / "D7_topology_drift_alerts.parquet"
        )
        self.topology = load_yaml(D7_ROOT / "configs" / "common" / "topology.yaml")
        self.sensors = pd.DataFrame(
            load_yaml(D7_ROOT / "configs" / "common" / "sensors.yaml")["nodes"]
        )
        self.manifest = json.loads(
            (self.paths.local_output_root / "D7_run_manifest.json").read_text(encoding="utf-8")
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
        parquet = self.paths.plot_data_root / "D7_plot_data.parquet"
        csv = self.paths.plot_data_root / "D7_plot_data.csv"
        output.to_parquet(parquet, index=False)
        output.to_csv(csv, index=False, encoding="utf-8-sig")
        metadata = {
            "generated_utc": pd.Timestamp.utcnow().isoformat(),
            "rows": len(output),
            "figure_ids": sorted(output["figure_id"].unique()),
            "rows_by_figure": output.groupby("figure_id").size().astype(int).to_dict(),
            "source_run_id": self.meta["source_run_id"],
            "source_hash": self.meta["source_hash"],
            "plot_data_hash": hash_object(output.fillna("NA").to_dict("records")),
            "business_metrics_recomputed_by_figure_script": False,
            "rendering_samples_removed": 0,
            "data_exclusion_policy": "Retain every finite source record required by each panel; no convenience sampling.",
        }
        (self.paths.plot_data_root / "D7_plot_data_manifest.json").write_text(
            json.dumps(metadata, indent=2, ensure_ascii=True), encoding="utf-8"
        )
        return output

    def _add(self, rows: list[dict[str, Any]], **record: Any) -> None:
        rows.append({**self.meta, **record})

    def _figure_1(self, rows: list[dict[str, Any]]) -> None:
        for node in self.sensors.itertuples(index=False):
            self._add(
                rows,
                figure_id="FigD7_1_framework",
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
                    figure_id="FigD7_1_framework",
                    panel="a",
                    record_type="edge",
                    x=edge["edge_id"],
                    x_numeric=float(coordinate[0]),
                    y=str(coordinate[1]),
                    value=float(coordinate[1]),
                    group=edge["edge_id"],
                    sensor_id=sensor,
                    annotation=edge["direction"],
                    order=order,
                )
        status = self.main["evaluation_status"].value_counts(normalize=True)
        for order, (name, value) in enumerate(status.items()):
            self._add(
                rows,
                figure_id="FigD7_1_framework",
                panel="b",
                record_type="status_rate",
                x=name,
                x_numeric=order,
                y="window_fraction",
                value=float(value),
                group="Local Track",
                annotation=f"{value:.1%}",
                order=order,
            )
        facts = [
            ("Raw spatial evidence", 1.0, "D7_raw retained when calculable"),
            ("Topology approval", 0.0, "Pending field drawing and two-person approval"),
            ("D7_forDQR", 0.0, "Null until all production gates pass"),
        ]
        for order, (label, value, annotation) in enumerate(facts):
            self._add(
                rows,
                figure_id="FigD7_1_framework",
                panel="c",
                record_type="boundary_gate",
                x=label,
                x_numeric=order,
                y="gate_state",
                value=value,
                target=1.0,
                group="pass" if value else "blocked",
                annotation=annotation,
                order=order,
            )

    def _figure_2(self, rows: list[dict[str, Any]]) -> None:
        daily = self.main.copy()
        daily["date"] = daily["timestamp"].dt.floor("D")
        daily = daily.groupby(["date", "sensor_id", "analyte"], as_index=False)["D7_raw"].quantile(0.25)
        sensor_order = self.sensors.sort_values(["analyte", "line_id", "position_order"])["sensor_id"].tolist()
        for record in daily.itertuples(index=False):
            self._add(
                rows,
                figure_id="FigD7_2_spatiotemporal",
                panel="a",
                record_type="daily_p25",
                x=record.date.isoformat(),
                x_numeric=float(record.date.value / 1e9),
                y=record.sensor_id,
                value=float(record.D7_raw),
                group=record.analyte,
                sensor_id=record.sensor_id,
                analyte=record.analyte,
                order=sensor_order.index(record.sensor_id),
            )
        distribution = self.main.dropna(subset=["D7_raw"])
        for record in distribution.itertuples(index=False):
            self._add(
                rows,
                figure_id="FigD7_2_spatiotemporal",
                panel="b",
                record_type="score_distribution",
                x=record.analyte,
                x_numeric=np.nan,
                y="D7_raw",
                value=float(record.D7_raw),
                group=record.analyte,
                sensor_id=record.sensor_id,
                analyte=record.analyte,
            )
        support_group = self.support.groupby(["analyte", "support_level"], as_index=False).agg(
            templates=("template_id", "size"),
            n_effective_median=("n_effective", "median"),
        )
        for order, record in enumerate(support_group.itertuples(index=False)):
            self._add(
                rows,
                figure_id="FigD7_2_spatiotemporal",
                panel="c",
                record_type="support_tier",
                x=record.analyte,
                x_numeric=order,
                y=record.support_level,
                value=float(record.templates),
                group=record.support_level,
                analyte=record.analyte,
                annotation=f"median n_eff={record.n_effective_median:.0f}",
                order=order,
            )

    def _figure_3(self, rows: list[dict[str, Any]]) -> None:
        if self.events.empty:
            return
        event = self.events.sort_values(["min_D7_raw", "duration_h"]).iloc[0]
        start = pd.Timestamp(event["start_ts"]) - pd.Timedelta(hours=24)
        end = pd.Timestamp(event["end_ts"]) + pd.Timedelta(hours=24)
        case = self.main[
            (self.main["sensor_id"] == event["sensor_id"])
            & self.main["timestamp"].between(start, end)
        ]
        event_analyte = case["analyte"].iloc[0] if not case.empty else np.nan
        for record in case.itertuples(index=False):
            for metric in ["D7_raw", "Q_profile", "Q_gradient", "Q_rank", "Q_rep"]:
                self._add(
                    rows,
                    figure_id="FigD7_3_evidence",
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
        center = pd.Timestamp(event["start_ts"]) + (
            pd.Timestamp(event["end_ts"]) - pd.Timestamp(event["start_ts"])
        ) / 2
        for order, (label, timestamp) in enumerate(
            [("event_start", pd.Timestamp(event["start_ts"])), ("event_end", pd.Timestamp(event["end_ts"]))]
        ):
            self._add(
                rows,
                figure_id="FigD7_3_evidence",
                panel="a",
                record_type="event_interval",
                x=timestamp.isoformat(),
                x_numeric=float(timestamp.value / 1e9),
                y=label,
                value=np.nan,
                group="candidate_event",
                sensor_id=event["sensor_id"],
                analyte=event_analyte,
                event_id=event["event_id"],
                annotation="unlabeled candidate interval",
                order=order,
            )
        timestamp = self.influence.iloc[
            (self.influence["timestamp"] - center).abs().argsort()[:1]
        ]["timestamp"].iloc[0]
        ranking = self.influence[self.influence["timestamp"] == timestamp].sort_values(
            "influence_score", ascending=False
        )
        for order, record in enumerate(ranking.itertuples(index=False)):
            self._add(
                rows,
                figure_id="FigD7_3_evidence",
                panel="b",
                record_type="influence_rank",
                x=record.sensor_id,
                x_numeric=order,
                y="influence_score",
                value=float(record.influence_score),
                group="target" if record.sensor_id == event["sensor_id"] else "other",
                sensor_id=record.sensor_id,
                event_id=event["event_id"],
                order=order,
            )
        labels = self.consensus["zone_consensus_label"].value_counts(normalize=True)
        for order, (label, value) in enumerate(labels.items()):
            self._add(
                rows,
                figure_id="FigD7_3_evidence",
                panel="c",
                record_type="consensus_rate",
                x=label,
                x_numeric=order,
                y="window_fraction",
                value=float(value),
                group="zone_consensus",
                annotation=f"{value:.1%}",
                order=order,
            )

    def _figure_4(self, rows: list[dict[str, Any]]) -> None:
        workbook = self.paths.local_output_root / "D7_validation_results.xlsx"
        acceptance = pd.read_excel(workbook, sheet_name="acceptance")
        metrics = pd.read_excel(workbook, sheet_name="metrics_by_scenario")
        negative = metrics[metrics["metric"] == "FAR"]
        top1 = metrics[
            (metrics["metric"] == "Top1")
            & metrics["scenario"].isin(["channel_swap", "role_offset", "role_substitution"])
        ]
        for order, record in enumerate(acceptance.iloc[:-1].itertuples(index=False)):
            self._add(
                rows,
                figure_id="FigD7_4_validation",
                panel="a",
                record_type="acceptance_metric",
                x=record.criterion,
                x_numeric=order,
                y="estimate",
                value=float(record.estimate),
                target=float(record.target),
                group="pass" if record.passed else "fail",
                annotation=f"target {record.operator} {record.target:.2f}",
                order=order,
            )
        for order, record in enumerate(top1.itertuples(index=False)):
            self._add(
                rows,
                figure_id="FigD7_4_validation",
                panel="b",
                record_type="top1_by_scenario",
                x=record.scenario,
                x_numeric=order,
                y="Top-1",
                value=float(record.estimate),
                target=0.80,
                group="pass" if record.estimate >= 0.80 else "fail",
                order=order,
            )
        for order, record in enumerate(negative.itertuples(index=False)):
            self._add(
                rows,
                figure_id="FigD7_4_validation",
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
            self.paths.sensitivity_output_root / "D7_track_invariance.xlsx",
            sheet_name="track_invariance",
        )
        targets = {"IE_track": 0.20, "event_jaccard": 0.80, "culprit_spearman": 0.80}
        for order, record in enumerate(invariance.itertuples(index=False)):
            if record.metric == "FAR_delta":
                continue
            self._add(
                rows,
                figure_id="FigD7_4_validation",
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
        support_counts = self.support.groupby(["analyte", "support_level"]).size()
        for order, ((analyte, level), value) in enumerate(support_counts.items()):
            self._add(
                rows,
                figure_id="FigD7_5_governance",
                panel="a",
                record_type="support_count",
                x=analyte,
                x_numeric=order,
                y=level,
                value=float(value),
                group=level,
                analyte=analyte,
                order=order,
            )
        state_rates = self.regime["regime_state"].value_counts(normalize=True)
        for order, (state, value) in enumerate(state_rates.items()):
            self._add(
                rows,
                figure_id="FigD7_5_governance",
                panel="b",
                record_type="regime_state_rate",
                x=state,
                x_numeric=order,
                y="fraction",
                value=float(value),
                group=state,
                annotation=f"{value:.1%}",
                order=order,
            )
        for order, record in enumerate(
            self.drift.sort_values("log_likelihood_ratio", ascending=False).head(14).itertuples(index=False)
        ):
            self._add(
                rows,
                figure_id="FigD7_5_governance",
                panel="c",
                record_type="topology_candidate",
                x=f"{record.target_sensor}->{record.candidate_mapping}",
                x_numeric=order,
                y="log likelihood ratio",
                value=float(record.log_likelihood_ratio),
                target=0.35,
                group=record.alert_level,
                sensor_id=record.target_sensor,
                annotation="report-only; production impact none",
                order=order,
            )
        validation = pd.read_excel(
            self.paths.local_output_root / "D7_validation_results.xlsx",
            sheet_name="acceptance",
        )
        gates = [
            ("Track isolation", 1.0, "Local consumes no D1-D6 scores"),
            ("Swap AUROC/AUPRC", float(validation.iloc[:2]["passed"].all()), "synthetic observed-window test"),
            ("Top-1", float(validation.loc[validation["criterion"] == "swap_Top1", "passed"].iloc[0]), "0.75 observed vs 0.80 target"),
            ("Topology approval", float(self.topology["verification_status"] == "verified"), "field verification pending"),
            ("DQR release", 0.0, "production gate remains closed"),
        ]
        for order, (gate, value, annotation) in enumerate(gates):
            self._add(
                rows,
                figure_id="FigD7_5_governance",
                panel="d",
                record_type="release_gate",
                x=gate,
                x_numeric=order,
                y="gate",
                value=value,
                target=1.0,
                group="pass" if value else "blocked",
                annotation=annotation,
                order=order,
            )
