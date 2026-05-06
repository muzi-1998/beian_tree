"""src/aggregation/multiscale_export.py
Pessimistic time aggregation min → h → d → w (spec §11 of v1.0 plan).
"""
from __future__ import annotations
import pandas as pd


def to_hourly(d1_min: pd.DataFrame, q: float = 0.05) -> pd.DataFrame:
    """min → hour: q-quantile (pessimistic)."""
    return d1_min.resample("1h").quantile(q)


def to_daily(d1_h: pd.DataFrame, q: float = 0.05) -> pd.DataFrame:
    return d1_h.resample("1D").quantile(q)


def to_weekly(d1_d: pd.DataFrame, op: str = "min") -> pd.DataFrame:
    if op == "min":
        return d1_d.resample("1W").min()
    elif op == "mean":
        return d1_d.resample("1W").mean()
    raise ValueError(op)
