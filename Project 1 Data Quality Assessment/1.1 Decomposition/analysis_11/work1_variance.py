"""analysis_11/work1_variance.py — Work 1: variance-contribution profile.

Supports the claim "why differentiated decomposition is necessary".

Method (plan): stepwise variance *reduction*, not raw Var ratios — additive
components are not orthogonal, so naive ratios do not close. With the §1.1
CAUSAL components (trend m, seasonal s, residual e = X−m−s):

    r0 = Var(X);  r1 = Var(X−m);  r2 = Var(e)
    trend%    = (r0−r1)/r0
    seasonal% = (r1−r2)/r0
    residual% = r2/r0           → trend% + seasonal% + residual% ≡ 1

m is rebuilt with §1.1's exact causal trend operator applied to the known
baseline b = X − e (e taken from residual_*.parquet, so residual% is exact and
no future sample enters m). A full-span (acausal) partition is computed in
parallel to show the causal scheme loses almost no explanatory power.

Outputs
  outputs/figures/fig_1x_variance_partition_profile.png   (stacked bars, blue/orange/grey)
  outputs/tables/A1_variance_partition.csv                (33ch × {trend%,seasonal%,residual%, causal−fullspan resid diff})
  outputs/plot_data/fig_1x_variance_partition_profile.csv (figure data)
"""
from __future__ import annotations
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches

from common import (ROOT, TAB, FIG, PDATA, COMP, PROCESS_ORDER, POS_BAND,
                    BAND_ORDER, load_manifest, load_config, longest_period_hours,
                    get_raw, get_residual, setup_style)
from src.baseline.deperiodise import _causal_trend, _causal_stl_seasonal


def _align(*series) -> pd.DataFrame:
    return pd.concat(series, axis=1).dropna()


def _win_pts(index, bw_h: float) -> int:
    dt_h = pd.Series(index).diff().dt.total_seconds().median() / 3600.0
    return max(3, int(round(bw_h / dt_h))) if dt_h and dt_h > 0 else int(bw_h)


def partition(X: pd.Series, e_final: pd.Series, longest_h: float,
              period_pts: int) -> dict:
    """Stepwise variance reduction (plan):  r0,r1,r2 = Var(X), Var(X−m), Var(e).

    The headline partition uses a SELF-CONSISTENT 2-step causal decomposition
    built from §1.1's own operators — a LONG causal trend m = causal_trend(X,
    3×longest_period) (averaging ≥3 full cycles zeroes the seasonal so m carries
    only the slow drift) + a causal trailing per-phase seasonal s on (X−m); then
    e = X−m−s. No future sample enters either step; the partition closes to 100%
    and the shares stay ≥0 (s is the trailing phase signal, e its complement).

    Reported alongside (Table A1, transparency):
      resid_final = Var(residual_*.parquet)/Var(X) — §1.1's actual whitening-input
        share; where it exceeds the 2-step residual the §1.1 harmonic forward-fit
        added variance (decomposition overfit on a hard channel — itself evidence
        for differentiated handling).
      resid_full  = acausal 2-step residual (centred trend + whole-series phase
        mean) → Δ = resid_causal − resid_full = the leakage cost of causality.
    """
    bw_trend = 3.0 * longest_h
    win = _win_pts(X.index, bw_trend)
    xv = X.astype(float)

    # ── causal 2-step (headline) ─────────────────────────────────────────────
    m_c = pd.Series(_causal_trend(xv.values, xv.index, int(round(bw_trend))), index=xv.index)
    des_c = (xv - m_c)
    s_c = pd.Series(_causal_stl_seasonal(des_c.values, period_pts), index=xv.index)
    e_c = (des_c - s_c)
    d = _align(xv.rename("X"), m_c.rename("m"), e_c.rename("e"))
    r0 = max(float(d["X"].var()), 1e-12)
    r1 = float((d["X"] - d["m"]).var())
    r2 = float(d["e"].var())

    # ── acausal 2-step (ablation) ────────────────────────────────────────────
    m_a = xv.rolling(win, center=True, min_periods=max(3, win // 2)).mean()
    des_a = (xv - m_a)
    ph = np.arange(len(xv)) % period_pts
    s_a = pd.Series(des_a.values, index=xv.index).groupby(ph).transform("mean")
    e_a = (des_a - s_a)
    rf_full = float(_align(xv.rename("X"), e_a.rename("ea"))["ea"].var()) / r0

    # ── §1.1 final whitening residual share (transparency) ───────────────────
    rf_final = float(_align(e_final.rename("ef"))["ef"].var()) / r0

    return {"r0": r0, "trend": (r0 - r1) / r0,
            "seasonal": (r1 - r2) / r0, "residual": r2 / r0,
            "resid_full2": rf_full, "resid_final": rf_final, "n": len(d)}


def main():
    setup_style()
    man = load_manifest()
    cfg = load_config()

    rows = []
    for ch in PROCESS_ORDER:
        group = man.loc[ch, "group"]
        longest_h = longest_period_hours(group, cfg)
        period_pts = int(cfg["groups"][group]["candidate_periods"][0])
        X = get_raw(ch).dropna()
        e = get_residual(ch).reindex(X.index)
        cp = partition(X, e, longest_h, period_pts)
        rows.append({
            "channel": ch, "band": POS_BAND[ch], "group": group,
            "scoring_mode": man.loc[ch, "scoring_mode"],
            "trend_pct": 100 * cp["trend"], "seasonal_pct": 100 * cp["seasonal"],
            "residual_pct": 100 * cp["residual"],
            "resid_full_pct": 100 * cp["resid_full2"],
            "resid_diff_causal_minus_full": 100 * (cp["residual"] - cp["resid_full2"]),
            "resid_final_pct": 100 * cp["resid_final"],
            "decomp_overfit": cp["resid_final"] > 1.0,
            "var_X": cp["r0"], "n": cp["n"],
        })
        print(f"  {ch:9s} tr={100*cp['trend']:5.1f} se={100*cp['seasonal']:5.1f} "
              f"re={100*cp['residual']:5.1f}  Δleak={100*(cp['residual']-cp['resid_full2']):+5.1f}"
              f"  re_final={100*cp['resid_final']:5.1f}")
    df = pd.DataFrame(rows)

    # ── Table A1 (appendix) ────────────────────────────────────────────────
    a1 = df[["channel", "band", "scoring_mode", "trend_pct", "seasonal_pct",
             "residual_pct", "resid_full_pct", "resid_diff_causal_minus_full",
             "resid_final_pct", "decomp_overfit"]].round(2)
    a1.to_csv(TAB / "A1_variance_partition.csv", index=False, encoding="utf-8-sig")

    # ── Fig 1.x: stacked bar, x ordered by process position ────────────────
    # display shares: clip the (occasionally <0 / >100 on hard channels) raw
    # stepwise shares to a proper [0,100] stack; honest raw numbers stay in the
    # bundle CSV + Table A1. A '‡' marks channels where the §1.1 harmonic fit is
    # residual-dominated / overfit (raw residual ≥ signal) → differentiated need.
    n = len(df)
    x = np.arange(n)
    disp = df[["trend_pct", "seasonal_pct", "residual_pct"]].clip(lower=0.0)
    disp = disp.div(disp.sum(axis=1).replace(0, np.nan), axis=0) * 100.0
    tr, se, re = (disp["trend_pct"].values, disp["seasonal_pct"].values,
                  disp["residual_pct"].values)
    # flag only the genuinely residual-dominated / §1.1-overfit channels
    flagged = ((df["residual_pct"] > 100) | df["decomp_overfit"]).values

    fig, ax = plt.subplots(figsize=(13.5, 5.8))
    ax.bar(x, tr, color=COMP["trend"], width=0.82, label="trend  m(t)", edgecolor="white", linewidth=0.4)
    ax.bar(x, se, bottom=tr, color=COMP["seasonal"], width=0.82, label="seasonal  s(t)", edgecolor="white", linewidth=0.4)
    ax.bar(x, re, bottom=tr + se, color=COMP["residual"], width=0.82, label="residual  e(t)", edgecolor="white", linewidth=0.4)
    for i in np.where(flagged)[0]:
        ax.text(i, 100.8, "‡", ha="center", va="bottom", fontsize=11, color="#B2182B")

    # band separators + labels
    band_edges = {}
    for i, ch in enumerate(df["channel"]):
        band_edges.setdefault(df["band"].iloc[i], [i, i])[1] = i
    for b in BAND_ORDER:
        if b not in band_edges:
            continue
        lo, hi = band_edges[b]
        if lo > 0:
            ax.axvline(lo - 0.5, color="0.35", lw=0.8, ls=":")
        ax.text((lo + hi) / 2, 105.5, b.replace("_", " "), ha="center", va="center",
                fontsize=8.6, fontweight="bold", color="0.15")

    ax.set_xticks(x)
    ax.set_xticklabels(df["channel"], rotation=60, ha="right", fontsize=7.6)
    ax.set_ylim(0, 110)
    ax.set_yticks([0, 20, 40, 60, 80, 100])
    ax.set_ylabel("Variance contribution (%)", fontsize=10)
    ax.set_xlim(-0.7, n - 0.3)
    ax.legend(loc="lower center", ncol=3, fontsize=8.8, framealpha=0.95,
              bbox_to_anchor=(0.5, 1.012))
    ax.grid(axis="y", alpha=0.3, lw=0.5)
    fig.suptitle("Figure 1.x  Causal variance-contribution profile along the process "
                 "(stepwise reduction; ‡ = residual-dominated / decomposition overfit)",
                 x=0.5, y=1.075, fontsize=10.5)
    ax.set_axisbelow(True)
    fig.subplots_adjust(left=0.06, right=0.99, top=0.86, bottom=0.20)
    out_png = FIG / "fig_1x_variance_partition_profile.png"
    fig.savefig(out_png, dpi=300, bbox_inches="tight")
    plt.close(fig)

    # ── figure data bundle (exactly what the bars encode) ──────────────────
    df.round(4).to_csv(PDATA / "fig_1x_variance_partition_profile.csv",
                       index=False, encoding="utf-8-sig")

    # ── console acceptance summary ─────────────────────────────────────────
    clos = (df["trend_pct"] + df["seasonal_pct"] + df["residual_pct"])
    print(f"[Work1] closure max|sum-100| = {float((clos - 100).abs().max()):.4f} %")
    print(f"[Work1] mean |causal-fullspan residual%| = "
          f"{float(df['resid_diff_causal_minus_full'].abs().mean()):.2f} pp "
          f"(max {float(df['resid_diff_causal_minus_full'].abs().max()):.2f} pp)")
    prof = df.groupby("band")[["trend_pct", "seasonal_pct", "residual_pct"]].mean().reindex(BAND_ORDER).round(1)
    print("[Work1] band-mean variance profile (%):")
    print(prof.to_string())
    print(f"[Work1] wrote {out_png.name}, A1_variance_partition.csv, fig data bundle")


if __name__ == "__main__":
    main()
