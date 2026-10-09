"""Export the frozen Q/E/G decision rule without inventing a repair model."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from prepare_sumo_inputs import ROOT, OUTPUT_DIR as PREPARED, sha256

HERE = Path(__file__).resolve().parent
OUT = PREPARED / "dqr_forcing"
REVISED = ROOT / "validation/revised_reference_20260917/outputs"
CONTRACT_PATH = HERE / "dqr_forcing_contract.json"
PLAN = Path("D:/001_Profile/010_Study/100_my work/102_project/00_Research Direction/00_Chapter Outline/Chapter1_Project 1 Data Quality Assessment/260917_DQR_InputDO_下游使用适宜性独立验证方案_顶刊SCI最终可执行版_v3.0.docx")
BOUNDS = ROOT / "D3 Physical rationality and rate constraints/configs/d3_physical_bounds.yaml"
DO = [f"DO_{line}_{pos}" for line in (1, 2) for pos in (1, 2, 3, 4)]
DO6 = [s for s in DO if not s.endswith("_4")]
ORP = [f"ORP_{line}_{pos}" for line in (1, 2) for pos in (1, 2, 3)]


def runs(mask):
    values = np.asarray(mask, dtype=bool)
    edges = np.diff(np.r_[False, values, False].astype(np.int8))
    return list(zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)))


def align_scores(index, evidence, expiry_minutes=60):
    if evidence.decision_at.duplicated().any():
        raise ValueError("Ambiguous score decision clock")
    result = pd.merge_asof(
        pd.DataFrame({"time": index}), evidence.sort_values("decision_at"),
        left_on="time", right_on="decision_at", direction="backward",
        tolerance=pd.Timedelta(minutes=expiry_minutes),
    ).set_index("time")
    stale = result.decision_at.notna() & (
        result.index - result.decision_at >= pd.Timedelta(minutes=expiry_minutes)
    )
    for col in result.columns:
        result[col] = result[col].mask(stale)
    return result


def decide(raw, aligned, *, is_do, zero_low=None, low_threshold=3.0):
    observed = raw.astype(float).copy()
    zero = observed.between(zero_low, 0, inclusive="left") if zero_low is not None else pd.Series(False, index=raw.index)
    physical = observed.mask(zero, 0.0)
    invalid = physical.notna() & (~np.isfinite(physical) | ((physical < 0) | (physical > 20) if is_do else physical.abs() > 1500))
    complete = np.isclose(aligned.E_node.fillna(-1), 1.0)
    low = pd.Series(complete, index=raw.index) & aligned.Q_node_available.lt(low_threshold) & aligned.D3_gate_status.isin(["Pass", "Warn"])
    gate_fail = aligned.D3_gate_status.eq("Fail")
    missing = observed.isna()
    requested = low | gate_fail | invalid | missing
    reason = pd.Series("keep", index=raw.index)
    reason.loc[aligned.D3_gate_status.eq("Warn")] = "operational_warning_keep"
    limited = ~pd.Series(complete, index=raw.index) | aligned.Q_node_available.isna() | aligned.D3_gate_status.eq("NotEvaluated") | aligned.D3_gate_status.isna()
    reason.loc[limited] = "evidence_limited_keep"
    reason.loc[zero] = "common_do4_zero_equivalence"
    reason.loc[low] = "DQR_low_quality_no_qualified_repair"
    reason.loc[gate_fail] = "gate_fail_no_qualified_repair"
    reason.loc[invalid] = "technical_invalid_no_qualified_repair"
    reason.loc[missing] = "native_missing_no_qualified_repair"
    action = pd.Series(np.where(requested, "UNRECOVERABLE", "KEEP"), index=raw.index)
    return pd.DataFrame({
        "raw": observed, "common": physical.mask(invalid | missing),
        "dqr_measurement": observed.mask(requested),
        "forcing": physical.mask(requested), "action": action, "reason": reason,
        "repair_requested": requested, "low_trigger": low, "gate_fail": gate_fail,
        "native_missing": missing, "technical_invalid": invalid,
        "zero_equivalent": zero, "evidence_limited": limited,
        "repair_method": "none", "repair_uncertainty": np.nan,
    })


def fill_native_short_gaps(frame, aligned, max_minutes=3, endpoint_score=4.0):
    # Never interpolate a quality-triggered fault, or bridge an unknown endpoint.
    trusted = (
        np.isclose(aligned.E_node.fillna(-1), 1.0)
        & aligned.Q_node_available.ge(endpoint_score)
        & aligned.D3_gate_status.eq("Pass") & frame.action.eq("KEEP")
        & frame.forcing.notna()
    )
    for start, stop in runs(frame.native_missing):
        if stop - start > max_minutes or start == 0 or stop == len(frame):
            continue
        if not (trusted.iloc[start - 1] and trusted.iloc[stop]):
            continue
        values = np.linspace(frame.forcing.iloc[start - 1], frame.forcing.iloc[stop], stop - start + 2)[1:-1]
        for col in ["forcing", "common", "dqr_measurement"]:
            frame.iloc[start:stop, frame.columns.get_loc(col)] = values
        frame.iloc[start:stop, frame.columns.get_loc("action")] = "REPAIR"
        frame.iloc[start:stop, frame.columns.get_loc("reason")] = "common_native_gap_le3min"
        frame.iloc[start:stop, frame.columns.get_loc("repair_method")] = "bounded_linear_common_native_gap"
    return frame


def aggregate_complete(frame, minutes=5):
    grouped = frame.resample(f"{minutes}min", closed="left", label="left")
    return grouped.mean().where(grouped.count().eq(minutes))


def save_csv(frame, name, *, origin=None):
    result = frame.copy()
    result.index.name = "datetime"
    if origin is not None:
        result.insert(0, "time_days", (result.index - pd.Timestamp(origin)).total_seconds() / 86400)
    result.to_csv(OUT / name, encoding="utf-8-sig", date_format="%Y-%m-%d %H:%M:%S", float_format="%.10g")


def verify_inputs():
    manifest = json.loads((REVISED / "DQR_manifest.json").read_text(encoding="utf-8"))
    checked = {}
    for name in ["DQR_node.parquet", "DQR_pair.parquet", "DQR_time_join.parquet"]:
        p = REVISED / name
        actual = sha256(p)
        if actual != manifest["outputs"][name]:
            raise ValueError(f"DQR output hash mismatch: {name}")
        checked[str(p)] = actual
    prepared_manifest = json.loads((PREPARED / "SUMO_input_manifest.json").read_text(encoding="utf-8"))
    for name in ["SUMO_DO_ORP_1min_raw.parquet", "SUMO_process_inputs_5min_ready.parquet"]:
        p = PREPARED / name
        actual = sha256(p)
        if actual != prepared_manifest["final_outputs"][name]["sha256"]:
            raise ValueError(f"Prepared output hash mismatch: {name}")
        checked[str(p)] = actual
    for p in [PLAN, BOUNDS, CONTRACT_PATH]:
        checked[str(p)] = sha256(p)
    return checked


def interval_records(mask, *, scope, warmup_days):
    records = []
    for a, b in runs(mask):
        start = mask.index[a]
        end = mask.index[b - 1] + pd.Timedelta(minutes=5)
        duration = (end - start).total_seconds() / 86400
        records.append({"scope": scope, "start": start, "end_exclusive": end,
                        "days": duration, "warmup_days": warmup_days,
                        "post_warmup_days": max(0, duration - warmup_days),
                        "supports_28d_plus_warmup": duration >= 28 + warmup_days})
    return records


def write_report(summary, monthly, intervals, checks, selected):
    do = summary[summary.sensor_id.isin(DO)]
    orp = summary[summary.sensor_id.isin(ORP)]
    report = f"""# DQR 处置后 SUMO 输入审查与交付

## 审查结论

可以输出 8 个 DO 与 6 个 ORP 的数值、Q/E/G、处置动作和连续可输入区间。
当前没有独立资格验证并冻结的故障修复器，所以低质量片段不填入臆测值。
这是 v3.0 规则的输入准备及可运行性审计，尚未完成三策略 SUMO 下游效用实验。

108 天各通道 D5 report 可用 66/2592 h（2.55%），但完整聚合证据 E=1 仅 65/2592 h（2.51%）。
两者不能混称 Full 覆盖率；按实际可用时钟连接后的完整证据分钟数列于通道摘要。
原评分小时中 8 个 DO 没有同时满足 E=1 且 Q<3 的记录。
按实际可用时钟连接后，DO 的低分触发分钟数为 {int(do.low_trigger_minutes.sum())}；ORP 为 {int(orp.low_trigger_minutes.sum())}。
在本规则下 Full-DQR 对 DO 的可辨识增益不足，应如实报告，不能为制造组间差异临时降低 E 要求。
D4 是 pair 层关系证据，不能直接把 pair 低分归咎于某一支探头。逐点附带 D4/pair 诊断，但不自动修复两端。

## 文件使用

- `DQR_DO8_5min_20260414_20260730.csv`：108 天 8 个 DO，单位 mg O2/L，time_days 从验证期起点计。
- `DQR_ORP6_5min_20260414_20260730.csv`：6 个 ORP，单位 mV，负值保留。
- `DQR_DO8_5min_with_14d_warmup.csv`：从 2026-03-31 开始，前 14 天共用原始技术合规序列。
- `pilot42d_DO8_DQR.csv` 和 `pilot42d_DO6_Raw.csv`：原拟 14 天预热加 28 天验证候选。DO 连续，但共同过程输入存在缺口，尚非完整 SUMO 可运行包。
- `pilot28d_DO8_DQR.csv`、`pilot28d_DO6_Raw.csv`、`pilot28d_ORP6.csv` 和 `pilot28d_common_process_inputs.csv`：基于共同输入覆盖选出的短期试运行包，前14天预热、后14天评价。
- `do_orp_strategy_audit_1min.parquet`：逐分钟原值、处置值、动作、原因、评分可用时刻与 pair 诊断。
- `DQR_DO_ORP_measurement_1min.csv.gz`：DQR 保留/修复后的测量域数据，DO4 原始小负值仍可追溯。
- `continuous_input_windows.csv`、`blocked_intervals.csv`：连续可输入时段与不可输入片段。空值不得由 SUMO 默认跨长段插值。
- `DQR_DO_ORP_export_audit.xlsx`：通道汇总、月份、时段和方法合同。

主研究用 6 个好氧 DO1-3。DO4 按 D3 已有零点等效阈值，将 [-0.05,0) mg/L
在 SUMO 共用模型输入层表示为 0；Raw 和 measurement 输出保留原负值。
这项物理化处理是三策略相同的暂定表示合同，不作为 DQR 故障修复，也不声称真实 DO 精确为零。
ORP 是诊断及自定义模型辅助数据；常规 Input DO 反应器不把 ORP 当作可直接替代 DO 的 forcing。

## 时间与可运行性

长期评价目标仍为 2026-04-14 至 2026-07-30 共 108 天；建议动态预热 2026-03-31 至 2026-04-13。
原拟 2026-04-14 至 2026-05-11 的28天验证候选，因共同过程输入断点，暂不作为完整可运行包。
当前短期试运行选择为 {selected.get('start')} 至 {selected.get('end_exclusive')}（结束时刻不含）：
预热 {selected.get('warmup_days')} 天，评价从 {selected.get('evaluation_start')} 开始，共14天。
选择依据是最早的完整日界连续输入窗口，不依据 DQR 高低或下游结果。
14 天只是预热起点建议，必须先建立统一的稳态/已校核状态，并检查 NH4、MLSS、氮平衡是否稳定。
若需从任意初态起步，应按 SRT/状态收敛决定更长预热，不能保证 14 天自动足够。
一旦遇到长断点，不拼接删除后的日期；三策略共同重构或从同一独立初态重新起算，并排除共同预热段。
本次只依据输入覆盖审查区间，没有读取 SUMO 误差，也没有用出水值反向选择窗口。

这 108 天已经经过 DQR 方法修订与查看，只能称修订后时间外评价。
若独立实验室 NH4/TN 尚未打开，可冻结新的下游分析计划后评价这一终点；
不能重新称整个 DQR 方法首次盲测。28 天约 4 个周区块，主要用于工程试运行；
当前14天短期试运行只能检验模型连接、单位和数值稳定性，不足以支撑周区块置信区间的正式效度主张。
正式效应量和区块 CI 应尽量覆盖 8-12 周或全部108天，而不把分钟数视作独立样本量。

评分按 decision_at 向后连接到分钟时刻，最长保留60分钟，端点不含；未把小时评分提前赋给尚不可用的时刻。
5分钟输出为 [t,t+5min) 均值，需5个分钟均有定义，代表区间值，不是 t 时刻已经可获得的瞬时值。
本文件用于离线动态重放，SUMO 内建议明确区间保持或插值设置。读取器不得跨空值区间自动连线。

## 当前科学边界

1. 需要独立遮蔽/故障注入与人工复核后冻结 repair operator，才能把待修复片段升级为可靠重构。
2. 常规 QC 比较器不能直接沿用上次仅 Hampel 清洗的工作表充当完整 v3.0 对照。
3. 该时段回流渠 MLSS 输入全缺失；如它只用于初态校核，可另提供独立 MLSS/SRT 证据，不能凭空填造。
4. 加药流量计工程单位需核实；现有进出水在线数据不能自动冒充独立实验室真值。
5. 尚未提供冻结 SUMO 模型、统一初态和独立实验室 outcome 集合，因此不能宣称正式下游效度已验证。

## 数值核验

{json.dumps(checks, ensure_ascii=False, indent=2)}

## 通道摘要

{summary.to_markdown(index=False)}

## 可运行区间

{intervals.to_markdown(index=False)}

## 软件依据

Dynamita 官方说明 Input DO 由指定 DO 驱动并计算需气量，动态模拟依赖共同初态。
- https://wiki.dynamita.com/en/process_units
- https://wiki.dynamita.com/en/using-sumo
- https://wiki.dynamita.com/en/advanced-simulations

依据文件：260917_DQR_InputDO_下游使用适宜性独立验证方案_顶刊SCI最终可执行版_v3.0.docx。
"""
    (OUT / "DQR_SUMO_INPUT_REVIEW_ZH.md").write_text(report, encoding="utf-8", newline="\n")


def main():
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    inputs = verify_inputs()
    OUT.mkdir(parents=True, exist_ok=True)
    start = pd.Timestamp(contract["validation_start"])
    end = pd.Timestamp(contract["end_exclusive"])
    warm_start = start - pd.Timedelta(days=contract["warmup_days"])
    raw = pd.read_parquet(PREPARED / "SUMO_DO_ORP_1min_raw.parquet")
    raw.columns = [c.split("（")[0] for c in raw.columns]
    raw = raw.loc[(raw.index >= warm_start) & (raw.index < end), DO + ORP]
    if not raw.index.equals(pd.date_range(warm_start, end, freq="min", inclusive="left", name=raw.index.name)):
        raise ValueError("Raw timebase is not complete, unique minute grid")
    node = pd.read_parquet(REVISED / "DQR_node.parquet")
    pair = pd.read_parquet(REVISED / "DQR_pair.parquet")
    bounds = yaml.safe_load(BOUNDS.read_text(encoding="utf-8"))
    score_fields = ["timestamp", "decision_at", "Q_node_available", "Q_node_core12", "E_node", "D3_gate_status", "D1_total", "D2_total", "D2_veto_flag", "D5_report_score", "D5_support_level", "regime_state", "coverage_class"]
    values, common, measurement, audit_parts, summary, monthly = {}, {}, {}, [], [], []
    for sensor in DO + ORP:
        evidence = node.loc[node.sensor_id.eq(sensor), score_fields]
        aligned = align_scores(raw.index, evidence, contract["score_expiry_minutes"])
        p = pair.loc[pair.left_sensor_id.eq(sensor) | pair.right_sensor_id.eq(sensor), ["decision_at", "D4_raw", "Q_pair_available", "E_pair"]]
        paired = align_scores(raw.index, p, contract["score_expiry_minutes"])
        zero_low = bounds["sensor_overrides"].get(sensor, {}).get("zero_equivalence_low")
        f = decide(raw[sensor], aligned, is_do=sensor in DO, zero_low=zero_low, low_threshold=contract["score_low_threshold"])
        f = fill_native_short_gaps(f, aligned, contract["common_native_gap_max_minutes"], contract["native_gap_endpoint_min_score"])
        values[sensor], common[sensor], measurement[sensor] = f.forcing, f.common, f.dqr_measurement
        data = f.join(aligned.rename(columns={"timestamp": "score_source_hour"}))
        data = data.join(paired[["D4_raw", "Q_pair_available", "E_pair"]])
        data["sensor_id"] = sensor
        data["phase"] = np.where(data.index < start, "common_warmup", "revised_temporal_evaluation")
        data["input_role"] = "aerobic_primary" if sensor in DO6 else "post_anoxic_common" if sensor in DO else "ORP_diagnostic"
        audit_parts.append(data.reset_index(names="datetime"))
        val = data.loc[data.index >= start]
        item = {
            "sensor_id": sensor, "minutes": len(val),
            "full_evidence_minutes": int(np.isclose(val.E_node.fillna(-1), 1.0).sum()),
            "evidence_limited_pct": float(val.evidence_limited.mean() * 100),
            "low_trigger_minutes": int(val.low_trigger.sum()),
            "gate_fail_minutes": int(val.gate_fail.sum()),
            "repaired_minutes": int(val.action.eq("REPAIR").sum()),
            "unrecoverable_minutes": int(val.action.eq("UNRECOVERABLE").sum()),
            "zero_equivalent_minutes": int(val.zero_equivalent.sum()),
        }
        summary.append(item)
        for month, v in val.groupby(val.index.to_period("M")):
            monthly.append({"month": str(month), "sensor_id": sensor, "minutes": len(v),
                "full_evidence_pct": float(np.isclose(v.E_node.fillna(-1), 1.0).mean() * 100),
                "low_trigger_minutes": int(v.low_trigger.sum()),
                "unrecoverable_minutes": int(v.action.eq("UNRECOVERABLE").sum())})
    values, common, measurement = pd.DataFrame(values), pd.DataFrame(common), pd.DataFrame(measurement)
    audit = pd.concat(audit_parts, ignore_index=True)
    for c in audit.select_dtypes(include="object"):
        audit[c] = audit[c].astype("category")
    audit.to_parquet(OUT / "do_orp_strategy_audit_1min.parquet", index=False)
    measurement.loc[start:].to_csv(OUT / "DQR_DO_ORP_measurement_1min.csv.gz", compression="gzip", encoding="utf-8-sig", index_label="datetime")
    wide = aggregate_complete(values)
    common5 = aggregate_complete(common)
    raw5 = aggregate_complete(raw)
    save_csv(wide.loc[start:, DO], "DQR_DO8_5min_20260414_20260730.csv", origin=start)
    save_csv(wide.loc[start:, ORP], "DQR_ORP6_5min_20260414_20260730.csv", origin=start)
    save_csv(raw5.loc[start:], "Raw_DO_ORP14_5min_20260414_20260730.csv", origin=start)
    save_csv(wide[DO], "DQR_DO8_5min_with_14d_warmup.csv", origin=warm_start)
    pilot_end = start + pd.Timedelta(days=contract["pilot_evaluation_days"])
    pilot = wide.loc[wide.index < pilot_end, DO]
    save_csv(pilot, "pilot42d_DO8_DQR.csv", origin=warm_start)
    save_csv(common5.loc[common5.index < pilot_end, DO6], "pilot42d_DO6_Raw.csv", origin=warm_start)
    process = pd.read_parquet(PREPARED / "SUMO_process_inputs_5min_ready.parquet").reindex(wide.index)
    required = ["进水瞬时流量（m³/h）", "进水COD（mg/L）", "进水氨氮（mg/L）", "进水总氮（mg/L）", "进水温度（℃）", "1#生物池外回流流量（m³/h）", "2#生物池外回流流量（m³/h）", "1#生物池内回流流量（m³/h）", "2#生物池内回流流量（m³/h）", "剩余污泥流量（m³/h）", "乙酸钠流量计2（m³/h）", "乙酸钠流量计4（m³/h）"]
    ready6 = wide[DO6].notna().all(axis=1)
    ready8 = wide[DO].notna().all(axis=1)
    masks = {"six_aerobic_DO": ready6, "eight_DO_common_DO4": ready8,
             "eight_DO_plus_required_process_nonmissing_units_pending": ready8 & process[required].notna().all(axis=1)}
    intervals = pd.DataFrame([r for scope, mask in masks.items() for r in interval_records(mask, scope=scope, warmup_days=contract["warmup_days"])])
    intervals.to_csv(OUT / "continuous_input_windows.csv", index=False, encoding="utf-8-sig")
    selected = {}
    for row in intervals[intervals.scope.eq("eight_DO_plus_required_process_nonmissing_units_pending")].itertuples():
        first = row.start.ceil("D")
        last = first + pd.Timedelta(days=28)
        if last > row.end_exclusive or first + pd.Timedelta(days=14) < start:
            continue
        chosen = (wide.index >= first) & (wide.index < last)
        save_csv(wide.loc[chosen, DO], "pilot28d_DO8_DQR.csv", origin=first)
        save_csv(common5.loc[chosen, DO6], "pilot28d_DO6_Raw.csv", origin=first)
        save_csv(wide.loc[chosen, ORP], "pilot28d_ORP6.csv", origin=first)
        common_process = process.loc[chosen, required].copy()
        for column in common_process.columns:
            if "m³/h" in column:
                common_process[column] *= 24.0
        common_process.columns = [c.replace("m³/h", "m³/d") for c in common_process.columns]
        save_csv(common_process, "pilot28d_common_process_inputs.csv", origin=first)
        selected = {"start": str(first), "end_exclusive": str(last), "evaluation_start": str(first + pd.Timedelta(days=14)),
                    "warmup_days": 14, "evaluation_days": 14, "selection": "earliest_complete_day_aligned_input_window",
                    "DO8_complete": bool(wide.loc[chosen, DO].notna().all().all()),
                    "ORP6_complete": bool(wide.loc[chosen, ORP].notna().all().all()),
                    "process_complete": bool(common_process.notna().all().all()),
                    "remaining_limits": "dosing_units_MLSS_initial_state_SUMO_model_and_independent_outcomes"}
        break
    process_coverage = pd.DataFrame({"variable": process.columns,
        "missing_bins_108d": process.loc[start:].isna().sum().values,
        "missing_pct_108d": (100 * process.loc[start:].isna().mean()).values})
    process_coverage.to_csv(OUT / "process_input_coverage.csv", index=False, encoding="utf-8-sig")
    blocked = []
    for sensor in DO + ORP:
        for a, b in runs(wide[sensor].isna()):
            blocked.append({"sensor_id": sensor, "start": wide.index[a], "end_exclusive": wide.index[b-1]+pd.Timedelta(minutes=5), "minutes": (b-a)*5})
    pd.DataFrame(blocked).to_csv(OUT / "blocked_intervals.csv", index=False, encoding="utf-8-sig")
    # Export complete contiguous blocks with their own elapsed-time origin.
    block_registry = []
    for i, row in intervals[intervals.scope.eq("eight_DO_common_DO4") & intervals.supports_28d_plus_warmup].iterrows():
        block = wide.loc[(wide.index >= row.start) & (wide.index < row.end_exclusive), DO]
        name = f"runnable_DO8_block_{row.start:%Y%m%d_%H%M}_{row.end_exclusive:%Y%m%d_%H%M}.csv"
        save_csv(block, name, origin=row.start)
        block_registry.append({"file": name, "start": str(row.start), "end_exclusive": str(row.end_exclusive), "warmup_days": 14, "scope": "DO_only_readiness_process_units_and_model_pending"})
    summary, monthly = pd.DataFrame(summary), pd.DataFrame(monthly)
    summary.to_csv(OUT / "channel_summary.csv", index=False, encoding="utf-8-sig")
    monthly.to_csv(OUT / "monthly_summary.csv", index=False, encoding="utf-8-sig")
    unknown = audit.action.eq("UNRECOVERABLE")
    iskeep = audit.action.eq("KEEP") & ~audit.zero_equivalent
    known = audit.decision_at.notna()
    changes_do = ((wide[DO6] - common5[DO6]).abs() > 1e-12).sum().sum()
    checks = {
        "source_hashes_match": True, "holdout_5min_rows": len(wide.loc[start:]),
        "no_future_score": bool((audit.loc[known, "decision_at"] <= audit.loc[known, "datetime"]).all()),
        "unrecoverable_forcing_stays_nan": bool(audit.loc[unknown, "forcing"].isna().all()),
        "kept_observations_unchanged": bool(np.allclose(audit.loc[iskeep, "raw"], audit.loc[iskeep, "forcing"], equal_nan=True)),
        "ORP_negative_values_retained": bool((wide[ORP].min() < 0).all()),
        "SUMO_DO_nonnegative": bool((wide[DO].stack() >= 0).all()),
        "pilot_DO8_complete": bool(pilot.notna().all().all()),
        "pilot_required_process_complete": bool(process.loc[process.index < pilot_end, required].notna().all().all()),
        "DO6_numeric_changes_vs_common_raw_5min": int(changes_do),
        "all_108d_DO8_continuous": bool(ready8.loc[start:].all()),
        "no_fault_repair_qualification_claimed": True,
    }
    assertions = ["no_future_score", "unrecoverable_forcing_stays_nan", "kept_observations_unchanged", "ORP_negative_values_retained", "SUMO_DO_nonnegative"]
    if not all(checks[k] for k in assertions):
        raise AssertionError(checks)
    checks["selected_14d_pilot_complete_except_documented_model_unit_limits"] = bool(selected and selected["DO8_complete"] and selected["ORP6_complete"] and selected["process_complete"])
    (OUT / "export_QA.json").write_text(json.dumps(checks, indent=2), encoding="utf-8", newline="\n")
    write_report(summary, monthly, intervals, checks, selected)
    tables = {"Channels": summary, "Months": monthly, "Windows": intervals,
              "ProcessCoverage": process_coverage,
              "Contract": pd.DataFrame({"field": list(contract), "value": [str(v) for v in contract.values()]})}
    payload = {key: {"columns": list(df.columns), "rows": json.loads(df.to_json(orient="values", date_format="iso"))} for key, df in tables.items()}
    (OUT / "audit_tables.json").write_text(json.dumps(payload, ensure_ascii=False, allow_nan=False), encoding="utf-8", newline="\n")
    registry = {"contract": contract, "input_sha256": inputs, "run_blocks": block_registry, "selected_pilot": selected, "checks": checks}
    (OUT / "DQR_forcing_manifest.json").write_text(json.dumps(registry, indent=2, ensure_ascii=False), encoding="utf-8", newline="\n")
    print(json.dumps(checks, indent=2))
    print(summary.to_string(index=False))
    print(intervals[intervals.days >= 7].to_string(index=False))


def finalize():
    path = OUT / "DQR_forcing_manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    # Canonicalize generated text before freezing byte hashes across checkouts.
    for artifact in OUT.iterdir():
        if artifact.is_file() and artifact.suffix in {".md", ".json", ".ndjson"}:
            artifact.write_bytes(artifact.read_bytes().replace(b"\r\n", b"\n"))
    manifest["code_sha256"] = {p.name: sha256(p) for p in [Path(__file__), HERE / "build_dqr_audit.mjs", HERE / "test_dqr_forcing.py", HERE / "verify_dqr_export.py", HERE / "prepare_sumo_inputs.py", HERE / ".gitattributes", CONTRACT_PATH]}
    manifest["output_sha256"] = {p.name: sha256(p) for p in sorted(OUT.iterdir()) if p.is_file() and p != path}
    path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8", newline="\n")
    print(f"Frozen {len(manifest['output_sha256'])} output hashes")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--finalize", action="store_true")
    args = parser.parse_args()
    finalize() if args.finalize else main()
