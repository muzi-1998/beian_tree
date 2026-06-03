"""src/whiten/offline_identify.py — slow-track ARMA/GARCH identification (plan §4, §6.4).

The "expensive statistical brain": given a de-trended de-seasonalised residual
(with fault samples removed), it
  1. grid-searches ARMA (p,q) by AIC, BIC as tie-break (plan §4.3),
  2. fits the chosen ARMA,
  3. if ARCH-LM is significant, fits a GARCH(1,1) on the innovations (plan §4.4),
  4. builds the warm-start internal state,
  5. packs an immutable `WhitenModel`.

Order ID runs on a capped window for tractability (ARMA order is robust to a
few thousand points); the fitted coefficients are then applied to the full
series by the fast-track filter.
"""
from __future__ import annotations
import warnings
import numpy as np
import pandas as pd

from .param_store import WhitenModel
from .diagnostics import arch_lm, full_diagnostics

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from statsmodels.tsa.arima.model import ARIMA

_ID_CAP = 5000          # max points used for order ID / MLE (speed)


def _fit_arima(y: np.ndarray, p: int, q: int):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            res = ARIMA(y, order=(p, 0, q), trend="c",
                        enforce_stationarity=True,
                        enforce_invertibility=True).fit(
                            method="statespace",
                            method_kwargs={"maxiter": 50, "disp": 0})
            return res
        except Exception:
            return None


def grid_search_arma(y: np.ndarray, grid: dict) -> tuple:
    """Return (best_p, best_q, aic, bic) by AIC; BIC breaks ties."""
    best = None
    for p in grid["p"]:
        for q in grid["q"]:
            if p == 0 and q == 0:
                continue
            res = _fit_arima(y, p, q)
            if res is None or not np.isfinite(res.aic):
                continue
            key = (round(res.aic, 3), round(res.bic, 3))
            if best is None or key < (best[2], best[3]):
                best = (p, q, res.aic, res.bic)
    if best is None:
        return 1, 0, np.nan, np.nan
    return best


def _fit_garch(innov: np.ndarray):
    """Fit GARCH(1,1) on innovations; return dict or None."""
    innov = innov[np.isfinite(innov)]
    if len(innov) < 200:
        return None
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            from arch import arch_model
            scale = np.std(innov)
            if scale <= 0:
                return None
            am = arch_model(innov / scale, mean="Zero", vol="GARCH", p=1, q=1,
                            rescale=False)
            r = am.fit(disp="off", show_warning=False)
            pr = r.params
            return dict(omega=float(pr["omega"]) * scale ** 2,
                        alpha=float(pr["alpha[1]"]),
                        beta=float(pr["beta[1]"]),
                        scale=float(scale))
        except Exception:
            return None


def identify(resid: pd.Series, fault_mask: pd.Series | None, grid: dict,
             use_garch: bool, version: str, lb_lags: int = 60,
             arch_lags: int = 12, id_cap: int = _ID_CAP) -> WhitenModel | None:
    """Identify a WhitenModel from a residual series (fault samples removed)."""
    s = resid.copy()
    if fault_mask is not None:
        s = s[~fault_mask.reindex(s.index, fill_value=False)]
    y = s.dropna().values.astype(float)
    if len(y) < 200:
        return None
    mu = float(np.mean(y))
    yc = y - mu
    # cap for identification
    y_id = yc[-id_cap:] if len(yc) > id_cap else yc

    p, q, aic, bic = grid_search_arma(y_id, grid)
    res = _fit_arima(y_id, p, q)
    if res is None:
        return None
    ar = np.asarray(res.arparams, dtype=float) if p > 0 else np.zeros(0)
    ma = np.asarray(res.maparams, dtype=float) if q > 0 else np.zeros(0)
    innov = np.asarray(res.resid, dtype=float)
    innov = innov[np.isfinite(innov)]

    garch = None
    if use_garch:
        a = arch_lm(innov, lags=arch_lags)
        if a.get("arch_heterosked"):
            garch = _fit_garch(innov)

    # warm-start internal state from the tail of the identification window
    eps_hist = list(yc[-p:][::-1]) if p > 0 else []        # newest first
    eta_hist = list(innov[-q:][::-1]) if q > 0 else []
    sigma2 = float(np.var(innov)) if len(innov) else 1.0
    warmup_state = dict(eps=eps_hist, eta=eta_hist, sigma2=sigma2)

    diag = full_diagnostics(innov, lb_lags=lb_lags, arch_lags=arch_lags)
    diag.update(dict(p=p, q=q, aic=round(float(aic), 2), bic=round(float(bic), 2),
                     has_garch=garch is not None))

    return WhitenModel(version=version, p=p, q=q, ar=ar, ma=ma, intercept=mu,
                       garch=garch, warmup_state=warmup_state, diagnostics=diag)
