"""src/baseline/deperiodise.py
Per工程目录终稿: "去周期化 — harmonic / STL 分解后取残差,而非简单24h rolling mean".

We implement two methods:
    1. harmonic_decomposition (default): least-squares fit of daily
       (T=1440 min) and weekly (T=10080 min) Fourier components, then return
       residual = signal − fitted seasonal − slowly-varying baseline.
    2. stl_decomposition: SciPy-only STL approximation (LOESS-style) using
       repeated rolling-median + smoothing.

Both return: residual_min, baseline_min (low-frequency mean), seasonal_min.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from typing import Tuple


def harmonic_design_matrix(n: int, periods_min: list, n_harmonics: int = 3) -> np.ndarray:
    """Build a sin/cos design matrix for given seasonal periods (in minutes)
    plus n_harmonics multiples of each.  Plus a constant column."""
    t = np.arange(n)
    cols = [np.ones(n)]
    for T in periods_min:
        for h in range(1, n_harmonics + 1):
            w = 2 * np.pi * h / T
            cols.append(np.sin(w * t))
            cols.append(np.cos(w * t))
    return np.column_stack(cols)


def harmonic_decomposition(
    s: pd.Series,
    daily_period_min: int = 1440,
    weekly_period_min: int = 10080,
    n_harmonics: int = 3,
    baseline_window: str = "168h",
    fit_first_days: int = 30,
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """Harmonic decomposition.

    1. Fit Fourier seasonal components on the FIRST fit_first_days of valid data
       (so seasonal component represents the "clean" daily/weekly cycle without
       being polluted by later anomalies).
    2. Subtract the seasonal from the full series.
    3. Apply rolling-mean smoothing to the residual to extract the slowly
       varying baseline.
    4. Final residual = signal − seasonal − baseline.

    Returns (residual_min, baseline_min, seasonal_min) all aligned to s.index.
    """
    n = len(s)
    x = s.values.astype(float)
    valid = ~np.isnan(x)

    # Fit on early-window only
    fit_n = min(fit_first_days * 1440, n)
    fit_mask = np.zeros(n, dtype=bool); fit_mask[:fit_n] = True
    fit_idx = fit_mask & valid
    if fit_idx.sum() < 1440:   # < 1 day of fit data → fall back to rolling mean
        baseline = pd.Series(x, index=s.index).rolling(baseline_window,
                                                         min_periods=60).mean()
        seasonal = pd.Series(0.0, index=s.index)
        residual = pd.Series(x, index=s.index) - baseline
        return residual.rename(f"{s.name}_resid"), baseline.rename(f"{s.name}_base"), \
               seasonal.rename(f"{s.name}_seas")

    Z = harmonic_design_matrix(n, [daily_period_min, weekly_period_min],
                                n_harmonics=n_harmonics)
    # Solve least-squares on fit window
    Zf = Z[fit_idx]; xf = x[fit_idx]
    beta, *_ = np.linalg.lstsq(Zf, xf, rcond=None)

    # Seasonal part = sin/cos columns × their coefficients (i.e. exclude intercept)
    seasonal_full = Z[:, 1:] @ beta[1:]      # length n
    intercept = beta[0]

    # Subtract seasonal; then extract slowly-varying baseline via rolling mean
    deseasonalised = x - seasonal_full

    base_series = pd.Series(deseasonalised, index=s.index).rolling(
        baseline_window, min_periods=60).mean()
    residual = pd.Series(x, index=s.index) - pd.Series(seasonal_full + intercept, index=s.index) \
                - (base_series - intercept)

    return (residual.rename(f"{s.name}_resid"),
            base_series.rename(f"{s.name}_base"),
            pd.Series(seasonal_full, index=s.index, name=f"{s.name}_seas"))


def harmonic_decomposition_dataframe(
    df: pd.DataFrame,
    **kwargs,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Apply harmonic_decomposition column-by-column."""
    residuals = {}
    baselines = {}
    seasonals = {}
    for c in df.columns:
        r, b, s = harmonic_decomposition(df[c], **kwargs)
        residuals[c] = r; baselines[c] = b; seasonals[c] = s
    return (pd.DataFrame(residuals, index=df.index).rename(columns=lambda x: x.replace("_resid", "")),
            pd.DataFrame(baselines, index=df.index).rename(columns=lambda x: x.replace("_base", "")),
            pd.DataFrame(seasonals, index=df.index).rename(columns=lambda x: x.replace("_seas", "")))


# ──────────────────────────────────────────────────────────────────────────
# STL alternative (statsmodels-free LOESS approximation)
# ──────────────────────────────────────────────────────────────────────────
def stl_decomposition(
    s: pd.Series,
    period_min: int = 1440,
    seasonal_smooth: int = 7,
    trend_smooth_h: int = 168,
    n_iter: int = 2,
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """Iterative STL approximation: subseries + seasonal smoothing + trend
    smoothing, repeated n_iter times.

    Period_min must divide len(s) reasonably; we tile the seasonal pattern.
    """
    n = len(s); x = s.values.astype(float)
    valid_mask = ~np.isnan(x)

    seasonal = np.zeros(n)
    trend = pd.Series(x, index=s.index).rolling(f"{trend_smooth_h}h",
                                                  min_periods=60).mean().values

    for _ in range(n_iter):
        detrended = x - trend
        # Seasonal subseries: bin by index modulo period
        bin_id = np.arange(n) % period_min
        season_means = pd.Series(detrended).groupby(bin_id).transform("mean")
        # Smooth seasonal with rolling median (Hampel-style)
        season_arr = season_means.values
        season_arr_smooth = pd.Series(season_arr).rolling(seasonal_smooth,
                                                          center=True,
                                                          min_periods=1).median().values
        seasonal = season_arr_smooth - np.nanmean(season_arr_smooth)
        # Re-fit trend on (signal − seasonal)
        deseasoned = x - seasonal
        trend = pd.Series(deseasoned, index=s.index).rolling(f"{trend_smooth_h}h",
                                                              min_periods=60).mean().values

    residual = x - trend - seasonal
    return (pd.Series(residual, index=s.index, name=f"{s.name}_resid"),
            pd.Series(trend,    index=s.index, name=f"{s.name}_base"),
            pd.Series(seasonal, index=s.index, name=f"{s.name}_seas"))
