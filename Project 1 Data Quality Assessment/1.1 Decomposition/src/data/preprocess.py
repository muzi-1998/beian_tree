"""src/data/preprocess.py — TimeAligner + DataImputer (plan §2.3, §2.4).

Principle: "mark, don't clean" — anomalies are the scoring target of §1.2 and
must NOT be erased at the base layer. Every transformation is flagged.

TimeAligner
-----------
* min-level (DO/ORP/QR/QIR) -> absolute equidistant 1-min master clock.
* hourly (influent/effluent) decomposed at NATIVE 1 h, then forward-step held
  onto the 1-min clock with a `hold_flag` (plan §2.3 multi-rate alignment).
  We do NOT resample hourly onto 1 min before decomposition (would fabricate
  fake high-frequency content).

DataImputer
-----------
Flag codes per cell (int8):
  0 original | 1 short-gap interp/ffill | 2 long-gap (kept NaN)
  3 cosine-filled sparse hourly | 4 same-day-multi-gap day (excluded from fit)
  5 transition zone (24h either side of a long gap, down-weighted)
  6 hold (low-frequency source held onto 1-min clock)
  7 range/physical violation -> NaN (kept as anomaly evidence)
  8 Tukey-IQR suspected outlier (kept, not removed)
  9 left-censored (<= detection limit)
"""
from __future__ import annotations
import numpy as np
import pandas as pd

from ..semantics import PHYS_RANGE, DETECTION_LIMIT

FLAG = dict(ORIGINAL=0, SHORT=1, LONG=2, COSINE=3, SAMEDAY=4, TRANSITION=5,
            HOLD=6, RANGE=7, OUTLIER=8, CENSORED=9)


# ── min-level 1-min master clock ────────────────────────────────────────────
def align_min(df: pd.DataFrame, short_gap_min: int = 3) -> tuple:
    """Reindex to absolute 1-min grid; range-clip; short-gap interp; flag.

    Returns (df_aligned, flags) with flags in {0,1,2,7}.
    """
    full = pd.date_range(df.index.min(), df.index.max(), freq="1min")
    df_a = df.reindex(full).copy()
    df_a.index.name = "timestamp"

    flags = pd.DataFrame(FLAG["ORIGINAL"], index=df_a.index,
                         columns=df_a.columns, dtype=np.int8)

    # physical range violation -> NaN, flag 7 (mark not clean)
    for c in df_a.columns:
        if c in PHYS_RANGE:
            lo, hi = PHYS_RANGE[c]
            bad = (df_a[c] < lo) | (df_a[c] > hi)
            flags.loc[bad, c] = FLAG["RANGE"]
            df_a.loc[bad, c] = np.nan

    # missing (reindex gaps): mark long initially
    missing = df_a.isna() & (flags == FLAG["ORIGINAL"])
    flags[missing] = FLAG["LONG"]

    # short-gap (<= short_gap_min) linear interp.
    # On the regular 1-min grid, linear == time-based but is far faster.
    df_filled = df_a.interpolate(method="linear", limit=short_gap_min,
                                 limit_area="inside")
    short = df_a.isna() & df_filled.notna()
    flags[short] = FLAG["SHORT"]
    # remaining NaN stay long
    still_na = df_filled.isna() & (flags == FLAG["SHORT"])
    flags[still_na] = FLAG["LONG"]

    return df_filled, flags


# ── hourly native preprocessing + cosine fill + same-day rule ───────────────
def preprocess_hourly(df: pd.DataFrame, cosine_window_h: int = 24) -> tuple:
    """Native-1h preprocessing: range-clip, cosine-fill sparse gaps, same-day
    multi-gap day exclusion, left-censoring flags.

    Returns (df_filled_native, flags_native) on the native hourly index.
    """
    full = pd.date_range(df.index.min(), df.index.max(), freq="1h")
    df_a = df.reindex(full).copy()
    df_a.index.name = "timestamp"
    flags = pd.DataFrame(FLAG["ORIGINAL"], index=df_a.index,
                         columns=df_a.columns, dtype=np.int8)

    # physical range -> NaN
    for c in df_a.columns:
        if c in PHYS_RANGE:
            lo, hi = PHYS_RANGE[c]
            bad = (df_a[c] < lo) | (df_a[c] > hi)
            flags.loc[bad, c] = FLAG["RANGE"]
            df_a.loc[bad, c] = np.nan

    # left-censoring flag (<= detection limit), value kept
    for c in df_a.columns:
        if c in DETECTION_LIMIT:
            cen = df_a[c] <= DETECTION_LIMIT[c]
            flags.loc[cen & (flags[c] == FLAG["ORIGINAL"]), c] = FLAG["CENSORED"]

    df_filled = df_a.copy()
    for c in df_a.columns:
        s = df_a[c]
        isna = s.isna()
        if not isna.any():
            continue
        # same-day rule: a day with >=2 missing hours -> exclude from fit (flag 4)
        day = s.index.normalize()
        miss_per_day = isna.groupby(day).sum()
        bad_days = set(miss_per_day[miss_per_day >= 2].index)
        sameday_mask = pd.Series([d in bad_days for d in day], index=s.index) & isna
        # cosine fill for the remaining (isolated, <=1/day) sparse gaps
        cosine_mask = isna & ~sameday_mask
        filled = _cosine_fill(s, cosine_mask, window_h=cosine_window_h)
        df_filled[c] = filled
        flags.loc[cosine_mask & filled.notna(), c] = FLAG["COSINE"]
        # same-day-multi gaps stay NaN, flagged 4
        flags.loc[sameday_mask, c] = FLAG["SAMEDAY"]
        # any leftover NaN -> long
        leftover = filled.isna() & (flags[c] == FLAG["ORIGINAL"])
        flags.loc[leftover, c] = FLAG["LONG"]

    return df_filled, flags


def _cosine_fill(s: pd.Series, mask: pd.Series, window_h: int = 24) -> pd.Series:
    """Fill masked points by a local cosine (24h harmonic) least-squares fit
    over a +/- window_h neighbourhood (Zhao 2020 / Attention 2025)."""
    out = s.copy()
    x = s.values.astype(float)
    n = len(x)
    idx_missing = np.where(mask.values)[0]
    for i in idx_missing:
        lo = max(0, i - window_h)
        hi = min(n, i + window_h + 1)
        t = np.arange(lo, hi)
        y = x[lo:hi]
        good = ~np.isnan(y)
        if good.sum() < 5:
            continue
        # design: const + cos/sin(24h) ; hourly so period=24
        w = 2 * np.pi / 24.0
        Z = np.column_stack([np.ones(len(t)), np.cos(w * t), np.sin(w * t)])
        beta, *_ = np.linalg.lstsq(Z[good], y[good], rcond=None)
        out.iloc[i] = float(np.array([1.0, np.cos(w * i), np.sin(w * i)]) @ beta)
    return out


def mark_transition_zones(flags: pd.DataFrame, transition_h: int = 24,
                          freq_min: int = 1) -> pd.DataFrame:
    """Mark 24 h either side of any long gap as transition (flag 5, down-weight).
    Only overwrites ORIGINAL cells (keeps stronger flags).

    Dilation uses an O(n) 1-D maximum filter (not convolution) so it stays fast
    on 360k-row min-level frames with a ~2881-wide window."""
    from scipy.ndimage import maximum_filter1d
    span = int(transition_h * 60 / freq_min)
    out = flags.copy()
    for c in flags.columns:
        islong = (flags[c] == FLAG["LONG"]).values
        if not islong.any():
            continue
        dil = maximum_filter1d(islong.astype(np.int8), size=2 * span + 1) > 0
        trans = dil & ~islong & (out[c].values == FLAG["ORIGINAL"])
        out.loc[trans, c] = FLAG["TRANSITION"]
    return out


# ── Tukey IQR outlier marking (mark, don't remove — plan §2.4) ──────────────
def mark_outliers_iqr(df: pd.DataFrame, flags: pd.DataFrame,
                      k: float = 1.5) -> pd.DataFrame:
    """Flag statistical outliers via Tukey IQR fences (k=1.5). Suspected points
    are flagged 8 but KEPT — they are §1.2 scoring evidence (氨氮 2023)."""
    out = flags.copy()
    for c in df.columns:
        v = df[c].dropna()
        if len(v) < 100:
            continue
        q1, q3 = v.quantile(0.25), v.quantile(0.75)
        iqr = q3 - q1
        if iqr <= 0:
            continue
        lo, hi = q1 - k * iqr, q3 + k * iqr
        susp = ((df[c] < lo) | (df[c] > hi)) & (out[c] == FLAG["ORIGINAL"])
        out.loc[susp, c] = FLAG["OUTLIER"]
    return out


# ── multi-rate alignment: hold hourly onto 1-min clock ──────────────────────
def hold_to_min(df_hourly: pd.DataFrame, min_index: pd.DatetimeIndex) -> tuple:
    """Forward-step-hold a native-hourly frame onto the 1-min master clock.

    Returns (df_held, hold_flags) where hold_flags == 6 wherever a value is a
    held (carried-forward) low-frequency sample rather than a native one.
    """
    df_held = df_hourly.reindex(min_index, method="ffill")
    # a row is "native" only at exact hourly stamps that exist in source
    native_stamps = df_hourly.index
    is_native = min_index.isin(native_stamps)
    hold_flags = pd.DataFrame(FLAG["HOLD"], index=min_index,
                              columns=df_hourly.columns, dtype=np.int8)
    hold_flags.loc[is_native, :] = FLAG["ORIGINAL"]
    # where held value is NaN keep as long
    hold_flags[df_held.isna()] = FLAG["LONG"]
    return df_held, hold_flags
