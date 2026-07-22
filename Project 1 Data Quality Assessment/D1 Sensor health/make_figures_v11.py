"""Generate current-result D1 validation figures V12-V15.

The manuscript-facing figures report only the locked current pipeline. Legacy
scores remain available in internal audit workbooks, but are not plotted as a
scientific comparator because they do not provide independent ground truth.
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
                               positive_data_ylim, save_publication_bundle)

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
print(f"  Final D1 mean = {S['D1_v11'].mean().mean():.3f}")
print(f"  Scored channels: {len(S['scored_channels'])}, Support: {len(S['support_channels'])}")

SCORED = S["scored_channels"]
SUPPORT = S["support_channels"]
D1_v11 = S["D1_v11"]
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


def moving_block_mean_ci(series, block_days=7, n_boot=2000, seed=42):
    """Return mean and a serial-dependence-aware 95% moving-block CI."""
    values = pd.Series(series).dropna().to_numpy(dtype=float)
    if values.size == 0:
        return np.nan, np.nan, np.nan
    if values.size <= block_days:
        mean = float(values.mean())
        return mean, mean, mean
    starts = np.arange(values.size - block_days + 1)
    n_blocks = int(np.ceil(values.size / block_days))
    rng = np.random.default_rng(seed)
    boot = np.empty(n_boot, dtype=float)
    for i in range(n_boot):
        sampled_starts = rng.choice(starts, size=n_blocks, replace=True)
        sampled = np.concatenate([
            values[start:start + block_days] for start in sampled_starts
        ])[:values.size]
        boot[i] = sampled.mean()
    return (
        float(values.mean()),
        float(np.quantile(boot, 0.025)),
        float(np.quantile(boot, 0.975)),
    )


# ============================================================================
# Figure V12 (HERO) — current D1 operating profile
# ============================================================================
print("[V12] Current D1 operating profile ...")
daily_by_channel = D1_v11.resample("1D").mean()
channel_rows = []
for channel_idx, channel in enumerate(SCORED):
    mean, ci_low, ci_high = moving_block_mean_ci(
        daily_by_channel[channel], seed=42 + channel_idx
    )
    values = D1_v11[channel].dropna()
    channel_rows.append({
        "channel": channel,
        "analyte": "DO" if channel.startswith("DO_") else "ORP",
        "mean_D1": mean,
        "ci95_low": ci_low,
        "ci95_high": ci_high,
        "median_D1": float(values.median()),
        "iqr_low": float(values.quantile(0.25)),
        "iqr_high": float(values.quantile(0.75)),
        "D1_lt_3_pct": float((values < 3.0).mean() * 100),
        "D1_lt_2_5_pct": float((values < 2.5).mean() * 100),
    })
channel_summary = pd.DataFrame(channel_rows).sort_values("mean_D1")

state_names = [
    "Normal", "Refractory", "BaselinePending", "SustainedAnomaly",
    "RecoveryCandidate", "Recovered",
]
state_pcts = pd.DataFrame(index=SCORED, columns=state_names, dtype=float)
for channel in SCORED:
    states = S["state_log_dict"][channel]["state_name"]
    for state_name in state_names:
        state_pcts.at[channel, state_name] = float((states == state_name).mean() * 100)

fig = plt.figure(figsize=(7.2, 7.0))
gs = gridspec.GridSpec(
    3, 2, figure=fig, hspace=0.82, wspace=0.50,
    height_ratios=[1.30, 1.00, 1.12],
)
fig.subplots_adjust(top=0.92, bottom=0.08, left=0.11, right=0.97)

# (a) Per-channel mean and serial-dependence-aware uncertainty
ax = fig.add_subplot(gs[0, 0])
y = np.arange(len(channel_summary))
for i, row in enumerate(channel_summary.itertuples()):
    color = C["blue"] if row.analyte == "DO" else C["green"]
    marker = "o" if row.analyte == "DO" else "s"
    ax.errorbar(
        row.mean_D1, i,
        xerr=[[row.mean_D1 - row.ci95_low], [row.ci95_high - row.mean_D1]],
        fmt=marker, ms=4.8, color=color, ecolor=color, elinewidth=0.9,
        capsize=2.0, markeredgecolor="white", markeredgewidth=0.5, zorder=3,
    )
ax.axvline(3.0, color="0.45", ls=":", lw=0.8, label="$D_1=3$")
ax.set_yticks(y)
ax.set_yticklabels(
    channel_summary["channel"].astype(str).str.replace("-", "_", regex=False).tolist(),
    fontsize=7.2, fontfamily="Arial",
)
ax.set_xlabel(r"Mean hourly $D_1$ (95% 7-d block-bootstrap CI)", fontsize=8.4)
ax.set_title("(a) Channel-level final score", loc="left")
ax.set_xlim(
    min(2.90, float(channel_summary["ci95_low"].min()) - 0.08),
    min(5.03, float(channel_summary["ci95_high"].max()) + 0.08),
)
ax.legend(
    handles=[
        Line2D([], [], marker="o", color=C["blue"], linestyle="", label="DO"),
        Line2D([], [], marker="s", color=C["green"], linestyle="", label="ORP"),
        Line2D([], [], color="0.45", ls=":", lw=0.8, label="$D_1=3$"),
    ],
    loc="lower right", fontsize=6.3, frameon=False,
)

# (b) Low-quality burden under the locked final score
ax = fig.add_subplot(gs[0, 1])
low = channel_summary["D1_lt_3_pct"].to_numpy()
severe = channel_summary["D1_lt_2_5_pct"].to_numpy()
ax.barh(y + 0.17, low, height=0.32, color=C["amber"], alpha=0.88,
        edgecolor="white", linewidth=0.4, label="$D_1<3.0$")
ax.barh(y - 0.17, severe, height=0.32, color=C["red"], alpha=0.88,
        edgecolor="white", linewidth=0.4, label="$D_1<2.5$")
ax.set_yticks(y)
ax.set_yticklabels(
    channel_summary["channel"].astype(str).str.replace("-", "_", regex=False).tolist(),
    fontsize=7.2, fontfamily="Arial",
)
ax.set_xlabel("Timeline below threshold (%)", fontsize=8.4)
ax.set_title("(b) Low-quality occupancy", loc="left")
ax.set_xlim(0, max(1.0, float(low.max()) * 1.12))
ax.legend(loc="upper right", fontsize=6.3, frameon=False)

# (c) Current state occupancy, excluding Normal to expose short-lived states
ax = fig.add_subplot(gs[1, :])
xs = np.arange(len(SCORED))
bottom = np.zeros(len(SCORED))
non_normal_states = [
    "Refractory", "BaselinePending", "SustainedAnomaly",
    "RecoveryCandidate", "Recovered",
]
for state_name in non_normal_states:
    values = state_pcts[state_name].to_numpy()
    ax.bar(
        xs, values, bottom=bottom, color=STATE_COL[state_name],
        edgecolor="white", linewidth=0.4, label=state_name, alpha=0.92,
    )
    bottom += values
ax.set_xticks(xs)
ax.set_xticklabels(
    [str(channel).replace("-", "_") for channel in SCORED],
    rotation=45, ha="right", fontsize=7.4, fontfamily="Arial",
)
ax.set_ylabel("Non-normal occupancy (%)", fontsize=8.6)
ax.set_ylim(*positive_data_ylim(bottom, headroom=0.22, minimum_upper=2.0))
ax.set_title("(c) State-machine occupancy", loc="left")
ax.legend(
    loc="upper center", bbox_to_anchor=(0.62, 0.985), ncol=5,
    fontsize=5.8, frameon=True, framealpha=0.72,
    facecolor="white", edgecolor="none", borderaxespad=0,
)

# (d) Cross-sensor daily trajectory and dispersion
ax = fig.add_subplot(gs[2, :])
daily_sensor_median = D1_v11.resample("1D").median()
daily_profile = pd.DataFrame({
    "p10": daily_sensor_median.quantile(0.10, axis=1),
    "median": daily_sensor_median.median(axis=1),
    "p90": daily_sensor_median.quantile(0.90, axis=1),
})
ax.fill_between(
    daily_profile.index, daily_profile["p10"], daily_profile["p90"],
    color=C["blue"], alpha=0.16, linewidth=0, label="10th-90th percentile",
)
ax.plot(
    daily_profile.index, daily_profile["median"], color=C["blue"],
    lw=1.15, label="cross-sensor median",
)
ax.axhline(3.0, color=C["red"], ls=":", lw=0.8, label="$D_1=3$")
ax.set_ylabel(r"Daily median $D_1$", fontsize=8.6)
ax.set_title("(d) Temporal profile across scored channels", loc="left")
ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
plt.setp(ax.get_xticklabels(), rotation=25, ha="right")
profile_min = min(3.0, float(daily_profile["p10"].min()))
profile_max = float(daily_profile["p90"].max())
padding = max((profile_max - profile_min) * 0.08, 0.05)
ax.set_ylim(max(1.0, profile_min - padding), min(5.05, profile_max + padding))
ax.legend(
    loc="lower left", bbox_to_anchor=(0.01, 0.03), ncol=3,
    fontsize=6.2, frameon=True, framealpha=0.72,
    facecolor="white", edgecolor="none", borderaxespad=0,
)

fig.suptitle("Figure V12. Current D1 operating profile", fontsize=9.8,
              fontweight="bold", y=0.995)
save(
    fig, "FigV12_current_D1_profile",
    plot_data={
        "channel_summary": channel_summary.set_index("channel"),
        "state_occupancy_pct": state_pcts,
        "daily_profile": daily_profile,
    },
)


# ============================================================================
# Figure V13 — causal six-state recovery machine in action
# ============================================================================
print("[V13] causal six-state recovery machine ...")
fig = plt.figure(figsize=(7.2, 6.7))
gs = gridspec.GridSpec(4, 1, figure=fig, hspace=0.80,
                        height_ratios=[1.2, 1.0, 1.0, 1.2])
fig.subplots_adjust(right=0.78, top=0.91, bottom=0.08)

# Pick the worst sensor for illustration: DO_2_3
target = "DO_2_3"
state_log = S["state_log_dict"][target]
qd_eff = S["Q_drift_eff_dict"][target]
qs = S["subs_v11"][target]["Q_step"]
qr = S["subs_v11"][target]["Q_regime"]
qf = S["subs_v11"][target]["Q_freeze"]
d1_final = D1_v11[target]
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
ax.set_ylim(1, 5.1)
ax.set_ylabel("Sub-score", fontsize=9)
ax.set_title(f"(a)  Sub-score timeseries with state-machine shading — {target}", loc="left")
# legend in the lower band (sub-scores live at 3.5–5; the 1–2.5 band is sparse)
ax.legend(loc="center left", bbox_to_anchor=(1.01, 0.5), ncol=1,
          fontsize=5.7, frameon=False, borderaxespad=0)
ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))

# (b) State-conditioned effective drift score
ax = fig.add_subplot(gs[1])
for s_name, col in STATE_COL.items():
    mask = state_arr == s_name
    if mask.any():
        ax.fill_between(idx, 0, 1, where=mask, alpha=0.18, color=col,
                        transform=ax.get_xaxis_transform(), step="mid")
ax.plot(idx, qd_eff, color=C["purple"], lw=0.6, alpha=0.92,
        label="$Q_{drift}^{eff}$ (state-conditioned)")
ax.axhline(3.0, color=C["amber"], ls="--", lw=0.7, alpha=0.6,
            label="neutral 3.0 (during Refractory)")
ax.set_ylim(1, 5.1)
ax.set_ylabel("$Q_{drift}$ score", fontsize=9)
ax.set_title(r"(b) State-conditioned $Q_{\rm drift}^{\rm eff}$", loc="left")
ax.legend(loc="center left", bbox_to_anchor=(1.01, 0.5), ncol=1,
          fontsize=5.8, frameon=False, borderaxespad=0)
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
ax2.set_ylim(*positive_data_ylim(state_log["recovery_streak"].values,
                                 headroom=0.10, minimum_upper=1.0))
ax.set_title("(c)  α-thaw schedule + recovery_streak counter", loc="left")
ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))

# (d) D1 final
ax = fig.add_subplot(gs[3])
for s_name, col in STATE_COL.items():
    mask = state_arr == s_name
    if mask.any():
        ax.fill_between(idx, 0, 1, where=mask, alpha=0.18, color=col,
                        transform=ax.get_xaxis_transform(), step="mid")
ax.plot(idx, d1_final, color=C["blue"], lw=0.65, alpha=0.92,
        label=f"Final $D_1$ (mean={float(d1_final.mean()):.3f})")
ax.axhline(2.5, color=C["red"], ls="--", lw=0.7, alpha=0.7,
            label="SustainedAnomaly / Veto-3 cap = 2.5")
ax.axhline(3.0, color="0.5", ls=":", lw=0.7, alpha=0.6, label="grade boundary")
ax.set_ylim(1.5, 5.1)
ax.set_ylabel("$D_1$ total", fontsize=9)
ax.set_title(f"(d)  Final $D_1$ — {target} ({len(state_log[state_log.state_name=='Refractory'])} h Refractory, "
              f"{len(state_log[state_log.state_name=='SustainedAnomaly'])} h Sustained)",
              loc="left")
ax.legend(loc="center left", bbox_to_anchor=(1.01, 0.5), ncol=1,
          fontsize=5.8, frameon=False, borderaxespad=0)
ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))

fig.suptitle("Figure V13.  Causal six-state recovery machine — DO_2_3 case study",
              fontsize=9.8, fontweight="bold", y=0.995)
save(fig, "FigV13_state_machine_DO_2_3",
      plot_data={"state_log": state_log,
                  "current_scores": pd.DataFrame({
                      "Q_step": qs, "Q_regime": qr, "Q_freeze": qf,
                      "Q_drift_eff": qd_eff, "D1_final": d1_final,
                  })})


# ============================================================================
# Figure V14 — Signal-only Veto-3 and event_id timeline
# ============================================================================
print("[V14] Signal-only Veto-3 ...")
fig = plt.figure(figsize=(7.2, 5.15))
gs = gridspec.GridSpec(
    2, 2, figure=fig, hspace=0.38, wspace=0.46,
    height_ratios=[1.18, 1.0],
)
fig.subplots_adjust(top=0.91, bottom=0.12, left=0.10, right=0.96)

v3 = pd.Series({
    c: S["veto_logs_v11"][c]["veto3_signal_only"].mean() * 100
    for c in SCORED
}).sort_values()

# (a) Per-channel state distribution heatmap
ax = fig.add_subplot(gs[0, :])
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
ax.set_xticklabels(state_tick_labels, fontsize=6.7)
for i in range(len(SCORED)):
    for j in range(len(state_dist_all.columns)):
        v = state_dist_all.values[i, j]
        ax.text(j, i, f"{v:.0f}", ha="center", va="center",
                  fontsize=7, color="white" if v > 60 else "black")
cbar = plt.colorbar(im, ax=ax, fraction=0.018, pad=0.015)
cbar.set_label("% of timeline", fontsize=8); cbar.ax.tick_params(labelsize=7)
ax.set_title("(a)  Per-channel state distribution", loc="left")
ax.grid(False)

# (b) State transition counts per channel
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
ax.set_ylim(*positive_data_ylim(bottom, headroom=0.50))
ax.set_title("(b)  State-transition counts (entire 8.4 mo)", loc="left")
_h14, _l14 = ax.get_legend_handles_labels()
ax.legend(
    _h14, _l14, loc="upper left", bbox_to_anchor=(0.07, 0.82, 0.90, 0.15),
    mode="expand",
    fontsize=5.5, ncol=3, frameon=True, framealpha=0.72,
    facecolor="white", edgecolor="none", borderaxespad=0,
    columnspacing=0.8, handletextpad=0.35,
)

# (c) Veto rule overlap heat (for one representative sensor)
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
co_max = max(float(co_mat.values.max()), 1e-6)
im = ax.imshow(co_mat.values, cmap="OrRd", aspect="equal", vmin=0, vmax=co_max)
ax.set_xticks(np.arange(len(co_mat))); ax.set_yticks(np.arange(len(co_mat)))
ax.set_xticklabels(co_mat.columns.tolist(), rotation=30, ha="right", fontsize=7.5)
ax.set_yticklabels(co_mat.index.tolist(), fontsize=7.5)
for i in range(len(co_mat)):
    for j in range(len(co_mat)):
        v = co_mat.values[i, j]
        ax.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=7,
                  color="white" if v > co_max * 0.5 else "black")
cbar = plt.colorbar(im, ax=ax, fraction=0.045, pad=0.02)
cbar.set_label("co-activation rate", fontsize=8); cbar.ax.tick_params(labelsize=7)
ax.set_title(
    f"Veto/state co-activation ({target})\n"
    f"Veto-3 observed: {float(v3.max()):.2f}%",
    loc="left", fontsize=8.3,
)
ax.grid(False)

fig.suptitle("Figure V14. Six-state occupancy, transitions, and veto co-activation",
              fontsize=9.8, fontweight="bold", y=0.995)
save(fig, "FigV14_veto3_state_audit",
      plot_data={"state_dist": state_dist_all,
                  "veto3_rate": v3.to_frame("rate_pct"),
                  "transitions": trans_counts,
                  "coactivation_DO_2_3": co_mat})


# ============================================================================
# Figure V15 — PELT change-points and event_id timeline
# ============================================================================
print("[V15] PELT batch change-points ...")
fig = plt.figure(figsize=(7.2, 6.5))
gs = gridspec.GridSpec(3, 2, figure=fig, hspace=0.88, wspace=0.28,
                        height_ratios=[1.4, 1.1, 1.0])
fig.subplots_adjust(right=0.80, top=0.92, bottom=0.10)

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
ax.legend(loc="center left", bbox_to_anchor=(1.01, 0.5), fontsize=6.2,
          frameon=False, borderaxespad=0)
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
    .nlargest(4, "information").index
)
label_offsets = {
    "ORP_1_3": (7, 6), "DO_2_3": (7, 9), "DO_2_4": (7, 3),
    "DO_1_2": (-8, 12), "DO_1_3": (-8, 0), "ORP_2_1": (8, 7),
}
for c in SCORED:
    if c not in label_channels:
        continue
    xy = (df_cmp.at[c, "PELT CPs"], df_cmp.at[c, "Refractory triggers"])
    offset = label_offsets.get(c, (5, 5))
    annotate_data_label(
        ax, c, xy, xytext=offset, fontsize=5.8, arrow=True,
        ha="left" if offset[0] >= 0 else "right",
        va="bottom" if offset[1] >= 0 else "top",
    )
mx = max(df_cmp.max()) + 5
ax.plot([0, mx], [0, mx], "k--", lw=0.6, alpha=0.5, label="1:1")
ax.set_xlim(-2, mx)
ax.set_ylim(-2, mx)
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
        ax.text(x, y + 0.25, str(int(y)), ha="center", va="bottom",
                  fontsize=7.5, fontweight="bold")
    ax.set_ylim(*positive_data_ylim(monthly.values, headroom=0.14))
ax.set_ylabel("# event triggers / month", fontsize=9)
ax.set_title("(d)  Refractory trigger density timeline (all channels)", loc="left")
ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
ax.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
plt.setp(ax.get_xticklabels(), rotation=45, ha="right")

fig.suptitle("Figure V15.  PELT batch calibration + event-uniqueness filter",
              fontsize=9.8, fontweight="bold", y=0.995)
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
