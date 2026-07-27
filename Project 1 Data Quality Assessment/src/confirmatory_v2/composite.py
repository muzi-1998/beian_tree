from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from .common import CONFIG_ROOT, PROJECT_ROOT, moving_block_bootstrap_mean, read_yaml


def _load_d1() -> pd.DataFrame:
    path = PROJECT_ROOT / "D1 Sensor health" / "outputs" / "data" / "D1_main_scores_min.xlsx"
    wide = pd.read_excel(path, sheet_name="D1_total_hourly")
    wide["timestamp"] = pd.to_datetime(wide["timestamp"])
    return wide.melt(id_vars="timestamp", var_name="sensor_id", value_name="D1_total")


def _load_d2() -> pd.DataFrame:
    path = (
        PROJECT_ROOT
        / "D2 Temporal Continuity & Information Availability"
        / "artifacts"
        / "data"
        / "D2_main_scores_hourly.xlsx"
    )
    frame = pd.read_excel(path, sheet_name="D2_scores")
    frame = frame.rename(columns={frame.columns[0]: "timestamp"})
    frame["timestamp"] = pd.to_datetime(frame["timestamp"])
    return frame[
        [
            "timestamp",
            "sensor_id",
            "D2_total",
            "usable_tag",
            "veto_flag",
            "veto_reason",
            "run_id",
            "calibration_id",
        ]
    ].rename(
        columns={
            "run_id": "D2_run_id",
            "calibration_id": "D2_calibration_id",
            "veto_flag": "D2_veto_flag",
            "veto_reason": "D2_veto_reason",
        }
    )


def _load_d5() -> pd.DataFrame:
    path = (
        PROJECT_ROOT
        / "D5 Topological Role Consistency and Structural Representativeness"
        / "outputs"
        / "local"
        / "D5_report_interface.parquet"
    )
    frame = pd.read_parquet(path)
    frame["timestamp"] = pd.to_datetime(frame["timestamp"])
    return frame[
        [
            "timestamp",
            "sensor_id",
            "pair_id",
            "D5_report_score",
            "uncertainty",
            "evaluation_status",
            "report_eligible",
            "support_level",
            "run_id",
            "template_hash",
            "topology_hash",
        ]
    ].rename(columns={"run_id": "D5_run_id", "uncertainty": "D5_uncertainty"})


def _expand_d3_gate(gate: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for hours_back in range(2, 0, -1):
        block = gate.copy()
        block["timestamp"] = pd.to_datetime(block["timestamp"]) - pd.Timedelta(hours=hours_back)
        rows.append(block)
    expanded = pd.concat(rows, ignore_index=True)
    precedence = pd.CategoricalDtype(["Pass", "Warn", "Fail"], ordered=True)
    expanded["D3_gate_status"] = expanded["D3_gate_status"].astype(precedence)
    expanded = (
        expanded.sort_values("D3_gate_status")
        .groupby(["timestamp", "sensor_id"], as_index=False)
        .tail(1)
    )
    expanded["D3_gate_status"] = expanded["D3_gate_status"].astype(str)
    return expanded


def build_node_scores(d3_gate: pd.DataFrame) -> pd.DataFrame:
    node = _load_d1().merge(_load_d2(), on=["timestamp", "sensor_id"], how="outer")
    node = node.merge(_load_d5(), on=["timestamp", "sensor_id"], how="outer")
    node = node.merge(
        _expand_d3_gate(d3_gate)[
            [
                "timestamp",
                "sensor_id",
                "D3_gate_status",
                "D3_hard_fail",
                "D3_soft_warning",
                "D3_rate_warning",
            ]
        ],
        on=["timestamp", "sensor_id"],
        how="left",
    )
    node["evaluable_D1"] = node["D1_total"].notna()
    node["evaluable_D2"] = node["D2_total"].notna()
    node["evaluable_D5"] = node["report_eligible"].fillna(False) & node[
        "D5_report_score"
    ].notna()
    score_columns = ["D1_total", "D2_total", "D5_report_score"]
    eligibility = node[["evaluable_D1", "evaluable_D2", "evaluable_D5"]].to_numpy(bool)
    scores = node[score_columns].to_numpy(dtype=float)
    eligible_scores = np.where(eligibility, scores, np.nan)
    node["effective_dimension_count"] = eligibility.sum(axis=1)
    node["effective_weight_sum"] = node["effective_dimension_count"] / 3.0
    node["Q_node_diagnostic"] = np.nanmean(eligible_scores, axis=1)
    node["Q_node"] = node["Q_node_diagnostic"].where(
        node["effective_dimension_count"].ge(2)
    )
    node["Q_min"] = np.nanmin(eligible_scores, axis=1)
    node.loc[node["effective_dimension_count"].eq(0), ["Q_node_diagnostic", "Q_min"]] = np.nan
    node["coverage_class"] = node["effective_dimension_count"].map(
        {3: "full", 2: "basic", 1: "limited", 0: "insufficient"}
    )
    node["contains_D5"] = node["evaluable_D5"]
    node["D3_gate_status"] = node["D3_gate_status"].fillna("NotEvaluated")
    node["physical_warning"] = node["D3_gate_status"].eq("Warn")
    node["unsafe_or_invalid"] = node["D3_gate_status"].eq("Fail")
    node["high_confidence_grade_eligible"] = (
        node["effective_dimension_count"].ge(2) & ~node["unsafe_or_invalid"]
    )
    node = node.sort_values(["sensor_id", "timestamp"]).reset_index(drop=True)
    for persistence in (2, 3):
        low = node["Q_min"].lt(3.0) & node["Q_node"].notna()
        run = low.astype(int).groupby(
            [
                node["sensor_id"],
                (~low | node.groupby("sensor_id")["timestamp"].diff().ne(pd.Timedelta(hours=1)))
                .groupby(node["sensor_id"])
                .cumsum(),
            ]
        ).cumsum()
        node[f"bottleneck_gate_{persistence}h"] = low & run.ge(persistence)
    return node


def build_pair_scores(node: pd.DataFrame) -> pd.DataFrame:
    path = (
        PROJECT_ROOT
        / "D4 Parallel-redundancy Temporal Consistency"
        / "outputs"
        / "data"
        / "D4_main_scores.xlsx"
    )
    d4 = pd.read_excel(path, sheet_name="main_scores")
    d4["timestamp"] = pd.to_datetime(d4["timestamp"])
    target = node[
        ["timestamp", "sensor_id", "Q_node", "coverage_class", "D3_gate_status"]
    ].rename(
        columns={
            "sensor_id": "target_sensor_id",
            "Q_node": "Q_node_target",
            "coverage_class": "coverage_target",
            "D3_gate_status": "D3_gate_target",
        }
    )
    reference = target.rename(
        columns={
            "target_sensor_id": "reference_sensor_id",
            "Q_node_target": "Q_node_reference",
            "coverage_target": "coverage_reference",
            "D3_gate_target": "D3_gate_reference",
        }
    )
    pair = d4.merge(
        target,
        left_on=["timestamp", "sensor_id"],
        right_on=["timestamp", "target_sensor_id"],
        how="left",
    ).merge(
        reference,
        left_on=["timestamp", "pair_sensor_id"],
        right_on=["timestamp", "reference_sensor_id"],
        how="left",
    )
    pair["contains_D4"] = pair["D4_raw"].notna() & pair["usable_for_D4"].fillna(False)
    components = pair[["Q_node_target", "Q_node_reference", "D4_raw"]]
    pair["Q_pair"] = components.mean(axis=1).where(
        pair["contains_D4"]
        & pair["Q_node_target"].notna()
        & pair["Q_node_reference"].notna()
    )
    pair["effective_component_count"] = components.notna().sum(axis=1)
    pair["D3_gate_status"] = np.select(
        [
            pair[["D3_gate_target", "D3_gate_reference"]].eq("Fail").any(axis=1),
            pair[["D3_gate_target", "D3_gate_reference"]].eq("Warn").any(axis=1),
        ],
        ["Fail", "Warn"],
        default="Pass",
    )
    return pair


def build_plant_summary(node: pd.DataFrame, pair: pd.DataFrame) -> pd.DataFrame:
    node_daily = (
        node.assign(date=node["timestamp"].dt.floor("1d"))
        .groupby("date", as_index=False)
        .agg(
            node_score_median=("Q_node", "median"),
            node_score_p10=("Q_node", lambda values: values.quantile(0.10)),
            node_full_coverage_rate=("coverage_class", lambda values: values.eq("full").mean()),
            node_insufficient_rate=(
                "coverage_class",
                lambda values: values.eq("insufficient").mean(),
            ),
            D3_fail_hours=("D3_gate_status", lambda values: values.eq("Fail").sum()),
            D3_warn_hours=("D3_gate_status", lambda values: values.eq("Warn").sum()),
        )
    )
    pair_daily = (
        pair.assign(date=pair["timestamp"].dt.floor("1d"))
        .groupby("date", as_index=False)
        .agg(
            pair_score_median=("Q_pair", "median"),
            pair_score_p10=("Q_pair", lambda values: values.quantile(0.10)),
            pair_evaluable_rate=("Q_pair", lambda values: values.notna().mean()),
        )
    )
    return node_daily.merge(pair_daily, on="date", how="outer").sort_values("date")


def composite_uncertainty(node: pd.DataFrame) -> pd.DataFrame:
    sap = read_yaml(CONFIG_ROOT / "statistical_analysis_plan_v2.yaml")
    repetitions = int(sap["uncertainty"]["repetitions"])
    rng = np.random.default_rng(int(sap["uncertainty"]["seed"]))
    plant_hour = (
        node.groupby("timestamp", as_index=False)
        .agg(Q_node=("Q_node", "median"), coverage=("Q_node", lambda values: values.notna().mean()))
        .dropna(subset=["Q_node"])
    )
    plant_hour["month"] = plant_hour["timestamp"].dt.to_period("M").astype(str)
    rows = []
    for month, frame in plant_hour.groupby("month"):
        for label, block_hours in (
            ("main_7d", int(sap["uncertainty"]["main_block_hours"])),
            ("sensitivity_48h", int(sap["uncertainty"]["sensitivity_block_hours"])),
        ):
            samples = moving_block_bootstrap_mean(
                frame["Q_node"].to_numpy(),
                block_size=block_hours,
                repetitions=repetitions,
                rng=rng,
            )
            rows.append(
                {
                    "month": month,
                    "method": label,
                    "block_hours": block_hours,
                    "repetitions": repetitions,
                    "estimate": float(frame["Q_node"].mean()),
                    "ci_low": float(np.nanquantile(samples, 0.025)),
                    "ci_high": float(np.nanquantile(samples, 0.975)),
                    "n_plant_hours": len(frame),
                    "analysis_unit": "plant_hour_joint_across_dimensions",
                }
            )
    return pd.DataFrame(rows)


def dimension_ablation(node: pd.DataFrame) -> pd.DataFrame:
    rows = []
    full = node["Q_node"]
    mapping = {"D1": "D1_total", "D2": "D2_total", "D5": "D5_report_score"}
    for dimension, column in mapping.items():
        kept = [value for key, value in mapping.items() if key != dimension]
        variant = node[kept].mean(axis=1, skipna=True)
        valid = full.notna() & variant.notna()
        rows.append(
            {
                "variant": f"without_{dimension}",
                "spearman_vs_full": float(spearmanr(full[valid], variant[valid]).statistic),
                "mean_score_change": float((variant[valid] - full[valid]).mean()),
                "p90_absolute_change": float(
                    (variant[valid] - full[valid]).abs().quantile(0.90)
                ),
                "n_sensor_hours": int(valid.sum()),
            }
        )
    for dimension, column in mapping.items():
        valid = full.notna() & node[column].notna()
        rows.append(
            {
                "variant": f"{dimension}_only",
                "spearman_vs_full": float(
                    spearmanr(full[valid], node.loc[valid, column]).statistic
                ),
                "mean_score_change": float((node.loc[valid, column] - full[valid]).mean()),
                "p90_absolute_change": float(
                    (node.loc[valid, column] - full[valid]).abs().quantile(0.90)
                ),
                "n_sensor_hours": int(valid.sum()),
            }
        )
    return pd.DataFrame(rows)


def run_composite(output_dir: Path, d3_gate: pd.DataFrame) -> dict[str, pd.DataFrame]:
    node = build_node_scores(d3_gate)
    pair = build_pair_scores(node)
    plant = build_plant_summary(node, pair)
    uncertainty = composite_uncertainty(node)
    ablation = dimension_ablation(node)
    outputs = {
        "WWDQS_node_scores": node,
        "WWDQS_pair_scores": pair,
        "WWDQS_plant_summary": plant,
        "WWDQS_block_bootstrap": uncertainty,
        "WWDQS_dimension_ablation": ablation,
    }
    for name, frame in outputs.items():
        frame.to_parquet(output_dir / f"{name}.parquet", index=False)
    return outputs

