"""src/baseline/harmonic_order.py — adaptive harmonic order selection (plan §3.3).

Upgrades the D1 fixed-3-harmonic scheme to a forward-nested selection:
  1. candidate periods per group (configs/deperiodise.yaml)
  2. Nyquist cap  J_max = floor(P / (2 dt))   (dt in native units)
  3. forward nesting from J=order_min: each added harmonic accepted only if the
     nested-F test is significant (p < alpha)
  4. AIC + BIC arbitration; on disagreement keep BIC (penalises complexity)
  5. independent selection per channel; result -> harmonic order table

Operates on the CAUSAL fit window (first `causal_fit_first_days`) to avoid
future-information leakage (plan §3.5).
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from scipy import stats


def harmonic_design_matrix(t: np.ndarray, periods: list, order: int) -> np.ndarray:
    """Const + sin/cos of `order` harmonics for each period (native units)."""
    cols = [np.ones(len(t))]
    for P in periods:
        for h in range(1, order + 1):
            w = 2 * np.pi * h / P
            cols.append(np.sin(w * t))
            cols.append(np.cos(w * t))
    return np.column_stack(cols) if len(cols) > 1 else cols[0][:, None]


def _ic(rss: float, n: int, k: int) -> tuple:
    """Gaussian AIC/BIC from residual sum of squares."""
    if rss <= 0 or n <= k:
        return np.inf, np.inf
    ll = -0.5 * n * (np.log(2 * np.pi * rss / n) + 1)
    aic = -2 * ll + 2 * k
    bic = -2 * ll + k * np.log(n)
    return aic, bic


def select_order(s: pd.Series, periods: list, dt_native: float,
                 order_min: int, order_max: int, alpha: float = 0.05) -> dict:
    """Forward-nested F + AIC/BIC selection for one channel.

    `dt_native` is the native sampling step in the SAME units as `periods`
    (min-level: minutes; hourly: hours). Returns a record dict.
    """
    x = s.values.astype(float)
    valid = ~np.isnan(x)
    t = np.arange(len(x), dtype=float)
    tv, xv = t[valid], x[valid]
    n = len(xv)

    # Nyquist cap across candidate periods
    j_nyq = int(min(np.floor(P / (2 * dt_native)) for P in periods)) if periods else 0
    j_cap = max(order_min, min(order_max, j_nyq if j_nyq > 0 else order_max))

    if n < 50 or not periods:
        return dict(channel=s.name, selected_order=order_min, nyquist_cap=j_nyq,
                    criterion="insufficient", periods=periods, aic=np.nan,
                    bic=np.nan, f_pvalues=[])

    prev_rss, prev_k = None, None
    f_pvals = []
    aic_path, bic_path = [], []
    orders = list(range(order_min, j_cap + 1))
    f_driven = order_min          # largest J whose every increment was significant
    f_chain_open = True           # becomes False at the first non-significant step

    for J in orders:
        if J == 0:
            Z = np.ones((n, 1))
        else:
            Z = harmonic_design_matrix(tv, periods, J)
        beta, *_ = np.linalg.lstsq(Z, xv, rcond=None)
        resid = xv - Z @ beta
        rss = float(resid @ resid)
        k = Z.shape[1]
        aic, bic = _ic(rss, n, k)
        aic_path.append(aic); bic_path.append(bic)
        if prev_rss is not None and J > order_min:        # nested-F vs J-1
            df1, df2 = k - prev_k, n - k
            if df1 > 0 and df2 > 0 and rss > 0:
                F = ((prev_rss - rss) / df1) / (rss / df2)
                pval = float(stats.f.sf(F, df1, df2))
            else:
                pval = 1.0
            f_pvals.append(round(pval, 4))
            if f_chain_open and pval < alpha:
                f_driven = J
            elif pval >= alpha:
                f_chain_open = False                       # stop growing on F
        prev_rss, prev_k = rss, k

    aic_best = orders[int(np.argmin(aic_path))]
    bic_best = orders[int(np.argmin(bic_path))]
    ic_order = bic_best if bic_best != aic_best else aic_best   # tie -> BIC
    # conservative final: do not exceed either the F-chain or the IC optimum
    final = int(np.clip(min(f_driven, ic_order), order_min, j_cap))
    return dict(channel=s.name, selected_order=final, nyquist_cap=j_nyq,
                cap_used=j_cap, criterion="aic_bic_f", periods=periods,
                f_driven_order=f_driven, aic_best_order=aic_best,
                bic_best_order=bic_best, f_pvalues=f_pvals)
