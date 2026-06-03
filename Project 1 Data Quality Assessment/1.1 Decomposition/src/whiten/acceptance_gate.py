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
    """Return (passed: bool, reasons: list[str])."""
    acc = cfg.get("acceptance", {})
    reasons = []
    ok = True

    if acc.get("require_stationary_invertible", True):
        if not _roots_inside_unit_circle(model.ar, "ar"):
            ok = False; reasons.append("AR not stationary")
        if not _roots_inside_unit_circle(model.ma, "ma"):
            ok = False; reasons.append("MA not invertible")

    if acc.get("require_ljungbox_pass", True) and diag is not None:
        if diag.get("lb_pass") is False:
            ok = False; reasons.append("Ljung-Box fail")

    innov = np.asarray(innov, dtype=float)
    innov = innov[np.isfinite(innov)]
    if len(innov) > 10 and residual_var > 0:
        ratio = float(np.var(innov) / residual_var)
        if ratio > acc.get("max_sigma2_ratio", 10.0) or ratio <= 0:
            ok = False; reasons.append(f"variance ratio {ratio:.2f} unreasonable")

    if ok:
        reasons.append("accepted")
    return ok, reasons
