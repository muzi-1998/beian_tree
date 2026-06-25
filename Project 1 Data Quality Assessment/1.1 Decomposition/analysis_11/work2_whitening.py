"""analysis_11/work2_whitening.py — Work 2: residual-whitening efficacy,
presented on THREE separate tracks by scoring_mode (never mixed):

  iid            : e(t) → η(t) before/after ACF, windowed Ljung–Box pass-rate,
                   mabsacf effect size (PACF in the appendix).
  autocorr_aware : NO before/after; residual ACF slow decay + broadband spectral
                   roll-off + n_eff/n  → "cannot be whitened, not a whitening
                   failure" (near unit root; mean-reverting ORP whitens fine).
  floor_freeze   : excluded from the whitening assessment, table-flagged only.

Ljung–Box is reported as a WINDOWED pass-rate + effect size (mabsacf), never a
single global p — at n≈3.7e5 a one-shot LB rejects almost surely (over-powered);
the windowed pass-rate + effect size is the honest large-n statement.

Outputs
  outputs/figures/fig_2a_iid_acf_before_after.png
  outputs/figures/fig_2b_nearUR_acf_spectrum.png
  outputs/figures/fig_1x_whiteness_control_gradient.png   (mechanism: along-process)
  outputs/figures/fig_A2_pacf_order.png                   (appendix)
  outputs/tables/T1_whitening_main.csv                    (33ch main table)
  outputs/plot_data/*.csv                                 (each figure's data)
"""
from __future__ import annotations
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.signal import welch
from statsmodels.tsa.stattools import acf, pacf

from common import (TAB, FIG, PDATA, OKABE_ITO, MODE_COLOR, PROCESS_ORDER,
                    POS_BAND, BAND_ORDER, load_manifest, get_residual,
                    get_innovation, setup_style)

NLAGS = 60
REP_IID = ["DO_1_2", "DO_1_3", "ORP_1_2", "ORP_2_1", "inf_COD", "eff_COD"]
NEAR_UR = ["DO_1_1", "DO_2_1", "DO_2_2"]
VERM = OKABE_ITO["vermillion"]; BLUE = OKABE_ITO["blue"]; GREY = OKABE_ITO["gray"]


def _acf(s: pd.Series, nlags=NLAGS) -> np.ndarray:
    v = s.dropna().values.astype(float)
    return acf(v, nlags=nlags, fft=True)


# ── main table ────────────────────────────────────────────────────────────────
def build_main_table(man: pd.DataFrame) -> pd.DataFrame:
    w = pd.read_csv(TAB / "whitening_before_after.csv", encoding="utf-8-sig").set_index("channel")
    rows = []
    for ch in PROCESS_ORDER:
        m, wr = man.loc[ch], w.loc[ch]
        rows.append({
            "channel": ch, "band": POS_BAND[ch], "scoring_mode": m["scoring_mode"],
            "innov_kind": m["innov_kind"],
            "acf1_resid": wr["acf1_resid"], "acf1_innov": wr["acf1_innov"],
            "mabsacf_resid": wr["mabsacf_resid"], "mabsacf_innov": wr["mabsacf_innov"],
            "mabsacf_drop_pct": 100 * (1 - wr["mabsacf_innov"] / wr["mabsacf_resid"])
                                 if wr["mabsacf_resid"] else np.nan,
            "lb_pass_resid": wr["lb_passrate_resid"], "lb_pass_innov": wr["lb_passrate_innov"],
            "adf_p": wr["adf_p_innov"], "adf_reject": wr["adf_reject_innov"],
            "kpss_p": wr["kpss_p_innov"],
            "n_eff_ratio": m["n_eff_ratio"],
        })
    df = pd.DataFrame(rows)
    df.round(4).to_csv(TAB / "T1_whitening_main.csv", index=False, encoding="utf-8-sig")
    return df


# ── Fig A: iid before/after ACF ─────────────────────────────────────────────────
def fig_iid_acf(man: pd.DataFrame, tab: pd.DataFrame):
    R = len(REP_IID)
    fig, axes = plt.subplots(R, 2, figsize=(8.6, 1.45 * R + 0.8), sharex=True, sharey=True)
    bundle = {}
    for i, ch in enumerate(REP_IID):
        e_acf = _acf(get_residual(ch)); n_acf = _acf(get_innovation(ch))
        bundle[f"{ch}_resid"] = e_acf; bundle[f"{ch}_innov"] = n_acf
        row = tab.set_index("channel").loc[ch]
        n_eff = max(int(row["n_eff_ratio"] * 3e5), 30)
        band = 1.96 / np.sqrt(n_eff)
        for j, (a, title, lab) in enumerate([(e_acf, "residual  e(t)", "resid"),
                                             (n_acf, "innovation  η(t)", "innov")]):
            ax = axes[i][j]
            ax.axhspan(-band, band, color=GREY, alpha=0.25, lw=0)
            ax.vlines(range(len(a)), 0, a, color=BLUE, lw=0.9)
            ax.axhline(0, color="0.4", lw=0.6)
            ax.set_ylim(-0.25, 1.02)
            if i == 0:
                ax.set_title(title, fontsize=10, fontweight="bold")
            if j == 0:
                ax.set_ylabel(ch, fontsize=9, fontweight="bold")
            mab = row["mabsacf_innov"] if lab == "innov" else row["mabsacf_resid"]
            ax.text(0.96, 0.88, f"mabsacf = {mab:.3f}", transform=ax.transAxes,
                    ha="right", va="top", fontsize=8, fontweight="bold", color="0.12",
                    bbox=dict(boxstyle="round,pad=0.18", fc="white", ec="0.7", alpha=0.85))
            if j == 1:
                ax.text(0.96, 0.60, f"−{row['mabsacf_drop_pct']:.0f}%",
                        transform=ax.transAxes, ha="right", va="top",
                        fontsize=10.5, color=OKABE_ITO["green"], fontweight="bold")
    for ax in axes[-1]:
        ax.set_xlabel("lag", fontsize=9)
    # explicit, bold legend (was only buried in the suptitle text)
    import matplotlib.patches as mp
    handles = [plt.Line2D([], [], color=BLUE, lw=2.2, label="ACF at lag k"),
               mp.Patch(color=GREY, alpha=0.25, label="±1.96/√n_eff white-noise band"),
               plt.Line2D([], [], color=OKABE_ITO["green"], lw=0, marker="$-94\\%$",
                          markersize=22, label="mabsacf reduction e→η")]
    fig.legend(handles=handles, loc="lower center", bbox_to_anchor=(0.5, 0.952),
               ncol=3, fontsize=9, frameon=True, framealpha=0.95, prop={"weight": "bold"})
    fig.suptitle("Figure A.  iid track — residual e(t) → innovation η(t) ACF (shared y)",
                 fontsize=11, fontweight="bold", y=1.0)
    fig.tight_layout(rect=(0, 0, 1, 0.93))
    fig.savefig(FIG / "fig_2a_iid_acf_before_after.png", dpi=300, bbox_inches="tight")
    plt.close(fig)
    pd.DataFrame(bundle).to_csv(PDATA / "fig_2a_iid_acf_before_after.csv",
                                index_label="lag", encoding="utf-8-sig")


# ── Fig B: near-unit-root residual ACF (slow decay) + spectrum (no peak) ───────
def fig_nearur(man: pd.DataFrame, tab: pd.DataFrame):
    fig, axes = plt.subplots(len(NEAR_UR), 2, figsize=(9.2, 1.7 * len(NEAR_UR) + 0.8))
    bundle_acf = {}; bundle_spec = {}
    for i, ch in enumerate(NEAR_UR):
        e = get_residual(ch).dropna()
        a = _acf(e, nlags=120); bundle_acf[ch] = a
        row = tab.set_index("channel").loc[ch]
        # ACF slow decay
        ax = axes[i][0]
        ax.vlines(range(len(a)), 0, a, color=BLUE, lw=0.7)
        ax.axhline(0, color="0.4", lw=0.6)
        ax.set_ylim(0, 1.02); ax.set_ylabel(ch, fontsize=8.5)
        ax.text(0.96, 0.9, f"acf1={row['acf1_resid']:.3f}\nn_eff/n={row['n_eff_ratio']:.3f}",
                transform=ax.transAxes, ha="right", va="top", fontsize=7, color="0.25")
        if i == 0:
            ax.set_title("residual ACF — slow (near-unit-root) decay", fontsize=9)
        if i == len(NEAR_UR) - 1:
            ax.set_xlabel("lag", fontsize=8.5)
        # spectrum — broadband red-noise roll-off, NO dominant peak
        ax = axes[i][1]
        v = e.values.astype(float)
        f, P = welch(v, fs=1.0, nperseg=min(8192, len(v)//4), detrend="linear")
        with np.errstate(divide="ignore"):
            per = np.where(f > 0, 1.0 / f, np.nan)
        msk = f > 0
        ax.loglog(per[msk], P[msk], color=OKABE_ITO["spectrum"], lw=0.8)
        ax.set_ylabel("PSD", fontsize=8); ax.grid(True, which="both", alpha=0.25, lw=0.4)
        if i == 0:
            ax.set_title("spectrum — broadband roll-off, no limit-cycle peak", fontsize=9)
        if i == len(NEAR_UR) - 1:
            ax.set_xlabel("period (min)", fontsize=8.5)
        if i == 0:
            bundle_spec["period_min"] = per[msk]
        bundle_spec[f"{ch}_PSD"] = np.interp(bundle_spec["period_min"], per[msk][::-1], P[msk][::-1]) \
            if i > 0 else P[msk]
    fig.suptitle("Figure B.  autocorr_aware track: near-unit-root residuals — NOT a whitening failure "
                 "(mean-reverting ORP whitens fine; cf. Fig A)", fontsize=9.6, y=0.999)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(FIG / "fig_2b_nearUR_acf_spectrum.png", dpi=300, bbox_inches="tight")
    plt.close(fig)
    pd.DataFrame(bundle_acf).to_csv(PDATA / "fig_2b_nearUR_acf.csv", index_label="lag", encoding="utf-8-sig")
    pd.DataFrame(bundle_spec).to_csv(PDATA / "fig_2b_nearUR_spectrum.csv", index=False, encoding="utf-8-sig")


# ── Fig 1.x mechanism: whiteness gradient vs scoring_mode along the process ─────
def fig_gradient(tab: pd.DataFrame):
    df = tab.set_index("channel").loc[PROCESS_ORDER].reset_index()
    n = len(df); x = np.arange(n)
    fig, ax = plt.subplots(figsize=(13.5, 4.6))
    colors = [MODE_COLOR[m] for m in df["scoring_mode"]]
    ax.bar(x, df["mabsacf_innov"].values, color=colors, width=0.82, edgecolor="white", linewidth=0.4)
    ax.axhline(0.1, color=VERM, lw=1.0, ls="--", label="near-white guide (mabsacf=0.10)")
    band_edges = {}
    for i, ch in enumerate(df["channel"]):
        band_edges.setdefault(POS_BAND[ch], [i, i])[1] = i
    ymax = float(df["mabsacf_innov"].max()) * 1.18
    for b in BAND_ORDER:
        lo, hi = band_edges[b]
        if lo > 0:
            ax.axvline(lo - 0.5, color="0.35", lw=0.8, ls=":")
        ax.text((lo + hi) / 2, ymax * 0.97, b.replace("_", " "), ha="center", va="top",
                fontsize=8.2, fontweight="bold", color="0.15")
    ax.set_xticks(x); ax.set_xticklabels(df["channel"], rotation=60, ha="right", fontsize=7.6)
    ax.set_ylim(0, ymax); ax.set_xlim(-0.7, n - 0.3)
    ax.set_ylabel("residual autocorr after whitening\n(mabsacf of η/robust_z)", fontsize=9)
    import matplotlib.patches as mp
    handles = [mp.Patch(color=MODE_COLOR[k], label=k) for k in ["iid", "autocorr_aware", "floor_freeze"]]
    handles.append(plt.Line2D([], [], color=VERM, ls="--", label="near-white guide (0.10)"))
    ax.legend(handles=handles, loc="upper right", ncol=2, fontsize=8.2, framealpha=0.95)
    fig.suptitle("Figure 1.x  Along-process whiteness gradient — clean innovations downstream, "
                 "un-whitenable near-unit-root DO at the aerobic front (control/integrator fingerprint)",
                 fontsize=9.8, y=1.0)
    fig.subplots_adjust(left=0.07, right=0.99, top=0.9, bottom=0.2)
    fig.savefig(FIG / "fig_1x_whiteness_control_gradient.png", dpi=300, bbox_inches="tight")
    plt.close(fig)
    df[["channel", "band", "scoring_mode", "mabsacf_innov", "n_eff_ratio"]].round(4).to_csv(
        PDATA / "fig_1x_whiteness_control_gradient.csv", index=False, encoding="utf-8-sig")


# ── Fig A2 PACF (appendix) ─────────────────────────────────────────────────────
def fig_pacf(man: pd.DataFrame):
    reps = ["DO_1_2", "ORP_1_2", "inf_COD", "DO_1_1"]
    fig, axes = plt.subplots(2, 2, figsize=(8.6, 5.0))
    bundle = {}
    for ax, ch in zip(axes.ravel(), reps):
        v = get_residual(ch).dropna().values.astype(float)
        p = pacf(v[:50000], nlags=40, method="ywm")
        bundle[ch] = p
        band = 1.96 / np.sqrt(min(len(v), 50000))
        ax.axhspan(-band, band, color=GREY, alpha=0.25, lw=0)
        ax.vlines(range(len(p)), 0, p, color=BLUE, lw=0.9)
        ax.axhline(0, color="0.4", lw=0.6)
        ax.set_title(f"{ch}  ({man.loc[ch, 'scoring_mode']})", fontsize=9)
        ax.set_xlabel("lag", fontsize=8); ax.set_ylabel("PACF", fontsize=8)
    fig.suptitle("Figure A2.  Residual PACF of representative channels (order-selection support)", fontsize=10)
    fig.tight_layout(rect=(0, 0, 1, 0.96))
    fig.savefig(FIG / "fig_A2_pacf_order.png", dpi=300, bbox_inches="tight")
    plt.close(fig)
    pd.DataFrame(bundle).to_csv(PDATA / "fig_A2_pacf.csv", index_label="lag", encoding="utf-8-sig")


def main():
    setup_style()
    man = load_manifest()
    tab = build_main_table(man)
    fig_iid_acf(man, tab)
    fig_nearur(man, tab)
    fig_gradient(tab)
    fig_pacf(man)
    # acceptance summary
    iid = tab[tab.scoring_mode == "iid"]
    print(f"[Work2] iid channels: mean mabsacf drop = {iid['mabsacf_drop_pct'].mean():.1f}% "
          f"| LB pass {iid['lb_pass_resid'].mean():.3f}→{iid['lb_pass_innov'].mean():.3f}")
    ur = tab[tab.scoring_mode == "autocorr_aware"]
    print(f"[Work2] autocorr_aware: acf1 {ur['acf1_resid'].mean():.3f}, n_eff/n {ur['n_eff_ratio'].mean():.4f}, "
          f"adf_reject={ur['adf_reject'].tolist()}")
    print("[Work2] wrote T1_whitening_main.csv + 4 figures + data bundles")


if __name__ == "__main__":
    main()
