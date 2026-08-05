"""Raw-source timestamp quality audit for D2 temporal integrity.

Timestamp defects must be classified before sorting or regular-grid alignment.
Long positive intervals are retained as gap-recovery diagnostics and are not
counted again as irregular sampling in Q_TI.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


SOURCE_HASH_KEYS = {"DO": "do_file", "ORP": "orp_file", "FLOW": "flw_file"}


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_source_files(contract: dict[str, Any], raw_dir: Path) -> dict[str, Path]:
    """Resolve and hash-verify timestamp sources declared by the 1.1 contract."""
    paths: dict[str, Path] = {}
    audit = contract.get("timestamp_audit", {})
    expected_hashes = contract.get("source_sha256", {})
    for source, facts in audit.items():
        path = Path(raw_dir) / str(facts["file"])
        if not path.exists():
            raise FileNotFoundError(f"Timestamp source not found: {path}")
        hash_key = SOURCE_HASH_KEYS.get(source)
        expected = expected_hashes.get(hash_key) if hash_key else None
        observed = file_sha256(path)
        if expected and observed.lower() != str(expected).lower():
            raise ValueError(
                f"Timestamp source hash mismatch for {source}: "
                f"expected {expected}, observed {observed}"
            )
        paths[source] = path
    return paths


def classify_timestamp_series(
    timestamps: pd.Series,
    *,
    expected_interval_sec: float = 60.0,
    jitter_tolerance_sec: float = 5.0,
    gap_interval_min_sec: float = 120.0,
) -> pd.DataFrame:
    """Classify adjacent raw timestamps without sorting the input series."""
    ts = pd.to_datetime(timestamps, errors="coerce")
    previous = ts.shift(1)
    valid_transition = ts.notna() & previous.notna()
    delta_sec = (ts - previous).dt.total_seconds()

    duplicate = valid_transition & delta_sec.eq(0)
    out_of_order = valid_transition & delta_sec.lt(0)
    gap_recovery = valid_transition & delta_sec.ge(gap_interval_min_sec)
    true_irregular = (
        valid_transition
        & delta_sec.gt(0)
        & delta_sec.lt(gap_interval_min_sec)
        & delta_sec.sub(expected_interval_sec).abs().gt(jitter_tolerance_sec)
    )
    regular = (
        valid_transition
        & delta_sec.gt(0)
        & delta_sec.lt(gap_interval_min_sec)
        & delta_sec.sub(expected_interval_sec).abs().le(jitter_tolerance_sec)
    )

    event_type = pd.Series("first_or_invalid", index=ts.index, dtype="object")
    event_type.loc[regular] = "regular"
    event_type.loc[true_irregular] = "true_irregular"
    event_type.loc[gap_recovery] = "gap_recovery"
    event_type.loc[duplicate] = "duplicate"
    event_type.loc[out_of_order] = "out_of_order"

    return pd.DataFrame({
        "timestamp": ts,
        "previous_timestamp": previous,
        "delta_sec": delta_sec,
        "valid_transition": valid_transition,
        "regular": regular,
        "true_irregular": true_irregular,
        "duplicate": duplicate,
        "out_of_order": out_of_order,
        "gap_recovery": gap_recovery,
        "event_type": event_type,
    })


def audit_timestamp_sources(
    contract: dict[str, Any],
    raw_dir: Path,
    *,
    expected_start: pd.Timestamp,
    expected_end: pd.Timestamp,
    expected_interval_sec: float = 60.0,
    jitter_tolerance_sec: float = 5.0,
    gap_interval_min_sec: float = 120.0,
) -> dict[str, Any]:
    """Audit raw source order and return localized events and hourly counts."""
    paths = verify_source_files(contract, raw_dir)
    hourly_grid = pd.date_range(
        pd.Timestamp(expected_start).floor("h"),
        pd.Timestamp(expected_end).floor("h"),
        freq="1h",
    )
    event_frames: list[pd.DataFrame] = []
    hourly_frames: list[pd.DataFrame] = []
    summaries: list[dict[str, Any]] = []
    count_cols = [
        "valid_transition", "regular", "true_irregular", "duplicate",
        "out_of_order", "gap_recovery",
    ]

    for source, path in paths.items():
        raw = pd.read_excel(path, usecols=[0])
        classified = classify_timestamp_series(
            raw.iloc[:, 0],
            expected_interval_sec=expected_interval_sec,
            jitter_tolerance_sec=jitter_tolerance_sec,
            gap_interval_min_sec=gap_interval_min_sec,
        )
        classified.insert(0, "source_row", np.arange(2, len(classified) + 2))
        classified.insert(0, "source", source)

        event_mask = classified["event_type"].isin(
            ["true_irregular", "duplicate", "out_of_order", "gap_recovery"]
        )
        event_frames.append(classified.loc[event_mask].copy())

        event_hour = classified["timestamp"].dt.floor("h")
        counts = classified.assign(event_hour=event_hour).groupby("event_hour")[count_cols].sum()
        counts = counts.reindex(hourly_grid, fill_value=0).astype(int)
        counts.index.name = "timestamp"
        counts.insert(0, "source", source)
        hourly_frames.append(counts)

        denominator = int(classified["valid_transition"].sum())
        summary = {
            "source": source,
            "file": path.name,
            "hash_verified": True,
            "rows": int(len(classified)),
            "valid_transition_count": denominator,
        }
        for col in count_cols[1:]:
            count = int(classified[col].sum())
            summary[f"{col}_count"] = count
            summary[f"{col}_rate"] = count / denominator if denominator else np.nan
        summaries.append(summary)

    events = pd.concat(event_frames, ignore_index=True) if event_frames else pd.DataFrame()
    hourly = pd.concat(hourly_frames).sort_index() if hourly_frames else pd.DataFrame()
    return {
        "events": events,
        "hourly": hourly,
        "summary": pd.DataFrame(summaries),
        "definition": {
            "expected_interval_sec": expected_interval_sec,
            "jitter_tolerance_sec": jitter_tolerance_sec,
            "gap_interval_min_sec": gap_interval_min_sec,
            "true_irregular": "positive sub-gap interval outside expected tolerance",
            "gap_recovery": "long interval; diagnostic only and represented by Q_GS",
        },
    }


def source_for_channel(sensor_id: str) -> str:
    if sensor_id.startswith("DO_"):
        return "DO"
    if sensor_id.startswith("ORP_"):
        return "ORP"
    return "FLOW"
