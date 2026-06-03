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


def _fit_garch(innov: np.ndarray, grid=((1, 1), (1, 2), (2, 1)),
               escalate: bool = True, egarch_fallback: bool = False,
               arch_lags: int = 12, alpha: float = 0.05):
    """在创新上拟合 GARCH,逐级升阶直到 ARCH-LM 不再显著(plan §4.4).

    依次尝试 grid 中各 (ARCH, GARCH) 阶;若标准化残差 ARCH-LM 仍显著且 escalate,
    升到下一更大阶;最后(可选)回退 EGARCH(1,1)。返回含条件方差递归参数的 dict
    (alpha/beta 为按滞后排列的列表,GARCH(1,1) 即长度 1),或 None。
    """
    try:
        from arch import arch_model
    except Exception:
        return None
    x = np.asarray(innov, dtype=float)
    x = x[np.isfinite(x)]
    if len(x) < 200:
        return None
    best = None
    for (gp, gq) in grid:                       # gp = ARCH lags, gq = GARCH lags
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                r = arch_model(x, mean="Zero", vol="GARCH", p=gp, q=gq,
                               rescale=False).fit(disp="off")
        except Exception:
            continue
        std = np.asarray(r.std_resid, dtype=float)
        het_p = arch_lm(std[np.isfinite(std)], lags=arch_lags).get("arch_pvalue", 1.0)
        if het_p is None or not np.isfinite(het_p):
            het_p = 1.0
        pr = r.params
        cand = dict(kind="garch", p=gp, q=gq,
                    omega=float(pr.get("omega", 0.0)),
                    alpha=[float(pr.get(f"alpha[{i}]", 0.0)) for i in range(1, gp + 1)],
                    beta=[float(pr.get(f"beta[{i}]", 0.0)) for i in range(1, gq + 1)],
                    arch_p_after=float(het_p))
        if best is None or het_p > best["arch_p_after"]:
            best = cand
        if het_p > alpha:                       # ARCH 已清除 -> 接受此阶
            return cand
        if not escalate:
            break
    if egarch_fallback:                          # 离线诊断用;在线递归暂不支持
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                r = arch_model(x, mean="Zero", vol="EGARCH", p=1, o=1, q=1,
                               rescale=False).fit(disp="off")
            pr = r.params
            return dict(kind="egarch", p=1, q=1,
                        omega=float(pr.get("omega", 0.0)),
                        alpha=[float(pr.get("alpha[1]", 0.0))],
                        beta=[float(pr.get("beta[1]", 0.0))],
                        gamma=float(pr.get("gamma[1]", 0.0)))
        except Exception:
            pass
    return best


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
    na = len(garch.get("alpha", [])) if garch else 0
    nb = len(garch.get("beta", [])) if garch else 0
    keep_eta = max(q, na)                                  # GARCH 需过去创新,即使 q=0
    eps_hist = list(yc[-p:][::-1]) if p > 0 else []        # newest first
    eta_hist = list(innov[-keep_eta:][::-1]) if keep_eta > 0 else []
    sigma2 = float(np.var(innov)) if len(innov) else 1.0
    warmup_state = dict(eps=eps_hist, eta=eta_hist, sigma2=sigma2,
                        sig2_hist=[sigma2] * max(nb, 1))

    diag = full_diagnostics(innov, lb_lags=lb_lags, arch_lags=arch_lags)
    diag.update(dict(p=p, q=q, aic=round(float(aic), 2), bic=round(float(bic), 2),
                     has_garch=garch is not None))

    return WhitenModel(version=version, p=p, q=q, ar=ar, ma=ma, intercept=mu,
                       garch=garch, warmup_state=warmup_state, diagnostics=diag)
