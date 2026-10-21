"""Development archive diagnostics; no step is admitted from unknown refresh."""
from __future__ import annotations

import json
import time

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from .aggregation import aggregate_common_support
from .splitting import contiguous_blocks
from ..runtime import Execution, sha256, write_json


def verify_intake(ctx: Execution) -> dict:
    state = json.loads((ctx.root / "run_manifest/module_states.json").read_text(encoding="utf-8"))["M01"]["manifest"]
    if state["result"]["status"] == "FAIL" or state["tests"]["status"] != "PASS":
        raise ValueError("M01 has failed; its older canonical outputs cannot be consumed.")
    if state["config_sha256"] != ctx.config_hashes:
        raise ValueError("M01 configuration provenance differs; rerun M01 before consuming its flags.")
    for output in state["outputs"]:
        if sha256(ctx.root / output["path"]) != output["sha256"]:
            raise ValueError(f"M01 output hash mismatch: {output['path']}")
    return state


def run_preparation(ctx: Execution) -> dict:
    intake = verify_intake(ctx)
    variables = list(ctx.study["variable_mapping"])
    flags = pq.read_table(ctx.root / "artifacts/data/01_observation_flags.parquet",
                          columns=["timestamp", "variable", "value", "technical_valid"],
                          filters=[("split", "=", "development"), ("variable", "in", variables)]).to_pandas()
    frame = flags.pivot(index="timestamp", columns="variable", values="value").sort_index()
    valid_frame = flags.pivot(index="timestamp", columns="variable", values="technical_valid").reindex(frame.index)
    profiles = {"Q_COD_T": ["Q", "COD", "T"], "Q_COD_NH4_TN_T": variables}
    views, ledgers, comparisons, blocks = [], [], [], []
    archive_frame = frame.copy()
    archive_frame["split"] = "development"
    archive_frame["frame_role"] = "archive_technical_only_not_admitted_model_frame"
    archive_frame["main_step_minutes"] = None
    archive_frame["model_admitted"] = False
    archive_frame["native_refresh_status"] = "UNKNOWN"
    block_counts = {}
    for profile, needed in profiles.items():
        common = valid_frame[needed].all(axis=1)
        archive_frame[f"technical_support_{profile}"] = common
        ids, records = contiguous_blocks(frame.index, common.to_numpy(), profile)
        archive_frame[f"block_id_{profile}"] = ids
        block_counts[profile] = len(records)
        blocks.extend(records)
        concentrations = [v for v in needed if v in {"COD", "TN", "NH4_N"}]
        reference_views, reference = aggregate_common_support(frame, common, concentrations, 1440, profile)
        reference = reference.set_index(["bin_start", "variable"])
        for step in ctx.study["candidate_steps_minutes"]:
            started = time.perf_counter()
            v, ledger = aggregate_common_support(frame, common, concentrations, step, profile)
            duration = time.perf_counter() - started
            daily = ledger.assign(day=ledger["bin_start"].dt.floor("D")).groupby(["day", "variable"])[["V_m3", "L_kg"]].sum(min_count=1)
            daily.index.names = ["bin_start", "variable"]
            # Calendar bins are not extrapolated to the full day across missing support.
            daily_error = ((daily - reference[["V_m3", "L_kg"]]).abs()
                           / reference[["V_m3", "L_kg"]].abs().clip(lower=1.0)).max()
            max_error = float(ledger["roundtrip_error_scaled"].max())
            comparisons.append({"step_minutes": step, "support_profile": profile, "split": "development",
                                "nominal_archive_bins": int(len(v) / len(concentrations)),
                                "full_technical_archive_bins": int(v.drop_duplicates("bin_start")["full_technical_archive_bin"].sum()),
                                "common_technical_archive_rows": int(common.sum()), "fresh_count": None,
                                "reference_native_support": "UNKNOWN", "native_peak_loss": None,
                                "native_phase_error_minutes": None, "native_event_duration_error_minutes": None,
                                "daily_volume_roundtrip_error_scaled": float(daily_error["V_m3"]),
                                "daily_load_roundtrip_error_scaled": float(daily_error["L_kg"]),
                                "FW_load_identity_error_scaled": max_error,
                                "median_abs_C_FW_minus_C_TW": float((v["C_FW"] - v["C_TW"]).abs().median()),
                                "arithmetic_runtime_seconds": duration,
                                "status": "PENDING_NATIVE_SUPPORT", "model_admitted": False,
                                "interpretation": "archive_arithmetic_only_not_event_or_process_validation", **ctx.metadata()})
            views.append(v)
            ledgers.append(ledger)
    views_out, ledger_out = pd.concat(views, ignore_index=True), pd.concat(ledgers, ignore_index=True)
    comparison = pd.DataFrame(comparisons)
    numeric_cols = ["daily_volume_roundtrip_error_scaled", "daily_load_roundtrip_error_scaled", "FW_load_identity_error_scaled"]
    max_roundtrip = float(comparison[numeric_cols].max().max())
    tolerance = ctx.study["numerical_invariants"]["relative_roundtrip_error_max"]
    if not np.isfinite(max_roundtrip) or max_roundtrip > tolerance:
        raise ValueError(f"Numerical load/support invariant failed: {max_roundtrip} > {tolerance}")
    for output in [views_out, ledger_out, archive_frame]:
        for key, value in ctx.metadata().items():
            output[key] = value
    block_frame = pd.DataFrame(blocks)
    block_frame["split"] = "development"
    for key, value in ctx.metadata().items():
        block_frame[key] = value
    archive_frame.reset_index().to_parquet(ctx.output("data/02_model_frame.parquet"), index=False, compression="zstd")
    block_frame.to_parquet(ctx.output("data/02_time_blocks.parquet"), index=False, compression="zstd")
    views_out.to_parquet(ctx.output("data/02_concentration_views.parquet"), index=False, compression="zstd")
    ledger_out.to_parquet(ctx.output("data/02_load_ledger.parquet"), index=False, compression="zstd")
    comparison.to_csv(ctx.output("validation/02_scale_comparison.csv"), index=False, encoding="utf-8-sig")
    decision = {**ctx.metadata(), "status": "PENDING", "main_step_minutes": None, "frozen": False,
                "candidate_steps_minutes": ctx.study["candidate_steps_minutes"], "fit_split": "development",
                "input_M01_run_id": intake["run_id"], "native_frequency": "UNKNOWN",
                "one_minute_admitted": False, "scientific_coverage_threshold": None,
                "observational_basis": "nominal_1min_aligned_archive_quadrature_only",
                "reason": "no_verifiable_native_refresh_averaging_or_hold_metadata; cannot_quantify_true_event_information_loss",
                "numerical_identity": {"status": "PASS", "tolerance": tolerance, "max_scaled_error": max_roundtrip,
                                       "normalizer": "max(abs(reference),1) in each native V/load unit; numerical_only"},
                "not_executed": ["native_peak_phase_duration_validation", "event_admission", "SUMO_response", "scale_selection"]}
    write_json(ctx.output("validation/02_scale_decision.json"), decision)
    return {"status": "PARTIAL", "objective": "在 development 上核验候选尺度的共同技术支持、TW/FW 双视图和档案负荷算术；不批准主步长。",
            "methods": "5/15/60 min 日历对齐；保留 Q/COD/T 与五变量两种共同支持；每行仅按名义 1 min 作矩形求积。缺口不填补，不外推满日。C_TW=ΣCΔt/ΣΔt，C_FW=ΣQCΔt/ΣQΔt，V=ΣQΔt，L=ΣQCΔt/1000。",
            "inputs": f"消费经 SHA 核验的 M01 {intake['run_id']}；只读 development，未使用 validation/terminal_test 做分布或尺度选择。02_model_frame 仅为开发集技术档案，model_admitted=false。",
            "metrics": {"development_archive_rows": len(frame), "candidate_steps_minutes": ctx.study["candidate_steps_minutes"],
                        "support_profiles": list(profiles), "contiguous_technical_blocks": block_counts,
                        "concentration_view_rows": len(views_out), "load_ledger_rows": len(ledger_out),
                        "max_scaled_numerical_error": max_roundtrip, "main_step_minutes": None,
                        "fresh_count": None, "validation_or_test_rows_in_aggregation": 0},
            "checks": [{"name": "M01 产物与配置谱系", "status": "PASS", "reason": "消费前核对全部上游文件 SHA 与配置 SHA。"},
                       {"name": "同支持 TW/FW/V/L 及日账本", "status": "PASS", "reason": f"最大数值重算误差 {max_roundtrip:.3g}，小于既定 {tolerance:g}；仅为算术恒等式。"},
                       {"name": "主步长及有效独立信息", "status": "PENDING", "reason": "原生信息 UNKNOWN；未报告原生峰值损失、事件相位误差或过程响应合格。"}],
            "limitations": ["名义档案求积不是已验证的物理观测积分；SCADA 保持、插值或平均支持未知。",
                            "技术连续块不代表独立事件；完整档案窗口不代表原生测量覆盖达标。",
                            "氮负荷使用表头计量作暂定算术，氮质量口径未准入。两种支持的负荷不能混合比较。"],
            "next": ["保持 main_step_minutes=null；在可核实观测支持与事件/过程尺度证据到位后再提交主步长决策。",
                     "若元数据持续无法取得，应先征得用户确认有限用途研究协议，再开展敏感性研究；当前不擅自放宽主链。"]}
