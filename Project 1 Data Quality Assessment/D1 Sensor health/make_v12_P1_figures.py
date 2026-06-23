"""make_v12_P1_figures.py — D1 v1.1 vs v1.2-P1 SCI comparison figures

Output: outputs/v12_P1/figures/  (PNG 600 dpi)
        outputs/v12_P1/data/     (CSV + XLSX)

Style spec:
  Font: Arial 8 pt (title 9 pt)
  Line width: main 1.0 pt, auxiliary 0.6 pt, axis 0.8 pt
  Colour-blind-safe: Wong 8-colour palette
  600 DPI PNG
"""
from __future__ import annotations
import sys, pickle, warnings
warnings.filterwarnings("ignore")
from pathlib import Path

_ROOT = Path(__file__).parent
sys.path.insert(0, str(_ROOT))

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.gridspec import GridSpec
from scipy.special import expit

# ─── SCI style constants ─────────────────────────────────────────────────────
FONT_SZ  = 8
TITLE_SZ = 9
TICK_SZ  = 7
LW_MAIN  = 1.0
LW_AUX   = 0.6
LW_AXIS  = 0.8
DPI      = 600

# Wong colour-blind-safe palette
WONG = {
    "black":  "#000000",
    "orange": "#E69F00",
    "sky":    "#56B4E9",
    "green":  "#009E73",
    "yellow": "#F0E442",
    "blue":   "#0072B2",
    "red":    "#D55E00",
    "pink":   "#CC79A7",
}
C_V11  = WONG["blue"]
C_P1   = WONG["orange"]
C_NORM = WONG["green"]
C_REFR = WONG["red"]
C_SUST = WONG["sky"]
C_RECV = WONG["yellow"]
C_RECD = WONG["pink"]

STATE_COLORS = {
    "Normal":            C_NORM,
    "Refractory":        C_REFR,
    "SustainedAnomaly":  C_SUST,
    "RecoveryCandidate": C_RECV,
    "Recovered":         C_RECD,
}
STATE_ORDER = ["Normal", "Refractory", "SustainedAnomaly", "RecoveryCandidate", "Recovered"]

FAULT_COLORS = {
    "Q_spike":  WONG["pink"],
    "Q_step":   WONG["red"],
    "Q_drift":  WONG["blue"],
    "Q_freeze": WONG["sky"],
    "Q_regime": WONG["orange"],
}


def sci_rc():
    plt.rcParams.update({
        "font.family":        "Arial",
        "font.size":          FONT_SZ,
        "axes.titlesize":     TITLE_SZ,
        "axes.labelsize":     FONT_SZ,
        "xtick.labelsize":    TICK_SZ,
        "ytick.labelsize":    TICK_SZ,
        "axes.linewidth":     LW_AXIS,
        "lines.linewidth":    LW_MAIN,
        "axes.spines.top":    False,
        "axes.spines.right":  False,
        "figure.dpi":         100,
        "savefig.dpi":        DPI,
        "savefig.bbox":       "tight",
        "savefig.pad_inches": 0.05,
        "legend.fontsize":    TICK_SZ,
        "legend.frameon":     False,
    })


def save_fig(fig, name: str, fig_dir: Path):
    p = fig_dir / f"{name}.png"
    fig.savefig(p, format="png")
    plt.close(fig)
    print(f"  [saved] {p.name}")


# ─── Load data ────────────────────────────────────────────────────────────────
def load_states():
    v11_path = _ROOT / "v11_state_v11.pkl"
    p1_path  = _ROOT / "v11_state.pkl"
    if not v11_path.exists():
        raise FileNotFoundError(f"v1.1 backup not found: {v11_path}")
    if not p1_path.exists():
        raise FileNotFoundError(f"v1.2-P1 state file not found: {p1_path}")
    with open(v11_path, "rb") as f:
        s11 = pickle.load(f)
    with open(p1_path, "rb") as f:
        sp1 = pickle.load(f)
    print(f"v1.1  D1 mean: {s11['D1_v11'].mean().mean():.3f}")
    print(f"v1.2-P1 D1 mean: {sp1['D1_v11'].mean().mean():.3f}")
    return s11, sp1


# ─── Fig 1: Parameter modification roadmap ───────────────────────────────────
def fig1_param_roadmap(fig_dir, data_dir):
    print("[Fig 1] Parameter roadmap...")
    rows = [
        ("P1-1", "step_confirmed logic",
         "(Q_24<=2.0) & (Q_36<=2.5)", "Q_step_final <= 2.0",
         "Align confirmed flag with Q_step_final; remove false triggers"),
        ("P1-2", "Q_step mapping (logistic)",
         "k=12.0, x0=0.30", "k=8.0, x0=0.40",
         "Shift midpoint right & soften slope; reduce over-penalisation of moderate KS"),
        ("P1-3a", "Refractory isolation period",
         "step_h = 24 h", "step_h = 48 h",
         "Extend lockout to break short-cycle Refractory trap"),
        ("P1-3b", "Event uniqueness interval",
         "min_sep = 12 h", "min_sep = 24 h",
         "Suppress redundant event IDs; lower spurious Refractory rate"),
        ("P1-4a", "RecoveryCandidate entry thresholds",
         "Q_step_min=3.2, Q_freeze_min=3.5", "Q_step_min=3.0, Q_freeze_min=3.0",
         "Relax entry to improve Recovery reachability"),
        ("P1-4b", "Recovery streak requirement",
         "min_streak = 24 h", "min_streak = 12 h",
         "Shorten confirmation window; increase Recovered transition rate"),
    ]
    df = pd.DataFrame(rows,
                      columns=["ID", "Parameter", "v1.1", "v1.2-P1", "Rationale"])
    df.to_csv(data_dir / "parameters_v11_v12.csv", index=False, encoding="utf-8-sig")
    df.to_excel(data_dir / "parameters_v11_v12.xlsx", index=False)

    sci_rc()
    fig, ax = plt.subplots(figsize=(9.5, 3.0))
    ax.axis("off")
    tbl = ax.table(cellText=df.values, colLabels=df.columns,
                   loc="center", cellLoc="left")
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(TICK_SZ)
    tbl.scale(1, 1.6)
    for (r, c_), cell in tbl.get_celld().items():
        cell.set_linewidth(0.5)
        if r == 0:
            cell.set_facecolor("#2166AC")
            cell.set_text_props(color="white", fontsize=FONT_SZ, fontweight="bold")
        elif r % 2 == 1:
            cell.set_facecolor("#EFF3FF")
        else:
            cell.set_facecolor("#FFFFFF")
    ax.set_title("D1 v1.2-P1 Parameter Modification Roadmap",
                 fontsize=TITLE_SZ, fontweight="bold", pad=6)
    save_fig(fig, "fig01_param_roadmap", fig_dir)


# ─── Fig 2: Q_step mapping curve comparison ──────────────────────────────────
def fig2_qstep_mapping(fig_dir, data_dir):
    print("[Fig 2] Q_step mapping curves...")
    x = np.linspace(0, 1.0, 500)

    def logistic_score(x, k, x0):
        return 1 + 4 * expit(-k * (x - x0))

    y11 = logistic_score(x, 12.0, 0.30)
    yp1 = logistic_score(x, 8.0,  0.40)

    pd.DataFrame({"ks_statistic": x,
                  "Q_step_v11 (k=12, x0=0.30)": y11,
                  "Q_step_P1  (k=8,  x0=0.40)": yp1
                  }).to_csv(data_dir / "fig_qstep_mapping_curve.csv", index=False)

    sci_rc()
    fig, ax = plt.subplots(figsize=(4.5, 3.0))
    ax.plot(x, y11, color=C_V11, lw=LW_MAIN, label="v1.1: k=12, x₀=0.30")
    ax.plot(x, yp1, color=C_P1,  lw=LW_MAIN, ls="--", label="v1.2-P1: k=8, x₀=0.40")
    ax.axvline(0.30, color=C_V11, lw=LW_AUX, ls=":")
    ax.axvline(0.40, color=C_P1,  lw=LW_AUX, ls=":")
    ax.axhline(3.0, color="gray", lw=LW_AUX, ls=":", alpha=0.6)
    ax.axhline(2.0, color="gray", lw=LW_AUX, ls=":", alpha=0.6)
    ax.fill_betweenx([1, 5], 0.30, 0.40, alpha=0.08, color="gray",
                     label="Midpoint shift")
    ax.set_xlabel("KS statistic", fontsize=FONT_SZ)
    ax.set_ylabel("Q_step score", fontsize=FONT_SZ)
    ax.set_xlim(0, 1.0)
    ax.set_ylim(1, 5)
    ax.set_yticks([1, 2, 3, 4, 5])
    ax.legend(loc="lower left", fontsize=TICK_SZ)
    ax.set_title("Q_step Mapping Curve Comparison (Logistic)",
                 fontsize=TITLE_SZ, fontweight="bold")
    save_fig(fig, "fig02_qstep_mapping", fig_dir)


# ─── Fig 3: Q_step distribution comparison (violin) ─────────────────────────
def fig3_qstep_distribution(s11, sp1, fig_dir, data_dir):
    print("[Fig 3] Q_step distribution...")
    channels = sp1["scored_channels"]
    rows = []
    for c in channels:
        for v in s11["subs_v1"]["Q_step"][c].dropna().values:
            rows.append({"channel": c, "version": "v1.1", "Q_step": v})
        for v in sp1["subs_v1"]["Q_step"][c].dropna().values:
            rows.append({"channel": c, "version": "v1.2-P1", "Q_step": v})
    pd.DataFrame(rows).to_csv(data_dir / "fig_qstep_distribution.csv", index=False)

    sci_rc()
    fig, ax = plt.subplots(figsize=(9.5, 3.2))
    pos11 = np.arange(len(channels)) * 2 - 0.4
    posp1 = np.arange(len(channels)) * 2 + 0.4

    for i, c in enumerate(channels):
        q11 = s11["subs_v1"]["Q_step"][c].dropna().values
        qp1 = sp1["subs_v1"]["Q_step"][c].dropna().values
        vp = ax.violinplot([q11], positions=[pos11[i]], widths=0.7,
                           showmedians=True, showextrema=False)
        for pc in vp["bodies"]:
            pc.set_facecolor(C_V11); pc.set_alpha(0.5)
        vp["cmedians"].set_color(C_V11); vp["cmedians"].set_lw(LW_MAIN)
        vp2 = ax.violinplot([qp1], positions=[posp1[i]], widths=0.7,
                            showmedians=True, showextrema=False)
        for pc in vp2["bodies"]:
            pc.set_facecolor(C_P1); pc.set_alpha(0.5)
        vp2["cmedians"].set_color(C_P1); vp2["cmedians"].set_lw(LW_MAIN)

    ax.axhline(3.0, color="gray", lw=LW_AUX, ls="--", alpha=0.7, label="Q = 3.0")
    ax.axhline(2.0, color="gray", lw=LW_AUX, ls=":",  alpha=0.7, label="Q = 2.0")
    ax.set_xticks(np.arange(len(channels)) * 2)
    ax.set_xticklabels(channels, rotation=45, ha="right", fontsize=TICK_SZ)
    ax.set_ylabel("Q_step score", fontsize=FONT_SZ)
    ax.set_ylim(1, 5)
    ax.set_yticks([1, 2, 3, 4, 5])
    p11 = mpatches.Patch(color=C_V11, alpha=0.5, label="v1.1  (k=12, x₀=0.30)")
    pp1 = mpatches.Patch(color=C_P1,  alpha=0.5, label="v1.2-P1 (k=8, x₀=0.40)")
    ax.legend(handles=[p11, pp1], loc="lower right", fontsize=TICK_SZ)
    ax.set_title("Q_step Distribution Comparison — Per-channel Violin Plot",
                 fontsize=TITLE_SZ, fontweight="bold")
    save_fig(fig, "fig03_qstep_distribution", fig_dir)


# ─── Fig 4: D1 score distribution comparison ─────────────────────────────────
def fig4_d1_distribution(s11, sp1, fig_dir, data_dir):
    print("[Fig 4] D1 distribution...")
    d11_all = s11["D1_v11"].values.flatten()
    dp1_all = sp1["D1_v11"].values.flatten()
    d11_all = d11_all[~np.isnan(d11_all)]
    dp1_all = dp1_all[~np.isnan(dp1_all)]

    grades = [1, 2, 3, 4, 5]

    def grade_dist(arr):
        counts = {g: np.sum((arr >= g) & (arr < g + 1)) / len(arr) * 100
                  for g in grades}
        counts[5] = np.sum(arr == 5) / len(arr) * 100
        return counts

    gd11 = grade_dist(d11_all)
    gdp1 = grade_dist(dp1_all)
    pd.DataFrame({"grade": grades,
                  "v1.1 (%)":    [gd11[g] for g in grades],
                  "v1.2-P1 (%)": [gdp1[g] for g in grades]
                  }).to_csv(data_dir / "fig_d1_grade_distribution.csv", index=False)

    sci_rc()
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(8.5, 3.0))

    bins = np.linspace(1, 5, 81)
    ax1.hist(d11_all, bins=bins, density=True, alpha=0.4, color=C_V11, label="v1.1")
    ax1.hist(dp1_all, bins=bins, density=True, alpha=0.4, color=C_P1,  label="v1.2-P1")
    ax1.axvline(np.mean(d11_all), color=C_V11, lw=LW_MAIN, ls="--",
                label=f"mean = {np.mean(d11_all):.3f}")
    ax1.axvline(np.mean(dp1_all), color=C_P1,  lw=LW_MAIN, ls="--",
                label=f"mean = {np.mean(dp1_all):.3f}")
    ax1.set_xlabel("D1 score", fontsize=FONT_SZ)
    ax1.set_ylabel("Probability density", fontsize=FONT_SZ)
    ax1.set_xlim(1, 5)
    ax1.legend(fontsize=TICK_SZ)
    ax1.set_title("D1 Score Density", fontsize=FONT_SZ, fontweight="bold")

    x = np.arange(len(grades))
    w = 0.35
    ax2.bar(x - w/2, [gd11[g] for g in grades], width=w, color=C_V11,
            alpha=0.7, label="v1.1")
    ax2.bar(x + w/2, [gdp1[g] for g in grades], width=w, color=C_P1,
            alpha=0.7, label="v1.2-P1")
    ax2.set_xticks(x)
    ax2.set_xticklabels([f"Grade {g}" for g in grades], fontsize=TICK_SZ)
    ax2.set_ylabel("Proportion (%)", fontsize=FONT_SZ)
    ax2.legend(fontsize=TICK_SZ)
    ax2.set_title("D1 Grade Distribution", fontsize=FONT_SZ, fontweight="bold")

    fig.suptitle("D1 Score Distribution Comparison (v1.1 vs v1.2-P1)",
                 fontsize=TITLE_SZ, fontweight="bold", y=1.02)
    save_fig(fig, "fig04_d1_distribution", fig_dir)


# ─── Fig 5: State machine coverage comparison ────────────────────────────────
def fig5_state_coverage(s11, sp1, fig_dir, data_dir):
    print("[Fig 5] State coverage...")
    channels = sp1["scored_channels"]
    rows = []
    for c in channels:
        sl11 = s11["state_log_dict"][c]["state_name"].value_counts(normalize=True) * 100
        slp1 = sp1["state_log_dict"][c]["state_name"].value_counts(normalize=True) * 100
        for st in STATE_ORDER:
            rows.append({"channel": c, "version": "v1.1",    "state": st, "pct": sl11.get(st, 0)})
            rows.append({"channel": c, "version": "v1.2-P1", "state": st, "pct": slp1.get(st, 0)})
    df_cov = pd.DataFrame(rows)
    df_cov.to_csv(data_dir / "fig_state_coverage.csv", index=False)

    sci_rc()
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 3.2), sharey=True)

    def plot_stacked(ax, state_data, title):
        bottoms = np.zeros(len(channels))
        for st in STATE_ORDER:
            vals = [state_data.get((c, st), 0) for c in channels]
            ax.bar(range(len(channels)), vals, bottom=bottoms,
                   color=STATE_COLORS[st], alpha=0.85, label=st, width=0.7)
            bottoms += np.array(vals)
        ax.set_xticks(range(len(channels)))
        ax.set_xticklabels(channels, rotation=45, ha="right", fontsize=TICK_SZ)
        ax.set_ylabel("State proportion (%)", fontsize=FONT_SZ)
        ax.set_ylim(0, 100)
        ax.set_title(title, fontsize=FONT_SZ, fontweight="bold")

    sd11 = {(r.channel, r.state): r.pct
            for r in df_cov[df_cov["version"] == "v1.1"].itertuples()}
    sdp1 = {(r.channel, r.state): r.pct
            for r in df_cov[df_cov["version"] == "v1.2-P1"].itertuples()}
    plot_stacked(ax1, sd11, "v1.1 State Distribution")
    plot_stacked(ax2, sdp1, "v1.2-P1 State Distribution")

    handles = [mpatches.Patch(color=STATE_COLORS[s], alpha=0.85, label=s)
               for s in STATE_ORDER]
    fig.legend(handles=handles, loc="upper center", ncol=5, fontsize=TICK_SZ,
               bbox_to_anchor=(0.5, 1.04))
    fig.suptitle("State Machine Coverage Comparison (Per Channel)",
                 fontsize=TITLE_SZ, fontweight="bold", y=1.08)
    save_fig(fig, "fig05_state_coverage", fig_dir)


# ─── Fig 6: State transition matrix comparison ───────────────────────────────
def fig6_transition_matrix(s11, sp1, fig_dir, data_dir):
    print("[Fig 6] Transition matrices...")

    def build_trans_matrix(state_dict, channels, states):
        mat = pd.DataFrame(0, index=states, columns=states)
        for c in channels:
            sl = state_dict[c]["state_name"]
            for fr, to in zip(sl[:-1], sl[1:]):
                if fr != to and fr in states and to in states:
                    mat.loc[fr, to] += 1
        return mat

    channels = sp1["scored_channels"]
    tm11 = build_trans_matrix(s11["state_log_dict"], channels, STATE_ORDER)
    tmp1 = build_trans_matrix(sp1["state_log_dict"], channels, STATE_ORDER)

    def norm_mat(m):
        s = m.sum(axis=1).replace(0, 1)
        return m.div(s, axis=0) * 100

    tm11_n = norm_mat(tm11)
    tmp1_n = norm_mat(tmp1)
    tm11_n.to_csv(data_dir / "fig_state_transition_v11.csv")
    tmp1_n.to_csv(data_dir / "fig_state_transition_p1.csv")

    sci_rc()
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9, 3.8))
    cmap = plt.cm.Blues
    short = ["Normal", "Refract.", "Sustained", "RecCand.", "Recovered"]

    def plot_tm(ax, mat, title):
        im = ax.imshow(mat.values, cmap=cmap, vmin=0, vmax=100, aspect="auto")
        ax.set_xticks(range(len(STATE_ORDER)))
        ax.set_yticks(range(len(STATE_ORDER)))
        ax.set_xticklabels(short, rotation=45, ha="right", fontsize=TICK_SZ)
        ax.set_yticklabels(short, fontsize=TICK_SZ)
        for i in range(len(STATE_ORDER)):
            for j in range(len(STATE_ORDER)):
                v = mat.values[i, j]
                if v > 0.5:
                    ax.text(j, i, f"{v:.0f}", ha="center", va="center",
                            fontsize=TICK_SZ, color="white" if v > 50 else "black")
        ax.set_xlabel("Target state", fontsize=FONT_SZ)
        ax.set_ylabel("Source state", fontsize=FONT_SZ)
        ax.set_title(title, fontsize=FONT_SZ, fontweight="bold")
        plt.colorbar(im, ax=ax, shrink=0.85, label="Transition probability (%)")

    plot_tm(ax1, tm11_n, "v1.1 State Transition Matrix (%)")
    plot_tm(ax2, tmp1_n, "v1.2-P1 State Transition Matrix (%)")
    fig.suptitle("State Transition Matrix Comparison",
                 fontsize=TITLE_SZ, fontweight="bold")
    save_fig(fig, "fig06_transition_matrix", fig_dir)


# ─── Fig 7: Dominant fault composition comparison ────────────────────────────
def fig7_dominant_fault(s11, sp1, fig_dir, data_dir):
    print("[Fig 7] Dominant fault composition...")
    channels    = sp1["scored_channels"]
    fault_names = ["Q_spike", "Q_step", "Q_drift", "Q_freeze", "Q_regime"]

    rows = []
    for c in channels:
        dom11 = s11["dominant_v11"][c].value_counts(normalize=True) * 100
        domp1 = sp1["dominant_v11"][c].value_counts(normalize=True) * 100
        for f in fault_names:
            rows.append({"channel": c, "version": "v1.1",    "fault": f, "pct": dom11.get(f, 0)})
            rows.append({"channel": c, "version": "v1.2-P1", "fault": f, "pct": domp1.get(f, 0)})
    df_fault = pd.DataFrame(rows)
    df_fault.to_csv(data_dir / "fig_dominant_fault_share.csv", index=False)

    sci_rc()
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 3.2), sharey=True)

    def plot_fault_stacked(ax, fault_data, title):
        bottoms = np.zeros(len(channels))
        for f in fault_names:
            vals = [fault_data.get((c, f), 0) for c in channels]
            ax.bar(range(len(channels)), vals, bottom=bottoms,
                   color=FAULT_COLORS[f], alpha=0.85, label=f, width=0.7)
            bottoms += np.array(vals)
        ax.set_xticks(range(len(channels)))
        ax.set_xticklabels(channels, rotation=45, ha="right", fontsize=TICK_SZ)
        ax.set_ylabel("Dominant fault share (%)", fontsize=FONT_SZ)
        ax.set_ylim(0, 100)
        ax.set_title(title, fontsize=FONT_SZ, fontweight="bold")

    fd11 = {(r.channel, r.fault): r.pct
            for r in df_fault[df_fault["version"] == "v1.1"].itertuples()}
    fdp1 = {(r.channel, r.fault): r.pct
            for r in df_fault[df_fault["version"] == "v1.2-P1"].itertuples()}
    plot_fault_stacked(ax1, fd11, "v1.1 Dominant Fault Decomposition")
    plot_fault_stacked(ax2, fdp1, "v1.2-P1 Dominant Fault Decomposition")

    handles = [mpatches.Patch(color=FAULT_COLORS[f], alpha=0.85, label=f)
               for f in fault_names]
    fig.legend(handles=handles, loc="upper center", ncol=5, fontsize=TICK_SZ,
               bbox_to_anchor=(0.5, 1.04))
    fig.suptitle("Dominant Fault Composition Comparison (Per Channel)",
                 fontsize=TITLE_SZ, fontweight="bold", y=1.08)
    save_fig(fig, "fig07_dominant_fault", fig_dir)


# ─── Fig 8: Veto and cap activation rate comparison ──────────────────────────
def fig8_veto_activation(s11, sp1, fig_dir, data_dir):
    print("[Fig 8] Veto activation rates...")
    channels  = sp1["scored_channels"]
    veto_cols = ["cooldown_active", "sustained_active",
                 "veto_freeze", "veto_regime", "veto3_signal_only"]
    rows = []
    for c in channels:
        vl11 = s11["veto_logs_v11"][c]
        vlp1 = sp1["veto_logs_v11"][c]
        for col in veto_cols:
            r11 = vl11[col].sum() / len(vl11) * 100 if col in vl11.columns else 0
            rp1 = vlp1[col].sum() / len(vlp1) * 100 if col in vlp1.columns else 0
            rows.append({"channel": c, "veto": col,
                         "v1.1 (%)": r11, "v1.2-P1 (%)": rp1})
    df_veto = pd.DataFrame(rows)
    df_veto.to_csv(data_dir / "fig_veto_activation.csv", index=False)

    veto_mean = df_veto.groupby("veto")[["v1.1 (%)", "v1.2-P1 (%)"]].mean()

    sci_rc()
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9, 3.2))

    x = np.arange(len(veto_cols))
    w = 0.35
    ax1.bar(x - w/2, [veto_mean.loc[col, "v1.1 (%)"]    for col in veto_cols],
            width=w, color=C_V11, alpha=0.7, label="v1.1")
    ax1.bar(x + w/2, [veto_mean.loc[col, "v1.2-P1 (%)"] for col in veto_cols],
            width=w, color=C_P1,  alpha=0.7, label="v1.2-P1")
    xlabels = ["cooldown", "sustained", "veto_freeze", "veto_regime", "veto3"]
    ax1.set_xticks(x)
    ax1.set_xticklabels(xlabels, rotation=30, ha="right", fontsize=TICK_SZ)
    ax1.set_ylabel("Mean activation rate (%)", fontsize=FONT_SZ)
    ax1.legend(fontsize=TICK_SZ)
    ax1.set_title("Global Veto Activation Rate", fontsize=FONT_SZ, fontweight="bold")

    cd11 = [df_veto[(df_veto.channel == c) & (df_veto.veto == "cooldown_active")]["v1.1 (%)"].values[0]
            for c in channels]
    cdp1 = [df_veto[(df_veto.channel == c) & (df_veto.veto == "cooldown_active")]["v1.2-P1 (%)"].values[0]
            for c in channels]
    x2 = np.arange(len(channels))
    ax2.bar(x2 - w/2, cd11, width=w, color=C_V11, alpha=0.7, label="v1.1")
    ax2.bar(x2 + w/2, cdp1, width=w, color=C_P1,  alpha=0.7, label="v1.2-P1")
    ax2.set_xticks(x2)
    ax2.set_xticklabels(channels, rotation=45, ha="right", fontsize=TICK_SZ)
    ax2.set_ylabel("Refractory activation rate (%)", fontsize=FONT_SZ)
    ax2.legend(fontsize=TICK_SZ)
    ax2.set_title("Refractory Rate Per Channel", fontsize=FONT_SZ, fontweight="bold")

    fig.suptitle("Veto Mechanism Activation Rate Comparison (v1.1 vs v1.2-P1)",
                 fontsize=TITLE_SZ, fontweight="bold")
    save_fig(fig, "fig08_veto_activation", fig_dir)


# ─── Fig 9: Typical channel time-series case study ───────────────────────────
def fig9_case_timeseries(s11, sp1, fig_dir, data_dir):
    print("[Fig 9] Case study time series...")
    case_channels = ["DO_2_3", "DO_1_4", "ORP_1_3"]

    sci_rc()
    fig = plt.figure(figsize=(12, 7.5))
    gs  = GridSpec(3, 2, figure=fig, hspace=0.55, wspace=0.3)

    ts_rows = []
    for row_i, c in enumerate(case_channels):
        d11  = s11["D1_v11"][c]
        dp1  = sp1["D1_v11"][c]
        slp1 = sp1["state_log_dict"][c]["state_name"]
        qs11 = s11["subs_v1"]["Q_step"][c]
        qsp1 = sp1["subs_v1"]["Q_step"][c]

        for t in dp1.index:
            ts_rows.append({"channel": c, "time": t,
                            "D1_v11": d11.get(t, np.nan),
                            "D1_P1":  dp1.get(t, np.nan),
                            "Q_step_v11": qs11.get(t, np.nan),
                            "Q_step_P1":  qsp1.get(t, np.nan)})

        # Left column: D1 time series
        ax_d1 = fig.add_subplot(gs[row_i, 0])
        ax_d1.plot(d11.index, d11.values, color=C_V11, lw=0.8, alpha=0.75, label="v1.1")
        ax_d1.plot(dp1.index, dp1.values, color=C_P1,  lw=0.8, alpha=0.75,
                   label="v1.2-P1", ls="--")
        state_vals = slp1.values
        times      = slp1.index
        for k in range(len(times) - 1):
            st = state_vals[k]
            if st in STATE_COLORS:
                ax_d1.axvspan(times[k], times[k + 1],
                              color=STATE_COLORS[st], alpha=0.12, linewidth=0)
        ax_d1.axhline(3.0, color="gray", lw=LW_AUX, ls=":", alpha=0.6)
        ax_d1.set_ylabel("D1 score", fontsize=FONT_SZ)
        ax_d1.set_ylim(1, 5)
        ax_d1.set_title(f"{c} — D1 Time Series", fontsize=FONT_SZ, fontweight="bold")
        if row_i == 0:
            ax_d1.legend(fontsize=TICK_SZ, loc="lower right")
        ax_d1.tick_params(axis="x", labelsize=TICK_SZ, rotation=20)

        # Right column: Q_step time series
        ax_qs = fig.add_subplot(gs[row_i, 1])
        ax_qs.plot(qs11.index, qs11.values, color=C_V11, lw=0.8, alpha=0.75,
                   label="Q_step v1.1")
        ax_qs.plot(qsp1.index, qsp1.values, color=C_P1,  lw=0.8, alpha=0.75,
                   label="Q_step v1.2-P1", ls="--")
        ax_qs.axhline(2.0, color=C_REFR, lw=LW_AUX, ls=":", alpha=0.7,
                      label="Confirmed threshold = 2.0")
        ax_qs.axhline(3.0, color="gray",  lw=LW_AUX, ls=":", alpha=0.5)
        ax_qs.set_ylabel("Q_step score", fontsize=FONT_SZ)
        ax_qs.set_ylim(1, 5)
        ax_qs.set_title(f"{c} — Q_step Time Series", fontsize=FONT_SZ, fontweight="bold")
        if row_i == 0:
            ax_qs.legend(fontsize=TICK_SZ, loc="lower right")
        ax_qs.tick_params(axis="x", labelsize=TICK_SZ, rotation=20)

    pd.DataFrame(ts_rows).to_csv(data_dir / "fig_case_timeseries.csv", index=False)

    state_legend = [mpatches.Patch(color=STATE_COLORS[s], alpha=0.3, label=s)
                    for s in STATE_ORDER]
    fig.legend(handles=state_legend, loc="lower center", ncol=5, fontsize=TICK_SZ,
               bbox_to_anchor=(0.5, -0.01))
    fig.suptitle("Typical Channel Time-Series Case Study (background = v1.2-P1 state)",
                 fontsize=TITLE_SZ, fontweight="bold")
    save_fig(fig, "fig09_case_timeseries", fig_dir)


# ─── Fig 10: Q_regime reference baseline sensitivity ─────────────────────────
def fig10_regime_sensitivity(sp1, fig_dir, data_dir):
    print("[Fig 10] Q_regime sensitivity...")
    channels = sp1["scored_channels"]
    qr_all   = sp1["subs_v1"]["Q_regime"]

    rows = []
    for c in channels:
        q = qr_all[c].dropna()
        rows.append({
            "channel":     c,
            "mean":        q.mean(),
            "median":      q.median(),
            "p05":         q.quantile(0.05),
            "p25":         q.quantile(0.25),
            "p75":         q.quantile(0.75),
            "p95":         q.quantile(0.95),
            "pct_below_2": (q < 2.0).mean() * 100,
            "pct_below_3": (q < 3.0).mean() * 100,
        })
    df_reg = pd.DataFrame(rows)
    df_reg.to_csv(data_dir / "fig_regime_sensitivity.csv", index=False)

    sci_rc()
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9, 3.2))

    data_list = [qr_all[c].dropna().values for c in channels]
    bp = ax1.boxplot(data_list, labels=channels, patch_artist=True,
                     medianprops=dict(color="black", linewidth=1.0),
                     whiskerprops=dict(linewidth=LW_AUX),
                     capprops=dict(linewidth=LW_AUX),
                     flierprops=dict(marker=".", ms=2, alpha=0.3))
    for patch in bp["boxes"]:
        patch.set_facecolor(WONG["sky"]); patch.set_alpha(0.6)
    ax1.axhline(2.0, color=C_REFR, lw=LW_AUX, ls="--", alpha=0.7,
                label="Veto threshold = 2.0")
    ax1.axhline(3.0, color="gray",  lw=LW_AUX, ls=":",  alpha=0.6)
    ax1.set_xticklabels(channels, rotation=45, ha="right", fontsize=TICK_SZ)
    ax1.set_ylabel("Q_regime score", fontsize=FONT_SZ)
    ax1.set_ylim(1, 5)
    ax1.set_yticks([1, 2, 3, 4, 5])
    ax1.legend(fontsize=TICK_SZ)
    ax1.set_title("Q_regime Distribution Per Channel",
                  fontsize=FONT_SZ, fontweight="bold")

    x = np.arange(len(channels))
    w = 0.35
    ax2.bar(x - w/2, df_reg["pct_below_2"].values, width=w, color=C_REFR,
            alpha=0.7, label="Q_regime < 2.0 (Veto)")
    ax2.bar(x + w/2, df_reg["pct_below_3"].values, width=w, color=WONG["orange"],
            alpha=0.7, label="Q_regime < 3.0")
    ax2.set_xticks(x)
    ax2.set_xticklabels(channels, rotation=45, ha="right", fontsize=TICK_SZ)
    ax2.set_ylabel("Trigger rate (%)", fontsize=FONT_SZ)
    ax2.legend(fontsize=TICK_SZ)
    ax2.set_title("Q_regime Veto Trigger Rate Per Channel",
                  fontsize=FONT_SZ, fontweight="bold")

    fig.suptitle("Q_regime Reference Baseline Sensitivity Analysis (v1.2-P1)",
                 fontsize=TITLE_SZ, fontweight="bold")
    save_fig(fig, "fig10_regime_sensitivity", fig_dir)


# ─── Main ─────────────────────────────────────────────────────────────────────
def main():
    import time
    t0 = time.time()
    fig_dir  = _ROOT / "outputs" / "v12_P1" / "figures"
    data_dir = _ROOT / "outputs" / "v12_P1" / "data"
    fig_dir.mkdir(parents=True, exist_ok=True)
    data_dir.mkdir(parents=True, exist_ok=True)

    print("=" * 65)
    print("D1 v1.1 vs v1.2-P1 — SCI comparison figures")
    print(f"  figures → {fig_dir}")
    print(f"  data    → {data_dir}")
    print("=" * 65)

    s11, sp1 = load_states()

    fig1_param_roadmap(fig_dir, data_dir)
    fig2_qstep_mapping(fig_dir, data_dir)
    fig3_qstep_distribution(s11, sp1, fig_dir, data_dir)
    fig4_d1_distribution(s11, sp1, fig_dir, data_dir)
    fig5_state_coverage(s11, sp1, fig_dir, data_dir)
    fig6_transition_matrix(s11, sp1, fig_dir, data_dir)
    fig7_dominant_fault(s11, sp1, fig_dir, data_dir)
    fig8_veto_activation(s11, sp1, fig_dir, data_dir)
    fig9_case_timeseries(s11, sp1, fig_dir, data_dir)
    fig10_regime_sensitivity(sp1, fig_dir, data_dir)

    print(f"\nDone! Total time: {time.time() - t0:.1f}s")
    print(f"Figures: {fig_dir}")
    print(f"Data:    {data_dir}")


if __name__ == "__main__":
    main()
