"""Load the canonical 1-minute observation grid without imputing values."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd


INPUT_KEYS = ("do_xlsx", "orp_xlsx")


def resolve_input_paths(paths_cfg: dict, root: Path) -> dict[str, Path]:
    resolved = {}
    for key in INPUT_KEYS:
        path = Path(paths_cfg["input"][key])
        if not path.is_absolute():
            path = (root / path).resolve()
        if not path.exists():
            raise FileNotFoundError(f"D3 input not found: {path}")
        resolved[key] = path
    return resolved


def _read_source(path: Path) -> pd.DataFrame:
    frame = pd.read_excel(path)
    time_col = next((c for c in ("ts", "data", "date", "datetime") if c in frame.columns), None)
    if time_col is None:
        raise ValueError(f"No timestamp column found in {path.name}")
    frame = frame.rename(columns={time_col: "ts"})
    frame["ts"] = pd.to_datetime(frame["ts"], errors="raise")
    frame = frame.set_index("ts").sort_index()
    frame = frame.loc[:, ~frame.columns.astype(str).str.startswith("Unnamed")]
    frame = frame.apply(pd.to_numeric, errors="coerce")
    return frame.groupby(level=0).mean()


def load_aligned_data(paths_cfg: dict, root: Path) -> pd.DataFrame:
    """Align raw observations to section 1.1's canonical clock.

    Only duplicate timestamps are averaged. Missing minutes remain NaN so D2
    retains ownership of availability and D3 never scores interpolated values.
    """
    inputs = resolve_input_paths(paths_cfg, root)
    frames = [_read_source(inputs[key]) for key in INPUT_KEYS]
    merged = pd.concat(frames, axis=1).sort_index()
    freq = paths_cfg["time_grid"]["freq"]
    merged = merged.resample(freq).mean()
    expected = pd.date_range(
        paths_cfg["time_grid"]["expected_start"],
        paths_cfg["time_grid"]["expected_end"],
        freq=freq,
    )
    return merged.reindex(expected).rename_axis("ts")


def source_fingerprints(paths_cfg: dict, root: Path) -> dict[str, dict]:
    fingerprints = {}
    for key, path in resolve_input_paths(paths_cfg, root).items():
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        stat = path.stat()
        fingerprints[key] = {
            "name": path.name,
            "sha256": digest,
            "size_bytes": stat.st_size,
        }
    return fingerprints

