"""src/detectors/regime_two_tier.py
Per spec §9 of D1 main scheme v2:
    Regime = W1 distance ≥ threshold (Tier-1, MAIN)
              AND adjacent KS test significant (Tier-2, CONFIRMATION)
              ↓
              both tiers triggered → regime_event = True

Tier-1 W1 fires for sustained drift; Tier-2 KS confirms a new operating regime
has formed. Either tier alone is insufficient (sustained slow drift may pass
Tier-1 but not Tier-2; sharp local KS hits may pass Tier-2 but not Tier-1).

Aux: BOCPD (low-frequency, daily) — tracked separately, can fortify Q_regime
in v1.1 D-S fusion.

The detector returns a "two-tier raw score" defined as:
    two_tier_score = w1_normalised  *  (1 + 0.5 * tier2_active_indicator)
That is: KS confirmation amplifies a Tier-1 W1 hit by 50%, ensuring the
mapping logistic curve produces sharper Q_regime degradation when both
tiers concur.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from scipy.stats import wasserstein_distance, ks_2samp
from .base import BaseDetector, DetectorResult


class TwoTierRegimeDetector(BaseDetector):
    """W1 (Tier-1) + adjacent KS (Tier-2) joint regime detector."""
    name = "regime_two_tier"

    def __init__(self,
                 ref_days: int = 30,
                 w1_win_days: int = 7,
                 ks_win_days: int = 7,
                 w1_update_h: int = 6,
                 ks_update_h: int = 24,
                 ks_alpha: float = 0.001,
                 n_bootstrap: int = 200,
                 amp_factor: float = 0.5):
        super().__init__(ref_days=ref_days, w1_win_days=w1_win_days,
                         ks_win_days=ks_win_days, w1_update_h=w1_update_h,
                         ks_update_h=ks_update_h, ks_alpha=ks_alpha,
                         n_bootstrap=n_bootstrap, amp_factor=amp_factor)
        self.ref_h = ref_days * 24
        self.w1_win_h = w1_win_days * 24
        self.ks_win_h = ks_win_days * 24
        self.w1_upd = w1_update_h
        self.ks_upd = ks_update_h
        self.amp = amp_factor
        c_alpha = {0.05: 1.36, 0.01: 1.63, 0.001: 1.95}.get(ks_alpha, 1.95)
        self.ks_crit = c_alpha * np.sqrt(2.0 / self.ks_win_h)
        self.n_bootstrap = n_bootstrap

    def score(self, series_hourly: pd.Series, **ctx) -> DetectorResult:
        x = series_hourly.values
        n = len(x)

        # ── Tier-1: W1 vs reference period ─────────────────────────────────
        ref = x[: self.ref_h]
        ref = ref[~np.isnan(ref)]
        if len(ref) < 24:
            empty = pd.Series(np.nan, index=series_hourly.index)
            return DetectorResult(sensor_id=series_hourly.name,
                                  detector_name=self.name,
                                  timestamps=series_hourly.index,
                                  raw_score=empty,
                                  aux_flag=empty.fillna(0).astype(np.int8),
                                  metadata={"reason": "insufficient_ref"})
        rng = np.random.default_rng(42)
        boots = []
        for _ in range(self.n_bootstrap):
            i1 = rng.choice(len(ref), size=min(self.w1_win_h, len(ref) - 1),
                              replace=False)
            i2 = rng.choice(len(ref), size=min(self.w1_win_h, len(ref) - 1),
                              replace=False)
            boots.append(wasserstein_distance(ref[i1], ref[i2]))
        baseline = max(float(np.percentile(boots, 99.5)), 1e-9)

        w1_arr = np.full(n, np.nan)
        for i in range(self.w1_win_h, n, self.w1_upd):
            seg = x[i - self.w1_win_h: i]
            seg = seg[~np.isnan(seg)]
            if len(seg) >= 24:
                w1_arr[i] = wasserstein_distance(seg, ref)
        w1_norm = pd.Series(w1_arr / baseline, index=series_hourly.index).ffill()

        # ── Tier-2: adjacent KS at 7-day windows ──────────────────────────
        ks_arr = np.full(n, np.nan)
        for i in range(2 * self.ks_win_h, n, self.ks_upd):
            s1 = x[i - 2 * self.ks_win_h: i - self.ks_win_h]
            s2 = x[i - self.ks_win_h: i]
            s1 = s1[~np.isnan(s1)]; s2 = s2[~np.isnan(s2)]
            if len(s1) >= 48 and len(s2) >= 48:
                D, _ = ks_2samp(s1, s2)
                ks_arr[i] = D
        ks_series = pd.Series(ks_arr, index=series_hourly.index).ffill()
        tier2_active = (ks_series > self.ks_crit).astype(float)

        # ── Two-tier joint score ──────────────────────────────────────────
        # raw_score = W1_norm × (1 + amp · tier2_active)
        # aux_flag  = (W1_norm > 3) AND (tier2_active = 1)
        w1_clean = w1_norm.fillna(0)
        joint_raw = w1_clean * (1.0 + self.amp * tier2_active.fillna(0))
        joint_flag = ((w1_clean > 3.0) & (tier2_active.fillna(0) == 1)).astype(np.int8)

        return DetectorResult(
            sensor_id=series_hourly.name, detector_name=self.name,
            timestamps=series_hourly.index,
            raw_score=joint_raw,
            aux_flag=joint_flag,
            metadata={
                "tier1_w1_baseline": baseline,
                "tier2_ks_crit": float(self.ks_crit),
                "ref_days": self.params["ref_days"],
                "w1_win_days": self.params["w1_win_days"],
                "ks_win_days": self.params["ks_win_days"],
                "amp_factor": self.amp,
                "tier1_only_count": int(((w1_clean > 3) & (tier2_active.fillna(0) == 0)).sum()),
                "tier2_only_count": int(((w1_clean <= 3) & (tier2_active.fillna(0) == 1)).sum()),
                "both_tiers_count": int(joint_flag.sum()),
                # Side-channel series for blackboard / audit:
                "w1_norm_series": w1_norm,
                "ks_series": ks_series,
                "tier2_active": tier2_active,
            },
        )
