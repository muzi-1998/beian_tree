"""auxiliary_modules.py — Batch & support modules for v1.1.

Contents:
    1. binseg_l2 + PELTBatchCalibrator   — batch CP detection (fast)
    2. build_regime_features + cluster_regimes + build_regime_templates
       — for D5/D7, NOT for D1 scoring
    3. compute_qr_qir_side_outputs — driver annotations (offline only,
       per QR_QIR 修订 §七)
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from typing import Dict, List
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler


# ─────────────────────────────────────────────────────────────────────────────
# 1. PELT batch (fast vectorised binary segmentation)
# ─────────────────────────────────────────────────────────────────────────────
def binseg_l2(x: np.ndarray, penalty: float, min_seg: int = 12,
                max_cps: int = 30) -> List[int]:
    n = len(x)
    if n < 2 * min_seg: return []
    cs = np.concatenate([[0.0], np.cumsum(x)])
    cs2 = np.concatenate([[0.0], np.cumsum(x ** 2)])
    found = []
    stack = [(0, n)]
    while stack and len(found) < max_cps:
        a, b = stack.pop()
        if b - a < 2 * min_seg: continue
        whole_n = b - a
        whole_s = cs[b] - cs[a]
        whole_s2 = cs2[b] - cs2[a]
        whole_cost = whole_s2 - whole_s * whole_s / max(whole_n, 1)
        ks = np.arange(a + min_seg, b - min_seg + 1)
        if len(ks) == 0: continue
        s_l = cs[ks] - cs[a]; s2_l = cs2[ks] - cs2[a]; n_l = ks - a
        cost_l = s2_l - s_l ** 2 / n_l
        s_r = cs[b] - cs[ks]; s2_r = cs2[b] - cs2[ks]; n_r = b - ks
        cost_r = s2_r - s_r ** 2 / n_r
        total = cost_l + cost_r
        best = int(np.argmin(total))
        gain = whole_cost - total[best]
        if gain > penalty:
            cp = int(ks[best])
            found.append(cp)
            stack.append((a, cp)); stack.append((cp, b))
    return sorted(found)


class PELTBatchCalibrator:
    """Batch calibrator using L2-cost binary segmentation (BIC-style penalty)."""
    def __init__(self, lookback_hours: int = 720, min_seg_hours: int = 12,
                 penalty_factor: float = 2.5, stride_h: int = 336,
                 max_cps_per_window: int = 20, neff_ratio: float = 1.0):
        self.lookback = lookback_hours
        self.min_seg = min_seg_hours
        self.penalty_factor = penalty_factor
        self.stride_h = stride_h
        self.max_cps = max_cps_per_window
        # n_eff awareness (audit §3): BIC penalty log(n)·var assumes n independent
        # samples; on an autocorrelated residual PELT over-segments. Inflate the
        # penalty by 1/neff_ratio so the effective sample size is n·neff_ratio.
        # 1 → unchanged (white input); ≈0.01 → ~100× penalty; 0 → no CPs (floor).
        self.neff_ratio = float(min(max(neff_ratio, 0.0), 1.0))

    def calibrate_series(self, ser: pd.Series) -> List[Dict]:
        ser = ser.dropna()
        if len(ser) < 2 * self.min_seg: return []
        if self.neff_ratio <= 0.0: return []   # floor channel — excluded
        events = []
        idx = ser.index
        end_positions = list(range(self.lookback, len(idx), self.stride_h))
        if end_positions and end_positions[-1] != len(idx):
            end_positions.append(len(idx))
        for end_pos in end_positions:
            start_pos = max(0, end_pos - self.lookback)
            seg = ser.iloc[start_pos:end_pos]
            x = seg.values
            if np.var(x) < 1e-10: continue
            penalty = self.penalty_factor * np.log(len(x)) * np.var(x) / self.neff_ratio
            cps = binseg_l2(x, penalty=penalty, min_seg=self.min_seg,
                              max_cps=self.max_cps)
            for cp in cps:
                cp_time = seg.index[cp]
                if any(abs((cp_time - ev["timestamp"]).total_seconds()) < 3600
                        for ev in events):
                    continue
                ws = max(0, cp - self.min_seg)
                we = min(len(x), cp + self.min_seg)
                events.append({
                    "timestamp": cp_time,
                    "magnitude": float(abs(np.mean(x[cp:we]) - np.mean(x[ws:cp]))),
                    "before_mean": float(np.mean(x[ws:cp])),
                    "after_mean":  float(np.mean(x[cp:we])),
                })
        return events


# ─────────────────────────────────────────────────────────────────────────────
# 2. Multi-regime clustering — for D7 templates only (NOT D1 scoring)
# ─────────────────────────────────────────────────────────────────────────────
def build_regime_features(df_h: pd.DataFrame, window_h: int = 24) -> pd.DataFrame:
    """Per-hour rolling features. Uses ALL available channels (DO/ORP/QR/QIR)
    because the regime clustering itself is just for D7 template, NOT D1 main link.
    """
    feats = {}
    for c in df_h.columns:
        feats[f"{c}_mean"] = df_h[c].rolling(window_h, min_periods=window_h // 2).mean()
        feats[f"{c}_std"] = df_h[c].rolling(window_h, min_periods=window_h // 2).std()
    feat_df = pd.DataFrame(feats)
    h = feat_df.index.hour
    d = feat_df.index.dayofweek
    feat_df["sin_h"] = np.sin(2*np.pi*h/24)
    feat_df["cos_h"] = np.cos(2*np.pi*h/24)
    feat_df["sin_d"] = np.sin(2*np.pi*d/7)
    feat_df["cos_d"] = np.cos(2*np.pi*d/7)
    return feat_df


def cluster_regimes(feat_df: pd.DataFrame, k: int = 4,
                    random_state: int = 42) -> Dict:
    valid = feat_df.dropna()
    if len(valid) < k * 24:
        labels = pd.Series(0, index=feat_df.index, name="regime_id")
        return {"labels": labels, "centers": None, "k": 1}
    sc = StandardScaler()
    Xs = sc.fit_transform(valid.values)
    km = KMeans(n_clusters=k, n_init=10, random_state=random_state)
    lab = km.fit_predict(Xs)
    labels_full = pd.Series(np.nan, index=feat_df.index)
    labels_full.loc[valid.index] = lab
    labels_full = labels_full.ffill().bfill().astype(int).rename("regime_id")
    centers = sc.inverse_transform(km.cluster_centers_)
    centers_df = pd.DataFrame(centers, columns=feat_df.columns,
                                index=[f"R{i}" for i in range(k)])
    return {"labels": labels_full, "centers": centers_df, "k": k,
             "scaler": sc, "kmeans": km, "feature_names": list(feat_df.columns)}


def build_regime_templates(df_h: pd.DataFrame, labels: pd.Series,
                            d1_h: pd.DataFrame, min_d1: float = 3.5,
                            scored_channels: list = None) -> Dict:
    """Per-regime high-quality template using ONLY scored channels for D1
    quality filter, but reporting on ALL channels.
    """
    median_d1 = d1_h.median(axis=1)
    high_q_idx = median_d1.index[median_d1 >= min_d1]
    do_cols = [c for c in df_h.columns if c.startswith("DO_")]
    orp_cols = [c for c in df_h.columns if c.startswith("ORP_")]
    templates = {}
    for r in sorted(labels.dropna().unique().astype(int)):
        idx_r = labels[labels == r].index.intersection(high_q_idx)
        if len(idx_r) < 24:
            idx_r = labels[labels == r].index[:240]
        if len(idx_r) == 0: continue
        sub = df_h.loc[idx_r]
        ranks = sub[do_cols].mean().rank(ascending=False).astype(int).to_dict()
        gradient = {}
        for p in (1, 2):
            g = []
            for i in range(1, 5):
                cn = f"DO_{p}_{i}"
                if cn in sub.columns:
                    g.append((cn, float(sub[cn].mean())))
            gradient[f"pool_{p}"] = g
        pairs = ([(f"DO_{1}_{i}", f"DO_{2}_{i}") for i in range(1, 5)]
                  + [(f"ORP_{1}_{i}", f"ORP_{2}_{i}") for i in range(1, 4)])
        sym = []
        for a, b in pairs:
            if a in sub.columns and b in sub.columns:
                sym.append({"pair": f"{a}|{b}",
                             "corr": float(sub[a].corr(sub[b])),
                             "mean_abs_diff": float((sub[a] - sub[b]).abs().mean())})
        templates[int(r)] = {
            "centers": sub.mean().to_dict(),
            "stds":    sub.std().to_dict(),
            "rank":    ranks,
            "gradient": gradient,
            "symmetry": sym,
            "n_hours_used": int(len(idx_r)),
        }
    return templates


# ─────────────────────────────────────────────────────────────────────────────
# 3. QR/QIR side-output annotations (offline-only, per QR_QIR 修订 §七)
# ─────────────────────────────────────────────────────────────────────────────
def compute_qr_qir_side_outputs(df_h: pd.DataFrame,
                                  qr_channels=("QR_1", "QR_2", "QIR_1", "QIR_2")
                                  ) -> pd.DataFrame:
    """Annotate hourly QR/QIR jumps for offline case study only.

    Returns DataFrame indexed by ts with columns:
        qr_context_available, qir_context_available,
        qr_jump_annotation, qir_jump_annotation,
        driver_note
    """
    idx = df_h.index
    out = pd.DataFrame(index=idx)
    qr_present = [c for c in qr_channels if c in df_h.columns and c.startswith("QR_")]
    qir_present = [c for c in qr_channels if c in df_h.columns and c.startswith("QIR_")]
    out["qr_context_available"] = bool(qr_present)
    out["qir_context_available"] = bool(qir_present)

    # Detect significant jumps (relative diff > 25%)
    def jump_annotation(ch_list):
        ann = pd.Series([""] * len(idx), index=idx, dtype=object)
        for c in ch_list:
            x = df_h[c]
            base = x.rolling(24, min_periods=12).mean().abs() + 1e-6
            rel = x.diff().abs() / base
            jumps = rel > 0.25
            for t in x.index[jumps.fillna(False)]:
                tag = f"{c}_jump_rel{float(rel.loc[t]):.2f}"
                if ann.loc[t]:
                    ann.loc[t] = ann.loc[t] + ";" + tag
                else:
                    ann.loc[t] = tag
        return ann

    out["qr_jump_annotation"] = jump_annotation(qr_present)
    out["qir_jump_annotation"] = jump_annotation(qir_present)
    out["driver_note"] = ""
    return out
