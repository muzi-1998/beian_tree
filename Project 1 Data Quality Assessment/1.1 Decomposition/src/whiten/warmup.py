"""src/whiten/warmup.py — warm-restart internal-state handoff (plan §6.4 (四)).

Swapping coefficients without re-seeding the internal eps/eta/sigma2 buffers
produces a switch spike that Spike would misfire on. Before publishing, the
slow track re-runs the *new* coefficients over the most recent `warmup_hours`
of real residual to obtain a consistent hot internal state, which is shipped
inside the WhitenModel.warmup_state.
"""
from __future__ import annotations
import numpy as np
import pandas as pd

from .param_store import WhitenModel
from .online_whitener import whiten_series


def warmup(model: WhitenModel, recent_resid: pd.Series) -> WhitenModel:
    """Re-run `model` on recent residual; refresh warmup_state (eps/eta/sigma2)."""
    if recent_resid is None or recent_resid.dropna().empty:
        return model
    res = whiten_series(recent_resid, model)
    eta = res["innovation"].values
    sig2 = res["sigma2"].values
    y = recent_resid.values.astype(float) - model.intercept
    p, q = model.p, model.q
    eps_hist = [v for v in y[::-1] if np.isfinite(v)][:p]
    eta_hist = [v for v in eta[::-1] if np.isfinite(v)][:q]
    last_sig2 = float(sig2[np.isfinite(sig2)][-1]) if np.isfinite(sig2).any() else \
        float(model.warmup_state.get("sigma2", 1.0))
    new_state = dict(eps=eps_hist, eta=eta_hist, sigma2=last_sig2)
    return WhitenModel(version=model.version, p=model.p, q=model.q, ar=model.ar,
                       ma=model.ma, intercept=model.intercept, garch=model.garch,
                       warmup_state=new_state, diagnostics=model.diagnostics)
