"""src/whiten/diagnostics.py — stationarity & white-noise diagnostics (plan §5.3).

  * Ljung-Box  : innovation has no residual autocorrelation (p > alpha pass)
  * ADF        : reject unit root  (p < alpha)
  * KPSS       : do not reject stationarity (p > alpha)
  * ARCH-LM    : conditional heteroskedasticity (p < alpha -> enable GARCH)
"""
from __future__ import annotations
import warnings
import numpy as np
import pandas as pd

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from statsmodels.stats.diagnostic import acorr_ljungbox, het_arch
    from statsmodels.tsa.stattools import adfuller, kpss


def _clean(x) -> np.ndarray:
    x = np.asarray(pd.Series(x).dropna().values, dtype=float)
    return x[np.isfinite(x)]


# Unit-root / stationarity tests don't need hundreds of thousands of points and
# adfuller(autolag) cost is ~O(n*maxlag^2); cap the input by even subsampling so
# the diagnostics stay fast on 360k-point min-level innovations.
_TEST_CAP = 20000


def _cap(x: np.ndarray, cap: int = _TEST_CAP) -> np.ndarray:
    n = len(x)
    if n <= cap:
        return x
    step = int(np.ceil(n / cap))
    return x[::step]


def ljung_box(x, lags: int = 60, alpha: float = 0.05, cap: bool = True) -> dict:
    x = _cap(_clean(x)) if cap else _clean(x)
    if len(x) < lags + 10:
        return dict(lb_stat=np.nan, lb_pvalue=np.nan, lb_pass=None, lags=lags)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        res = acorr_ljungbox(x, lags=[lags], return_df=True)
    p = float(res["lb_pvalue"].iloc[-1])
    return dict(lb_stat=round(float(res["lb_stat"].iloc[-1]), 3),
                lb_pvalue=round(p, 4), lb_pass=bool(p > alpha), lags=lags)


def adf_test(x, alpha: float = 0.05) -> dict:
    x = _cap(_clean(x))
    if len(x) < 50:
        return dict(adf_stat=np.nan, adf_pvalue=np.nan, adf_reject_unitroot=None)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            stat, p, *_ = adfuller(x, maxlag=24, autolag="AIC")
        except Exception:
            return dict(adf_stat=np.nan, adf_pvalue=np.nan, adf_reject_unitroot=None)
    return dict(adf_stat=round(float(stat), 3), adf_pvalue=round(float(p), 4),
                adf_reject_unitroot=bool(p < alpha))


def kpss_test(x, alpha: float = 0.05) -> dict:
    x = _cap(_clean(x))
    if len(x) < 50:
        return dict(kpss_stat=np.nan, kpss_pvalue=np.nan, kpss_stationary=None)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            stat, p, *_ = kpss(x, regression="c", nlags="auto")
        except Exception:
            return dict(kpss_stat=np.nan, kpss_pvalue=np.nan, kpss_stationary=None)
    return dict(kpss_stat=round(float(stat), 3), kpss_pvalue=round(float(p), 4),
                kpss_stationary=bool(p > alpha))


def arch_lm(x, lags: int = 12, alpha: float = 0.05) -> dict:
    x = _cap(_clean(x))
    if len(x) < lags + 20:
        return dict(arch_stat=np.nan, arch_pvalue=np.nan, arch_heterosked=None)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            stat, p, *_ = het_arch(x, nlags=lags)
        except Exception:
            return dict(arch_stat=np.nan, arch_pvalue=np.nan, arch_heterosked=None)
    return dict(arch_stat=round(float(stat), 3), arch_pvalue=round(float(p), 4),
                arch_heterosked=bool(p < alpha))


def full_diagnostics(x, lb_lags: int = 60, alpha_lb: float = 0.05,
                     alpha_adf: float = 0.05, alpha_kpss: float = 0.05,
                     alpha_arch: float = 0.05, arch_lags: int = 12) -> dict:
    out = {}
    out.update(ljung_box(x, lags=lb_lags, alpha=alpha_lb))
    out.update(adf_test(x, alpha=alpha_adf))
    out.update(kpss_test(x, alpha=alpha_kpss))
    out.update(arch_lm(x, lags=arch_lags, alpha=alpha_arch))
    return out


def windowed_lb_pass_rate(s: pd.Series, window_pts: int, lags: int = 60,
                          alpha: float = 0.05, max_windows: int = 400) -> dict:
    """Segment-wise Ljung-Box pass rate (plan §8 "LB pass rate").

    At very large n a single Ljung-Box test rejects on trivially small
    autocorrelation, so we split the series into `window_pts`-long blocks, test
    each, and report the fraction passing (p > alpha). This is the meaningful
    whitening-sufficiency metric for 360k-point min-level series.
    """
    v = s.dropna()
    n = len(v)
    if n < window_pts + lags:
        d = ljung_box(v.values, lags=min(lags, max(10, n // 4)), alpha=alpha)
        return dict(lb_pass_rate=1.0 if d["lb_pass"] else 0.0, n_windows=1,
                    lags=d["lags"])
    n_win = min(max_windows, n // window_pts)
    passes = 0
    for i in range(n_win):
        seg = v.values[i * window_pts:(i + 1) * window_pts]
        d = ljung_box(seg, lags=lags, alpha=alpha)
        if d["lb_pass"]:
            passes += 1
    return dict(lb_pass_rate=round(passes / n_win, 3), n_windows=n_win, lags=lags)


def acf1(x) -> float:
    """Lag-1 autocorrelation (substantive whitening evidence)."""
    a = acf(x, nlags=1)
    return round(float(a[1]), 4) if len(a) > 1 else np.nan


def mean_abs_acf(x, lo: int = 1, hi: int = 10) -> float:
    """Mean |ACF| over lags lo..hi (residual vs innovation decay)."""
    a = acf(x, nlags=hi)
    return round(float(np.mean(np.abs(a[lo:hi + 1]))), 4) if len(a) > hi else np.nan


def acf(x, nlags: int = 40) -> np.ndarray:
    """Sample ACF (lags 0..nlags) for plotting."""
    x = _clean(x)
    x = x - x.mean()
    n = len(x)
    if n < nlags + 2:
        return np.zeros(nlags + 1)
    var = np.dot(x, x)
    out = np.array([np.dot(x[:n - k], x[k:]) / var for k in range(nlags + 1)])
    return out


def acf_conf(n: int) -> float:
    """95% white-noise confidence band ~ 1.96/sqrt(n)."""
    return 1.96 / np.sqrt(max(n, 1))


def robust_z(x: pd.Series, mad_c: float = 1.4826) -> pd.Series:
    """接受门失败时的兜底"白化"(plan §6.4 优雅降级).

    用 MAD 标准化残差。它不是真白化(仍含自相关),但有界、稳健,确保不合格模型
    永不被静默发布——失败通道得到一个降级但可用的分数,而非伪精确的创新。
    """
    v = x.astype(float)
    med = v.median()
    mad = mad_c * (v - med).abs().median() + 1e-9
    return (v - med) / mad
