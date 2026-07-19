"""make_baseline_figures_v11.py — Updated Fig 1-11 with v1.1 data
(DO/ORP only main link, with state-machine cooldown applied)
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
from matplotlib.colors import LinearSegmentedColormap, BoundaryNorm, ListedColormap
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle, Patch
from publication_style import (PALETTE as C, configure_publication_style,
                               finalize_figure, positive_data_ylim,
                               save_publication_bundle)
from src.config.loader import load_project_config

OUT = ROOT / "outputs" / "figures"
PLOTDATA = ROOT / "outputs" / "plot_data"
OUT.mkdir(parents=True, exist_ok=True)
PLOTDATA.mkdir(parents=True, exist_ok=True)

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans", "Liberation Sans"],
    "font.size": 8.5,
    "axes.titlesize": 9.5, "axes.labelsize": 9,
    "xtick.labelsize": 8, "ytick.labelsize": 8, "legend.fontsize": 7.5,
    "legend.framealpha": 0.92, "legend.edgecolor": "0.4",
    "figure.dpi": 150, "savefig.dpi": 600, "savefig.bbox": "tight",
    "savefig.pad_inches": 0.04,
    "axes.linewidth": 0.8, "axes.grid": True, "grid.alpha": 0.16,
    "grid.linewidth": 0.4, "lines.linewidth": 1.0,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.titleweight": "bold", "axes.titlelocation": "left",
    "axes.titlepad": 6,
    "pdf.fonttype": 42, "ps.fonttype": 42, "svg.fonttype": "none",
})
configure_publication_style()

with open(ROOT / "v11_state.pkl", "rb") as f:
    S = pickle.load(f)
FIGURE_VERSION = S.get("algorithm_version", "unknown")

SCORED = S["scored_channels"]
DO_CH = [c for c in SCORED if c.startswith("DO_")]
ORP_CH = [c for c in SCORED if c.startswith("ORP_")]
D1_v11 = S["D1_v11"]
subs_v11 = S["subs_v11"]
MAPPING_CFG = load_project_config().mapping


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
                if isinstance(v, pd.DataFrame): v.to_excel(w, sheet_name=k[:31], index=True)
                elif isinstance(v, pd.Series): v.to_frame(k).to_excel(w, sheet_name=k[:31], index=True)
                elif isinstance(v, dict): pd.DataFrame(v).to_excel(w, sheet_name=k[:31], index=True)
    print(f"  [OK] {name}.png + .svg + .pdf + .tiff")


# Grade colormap
grade_clrs = ["#9E1F1F", "#F46D43", "#FEE08B", "#A6D96A", "#1A9850"]
grade_cmap = LinearSegmentedColormap.from_list("grade", grade_clrs[::-1], N=256)


# ============================================================================
# Fig 1: D1 dimension matrix (5 sub-scores × 5 grade levels)
# ============================================================================
print("[Fig1] D1 dimension reference matrix ...")
fig, ax = plt.subplots(figsize=(7.2, 4.2))
sub_names = ["Q_spike\n(spike)", "Q_step\n(step)", "Q_drift\n(drift)",
              "Q_freeze\n(freeze)", "Q_regime\n(regime)"]
grades = ["A (≥4.5)", "B (3.5–4.5)", "C (2.5–3.5)", "D (1.5–2.5)", "F (<1.5)"]
matrix_text = [
    ["spike rate ≤ 2%", "very rare", "rare", "occasional", "frequent",
       "very frequent (>20%)"],
    ["KS statistic", "near 0",        "low",        "moderate",
       "elevated",       "high (sustained)"],
    ["PLS residual z", "|z| < 1.5",   "1.5–2.0",    "2.0–2.5",
       "2.5–3.0",         "> 3.0 sustained"],
    ["RLE duration", "<15 min", "15–30 min", "30–60 min",
       "60–360 min", "≥360 min"],
    ["W1 normalised", "< 1.0",        "1.0–2.0",    "2.0–3.0",
       "3.0–4.0",         "> 4.0"],
]
ax.set_xlim(0, 7); ax.set_ylim(0, 6)
ax.axis("off")
# Header
for j, g in enumerate(["criterion"] + grades):
    ax.text(j + 0.5 + (1 if j > 0 else 0), 5.55, g, ha="center", va="center",
            fontsize=10, fontweight="bold",
            color="white" if j > 0 else "black",
            bbox=dict(boxstyle="round,pad=0.2", facecolor=grade_clrs[::-1][j-1] if j > 0 else "#E0E0E0",
                       edgecolor="none"))
for i, (sn, row) in enumerate(zip(sub_names, matrix_text)):
    y = 4.5 - i
    ax.text(0.5, y, sn, ha="center", va="center", fontsize=9.5, fontweight="bold")
    for j, v in enumerate(row):
        x = j + 1.5
        clr = grade_clrs[::-1][j-1] if j > 0 else "#F2F2F2"
        rect = Rectangle((j+1, y-0.42), 1, 0.84, facecolor=clr,
                            edgecolor="white", lw=1.0, alpha=0.30 if j > 0 else 1.0)
        ax.add_patch(rect)
        ax.text(x, y, v, ha="center", va="center", fontsize=8.5,
                  color="black")
ax.set_title("Figure 1.  D1 sub-score → grade reference matrix  (DO/ORP-only main link, v1.1)",
             loc="left")
save(fig, "Fig1_D1_dimension_matrix",
      plot_data={"reference_matrix": pd.DataFrame(matrix_text,
                                                    index=[s.split('\n')[0] for s in sub_names],
                                                    columns=["criterion"] + grades)})


# ============================================================================
# Fig 2: Monthly D1 heatmap (DO/ORP only, v1.1)
# ============================================================================
print("[Fig2] Monthly D1 heatmap ...")
fig, ax = plt.subplots(figsize=(7.2, 4.0))
monthly = D1_v11.resample("ME").mean().T
months = [t.strftime("%Y-%m") for t in monthly.columns]
im = ax.imshow(monthly.values, cmap="RdBu_r", aspect="auto", vmin=2.0, vmax=5.0)
ax.set_yticks(np.arange(len(monthly))); ax.set_yticklabels(monthly.index.tolist(),
                                                              fontsize=8.5)
ax.set_xticks(np.arange(len(months))); ax.set_xticklabels(months, rotation=30,
                                                              ha="right", fontsize=8)
for i in range(len(monthly)):
    for j in range(len(months)):
        v = monthly.values[i, j]
        if not np.isnan(v):
            txt_clr = "white" if (v < 2.75 or v > 4.25) else "black"
            ax.text(j, i, f"{v:.2f}", ha="center", va="center",
                      fontsize=7.5, color=txt_clr, fontweight="bold")
cbar = plt.colorbar(im, ax=ax, fraction=0.025, pad=0.09)
cbar.set_label(r"Mean monthly $D_1$  (2.0=poor — 5.0=excellent)", fontsize=9)
cbar.ax.tick_params(labelsize=7.5)
ax.set_title("Figure 2.  Per-channel monthly $D_1$ heatmap (v1.1, DO/ORP n=14)",
             loc="left")
ax.grid(False)
save(fig, "Fig2_monthly_heatmap",
      plot_data={"monthly_D1": monthly})


# ============================================================================
# Fig 3: Case sub-score time-series (4 worst + 4 best)
# ============================================================================
print("[Fig3] Case sub-score time-series ...")
df_means = D1_v11.mean()
worst4 = df_means.nsmallest(4).index.tolist()
best4 = df_means.nlargest(4).index.tolist()
case_channels = worst4 + best4
fig, axes = plt.subplots(4, 2, figsize=(7.2, 6.7), sharex=True)
fig.subplots_adjust(hspace=0.58, wspace=0.18, top=0.84, bottom=0.08)
for i, c in enumerate(case_channels):
    ax = axes[i // 2, i % 2]
    s = subs_v11[c]
    for sub_name, clr, lw in [("Q_spike", C["amber"], 0.5),
                                 ("Q_step", C["blue"], 0.55),
                                 ("Q_drift", C["purple"], 0.6),
                                 ("Q_freeze", C["red"], 0.5),
                                 ("Q_regime", C["green"], 0.55)]:
        ax.plot(s[sub_name].index, s[sub_name].values, color=clr,
                lw=lw, alpha=0.75, label=sub_name)
    ax.plot(D1_v11[c].index, D1_v11[c].values, color="black", lw=0.7,
            alpha=0.85, label=r"$D_1$")
    ax.axhline(3, color="0.5", ls=":", lw=0.6, alpha=0.6)
    ax.axhline(2.5, color=C["red"], ls="--", lw=0.6, alpha=0.6)
    ax.set_ylim(1, 5.2)
    title_pre = "WORST" if i < 4 else "BEST"
    ax.set_title(f"{title_pre}: {c} (mean $D_1$={df_means[c]:.3f})",
                 loc="left", fontsize=7.6, fontweight="normal", pad=4)
    ax.text(-0.08, 1.04, f"({chr(97+i)})", transform=ax.transAxes,
            ha="left", va="bottom", fontsize=8, fontweight="bold",
            clip_on=False)
    if i % 2 == 0:
        ax.set_ylabel("Sub-score / D1", fontsize=8.5)
    # every panel carries its own date labels (was shared via sharex → bottom row)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    ax.tick_params(axis="x", labelbottom=True)
# shared legend at the figure top (outside the dense panels — was overlapping
# panel (a)'s data at lower-right)
_h3, _l3 = axes[0, 0].get_legend_handles_labels()
fig.legend(_h3, _l3, loc="upper center", bbox_to_anchor=(0.5, 0.935),
           ncol=6, fontsize=7.2, frameon=False)
fig.suptitle("Figure 3.  Sub-score timeseries — 4 worst + 4 best (v1.1)",
              fontsize=9.8, fontweight="bold", y=0.992)
save(fig, "Fig3_case_subscores",
      plot_data={c: D1_v11[[c]] for c in case_channels})


# ============================================================================
# Fig 4: Sub-score distribution (violin per channel)
# ============================================================================
print("[Fig4] Sub-score violin distribution ...")
fig, axes = plt.subplots(5, 1, figsize=(7.2, 6.7), sharex=True)
fig.subplots_adjust(hspace=0.55)
sub_names = ["Q_spike", "Q_step", "Q_drift", "Q_freeze", "Q_regime"]
sub_clrs = [C["amber"], C["blue"], C["purple"], C["red"], C["green"]]
for i, (sn, clr) in enumerate(zip(sub_names, sub_clrs)):
    ax = axes[i]
    data = []
    for c in SCORED:
        v = subs_v11[c][sn].dropna().values
        data.append(v)
    parts = ax.violinplot(data, positions=np.arange(len(SCORED)), widths=0.75,
                            showmedians=True, showextrema=False)
    for body in parts["bodies"]:
        body.set_facecolor(clr); body.set_edgecolor("0.3"); body.set_alpha(0.65)
    parts["cmedians"].set_color("k"); parts["cmedians"].set_linewidth(1.0)
    ax.set_ylim(0.7, 5.3)
    ax.axhline(3, color="0.5", ls=":", lw=0.5, alpha=0.6)
    ax.set_ylabel(sn, fontsize=9.5, fontweight="bold")
    ax.set_xticks(np.arange(len(SCORED)))
    if i == 4:
        ax.set_xticklabels(SCORED, rotation=45, ha="right", fontsize=8)
    else:
        ax.set_xticklabels([])
fig.suptitle("Figure 4.  Sub-score distribution per channel (v1.1, DO/ORP n=14)",
              fontsize=11, fontweight="bold", y=0.995)
save(fig, "Fig4_subscore_distribution")


# ============================================================================
# Fig 5: Mapping function curves
# ============================================================================
print("[Fig5] Mapping curves ...")
fig, axes = plt.subplots(2, 3, figsize=(7.2, 4.8))
fig.subplots_adjust(hspace=0.4, wspace=0.32)
def logistic(x, k, x0, direction="hi_lo"):
    if direction == "hi_lo":
        return 1 + 4 / (1 + np.exp(k * (x - x0)))
    else:
        return 1 + 4 / (1 + np.exp(-k * (x - x0)))

# Q_spike: piecewise on spike_rate_6h
ax = axes[0, 0]
x = np.linspace(0, 0.3, 200)
breaks = [0.02, 0.05, 0.1, 0.2, 1.0]
scores = [5, 4, 3, 2, 1]
y = np.zeros_like(x)
for i in range(len(breaks)):
    if i == 0:
        y[x <= breaks[i]] = scores[i]
    else:
        y[(x > breaks[i-1]) & (x <= breaks[i])] = scores[i]
y[x > breaks[-1]] = 1
ax.plot(x, y, color=C["amber"], lw=1.8)
ax.set_xlabel("spike_rate_6h", fontsize=9)
ax.set_ylabel(r"$Q_{spike}$", fontsize=9)
ax.set_title("(a) Spike: piecewise", loc="left")
ax.set_ylim(0.8, 5.2); ax.set_xlim(0, 0.3)
for b, s in zip(breaks[:-1], scores[:-1]):
    ax.axvline(b, color="0.6", ls=":", lw=0.5)

# Q_step: injection-calibrated logistic mapping
ax = axes[0, 1]
x = np.linspace(0, 1.0, 300)
step_k = float(MAPPING_CFG.step.k)
step_x0 = float(MAPPING_CFG.step.x0)
y = logistic(x, step_k, step_x0)
ax.plot(x, y, color=C["blue"], lw=1.8)
ax.axvline(step_x0, color="0.35", ls=":", lw=0.8)
ax.set_xlabel("KS statistic", fontsize=9)
ax.set_ylabel(r"$Q_{step}$", fontsize=9)
ax.set_title(f"(b) Step: $k={step_k:.0f}$, $x_0={step_x0:.2f}$", loc="left")
ax.set_ylim(0.8, 5.2)

# Q_drift: logistic k=1.5, x0=2.5
ax = axes[0, 2]
x = np.linspace(0, 6, 200)
y = logistic(x, 1.5, 2.5)
ax.plot(x, y, color=C["purple"], lw=1.8)
ax.set_xlabel("PLS residual z (|·|)", fontsize=9)
ax.set_ylabel(r"$Q_{drift}$", fontsize=9)
ax.set_title("(c) Drift: $k=1.5$, $x_0=2.5$", loc="left")
ax.set_ylim(0.8, 5.2)

# Q_freeze: stepwise duration
ax = axes[1, 0]
durations = [15, 30, 60, 360]
scores_f = [5, 4, 3, 2, 1]
x_f = np.linspace(0, 400, 400)
y_f = np.zeros_like(x_f)
for i, d in enumerate(durations):
    if i == 0:
        y_f[x_f < d] = scores_f[i]
    elif i < len(durations):
        y_f[(x_f >= durations[i-1]) & (x_f < d)] = scores_f[i]
y_f[x_f >= durations[-1]] = 1
ax.plot(x_f, y_f, color=C["red"], lw=1.8)
ax.set_xlabel("freeze RLE duration (min)", fontsize=9)
ax.set_ylabel(r"$Q_{freeze,RLE}$", fontsize=9)
ax.set_title("(d) Freeze duration", loc="left")
ax.set_ylim(0.8, 5.2)
for d in durations:
    ax.axvline(d, color="0.6", ls=":", lw=0.5)

# Q_freeze: low_var (logistic neg)
ax = axes[1, 1]
x = np.linspace(0, 1, 200)
y = logistic(x, 10, 0.2, "lo_hi")
ax.plot(x, y, color=C["red"], lw=1.8, label="low_var")
y2 = logistic(x, 15, 0.2, "lo_hi")
ax.plot(x, y2, color=C["orange"], lw=1.8, label="unique_ratio", ls="--")
ax.set_xlabel("rel-var / unique-ratio", fontsize=9)
ax.set_ylabel(r"$Q$", fontsize=9)
ax.set_title("(e) Freeze metrics", loc="left")
ax.set_ylim(0.8, 5.2)
ax.legend(fontsize=7.2, loc="lower right", frameon=False)

# Q_regime: logistic
ax = axes[1, 2]
x = np.linspace(0, 8, 200)
y = logistic(x, 1.2, 3.0)
ax.plot(x, y, color=C["green"], lw=1.8)
ax.set_xlabel("W1 normalised (×IQR)", fontsize=9)
ax.set_ylabel(r"$Q_{regime}$", fontsize=9)
ax.set_title("(f) Regime mapping", loc="left")
ax.text(0.98, 0.95, "$k=1.2$, $x_0=3.0$", transform=ax.transAxes,
        ha="right", va="top", fontsize=7)
ax.set_ylim(0.8, 5.2)

fig.suptitle("Figure 5.  D1 mapping function curves (v1.1)",
              fontsize=11, fontweight="bold", y=1.0)
save(fig, "Fig5_mapping_curves")


# ============================================================================
# Fig 6: Exact pre-cap score-loss attribution + severe evidence rate
# ============================================================================
print("[Fig6] Pre-cap score-loss attribution ...")
fig, axes = plt.subplots(2, 1, figsize=(7.2, 5.8), gridspec_kw={"height_ratios": [1.15, 1.0]})
fig.subplots_adjust(hspace=0.55, top=0.82, bottom=0.18, right=0.92)
faults = ["Q_spike", "Q_step", "Q_drift", "Q_freeze", "Q_regime"]
fclr = {"Q_spike": C["amber"], "Q_step": C["blue"], "Q_drift": C["purple"],
        "Q_freeze": C["red"], "Q_regime": C["green"]}

weights = S["rules_yaml"]["aggregation"]["weights"]
lambda_blend = float(S["rules_yaml"]["aggregation"]["lambda_blend"])
weight_by_q = {
    "Q_spike": weights["spike"], "Q_step": weights["step"],
    "Q_drift": weights["drift"], "Q_freeze": weights["freeze"],
    "Q_regime": weights["regime"],
}
loss_share = pd.DataFrame(index=SCORED, columns=faults, dtype=float)
severe_rate = pd.DataFrame(index=faults, columns=SCORED, dtype=float)
loss_closure = []
for c in SCORED:
    q = pd.DataFrame({f: subs_v11[c][f] for f in faults})
    min_q = q.min(axis=1)
    is_min = q.eq(min_q, axis=0)
    tie_count = is_min.sum(axis=1).clip(lower=1)
    min_penalty = (1.0 - lambda_blend) * (5.0 - min_q)
    contribution = pd.DataFrame(index=q.index, columns=faults, dtype=float)
    for f in faults:
        weighted_loss = lambda_blend * weight_by_q[f] * (5.0 - q[f])
        limiting_loss = min_penalty * is_min[f] / tie_count
        contribution[f] = weighted_loss + limiting_loss
        severe_rate.at[f, c] = 100.0 * float((q[f] < 3.0).mean())
    integrated = contribution.sum(axis=0)
    total = float(integrated.sum())
    loss_share.loc[c] = 100.0 * integrated / total if total > 0 else 0.0
    expected_loss = 5.0 - S["components_v11"][c]["D1_pre"]
    loss_closure.append(float((contribution.sum(axis=1) - expected_loss).abs().max()))

ax = axes[0]
xs = np.arange(len(SCORED))
bottom = np.zeros(len(SCORED))
for f in faults:
    values = loss_share[f].to_numpy(dtype=float)
    ax.bar(xs, values, bottom=bottom, color=fclr[f], label=f.replace("Q_", ""),
            alpha=0.92, edgecolor="white", linewidth=0.5)
    bottom += values
ax.set_xticks(xs); ax.set_xticklabels([])
ax.set_ylabel("Share of pre-cap $D_1$ loss (%)", fontsize=9)
ax.set_ylim(0, 100)
ax.set_title("(a) Exact additive attribution of $5-D_{1,pre}$", loc="left")
_h6, _l6 = ax.get_legend_handles_labels()
fig.legend(_h6, _l6, loc="upper center", bbox_to_anchor=(0.5, 0.89),
           ncol=5, fontsize=7.4, frameon=False)

ax = axes[1]
im = ax.imshow(severe_rate.to_numpy(dtype=float), cmap="Reds", aspect="auto", vmin=0,
               vmax=max(1.0, float(np.nanpercentile(severe_rate.to_numpy(dtype=float), 98))))
ax.set_yticks(np.arange(len(faults)))
ax.set_yticklabels([f.replace("Q_", "") for f in faults])
ax.set_xticks(xs)
ax.set_xticklabels(SCORED, rotation=45, ha="right", fontsize=8.0)
ax.set_ylabel("Sub-score")
ax.set_title("(b) Absolute severe-evidence frequency", loc="left")
ax.grid(False)
for i in range(len(faults)):
    for j in range(len(SCORED)):
        value = float(severe_rate.iat[i, j])
        if value >= 0.05:
            ax.text(j, i, f"{value:.1f}", ha="center", va="center", fontsize=6.2,
                    color="white" if value > im.norm.vmax * 0.55 else "black")
cbar = fig.colorbar(im, ax=ax, fraction=0.025, pad=0.025)
cbar.set_label("Hours with $Q<3$ (%)", fontsize=8.5)

fig.suptitle("Figure 6.  Sensor-health score-loss attribution and severe evidence",
             fontsize=9.8, fontweight="bold", y=0.98)
save(fig, "Fig6_score_loss_attribution",
      plot_data={"loss_attribution_pct": loss_share,
                 "subscore_lt3_pct": severe_rate,
                 "closure_audit": pd.DataFrame({
                     "sensor_id": SCORED, "max_abs_error": loss_closure,
                 }).set_index("sensor_id")})


# ============================================================================
# Fig 7: Daily timeseries by sensor group
# ============================================================================
print("[Fig7] Daily timeseries ...")
fig = plt.figure(figsize=(7.2, 6.5))
gs = gridspec.GridSpec(3, 1, figure=fig, hspace=0.52, height_ratios=[1, 1, 1.05])
fig.subplots_adjust(right=0.79, top=0.91, bottom=0.09)

# (a) DO daily
ax = fig.add_subplot(gs[0])
D1_d = D1_v11.resample("1D").median()
do_clrs = plt.cm.Blues(np.linspace(0.4, 0.95, len(DO_CH)))
for c, clr in zip(DO_CH, do_clrs):
    ax.plot(D1_d.index, D1_d[c].values, color=clr, lw=0.85, alpha=0.85, label=c)
ax.axhline(3, color=C["red"], ls=":", lw=0.7)
ax.set_ylabel("Daily $D_1$ (median)", fontsize=9.5)
ax.set_ylim(1.5, 5.0)
ax.set_title("(a)  DO channels (n=8)", loc="left")
ax.legend(loc="center left", bbox_to_anchor=(1.01, 0.5), ncol=1,
          fontsize=6.7, frameon=False, borderaxespad=0)
ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))

# (b) ORP daily
ax = fig.add_subplot(gs[1])
orp_clrs = plt.cm.Greens(np.linspace(0.4, 0.95, len(ORP_CH)))
for c, clr in zip(ORP_CH, orp_clrs):
    ax.plot(D1_d.index, D1_d[c].values, color=clr, lw=0.85, alpha=0.85, label=c)
ax.axhline(3, color=C["red"], ls=":", lw=0.7)
ax.set_ylabel("Daily $D_1$ (median)", fontsize=9.5)
ax.set_ylim(1.5, 5.0)
ax.set_title("(b)  ORP channels (n=6)", loc="left")
ax.legend(loc="center left", bbox_to_anchor=(1.01, 0.5), ncol=1,
          fontsize=6.7, frameon=False, borderaxespad=0)
ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))

# (c) ORP_1_2 platform mechanism: state cap is retained but made explicit
case_channel = "ORP_1_2"
ax = fig.add_subplot(gs[2])
pre_daily = S["components_v11"][case_channel]["D1_pre"].resample("1D").median()
final_daily = D1_d[case_channel]
cap_daily = (
    S["veto_logs_v11"][case_channel]["sustained_active"].resample("1D").mean() * 100
)
line_pre, = ax.plot(pre_daily.index, pre_daily, color="0.55", lw=0.8,
                    label=r"Pre-cap $D_{1,pre}$")
line_final, = ax.plot(final_daily.index, final_daily, color=C["purple"], lw=1.15,
                      label=r"Final $D_1$")
ax.axhline(2.5, color=C["red"], ls=":", lw=0.8)
ax.set_ylabel("Daily score")
ax.set_ylim(1.5, 5.0)
ax.set_title(f"(c)  {case_channel}: state-cap mechanism behind the 2.5 platform",
             loc="left")
ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
cap_ax = ax.twinx()
cap_ax.fill_between(cap_daily.index, 0, cap_daily.values,
                    color=C["amber"], alpha=0.18)
cap_ax.set_ylabel("Cap-active hours (%)", color=C["amber"])
cap_ax.set_ylim(0, 105)
cap_ax.tick_params(axis="y", colors=C["amber"], direction="out")
cap_ax.spines["right"].set_visible(True)
cap_ax.spines["right"].set_color(C["amber"])
ax.legend(
    [line_pre, line_final, Line2D([0], [0], color=C["red"], ls=":"),
     Patch(facecolor=C["amber"], alpha=0.25)],
    [r"Pre-cap $D_{1,pre}$", r"Final $D_1$", "State cap (2.5)",
     "Cap-active hours"],
    loc="upper left", bbox_to_anchor=(0.01, 0.98), fontsize=6.7,
    frameon=True, framealpha=0.68, facecolor="white", edgecolor="none",
    borderaxespad=0,
)

fig.suptitle("Figure 7.  Daily sensor-health trajectories and state-cap interpretation",
             fontsize=9.8, fontweight="bold", y=0.985)
save(fig, "Fig7_daily_timeseries",
     plot_data={"D1_daily": D1_d,
                "ORP_1_2_platform": pd.DataFrame({
                    "D1_pre_daily": pre_daily,
                    "D1_final_daily": final_daily,
                    "cap_active_hours_pct": cap_daily,
                })})


# ============================================================================
# Fig 8: Veto / cooldown activation rate (NEW: state-machine breakdown)
# ============================================================================
print("[Fig8] Veto + state-machine activation rates ...")
fig, ax = plt.subplots(figsize=(7.2, 4.0))
fig.subplots_adjust(top=0.79, bottom=0.27)
delta_df = S["delta_df"]
xs = np.arange(len(SCORED))
bw = 0.12
# Compute counts per channel
data = []
for c in SCORED:
    vlog = S["veto_logs_v11"][c]
    states = S["state_log_dict"][c]["state_name"]
    data.append({
        "Refractory": states.eq("Refractory").mean() * 100,
        "BaselinePending": states.eq("BaselinePending").mean() * 100,
        "Sustained": states.eq("SustainedAnomaly").mean() * 100,
        "RecoveryCandidate": states.eq("RecoveryCandidate").mean() * 100,
        "Recovered observation": states.eq("Recovered").mean() * 100,
        "VetoFreeze": vlog["veto_freeze"].mean() * 100,
        "VetoRegime": vlog["veto_regime"].mean() * 100,
    })
df_v = pd.DataFrame(data, index=SCORED)
clr_map = {
    "Refractory": C["orange"], "BaselinePending": C["amber"],
    "Sustained": C["purple"], "RecoveryCandidate": C["rose"],
    "Recovered observation": C["blue"],
    "VetoFreeze": C["red"], "VetoRegime": C["green"],
}
for i, (k_name, clr) in enumerate(clr_map.items()):
    ax.bar(xs + (i - (len(clr_map) - 1) / 2) * bw, df_v[k_name].values, bw, color=clr,
            edgecolor="white", linewidth=0.4, alpha=0.88, label=k_name)
ax.set_xticks(xs); ax.set_xticklabels(SCORED, rotation=45, ha="right", fontsize=8.5)
ax.set_ylabel("Activation rate (%)", fontsize=9.5)
ax.set_ylim(*positive_data_ylim(df_v.to_numpy(), headroom=0.10))
_h8, _l8 = ax.get_legend_handles_labels()
fig.legend(_h8, _l8, loc="upper center", bbox_to_anchor=(0.5, 0.875),
           ncol=4, fontsize=6.7, frameon=False)
fig.suptitle("Figure 8.  Veto and state-machine activation rates per channel (v1.1)",
             fontsize=9.8, fontweight="bold", y=0.98)
save(fig, "Fig8_veto_cooldown",
      plot_data={"activation_rates": df_v})


# ============================================================================
# Fig 9: Harmonic decomposition demonstration  (carry over from STRICT V1)
# ============================================================================
print("[Fig9] Input-routing audit ...")
fig, axes = plt.subplots(1, 3, figsize=(7.2, 4.3),
                         gridspec_kw={"width_ratios": [1.25, 1.0, 0.9]})
fig.subplots_adjust(wspace=0.50, top=0.84, bottom=0.25)
resid_h = S["resid_h"]
routed_h = S.get("whitened_input_h", resid_h)
scoring_mode = S.get("scoring_mode", {})
eff_neff = S.get("eff_neff", {})
route_columns = ["PLS/state\nresidual", "KS/PELT\ninnovation",
                 "KS/PELT\n$n_{eff}$ residual", "KS/PELT\nexcluded"]
route_matrix = pd.DataFrame(0, index=SCORED, columns=route_columns, dtype=int)
route_matrix.iloc[:, 0] = 1
for channel in SCORED:
    mode = scoring_mode.get(channel, "iid")
    target_column = 1 if mode == "iid" else 2 if mode == "autocorr_aware" else 3
    route_matrix.at[channel, route_columns[target_column]] = 1

ax = axes[0]
ax.imshow(route_matrix.values, cmap=ListedColormap(["#F2F2F2", C["blue"]]),
          aspect="auto", vmin=0, vmax=1)
ax.set_yticks(np.arange(len(SCORED))); ax.set_yticklabels(SCORED, fontsize=7.2)
ax.set_xticks(np.arange(len(route_columns)))
ax.set_xticklabels(route_columns, rotation=50, ha="right", fontsize=6.7)
ax.set_title("(a) Routed evidence", loc="left")
ax.grid(False)

acf_audit = pd.DataFrame(index=SCORED,
                         columns=["residual_abs_acf1", "routed_abs_acf1"], dtype=float)
for channel in SCORED:
    acf_audit.at[channel, "residual_abs_acf1"] = abs(float(resid_h[channel].autocorr(1)))
    acf_audit.at[channel, "routed_abs_acf1"] = abs(float(routed_h[channel].autocorr(1)))
ax = axes[1]
ys = np.arange(len(SCORED))
for y_pos, channel in zip(ys, SCORED):
    x0_acf = acf_audit.at[channel, "residual_abs_acf1"]
    x1_acf = acf_audit.at[channel, "routed_abs_acf1"]
    ax.plot([x0_acf, x1_acf], [y_pos, y_pos], color="0.75", lw=0.7, zorder=1)
ax.scatter(acf_audit["residual_abs_acf1"], ys, s=13, color="0.55",
           label="1.1 residual", zorder=2)
ax.scatter(acf_audit["routed_abs_acf1"], ys, s=14, color=C["blue"], marker="D",
           label="D1 detector input", zorder=3)
ax.set_yticks(ys); ax.set_yticklabels([])
ax.set_xlim(0, 1.02); ax.set_xlabel(r"Absolute lag-1 ACF, $|\rho_1|$")
ax.set_title("(b) Whitening effect", loc="left")
ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.24), ncol=1,
          fontsize=6.5, frameon=False)

reachability = pd.DataFrame({
    "scoring_mode": [scoring_mode.get(c, "iid") for c in SCORED],
    "neff_ratio": [float(eff_neff.get(c, 1.0)) for c in SCORED],
}, index=SCORED)
reachability["max_corrected_ks"] = np.sqrt(reachability["neff_ratio"].clip(0, 1))
mode_colors = {"iid": C["blue"], "autocorr_aware": C["amber"],
               "floor_freeze": "0.65"}
ax = axes[2]
ax.barh(ys, reachability["max_corrected_ks"],
        color=[mode_colors.get(mode, "0.65") for mode in reachability["scoring_mode"]],
        height=0.68)
ax.axvline(step_x0, color=C["red"], ls=":", lw=0.9,
           label=fr"Mapping midpoint $x_0={step_x0:.2f}$")
ax.set_yticks(ys); ax.set_yticklabels([])
ax.set_xlim(0, 1.05); ax.set_xlabel("Theoretical corrected-KS bound")
ax.set_title("(c) Step applicability", loc="left")
ax.legend(handles=[
    Patch(facecolor=C["blue"], label="iid route"),
    Patch(facecolor=C["amber"], label=r"$n_{eff}$-aware route"),
    Patch(facecolor="0.65", label="process-floor route"),
    Line2D([0], [0], color=C["red"], ls=":",
           label=fr"Midpoint $x_0={step_x0:.2f}$"),
], loc="upper center", bbox_to_anchor=(0.5, -0.24), ncol=2, fontsize=6.2,
          frameon=False)

fig.suptitle("Figure 9.  Section 1.1-to-D1 input routing and detector applicability",
             fontsize=9.8, fontweight="bold", y=0.98)
save(fig, "Fig9_input_routing_audit",
     plot_data={"route_matrix": route_matrix,
                "acf_audit": acf_audit,
                "step_applicability": reachability})


# ============================================================================
# Fig 10: Two-tier regime visualization
# ============================================================================
print("[Fig10] Two-tier regime ...")
fig, axes = plt.subplots(2, 1, figsize=(7.2, 4.8), sharex=True)
fig.subplots_adjust(hspace=0.42, top=0.76, bottom=0.10)
ch = "DO_2_3"
det_raw = S["detectors_raw"]
w1 = det_raw["w1_normalised_hourly"][ch]
ks = det_raw["ks_statistic_hourly"][ch]
qregime = subs_v11[ch]["Q_regime"]

ax = axes[0]
line_w1, = ax.plot(w1.index, w1.values, color=C["red"], lw=0.5, alpha=0.85,
                   label="W1 normalised (Tier-1)")
fill_w1 = ax.fill_between(w1.index, 0, w1.values, where=w1.values > 3,
                          color=C["red"], alpha=0.15,
                          label="Tier-1 active (W1>3)")
ax.set_ylabel("W1 normalised", fontsize=9.5)
ax.set_yscale("symlog", linthresh=2)
ax.set_ylim(*positive_data_ylim(w1.values, headroom=0.08))
ax.set_title(f"(a)  Tier-1 W1 distance — {ch}", loc="left")

ax = axes[1]
line_ks, = ax.plot(ks.index, ks.values, color=C["blue"], lw=0.5, alpha=0.85,
                   label="adjacent KS statistic (Tier-2)")
fill_ks = ax.fill_between(ks.index, 0, ks.values, where=ks.values > 0.3,
                          color=C["blue"], alpha=0.15,
                          label="Tier-2 active (KS>0.3)")
ax.set_ylabel("adjacent KS", fontsize=9.5)
ax.set_ylim(*positive_data_ylim(ks.values, headroom=0.08, minimum_upper=0.5))
ax.set_title(f"(b)  Tier-2 adjacent KS — {ch}", loc="left")
# each panel carries its own date labels (was shared via sharex → only bottom)
for _ax in axes:
    _ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    _ax.tick_params(axis="x", labelbottom=True)

fig.suptitle(f"Figure 10.  Two-tier regime detector outputs — {ch} (v1.1)",
              fontsize=9.8, fontweight="bold", y=0.985)
fig.legend([line_w1, fill_w1, line_ks, fill_ks],
           ["W1 normalised", "W1 > 3", "Adjacent KS", "KS > 0.3"],
           loc="upper center", bbox_to_anchor=(0.5, 0.895), ncol=4,
           fontsize=6.9, frameon=False)
save(fig, "Fig10_two_tier_regime")


# ============================================================================
# Fig 11: PLS peer audit (engineered peers)
# ============================================================================
print("[Fig11] PLS peer audit ...")
fig, axes = plt.subplots(1, 2, figsize=(7.2, 4.3),
                         gridspec_kw={"width_ratios": [1.45, 0.9]})
fig.subplots_adjust(wspace=0.42, top=0.84, bottom=0.25)
peer_matrix = S["detectors_raw"]["pls_peer_matrix"].reindex(
    index=SCORED, columns=SCORED
).fillna(0).astype(int)
peer_audit = S["detectors_raw"]["pls_peer_selection_audit"].reindex(SCORED)

ax = axes[0]
peer_cmap = ListedColormap(["#F2F2F2", C["blue"], C["amber"]])
peer_norm = BoundaryNorm([-0.5, 0.5, 1.5, 2.5], peer_cmap.N)
ax.imshow(peer_matrix.values, cmap=peer_cmap, norm=peer_norm, aspect="auto")
ax.set_yticks(np.arange(len(SCORED))); ax.set_yticklabels(SCORED, fontsize=7.2)
ax.set_xticks(np.arange(len(SCORED)))
ax.set_xticklabels(SCORED, rotation=55, ha="right", fontsize=6.8)
ax.set_xlabel("Predictor")
ax.set_ylabel("Target")
ax.set_title("(a) Selected same-analyte peers", loc="left")
ax.grid(False)
ax.legend(handles=[Patch(facecolor=C["blue"], label="Structural core"),
                   Patch(facecolor=C["amber"], label="CV-added peer")],
          loc="upper center", bbox_to_anchor=(0.5, -0.25), ncol=2,
          fontsize=6.5, frameon=False)

ax = axes[1]
improvement = peer_audit["cv_improvement_pct"].fillna(0.0)
colors = [C["amber"] if str(peer_audit.at[c, "selected_noncore_peers"]).strip()
          else "0.65" for c in SCORED]
ax.barh(np.arange(len(SCORED)), improvement.values, color=colors, height=0.68)
ax.axvline(2.0, color=C["red"], ls=":", lw=0.8, label="2% inclusion threshold")
ax.set_yticks(np.arange(len(SCORED))); ax.set_yticklabels(SCORED, fontsize=7.2)
ax.invert_yaxis()
ax.set_xlabel("CV NRMSE gain (%)")
ax.set_title("(b) Predictive gain", loc="left")
improvement_upper = positive_data_ylim(
    improvement.values, headroom=0.12, minimum_upper=2.5
)[1]
ax.set_xlim(0.0, improvement_upper)
ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.25), fontsize=6.5,
          frameon=False)

fig.suptitle("Figure 11.  Same-analyte PLS peer selection with blocked temporal validation",
             fontsize=9.8, fontweight="bold", y=0.98)
save(fig, "Fig11_pls_peer_selection",
     plot_data={"selected_peer_matrix": peer_matrix,
                "blocked_cv_audit": peer_audit})

print("\n[done] Updated baseline figures Fig 1-11 complete.\n")
try:
    from generate_expert_report_v11 import maybe_update_report
    maybe_update_report()
except Exception as exc:
    print(f"[auto-report] skipped: {exc}")
