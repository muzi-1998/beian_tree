"""src/detectors/ffpca_aux.py
Forgetting-Factor PCA (FF-PCA) — O(d²) streaming covariance update.

Per Supplementary Benchmark Report Study 4:
    C_t = α · C_{t-1} + (1-α) · x_t · x_t^T,    α = 0.995
    Eigenvectors recomputed every K steps (K=50, default).
    Time complexity: O(d²) per step  (vs expanding window's O(n·d²)).

Use case in D1 v1.1: drift sub-score AUXILIARY validator. PLS remains the
main detector; FF-PCA's SPE statistic provides a second opinion at
production-grade speed.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from .base import BaseDetector, DetectorResult


class FFPCADetector(BaseDetector):
    name = "ff_pca"

    def __init__(self, alpha: float = 0.995, n_components: int = 5,
                 refresh_every: int = 50, train_steps: int = 168):
        super().__init__(alpha=alpha, n_components=n_components,
                         refresh_every=refresh_every, train_steps=train_steps)
        self.alpha = alpha
        self.k = n_components
        self.K = refresh_every
        self.train_steps = train_steps

    def score(self, df_hourly: pd.DataFrame, **ctx) -> DetectorResult:
        """Multivariate FF-PCA SPE on full residual matrix, returned per channel
        attribution (squared reconstruction error per variable).
        """
        X = df_hourly.fillna(0).values
        n, d = X.shape

        # Initial mean & cov from first train_steps rows
        if n <= self.train_steps:
            raise ValueError(f"Need >{self.train_steps} rows for FF-PCA init")
        X_tr = X[: self.train_steps]
        mu = X_tr.mean(axis=0)
        # Sample covariance
        Xc = X_tr - mu
        C = (Xc.T @ Xc) / max(1, len(Xc) - 1)
        # Initial eigendecomposition
        eigvals, eigvecs = np.linalg.eigh(C)
        order = np.argsort(eigvals)[::-1]
        eigvals = eigvals[order]; eigvecs = eigvecs[:, order]
        Pk = eigvecs[:, : self.k]   # principal subspace

        spe_arr = np.zeros(n)
        contrib = np.zeros((n, d))
        # Streaming update
        for t in range(n):
            x = X[t]
            xc = x - mu

            # Project & reconstruct
            score_t = Pk.T @ xc
            xhat = Pk @ score_t
            res = xc - xhat
            spe_arr[t] = float(res @ res)
            contrib[t] = res ** 2

            # Update mu (EMA)
            mu = self.alpha * mu + (1 - self.alpha) * x
            # Update covariance (rank-1)
            xc_new = x - mu
            C = self.alpha * C + (1 - self.alpha) * np.outer(xc_new, xc_new)

            # Periodic eigen-refresh
            if (t + 1) % self.K == 0:
                eigvals, eigvecs = np.linalg.eigh(C)
                order = np.argsort(eigvals)[::-1]
                eigvecs = eigvecs[:, order]
                Pk = eigvecs[:, : self.k]

        # SPE → control-limit (rolling 99% percentile of training-period SPE)
        ucl = np.percentile(spe_arr[: self.train_steps], 99)
        flag_global = pd.Series((spe_arr > ucl).astype(np.int8),
                                index=df_hourly.index, name="ff_pca_flag")

        # Per-channel: contribution-weighted flag
        contrib_df = pd.DataFrame(contrib, index=df_hourly.index, columns=df_hourly.columns)
        # Normalised contribution (each row sums to 1)
        norm = contrib_df.div(contrib_df.sum(axis=1).replace(0, np.nan), axis=0).fillna(0)
        # A channel is "drifting" if SPE>UCL AND it contributes top-3
        rank = (-contrib_df.values).argsort(axis=1)
        per_ch_flag = pd.DataFrame(0, index=df_hourly.index, columns=df_hourly.columns,
                                    dtype=np.int8)
        for i in range(n):
            if flag_global.iat[i] == 1:
                top3 = rank[i, :3]
                per_ch_flag.iloc[i, top3] = 1

        # Per-channel "raw_score" = normalised contribution (continuous)
        raw_per_ch = norm
        return DetectorResult(
            sensor_id="ALL",
            detector_name=self.name,
            timestamps=df_hourly.index,
            raw_score=pd.Series(spe_arr, index=df_hourly.index, name="ff_pca_spe"),
            aux_flag=flag_global,
            metadata={
                "alpha": self.alpha, "n_components": self.k,
                "refresh_every": self.K, "ucl": float(ucl),
                "per_channel_flag": per_ch_flag,
                "per_channel_norm_contribution": raw_per_ch,
            },
        )
