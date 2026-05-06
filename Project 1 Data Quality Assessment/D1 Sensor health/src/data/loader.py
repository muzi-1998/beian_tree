"""src/data/loader.py — raw min-level data loading, time alignment, imputation.

Per spec §4.7: detectors must receive equally-spaced 1-min series.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from pathlib import Path
from typing import Tuple


PHYS_RANGE = {
    # DO_*  : DO sensors
    **{f"DO_{p}_{i}": (-0.5, 12.0)  for p in (1, 2) for i in range(1, 5)},
    # ORP_* : ORP sensors
    **{f"ORP_{p}_{i}": (-550, 550)  for p in (1, 2) for i in range(1, 4)},
    # Flows
    **{f"QR_{p}":   (-50, 8000)     for p in (1, 2)},
    **{f"QIR_{p}":  (-20, 5000)     for p in (1, 2)},
}

DO_CHANNELS  = [f"DO_{p}_{i}"  for p in (1, 2) for i in range(1, 5)]
ORP_CHANNELS = [f"ORP_{p}_{i}" for p in (1, 2) for i in range(1, 4)]
FLOW_CHANNELS = [f"QR_{p}" for p in (1, 2)] + [f"QIR_{p}" for p in (1, 2)]
ALL_CHANNELS = DO_CHANNELS + ORP_CHANNELS + FLOW_CHANNELS


def load_raw(do_path: str, orp_path: str, flw_path: str) -> pd.DataFrame:
    """Load and merge the three min-level Excel files."""
    do  = pd.read_excel(do_path)
    orp = pd.read_excel(orp_path)
    flw = pd.read_excel(flw_path)
    df = do.merge(orp, on="data").merge(flw, on="data")
    df["data"] = pd.to_datetime(df["data"])
    df = df.set_index("data").sort_index()
    df.index.name = "timestamp"
    return df


def time_align_and_impute(
    df: pd.DataFrame,
    short_gap_min: int = 3,
    long_gap_min: int = 5,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """Align to absolute 1-min grid; impute short gaps; flag long gaps.

    Returns
    -------
    df_aligned : 1-min-regular DataFrame; short gaps filled via linear interp.
    flags : DataFrame of identical shape:
        0 = original, 1 = imputed (short), 2 = long-gap (kept as NaN).
    """
    full = pd.date_range(df.index.min(), df.index.max(), freq="1min")
    df_a = df.reindex(full).copy()
    df_a.index.name = "timestamp"

    # Range-clip to NaN
    for c in df_a.columns:
        if c in PHYS_RANGE:
            lo, hi = PHYS_RANGE[c]
            df_a.loc[(df_a[c] < lo) | (df_a[c] > hi), c] = np.nan

    flags = pd.DataFrame(0, index=df_a.index, columns=df_a.columns, dtype=np.int8)
    flags[df_a.isna()] = 2  # mark all NaN as long-gap initially

    # Short-gap interp (≤ short_gap_min)
    df_filled = df_a.interpolate(method="time", limit=short_gap_min, limit_area="inside")
    short_imputed = df_a.isna() & df_filled.notna()
    flags[short_imputed] = 1

    # Mark remaining NaN as long-gap (= 2)
    long_gap = df_filled.isna()
    flags[long_gap] = 2

    return df_filled, flags


def summary_stats(df: pd.DataFrame, flags: pd.DataFrame) -> pd.DataFrame:
    """Per-channel quick stats useful for sanity checks."""
    rows = []
    for c in df.columns:
        x = df[c]
        rows.append({
            "channel": c,
            "n_total": len(x),
            "n_valid": x.notna().sum(),
            "n_imputed_short": (flags[c] == 1).sum(),
            "n_long_gap": (flags[c] == 2).sum(),
            "miss_rate_pct": 100 * x.isna().mean(),
            "mean": x.mean(),
            "std": x.std(),
            "min": x.min(),
            "p05": x.quantile(0.05),
            "p50": x.quantile(0.50),
            "p95": x.quantile(0.95),
            "max": x.max(),
        })
    return pd.DataFrame(rows)
