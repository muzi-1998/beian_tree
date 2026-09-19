"""Isolated holdout paths, content fingerprints and no-opening contracts."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pandas as pd

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
OFFICIAL = Path(os.environ.get(
    "BEIAN_OFFICIAL_PROJECT",
    "D:/004_git/beian_tree-main/Project 1 Data Quality Assessment",
))
LEGACY = Path(os.environ.get(
    "BEIAN_LEGACY_PROJECT",
    "D:/004_git/beian_tree/Project 1 Data Quality Assessment",
))
START = pd.Timestamp("2026-04-14")
END = pd.Timestamp("2026-07-31")
HISTORICAL_END = START - pd.Timedelta(minutes=1)
D5_REFERENCE_END = pd.Timestamp("2026-01-27 04:30:00")
DIMENSIONS = {
    "D1": "D1 Sensor health",
    "D2": "D2 Temporal Continuity & Information Availability",
    "D3": "D3 Physical rationality and rate constraints",
    "D4": "D4 Parallel-redundancy Temporal Consistency",
    "D5": "D5 Topological Role Consistency and Structural Representativeness",
}
OUTPUT = HERE / "outputs"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def content_hash(path: Path) -> str:
    """Text content is LF-canonical; binary artifacts retain byte identity."""
    data = path.read_bytes()
    if path.suffix in {".py", ".yaml", ".yml", ".md", ".mjs"}:
        data = data.replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, default=str,
                               allow_nan=False) + "\n", encoding="utf-8", newline="\n")


def historical_only(frame: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(frame.index, pd.DatetimeIndex):
        raise TypeError("A DatetimeIndex is required for the freeze boundary")
    if not frame.index.is_unique or not frame.index.is_monotonic_increasing:
        raise ValueError("Historical inference requires a unique increasing clock")
    selected = frame.loc[frame.index < START].copy()
    if selected.empty:
        raise ValueError("No pre-holdout observations")
    return selected


def assert_fit_before_holdout(index: pd.DatetimeIndex, cutoff: pd.Timestamp) -> None:
    if len(index) == 0 or index.max() > cutoff or cutoff >= START:
        raise ValueError("Fit input violates the frozen historical cutoff")


def require_opening_gate(path: Path) -> dict:
    if not path.is_file():
        raise RuntimeError("Holdout remains sealed: no completed readiness gate")
    data = json.loads(path.read_text(encoding="utf-8"))
    required = ("historical_replay", "prefix_invariance", "chunk_equivalence",
                "time_contract", "unknown_evidence", "asset_closure")
    if data.get("performance_opening_allowed") is not True or any(data.get(key) != "passed" for key in required):
        raise RuntimeError("Holdout remains sealed: not all readiness contracts passed")
    return data
