"""src/data/consistency.py — cross-variable physical consistency (plan §2.5).

Four diagnostic families + DO_4 near-zero floor vs freeze discrimination:
  1. value / rate  : flows & concentrations cannot be negative; DO/ORP rate caps
  2. conservation  : influent TN vs effluent TN (low-freq nitrogen anchor, D5)
  3. spatial sym.  : 1#/2# parallel-train DO/ORP gradient near-symmetry (D7)
  4. floor / freeze: DO_4 near-zero — distinguish real low-DO (still responds to
                     QR/QIR) from a frozen sensor (no response at all)
"""
from __future__ import annotations
import numpy as np
import pandas as pd

from ..semantics import (DO_CHANNELS, ORP_CHANNELS, FLOW_CHANNELS,
                         AEROBIC_DO, POSTANOXIC_DO)


def value_rate_report(df_min_raw: pd.DataFrame, df_inf: pd.DataFrame,
                      df_eff: pd.DataFrame) -> pd.DataFrame:
    """Negative-value / out-of-range fractions per variable (pre-clip stats)."""
    rows = []

    def neg_frac(s):
        v = s.dropna()
        return 100.0 * (v < 0).mean() if len(v) else np.nan

    for c in FLOW_CHANNELS:
        rows.append(dict(variable=c, kind="flow",
                         neg_pct=round(neg_frac(df_min_raw[c]), 3),
                         note="negative flow physically impossible"))
    for c in ["inf_Q", "inf_NH4", "inf_TN", "inf_COD", "inf_TP", "inf_SS"]:
        if c in df_inf:
            rows.append(dict(variable=c, kind="influent",
                             neg_pct=round(neg_frac(df_inf[c]), 3),
                             note="negative concentration/flow = acquisition error"))
    for c in ["eff_COD", "eff_NH4", "eff_TN", "eff_TP"]:
        if c in df_eff:
            rows.append(dict(variable=c, kind="effluent",
                             neg_pct=round(neg_frac(df_eff[c]), 3),
                             note="near detection limit; left-censored"))
    return pd.DataFrame(rows)


def parallel_symmetry(df_min: pd.DataFrame) -> pd.DataFrame:
    """1# vs 2# train gradient symmetry — DO/ORP per sequence position.

    For each (sensor-type, seq) compare train-1 vs train-2 mean; report the
    asymmetry. Strong asymmetry is a D7 pre-signal (kept as evidence)."""
    rows = []
    # DO seq 1..4, ORP seq 1..3
    for seq in range(1, 5):
        c1, c2 = f"DO_1_{seq}", f"DO_2_{seq}"
        if c1 in df_min and c2 in df_min:
            m1, m2 = df_min[c1].mean(), df_min[c2].mean()
            rows.append(dict(sensor="DO", seq=seq, train1_mean=round(m1, 3),
                             train2_mean=round(m2, 3),
                             abs_diff=round(abs(m1 - m2), 3)))
    for seq in range(1, 4):
        c1, c2 = f"ORP_1_{seq}", f"ORP_2_{seq}"
        if c1 in df_min and c2 in df_min:
            m1, m2 = df_min[c1].mean(), df_min[c2].mean()
            rows.append(dict(sensor="ORP", seq=seq, train1_mean=round(m1, 1),
                             train2_mean=round(m2, 1),
                             abs_diff=round(abs(m1 - m2), 1)))
    return pd.DataFrame(rows)


def along_train_gradient(df_min: pd.DataFrame) -> pd.DataFrame:
    """Along-train spatial gradient = D7 template basis (plan §2.2).

    Aerobic DO should rise front->rear; post-anoxic DO ~0; ORP anaerobic->anoxic
    should step down. Returns per-train ordered means."""
    rows = []
    for train in (1, 2):
        do_means = {f"DO_{train}_{i}": df_min.get(f"DO_{train}_{i}",
                    pd.Series(dtype=float)).mean() for i in range(1, 5)}
        orp_means = {f"ORP_{train}_{i}": df_min.get(f"ORP_{train}_{i}",
                     pd.Series(dtype=float)).mean() for i in range(1, 4)}
        rows.append(dict(train=train, **{k: round(v, 3) for k, v in
                                         {**do_means, **orp_means}.items()}))
    return pd.DataFrame(rows)


def do4_floor_vs_freeze(df_min: pd.DataFrame) -> pd.DataFrame:
    """DO_4 near-zero floor vs freeze discrimination (plan §2.2, §2.5).

    A true process floor still shows a (small) RESPONSE to the recycle drivers
    QR/QIR; a frozen sensor shows none. We report:
      * day/night means (floor should be load-independent),
      * |corr(DO_4, QIR)| as a response proxy (higher => responsive => real low-DO),
      * residual std after removing a slow baseline (freeze => ~0).
    """
    rows = []
    for train in (1, 2):
        c = f"DO_{train}_4"
        if c not in df_min:
            continue
        s = df_min[c]
        hour = s.index.hour
        day = s[(hour >= 8) & (hour < 20)].mean()
        night = s[(hour < 6) | (hour >= 22)].mean()
        # response proxy: correlation with internal recycle of same train
        qir = df_min.get(f"QIR_{train}")
        resp = np.nan
        if qir is not None:
            joint = pd.concat([s, qir], axis=1).dropna()
            if len(joint) > 100 and joint.iloc[:, 0].std() > 0:
                resp = abs(joint.iloc[:, 0].corr(joint.iloc[:, 1]))
        # short-term variability (freeze => near 0)
        microvar = s.diff().abs().median()
        rows.append(dict(channel=c, mean=round(s.mean(), 4),
                         day_mean=round(day, 4), night_mean=round(night, 4),
                         day_night_diff=round(abs(day - night), 4),
                         abs_corr_QIR=round(resp, 3) if resp == resp else np.nan,
                         micro_var=round(microvar, 4),
                         interpretation="process_floor" if (resp == resp and resp > 0.05)
                                        or microvar > 0.005 else "possible_freeze"))
    return pd.DataFrame(rows)


def nitrogen_balance(df_inf: pd.DataFrame, df_eff: pd.DataFrame) -> pd.DataFrame:
    """Low-frequency nitrogen anchor: daily influent TN vs effluent TN (D5)."""
    if "inf_TN" not in df_inf or "eff_TN" not in df_eff:
        return pd.DataFrame()
    inf_d = df_inf["inf_TN"].resample("1D").mean()
    eff_d = df_eff["eff_TN"].resample("1D").mean()
    j = pd.concat([inf_d.rename("inf_TN"), eff_d.rename("eff_TN")], axis=1).dropna()
    j["removed_TN"] = j["inf_TN"] - j["eff_TN"]
    j["removal_pct"] = 100 * j["removed_TN"] / j["inf_TN"]
    return j.reset_index().rename(columns={"index": "date"})
