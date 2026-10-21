"""Read-only intake of the aligned exports, preserving lexical cell provenance."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq

from .label_admission import label_admission
from .native_frequency import archive_frequency_diagnostics
from ..preparation.splitting import split_ids
from ..runtime import Execution, sha256, write_json


def technical_valid(values: pd.Series, variable: str) -> pd.Series:
    finite = pd.Series(np.isfinite(values.to_numpy(dtype=float)), index=values.index)
    if variable == "Q":
        return finite & values.gt(0)
    if variable in {"COD", "TN", "NH4_N", "effluent_TN", "effluent_NH4_N"}:
        return finite & values.ge(0)
    return finite


def parse_archive_clock(raw: pd.Series, timezone: str) -> pd.DatetimeIndex:
    parsed = pd.DatetimeIndex(pd.to_datetime(raw, format="mixed", errors="raise"))
    parsed = parsed.tz_localize(timezone, ambiguous="raise", nonexistent="raise")
    if parsed.has_duplicates or not parsed.is_monotonic_increasing:
        raise ValueError("Archive clock has duplicate or unordered timestamps; no silent sorting/averaging allowed.")
    if not parsed.equals(parsed.floor("min")):
        raise ValueError("Aligned archive contains off-minute timestamps; revise source audit before aggregation.")
    return parsed


def run_intake(ctx: Execution) -> dict:
    study = ctx.study
    raw_root = (ctx.root / ctx.contracts["external_inputs"]["raw_data"]["path"]).resolve()
    mappings = {k: dict(v) for k, v in study["variable_mapping"].items()}
    quality_file = mappings["COD"]["file"]
    labels = {"effluent_TN": "出水总氮（mg/L）", "effluent_NH4_N": "出水氨氮（mg/L）"}
    for name, column in labels.items():
        mappings[name] = {"file": quality_file, "column": column, "unit": "mg N/L pending source confirmation"}
    frames, sources = {}, []
    for filename in sorted({m["file"] for m in mappings.values()}):
        path = raw_root / filename
        source_hash = sha256(path)
        cols = ["日期"] + [m["column"] for m in mappings.values() if m["file"] == filename]
        frame = pd.read_csv(path, encoding="utf-8-sig", usecols=cols, dtype=str, keep_default_na=False)
        frame.index = parse_archive_clock(frame.pop("日期"), study["timezone"])
        frames[filename] = frame
        expected = pd.date_range(frame.index[0], frame.index[-1], freq="min")
        missing = expected.difference(frame.index)
        sources.append({"file": filename, "sha256": source_hash, "bytes": path.stat().st_size,
                        "records": len(frame), "start": frame.index[0].isoformat(),
                        "end": frame.index[-1].isoformat(), "duplicate_timestamps": 0,
                        "missing_archive_grid_rows": len(missing), "source_type": "aligned_archive",
                        "source_record_index": "1-based CSV logical data record; header excluded"})
    first = next(iter(frames.values())).index
    if any(not frame.index.equals(first) for frame in frames.values()):
        raise ValueError("Core source clocks do not agree; explicit support reconciliation is required.")
    actual_dates = set(first.strftime("%Y-%m-%d"))
    target_dates = pd.date_range(study["target_period"]["start"], study["target_period"]["end"], freq="D")
    missing_dates = [x.strftime("%Y-%m-%d") for x in target_dates if x.strftime("%Y-%m-%d") not in actual_dates]
    splits = split_ids(first, study)
    if "outside_target" in splits:
        raise ValueError("Archive contains records outside the declared target; explicit reconciliation required.")
    source_hashes = {s["file"]: s["sha256"] for s in sources}
    frequency, quality = [], []
    all_valid = np.ones(len(first), dtype=bool)
    core_valid = np.ones(len(first), dtype=bool)
    flags_path = ctx.output("data/01_observation_flags.parquet")
    with pq.ParquetWriter(flags_path, schema=pa.schema([
        ("timestamp", pa.timestamp("ns", tz=study["timezone"])), ("variable", pa.string()),
        ("raw_value", pa.string()), ("value", pa.float64()), ("unit", pa.string()),
        ("source_file", pa.string()), ("source_sha256", pa.string()), ("source_column", pa.string()),
        ("source_record_index", pa.int64()), ("split", pa.string()),
        ("archival_cell_present", pa.bool_()), ("observed", pa.bool_()),
        ("held", pa.bool_()), ("imputed", pa.bool_()), ("refresh_status", pa.string()),
        ("technical_valid", pa.bool_()), ("dqr_status", pa.string()),
        ("available_at", pa.timestamp("ns", tz=study["timezone"])), ("run_id", pa.string()),
        ("protocol_sha256", pa.string()), ("study_sha256", pa.string())
    ]), compression="zstd") as writer:
        for variable, mapping in mappings.items():
            raw = frames[mapping["file"]][mapping["column"]]
            values = pd.to_numeric(raw, errors="coerce").astype(float)
            valid = technical_valid(values, variable)
            if variable in study["variable_mapping"]:
                all_valid &= valid.to_numpy()
            if variable in {"Q", "COD", "T"}:
                core_valid &= valid.to_numpy()
            flags = pd.DataFrame({"timestamp": first, "variable": variable,
                                  "raw_value": raw.to_numpy(), "value": values.to_numpy(), "unit": mapping["unit"],
                                  "source_file": mapping["file"], "source_sha256": source_hashes[mapping["file"]],
                                  "source_column": mapping["column"], "source_record_index": np.arange(1, len(first) + 1),
                                  "split": splits, "archival_cell_present": raw.ne("").to_numpy(),
                                  "observed": pd.array([None] * len(first), dtype="boolean"),
                                  "held": pd.array([None] * len(first), dtype="boolean"),
                                  "imputed": pd.array([None] * len(first), dtype="boolean"),
                                  "refresh_status": "UNKNOWN", "technical_valid": valid.to_numpy(),
                                  "dqr_status": "PENDING", "available_at": pd.NaT,
                                  **ctx.metadata()})
            table = pa.Table.from_pandas(flags, schema=writer.schema, preserve_index=False)
            writer.write_table(table, row_group_size=131072)
            dev = splits == "development"
            frequency.append({"variable": variable, "source_channel": mapping["column"],
                              "source_file": mapping["file"], "archive_grid_minutes": 1,
                              **archive_frequency_diagnostics(values[dev], valid[dev]), **ctx.metadata()})
            for split in [s["id"] for s in study["splits"]]:
                mask = splits == split
                quality.append({"variable": variable, "split": split, "archive_rows": int(mask.sum()),
                                "present_cells": int(raw[mask].ne("").sum()),
                                "technical_valid_rows": int(valid[mask].sum()),
                                "nonfinite_or_unparseable": int((~np.isfinite(values[mask])).sum()),
                                "negative_finite": int((values[mask].lt(0) & np.isfinite(values[mask])).sum()),
                                "zero_rows": int(values[mask].eq(0).sum()), "fresh_count": None,
                                "audit_role": "mechanical_quality_only_not_distribution_or_model_selection",
                                **ctx.metadata()})
    pd.DataFrame(frequency).to_csv(ctx.output("validation/01_native_frequency.csv"), index=False, encoding="utf-8-sig")
    pd.DataFrame(quality).to_csv(ctx.output("validation/01_technical_quality.csv"), index=False, encoding="utf-8-sig")
    write_json(ctx.output("validation/01_label_admission.json"), label_admission(labels, ctx.metadata()))
    for source in sources:
        if sha256(raw_root / source["file"]) != source["sha256"]:
            raise RuntimeError("Raw file changed during intake; outputs cannot be admitted.")
    counts = {s["id"]: int((splits == s["id"]).sum()) for s in study["splits"]}
    audit = {**ctx.metadata(), "sources": sources, "timezone": study["timezone"],
             "target_period": study["target_period"], "archive_rows": len(first), "unique_archive_days": len(actual_dates),
             "split_rows": counts, "missing_target_dates": missing_dates,
             "technical_all_five_rows": int(all_valid.sum()), "technical_Q_COD_T_rows": int(core_valid.sum()),
             "native_frequency_status": "UNKNOWN", "raw_hash_unchanged": True,
             "nitrogen_units": "source_header_mg/L; nitrogen_basis_pending_confirmation",
             "holdout_access": {"purpose": "read_only_provenance_and_mechanical_flags_only", "fitting": False,
                                "distribution_diagnostics": "development_only",
                                "legacy_audit": "preexisting_audits_have_already_inspected_all_periods; no_pristine_holdout_claim"},
             "quality_rules": "finite; Q>0; COD/NH4/TN>=0; T finite_only; no_clip_no_fill_no_DQR_invention",
             "scientific_admission": "PENDING", "main_step_minutes": None}
    write_json(ctx.output("data/01_input_audit.json"), audit)
    return {"status": "PARTIAL", "objective": "核对两份核心分钟对齐档案和七个输入/标签通道，保留原值与逐单元来源。",
            "methods": "按既定日历切分；Q 使用 06 瞬时流量。只做有限/正值技术标记，不插值、不裁剪，不套用历史小时保持规则。原生刷新与可用时点一律 UNKNOWN。",
            "inputs": "两份只读 CSV；五个进水变量及两个出口候选标签。全时段只做来源及机械质量审计；常数段统计仅使用 development。",
            "metrics": {"archive_rows_per_source": len(first), "archive_days": len(actual_dates),
                        "flag_cells": len(first) * len(mappings), "split_rows": counts,
                        "technical_all_five_rows": int(all_valid.sum()), "technical_Q_COD_T_rows": int(core_valid.sum()),
                        "missing_target_dates": missing_dates, "native_frequency": "UNKNOWN",
                        "confirmed_fresh_count": None, "raw_hash_unchanged": True},
            "checks": [{"name": "来源与时钟", "status": "PASS", "reason": "两源时钟一致，无重复/乱序；输入前后 SHA256 相同。"},
                       {"name": "原生支持", "status": "PENDING", "reason": "暂无可核实元数据；observed/held/imputed 保持空值，刷新状态 UNKNOWN。"},
                       {"name": "标签和 DQR", "status": "PENDING", "reason": "列存在不等于独立标签、氮计量或 DQR 已准入。"}],
            "limitations": ["档案数值重复可能源于平稳、量化、保持或填补，不能由本次统计区分。",
                            "2026-07-31 原始数据缺失；未伪造完整 365 天。",
                            "氮计量口径、出口观测算子、延迟与实验室对照尚待核实。"],
            "next": ["M02 仅开展开发集档案算术诊断；主步长与原生频率保持待定。",
                     "后续取得仪表/SCADA 证据时更新本报告并保留本次不可变清单。"]}
