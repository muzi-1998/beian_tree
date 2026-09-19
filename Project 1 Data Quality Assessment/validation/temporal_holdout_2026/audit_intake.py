"""Read-only source intake audit; never fits or scores the candidate holdout."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import re
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import yaml


HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
NEW_START = pd.Timestamp("2026-04-14 00:00:00")
CHANNEL_PATTERN = re.compile(r"([12])#\u751f\u7269\u6c60(DO|ORP)([1-4])\uff08(mg/L|mV)\uff09")
FLOW_PATTERN = re.compile(r"([12])#\u751f\u7269\u6c60(\u5916|\u5185)\u56de\u6d41\u6d41\u91cf\uff08m\u00b3/h\uff09")
TIMESTAMP = "\u65e5\u671f"


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest() if hasattr(hashlib, "file_digest") else _digest(stream)


def _digest(stream) -> str:
    result = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        result.update(chunk)
    return result.hexdigest()


def mapping_rows(columns: list[str]) -> list[dict]:
    records = []
    for column in columns:
        if column == TIMESTAMP:
            continue
        channel = CHANNEL_PATTERN.fullmatch(column)
        flow = FLOW_PATTERN.fullmatch(column)
        if channel:
            line, analyte, position, unit = channel.groups()
            if (analyte == "DO" and unit != "mg/L") or (analyte == "ORP" and (unit != "mV" or position == "4")):
                raise ValueError(f"Invalid analyte/position/unit: {column}")
            canonical = f"{analyte}_{line}_{position}"
            role = "scored_sensor"
        elif flow:
            line, direction = flow.groups()
            canonical = f"{'QR' if direction == chr(0x5916) else 'QIR'}_{line}"
            unit, role = "m3/h", "context_only"
        else:
            raise ValueError(f"Unmapped source column: {column}")
        records.append({"source_column": column, "canonical_id": canonical, "unit": unit, "role": role})
    identifiers = [row["canonical_id"] for row in records]
    expected = {f"{a}_{line}_{position}" for a, n in [("DO", 4), ("ORP", 3)] for line in (1, 2) for position in range(1, n + 1)}
    expected |= {f"{kind}_{line}" for kind in ("QR", "QIR") for line in (1, 2)}
    if len(identifiers) != len(set(identifiers)) or set(identifiers) != expected:
        raise ValueError("Source must contain exactly 14 sensors and 4 context channels")
    return records


def read_csv(path: Path, mapped: bool = True) -> tuple[pd.DataFrame, dict, list[dict]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        columns = next(csv.reader(stream))
    if len(columns) != len(set(columns)):
        raise ValueError(f"Duplicate header: {path.name}")
    rows = mapping_rows(columns) if mapped else []
    frame = pd.read_csv(path, encoding="utf-8-sig", low_memory=False)
    ts = pd.to_datetime(frame.pop(TIMESTAMP), format="%Y-%m-%d %H:%M:%S", errors="raise")
    intervals = ts.diff().dt.total_seconds()
    summary = {
        "file_name": path.name, "sha256_raw_bytes": sha256(path), "size_bytes": path.stat().st_size,
        "row_count": len(frame), "first_timestamp": str(ts.min()), "last_timestamp": str(ts.max()),
        "duplicate_timestamp_rows": int(ts.duplicated(keep=False).sum()),
        "backward_intervals": int(intervals.lt(0).sum()),
        "interval_seconds_counts": {str(k): int(v) for k, v in intervals.value_counts().items()},
        "invalid_numeric_cells": {},
    }
    for col in frame:
        values = pd.to_numeric(frame[col], errors="coerce")
        summary["invalid_numeric_cells"][col] = int((frame[col].notna() & values.isna()).sum())
        frame[col] = values
    frame.index = pd.DatetimeIndex(ts, name="timestamp")
    if rows:
        frame = frame.rename(columns={r["source_column"]: r["canonical_id"] for r in rows})
    if not frame.index.is_unique or not frame.index.is_monotonic_increasing:
        raise ValueError(f"Aligned export clock requires review: {summary}")
    return frame, summary, rows


def compare_overlap(old: pd.DataFrame, new: pd.DataFrame, source: str) -> list[dict]:
    overlap = old.index.intersection(new.index)
    if overlap.empty or overlap.max() >= NEW_START:
        raise ValueError("Historical bridge must be nonempty and precede holdout")
    inserted = new.loc[(new.index >= old.index.min()) & (new.index <= old.index.max())].index.difference(old.index)
    output = []
    for col in old.columns:
        if col not in new:
            raise ValueError(f"Unmapped legacy column: {col}")
        left, right = old.loc[overlap, col], new.loc[overlap, col]
        finite = np.isfinite(left) & np.isfinite(right)
        diff = (left[finite] - right[finite]).abs()
        output.append({
            "source": source, "channel": col, "overlap_rows": len(overlap),
            "old_only_timestamp_rows": len(old.index.difference(new.index)),
            "new_only_timestamps_inside_old_span": len(inserted),
            "inserted_timestamp_new_present": int(new.loc[inserted, col].notna().sum()),
            "inserted_timestamp_new_missing": int(new.loc[inserted, col].isna().sum()),
            "both_present": int(finite.sum()), "both_missing": int((left.isna() & right.isna()).sum()),
            "old_missing_new_present": int((left.isna() & right.notna()).sum()),
            "old_present_new_missing": int((left.notna() & right.isna()).sum()),
            "equal_within_1e_9_fraction": float(diff.le(1e-9).mean()) if len(diff) else None,
            "within_0_0050001_fraction": float(diff.le(0.0050001).mean()) if len(diff) else None,
            "mae": float(diff.mean()) if len(diff) else None,
            "p99_abs_difference": float(diff.quantile(0.99)) if len(diff) else None,
            "max_abs_difference": float(diff.max()) if len(diff) else None,
        })
    return output


def unique_source(directory: Path, pattern: str) -> Path:
    matches = sorted(directory.glob(pattern))
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one source for {pattern}, found {len(matches)}")
    return matches[0]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-root", type=Path, required=True)
    args = parser.parse_args()
    raw_root = args.raw_root.resolve(strict=True)
    year_root = raw_root / "09_25.08.01-26.07.30_all data"
    minute_path = unique_source(year_root, "*\u5206\u949f\u6570\u636e*_02_shengwuchi.csv")
    daily_path = unique_source(year_root, "*\u65e5\u62a5\u8868*_02_shengwuchi.csv")
    hourly_path = unique_source(year_root, "*\u5c0f\u65f6\u5747\u503c*_02_shengwuchi.csv")
    output_root = HERE / "intake_audit"
    output_root.mkdir(exist_ok=True)
    print("Reading aligned minute, hourly and daily exports (intake only)", flush=True)
    minute, minute_meta, mapping = read_csv(minute_path)
    daily, daily_meta, _ = read_csv(daily_path)
    hourly, hourly_meta, _ = read_csv(hourly_path)
    pd.DataFrame(mapping).to_csv(output_root / "channel_mapping.csv", index=False, encoding="utf-8-sig", lineterminator="\n")

    future = minute.loc[minute.index >= NEW_START]
    completeness = []
    for month, part in future.groupby(future.index.to_period("M")):
        for col in part:
            completeness.append({"month": str(month), "channel": col, "exported_rows": len(part),
                                 "exported_values_present": int(part[col].notna().sum()),
                                 "export_missing_fraction": float(part[col].isna().mean()),
                                 "original_observation_provenance": "unverified_aligned_export"})
    pd.DataFrame(completeness).to_csv(output_root / "new_period_completeness.csv", index=False, lineterminator="\n")
    overlap, legacy = [], []
    for name in ("beian_min_1_DO_25-08-26-04.xlsx", "beian_min_2_ORP-08-26-04.xlsx", "beian_min_3_QR+QIR-08-26-04.xlsx"):
        path = raw_root / name
        print(f"Comparing historical overlap: {name}", flush=True)
        old = pd.read_excel(path)
        ts = pd.to_datetime(old.pop("data"), errors="raise")
        old = old.apply(pd.to_numeric, errors="raise")
        old.index = pd.DatetimeIndex(ts, name="timestamp")
        if not old.index.is_unique or old.index.max() >= NEW_START:
            raise ValueError("Legacy cutoff or duplicate contract requires review")
        legacy.append({"file_name": name, "sha256_raw_bytes": sha256(path), "rows": len(old),
                       "first_timestamp": str(old.index.min()), "last_timestamp": str(old.index.max()),
                       "backward_intervals": int(old.index.to_series().diff().lt(pd.Timedelta(0)).sum()),
                       "columns": list(old.columns)})
        overlap.extend(compare_overlap(old, minute, name))
    pd.DataFrame(overlap).to_csv(output_root / "historical_overlap.csv", index=False, lineterminator="\n")

    # Only old-period values enter aggregation-identity comparisons.
    old_minute = minute.loc[minute.index < NEW_START]
    summary_identity = []
    for label, supplied, frequency in [("hourly", hourly, "h"), ("daily", daily, "D")]:
        calculated = old_minute.resample(frequency).mean()
        for record in compare_overlap(calculated, supplied, label):
            summary_identity.append(record)
    pd.DataFrame(summary_identity).to_csv(output_root / "historical_aggregation_identity.csv", index=False, lineterminator="\n")

    temperature_path = unique_source(year_root, "*\u5206\u949f\u6570\u636e*_01_influent+effluent.csv")
    temp, temperature_meta, _ = read_csv(temperature_path, mapped=False)
    temp_col = "\u8fdb\u6c34\u6e29\u5ea6\uff08\u2103\uff09"
    temp_future = temp.loc[temp.index >= NEW_START, temp_col]
    temperature_meta["new_period_present_fraction"] = float(temp_future.notna().mean())
    temperature_meta["prior_use"] = "D3 temperature source already referenced; old study alignment ends 2026-04-13"
    config = yaml.safe_load((PROJECT / "DQR Multidimensional Aggregation and Evidence-Aware Integration" / "configs" / "aggregation_v2_3.yaml").read_text(encoding="utf-8"))
    result = {
        "audit_id": "DQR-TEMPORAL-INTAKE-20260905-v1.0", "audit_scope": "structural_QA_and_historical_bridge_no_holdout_scores_or_model_selection",
        "freeze_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=PROJECT, text=True).strip(),
        "software": {"python": platform.python_version(), "pandas": pd.__version__},
        "sources": {"minute": minute_meta, "hourly": hourly_meta, "daily": daily_meta, "temperature": temperature_meta},
        "legacy_sources": legacy,
        "holdout": {"start": str(NEW_START), "end_inclusive": str(future.index.max()),
                    "end_exclusive": str(future.index.max() + pd.Timedelta(minutes=1)),
                    "minute_rows": len(future), "hour_bins": len(future.resample("h")),
                    "day_bins": len(future.resample("D")), "sensor_count": 14,
                    "nominal_sensor_hours": 14 * len(future.resample("h")),
                    "original_config_end": config["study"]["future_holdout"]["end"],
                    "source_timestamp_provenance": "aligned_export_does_not_reveal_pre_sort_duplicate_or_missing_masks"},
        "holdout_distribution_and_performance_unexamined": True,
        "private_raw_files_copied_or_modified": False,
        "audit_script_sha256": sha256(Path(__file__)),
        "source_config_sha256": sha256(PROJECT / "DQR Multidimensional Aggregation and Evidence-Aware Integration" / "configs" / "aggregation_v2_3.yaml"),
        "audit_tables_sha256": {path.name: sha256(path) for path in sorted(output_root.glob("*.csv"))},
    }
    (output_root / "intake_manifest.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(result["holdout"], ensure_ascii=False, indent=2), flush=True)
    print(pd.DataFrame(overlap).to_string(index=False), flush=True)


if __name__ == "__main__":
    main()
