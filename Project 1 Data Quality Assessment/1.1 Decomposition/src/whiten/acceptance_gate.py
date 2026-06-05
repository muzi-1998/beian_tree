"""src/whiten/acceptance_gate.py — pre-swap model validation (plan §6.4 (三)).

"Optimised" is not enough: before a new model is published it must pass
  1. stationarity & invertibility — AR/MA roots strictly outside the unit circle
  2. Ljung-Box on the model's own innovations (white)
  3. variance sanity — innovation variance not absurd vs residual variance
Otherwise the previous valid model is kept (Haimi 2016).
"""
from __future__ import annotations
import numpy as np


def _roots_inside_unit_circle(coeffs: np.ndarray, kind: str = "ar") -> bool:
    """Stationarity (AR) / invertibility (MA) via the characteristic polynomial.

    AR(p) is stationary iff the roots of  z^p - phi_1 z^(p-1) - ... - phi_p = 0
    lie strictly INSIDE the unit circle. In np.roots' decreasing-power
    convention this polynomial is [1, -phi_1, ..., -phi_p]; the (equivalent)
    MA polynomial is [1, theta_1, ..., theta_q]. Require all |root| < 1.
    """
    if coeffs is None or len(coeffs) == 0:
        return True
    if kind == "ar":
        poly = np.r_[1.0, -np.asarray(coeffs, dtype=float)]
    else:
        poly = np.r_[1.0, np.asarray(coeffs, dtype=float)]
    roots = np.roots(poly)
    if len(roots) == 0:
        return True
    return bool(np.all(np.abs(roots) < 1.0 - 1e-8))


def acceptance_gate(model, residual_var: float, innov, cfg: dict,
                    diag: dict | None = None) -> tuple:
    """Return (passed: bool, reasons: list[str]).

    Whiteness is judged by the WINDOWED Ljung-Box pass-rate when
    `acceptance.require_windowed_ljungbox` is set — at n~10^3-10^5 a single LB
    rejects on trivial autocorrelation, so the single-shot variant wrongly
    discarded perfectly serviceable models (plan §8). Stationarity/invertibility
    uses the selector's φ/θ flags when present, so the *intentional* unit root of
    a differenced (ARIMA/SARIMA/ARFIMA) model is not misread as non-stationary.
    """
    acc = cfg.get("acceptance", {})
    diag = diag if diag is not None else getattr(model, "diagnostics", {}) or {}
    reasons = []
    ok = True

    if acc.get("require_stationary_invertible", True):
        if ("phi_stationary" in diag) or ("ma_invertible" in diag):
            if diag.get("phi_stationary") is False:
                ok = False; reasons.append("AR not stationary")
            if diag.get("ma_invertible") is False:
                ok = False; reasons.append("MA not invertible")
        else:
            if not _roots_inside_unit_circle(model.ar, "ar"):
                ok = False; reasons.append("AR not stationary")
            if not _roots_inside_unit_circle(model.ma, "ma"):
                ok = False; reasons.append("MA not invertible")

    if acc.get("require_windowed_ljungbox", False):
        wlb = diag.get("windowed_lb_passrate")
        thr = acc.get("min_windowed_lb_passrate", 0.10)
        if wlb is not None and wlb < thr:
            ok = False; reasons.append(f"windowed-LB {wlb:.2f}<{thr}")
    elif acc.get("require_ljungbox_pass", True):
        if diag.get("lb_pass") is False:
            ok = False; reasons.append("Ljung-Box fail")

    max_a1 = acc.get("max_abs_acf1")
    if max_a1 is not None:
        a1 = diag.get("acf1_innov")
        if a1 is not None and abs(float(a1)) > max_a1:
            ok = False; reasons.append(f"|acf1| {abs(float(a1)):.2f}>{max_a1}")

    innov = np.asarray(innov, dtype=float)
    innov = innov[np.isfinite(innov)]
    if len(innov) > 10 and residual_var > 0:
        ratio = float(np.var(innov) / residual_var)
        if ratio > acc.get("max_sigma2_ratio", 10.0) or ratio <= 0:
            ok = False; reasons.append(f"variance ratio {ratio:.2f} unreasonable")

    if ok:
        reasons.append("accepted")
    return ok, reasons
