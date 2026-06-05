"""src/baseline/deperiodise.py — differentiated additive decomposition (plan §3).

Additive model  X_k(t) = m_k(t) + s_k(t) + e_k(t)
  * m_k(t) : long-term trend (causal LOESS / rolling mean on de-seasonalised)
  * s_k(t) : periodic part (adaptive-order Fourier harmonics, group-specific)
  * e_k(t) : de-trended de-seasonalised residual -> §1.1.3 whitening input

Differentiation (plan §3.2):
  aerobic_do  : high-order harmonics {24h,12h} + trend
  postanoxic  : near-zero floor -> (almost) no harmonics, censoring path
  anoxic_orp  : low-order {24h} + trend/regime
  flow        : {24h,168h} driver
  influent    : {24h,168h} order<=4
  effluent    : STL trend/season dominant, harmonics 0-2, LEFT-CENSORED robust

Causality (plan §3.5): harmonic coefficients are fit on the first
`causal_fit_first_days` (reference period); the slowly varying baseline uses a
backward (causal) rolling mean. No future samples enter the fit.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

from .harmonic_order import harmonic_design_matrix, select_order


def _causal_trend(x: np.ndarray, index: pd.DatetimeIndex, bandwidth_h: int,
                  min_periods: int = 30) -> np.ndarray:
    """Causal (backward) rolling-mean trend at given bandwidth in hours.

    `min_periods` is adaptive: a fixed-TIME window must never demand more points
    than it can physically hold, else a short bandwidth on a coarse sampling rate
    (e.g. a 24h window on hourly data = 24 points < 30) yields an all-NaN trend.
    We cap min_periods at half the window's point count. For every real channel
    (min-level 24h≈1440 pts, hourly 168h=168 pts) the cap is >=30, so the floor
    stays exactly 30 and results are unchanged; only degenerate short windows
    relax it.
    """
    dt_h = pd.Series(index).diff().dt.total_seconds().median() / 3600.0
    if dt_h and not pd.isna(dt_h) and dt_h > 0:
        win_pts = bandwidth_h / dt_h
        mp = max(3, int(min(min_periods, 0.5 * win_pts)))
    else:
        mp = min_periods
    return (pd.Series(x, index=index)
            .rolling(f"{bandwidth_h}h", min_periods=mp).mean().values)


def _causal_stl_seasonal(resid: np.ndarray, period: int,
                         n_cycles: int = 14, min_cycles: int = 3) -> np.ndarray:
    """Causal STL-style seasonal: per-phase trailing mean over past cycles.

    Captures the NON-sinusoidal part of a periodic pattern (e.g. aeration
    on/off square-wave) that Fourier harmonics miss. For each phase position
    p = i mod period, the seasonal estimate is the mean of the same-phase values
    over the previous `n_cycles` cycles (shifted by 1 cycle => strictly causal).
    """
    n = len(resid)
    phase = np.arange(n) % period
    df = pd.DataFrame({"e": resid, "phase": phase})
    trailing = df.groupby("phase")["e"].transform(
        lambda v: v.shift(1).rolling(n_cycles, min_periods=min_cycles).mean())
    out = trailing.values.astype(float)
    out[~np.isfinite(out)] = 0.0
    return out


def decompose_channel(s: pd.Series, group_cfg: dict, dt_native: float,
                      causal_fit_first_days: int, order_alpha: float = 0.05,
                      censored_mask: pd.Series | None = None,
                      refit_block_days: int = 14) -> dict:
    """Decompose one channel given its group config. Returns dict with
    trend/seasonal/residual series + the selected-order record.

    Harmonic coefficients are re-estimated block-wise on a trailing causal
    window (plan §3.3 "按季节 regime 重拟合，系数随季节缓慢变化" + §3.5 block-wise
    update), so a slowly drifting daily amplitude/phase is tracked without using
    future samples. The harmonic ORDER is fixed once on the reference window.
    """
    name = s.name
    x = s.values.astype(float)
    n = len(x)
    index = s.index
    periods = group_cfg["candidate_periods"]
    order_min = group_cfg["harmonic_order_min"]
    order_max = group_cfg["harmonic_order_max"]
    bw_h = group_cfg["loess_trend_bandwidth_h"]

    # ── causal fit window (reference period) ───────────────────────────────
    step_per_day = int(round(24 * 60 / dt_native)) if dt_native < 60 else 24
    fit_n = min(causal_fit_first_days * step_per_day, n)
    fit_slice = slice(0, fit_n)
    s_fit = s.iloc[fit_slice]

    # ── adaptive harmonic order on the causal window ──────────────────────
    rec = select_order(s_fit, periods, dt_native, order_min, order_max,
                       alpha=order_alpha)
    order = rec["selected_order"]

    # ── block-wise causal harmonic coefficient re-fit ─────────────────────
    t = np.arange(n, dtype=float)
    intercept = np.nanmean(x[fit_slice]) if np.isfinite(np.nanmean(x[fit_slice])) else 0.0
    if order > 0:
        seasonal = np.zeros(n)

        def _fit(lo, hi):
            Z = harmonic_design_matrix(t[lo:hi], periods, order)
            xs = x[lo:hi]; good = ~np.isnan(xs)
            if good.sum() > Z.shape[1] + 5:
                b, *_ = np.linalg.lstsq(Z[good], xs[good], rcond=None)
                return b
            return None

        # reference block [0, fit_n): in-sample fit on the reference period
        beta_ref = _fit(0, fit_n)
        if beta_ref is None:
            beta_ref = np.zeros(1 + 2 * len(periods) * order)
        Zref = harmonic_design_matrix(t[0:fit_n], periods, order)
        seasonal[0:fit_n] = Zref[:, 1:] @ beta_ref[1:]
        intercept = beta_ref[0]

        # forward blocks: coefficients from the trailing `fit_n` window (causal)
        trail = fit_n
        block = max(1, int(refit_block_days * step_per_day))
        last_beta = beta_ref
        b = fit_n
        while b < n:
            end = min(b + block, n)
            beta = _fit(max(0, b - trail), b)        # strictly past data
            if beta is None:
                beta = last_beta
            last_beta = beta
            Zb = harmonic_design_matrix(t[b:end], periods, order)
            seasonal[b:end] = Zb[:, 1:] @ beta[1:]
            b = end
    else:
        seasonal = np.zeros(n)

    # ── causal trend on de-seasonalised series ────────────────────────────
    deseason = x - seasonal
    trend = _causal_trend(deseason, index, bw_h)
    e1 = x - seasonal - trend

    # ── STL seasonal refinement (non-sinusoidal daily shape) ──────────────
    # apply at the daily period when present (1440 min-level / 24 hourly);
    # captures the square-wave aeration pattern harmonics cannot.
    daily_period = 1440 if 1440 in periods else (24 if 24 in periods else None)
    if daily_period is not None and order >= 0 and group_cfg.get("stl_seasonal", True):
        stl_seas = _causal_stl_seasonal(e1, daily_period)
        seasonal = seasonal + stl_seas
        residual = e1 - stl_seas
    else:
        residual = e1

    # ── effluent left-censoring: do not let censored points distort residual
    if censored_mask is not None and censored_mask.any():
        # for censored (<= DL) points, residual is set to 0 contribution-safe
        # (Tobit-style: censored obs carry no positive residual evidence)
        cm = censored_mask.values
        residual = residual.copy()
        residual[cm] = np.nan      # excluded from whitening evidence, flagged 9

    return dict(
        channel=name,
        trend=pd.Series(trend, index=index, name=name),
        seasonal=pd.Series(seasonal, index=index, name=name),
        residual=pd.Series(residual, index=index, name=name),
        order_record=rec,
    )


def extra_stl_pass(residual: pd.Series, period: int, n_cycles: int = 14,
                   min_cycles: int = 3) -> pd.Series:
    """对已分解的残差再做一次因果 STL 精修(plan §3.4 互补建模).

    谐波 + 首次 STL 之后仍残留的非正弦周期(ORP/QR 的方波/事件型日周期),
    用同相位、仅取过去 n_cycles 个周期均值的方式再减一层。严格因果。
    """
    e = residual.values.astype(float)
    seas = _causal_stl_seasonal(e, period, n_cycles=n_cycles, min_cycles=min_cycles)
    return pd.Series(e - seas, index=residual.index, name=residual.name)


def detect_dominant_period(resid: pd.Series, dt_native: float = 1.0,
                           period_range=(20, 180), min_prominence: float = 5.0):
    """Detect a GENUINE LOCAL spectral peak (e.g. a sub-hourly aeration/blower
    limit cycle the 24h/12h harmonics miss) in `period_range` (native units).

    Uses Welch + scipy.find_peaks on log-power, so a monotone red-noise /
    near-unit-root roll-off — which has NO local peak — correctly returns None
    (rather than a spurious band-edge "period"). `min_prominence` is the linear
    peak/continuum ratio, converted to a log-prominence threshold. Returns
    {period, prominence} or None.
    """
    from scipy.signal import welch, find_peaks
    x = pd.Series(resid).interpolate(limit=6).dropna().values.astype(float)
    n = len(x)
    if n < 4096:
        return None
    nper = max(int(min(8 * period_range[1] / dt_native, n)), 1024)
    freq, P = welch(x, fs=1.0 / dt_native, nperseg=nper, detrend="linear")
    with np.errstate(divide="ignore"):
        per = np.where(freq > 0, 1.0 / freq, np.inf)
    logP = np.log(P + 1e-30)
    pk, props = find_peaks(logP, prominence=np.log(max(min_prominence, 1.01)))
    cand = [(int(round(per[p])), float(np.exp(props["prominences"][i])))
            for i, p in enumerate(pk)
            if period_range[0] <= per[p] <= period_range[1]]
    if not cand:
        return None
    period, prom = max(cand, key=lambda t: t[1])
    return dict(period=period, prominence=round(prom, 1))


def residual_spectrum_peak_ratio(resid: pd.Series, periods: list,
                                 dt_native: float, half_window: int = 60,
                                 peak_bins: int = 3) -> dict:
    """Sufficiency check (plan §8): LOCAL peak prominence at target periods.

    A real residual has a 1/f-type continuum, so comparing the target-period
    power to the global median is meaningless. We instead measure whether a
    PEAK sticks out above the LOCAL continuum: peak power in +/-`peak_bins`
    around the target frequency vs the median power of the surrounding bins
    (excluding the peak region). ratio < 2 => the period left no residual peak.
    """
    x = resid.dropna().values
    n = len(x)
    if n < 200:
        return {}
    x = x - x.mean()
    freqs = np.fft.rfftfreq(n, d=dt_native)          # cycles per native unit
    power = np.abs(np.fft.rfft(x)) ** 2
    out = {}
    for P in periods:
        f_target = 1.0 / P
        k = int(np.argmin(np.abs(freqs - f_target)))
        lo, hi = max(1, k - half_window), min(len(power), k + half_window + 1)
        peak = power[max(1, k - peak_bins):k + peak_bins + 1].max()
        # local continuum: neighbourhood excluding the peak region
        neigh = np.r_[power[lo:max(1, k - peak_bins)], power[k + peak_bins + 1:hi]]
        local_base = np.median(neigh) + 1e-15 if len(neigh) else np.median(power[1:]) + 1e-15
        out[f"P{P}"] = round(float(peak / local_base), 3)
    return out
