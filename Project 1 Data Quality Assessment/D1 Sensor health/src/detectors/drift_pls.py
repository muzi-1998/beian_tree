"""src/detectors/drift_pls.py
PLS virtual-sensor drift detector — STRICT spec v2 §7 peer selection:
    1. Same-pool adjacent segments (DO_p_i ↔ DO_p_(i±1) and ORP_p_j ↔ DO_p_j)
    2. Twin-pool counterpart (DO_1_i ↔ DO_2_i, ORP_1_j ↔ ORP_2_j, QR_1 ↔ QR_2)
    3. QR / QIR exogenous drivers (always added as predictors)

This is a hard-coded engineering prior, NOT a data-driven correlation pick.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from sklearn.cross_decomposition import PLSRegression
from sklearn.preprocessing import StandardScaler
from .base import BaseDetector, DetectorResult


# Engineering peer rules — declarative, easy to audit
def engineered_peers(target: str, all_columns: list) -> list:
    """Return peer-column list per spec §7 engineering prior."""
    cols = set(all_columns)
    peers = set()

    flow_cols = {c for c in cols if c.startswith("Q")}      # QR_1, QR_2, QIR_1, QIR_2

    # Helper parser
    def _parse(c):
        # 'DO_1_3' → ('DO', 1, 3); 'ORP_2_2' → ('ORP', 2, 2); 'QR_1' → ('Q', 0, 0)
        parts = c.split("_")
        if c.startswith("DO_") or c.startswith("ORP_"):
            return parts[0], int(parts[1]), int(parts[2])
        return None, None, None

    kind, pool, seg = _parse(target)

    # Rule 1 — same-pool adjacent (DO ↔ DO and ORP ↔ ORP segments ±1)
    if kind in ("DO", "ORP"):
        for d in (-1, +1):
            cand = f"{kind}_{pool}_{seg + d}"
            if cand in cols:
                peers.add(cand)
    # Rule 1b — DO_p_i and ORP_p_j cross-kind same-pool same-segment
    if kind == "DO":
        cand = f"ORP_{pool}_{min(seg, 3)}"
        if cand in cols:
            peers.add(cand)
    elif kind == "ORP":
        cand = f"DO_{pool}_{seg}"
        if cand in cols:
            peers.add(cand)

    # Rule 2 — twin-pool counterpart
    if kind in ("DO", "ORP") and pool in (1, 2):
        twin_pool = 2 if pool == 1 else 1
        cand = f"{kind}_{twin_pool}_{seg}"
        if cand in cols:
            peers.add(cand)
    elif target in ("QR_1", "QR_2"):
        twin = "QR_2" if target == "QR_1" else "QR_1"
        if twin in cols: peers.add(twin)
    elif target in ("QIR_1", "QIR_2"):
        twin = "QIR_2" if target == "QIR_1" else "QIR_1"
        if twin in cols: peers.add(twin)

    # Rule 3 — QR / QIR exogenous drivers (always)
    peers.update(flow_cols)

    # Don't include target itself
    peers.discard(target)
    return sorted(peers)


class PLSVirtualSensorDetector(BaseDetector):
    """PLS detector with spec-mandated engineered peer selection."""
    name = "pls_virtual"

    def __init__(self, n_components: int = 3, train_days: int = 21):
        super().__init__(n_components=n_components, train_days=train_days)
        self.k = n_components
        self.train_days = train_days
        self._models = {}
        self._peers_used = {}    # for audit

    def fit(self, df_hourly: pd.DataFrame, target: str, peer_cols: list, **ctx):
        n_train = self.train_days * 24
        Xtr = df_hourly.loc[:, peer_cols].iloc[:n_train].ffill().fillna(0).values
        ytr = df_hourly.loc[:, target].iloc[:n_train].ffill().fillna(0).values
        sx = StandardScaler().fit(Xtr)
        sy = StandardScaler().fit(ytr.reshape(-1, 1))
        Xs = sx.transform(Xtr)
        ys = sy.transform(ytr.reshape(-1, 1)).ravel()
        k = min(self.k, max(1, min(Xs.shape[0] - 1, Xs.shape[1])))
        pls = PLSRegression(n_components=k, scale=False).fit(Xs, ys)
        yhat = pls.predict(Xs).ravel()
        sigma = float(np.std(ys - yhat) + 1e-9)
        self._models[target] = (pls, sx, sy, sigma)
        self._peers_used[target] = list(peer_cols)

    def score(self, df_hourly: pd.DataFrame, target: str,
              peer_cols: list = None, **ctx) -> DetectorResult:
        # Engineering peer rule kicks in if not provided
        if peer_cols is None:
            peer_cols = engineered_peers(target, list(df_hourly.columns))
        if target not in self._models:
            self.fit(df_hourly, target=target, peer_cols=peer_cols)
        pls, sx, sy, sigma = self._models[target]

        X = df_hourly.loc[:, peer_cols].ffill().fillna(0).values
        y = df_hourly.loc[:, target].ffill().fillna(0).values
        Xs = sx.transform(X)
        yhat_s = pls.predict(Xs).ravel()
        yhat = sy.inverse_transform(yhat_s.reshape(-1, 1)).ravel()
        resid = y - yhat
        sigma_y = float(np.std(y[: self.train_days * 24]) + 1e-9)
        resid_z = pd.Series(np.abs(resid) / sigma_y, index=df_hourly.index)
        flag = (resid_z > 3.0).astype(np.int8)
        return DetectorResult(
            sensor_id=target, detector_name=self.name,
            timestamps=df_hourly.index, raw_score=resid_z, aux_flag=flag,
            metadata={"n_components": self.k, "train_days": self.train_days,
                      "sigma_resid": sigma, "sigma_y": sigma_y,
                      "peer_cols": peer_cols,
                      "peer_selection_rule": "spec_v2_engineered_prior"},
        )
