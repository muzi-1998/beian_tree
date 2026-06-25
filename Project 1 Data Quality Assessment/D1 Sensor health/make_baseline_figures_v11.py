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
from matplotlib.colors import LinearSegmentedColormap, BoundaryNorm
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle, Patch

OUT = ROOT / "outputs" / "figures"
PLOTDATA = ROOT / "outputs" / "plot_data"

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 8.5,
    "axes.titlesize": 9.5, "axes.labelsize": 9,
    "xtick.labelsize": 8, "ytick.labelsize": 8, "legend.fontsize": 7.5,
    "legend.framealpha": 0.92, "legend.edgecolor": "0.4",
    "figure.dpi": 150, "savefig.dpi": 600, "savefig.bbox": "tight",
    "savefig.pad_inches": 0.04,
    "axes.linewidth": 0.7, "axes.grid": True, "grid.alpha": 0.16,
    "grid.linewidth": 0.4, "lines.linewidth": 1.0,
    "axes.spines.top": False, "axes.spines.right": False,
    "axes.titleweight": "bold", "axes.titlelocation": "left",
    "axes.titlepad": 6,
})

C = {"blue":"#2166AC","red":"#B2182B","green":"#1B7837","orange":"#F46D43",
     "purple":"#762A83","gray":"#707070","teal":"#1A9988","amber":"#E08214",
     "navy":"#053061","cyan":"#35978F","rose":"#D6604D"}

with open(ROOT / "v11_state.pkl", "rb") as f:
    S = pickle.load(f)

SCORED = S["scored_channels"]
DO_CH = [c for c in SCORED if c.startswith("DO_")]
ORP_CH = [c for c in SCORED if c.startswith("ORP_")]
D1_v11 = S["D1_v11"]
subs_v11 = S["subs_v11"]


def _finish_axes(fig):
    """Draw tick marks at both ends of every data axis. The default locator
    places ticks at 'nice' interior values and leaves the spine ends bare;
    here the axis min/max are added as same-size minor ticks (marks only, no
    extra labels) so every axis reads complete to its end."""
    for ax in fig.axes:
        for which in ("x", "y"):
            get_lim = ax.get_xlim if which == "x" else ax.get_ylim
            get_maj = ax.get_xticks if which == "x" else ax.get_yticks
            lo, hi = sorted(get_lim())
            span = hi - lo
            if span <= 0:
                continue
            majors = [t for t in get_maj() if lo - 1e-9 <= t <= hi + 1e-9]
            if len(majors) < 2:
                continue   # colorbar short axis / schematic / label-less axis
            tol = span * 0.015
            ends = [v for v in (lo, hi)
                    if not any(abs(m - v) <= tol for m in majors)]
            if not ends:
                continue
            spine = "bottom" if which == "x" else "left"
            col = ax.spines[spine].get_edgecolor()
            if which == "x":
                ax.set_xticks(ends, minor=True)
                ax.tick_params(axis="x", which="minor", length=3.2, width=0.7,
                               color=col, bottom=True, top=False)
            else:
                ax.set_yticks(ends, minor=True)
                ax.tick_params(axis="y", which="minor", length=3.2, width=0.7,
                               color=col, left=True, right=False)


def save(fig, name, plot_data: dict = None):
    _finish_axes(fig)
    fig.savefig(OUT / f"{name}.png")
    plt.close(fig)
    if plot_data is not None:
        with pd.ExcelWriter(PLOTDATA / f"{name}_data.xlsx", engine="openpyxl") as w:
            for k, v in plot_data.items():
                if isinstance(v, pd.DataFrame): v.to_excel(w, sheet_name=k[:31], index=True)
                elif isinstance(v, pd.Series): v.to_frame(k).to_excel(w, sheet_name=k[:31], index=True)
                elif isinstance(v, dict): pd.DataFrame(v).to_excel(w, sheet_name=k[:31], index=True)
    print(f"  [OK] {name}.png")


# Grade colormap
grade_clrs = ["#9E1F1F", "#F46D43", "#FEE08B", "#A6D96A", "#1A9850"]
grade_cmap = LinearSegmentedColormap.from_list("grade", grade_clrs[::-1], N=256)


# ============================================================================
# Fig 1: D1 dimension matrix (5 sub-scores × 5 grade levels)
# ============================================================================
print("[Fig1] D1 dimension reference matrix ...")
fig, ax = plt.subplots(figsize=(10, 5.6))
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
    ["RLE / unique ratio", "no freeze", "<5 min",   "5–15 min",
       "15–60 min",       ">60 min"],
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
fig, ax = plt.subplots(figsize=(11, 5.5))
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
fig, axes = plt.subplots(4, 2, figsize=(13.5, 10), sharex=True)
fig.subplots_adjust(hspace=0.50, wspace=0.18, top=0.90)
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
    ax.set_title(f"({chr(97+i)}) {title_pre}: {c} (mean $D_1$={df_means[c]:.3f})",
                  loc="left")
    if i % 2 == 0:
        ax.set_ylabel("Sub-score / D1", fontsize=8.5)
    # every panel carries its own date labels (was shared via sharex → bottom row)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    ax.tick_params(axis="x", labelbottom=True)
# shared legend at the figure top (outside the dense panels — was overlapping
# panel (a)'s data at lower-right)
_h3, _l3 = axes[0, 0].get_legend_handles_labels()
fig.legend(_h3, _l3, loc="upper center", bbox_to_anchor=(0.5, 0.955),
           ncol=6, fontsize=8.5, framealpha=0.9)
fig.suptitle("Figure 3.  Sub-score timeseries — 4 worst + 4 best (v1.1)",
              fontsize=11, fontweight="bold", y=0.99)
save(fig, "Fig3_case_subscores",
      plot_data={c: D1_v11[[c]] for c in case_channels})


# ============================================================================
# Fig 4: Sub-score distribution (violin per channel)
# ============================================================================
print("[Fig4] Sub-score violin distribution ...")
fig, axes = plt.subplots(5, 1, figsize=(13, 11), sharex=True)
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
fig, axes = plt.subplots(2, 3, figsize=(13, 7.5))
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
ax.set_title("(a)  spike: piecewise", loc="left")
ax.set_ylim(0.8, 5.2); ax.set_xlim(0, 0.3)
for b, s in zip(breaks[:-1], scores[:-1]):
    ax.axvline(b, color="0.6", ls=":", lw=0.5)

# Q_step: logistic k=12, x0=0.3
ax = axes[0, 1]
x = np.linspace(0, 0.6, 200)
y = logistic(x, 12, 0.3)
ax.plot(x, y, color=C["blue"], lw=1.8)
ax.set_xlabel("KS statistic", fontsize=9)
ax.set_ylabel(r"$Q_{step}$", fontsize=9)
ax.set_title("(b)  step: logistic k=12, x₀=0.3", loc="left")
ax.set_ylim(0.8, 5.2)

# Q_drift: logistic k=1.5, x0=2.5
ax = axes[0, 2]
x = np.linspace(0, 6, 200)
y = logistic(x, 1.5, 2.5)
ax.plot(x, y, color=C["purple"], lw=1.8)
ax.set_xlabel("PLS residual z (|·|)", fontsize=9)
ax.set_ylabel(r"$Q_{drift}$", fontsize=9)
ax.set_title("(c)  drift: logistic k=1.5, x₀=2.5", loc="left")
ax.set_ylim(0.8, 5.2)

# Q_freeze: stepwise duration
ax = axes[1, 0]
durations = [5, 15, 30, 60, 360]
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
ax.set_title("(d)  freeze (RLE): stepwise", loc="left")
ax.set_ylim(0.8, 5.2)
for d in durations[:-1]:
    ax.axvline(d, color="0.6", ls=":", lw=0.5)

# Q_freeze: low_var (logistic neg)
ax = axes[1, 1]
x = np.linspace(0, 1, 200)
y = logistic(x, -10, 0.2, "lo_hi")
ax.plot(x, y, color=C["red"], lw=1.8, label="low_var")
y2 = logistic(x, -15, 0.2, "lo_hi")
ax.plot(x, y2, color=C["orange"], lw=1.8, label="unique_ratio", ls="--")
ax.set_xlabel("rel-var / unique-ratio", fontsize=9)
ax.set_ylabel(r"$Q$", fontsize=9)
ax.set_title("(e)  freeze: low_var / unique_ratio", loc="left")
ax.set_ylim(0.8, 5.2)
ax.legend(fontsize=7.5)

# Q_regime: logistic
ax = axes[1, 2]
x = np.linspace(0, 8, 200)
y = logistic(x, 1.2, 3.0)
ax.plot(x, y, color=C["green"], lw=1.8)
ax.set_xlabel("W1 normalised (×IQR)", fontsize=9)
ax.set_ylabel(r"$Q_{regime}$", fontsize=9)
ax.set_title("(f)  regime: logistic k=1.2, x₀=3", loc="left")
ax.set_ylim(0.8, 5.2)

fig.suptitle("Figure 5.  D1 mapping function curves (v1.1)",
              fontsize=11, fontweight="bold", y=1.0)
save(fig, "Fig5_mapping_curves")


# ============================================================================
# Fig 6: Dominant fault per channel (stacked bar)
# ============================================================================
print("[Fig6] Dominant fault per channel ...")
fig, ax = plt.subplots(figsize=(13, 5.5))
dom = S["dominant_v11"]
faults = ["Q_spike", "Q_step", "Q_drift", "Q_freeze", "Q_regime"]
fclr = {"Q_spike": C["amber"], "Q_step": C["blue"], "Q_drift": C["purple"],
        "Q_freeze": C["red"], "Q_regime": C["green"]}
shares = {f: [] for f in faults}
for c in SCORED:
    counts = dom[c].value_counts(normalize=True)
    for f in faults:
        shares[f].append(float(counts.get(f, 0)) * 100)
xs = np.arange(len(SCORED))
bottom = np.zeros(len(SCORED))
for f in faults:
    ax.bar(xs, shares[f], bottom=bottom, color=fclr[f], label=f.replace("Q_", ""),
            alpha=0.92, edgecolor="white", linewidth=0.5)
    bottom += np.array(shares[f])
ax.set_xticks(xs); ax.set_xticklabels(SCORED, rotation=45, ha="right", fontsize=8.5)
ax.set_ylabel("Dominant-fault share (%)", fontsize=9)
ax.set_ylim(0, 120)
ax.set_title("Figure 6.  Dominant fault decomposition per channel (v1.1)",
              loc="left")
ax.legend(loc="upper right", ncol=5, fontsize=8, framealpha=0.92)
save(fig, "Fig6_dominant_fault",
      plot_data={"dominant_share": pd.DataFrame(shares, index=SCORED)})


# ============================================================================
# Fig 7: Daily timeseries by sensor group
# ============================================================================
print("[Fig7] Daily timeseries ...")
fig = plt.figure(figsize=(13, 8))
gs = gridspec.GridSpec(2, 1, figure=fig, hspace=0.32, height_ratios=[1, 1])

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
ax.legend(loc="lower right", ncol=4, fontsize=7.5, framealpha=0.92)
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
ax.legend(loc="lower right", ncol=3, fontsize=7.5, framealpha=0.92)
ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))

fig.suptitle("Figure 7.  Daily $D_1$ trajectories by sensor group (v1.1, DO/ORP only)",
              fontsize=11, fontweight="bold", y=0.99)
save(fig, "Fig7_daily_timeseries", plot_data={"D1_daily": D1_d})


# ============================================================================
# Fig 8: Veto / cooldown activation rate (NEW: state-machine breakdown)
# ============================================================================
print("[Fig8] Veto + state-machine activation rates ...")
fig, ax = plt.subplots(figsize=(13.5, 5.5))
delta_df = S["delta_df"]
xs = np.arange(len(SCORED))
bw = 0.22
# Compute counts per channel
data = []
for c in SCORED:
    vlog = S["veto_logs_v11"][c]
    data.append({
        "Refractory": vlog["cooldown_active"].mean() * 100,
        "Sustained":  vlog["sustained_active"].mean() * 100,
        "Veto3":      vlog["veto3_signal_only"].mean() * 100,
        "VetoFreeze": vlog["veto_freeze"].mean() * 100,
        "VetoRegime": vlog["veto_regime"].mean() * 100,
    })
df_v = pd.DataFrame(data, index=SCORED)
clr_map = {"Refractory": C["orange"], "Sustained": C["purple"],
            "Veto3": C["blue"], "VetoFreeze": C["red"], "VetoRegime": C["green"]}
for i, (k_name, clr) in enumerate(clr_map.items()):
    ax.bar(xs + (i - 2) * bw, df_v[k_name].values, bw, color=clr,
            edgecolor="white", linewidth=0.4, alpha=0.88, label=k_name)
ax.set_xticks(xs); ax.set_xticklabels(SCORED, rotation=45, ha="right", fontsize=8.5)
ax.set_ylabel("Activation rate (%)", fontsize=9.5)
ax.set_ylim(0, 40)
ax.set_title("Figure 8.  Veto and state-machine activation rates per channel (v1.1)",
              loc="left")
ax.legend(loc="upper right", ncol=5, fontsize=8, framealpha=0.92)
save(fig, "Fig8_veto_cooldown",
      plot_data={"activation_rates": df_v})


# ============================================================================
# Fig 9: Harmonic decomposition demonstration  (carry over from STRICT V1)
# ============================================================================
print("[Fig9] Harmonic decomposition ...")
fig, axes = plt.subplots(3, 1, figsize=(13, 8), sharex=True)
fig.subplots_adjust(hspace=0.45)   # room for each panel's own date labels
df_h = S["df_h"]; resid_h = S["resid_h"]
for i, ch in enumerate(["DO_2_3", "ORP_1_1", "ORP_2_1"]):
    ax = axes[i]
    x = df_h[ch].iloc[:24*7]   # 7 days
    r = resid_h[ch].iloc[:24*7]
    seasonal = x - r
    ax.plot(x.index, x.values, color=C["gray"], lw=0.6, alpha=0.65,
            label=f"{ch} raw hourly mean")
    ax.plot(seasonal.index, seasonal.values, color=C["blue"], lw=1.2, alpha=0.92,
            label="harmonic seasonal (daily T=24h + weekly T=168h, 3 each)")
    ax.plot(r.index, r.values, color=C["red"], lw=0.7, alpha=0.85,
            label="residual after harmonic removal")
    ax.set_ylabel(ch, fontsize=9.5)
    ax.axhline(0, color="0.5", lw=0.4, alpha=0.5)
    # add top headroom so the (full-width) legend sits above the data, not over it
    _y0, _y1 = ax.get_ylim()
    ax.set_ylim(_y0, _y1 + 0.32 * (_y1 - _y0))
    ax.legend(loc="upper right", fontsize=7.5, ncol=3, framealpha=0.9)
# each panel carries its own date labels (was shared via sharex → only bottom)
for ax in axes:
    ax.tick_params(axis="x", labelbottom=True)
fig.suptitle("Figure 9.  Harmonic decomposition demonstration (first 7 days)",
              fontsize=11, fontweight="bold", y=0.995)
save(fig, "Fig9_harmonic_demo")


# ============================================================================
# Fig 10: Two-tier regime visualization
# ============================================================================
print("[Fig10] Two-tier regime ...")
fig, axes = plt.subplots(2, 1, figsize=(13, 7), sharex=True)
fig.subplots_adjust(hspace=0.42)   # room for each panel's own date labels
ch = "DO_2_3"
det_raw = S["detectors_raw"]
w1 = det_raw["w1_normalised_hourly"][ch]
ks = det_raw["ks_statistic_hourly"][ch]
qregime = subs_v11[ch]["Q_regime"]

ax = axes[0]
ax.plot(w1.index, w1.values, color=C["red"], lw=0.5, alpha=0.85,
        label="W1 normalised (Tier-1)")
ax.fill_between(w1.index, 0, w1.values, where=w1.values > 3,
                 color=C["red"], alpha=0.15, label="Tier-1 active (W1>3)")
ax.set_ylabel("W1 normalised", fontsize=9.5)
ax.set_yscale("symlog", linthresh=2)
ax.set_title(f"(a)  Tier-1 W1 distance — {ch}", loc="left")
ax.legend(loc="upper left", fontsize=7.5)

ax = axes[1]
ax.plot(ks.index, ks.values, color=C["blue"], lw=0.5, alpha=0.85,
        label="adjacent KS statistic (Tier-2)")
ax.fill_between(ks.index, 0, ks.values, where=ks.values > 0.3,
                 color=C["blue"], alpha=0.15, label="Tier-2 active (KS>0.3)")
ax.set_ylabel("adjacent KS", fontsize=9.5)
ax.set_title(f"(b)  Tier-2 adjacent KS — {ch}", loc="left")
ax.legend(loc="upper left", fontsize=7.5)
# each panel carries its own date labels (was shared via sharex → only bottom)
for _ax in axes:
    _ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    _ax.tick_params(axis="x", labelbottom=True)

fig.suptitle(f"Figure 10.  Two-tier regime detector outputs — {ch} (v1.1)",
              fontsize=11, fontweight="bold", y=0.995)
save(fig, "Fig10_two_tier_regime")


# ============================================================================
# Fig 11: PLS peer audit (engineered peers)
# ============================================================================
print("[Fig11] PLS peer audit ...")
fig, axes = plt.subplots(1, 2, figsize=(13, 5.5))
# (a) Peer matrix for DO targets
peer_matrix = pd.DataFrame(0, index=DO_CH, columns=SCORED, dtype=int)
for t in DO_CH:
    p, seg = t.split("_")[1], int(t.split("_")[2])
    peers = []
    # Rule 1: same-pool adjacent
    if seg > 1: peers.append(f"DO_{p}_{seg-1}")
    if seg < 4: peers.append(f"DO_{p}_{seg+1}")
    orp_seg = min(seg, 3)
    peers.append(f"ORP_{p}_{orp_seg}")
    # Rule 2: twin-pool counterpart
    p_twin = "2" if p == "1" else "1"
    peers.append(f"DO_{p_twin}_{seg}")
    # Rule 3: exogenous flow (NOT in current scored set, but historic peers)
    # NOTE: in v1.1 PLS is peer-only per QR/QIR 修订 §四 — no QR/QIR
    # We mark with light shade for completeness
    for pp in peers:
        if pp in peer_matrix.columns:
            peer_matrix.at[t, pp] = 1
ax = axes[0]
im = ax.imshow(peer_matrix.values, cmap="Blues", aspect="auto", vmin=0, vmax=1)
ax.set_yticks(np.arange(len(DO_CH))); ax.set_yticklabels(DO_CH, fontsize=8)
ax.set_xticks(np.arange(len(SCORED))); ax.set_xticklabels(SCORED, rotation=70, fontsize=7.5)
ax.set_title("(a)  PLS peer matrix for DO targets (peer-only mode in v1.1)", loc="left")
ax.grid(False)

# (b) ORP peer matrix
peer_matrix2 = pd.DataFrame(0, index=ORP_CH, columns=SCORED, dtype=int)
for t in ORP_CH:
    p, seg = t.split("_")[1], int(t.split("_")[2])
    peers = []
    if seg > 1: peers.append(f"ORP_{p}_{seg-1}")
    if seg < 3: peers.append(f"ORP_{p}_{seg+1}")
    peers.append(f"DO_{p}_{seg}")
    p_twin = "2" if p == "1" else "1"
    peers.append(f"ORP_{p_twin}_{seg}")
    for pp in peers:
        if pp in peer_matrix2.columns:
            peer_matrix2.at[t, pp] = 1
ax = axes[1]
im = ax.imshow(peer_matrix2.values, cmap="Greens", aspect="auto", vmin=0, vmax=1)
ax.set_yticks(np.arange(len(ORP_CH))); ax.set_yticklabels(ORP_CH, fontsize=8)
ax.set_xticks(np.arange(len(SCORED))); ax.set_xticklabels(SCORED, rotation=70, fontsize=7.5)
ax.set_title("(b)  PLS peer matrix for ORP targets (peer-only mode in v1.1)", loc="left")
ax.grid(False)

fig.suptitle("Figure 11.  Engineered PLS peer matrix (v1.1: peer-only, no QR/QIR exogenous)",
              fontsize=11, fontweight="bold", y=1.02)
save(fig, "Fig11_pls_peer_audit",
      plot_data={"DO_peer_matrix": peer_matrix,
                  "ORP_peer_matrix": peer_matrix2})

print("\n[done] Updated baseline figures Fig 1-11 complete.\n")
