"""generate_mock_data.py — create synthetic sensor data for D1 v1.1 demo.

Generates two pickle files that run_v11_pipeline.py expects:
  strict_v1_inputs.pkl  — STRICT-V1 sub-scores, D1, detector raw outputs
  raw_hourly.pkl        — hourly sensor readings + PLS residuals

Scenario (30 days / 720 h, 14 scored channels):
  Normal operation     — scores mostly 3.8–5.0
  Step event           — DO_1_3, hours 150–186 (36 h)  → Q_step drops
  Regime shift         — ORP_2_1, hours 300–372 (72 h) → Q_regime drops
  Freeze event         — DO_2_2,  hours 450–474 (24 h) → Q_freeze drops
"""
from __future__ import annotations
import pickle
import numpy as np
import pandas as pd
from pathlib import Path

_ROOT = Path(__file__).parent
np.random.seed(42)

# ─── time axis ───────────────────────────────────────────────────────────────
N_HOURS = 720
START   = pd.Timestamp("2025-10-01 00:00")
IDX     = pd.date_range(START, periods=N_HOURS, freq="1h")
H_ARR   = np.asarray(IDX.hour, dtype=float)   # 0–23 daily cycle

# ─── channels ────────────────────────────────────────────────────────────────
SCORED  = [
    "DO_1_1","DO_1_2","DO_1_3","DO_1_4",
    "DO_2_1","DO_2_2","DO_2_3","DO_2_4",
    "ORP_1_1","ORP_1_2","ORP_1_3",
    "ORP_2_1","ORP_2_2","ORP_2_3",
]
SUPPORT = ["QR_1","QR_2","QIR_1","QIR_2"]
ALL_CH  = SCORED + SUPPORT

WEIGHTS = {"spike": 0.15, "step": 0.20, "drift": 0.25, "freeze": 0.20, "regime": 0.20}


# ─── helpers ─────────────────────────────────────────────────────────────────
def _normal_scores(n: int, mu: float = 4.3, sigma: float = 0.25) -> np.ndarray:
    return np.clip(mu + np.random.randn(n) * sigma, 1.0, 5.0)


def _logistic_score(x: np.ndarray, k: float, x0: float) -> np.ndarray:
    """Map detector metric → quality score [1, 5]."""
    return np.clip(1.0 + 4.0 / (1.0 + np.exp(k * (x - x0))), 1.0, 5.0)


# ─── sub-scores ──────────────────────────────────────────────────────────────
print("[1/4] Generating sub-scores …")

data_q: dict[str, dict[str, np.ndarray]] = {
    q: {c: _normal_scores(N_HOURS) for c in SCORED}
    for q in ("Q_spike", "Q_step", "Q_drift", "Q_freeze", "Q_regime")
}

# ── Step event: DO_1_3, h 150–186 ──
data_q["Q_step"]["DO_1_3"][150:186] = np.clip(
    1.8 + np.random.randn(36) * 0.15, 1.0, 2.5)

# ── Regime shift: ORP_2_1, h 300–372 ──
data_q["Q_regime"]["ORP_2_1"][300:372] = np.clip(
    1.6 + np.random.randn(72) * 0.12, 1.0, 2.5)

# ── Freeze event: DO_2_2, h 450–474 ──
data_q["Q_freeze"]["DO_2_2"][450:474] = np.clip(
    1.5 + np.random.randn(24) * 0.10, 1.0, 2.0)

subs_v1 = {q: pd.DataFrame(v, index=IDX) for q, v in data_q.items()}

# ── Strict-V1 D1 (weighted aggregation + λ-blend, no state-machine) ──
D1_base = (
    WEIGHTS["spike"]  * subs_v1["Q_spike"]  +
    WEIGHTS["step"]   * subs_v1["Q_step"]   +
    WEIGHTS["drift"]  * subs_v1["Q_drift"]  +
    WEIGHTS["freeze"] * subs_v1["Q_freeze"] +
    WEIGHTS["regime"] * subs_v1["Q_regime"]
)
M = pd.DataFrame(index=IDX, columns=SCORED, dtype=float)
for c in SCORED:
    M[c] = pd.concat([subs_v1[q][c] for q in subs_v1], axis=1).min(axis=1)

D1_v1_full = (0.70 * D1_base + 0.30 * M).clip(1.0, 5.0)

# ─── raw detector outputs ─────────────────────────────────────────────────────
print("[2/4] Generating detector raw outputs …")

# KS statistic (step detector): logistic maps to Q_step
# Normal: ks≈0.08 → Q_step≈4.9; event: ks≈0.45 → Q_step≈1.2
ks_base = np.clip(0.08 + np.abs(np.random.randn(N_HOURS)) * 0.03, 0.0, 1.0)
ks_stat = {c: ks_base.copy() for c in SCORED}
ks_stat["DO_1_3"][150:186] = np.clip(0.45 + np.random.randn(36) * 0.04, 0.3, 0.9)
ks_stat_df = pd.DataFrame(ks_stat, index=IDX)

# W1 norm (regime detector): normal ~1.2, regime event ~4.8
w1_base = np.clip(1.2 + np.abs(np.random.randn(N_HOURS)) * 0.4, 0.0, 8.0)
w1_norm = {c: w1_base.copy() for c in SCORED}
w1_norm["ORP_2_1"][300:372] = np.clip(4.8 + np.random.randn(72) * 0.25, 3.5, 7.0)
w1_norm_df = pd.DataFrame(w1_norm, index=IDX)

# Hampel z (spike)
hampel_z = {c: np.clip(0.8 + np.abs(np.random.randn(N_HOURS)) * 0.3, 0, 8) for c in SCORED}
hampel_z_df = pd.DataFrame(hampel_z, index=IDX)

# PLS residual z (drift)
pls_z = {c: np.clip(0.8 + np.abs(np.random.randn(N_HOURS)) * 0.4, 0, 8) for c in SCORED}
pls_z_df = pd.DataFrame(pls_z, index=IDX)

# Freeze: rle run (min), rel_var, unique_ratio — mostly normal
freeze_rle   = pd.DataFrame(np.zeros((N_HOURS, len(SCORED))), index=IDX, columns=SCORED)
freeze_rle.loc[IDX[450:474], "DO_2_2"] = 35.0   # 35-min freeze run
freeze_rvar  = pd.DataFrame(np.ones((N_HOURS, len(SCORED))), index=IDX, columns=SCORED)
freeze_rvar.loc[IDX[450:474], "DO_2_2"] = 0.05  # low variance during freeze
freeze_uniq  = pd.DataFrame(np.ones((N_HOURS, len(SCORED))), index=IDX, columns=SCORED)
freeze_uniq.loc[IDX[450:474], "DO_2_2"] = 0.08  # few unique values

spike_rate = {c: np.clip(0.01 + np.abs(np.random.randn(N_HOURS)) * 0.004, 0, 1)
              for c in SCORED}
spike_rate_df = pd.DataFrame(spike_rate, index=IDX)

detectors_raw = {
    "ks_statistic_hourly":  ks_stat_df,
    "w1_normalised_hourly": w1_norm_df,
    "hampel_z_hourly_max":  hampel_z_df,
    "pls_residual_z_hourly": pls_z_df,
    "freeze_rle_run_min":   freeze_rle,
    "freeze_rel_var":       freeze_rvar,
    "freeze_unique_ratio":  freeze_uniq,
    "spike_rate_6h_input":  spike_rate_df,
}

# ─── save strict_v1_inputs.pkl ────────────────────────────────────────────────
v1_payload = {
    "subs_v1":   subs_v1,
    "D1_v1":     D1_v1_full,
    "detectors": detectors_raw,
}
out1 = _ROOT / "strict_v1_inputs.pkl"
with open(out1, "wb") as f:
    pickle.dump(v1_payload, f)
print(f"  → {out1.name} ({out1.stat().st_size // 1024} KB)")

# ─── hourly sensor readings (df_h) + residuals (resid_h) ─────────────────────
print("[3/4] Generating hourly sensor readings …")

daily = np.sin(2 * np.pi * H_ARR / 24)   # daily cycle component

do_data: dict[str, np.ndarray] = {}
for p in (1, 2):
    for i in (1, 2, 3, 4):
        col = f"DO_{p}_{i}"
        base = 9.5 + 0.5 * daily + np.random.randn(N_HOURS) * 0.6
        do_data[col] = base

orp_data: dict[str, np.ndarray] = {}
for p in (1, 2):
    for i in (1, 2, 3):
        col = f"ORP_{p}_{i}"
        base = 300 + 15 * daily + np.random.randn(N_HOURS) * 12
        orp_data[col] = base

# Inject sensor changes matching sub-score anomalies
do_data["DO_1_3"][150:186]   += 1.8        # upward step (biofouling analogue)
orp_data["ORP_2_1"][300:372]  = (
    250 + 10 * daily[300:372] + np.random.randn(72) * 8)  # regime shift (lower ORP band)
do_data["DO_2_2"][450:474]   = do_data["DO_2_2"][449]     # flat freeze

qr_data  = {f"QR_{i}":  300 + np.random.randn(N_HOURS) * 25 for i in (1, 2)}
qir_data = {f"QIR_{i}": 280 + np.random.randn(N_HOURS) * 20 for i in (1, 2)}

df_h = pd.DataFrame({**do_data, **orp_data, **qr_data, **qir_data}, index=IDX)

# PLS residuals: normal N(0, 0.5), large during anomaly events
resid_dict: dict[str, np.ndarray] = {
    c: np.random.randn(N_HOURS) * 0.5 for c in SCORED
}
resid_dict["DO_1_3"][150:186]   = np.random.randn(36) * 2.2 + 1.6
resid_dict["ORP_2_1"][300:372]  = np.random.randn(72) * 2.8 + 2.0
resid_dict["DO_2_2"][450:474]   = np.random.randn(24) * 0.05  # frozen → near-zero residual
resid_h = pd.DataFrame(resid_dict, index=IDX)

raw_payload = {"df_h": df_h, "resid_h": resid_h}
out2 = _ROOT / "raw_hourly.pkl"
with open(out2, "wb") as f:
    pickle.dump(raw_payload, f)
print(f"  → {out2.name} ({out2.stat().st_size // 1024} KB)")

# ─── summary ─────────────────────────────────────────────────────────────────
print("[4/4] Summary")
print(f"  Time span : {IDX[0]} → {IDX[-1]}  ({N_HOURS} h)")
print(f"  Channels  : {len(SCORED)} scored + {len(SUPPORT)} support")
print(f"  D1_v1 mean: {D1_v1_full.mean().mean():.3f}")
print(f"  Anomaly scenarios:")
print(f"    Step   DO_1_3  h150–186  Q_step min  = {subs_v1['Q_step']['DO_1_3'][150:186].min():.2f}")
print(f"    Regime ORP_2_1 h300–372  Q_regime min= {subs_v1['Q_regime']['ORP_2_1'][300:372].min():.2f}")
print(f"    Freeze DO_2_2  h450–474  Q_freeze min= {subs_v1['Q_freeze']['DO_2_2'][450:474].min():.2f}")
print("Done.")
