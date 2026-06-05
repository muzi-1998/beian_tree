"""src/whiten/model_selection.py — per-channel, data-driven whitening model selection.

Unifies several model families into ONE combined AR-polynomial form so the
existing frozen-coefficient lfilter whitener (online + batch) applies every
family unchanged — only the AR polynomial gets longer:

    η_t = A(B) / θ(B) · (x_t − μ),     A(B) = φ(B) · ∇(B)

where ∇(B) is the differencing operator:
  * ARMA(p,q)            : ∇ = 1
  * ARIMA(p,d,q)         : ∇ = (1−B)^d        (d chosen by ADF+KPSS, not fixed)
  * SARIMA(p,d,q)(P,D,Q)s: ∇ = (1−B)^d (1−B^s)^D   (D from a seasonal-UR test)
  * ARFIMA(p,d_f,q)      : ∇ = truncated fractional diff (1−B)^{d_f}, |d_f|<0.5
  * local level          : ≡ ARIMA(0,1,1)   (subsumed)

Selection is data-driven (no per-variable hand-assignment):
  1. ADF+KPSS decide integer d∈{0,1}; a seasonal-UR test decides D∈{0,1}.
  2. an LRD test (GPH d̂ + R/S Hurst + log-log ACF slope) gates the ARFIMA
     candidate and supplies its fractional d̂.
  3. candidates are fit, then filtered by guards:
       φ stationary, θ invertible, variance ratio sane, and — for any
       *differenced* candidate — an OVER-DIFFERENCING guard (innovation
       acf(1) ≥ −τ, i.e. no negative-MA(1) signature).
  4. the differenced/fractional candidate is preferred over plain ARMA ONLY if
     it raises the windowed Ljung-Box pass-rate by a margin. Differencing turns
     a slow drift into a near-constant increment (masking drift faults), so this
     parsimony bias *is* the fault-separability constraint.
"""
from __future__ import annotations
import warnings

import numpy as np
import pandas as pd
from scipy.signal import lfilter

from .param_store import WhitenModel
from .diagnostics import (adf_test, kpss_test, arch_lm, acf, acf1,
                          windowed_lb_pass_rate, full_diagnostics)
from .offline_identify import _fit_garch

with warnings.catch_warnings():
    warnings.simplefilter("ignore")
    from statsmodels.tsa.arima.model import ARIMA

_ID_CAP = 5000


# ────────────────────────────────────────────────────────────────────────
# Long-range-dependence diagnostics (GPH / R-S / log-log ACF)
# ────────────────────────────────────────────────────────────────────────
def gph_d(x: np.ndarray, m: int | None = None) -> float:
    """Geweke–Porter-Hudak estimate of the fractional-integration order d."""
    x = np.asarray(x, float); x = x[np.isfinite(x)]
    n = len(x)
    if n < 64:
        return np.nan
    x = x - x.mean()
    per = (np.abs(np.fft.rfft(x)) ** 2) / (2 * np.pi * n)
    freqs = 2 * np.pi * np.arange(len(per)) / n
    if m is None:
        m = int(n ** 0.6)
    m = max(8, min(m, len(per) - 1))
    lam = freqs[1:m + 1]
    I = per[1:m + 1]
    good = I > 0
    if good.sum() < 8:
        return np.nan
    reg = np.log(4 * np.sin(lam[good] / 2) ** 2)
    y = np.log(I[good])
    # slope of y on (−reg); d̂ = slope
    X = np.column_stack([np.ones(good.sum()), -reg])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    return float(beta[1])


def rs_hurst(x: np.ndarray) -> float:
    """Rescaled-range (R/S) Hurst exponent."""
    x = np.asarray(x, float); x = x[np.isfinite(x)]
    n = len(x)
    if n < 128:
        return np.nan
    sizes = np.unique(np.floor(np.logspace(np.log10(16), np.log10(n // 2), 12)).astype(int))
    rs = []
    for w in sizes:
        if w < 8:
            continue
        k = n // w
        vals = []
        for i in range(k):
            seg = x[i * w:(i + 1) * w]
            z = seg - seg.mean()
            Z = np.cumsum(z)
            R = Z.max() - Z.min()
            S = seg.std()
            if S > 0:
                vals.append(R / S)
        if vals:
            rs.append((w, np.mean(vals)))
    if len(rs) < 4:
        return np.nan
    ws = np.log([r[0] for r in rs]); ys = np.log([r[1] for r in rs])
    H = np.polyfit(ws, ys, 1)[0]
    return float(H)


def loglog_acf_slope(x: np.ndarray, kmax: int = 50) -> float:
    """Slope of log|ACF(k)| vs log k (≈ 2d−1 for long memory; ≈ −∞/steep for short)."""
    a = acf(x, nlags=kmax)
    if len(a) <= kmax:
        return np.nan
    ks = np.arange(1, kmax + 1)
    av = np.abs(a[1:kmax + 1])
    good = av > 1e-4
    if good.sum() < 6:
        return np.nan
    return float(np.polyfit(np.log(ks[good]), np.log(av[good]), 1)[0])


def lrd_flags(x: np.ndarray, cfg: dict) -> dict:
    d = gph_d(x); H = rs_hurst(x); sl = loglog_acf_slope(x)
    d_lo = cfg.get("lrd_d_min", 0.10)
    is_lrd = (np.isfinite(d) and d_lo < d < 0.5) and \
             (np.isfinite(H) and H > cfg.get("lrd_hurst_min", 0.60))
    return dict(d_gph=round(float(d), 3) if np.isfinite(d) else np.nan,
                hurst_rs=round(float(H), 3) if np.isfinite(H) else np.nan,
                acf_loglog_slope=round(float(sl), 3) if np.isfinite(sl) else np.nan,
                is_lrd=bool(is_lrd))


# ────────────────────────────────────────────────────────────────────────
# differencing decisions + polynomials
# ────────────────────────────────────────────────────────────────────────
def choose_d(x: np.ndarray, alpha: float = 0.05) -> int:
    """Integer differencing order d∈{0,1} via ADF+KPSS (conservative joint rule)."""
    ad = adf_test(x, alpha=alpha); kp = kpss_test(x, alpha=alpha)
    adf_unitroot = (ad.get("adf_reject_unitroot") is False)   # ADF fails to reject UR
    kpss_nonstat = (kp.get("kpss_stationary") is False)       # KPSS rejects stationarity
    return 1 if (adf_unitroot and kpss_nonstat) else 0


def choose_D(x: np.ndarray, s: int, thresh: float = 0.3) -> int:
    """Seasonal differencing D∈{0,1}: fire only if a strong, persistent seasonal
    autocorrelation remains AND seasonal differencing reduces variance."""
    a = acf(x, nlags=s + 1)
    if len(a) <= s:
        return 0
    seas_acf = abs(a[s])
    if seas_acf < thresh:
        return 0
    xv = np.asarray(x, float); xv = xv[np.isfinite(xv)]
    if len(xv) < 3 * s:
        return 0
    sd = xv[s:] - xv[:-s]
    return 1 if np.var(sd) < np.var(xv) else 0


def _intdiff_poly(d: int, seasonal: list | None = None) -> np.ndarray:
    poly = np.array([1.0])
    for _ in range(d):
        poly = np.convolve(poly, np.array([1.0, -1.0]))
    for (s, D) in (seasonal or []):
        sp = np.zeros(s + 1); sp[0] = 1.0; sp[s] = -1.0
        for _ in range(D):
            poly = np.convolve(poly, sp)
    return poly


def fracdiff_weights(d: float, K: int = 64) -> np.ndarray:
    """Truncated fractional-differencing FIR weights for (1−B)^d, length K+1."""
    w = np.zeros(K + 1); w[0] = 1.0
    for k in range(1, K + 1):
        w[k] = -w[k - 1] * (d - k + 1) / k
    return w


# ────────────────────────────────────────────────────────────────────────
# fitting one candidate (ARMA on the differenced residual) → combined model
# ────────────────────────────────────────────────────────────────────────
def _roots_inside(poly: np.ndarray) -> bool:
    if poly is None or len(poly) <= 1:
        return True
    r = np.roots(poly)
    return bool(len(r) == 0 or np.all(np.abs(r) < 1.0 - 1e-8))


def _fit_arma_n(w: np.ndarray, p: int, q: int):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            return ARIMA(w, order=(p, 0, q), trend="n",
                         enforce_stationarity=True, enforce_invertibility=True
                         ).fit(method="statespace",
                               method_kwargs={"maxiter": 50, "disp": 0})
        except Exception:
            return None


def _grid_arma_n(w: np.ndarray, grid: dict) -> tuple:
    best = None
    for p in grid["p"]:
        for q in grid["q"]:
            if p == 0 and q == 0:
                continue
            res = _fit_arma_n(w, p, q)
            if res is None or not np.isfinite(res.aic):
                continue
            key = (round(res.aic, 3), round(res.bic, 3))
            if best is None or key < (best[2], best[3]):
                best = (p, q, res.aic, res.bic, res)
    return best


def fit_candidate(resid: np.ndarray, diff_poly: np.ndarray, grid: dict,
                  use_garch: bool, win: int, lb_lags: int, family: str,
                  d_int: int = 0, D_int: int = 0, fd: float | None = None,
                  id_cap: int = _ID_CAP) -> dict | None:
    x = np.asarray(resid, float)
    deg = len(diff_poly) - 1                 # differencing-polynomial degree
    mu = float(np.nanmean(x)) if deg == 0 else 0.0
    xc = x - mu
    # differenced series for identification
    if deg > 0:
        w = lfilter(diff_poly, [1.0], np.where(np.isfinite(xc), xc, 0.0))
        w = w[deg:]
    else:
        w = xc
    w = w[np.isfinite(w)]
    if len(w) < 200:
        return None
    w_id = w[-id_cap:] if len(w) > id_cap else w
    best = _grid_arma_n(w_id, grid)
    if best is None:
        return None
    p, q, aic, bic, res = best
    phi = np.asarray(res.arparams, float) if p > 0 else np.zeros(0)
    tht = np.asarray(res.maparams, float) if q > 0 else np.zeros(0)
    phi_poly = np.r_[1.0, -phi] if p > 0 else np.array([1.0])
    ma_poly = np.r_[1.0, tht] if q > 0 else np.array([1.0])
    A_poly = np.convolve(phi_poly, diff_poly)          # combined AR side
    ar = -A_poly[1:]

    y = np.where(np.isfinite(xc), xc, 0.0)
    eta = lfilter(A_poly, ma_poly, y)
    eta[~np.isfinite(xc)] = np.nan
    eta_fin = eta[np.isfinite(eta)]
    if len(eta_fin) < win:
        return None

    rv = xc[np.isfinite(xc)]
    var_ratio = float(np.var(eta_fin) / (np.var(rv) + 1e-12))
    a1 = acf1(eta_fin)
    wlb = windowed_lb_pass_rate(pd.Series(eta), win, lags=lb_lags)["lb_pass_rate"]

    garch = None
    if use_garch:
        a = arch_lm(eta_fin, lags=12)
        if a.get("arch_heterosked"):
            garch = _fit_garch(eta_fin)

    return dict(family=family, p_arma=p, q=q, d=d_int, D=D_int, fd=fd,
                ar=ar, ma=tht, garch=garch, intercept=mu, innov=eta,
                phi_stationary=_roots_inside(phi_poly),
                ma_invertible=_roots_inside(ma_poly),
                var_ratio=round(var_ratio, 4), acf1_innov=a1,
                windowed_lb=wlb, aic=round(float(aic), 2), bic=round(float(bic), 2),
                order_total=p + q + d_int + D_int + (1 if fd else 0))


# ────────────────────────────────────────────────────────────────────────
# the selector
# ────────────────────────────────────────────────────────────────────────
def _to_model(cand: dict, resid: np.ndarray, version: str, lb_lags: int,
              win: int, sel_record: dict) -> WhitenModel:
    ar = np.asarray(cand["ar"], float)
    ma = np.asarray(cand["ma"], float)
    eta = cand["innov"]; eta_fin = eta[np.isfinite(eta)]
    p, q = len(ar), len(ma)
    na = len(cand["garch"].get("alpha", [])) if cand["garch"] else 0
    nb = len(cand["garch"].get("beta", [])) if cand["garch"] else 0
    keep_eta = max(q, na)
    yc = (np.asarray(resid, float) - cand["intercept"])
    yc = yc[np.isfinite(yc)]
    eps_hist = list(yc[-p:][::-1]) if p > 0 else []
    eta_hist = list(eta_fin[-keep_eta:][::-1]) if keep_eta > 0 else []
    sigma2 = float(np.var(eta_fin)) if len(eta_fin) else 1.0
    ws = dict(eps=eps_hist, eta=eta_hist, sigma2=sigma2,
              sig2_hist=[sigma2] * max(nb, 1))
    diag = full_diagnostics(eta_fin, lb_lags=lb_lags)
    diag.update(dict(aic=cand["aic"], bic=cand["bic"],
                     p=p, q=q, has_garch=cand["garch"] is not None,
                     phi_stationary=cand["phi_stationary"],
                     ma_invertible=cand["ma_invertible"],
                     windowed_lb_passrate=cand["windowed_lb"],
                     var_ratio=cand["var_ratio"], acf1_innov=cand["acf1_innov"],
                     **sel_record))
    return WhitenModel(version=version, p=p, q=q, ar=ar, ma=ma,
                       intercept=cand["intercept"], garch=cand["garch"],
                       warmup_state=ws, diagnostics=diag)


def select_model(resid: pd.Series, cfg: dict, version: str, track: str,
                 lb_lags: int = 60) -> tuple:
    """Data-driven per-channel selection. Returns (WhitenModel|None, record)."""
    s = resid.dropna()
    rv = s.values.astype(float)
    if len(rv) < 300:
        return None, dict(family="none", reason="too_short")
    msc = cfg.get("model_selection", {})
    win = 1440 if track == "min" else 168
    full_grid = cfg["arma_grid"]["min" if track == "min" else "hour"]
    small_grid = msc.get("diff_grid", {"p": [0, 1, 2], "q": [0, 1, 2]})
    use_garch = cfg.get("use_garch", True)
    K = msc.get("fracdiff_truncation", 64)

    # ── decide candidate structures from tests (data-driven) ──────────────
    d = choose_d(rv, alpha=msc.get("unitroot_alpha", 0.05))
    D = choose_D(rv, 24, msc.get("seasonal_acf_thresh", 0.3)) if track == "hour" else 0
    lrd = lrd_flags(rv, msc) if msc.get("enable_arfima", True) else dict(is_lrd=False)

    specs = [("arma", _intdiff_poly(0), full_grid, 0, 0, None)]
    if msc.get("enable_arima", True) and d >= 1:
        specs.append(("arima", _intdiff_poly(1), small_grid, 1, 0, None))
    if msc.get("enable_sarima", True) and D >= 1:
        specs.append(("sarima", _intdiff_poly(d, [(24, 1)]), small_grid, d, 1, None))
    if msc.get("enable_arfima", True) and lrd.get("is_lrd"):
        fd = float(np.clip(lrd["d_gph"], 0.05, 0.49))
        specs.append(("arfima", fracdiff_weights(fd, K), small_grid, 0, 0, fd))

    cands = []
    for fam, dp, grid, d_int, D_int, fd in specs:
        c = fit_candidate(rv, dp, grid, use_garch, win, lb_lags, fam,
                          d_int=d_int, D_int=D_int, fd=fd)
        if c is not None:
            cands.append(c)
    if not cands:
        return None, dict(family="none", reason="no_fit", d=d, D=D, **lrd)

    # ── guards ────────────────────────────────────────────────────────────
    # a strongly NEGATIVE innovation acf(1) is the over-modelling / over-
    # differencing signature (negative MA(1)); reject it for ALL candidates so
    # neither a blanket d=1 nor an over-rich ARMA is selected.
    min_a1 = msc.get("min_acf1_innov", -0.30)
    max_vr = msc.get("max_var_ratio", 5.0)

    def _ok(c):
        if not (c["phi_stationary"] and c["ma_invertible"]):
            return False
        if c["var_ratio"] > max_vr or c["var_ratio"] <= 0:
            return False
        if c["acf1_innov"] is not None and c["acf1_innov"] < min_a1:
            return False                      # over-modelling / over-differencing
        return True

    valid = [c for c in cands if _ok(c)]
    arma = next((c for c in cands if c["family"] == "arma"), None)
    pool = valid if valid else ([arma] if arma else cands)

    # ── pick: ARMA unless a differenced model meaningfully improves wLB ────
    margin = msc.get("diff_improve_margin", 0.05)
    base = next((c for c in pool if c["family"] == "arma"), None)
    best = base
    for c in pool:
        if c["family"] == "arma":
            continue
        improves = base is None or c["windowed_lb"] >= base["windowed_lb"] + margin
        if not improves:
            continue
        if best is None or c["windowed_lb"] > best["windowed_lb"] or \
           (abs(c["windowed_lb"] - best["windowed_lb"]) < 1e-9 and
                c["order_total"] < best["order_total"]):
            best = c
    if best is None:
        best = min(pool, key=lambda c: c["bic"])

    rec = dict(family=best["family"], d=best["d"], D=best["D"],
               p_arma=best["p_arma"], q=best["q"], fd=best.get("fd"),
               unitroot_d=int(d), seasonal_ur=int(D),     # what the tests proposed
               lrd_d_gph=lrd.get("d_gph"), lrd_hurst=lrd.get("hurst_rs"),
               lrd_flag=bool(lrd.get("is_lrd")),
               windowed_lb=best["windowed_lb"], acf1_innov=best["acf1_innov"],
               n_candidates=len(cands))
    model = _to_model(best, rv, version, lb_lags, win, sel_record=dict(
        family=best["family"], d=best["d"], fd=best.get("fd")))
    return model, rec
