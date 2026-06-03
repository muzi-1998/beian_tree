"""src/outputs/tables.py — deliverable tables (plan §6.3).

Builds the multi-source data inventory table (with process semantics) and a
small helper to write any DataFrame to both CSV and a combined Excel workbook.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from pathlib import Path

from ..semantics import CHANNEL_META, PHYS_RANGE
from ..data.preprocess import FLAG


def inventory_table(frames_flags: dict) -> pd.DataFrame:
    """frames_flags: {channel: (series_native, flag_series_native, track)}.

    Returns one row per variable: class, zone, role, track, range, span,
    n_rows, missing%, range-violation%, outlier%, censored%, mean/std/min/max.
    """
    rows = []
    for ch, (s, fl, track) in frames_flags.items():
        meta = CHANNEL_META.get(ch, {})
        v = s.dropna()
        lo, hi = PHYS_RANGE.get(ch, (np.nan, np.nan))
        n = len(s)
        miss = 100.0 * s.isna().mean()
        rng_v = 100.0 * (fl == FLAG["RANGE"]).mean() if fl is not None else np.nan
        out_v = 100.0 * (fl == FLAG["OUTLIER"]).mean() if fl is not None else np.nan
        cen_v = 100.0 * (fl == FLAG["CENSORED"]).mean() if fl is not None else np.nan
        rows.append(dict(
            variable=ch, cls=meta.get("cls", "?"), zone=meta.get("zone", "?"),
            role=meta.get("role", "?"), group=meta.get("group", "?"),
            track=track, train=meta.get("train", 0),
            range_lo=lo, range_hi=hi,
            t_start=str(s.index.min()), t_end=str(s.index.max()),
            n_rows=n, missing_pct=round(miss, 3),
            range_violation_pct=round(rng_v, 3) if rng_v == rng_v else np.nan,
            iqr_outlier_pct=round(out_v, 3) if out_v == out_v else np.nan,
            censored_pct=round(cen_v, 3) if cen_v == cen_v else np.nan,
            mean=round(float(v.mean()), 4) if len(v) else np.nan,
            std=round(float(v.std()), 4) if len(v) else np.nan,
            min=round(float(v.min()), 4) if len(v) else np.nan,
            p50=round(float(v.median()), 4) if len(v) else np.nan,
            max=round(float(v.max()), 4) if len(v) else np.nan,
        ))
    return pd.DataFrame(rows)


def write_table(df: pd.DataFrame, table_root: Path, name: str) -> None:
    """Write a DataFrame to CSV (utf-8-sig for Excel-friendly Chinese)."""
    table_root = Path(table_root)
    table_root.mkdir(parents=True, exist_ok=True)
    df.to_csv(table_root / f"{name}.csv", index=False, encoding="utf-8-sig")


def write_excel(tables: dict, path: Path) -> None:
    """Write a dict {sheet_name: df} to one Excel workbook."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="openpyxl") as xw:
        for sheet, df in tables.items():
            df.to_excel(xw, sheet_name=sheet[:31], index=False)
