"""Export the full observed period with explicit retrospective/prospective boundaries."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from export_dqr_forcing import DO, DO6, ORP, OUT as HOLDOUT_OUT, REVISED, aggregate_complete, decide
from prepare_sumo_inputs import OUTPUT_DIR as PREPARED, ROOT, sha256

HERE = Path(__file__).resolve().parent
OUT = PREPARED / "dqr_full_period"
OLD_DQR = ROOT / "DQR Multidimensional Aggregation and Evidence-Aware Integration/outputs/aggregation_v2_4"
OLD_NODE = OLD_DQR / "data/DQR_node_scores_v2.4.parquet"
OLD_MANIFEST = OLD_DQR / "manifests/DQR_publication_manifest.json"
OLD_RAW = ROOT / "1.1 Decomposition/outputs/parquet/time_base_1min_raw.parquet"
BOUNDS = ROOT / "D3 Physical rationality and rate constraints/configs/d3_physical_bounds.yaml"
D5_AUDIT = ROOT / "D5 Topological Role Consistency and Structural Representativeness/outputs/audit/support_migration/D5_support_migration_manifest.json"
REVISED_MANIFEST = REVISED / "Reevaluation_publication_manifest.json"
PREPARED_MANIFEST = PREPARED / "SUMO_input_manifest.json"
HOLDOUT_MANIFEST = HOLDOUT_OUT / "DQR_forcing_manifest.json"
START = pd.Timestamp("2025-08-01 00:00:00")
BOUNDARY = pd.Timestamp("2026-04-14 00:00:00")
END = pd.Timestamp("2026-07-31 00:00:00")
WINDOW_DAYS = 14


def same_hour_evidence(index: pd.DatetimeIndex, evidence: pd.DataFrame) -> pd.DataFrame:
    """Join retrospective hourly labels to the minutes they summarize."""
    fields = ["timestamp", "Q_node_available", "E_node", "D3_gate_status", "D5_report_score", "coverage_class"]
    hourly = evidence[fields].drop_duplicates("timestamp").set_index("timestamp")
    joined = hourly.reindex(index.floor("h"))
    joined.index = index
    return joined


def historical_sensor(sensor, raw, old_raw, node, zero_low):
    evidence = same_hour_evidence(raw.index, node.loc[node.sensor_id.eq(sensor)])
    result = decide(raw, evidence, is_do=sensor in DO, zero_low=zero_low, low_threshold=3.0)
    source_unassessed = raw.notna() & old_raw.isna()
    result.loc[source_unassessed, ["dqr_measurement", "forcing"]] = np.nan
    result.loc[source_unassessed, "action"] = "UNASSESSED"
    result.loc[source_unassessed, "reason"] = "observation_not_present_in_historical_DQR_source"
    result["source_unassessed"] = source_unassessed
    result["source_period"] = "retrospective_same_hour_conditioning"
    result["Q_node_available"] = evidence.Q_node_available
    result["E_node"] = evidence.E_node
    result["D3_gate_status"] = evidence.D3_gate_status
    result["D5_report_score"] = evidence.D5_report_score
    result["coverage_class"] = evidence.coverage_class
    result["decision_at"] = pd.NaT
    return result


def window_table(common5, forcing5, quality5, unassessed5, process, evidence_hourly):
    required = [
        "进水瞬时流量（m³/h）", "进水COD（mg/L）", "进水氨氮（mg/L）", "进水总氮（mg/L）", "进水温度（℃）",
        "1#生物池外回流流量（m³/h）", "2#生物池外回流流量（m³/h）", "1#生物池内回流流量（m³/h）",
        "2#生物池内回流流量（m³/h）", "剩余污泥流量（m³/h）", "乙酸钠流量计2（m³/h）", "乙酸钠流量计4（m³/h）",
    ]
    rows = []
    bins = WINDOW_DAYS * 24 * 12
    for start in pd.date_range(START.normalize(), END.normalize() - pd.Timedelta(days=WINDOW_DAYS), freq="D"):
        end = start + pd.Timedelta(days=WINDOW_DAYS)
        ix = (forcing5.index >= start) & (forcing5.index < end)
        q = quality5.loc[ix]
        u = unassessed5.loc[ix]
        c = common5.loc[ix]
        f = forcing5.loc[ix]
        proc = process.loc[ix, required]
        hourly = evidence_hourly.loc[(evidence_hourly.timestamp >= start) & (evidence_hourly.timestamp < end)]
        phase = "retrospective_development" if end <= BOUNDARY else "revised_temporal_re_evaluation" if start >= BOUNDARY else "boundary_straddling"
        rows.append({
            "start": start, "end_exclusive": end, "phase": phase,
            "DO6_quality_excluded_bins": int(q[DO6].sum().sum()),
            "DO6_quality_excluded_pct_raw_valid": 100 * q[DO6].sum().sum() / max(1, c[DO6].notna().sum().sum()),
            "ORP_quality_excluded_bins": int(q[ORP].sum().sum()),
            "ORP_quality_excluded_pct_raw_valid": 100 * q[ORP].sum().sum() / max(1, c[ORP].notna().sum().sum()),
            "source_unassessed_bins": int(u.sum().sum()),
            "DO6_common_complete_pct": 100 * c[DO6].notna().all(axis=1).mean(),
            "DO6_DQR_complete_pct": 100 * f[DO6].notna().all(axis=1).mean(),
            "DO8_DQR_complete_pct": 100 * f[DO].notna().all(axis=1).mean(),
            "ORP6_DQR_complete_pct": 100 * f[ORP].notna().all(axis=1).mean(),
            "required_process_complete_pct": 100 * proc.notna().all(axis=1).mean(),
            "joint_DO8_process_complete_pct": 100 * (f[DO].notna().all(axis=1) & proc.notna().all(axis=1)).mean(),
            "joint_DO8_ORP6_process_complete_pct": 100 * (f[DO + ORP].notna().all(axis=1) & proc.notna().all(axis=1)).mean(),
            "D5_report_available_pct": 100 * hourly.D5_report_score.notna().mean(),
            "full_evidence_pct": 100 * hourly.E_node.eq(1).mean(),
            "expected_5min_bins": bins,
        })
    result = pd.DataFrame(rows)
    result["contrast_rank"] = result[["DO6_quality_excluded_bins", "ORP_quality_excluded_bins"]].sum(axis=1).rank(method="min", ascending=False).astype(int)
    result["direct_run_rank"] = result["joint_DO8_ORP6_process_complete_pct"].rank(method="min", ascending=False).astype(int)
    return result


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    raw = pd.read_parquet(PREPARED / "SUMO_DO_ORP_1min_raw.parquet")
    raw.columns = [c.split("（")[0] for c in raw.columns]
    raw = raw.loc[(raw.index >= START) & (raw.index < END), DO + ORP]
    old_raw = pd.read_parquet(OLD_RAW).reindex(raw.index)[DO + ORP]
    old_node = pd.read_parquet(OLD_NODE)
    future_audit = pd.read_parquet(HOLDOUT_OUT / "do_orp_strategy_audit_1min.parquet")
    future_audit["sensor_id"] = future_audit.sensor_id.astype(str)
    future_audit = future_audit.loc[future_audit.datetime.ge(BOUNDARY)]
    bounds = yaml.safe_load(BOUNDS.read_text(encoding="utf-8"))

    parts = []
    for sensor in DO + ORP:
        hist_raw = raw.loc[raw.index < BOUNDARY, sensor]
        hist = historical_sensor(sensor, hist_raw, old_raw.loc[hist_raw.index, sensor], old_node, bounds["sensor_overrides"].get(sensor, {}).get("zero_equivalence_low"))
        future = future_audit.loc[future_audit.sensor_id.eq(sensor)].set_index("datetime").sort_index()
        common_cols = ["raw", "common", "dqr_measurement", "forcing", "action", "reason", "repair_requested", "low_trigger", "gate_fail", "native_missing", "technical_invalid", "zero_equivalent", "evidence_limited", "repair_method", "repair_uncertainty", "Q_node_available", "E_node", "D3_gate_status", "D5_report_score", "coverage_class", "decision_at"]
        future = future[common_cols].copy()
        future["source_unassessed"] = False
        future["source_period"] = "revised_temporal_decision_clock"
        combined = pd.concat([hist, future]).sort_index()
        if not combined.index.equals(raw.index):
            raise ValueError(f"Full minute timebase mismatch for {sensor}")
        combined["sensor_id"] = sensor
        parts.append(combined.reset_index(names="datetime"))

    audit = pd.concat(parts, ignore_index=True)
    for column in ["sensor_id", "action", "reason", "source_period", "D3_gate_status", "coverage_class", "repair_method"]:
        audit[column] = audit[column].astype("category")
    audit.to_parquet(OUT / "DQR_DO_ORP_full_period_1min_long.parquet", index=False)
    forcing = audit.pivot(index="datetime", columns="sensor_id", values="forcing")[DO + ORP]
    common = audit.pivot(index="datetime", columns="sensor_id", values="common")[DO + ORP]
    measurement = audit.pivot(index="datetime", columns="sensor_id", values="dqr_measurement")[DO + ORP]
    forcing5, common5, raw5 = aggregate_complete(forcing), aggregate_complete(common), aggregate_complete(raw)
    quality = audit.reason.isin(["DQR_low_quality_no_qualified_repair", "gate_fail_no_qualified_repair"])
    quality1 = audit.assign(flag=quality).pivot(index="datetime", columns="sensor_id", values="flag")[DO + ORP]
    unassessed1 = audit.pivot(index="datetime", columns="sensor_id", values="source_unassessed")[DO + ORP]
    quality5 = quality1.resample("5min").max().fillna(False).astype(bool) & common.resample("5min").count().eq(5)
    unassessed5 = unassessed1.resample("5min").max().fillna(False).astype(bool) & common.resample("5min").count().eq(5)

    def save(frame, name):
        value = frame.copy()
        value.index.name = "datetime"
        value.insert(0, "time_days", (value.index - START).total_seconds() / 86400)
        value.to_csv(OUT / name, encoding="utf-8-sig", date_format="%Y-%m-%d %H:%M:%S", float_format="%.10g")

    save(forcing5[DO], "DQR_DO8_5min_20250801_20260730.csv")
    save(forcing5[ORP], "DQR_ORP6_5min_20250801_20260730.csv")
    save(raw5[DO + ORP], "Raw_DO_ORP14_5min_20250801_20260730.csv")
    save(common5[DO + ORP], "Common_technical_DO_ORP14_5min_20250801_20260730.csv")
    measurement.to_csv(OUT / "DQR_DO_ORP_measurement_full_period_1min.csv.gz", compression="gzip", encoding="utf-8-sig", index_label="datetime")

    evidence = pd.concat([
        old_node[["timestamp", "sensor_id", "D5_report_score", "E_node"]],
        pd.read_parquet(REVISED / "DQR_node.parquet")[["timestamp", "sensor_id", "D5_report_score", "E_node"]],
    ], ignore_index=True)
    evidence["timestamp"] = pd.to_datetime(evidence["timestamp"])
    process = pd.read_parquet(PREPARED / "SUMO_process_inputs_5min_ready.parquet").reindex(forcing5.index)
    windows = window_table(common5, forcing5, quality5, unassessed5, process, evidence)
    windows.to_csv(OUT / "DQR_Raw_14d_window_comparison.csv", index=False, encoding="utf-8-sig")

    channel = audit.groupby(["source_period", "sensor_id"], observed=True).agg(
        minutes=("datetime", "size"), raw_present=("raw", "count"), DQR_present=("forcing", "count"),
        quality_excluded_minutes=("reason", lambda s: s.isin(["DQR_low_quality_no_qualified_repair", "gate_fail_no_qualified_repair"]).sum()),
        source_unassessed_minutes=("source_unassessed", "sum"), zero_equivalent_minutes=("zero_equivalent", "sum"),
        native_missing_minutes=("native_missing", "sum"), technical_invalid_minutes=("technical_invalid", "sum"),
        low_trigger_minutes=("low_trigger", "sum"), gate_fail_minutes=("gate_fail", "sum"),
        full_evidence_minutes=("E_node", lambda s: s.eq(1).sum()), D5_report_minutes=("D5_report_score", "count"),
    ).reset_index()
    channel["raw_present_pct"] = 100 * channel.raw_present / channel.minutes
    channel["DQR_present_pct"] = 100 * channel.DQR_present / channel.minutes
    channel.to_csv(OUT / "DQR_Raw_channel_comparison.csv", index=False, encoding="utf-8-sig")

    action = audit.groupby(["source_period", "action"], observed=True).size().rename("sensor_minutes").reset_index()
    action["pct_within_period"] = 100 * action.sensor_minutes / action.groupby("source_period", observed=True).sensor_minutes.transform("sum")
    action.to_csv(OUT / "DQR_action_summary.csv", index=False, encoding="utf-8-sig")

    period = audit.groupby("source_period", observed=True).agg(
        sensor_minutes=("datetime", "size"), raw_present=("raw", "count"), DQR_present=("forcing", "count"),
        source_unassessed_minutes=("source_unassessed", "sum"), quality_excluded_minutes=("reason", lambda s: s.isin(["DQR_low_quality_no_qualified_repair", "gate_fail_no_qualified_repair"]).sum()),
        full_evidence_minutes=("E_node", lambda s: s.eq(1).sum()), D5_report_minutes=("D5_report_score", "count"),
    ).reset_index()
    period["raw_present_pct"] = 100 * period.raw_present / period.sensor_minutes
    period["DQR_present_pct"] = 100 * period.DQR_present / period.sensor_minutes
    period["D5_report_pct"] = 100 * period.D5_report_minutes / period.sensor_minutes
    period["full_evidence_pct"] = 100 * period.full_evidence_minutes / period.sensor_minutes
    period.to_csv(OUT / "DQR_period_summary.csv", index=False, encoding="utf-8-sig")

    max_contrast = windows.sort_values(["contrast_rank", "start"]).iloc[0].to_dict()
    best_direct = windows.sort_values(["direct_run_rank", "start"]).iloc[0].to_dict()
    balanced_candidates = windows.loc[
        windows.joint_DO8_process_complete_pct.ge(90) & windows.DO6_quality_excluded_bins.gt(0)
    ].copy()
    balanced_candidates["DO_ORP_quality_excluded_bins"] = (
        balanced_candidates.DO6_quality_excluded_bins + balanced_candidates.ORP_quality_excluded_bins
    )
    balanced = balanced_candidates.sort_values(
        ["DO_ORP_quality_excluded_bins", "joint_DO8_process_complete_pct", "start"],
        ascending=[False, False, True],
    ).iloc[0].to_dict()
    d5_contract = json.loads(D5_AUDIT.read_text(encoding="utf-8"))
    summary = {
        "actual_data_period": [str(START), str(END)],
        "requested_2028_end_available": False,
        "historical_boundary": str(BOUNDARY),
        "historical_semantics": "retrospective_same_hour_conditioning_not_online_causal",
        "future_semantics": "revised_temporal_decision_clock_not_first_blind_test",
        "D5_reference_end": d5_contract["reference_end"],
        "D5_post_embargo_start": d5_contract["support_audit_post_start"],
        "qualified_fault_repair_operator": None,
        "DO6_numeric_changes_where_both_present": int(((forcing5[DO6] - common5[DO6]).abs() > 1e-12).sum().sum()),
        "max_contrast_window": {k: str(v) if isinstance(v, pd.Timestamp) else v for k, v in max_contrast.items()},
        "balanced_DO_intervention_window": {k: str(v) if isinstance(v, pd.Timestamp) else v for k, v in balanced.items()},
        "best_direct_coverage_window": {k: str(v) if isinstance(v, pd.Timestamp) else v for k, v in best_direct.items()},
        "interpretation": "maximum contrast is a post-hoc mechanism stress-test, not an independent validation window",
    }
    (OUT / "full_period_summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8", newline="\n")
    report = f"""# 全期 DQR-SUMO 输入与14天窗口审查

## 数据边界

磁盘中实际分钟数据为 2025-08-01 至 2026-07-30 23:59，不存在可核验的 2026-08 至 2028-07 数据。
2025-08-01 至 2026-04-13 使用历史回顾性 DQR；2026-04-14 以后使用冻结资产的新期重评价。
两段估计语义不同，不能合并声称为单一前瞻性验证。

历史源在 2026-04-13 17:18 后存在后来补齐的观测，这些值没有进入原历史 DQR，已标记 UNASSESSED，未套用旧评分。

## Raw 与 DQR

DQR 不改变保留的 DO1-3/ORP 数值，只把完整证据低分、Gate Fail、技术无效或原始缺失标记为不可用。
DO4 的 [-0.05, 0) mg/L 映射到0是三策略共享的零点等效物理化，不是 DQR 修复。
当前没有独立资格验证并冻结的 repair operator，因此 DQR 与 Raw 的主要差异是可用性掩码，而不是生成新的浓度值。

## 14天窗口

全期差异最大窗口：{max_contrast['start']} 至 {max_contrast['end_exclusive']}（结束不含）。
DO6质量屏蔽 {int(max_contrast['DO6_quality_excluded_bins'])} 个 channel-bin，ORP屏蔽 {int(max_contrast['ORP_quality_excluded_bins'])} 个 channel-bin。
这是按已观察到的DQR差异事后选择的机制压力测试窗口，不能作为独立验证主窗口。

DO干预与可运行性平衡窗口：{balanced['start']} 至 {balanced['end_exclusive']}。
DO6质量屏蔽 {int(balanced['DO6_quality_excluded_bins'])} 个 channel-bin，DO8+过程输入联合完整率 {balanced['joint_DO8_process_complete_pct']:.2f}%。
该窗口仍是事后选择，适合验证机制与数值稳定性，不得宣称为首次盲测；进入连续SUMO前仍需预注册并验证缺口修复或分段重启策略。

直接运行覆盖最佳窗口：{best_direct['start']} 至 {best_direct['end_exclusive']}。
DO8 DQR完整率 {best_direct['DO8_DQR_complete_pct']:.2f}%，ORP6完整率 {best_direct['ORP6_DQR_complete_pct']:.2f}%，12项过程输入完整率 {best_direct['required_process_complete_pct']:.2f}%，DO8+ORP6+过程输入联合完整率 {best_direct['joint_DO8_ORP6_process_complete_pct']:.2f}%。
若联合完整率不足100%，SUMO不得自动跨缺口连接；应使用连续子段、统一合格修复器或共同重启初态。

## D5审查

D5冻结参考终点实际为 {d5_contract['reference_end']}，并非2026-04-23；禁运期后审计从 {d5_contract['support_audit_post_start']} 开始。既有支持迁移审计显示，后期R2参考仅29个有效日，低于预设L2的40日；
同时新期存在大量OOD/out-of-template。因此，D5低覆盖主要是证据成熟度与适用域限制，不是传感器低质量本身。

这不否定108天作为冻结模型的时间外适用域测试，但会使“必须E=1才干预”的Full-DQR策略几乎没有可辨识对比。
正式论文应把Core D1+D2、Full D1+D2+D5和D5 abstention分层报告。若要验证含D5的最终DQR干预，应先按预注册规则升级版本化模板，随后在新的未来数据上冻结验证；不能用本期数据扩展模板后再评价本期。
"""
    (OUT / "FULL_PERIOD_DQR_SUMO_REVIEW_ZH.md").write_text(report, encoding="utf-8", newline="\n")
    tables = {"PeriodSummary": period, "ActionSummary": action, "ChannelSummary": channel,
              "WindowRanking": windows.sort_values(["contrast_rank", "start"]).head(60),
              "SelectedWindows": pd.DataFrame([max_contrast, balanced, best_direct]),
              "Contract": pd.DataFrame({"Field": list(summary), "Value": [json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v for v in summary.values()]})}
    payload = {k: {"columns": list(v.columns), "rows": json.loads(v.to_json(orient="values", date_format="iso"))} for k, v in tables.items()}
    (OUT / "audit_tables.json").write_text(json.dumps(payload, ensure_ascii=False, allow_nan=False), encoding="utf-8", newline="\n")
    inputs = [PREPARED / "SUMO_DO_ORP_1min_raw.parquet", PREPARED_MANIFEST, OLD_RAW, OLD_NODE, OLD_MANIFEST,
              REVISED / "DQR_node.parquet", REVISED_MANIFEST, HOLDOUT_OUT / "do_orp_strategy_audit_1min.parquet",
              HOLDOUT_MANIFEST, BOUNDS, D5_AUDIT]
    manifest = {"version": "DQR-FULL-PERIOD-SUMO-V1", "inputs": {str(p): sha256(p) for p in inputs},
                "outputs": {}, "code": {Path(__file__).name: sha256(Path(__file__))}}
    (OUT / "full_period_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8", newline="\n")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


def finalize():
    path = OUT / "full_period_manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    code = [Path(__file__), HERE / "export_dqr_forcing.py", HERE / "prepare_sumo_inputs.py",
            HERE / "verify_full_period_dqr.py", HERE / "test_full_period_dqr.py", HERE / "build_full_period_audit.mjs"]
    manifest["code"] = {p.name: sha256(p) for p in code}
    manifest["outputs"] = {p.name: sha256(p) for p in sorted(OUT.iterdir()) if p.is_file() and p != path}
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--finalize", action="store_true")
    args = parser.parse_args()
    finalize() if args.finalize else main()
