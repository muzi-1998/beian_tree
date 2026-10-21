"""Audit real prototype outputs and write a source-grounded stage review."""
from __future__ import annotations

import json
from pathlib import Path
import re
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from project2_synthesis.runtime import sha256, write_json


def main() -> None:
    state = json.loads((ROOT / "run_manifest/archive_sensitivity_states.json").read_text(encoding="utf-8"))
    run_id = state["M11"][-1]["run_id"]
    run_dir = ROOT / "run_manifest/archive_sensitivity/runs" / run_id
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    checked = set()
    for stage in manifest["stages"]:
        for name, expected in stage["output_hashes"].items():
            snapshot = run_dir / "artifacts/archive_sensitivity" / name
            current = ROOT / "artifacts/archive_sensitivity" / name
            if sha256(snapshot) != expected["sha256"] or sha256(current) != expected["sha256"]:
                raise ValueError(f"Output hash mismatch: {name}")
            checked.add(name)
    data_root = ROOT / "artifacts/archive_sensitivity"
    diagnostic = pd.read_csv(data_root / "validation/synthesis_diagnostics.csv")
    trajectory = pd.read_csv(data_root / "validation/trajectory_manifest.csv")
    support = pd.read_csv(data_root / "validation/support_card.csv")
    temporal = pd.read_csv(data_root / "validation/temporal_roundtrip.csv")
    copula = pd.read_csv(data_root / "validation/copula_fits.csv")
    if len(trajectory) != 108 or not trajectory["status"].eq("PASS").all() or len(diagnostic) != 108:
        raise ValueError("Configured trajectory grid incomplete")
    expected_grid = {(s, t, p, f, seed) for s in [5, 15, 60] for t in ["identity", "log1p"] for p in [0, 1]
                     for f in ["independence", "Gaussian", "Student_t"] for seed in [20261020, 20261021, 20261022]}
    actual_grid = set(zip(trajectory.step_minutes, trajectory["transform"], trajectory.p, trajectory.family, trajectory.seed))
    if expected_grid != actual_grid:
        raise ValueError("Missing/duplicated case grid")
    source_data = pd.read_csv(data_root / "figures/archive_diagnostics_source.csv")
    if set(source_data.trajectory_id) != set(trajectory.trajectory_id):
        raise ValueError("Figure source data do not cover all successful trajectories")
    start, end = pd.Timestamp("2025-08-01", tz="Asia/Shanghai"), pd.Timestamp("2025-08-31", tz="Asia/Shanghai")
    mapping, negatives = [], {"Q": 0, "COD": 0}
    for row in trajectory.itertuples(index=False):
        family = {"independence": "I", "Gaussian": "G", "Student_t": "T"}[row.family]
        relative = f"data/t/{row.case_id}_{family}_{row.seed}.parquet"
        path = data_root / relative
        frame = pd.read_parquet(path)
        support_frame = pd.read_parquet(data_root / f"data/support_{row.step_minutes:02d}m.parquet")
        reference = support_frame[(support_frame.timestamp >= start) & (support_frame.timestamp < end)]
        if not frame.timestamp.equals(reference.timestamp.reset_index(drop=True)):
            raise ValueError("Trajectory calendar differs from its comparison reference")
        if (frame.timestamp.min() < start or frame.timestamp.max() >= end or not frame.split.eq("development").all()
                or frame.model_admitted.any() or not frame.measurement_support.eq("UNKNOWN").all()):
            raise ValueError("Trajectory scope or admission bypass")
        if not np.isfinite(frame[["Q_unconstrained", "COD_FW_unconstrained", "T_fixed_archive_context"]].to_numpy()).all():
            raise ValueError("Nonfinite generated values")
        np.testing.assert_array_equal(frame.T_fixed_archive_context, reference["T"].to_numpy())
        for variable, column, count in [("Q", "Q_unconstrained", row.Q_negative_rows), ("COD", "COD_FW_unconstrained", row.COD_negative_rows)]:
            actual_negative = frame[column].lt(0)
            if not actual_negative.equals(frame[f"{variable}_negative"]) or int(actual_negative.sum()) != count:
                raise ValueError("Negative-value ledger mismatch")
            negatives[variable] += int(actual_negative.sum())
        mapping.append({"trajectory_id": row.trajectory_id, "path": path.relative_to(ROOT).as_posix(),
                        "sha256": sha256(path), "seed": row.seed, "archive_bins": len(frame),
                        "Q_unit": "m3/h", "COD_FW_unit": "mg/L_source_header", "T_unit": "degC"})
    pd.DataFrame(mapping).to_csv(data_root / "validation/trajectory_file_map.csv", index=False, encoding="utf-8-sig")
    source_frame = pd.read_parquet(ROOT / "artifacts/data/02_model_frame.parquet")
    valid_minutes = int(source_frame.technical_support_Q_COD_T.sum())
    retained_minutes = int(support.archive_minutes.iloc[0])
    if support.archive_minutes.nunique() != 1 or support.common_hours.nunique() != 1:
        raise ValueError("Cross-scale calendar support differs")
    max_integral_error = max(float((support[v] - support[v].iloc[0]).abs().max() / max(abs(support[v].iloc[0]), 1)) for v in ["V_m3", "COD_load_kg"])
    if max_integral_error > 1e-8:
        raise ValueError("Cross-scale integral failed")
    for variable in ["Q", "COD"]:
        for lag in [60, 360, 1440, 10080]:
            diagnostic[f"{variable}_acf_abs_error_{lag}m"] = (diagnostic[f"{variable}_acf_{lag}m_synthetic"] - diagnostic[f"{variable}_acf_{lag}m_reference"]).abs()
    columns = ["tau_abs_error", "Q_acf_abs_error_60m", "COD_acf_abs_error_60m", "Q_negative_rows", "COD_negative_rows"]
    group = diagnostic.groupby(["transform", "p", "family"])[columns].agg({columns[0]: "median", columns[1]: "median", columns[2]: "median", columns[3]: "sum", columns[4]: "sum"})
    group.to_csv(data_root / "validation/grouped_descriptive_summary.csv", encoding="utf-8-sig")
    near_upper = copula[(copula.family == "Student_t") & (200 - copula.df < 1e-3)]
    near_upper.to_csv(data_root / "validation/student_df_boundary_diagnostics.csv", index=False, encoding="utf-8-sig")
    margin_checks = pd.read_csv(data_root / "validation/empirical_margin_checks.csv")
    test_match = re.search(r"Ran (\d+) tests", (run_dir / "tests.log").read_text(encoding="utf-8"))
    test_count = int(test_match.group(1)) if test_match else None
    window_hours = int(reference.archive_rows.sum() // 60)
    total_bins = int(trajectory.archive_bins.sum())
    negative_kinds = sorted(trajectory.loc[(trajectory.Q_negative_rows > 0) | (trajectory.COD_negative_rows > 0), "transform"].unique())
    study = json.loads((ROOT / "configs/study_design.json").read_text(encoding="utf-8"))
    if study["main_step_minutes"] is not None or study["ready_for_model_execution"]:
        raise ValueError("Formal model admission unexpectedly changed")
    result = {"run_id": run_id, "technical_output_verification": "PASS", "scientific_acceptance": "PARTIAL",
              "unique_outputs_hash_verified": len(checked), "configured_and_verified_trajectories": len(mapping),
              "trajectory_archive_rows_across_all_cases": total_bins, "pre_execution_tests_passed": test_count,
              "negative_rows_across_cases": negatives, "native_support": "UNKNOWN", "formal_main_step_minutes": None,
              "cross_scale_integral_error_scaled": max_integral_error, "common_development_hours": int(support.common_hours.iloc[0]),
              "technical_valid_development_minutes_before_common_hour_rule": valid_minutes,
              "retained_common_minutes": retained_minutes, "valid_minutes_excluded_by_complete_hour_rule": valid_minutes - retained_minutes,
              "near_numeric_df_upper_bound": near_upper.case_id.to_list(), "heldout_rows_used": 0,
              "first_run_failure_preserved": "20261020T143451_066150Z_archive/error.log", "copulas_refitted_on_resume": False}
    write_json(ROOT / "run_manifest/archive_execution_verification.json", result)
    table = "|变换|AR阶|Copula|τ差中位数|Q一小时ACF差中位数|COD一小时ACF差中位数|负Q行|负COD行|\n|---|---:|---|---:|---:|---:|---:|---:|\n"
    for key, row in group.iterrows():
        table += f"|{key[0]}|{key[1]}|{key[2]}|{row.iloc[0]:.4f}|{row.iloc[1]:.4f}|{row.iloc[2]:.4f}|{int(row.iloc[3])}|{int(row.iloc[4])}|\n"
    report = ("# 已授权档案敏感性支线：阶段复核\n\n2026-10-20，Asia/Shanghai。技术输出复核 PASS；科学准入 PARTIAL。"
              f"成功运行 `{run_id}`，原始失败和恢复谱系均保留。\n\n"
              "## 1. 目标与实际执行\n\n开发集 Q–COD/T 的 5/15/60 min 平行原型；K=1、两变换、AR(0/1)、三个同期创新Copula、三个探索种子。未开启验证/终端测试、氮、DQR收益、GPD/Vine、SUMO或E1–E3。\n\n"
              "## 2. 方法和配置\n\nconfigs/archive_sensitivity.json 保存全部原型数值与用途；日/周各一组唯一谐波，条件慢项为截距/标准化日历与T，分块条件OLS。经验边际保留原子，用固定种子随机PIT；t自由度仅在登记数值范围内条件伪似然搜索。"
              "[SciPy 1.15.3官方接口](https://docs.scipy.org/doc/scipy-1.15.3/reference/generated/scipy.stats.multivariate_t.html)与[statsmodels参考接口](https://www.statsmodels.org/v0.14.4/generated/statsmodels.distributions.copula.api.StudentTCopula.html)已核对，且密度与本机参考实现做数值比对。\n\n"
              "## 3. 输入与覆盖\n\n"
              f"原开发档案393120分钟，其中Q/COD/T技术有效{valid_minutes}分钟；共同完整小时规则保留{retained_minutes}分钟（6373小时，97.268%日历时长），连带排除{valid_minutes-retained_minutes}个技术有效分钟。"
              "这可能改变事件覆盖，尚无独立事件证据证明排除随机。三尺度的名义水量与COD负荷重算一致，不代表原生测量积分已经验证。"
              f"合成采用8月1日至8月30日的30日日历窗口，其中共同有效时长{window_hours}小时；缺口保留并重置状态。记录的T/日历是回顾条件，且生成窗口属于拟合域，不是独立测试。\n\n"
              f"## 4. 实际结果\n\n{len(temporal)}个时间原型、{len(margin_checks)}个经验边际、{len(copula)}个Copula拟合和{len(trajectory)}条轨迹完成。最大可逆误差{temporal.roundtrip_error_scaled.max():.3g}；经验广义逆训练支持恢复误差{margin_checks.roundtrip_absolute_error.max():.3g}。下表在各尺度×探索种子上作描述性汇总，不是置信区间或独立环境事件重复。\n\n"
              + table + f"\n{len(near_upper)}组t自由度接近200数值搜索上界，具体case见边界诊断CSV；优化收敛不代表尾部结构可辨识，不能把200当已确定的物理/统计参数。\n\n"
              "## 5. 输出与图表\n\n[诊断数据](../artifacts/archive_sensitivity/validation/synthesis_diagnostics.csv)、[全物理滞后相关](../artifacts/archive_sensitivity/validation/temporal_correlations.csv)、[轨迹文件谱系](../artifacts/archive_sensitivity/validation/trajectory_file_map.csv)、[支持卡](../artifacts/archive_sensitivity/validation/support_card.csv)。"
              "两变换各一张三面板图提供SVG/PDF/PNG与全108轨迹源CSV；颜色表示Copula，线型/标记表示AR阶，跨种子取中位数。\n\n"
              f"## 6. 测试与验收\n\n{test_count}项工程测试通过。独立检查实际文件SHA、全部配置组合、时间/支持/T条件、负值账本和正式准入状态，记录于 [archive_execution_verification.json](../run_manifest/archive_execution_verification.json)。"
              "一小时在60min网格是拟合的一阶滞后，在5min网格是十二阶；更低误差不构成选60min的理由。应结合已输出6h/24h/168h诊断，不用该原型选择主步长。\n\n"
              "## 7. 失败、风险及局限\n\n首次M07在260字符Windows路径处失败；只缩短文件名并用SHA一致检查点恢复，未重新拟合。失败manifest/error.log及M07补充记录保留。"
              f"{len(trajectory)}条轨迹共{total_bins}个输出行出现{negatives['Q']}条负Q、{negatives['COD']}条负COD，涉及变换{negative_kinds}，未裁剪/投影；这是跨配置输出计数，不是真实发生率。"
              "本次log1p未出现负值，但expm1(y)在y<0时仍可能为负，不能宣称该变换保证非负。正式物理准入未通过。"
              "同期τ优劣随变换/尺度/AR变化，不存在本轮已验证的统一赢家。AR1对一小时ACF的描述改善不等于事件/过程保真、留出改进或跨时滞因果效应。\n\n"
              "## 8. 下一步\n\n先审查非负支持、残留自相关/平方创新/CCF、共同支持对候选事件覆盖的影响，再提交是否扩展原有ARMA/低阶VAR候选及冻结规则的证据。"
              "暂不扩大t自由度范围、不裁剪负值、不升级复杂分解或GPD。主步长仍null，原生频率UNKNOWN；科学参数/实验或验收变更继续先确认。"
              "已批准的M01/M02提交4dd7ae38已推送；本支线新增代码/报告/汇总结果未上传，另备白名单等待确认。\n")
    (ROOT / "reports/ARCHIVE_SENSITIVITY_阶段复核.md").write_text(report, encoding="utf-8")
    card = ("# Archive sensitivity dataset card\n\nPurpose: retrospective development-only method prototype. Native measurement support UNKNOWN; model_admitted=false; no formal time step.\n\n"
            "Inputs: hash-verified M02 aligned archive, Q/COD/T common complete calendar hours. Q in m3/h, COD_FW and COD_TW in source-header mg/L, T in degC. Nitrogen and effluent labels excluded.\n\n"
            f"Training: 2025-08-01 through 2026-04-30. Generation: first30 development calendar days, same recorded T/time, {window_hours} common support hours; hindsight conditional replay, not forecast.\n\n"
            f"{len(trajectory)} unconstrained trajectories; complete IDs, seeds and file hashes in validation/trajectory_file_map.csv and trajectory_manifest.csv. They share model/context and are not independent environmental event replications.\n\n"
            f"{negatives['Q']} negative Q and {negatives['COD']} negative COD output rows retained, no physical correction. No SUMO/field-TN/augmentation admission. No natural event frequency, calibrated process response or validated tail extrapolation claim.\n\n"
            "Raw observations and observation-level outputs remain local. Latest successful run and immutable failure/recovery history are under run_manifest/archive_sensitivity/runs.\n")
    (data_root / "DATASET_CARD.md").write_text(card, encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
