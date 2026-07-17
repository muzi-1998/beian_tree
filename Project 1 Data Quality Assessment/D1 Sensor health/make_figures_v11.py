"""make_figures_v11.py — SCI-quality v1.1 figure suite.

Produces:
    Updated v1.1 versions of Fig 1-11 from STRICT V1 (where applicable)
    NEW v1.1 figures: V12-V18 highlighting state machine, signal-only Veto-3,
    DO/ORP-only scoring scope, and v1.1 vs STRICT V1 comparisons.

Style: Nature/Cell/Water Research/EST publication grade, 600 dpi PNG.
"""
from __future__ import annotations
import sys, pickle
from pathlib import Path
ROOT = Path(__file__).parent
sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.gridspec as gridspec
from matplotlib.colors import LinearSegmentedColormap, BoundaryNorm
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle, Patch, FancyArrowPatch
from publication_style import (PALETTE as C, STATE_COLORS as STATE_COL,
                               annotate_data_label,
                               configure_publication_style, finalize_figure,
                               save_publication_bundle)

OUT = ROOT / "outputs" / "figures"
OUT.mkdir(parents=True, exist_ok=True)
PLOTDATA = ROOT / "outputs" / "plot_data"
PLOTDATA.mkdir(parents=True, exist_ok=True)

# ─── SCI publication style ─────────────────────────────────────────────────
plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans", "Liberation Sans"],
    "font.size": 8.5,
    "axes.titlesize": 9.5,
    "axes.labelsize": 9,
    "xtick.labelsize": 8,
    "ytick.labelsize": 8,
    "legend.fontsize": 7.5,
    "legend.frameon": True,
    "legend.framealpha": 0.92,
    "legend.edgecolor": "0.4",
    "figure.dpi": 150,
    "savefig.dpi": 600,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.04,
    "axes.linewidth": 0.8,
    "axes.grid": True,
    "axes.grid.which": "major",
    "grid.alpha": 0.16,
    "grid.linewidth": 0.4,
    "lines.linewidth": 1.0,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.titleweight": "bold",
    "axes.titlelocation": "left",
    "axes.titlepad": 6,
    "xtick.major.size": 3,
    "xtick.minor.size": 1.5,
    "ytick.major.size": 3,
    "ytick.minor.size": 1.5,
    "xtick.major.width": 0.8,
    "ytick.major.width": 0.8,
    "pdf.fonttype": 42,
    "ps.fonttype": 42,
    "svg.fonttype": "none",
})
configure_publication_style()

# ─────────────────────────────────────────────────────────────────────────────
print("Loading v1.1 state ...")
with open(ROOT / "v11_state.pkl", "rb") as f:
    S = pickle.load(f)
FIGURE_VERSION = S.get("algorithm_version", "unknown")
print(f"  D1_v1_scored mean = {S['D1_v1_scored'].mean().mean():.3f}")
print(f"  D1_v11      mean  = {S['D1_v11'].mean().mean():.3f}")
print(f"  Scored channels: {len(S['scored_channels'])}, Support: {len(S['support_channels'])}")

SCORED = S["scored_channels"]
SUPPORT = S["support_channels"]
D1_v1 = S["D1_v1_scored"]
D1_v11 = S["D1_v11"]
delta_df = S["delta_df"]
DO_CH = [c for c in SCORED if c.startswith("DO_")]
ORP_CH = [c for c in SCORED if c.startswith("ORP_")]


def _finish_axes(fig):
    finalize_figure(fig)


def save(fig, name, plot_data: dict = None):
    save_publication_bundle(fig, OUT / name, version_label=FIGURE_VERSION)
    plt.close(fig)
    if plot_data is not None:
        with pd.ExcelWriter(PLOTDATA / f"{name}_data.xlsx", engine="openpyxl") as w:
            pd.DataFrame([{"run_id": S.get("run_id"), "algorithm_version": FIGURE_VERSION}]).to_excel(
                w, sheet_name="figure_metadata", index=False
            )
            for k, v in plot_data.items():
                if isinstance(v, pd.DataFrame):
                    v.to_excel(w, sheet_name=k[:31], index=True)
                elif isinstance(v, pd.Series):
                    v.to_frame(k).to_excel(w, sheet_name=k[:31], index=True)
                elif isinstance(v, dict):
                    pd.DataFrame(v).to_excel(w, sheet_name=k[:31], index=True)
    print(f"  [OK] {name}.png + .svg + .pdf + .tiff")


# ============================================================================
# Figure V12 (HERO) — D1 v1.1 vs STRICT V1 comprehensive comparison
# ============================================================================
print("[V12] D1 v1.1 vs STRICT V1 — hero comparison ...")
fig = plt.figure(figsize=(7.2, 6.7))
gs = gridspec.GridSpec(3, 3, figure=fig, hspace=0.62, wspace=0.32,
                        height_ratios=[1.2, 1.0, 1.0])

# (a) Per-channel mean D1: V1 vs v1.1 (DO/ORP only)
ax = fig.add_subplot(gs[0, :2])
df_sorted = delta_df.sort_values("delta_D1")
y = np.arange(len(df_sorted))
for i, row in enumerate(df_sorted.itertuples()):
    clr = C["red"] if row.delta_D1 < 0 else C["green"]
    ax.plot([row.D1_v1, row.D1_v11], [i, i], "-",
            color=clr, lw=2.0, alpha=0.65, solid_capstyle="round")
    ax.plot(row.D1_v1, i, "o", color=C["gray"], ms=6.5, zorder=3,
            markerfacecolor="white", markeredgecolor=C["gray"], markeredgewidth=1.2)
    ax.plot(row.D1_v11, i, "o", color=clr, ms=7.5, zorder=4,
            markerfacecolor=clr, markeredgecolor="white", markeredgewidth=0.8)
ax.set_yticks(y); ax.set_yticklabels(df_sorted["channel"].tolist(), fontsize=7.8)
ax.axvline(3.0, color="0.5", ls=":", lw=0.8, alpha=0.7)
ax.set_xlabel(r"Mean $D_1$ score (1 = poor — 5 = excellent)", fontsize=9)
ax.set_title("(a) Per-channel mean $D_1$", loc="left")
leg_h = [Line2D([], [], marker="o", color=C["gray"], ms=7,
                  linestyle="", markerfacecolor="white", label="STRICT V1"),
          Line2D([], [], marker="o", color=C["green"], ms=7,
                  linestyle="", markerfacecolor=C["green"], label="v1.1 (Δ ≥ 0)"),
          Line2D([], [], marker="o", color=C["red"], ms=7,
                  linestyle="", markerfacecolor=C["red"], label="v1.1 (Δ < 0; SustainedAnomaly cap)"),
          Line2D([], [], color="0.5", ls=":", lw=0.8, label="grade boundary D1 = 3")]
ax.legend(handles=leg_h, loc="upper left", fontsize=6.6, ncol=2, frameon=False)
# data-driven x-limits: means are ~3.7–4.5; keep the grade boundary (3.0) visible
# but never clip the markers (the old fixed (2.0, 3.6) clipped every channel).
_va = np.r_[df_sorted["D1_v1"].values, df_sorted["D1_v11"].values]
ax.set_xlim(min(2.9, float(_va.min()) - 0.15), float(_va.max()) + 0.20)
ax.grid(axis="x", alpha=0.18, lw=0.4)

# (b) Delta bar
ax = fig.add_subplot(gs[0, 2])
clrs = [C["red"] if d < 0 else C["green"] for d in df_sorted["delta_D1"]]
ax.barh(np.arange(len(df_sorted)), df_sorted["delta_D1"], color=clrs,
         edgecolor="white", linewidth=0.6, alpha=0.88)
ax.set_yticks(np.arange(len(df_sorted)))
ax.set_yticklabels(df_sorted["channel"].tolist(), fontsize=7.8)
ax.axvline(0, color="0.3", lw=0.8)
mean_d = float(df_sorted["delta_D1"].mean())
ax.axvline(mean_d, color=C["amber"], ls="--", lw=1.0,
            label=f"mean Δ = {mean_d:+.4f}")
ax.set_xlabel(r"$\Delta D_1$  (v1.1 − STRICT V1)", fontsize=9)
ax.set_title("(b)  $\\Delta D_1$ distribution", loc="left")
ax.legend(loc="upper right", fontsize=7.5)

# (c) State distribution stacked (one bar per channel)
ax = fig.add_subplot(gs[1, :])
state_pcts = pd.DataFrame({
    "Normal":            [delta_df.set_index("channel").at[c, "Normal_pct"] for c in SCORED],
    "Refractory":        [delta_df.set_index("channel").at[c, "Refractory_pct"] for c in SCORED],
    "BaselinePending":   [delta_df.set_index("channel").at[c, "BaselinePending_pct"] for c in SCORED],
    "SustainedAnomaly":  [delta_df.set_index("channel").at[c, "Sustained_pct"] for c in SCORED],
    "RecoveryCandidate": [delta_df.set_index("channel").at[c, "RecCand_pct"] for c in SCORED],
    "Recovered":         [delta_df.set_index("channel").at[c, "Recovered_state_occupancy_pct"] for c in SCORED],
}, index=SCORED)
xs = np.arange(len(SCORED))
bottom = np.zeros(len(SCORED))
non_normal_states = [
    "Refractory", "BaselinePending", "SustainedAnomaly",
    "RecoveryCandidate", "Recovered",
]
for s_name in non_normal_states:
    vals = state_pcts[s_name].values
    ax.bar(xs, vals, bottom=bottom, color=STATE_COL[s_name],
            edgecolor="white", linewidth=0.4, label=s_name, alpha=0.92)
    bottom += vals
ax.set_xticks(xs); ax.set_xticklabels(SCORED, rotation=45, ha="right", fontsize=7.8)
ax.set_ylabel("Non-normal occupancy (%)", fontsize=9)
ax.set_ylim(0, max(2.0, float(bottom.max()) * 1.28))
ax.set_title("(c) Non-normal causal state occupancy", loc="left")
ax.legend(loc="upper right", ncol=3, fontsize=6.4, frameon=False)

# (d) Daily median trajectory
ax = fig.add_subplot(gs[2, :2])
d1v1_d = D1_v1.resample("1D").median().median(axis=1)
d1v11_d = D1_v11.resample("1D").median().median(axis=1)
ax.plot(d1v1_d.index, d1v1_d.values, color=C["gray"], lw=1.2,
        label="STRICT V1 (DO/ORP only, daily median)", alpha=0.85)
ax.plot(d1v11_d.index, d1v11_d.values, color=C["blue"], lw=1.4,
        label="v1.1", alpha=0.92)
ax.fill_between(d1v1_d.index, d1v1_d.values, d1v11_d.values,
                 where=d1v11_d.values >= d1v1_d.values,
                 alpha=0.18, color=C["green"], label="v1.1 ≥ V1")
ax.fill_between(d1v1_d.index, d1v1_d.values, d1v11_d.values,
                 where=d1v11_d.values < d1v1_d.values,
                 alpha=0.18, color=C["red"], label="v1.1 < V1")
ax.set_ylabel(r"Median daily $D_1$  (across DO/ORP)", fontsize=9)
ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
plt.setp(ax.get_xticklabels(), rotation=25, ha="right")
ax.set_title("(d)  Daily median $D_1$ trajectory", loc="left")
# add top headroom so the legend sits above the trajectory (was overlapping it)
_dmin = float(min(d1v1_d.min(), d1v11_d.min()))
ax.set_ylim(_dmin - 0.15, 5.3)
ax.legend(loc="upper right", fontsize=7.5, ncol=2, framealpha=0.92)

# (e) Weekly delta heatmap
ax = fig.add_subplot(gs[2, 2])
d1v1_w = D1_v1.resample("7D").median()
d1v11_w = D1_v11.resample("7D").median()
delta_w = d1v11_w - d1v1_w
im = ax.imshow(delta_w.T.values, cmap="RdBu_r", aspect="auto",
                vmin=-0.30, vmax=0.30, interpolation="nearest")
ax.set_yticks(np.arange(len(delta_w.columns)))
ax.set_yticklabels(delta_w.columns.tolist(), fontsize=7)
ax.set_xticks(np.arange(0, len(delta_w), 4))
ax.set_xticklabels([t.strftime("%y-%m") for t in delta_w.index[::4]],
                    rotation=70, fontsize=7)
ax.set_title("(e)  Weekly $\\Delta D_1$ heatmap", loc="left")
cbar = plt.colorbar(im, ax=ax, fraction=0.045, pad=0.02)
cbar.set_label(r"$\Delta D_1$", fontsize=8)
cbar.ax.tick_params(labelsize=7)
ax.grid(False)

fig.suptitle("Figure V12. Final D1 versus STRICT V1", fontsize=11.5,
              fontweight="bold", y=1.0)
save(fig, "FigV12_v11_vs_strictV1_hero",
      plot_data={"per_channel_delta": delta_df,
                  "state_pcts": state_pcts,
                  "daily_median": pd.DataFrame({"v1": d1v1_d, "v11": d1v11_d}),
                  "weekly_delta": delta_w})


# ============================================================================
# Figure V13 — causal six-state recovery machine in action
# ============================================================================
print("[V13] causal six-state recovery machine ...")
fig = plt.figure(figsize=(7.2, 6.7))
gs = gridspec.GridSpec(4, 1, figure=fig, hspace=0.80,
                        height_ratios=[1.2, 1.0, 1.0, 1.2])

# Pick the worst sensor for illustration: DO_2_3
target = "DO_2_3"
state_log = S["state_log_dict"][target]
qd_v1 = S["subs_v1"]["Q_drift"][target]
qd_eff = S["Q_drift_eff_dict"][target]
qs = S["subs_v1"]["Q_step"][target]
qr = S["subs_v1"]["Q_regime"][target]
qf = S["subs_v1"]["Q_freeze"][target]
d1v1 = D1_v1[target]
d1v11 = D1_v11[target]
idx = state_log.index

# (a) Sub-scores time-series with state shading
ax = fig.add_subplot(gs[0])
# State background
state_arr = state_log["state_name"].values
for s_name, col in STATE_COL.items():
    mask = state_arr == s_name
    if mask.any():
        ax.fill_between(idx, 0, 1, where=mask, alpha=0.22, color=col,
                        transform=ax.get_xaxis_transform(), step="mid",
                        label=s_name)
ax.plot(idx, qs, color=C["blue"], lw=0.45, alpha=0.85, label="$Q_{step}$")
ax.plot(idx, qr, color=C["green"], lw=0.45, alpha=0.85, label="$Q_{regime}$")
ax.plot(idx, qf, color=C["amber"], lw=0.45, alpha=0.85, label="$Q_{freeze}$")
ax.axhline(2.0, color=C["red"], ls=":", lw=0.7, alpha=0.7)
ax.set_ylim(1, 5.2)
ax.set_ylabel("Sub-score", fontsize=9)
ax.set_title(f"(a)  Sub-score timeseries with state-machine shading — {target}", loc="left")
# legend in the lower band (sub-scores live at 3.5–5; the 1–2.5 band is sparse)
ax.legend(loc="lower center", ncol=4, fontsize=6.8, framealpha=0.92)
ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))

# (b) Q_drift v1 vs Q_drift_eff (showing α-thaw effect)
ax = fig.add_subplot(gs[1])
for s_name, col in STATE_COL.items():
    mask = state_arr == s_name
    if mask.any():
        ax.fill_between(idx, 0, 1, where=mask, alpha=0.18, color=col,
                        transform=ax.get_xaxis_transform(), step="mid")
ax.plot(idx, qd_v1, color=C["gray"], lw=0.45, alpha=0.7,
        label="$Q_{drift}$ — STRICT V1 (raw)")
ax.plot(idx, qd_eff, color=C["purple"], lw=0.6, alpha=0.92,
        label="$Q_{drift}^{eff}$ — v1.1 (after α-thaw)")
ax.axhline(3.0, color=C["amber"], ls="--", lw=0.7, alpha=0.6,
            label="neutral 3.0 (during Refractory)")
ax.set_ylim(1, 5.2)
ax.set_ylabel("$Q_{drift}$ score", fontsize=9)
ax.set_title(r"(b)  $Q_{\rm drift}$  vs  $Q_{\rm drift}^{\rm eff}$  (α-thaw effect)", loc="left")
ax.legend(loc="lower center", ncol=3, fontsize=7.2, framealpha=0.92)
ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))

# (c) α(t) timeline + recovery_streak
ax = fig.add_subplot(gs[2])
ax2 = ax.twinx()
ax.fill_between(idx, 0, state_log["alpha"].values, color=C["teal"], alpha=0.35,
                 label=r"α(t) — drift mixing")
ax.plot(idx, state_log["alpha"].values, color=C["teal"], lw=0.5, alpha=0.85)
ax.set_ylabel(r"α(t)  (1 = neutral, 0 = full new baseline)", fontsize=9, color=C["teal"])
ax.set_ylim(-0.05, 1.05)
ax.tick_params(axis="y", colors=C["teal"])
ax2.plot(idx, state_log["recovery_streak"].values, color=C["red"], lw=0.55,
          alpha=0.85, label="recovery_streak (h)")
ax2.set_ylabel("recovery_streak (h)", fontsize=9, color=C["red"])
ax2.tick_params(axis="y", colors=C["red"])
ax2.set_ylim(0, max(state_log["recovery_streak"].max(), 25))
ax.set_title("(c)  α-thaw schedule + recovery_streak counter", loc="left")
ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))

# (d) D1 final
ax = fig.add_subplot(gs[3])
for s_name, col in STATE_COL.items():
    mask = state_arr == s_name
    if mask.any():
        ax.fill_between(idx, 0, 1, where=mask, alpha=0.18, color=col,
                        transform=ax.get_xaxis_transform(), step="mid")
ax.plot(idx, d1v1, color=C["gray"], lw=0.55, alpha=0.7,
        label=f"$D_1$ STRICT V1 (mean={float(d1v1.mean()):.3f})")
ax.plot(idx, d1v11, color=C["blue"], lw=0.65, alpha=0.92,
        label=f"$D_1$ v1.1 (mean={float(d1v11.mean()):.3f})")
ax.axhline(2.5, color=C["red"], ls="--", lw=0.7, alpha=0.7,
            label="SustainedAnomaly / Veto-3 cap = 2.5")
ax.axhline(3.0, color="0.5", ls=":", lw=0.7, alpha=0.6, label="grade boundary")
ax.set_ylim(1.5, 4.5)
ax.set_ylabel("$D_1$ total", fontsize=9)
ax.set_title(f"(d)  Final $D_1$ — {target} ({len(state_log[state_log.state_name=='Refractory'])} h Refractory, "
              f"{len(state_log[state_log.state_name=='SustainedAnomaly'])} h Sustained)",
              loc="left")
ax.legend(loc="lower left", fontsize=7.2, framealpha=0.92)
ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))

fig.suptitle("Figure V13.  Causal six-state recovery machine — DO_2_3 case study",
              fontsize=11.5, fontweight="bold", y=1.0)
save(fig, "FigV13_state_machine_DO_2_3",
      plot_data={"state_log": state_log,
                  "Q_drift_compare": pd.DataFrame({
                      "Q_drift_v1": qd_v1, "Q_drift_eff_v11": qd_eff})})


# ============================================================================
# Figure V14 — Signal-only Veto-3 and event_id timeline
# ============================================================================
print("[V14] Signal-only Veto-3 ...")
fig = plt.figure(figsize=(7.2, 6.7))
gs = gridspec.GridSpec(3, 2, figure=fig, hspace=0.90, wspace=0.36,
                        height_ratios=[1.0, 1.0, 1.0])

# (a) Per-channel state distribution heatmap
ax = fig.add_subplot(gs[0, 0])
state_dist_all = pd.DataFrame(index=SCORED,
                                columns=["Normal","Refractory","BaselinePending","SustainedAnomaly",
                                          "RecoveryCandidate","Recovered"], dtype=float)
for c in SCORED:
    sl = S["state_log_dict"][c]["state_name"]
    for s in state_dist_all.columns:
        state_dist_all.at[c, s] = (sl == s).mean() * 100
im = ax.imshow(state_dist_all.values, cmap="YlOrRd", aspect="auto", vmin=0, vmax=100)
ax.set_yticks(np.arange(len(SCORED))); ax.set_yticklabels(SCORED, fontsize=6.2)
ax.set_xticks(np.arange(len(state_dist_all.columns)))
state_tick_labels = ["Normal", "Refract.", "Pending", "Sustained", "Candidate", "Recovered"]
ax.set_xticklabels(state_tick_labels, rotation=28, ha="right", fontsize=6.5)
for i in range(len(SCORED)):
    for j in range(len(state_dist_all.columns)):
        v = state_dist_all.values[i, j]
        ax.text(j, i, f"{v:.0f}", ha="center", va="center",
                  fontsize=7, color="white" if v > 60 else "black")
cbar = plt.colorbar(im, ax=ax, fraction=0.045, pad=0.02)
cbar.set_label("% of timeline", fontsize=8); cbar.ax.tick_params(labelsize=7)
ax.set_title("(a)  Per-channel state distribution", loc="left")
ax.grid(False)

# (b) Veto-3 signal-only activation rate per channel
ax = fig.add_subplot(gs[0, 1])
v3 = {c: S["veto_logs_v11"][c]["veto3_signal_only"].mean() * 100 for c in SCORED}
v3 = pd.Series(v3).sort_values()
clrs_v3 = [C["red"] if v > 1.5 else (C["amber"] if v > 0.5 else C["gray"])
            for v in v3.values]
ax.barh(np.arange(len(v3)), v3.values, color=clrs_v3, edgecolor="white",
         linewidth=0.5, alpha=0.88)
ax.set_yticks(np.arange(len(v3)))
ax.set_yticklabels(v3.index.tolist(), fontsize=6.2)
ax.scatter(v3.values, np.arange(len(v3)), s=16, color=C["gray"], zorder=3)
ax.set_xlim(-0.002, max(0.10, float(v3.max()) * 1.15))
if float(v3.max()) == 0:
    ax.text(0.05, (len(v3) - 1) / 2, "0% for all 14 channels",
            ha="center", va="center", fontsize=7.5,
            bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.75})
ax.set_xlabel("Veto-3 signal-only activation rate (%)", fontsize=9)
ax.set_title("(b)  Signal-only Veto-3 activation per channel", loc="left")

# (c) State transition counts per channel
ax = fig.add_subplot(gs[1, 0])
trans_counts = pd.DataFrame(
    0, index=SCORED,
    columns=[f"to:{state}" for state in [
        "Refractory", "BaselinePending", "SustainedAnomaly",
        "RecoveryCandidate", "Recovered", "Normal",
    ]],
    dtype=int,
)
for transition in S["transitions_all"]:
    column = f"to:{transition['to_state']}"
    if transition["sensor_id"] in trans_counts.index and column in trans_counts.columns:
        trans_counts.at[transition["sensor_id"], column] += 1
xs = np.arange(len(SCORED)); bottom = np.zeros(len(SCORED))
for i, col_name in enumerate(trans_counts.columns):
    values = trans_counts[col_name].values
    ax.bar(xs, values, bottom=bottom, width=0.72,
            label=col_name.replace("to:", ""),
            color=STATE_COL[col_name.replace("to:", "")],
            edgecolor="white", linewidth=0.4, alpha=0.88)
    bottom += values
ax.set_xticks(xs); ax.set_xticklabels(SCORED, rotation=48, ha="right", fontsize=6.5)
ax.set_ylabel("# transitions", fontsize=9)
ax.set_title("(c)  State-transition counts (entire 8.4 mo)", loc="left")
ax.legend(loc="upper left", fontsize=5.9, ncol=2, frameon=False)

# (d) Veto rule overlap heat (for one representative sensor)
ax = fig.add_subplot(gs[1, 1])
target = "DO_2_3"
vlog = S["veto_logs_v11"][target]
overlap = pd.DataFrame({
    "veto_freeze":   vlog["veto_freeze"],
    "veto_regime":   vlog["veto_regime"],
    "veto3_signal":  vlog["veto3_signal_only"],
    "sustained":     vlog["sustained_active"],
    "Refractory":    vlog["cooldown_active"],
})
co_mat = overlap.T.dot(overlap) / len(overlap)
im = ax.imshow(co_mat.values, cmap="OrRd", aspect="equal", vmin=0, vmax=co_mat.values.max())
ax.set_xticks(np.arange(len(co_mat))); ax.set_yticks(np.arange(len(co_mat)))
ax.set_xticklabels(co_mat.columns.tolist(), rotation=30, ha="right", fontsize=7.5)
ax.set_yticklabels(co_mat.index.tolist(), fontsize=7.5)
for i in range(len(co_mat)):
    for j in range(len(co_mat)):
        v = co_mat.values[i, j]
        ax.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=7,
                  color="white" if v > co_mat.values.max() * 0.5 else "black")
cbar = plt.colorbar(im, ax=ax, fraction=0.045, pad=0.02)
cbar.set_label("co-activation rate", fontsize=8); cbar.ax.tick_params(labelsize=7)
ax.set_title(f"(d)  Veto/state co-activation matrix ({target})", loc="left")
ax.grid(False)

# (e) Comparison: V1 cooldown estimate vs v1.1 Refractory rate
ax = fig.add_subplot(gs[2, :])
# V1 cooldown estimate: 48h timer triggered by Q_step≤2 OR Q_regime≤2
def v1_cooldown_estimate(qs_, qr_):
    n = len(qs_)
    cd = np.zeros(n, dtype=bool)
    last_trig = -10000
    for i in range(n):
        if (qs_.iat[i] <= 2 or qr_.iat[i] <= 2):
            last_trig = i
        if i - last_trig <= 48:
            cd[i] = True
    return cd.mean()
cd_v1_est = {c: v1_cooldown_estimate(S["subs_v1"]["Q_step"][c],
                                       S["subs_v1"]["Q_regime"][c]) * 100
              for c in SCORED}
refr_v11 = {c: (S["state_log_dict"][c]["state_name"] == "Refractory").mean() * 100
             for c in SCORED}
sust_v11 = {c: (S["state_log_dict"][c]["state_name"] == "SustainedAnomaly").mean() * 100
             for c in SCORED}
xs = np.arange(len(SCORED)); bw = 0.27
ax.bar(xs - bw, [cd_v1_est[c] for c in SCORED], bw, color=C["gray"],
        edgecolor="white", alpha=0.88,
        label="STRICT V1: 48h cooldown timer (estimate)")
ax.bar(xs, [refr_v11[c] for c in SCORED], bw, color=STATE_COL["Refractory"],
        edgecolor="white", alpha=0.88,
        label="v1.1: Refractory (event-triggered, fixed)")
ax.bar(xs + bw, [sust_v11[c] for c in SCORED], bw, color=STATE_COL["SustainedAnomaly"],
        edgecolor="white", alpha=0.88,
        label="v1.1: SustainedAnomaly (with α-thaw, recoverable)")
ax.set_xticks(xs); ax.set_xticklabels(SCORED, rotation=45, ha="right", fontsize=7.8)
ax.set_ylabel("State % of timeline", fontsize=9)
ax.set_title("(e) Timer baseline versus causal event states",
              loc="left")
ax.legend(loc="upper right", fontsize=6.5, ncol=1, frameon=False)

fig.suptitle("Figure V14.  Signal-only Veto-3 and six-state machine audit",
              fontsize=11.5, fontweight="bold", y=1.0)
save(fig, "FigV14_veto3_state_audit",
      plot_data={"state_dist": state_dist_all,
                  "veto3_rate": v3.to_frame("rate_pct"),
                  "transitions": trans_counts,
                  "v1_v11_state_compare": pd.DataFrame({
                      "v1_cooldown_pct": cd_v1_est,
                      "v11_refractory_pct": refr_v11,
                      "v11_sustained_pct": sust_v11})})


# ============================================================================
# Figure V15 — PELT change-points and event_id timeline
# ============================================================================
print("[V15] PELT batch change-points ...")
fig = plt.figure(figsize=(7.2, 5.8))
gs = gridspec.GridSpec(3, 2, figure=fig, hspace=0.55, wspace=0.28,
                        height_ratios=[1.4, 1.1, 1.0])

# (a) PELT CPs overlay on residual + state machine on DO_2_3
ax = fig.add_subplot(gs[0, :])
target = "DO_2_3"
resid = S["resid_h"][target]
sl = S["state_log_dict"][target]
ax.plot(resid.index, resid.values, color=C["gray"], lw=0.4, alpha=0.55,
        label=f"{target} hourly residual")
sm = resid.rolling(48, center=True, min_periods=12).mean()
ax.plot(sm.index, sm.values, color=C["blue"], lw=1.0, alpha=0.92, label="48h rolling mean")
# PELT CPs
cps = S["pelt_results"][target]
for ev in cps:
    ax.axvline(ev["timestamp"], color=C["red"], lw=0.5, alpha=0.4)
# State transitions where event_id changes
transitions_target = [tr for tr in S["transitions_all"] if tr["sensor_id"] == target
                       and tr["to_state"] == "Refractory"]
for tr in transitions_target:
    ax.axvline(tr["ts"], color=C["green"], lw=0.9, alpha=0.7)
ax.plot([], [], color=C["red"], lw=0.7, label=f"PELT CPs (n={len(cps)})")
ax.plot([], [], color=C["green"], lw=1.0,
        label=f"new-event-id Refractory triggers (n={len(transitions_target)})")
ax.set_ylabel(f"{target} residual (mg/L)", fontsize=9)
ax.set_title(f"(a)  PELT change-points + new-event-id Refractory triggers — {target}",
              loc="left")
ax.legend(loc="upper right", fontsize=7.5)
ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))

# (b) PELT CP count per scored channel
ax = fig.add_subplot(gs[1, 0])
ch_cp_counts = {c: len(S["pelt_results"][c]) for c in SCORED}
df_cp = pd.Series(ch_cp_counts).sort_values()
nonzero = df_cp.nlargest(8).sort_values()
ax.barh(np.arange(len(nonzero)), nonzero.values, color=C["teal"],
         edgecolor="white", alpha=0.88, linewidth=0.5)
ax.set_yticks(np.arange(len(nonzero)))
ax.set_yticklabels(nonzero.index.tolist(), fontsize=6.8)
ax.set_xlabel("# PELT change-points (lookback 720h, stride 336h)", fontsize=9)
ax.set_title("(b)  PELT CP count per scored channel", loc="left")

# (c) Refractory triggers vs PELT CPs
ax = fig.add_subplot(gs[1, 1])
refr_triggers = {c: 0 for c in SCORED}
for tr in S["transitions_all"]:
    if tr["to_state"] == "Refractory" and tr["sensor_id"] in refr_triggers:
        refr_triggers[tr["sensor_id"]] += 1
df_cmp = pd.DataFrame({"PELT CPs": ch_cp_counts,
                        "Refractory triggers": refr_triggers}).reindex(SCORED)
point_colors = [C["blue"] if c.startswith("DO_") else C["rose"] for c in SCORED]
ax.scatter(df_cmp["PELT CPs"], df_cmp["Refractory triggers"], s=72,
           color=point_colors, edgecolor="white", alpha=0.88, linewidths=0.8)
label_channels = set(
    df_cmp.assign(information=df_cmp.max(axis=1))
    .nlargest(6, "information").index
)
for c in SCORED:
    if c not in label_channels:
        continue
    xy = (df_cmp.at[c, "PELT CPs"], df_cmp.at[c, "Refractory triggers"])
    annotate_data_label(ax, c, xy, xytext=(4, 5), fontsize=6.2,
                        ha="left", va="bottom")
mx = max(df_cmp.max()) + 5
ax.plot([0, mx], [0, mx], "k--", lw=0.6, alpha=0.5, label="1:1")
ax.set_xlabel("PELT CPs", fontsize=9)
ax.set_ylabel("Refractory triggers", fontsize=9)
ax.set_title("(c)  PELT CPs vs Refractory triggers (event-uniqueness filter)",
              loc="left")
ax.legend(fontsize=7.5)

# (d) Monthly distribution of new event_id triggers
ax = fig.add_subplot(gs[2, :])
ts_list = [tr["ts"] for tr in S["transitions_all"] if tr["to_state"] == "Refractory"]
if ts_list:
    ts_series = pd.Series(1, index=pd.DatetimeIndex(ts_list))
    monthly = ts_series.resample("ME").sum()
    ax.bar(monthly.index, monthly.values, width=20, color=C["amber"],
            edgecolor="white", alpha=0.88, linewidth=0.6)
    for x, y in zip(monthly.index, monthly.values):
        ax.text(x, y + 4, str(int(y)), ha="center", va="bottom",
                  fontsize=7.5, fontweight="bold")
ax.set_ylabel("# event triggers / month", fontsize=9)
ax.set_title("(d)  Refractory trigger density timeline (all channels)", loc="left")
ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
ax.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
plt.setp(ax.get_xticklabels(), rotation=45, ha="right")

fig.suptitle("Figure V15.  PELT batch calibration + event-uniqueness filter",
              fontsize=11.5, fontweight="bold", y=1.0)
save(fig, "FigV15_pelt_event_id",
      plot_data={"cp_count": pd.Series(ch_cp_counts).to_frame("cp_count"),
                  "refractory_triggers": pd.Series(refr_triggers).to_frame("triggers"),
                  "pelt_DO_2_3": pd.DataFrame(S["pelt_results"]["DO_2_3"])})

print(f"\n[done] First 4 v1.1 figures complete.\nNext: v16-18 + updated v1-11.\n")
try:
    from generate_expert_report_v11 import maybe_update_report
    maybe_update_report()
except Exception as exc:
    print(f"[auto-report] skipped: {exc}")
