"""src/whiten/online_whitener.py — fast-track whitening (plan §6.4 (一)).

Frozen-coefficient filter. Per step it computes the standardised innovation
    eta_t   = (eps_t - mu) - sum phi_i (eps_{t-i}-mu) - sum theta_j eta_{t-j}
    sigma2_t = omega + alpha * eta_{t-1}^2 + beta * sigma2_{t-1}      (GARCH)
    z_t     = eta_t / sqrt(sigma2_t)
complexity O(p+q) per channel per step — milliseconds, runs every minute.

Crucially the coefficients are FROZEN (no online RLS): self-adaptation would
"track" and erase slow drift, but drift is exactly the D1 fault to be scored
(plan §6.4). Coefficients change only when the slow track publishes a new
version, triggering an atomic hot-swap + warm-state load.

A vectorised batch helper `whiten_series` applies the same filter to a full
series via scipy.signal.lfilter (identical maths, C-speed) for offline runs.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from scipy.signal import lfilter

from .param_store import ParamStore, WhitenModel


class OnlineWhitener:
    """Streaming O(p+q) whitener for one channel."""

    def __init__(self, ch: str, store: ParamStore):
        self.ch = ch
        self.store = store
        self._ver = None
        self._eps = np.zeros(0)     # de-meaned eps history, newest first
        self._eta = np.zeros(0)     # innovation history, newest first
        self._sig2 = 1.0
        self._s2 = np.zeros(0)      # past conditional variances, newest first
        self._mu = 0.0
        self._m: WhitenModel | None = None

    def _hot_swap(self, m: WhitenModel) -> None:
        self._m = m
        self._ver = m.version
        self._mu = m.intercept
        ws = m.warmup_state or {}
        self._eps = np.array(ws.get("eps", []), dtype=float)
        self._eta = np.array(ws.get("eta", []), dtype=float)
        self._sig2 = float(ws.get("sigma2", 1.0)) or 1.0
        self._s2 = np.array(ws.get("sig2_hist", []), dtype=float)

    def step(self, eps_t: float) -> float:
        m = self.store.latest(self.ch)
        if m is None:
            return np.nan
        if m.version != self._ver:
            self._hot_swap(m)
        if not np.isfinite(eps_t):
            return np.nan
        y = eps_t - self._mu
        p, q = m.p, m.q
        ar_term = float(np.dot(m.ar, self._eps[:p])) if p and len(self._eps) >= p else 0.0
        ma_term = float(np.dot(m.ma, self._eta[:q])) if q and len(self._eta) >= q else 0.0
        eta = y - ar_term - ma_term
        if m.garch:
            g = m.garch
            a = np.atleast_1d(np.asarray(g.get("alpha", 0.0), float))   # eta 滞后系数
            b = np.atleast_1d(np.asarray(g.get("beta", 0.0), float))    # sig2 滞后系数
            e2 = (self._eta[:len(a)] ** 2) if len(self._eta) else np.zeros(0)
            e2 = np.pad(e2, (0, len(a) - len(e2)))
            s2 = self._s2[:len(b)] if len(self._s2) else np.zeros(0)
            s2 = np.pad(s2, (0, len(b) - len(s2)))
            sig2 = max(float(g["omega"]) + float(a @ e2) + float(b @ s2), 1e-12)
        else:
            sig2 = self._sig2
        # push histories (newest first)
        if p:
            self._eps = np.r_[y, self._eps][:p]
        na = len(np.atleast_1d(np.asarray(m.garch.get("alpha", 0.0), float))) if m.garch else 0
        keep_eta = max(q, na)
        if keep_eta:
            self._eta = np.r_[eta, self._eta][:keep_eta]
        if m.garch:
            nb = len(np.atleast_1d(np.asarray(m.garch.get("beta", 0.0), float)))
            self._s2 = np.r_[sig2, self._s2][:max(nb, 1)]
        self._sig2 = sig2
        return eta / np.sqrt(sig2)


def whiten_series(eps: pd.Series, model: WhitenModel) -> dict:
    """Batch-apply the frozen ARMA(+GARCH) filter to a whole series.

    eta = lfilter([1,-phi_1,...,-phi_p], [1,theta_1,...,theta_q], y)
    (identical recursion to OnlineWhitener.step). GARCH sigma2 is then a simple
    forward recursion. NaNs are bridged (filter resets are handled by the
    pipeline at long gaps).
    """
    y = (eps.values.astype(float) - model.intercept)
    nan_mask = ~np.isfinite(y)
    y_filled = np.where(nan_mask, 0.0, y)

    ar_poly = np.r_[1.0, -model.ar] if model.p > 0 else np.array([1.0])
    ma_poly = np.r_[1.0, model.ma] if model.q > 0 else np.array([1.0])
    eta = lfilter(ar_poly, ma_poly, y_filled)
    eta[nan_mask] = np.nan

    if model.garch:
        g = model.garch
        omega = float(g["omega"])
        alpha = np.atleast_1d(np.asarray(g.get("alpha", 0.0), dtype=float))  # ARCH lags
        beta = np.atleast_1d(np.asarray(g.get("beta", 0.0), dtype=float))    # GARCH lags
        na, nb = len(alpha), len(beta)
        e2 = np.where(np.isfinite(eta), eta, 0.0) ** 2
        sig2 = np.empty_like(eta)
        s0 = float(model.warmup_state.get("sigma2", np.nanvar(eta)) or 1.0)
        e2_hist = np.zeros(max(na, 1))          # newest first: e2_hist[k] = e2[i-1-k]
        s2_hist = np.full(max(nb, 1), s0)       # newest first: s2_hist[k] = sig2[i-1-k]
        for i in range(len(eta)):
            v = omega + (float(alpha @ e2_hist[:na]) if na else 0.0) \
                      + (float(beta @ s2_hist[:nb]) if nb else 0.0)
            v = max(v, 1e-12)
            sig2[i] = v
            if na:
                e2_hist = np.r_[e2[i], e2_hist[:na - 1]]
            if nb:
                s2_hist = np.r_[v, s2_hist[:nb - 1]]
        z = eta / np.sqrt(sig2)
    else:
        s2 = float(np.nanvar(eta)) or 1.0
        sig2 = np.full_like(eta, s2)
        z = eta / np.sqrt(s2)
    z[nan_mask] = np.nan
    return dict(innovation=pd.Series(eta, index=eps.index, name=eps.name),
                std_innovation=pd.Series(z, index=eps.index, name=eps.name),
                sigma2=pd.Series(sig2, index=eps.index, name=eps.name))
