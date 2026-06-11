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


def whiteness_manifest(arma_df: pd.DataFrame, cmp_df: pd.DataFrame) -> pd.DataFrame:
    """§1.1 -> §1.2 input contract: per-channel whitening usability.

    Tells §1.2 whether each channel's "innovation" is a genuine ~i.i.d. white
    series (so iid control-charts apply) or a degraded fallback that is still
    autocorrelated (near-unit-root robust_z) / a censored floor — so §1.2 must
    branch its scoring instead of naively assuming whiteness.
    """
    keep = ["channel", "track", "acf1_innov", "mabsacf_innov", "lb_passrate_innov"]
    cm = cmp_df[[c for c in keep if c in cmp_df.columns]]
    m = arma_df.merge(cm, on=["channel", "track"], how="left")
    rows = []
    for _, r in m.iterrows():
        ch = r["channel"]; meta = CHANNEL_META.get(ch, {})
        fam = r.get("family", "arma")
        acc = bool(r.get("accepted")) if pd.notna(r.get("accepted")) else False
        a1 = r.get("acf1_innov")
        if fam == "floor":
            kind, whitened, mode = "censored_z", False, "floor_freeze"
            note = "post-anoxic 检测地板;走 floor/freeze + 截尾标准化,排除出白化考核"
        elif acc:
            kind, whitened, mode = "innovation", True, "iid"
            note = "已白化近 i.i.d. 创新;iid 控制图/独立性评分可用"
        else:
            kind, whitened, mode = "robust_z", False, "autocorr_aware"
            note = "近单位根;robust_z 非白噪声 -> 用自相关感知方法 + 倚重 D7 多变量一致性"
        neff = round((1 - abs(a1)) / (1 + abs(a1)), 4) if pd.notna(a1) else np.nan
        rows.append(dict(
            channel=ch, track=r["track"], group=meta.get("group"),
            zone=meta.get("zone"), cls=meta.get("cls"),
            family=fam, accepted=acc, whitened=whitened, innov_kind=kind,
            scoring_mode=mode,
            acf1_innov=round(float(a1), 4) if pd.notna(a1) else np.nan,
            mabsacf_innov=r.get("mabsacf_innov"),
            lb_passrate_innov=r.get("lb_passrate_innov"),
            n_eff_ratio=neff, note=note))
    out = pd.DataFrame(rows)
    order = {"min": 0, "hour": 1}
    return out.sort_values(["whitened", "track", "channel"],
                           ascending=[False, True, True],
                           key=lambda s: s.map(order) if s.name == "track" else s
                           ).reset_index(drop=True)


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
