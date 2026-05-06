"""src/baseline/regime_clustering.py
Multi-regime clustering — replaces V1's single high-quality template with
k regime-specific templates (per spec §6 of output design).

Approach: k-means on hourly multivariate features:
  - mean/std of all 18 channels in a 24-h sliding window
  - day-of-week + hour-of-day cyclical features
Output: regime_id per hour, written to blackboard. Aggregation layer can
then use regime-conditional templates for D7 and adjust expectations.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
from typing import Dict, List


def build_regime_features(df_h: pd.DataFrame, window_h: int = 24
                            ) -> pd.DataFrame:
    """Feature matrix for clustering.

    Per hour, features are:
        - mean of each channel over the past `window_h`
        - std  of each channel over the past `window_h`
        - sin/cos of hour-of-day (period 24)
        - sin/cos of day-of-week (period 7)
    """
    feats = []
    for c in df_h.columns:
        feats.append(df_h[c].rolling(window_h, min_periods=window_h // 2).mean()
                     .rename(f"{c}_mean"))
        feats.append(df_h[c].rolling(window_h, min_periods=window_h // 2).std()
                     .rename(f"{c}_std"))
    feat_df = pd.concat(feats, axis=1)
    # Cyclical time features
    h = feat_df.index.hour
    d = feat_df.index.dayofweek
    feat_df["sin_h"] = np.sin(2 * np.pi * h / 24)
    feat_df["cos_h"] = np.cos(2 * np.pi * h / 24)
    feat_df["sin_d"] = np.sin(2 * np.pi * d / 7)
    feat_df["cos_d"] = np.cos(2 * np.pi * d / 7)
    return feat_df


def cluster_regimes(feat_df: pd.DataFrame, k: int = 4,
                     random_state: int = 42) -> Dict:
    """Fit k-means on the feature matrix and return regime assignment + centers."""
    valid = feat_df.dropna()
    if len(valid) < k * 10:
        # Insufficient data: assign all to single regime
        labels = pd.Series(0, index=feat_df.index, name="regime_id")
        return {"labels": labels, "centers": None, "k": 1, "feature_names": list(feat_df.columns)}
    sc = StandardScaler()
    Xs = sc.fit_transform(valid.values)
    km = KMeans(n_clusters=k, n_init=10, random_state=random_state)
    lab = km.fit_predict(Xs)
    labels_full = pd.Series(np.nan, index=feat_df.index)
    labels_full.loc[valid.index] = lab
    labels_full = labels_full.ffill().bfill().astype(int).rename("regime_id")
    # De-standardise centers
    centers_orig = sc.inverse_transform(km.cluster_centers_)
    centers_df = pd.DataFrame(centers_orig, columns=feat_df.columns,
                              index=[f"R{i}" for i in range(k)])
    return {"labels": labels_full, "centers": centers_df, "k": k,
            "scaler": sc, "kmeans": km,
            "feature_names": list(feat_df.columns)}


def regime_summary(labels: pd.Series, df_h: pd.DataFrame) -> pd.DataFrame:
    """Per-regime summary: time coverage, channel-wise mean/std."""
    rows = []
    for r in sorted(labels.dropna().unique().astype(int)):
        idx = labels[labels == r].index
        row = {"regime_id": int(r), "n_hours": len(idx),
               "time_pct": float(len(idx) / len(labels))}
        for c in df_h.columns:
            row[f"{c}_mean"] = float(df_h.loc[idx, c].mean())
            row[f"{c}_std"]  = float(df_h.loc[idx, c].std())
        rows.append(row)
    return pd.DataFrame(rows)


def build_regime_templates(df_h: pd.DataFrame, labels: pd.Series,
                            d1_h: pd.DataFrame, min_d1: float = 3.5) -> Dict:
    """For each regime, build templates (cluster center, rank, gradient,
    twin-symmetry) using ONLY high-quality hours (D1 ≥ min_d1).

    Returns
    -------
    templates : {regime_id: {centers, rank, gradient, sym, n_hours}}
    """
    templates = {}
    median_d1 = d1_h.median(axis=1)
    high_q = labels.index[median_d1.reindex(labels.index) >= min_d1]
    do_cols  = [c for c in df_h.columns if c.startswith("DO_")]

    for r in sorted(labels.dropna().unique().astype(int)):
        # Hours in this regime AND high-quality
        idx_r = labels[labels == r].index.intersection(high_q)
        if len(idx_r) < 24:
            # Fallback: all hours in regime
            idx_r = labels[labels == r].index
        if len(idx_r) == 0:
            continue
        sub = df_h.loc[idx_r]
        # Rank template (descending mean over DO channels)
        ranks = sub[do_cols].mean().rank(ascending=False).astype(int).to_dict()
        # Gradient template per pool
        gradient = {}
        for p in (1, 2):
            pool_means = []
            for i in range(1, 5):
                cn = f"DO_{p}_{i}"
                if cn in sub.columns:
                    pool_means.append((cn, float(sub[cn].mean())))
            gradient[f"pool_{p}"] = pool_means
        # Symmetry: corr per twin pair
        pairs = [(f"DO_{1}_{i}", f"DO_{2}_{i}") for i in range(1, 5)] + \
                [(f"ORP_{1}_{i}", f"ORP_{2}_{i}") for i in range(1, 4)] + \
                [("QR_1", "QR_2"), ("QIR_1", "QIR_2")]
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
            "n_hours": int(len(idx_r)),
        }
    return templates
