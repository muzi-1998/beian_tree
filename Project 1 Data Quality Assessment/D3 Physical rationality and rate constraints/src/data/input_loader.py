"""Load the canonical 1-minute observation grid without imputing values."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd


SENSOR_INPUT_KEYS = ("do_xlsx", "orp_xlsx")
AUXILIARY_INPUT_KEYS = ("temperature_csv",)


def resolve_input_paths(paths_cfg: dict, root: Path) -> dict[str, Path]:
    resolved = {}
    for key in (*SENSOR_INPUT_KEYS, *AUXILIARY_INPUT_KEYS):
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
    frames = [_read_source(inputs[key]) for key in SENSOR_INPUT_KEYS]
    merged = pd.concat(frames, axis=1).sort_index()
    freq = paths_cfg["time_grid"]["freq"]
    merged = merged.resample(freq).mean()
    expected = pd.date_range(
        paths_cfg["time_grid"]["expected_start"],
        paths_cfg["time_grid"]["expected_end"],
        freq=freq,
    )
    return merged.reindex(expected).rename_axis("ts")


def load_temperature_proxy(paths_cfg: dict, root: Path) -> pd.Series:
    """Load the minute influent-temperature proxy and mask invalid values."""
    path = resolve_input_paths(paths_cfg, root)["temperature_csv"]
    cfg = paths_cfg["temperature"]
    required = {cfg["timestamp_column"], cfg["value_column"]}
    frame = pd.read_csv(path, usecols=list(required))
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Temperature source missing columns: {sorted(missing)}")
    index = pd.to_datetime(
        frame[cfg["timestamp_column"]], format=cfg["datetime_format"], errors="raise"
    )
    raw_values = pd.to_numeric(frame[cfg["value_column"]], errors="coerce")
    low, high = map(float, cfg["valid_range_C"])
    valid = raw_values.between(low, high)
    values = raw_values.where(valid)
    series = pd.Series(values.to_numpy(dtype=float), index=index, name="influent_temperature_C")
    if series.index.has_duplicates:
        raise ValueError("Temperature source contains duplicate timestamps")
    if not series.index.is_monotonic_increasing:
        raise ValueError("Temperature source is not chronologically ordered")
    if len(series) > 1 and not series.index.to_series().diff().iloc[1:].eq(pd.Timedelta(minutes=1)).all():
        raise ValueError("Temperature source is not a complete 1-minute time axis")
    series.attrs.update(
        {
            "raw_missing_count": int(raw_values.isna().sum()),
            "invalid_range_count": int((raw_values.notna() & ~valid).sum()),
            "valid_range_C": [low, high],
            "source_rows": int(len(series)),
            "source_path": str(path),
        }
    )
    return series


def align_temperature_to_grid(temperature: pd.Series, target_index: pd.DatetimeIndex) -> pd.Series:
    """Align by exact minute without interpolation or extrapolation."""
    aligned = temperature.reindex(target_index)
    aligned.name = temperature.name
    aligned.attrs.update(temperature.attrs)
    return aligned


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

