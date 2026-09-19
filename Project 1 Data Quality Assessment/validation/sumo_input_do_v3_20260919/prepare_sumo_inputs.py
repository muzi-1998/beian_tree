from __future__ import annotations

import argparse
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = (
    ROOT
    / "1.1 Decomposition"
    / "Raw data"
    / "09_25.08.01-26.07.30_all data"
)
OUTPUT_DIR = Path(__file__).resolve().parent / "outputs"
INTERMEDIATE_DIR = OUTPUT_DIR / "intermediate"
START = pd.Timestamp("2025-08-01 00:00:00")
END = pd.Timestamp("2026-07-30 23:59:00")
MINUTE_INDEX = pd.date_range(START, END, freq="1min", name="日期")

FLAG_SOURCE_MISSING = 1
FLAG_PHYSICAL_INVALID = 2
FLAG_ZERO_EQUIVALENT = 4
FLAG_HAMPEL_REPLACED = 8
FLAG_SHORT_INTERPOLATED = 16
FLAG_LONG_GAP = 32


@dataclass(frozen=True)
class ColumnSpec:
    source: str
    original: str
    canonical: str
    unit: str
    kind: str
    lower: float | None = None
    upper: float | None = None
    unit_status: str = "registered"


SOURCES = {
    "water": RAW_DIR / "整年对齐_分钟数据_2025-08-01_2026-07-30_01_influent+effluent.csv",
    "bio": RAW_DIR / "整年对齐_分钟数据_2025-08-01_2026-07-30_02_shengwuchi.csv",
    "dose": RAW_DIR / "整年对齐_分钟数据_2025-08-01_2026-07-30_04_jiayaojian.csv",
    "s3d": RAW_DIR / "整年对齐_分钟数据_2025-08-01_2026-07-30_05_S3Dchi.csv",
    "flow": RAW_DIR / "整年对齐_分钟数据_2025-08-01_2026-07-30_06_liuliangjiance.csv",
    "residual": RAW_DIR / "30分钟级_剩余污泥与回流渠MLSS_2025-08-01_2026-07-31.xlsx",
}


PROCESS_SPECS = [
    ColumnSpec("flow", "进水瞬时流量（m³/h）", "进水瞬时流量（m³/h）", "m3/h", "flow"),
    ColumnSpec("flow", "出水瞬时流量（m³/h）", "出水瞬时流量（m³/h）", "m3/h", "flow"),
    ColumnSpec("water", "进水PH", "进水pH", "pH", "ph", 0, 14),
    ColumnSpec("water", "进水COD（mg/L）", "进水COD（mg/L）", "mg/L", "concentration", 0),
    ColumnSpec("water", "进水氨氮（mg/L）", "进水氨氮（mg/L）", "mg/L", "concentration", 0),
    ColumnSpec("water", "进水温度（℃）", "进水温度（℃）", "degC", "temperature", 0, 50),
    ColumnSpec("water", "进水总磷（mg/L）", "进水总磷（mg/L）", "mg/L", "concentration", 0),
    ColumnSpec("water", "进水总氮（mg/L）", "进水总氮（mg/L）", "mg/L", "concentration", 0),
    ColumnSpec("water", "进水SS（mg/L）", "进水SS（mg/L）", "mg/L", "concentration", 0),
    ColumnSpec("water", "出水PH", "出水pH", "pH", "ph", 0, 14),
    ColumnSpec("water", "出水COD（mg/L）", "出水COD（mg/L）", "mg/L", "concentration", 0),
    ColumnSpec("water", "出水氨氮（mg/L）", "出水氨氮（mg/L）", "mg/L", "concentration", 0),
    ColumnSpec("water", "出水温度（℃）", "出水温度（℃）", "degC", "temperature", 0, 50),
    ColumnSpec("water", "出水总磷（mg/L）", "出水总磷（mg/L）", "mg/L", "concentration", 0),
    ColumnSpec("water", "出水总氮（mg/L）", "出水总氮（mg/L）", "mg/L", "concentration", 0),
    ColumnSpec("dose", "氯化铁流量计1（m³/h）", "氯化铁流量计1（m³/h）", "m3/h", "flow", unit_status="provisional_unverified"),
    ColumnSpec("dose", "氯化铁流量计2（m³/h）", "氯化铁流量计2（m³/h）", "m3/h", "flow", unit_status="provisional_unverified"),
    ColumnSpec("dose", "乙酸钠流量计2（m³/h）", "乙酸钠流量计2（m³/h）", "m3/h", "flow", unit_status="provisional_unverified"),
    ColumnSpec("dose", "乙酸钠流量计4（m³/h）", "乙酸钠流量计4（m³/h）", "m3/h", "flow", unit_status="provisional_unverified"),
    ColumnSpec("s3d", "排泥管流量计FIT1531A输出单位量（m³/h）", "FIT1531A排泥流量（m³/h）", "m3/h", "flow"),
    ColumnSpec("s3d", "排泥管流量计FIT1531B输出单位量（m³/h）", "FIT1531B排泥流量（m³/h）", "m3/h", "flow"),
    ColumnSpec("bio", "1#生物池外回流流量（m³/h）", "1#生物池外回流流量（m³/h）", "m3/h", "flow"),
    ColumnSpec("bio", "2#生物池外回流流量（m³/h）", "2#生物池外回流流量（m³/h）", "m3/h", "flow"),
    ColumnSpec("bio", "1#生物池内回流流量（m³/h）", "1#生物池内回流流量（m³/h）", "m3/h", "flow"),
    ColumnSpec("bio", "2#生物池内回流流量（m³/h）", "2#生物池内回流流量（m³/h）", "m3/h", "flow"),
    ColumnSpec("residual", "剩余污泥流量（m³/h）", "剩余污泥流量（m³/h）", "m3/h", "flow"),
    ColumnSpec("residual", "回流渠MLSS", "回流渠MLSS（mg/L）", "mg/L", "mlss", 0, 30000),
]


DO_ORP_SPECS = [
    *[
        ColumnSpec("bio", f"{line}#生物池DO{pos}（mg/L）", f"DO_{line}_{pos}（mg/L）", "mg/L", "do", -0.2, 20)
        for line in (1, 2)
        for pos in (1, 2, 3, 4)
    ],
    *[
        ColumnSpec("bio", f"{line}#生物池ORP{pos}（mV）", f"ORP_{line}_{pos}（mV）", "mV", "orp", -1500, 1500)
        for line in (1, 2)
        for pos in (1, 2, 3)
    ],
]


RATE_COLUMNS = [spec.canonical for spec in PROCESS_SPECS if spec.kind == "flow"]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _read_csv_source(source: str, specs: list[ColumnSpec]) -> pd.DataFrame:
    path = SOURCES[source]
    columns = ["日期", *[spec.original for spec in specs]]
    frame = pd.read_csv(path, usecols=columns, encoding="utf-8-sig", low_memory=False)
    frame["日期"] = pd.to_datetime(frame["日期"], errors="coerce")
    if frame["日期"].isna().any() or frame["日期"].duplicated().any():
        raise ValueError(f"Unexpected timestamp defect in {path.name}")
    frame = frame.set_index("日期").reindex(MINUTE_INDEX)
    result = pd.DataFrame(index=MINUTE_INDEX)
    for spec in specs:
        result[spec.canonical] = pd.to_numeric(frame[spec.original], errors="coerce")
    return result


def _read_residual_source(specs: list[ColumnSpec]) -> tuple[pd.DataFrame, dict[str, int]]:
    path = SOURCES["residual"]
    source = pd.read_excel(path, sheet_name="分钟级", usecols=["日期", *[s.original for s in specs]])
    parsed = pd.to_datetime(source["日期"], errors="coerce")

    # The workbook contains one duplicated calendar day and 226 time-only cells.
    # Time-only cells are anchored to the date of the immediately following
    # fully specified timestamp. Duplicated timestamps are not arbitrarily
    # selected; all competing values at that minute are treated as ambiguous.
    repaired = parsed.copy()
    bad_positions = np.flatnonzero(parsed.isna().to_numpy())
    for position in bad_positions:
        next_valid = parsed.iloc[position + 1 :].dropna()
        if next_valid.empty:
            continue
        raw_value = source.iloc[position]["日期"]
        try:
            clock = pd.to_datetime(str(raw_value)).time()
        except (TypeError, ValueError):
            continue
        next_date = next_valid.iloc[0].normalize()
        repaired.iloc[position] = next_date + pd.Timedelta(
            hours=clock.hour, minutes=clock.minute, seconds=clock.second
        )

    work = source.drop(columns=["日期"]).copy()
    work.index = repaired
    work = work.loc[work.index.notna()]
    duplicate_mask = work.index.duplicated(keep=False)
    duplicate_rows = int(duplicate_mask.sum())
    duplicate_timestamps = int(work.index[duplicate_mask].nunique())
    if duplicate_rows:
        work.loc[duplicate_mask, :] = np.nan
    work = work.groupby(level=0, sort=True).first().reindex(MINUTE_INDEX)

    result = pd.DataFrame(index=MINUTE_INDEX)
    for spec in specs:
        result[spec.canonical] = pd.to_numeric(work[spec.original], errors="coerce")
    audit = {
        "time_only_cells_repaired": int(len(bad_positions)),
        "duplicate_rows_marked_ambiguous": duplicate_rows,
        "duplicate_timestamps_marked_ambiguous": duplicate_timestamps,
    }
    return result, audit


def load_raw(specs: list[ColumnSpec]) -> tuple[pd.DataFrame, dict[str, object]]:
    groups: list[pd.DataFrame] = []
    source_audit: dict[str, object] = {}
    for source in dict.fromkeys(spec.source for spec in specs):
        source_specs = [spec for spec in specs if spec.source == source]
        if source == "residual":
            frame, audit = _read_residual_source(source_specs)
            source_audit[source] = audit
        else:
            frame = _read_csv_source(source, source_specs)
            source_audit[source] = {
                "rows": int(len(frame)),
                "start": str(frame.index.min()),
                "end": str(frame.index.max()),
            }
        groups.append(frame)
    return pd.concat(groups, axis=1), source_audit


def _bounded_linear_interpolate(series: pd.Series, max_gap: int = 3) -> tuple[pd.Series, pd.Series]:
    missing = series.isna()
    group_id = missing.ne(missing.shift(fill_value=False)).cumsum()
    run_size = missing.groupby(group_id).transform("sum")
    bounded = series.notna().shift(1, fill_value=False).groupby(group_id).transform("max")
    bounded &= series.notna().shift(-1, fill_value=False).groupby(group_id).transform("max")
    eligible = missing & (run_size <= max_gap) & bounded
    candidate = series.interpolate(method="time", limit_area="inside")
    result = series.copy()
    result.loc[eligible] = candidate.loc[eligible]
    return result, eligible


def _longest_missing_run(series: pd.Series) -> int:
    missing = series.isna()
    if not missing.any():
        return 0
    group = missing.ne(missing.shift(fill_value=False)).cumsum()
    sizes = missing.groupby(group).sum()
    return int(sizes.max())


def _physical_screen(series: pd.Series, spec: ColumnSpec) -> tuple[pd.Series, pd.Series, pd.Series, float | None]:
    clean = series.copy()
    invalid = pd.Series(False, index=series.index)
    zero_equivalent = pd.Series(False, index=series.index)
    zero_deadband: float | None = None

    if spec.kind == "flow":
        positive = series[series > 0]
        positive_median = float(positive.median()) if not positive.empty else np.nan
        zero_deadband = 0.05 * positive_median if np.isfinite(positive_median) else 0.0
        negative = series < 0
        zero_equivalent = negative & (series.abs() <= zero_deadband)
        invalid = negative & ~zero_equivalent
        clean.loc[zero_equivalent] = 0.0
        clean.loc[invalid] = np.nan
    elif spec.kind == "do":
        negative = series < 0
        zero_equivalent = negative & (series >= -0.05)
        clean.loc[zero_equivalent] = 0.0
        invalid |= negative & ~zero_equivalent
        if spec.lower is not None:
            invalid |= series < spec.lower
        if spec.upper is not None:
            invalid |= series > spec.upper
        clean.loc[invalid] = np.nan
        zero_deadband = 0.05
    else:
        if spec.lower is not None:
            invalid |= series < spec.lower
        if spec.upper is not None:
            invalid |= series > spec.upper
        clean.loc[invalid] = np.nan
    return clean, invalid, zero_equivalent, zero_deadband


def _hampel(series: pd.Series, window: int = 15, k: float = 6.0) -> tuple[pd.Series, pd.Series, float]:
    rolling_median = series.rolling(window=window, center=True, min_periods=8).median()
    absolute_deviation = (series - rolling_median).abs()
    rolling_mad = absolute_deviation.rolling(window=window, center=True, min_periods=8).median()
    nonzero_diff = series.diff().abs()
    nonzero_diff = nonzero_diff[(nonzero_diff > 0) & np.isfinite(nonzero_diff)]
    global_floor = float(nonzero_diff.median()) if not nonzero_diff.empty else 1e-6
    global_floor = max(global_floor, 1e-6)
    scale = np.maximum(1.4826 * rolling_mad, global_floor)
    outlier = series.notna() & rolling_median.notna() & (absolute_deviation > k * scale)
    result = series.copy()
    result.loc[outlier] = rolling_median.loc[outlier]
    return result, outlier, global_floor


def clean_frame(raw: pd.DataFrame, specs: list[ColumnSpec]) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    clean = pd.DataFrame(index=raw.index)
    flags = pd.DataFrame(index=raw.index)
    qa_rows: list[dict[str, object]] = []

    for spec in specs:
        source = raw[spec.canonical]
        value, invalid, zero_equivalent, zero_deadband = _physical_screen(source, spec)
        hampel_value, hampel_candidate, noise_floor = _hampel(value)
        if spec.kind == "flow":
            # Pump, recycle and dosing pulses are process inputs. A local MAD
            # excursion alone is insufficient evidence for replacement.
            hampel_replaced = pd.Series(False, index=value.index)
        else:
            value = hampel_value
            hampel_replaced = hampel_candidate
        value, interpolated = _bounded_linear_interpolate(value, max_gap=3)
        long_gap = value.isna()

        bitmask = np.zeros(len(value), dtype=np.uint8)
        bitmask[source.isna().to_numpy()] |= FLAG_SOURCE_MISSING
        bitmask[invalid.to_numpy()] |= FLAG_PHYSICAL_INVALID
        bitmask[zero_equivalent.to_numpy()] |= FLAG_ZERO_EQUIVALENT
        bitmask[hampel_replaced.to_numpy()] |= FLAG_HAMPEL_REPLACED
        bitmask[interpolated.to_numpy()] |= FLAG_SHORT_INTERPOLATED
        bitmask[long_gap.to_numpy()] |= FLAG_LONG_GAP

        clean[spec.canonical] = value
        flags[spec.canonical] = bitmask
        qa_rows.append(
            {
                "变量": spec.canonical,
                "来源": spec.source,
                "单位": spec.unit,
                "单位状态": spec.unit_status,
                "原始缺失率（%）": 100 * source.isna().mean(),
                "物理无效率（%）": 100 * invalid.mean(),
                "零点等效率（%）": 100 * zero_equivalent.mean(),
                "Hampel候选率（%）": 100 * hampel_candidate.mean(),
                "Hampel替换率（%）": 100 * hampel_replaced.mean(),
                "短缺口插值率（%）": 100 * interpolated.mean(),
                "清洗后缺失率（%）": 100 * value.isna().mean(),
                "最长剩余缺口（min）": _longest_missing_run(value),
                "Hampel全局尺度下限": noise_floor,
                "零点等效阈值": zero_deadband,
            }
        )
    return clean, flags.astype("uint8"), pd.DataFrame(qa_rows)


def aggregate(frame: pd.DataFrame, freq: str, expected: int, min_fraction: float = 0.8) -> pd.DataFrame:
    result = frame.resample(freq).mean()
    counts = frame.resample(freq).count()
    required = math.ceil(expected * min_fraction)
    return result.mask(counts < required)


def make_derived(clean: pd.DataFrame) -> pd.DataFrame:
    derived = pd.DataFrame(index=clean.index)
    for column in RATE_COLUMNS:
        derived[column.replace("（m³/h）", "（m³/d）")] = clean[column] * 24.0

    derived["MBR循环流（m³/d）"] = 24.0 * (
        clean["剩余污泥流量（m³/h）"]
        + clean["2#生物池外回流流量（m³/h）"]
        + clean["1#生物池外回流流量（m³/h）"]
    )
    tn = clean["进水总氮（mg/L）"]
    derived["frSNHx_TKN（氨氮/总氮）"] = (clean["进水氨氮（mg/L）"] / tn).where(tn > 0)
    derived["frSU_SCCOD代理量（mg/L）"] = clean["出水COD（mg/L）"] - 2.5
    return derived


def _write_csv(frame: pd.DataFrame, path: Path) -> None:
    output = frame.reset_index()
    output.to_csv(path, index=False, encoding="utf-8-sig", date_format="%Y-%m-%d %H:%M:%S", float_format="%.8g")


def _write_data_products(prefix: str, raw: pd.DataFrame, clean: pd.DataFrame) -> list[Path]:
    paths: list[Path] = []
    for label, frame in (("raw", raw), ("clean", clean)):
        path = INTERMEDIATE_DIR / f"{prefix}_{label}.csv"
        _write_csv(frame, path)
        paths.append(path)
    if prefix.startswith("process"):
        derived = make_derived(clean)
        path = INTERMEDIATE_DIR / f"{prefix}_derived.csv"
        _write_csv(derived, path)
        paths.append(path)
    return paths


def _dictionary(specs: Iterable[ColumnSpec]) -> pd.DataFrame:
    rows = []
    for spec in specs:
        rows.append(
            {
                "输出变量": spec.canonical,
                "原始字段": spec.original,
                "原始文件组": spec.source,
                "单位": spec.unit,
                "变量类型": spec.kind,
                "物理下限": spec.lower,
                "物理上限": spec.upper,
                "单位确认状态": spec.unit_status,
            }
        )
    rows.extend(
        [
            {"输出变量": "MBR循环流（m³/d）", "原始字段": "剩余污泥+两线外回流", "原始文件组": "derived", "单位": "m3/d", "变量类型": "formula", "单位确认状态": "derived"},
            {"输出变量": "frSNHx_TKN（氨氮/总氮）", "原始字段": "进水氨氮/进水总氮", "原始文件组": "derived", "单位": "dimensionless", "变量类型": "formula", "单位确认状态": "derived"},
            {"输出变量": "frSU_SCCOD代理量（mg/L）", "原始字段": "出水COD-2.5", "原始文件组": "derived", "单位": "mg/L", "变量类型": "formula", "单位确认状态": "user-specified proxy; not a fraction"},
        ]
    )
    return pd.DataFrame(rows)


def _write_report(qa: pd.DataFrame, residual_audit: dict[str, object]) -> None:
    top_hampel = qa.nlargest(5, "Hampel替换率（%）")[["变量", "Hampel替换率（%）"]]
    top_missing = qa.nlargest(5, "清洗后缺失率（%）")[["变量", "清洗后缺失率（%）"]]
    report = f"""# SUMO 输入数据准备与质量审计

## 结论

- 主动态时间尺度：5 min。
- 1 min：保留用于原始证据、异常定位与时间尺度敏感性。
- 1 h：仅用于 DQR 小时证据连接、工况摘要和报告，不作为主 SUMO forcing。
- 所有清洗先在 1 min 完成，随后生成 5 min 与 1 h，避免不同时间尺度分别清洗造成结果漂移。
- 缺失值只对内部有界且不超过 3 min 的缺口进行线性插值；长缺口保留为空值，进入 unrecoverable/repair 资格判断。

## 15 min rolling median/MAD

采用中心 15 min、至少 8 个有效点、`k=6` 的保守 Hampel 技术异常筛查。流量、回流、排泥和加药通道仅输出 Hampel 候选诊断，不因局部偏离自动替换，避免删除真实泵启停脉冲。状态量清洗副本可替换候选值。该步骤不得在论文中描述为实时因果滤波；未来在线部署应补做 trailing-window 敏感性。

## 剩余污泥与回流渠 MLSS 时间戳

- 仅时间单元格修复：{residual_audit.get('time_only_cells_repaired', 0)} 行。
- 重复行标记为歧义：{residual_audit.get('duplicate_rows_marked_ambiguous', 0)} 行。
- 重复时间点标记为歧义：{residual_audit.get('duplicate_timestamps_marked_ambiguous', 0)} 个。

重复时间点没有选择任一副本或取均值，避免把“停泵”与“运行”两个互斥状态平均成虚假中间流量。

## 单位限制

氯化铁和乙酸钠标签登记为 m3/h，但数值量级要求继续核对 PLC scaling、仪表工程单位及小数点。工作簿中的 m3/d 仅按登记单位乘以 24，状态为 provisional，不应直接写成已核实的实际日投加量。

## Hampel 替换率最高的变量

{top_hampel.to_markdown(index=False, floatfmt='.4f')}

## 清洗后缺失率最高的变量

{top_missing.to_markdown(index=False, floatfmt='.4f')}
"""
    (OUTPUT_DIR / "SUMO_input_preparation_QA_ZH.md").write_text(report, encoding="utf-8")


def prepare() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    INTERMEDIATE_DIR.mkdir(parents=True, exist_ok=True)

    process_raw, process_source_audit = load_raw(PROCESS_SPECS)
    sensor_raw, sensor_source_audit = load_raw(DO_ORP_SPECS)
    process_clean, process_flags, process_qa = clean_frame(process_raw, PROCESS_SPECS)
    sensor_clean, sensor_flags, sensor_qa = clean_frame(sensor_raw, DO_ORP_SPECS)
    qa = pd.concat([process_qa, sensor_qa], ignore_index=True)

    process_5m_raw = aggregate(process_raw, "5min", 5)
    process_5m_clean = aggregate(process_clean, "5min", 5)
    process_1h_raw = aggregate(process_raw, "1h", 60)
    process_1h_clean = aggregate(process_clean, "1h", 60)
    sensor_5m_raw = aggregate(sensor_raw, "5min", 5)
    sensor_5m_clean = aggregate(sensor_clean, "5min", 5)

    csv_paths: list[Path] = []
    csv_paths += _write_data_products("process_1min", process_raw, process_clean)
    csv_paths += _write_data_products("process_5min", process_5m_raw, process_5m_clean)
    csv_paths += _write_data_products("process_1h", process_1h_raw, process_1h_clean)
    csv_paths += _write_data_products("sensors_1min", sensor_raw, sensor_clean)
    csv_paths += _write_data_products("sensors_5min", sensor_5m_raw, sensor_5m_clean)

    qa.to_csv(INTERMEDIATE_DIR / "qa_summary.csv", index=False, encoding="utf-8-sig")
    dictionary = _dictionary([*PROCESS_SPECS, *DO_ORP_SPECS])
    dictionary.to_csv(INTERMEDIATE_DIR / "data_dictionary.csv", index=False, encoding="utf-8-sig")

    process_raw.to_parquet(OUTPUT_DIR / "SUMO_process_inputs_1min_raw.parquet")
    process_clean.to_parquet(OUTPUT_DIR / "SUMO_process_inputs_1min_clean.parquet")
    make_derived(process_clean).to_parquet(OUTPUT_DIR / "SUMO_process_inputs_1min_derived.parquet")
    process_5m_clean.join(make_derived(process_5m_clean), rsuffix="_derived").to_parquet(
        OUTPUT_DIR / "SUMO_process_inputs_5min_ready.parquet"
    )
    process_1h_clean.join(make_derived(process_1h_clean), rsuffix="_derived").to_parquet(
        OUTPUT_DIR / "SUMO_process_inputs_1h_ready.parquet"
    )
    sensor_raw.to_parquet(OUTPUT_DIR / "SUMO_DO_ORP_1min_raw.parquet")
    sensor_clean.to_parquet(OUTPUT_DIR / "SUMO_DO_ORP_1min_clean.parquet")
    sensor_5m_clean.to_parquet(OUTPUT_DIR / "SUMO_DO_ORP_5min_ready.parquet")
    pd.concat(
        {"process": process_flags, "sensor": sensor_flags}, axis=1
    ).to_parquet(OUTPUT_DIR / "SUMO_input_quality_flags_1min.parquet")

    residual_audit = process_source_audit.get("residual", {})
    _write_report(qa, residual_audit if isinstance(residual_audit, dict) else {})
    manifest = {
        "run_id": "SUMO-INPUT-V3-20260919",
        "period": {"start": str(START), "end": str(END)},
        "time_scale": {"primary": "5min", "sensitivity": "1min", "context": "1h"},
        "cleaning": {
            "hampel_window_min": 15,
            "hampel_k": 6.0,
            "hampel_alignment": "centered_offline_common_technical_qc",
            "linear_interpolation_max_gap_min": 3,
            "aggregation_min_support_fraction": 0.8,
        },
        "source_audit": {**process_source_audit, **sensor_source_audit},
        "input_sha256": {key: sha256(path) for key, path in SOURCES.items()},
        "intermediate_sha256": {path.name: sha256(path) for path in csv_paths},
        "final_outputs": {},
    }
    (OUTPUT_DIR / "SUMO_input_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def finalize_manifest() -> None:
    path = OUTPUT_DIR / "SUMO_input_manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    outputs = {}
    for item in sorted(OUTPUT_DIR.iterdir()):
        if item.is_file() and item.name != path.name:
            outputs[item.name] = {"bytes": item.stat().st_size, "sha256": sha256(item)}
    manifest["final_outputs"] = outputs
    path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--finalize", action="store_true")
    args = parser.parse_args()
    if args.finalize:
        finalize_manifest()
    else:
        prepare()


if __name__ == "__main__":
    main()
