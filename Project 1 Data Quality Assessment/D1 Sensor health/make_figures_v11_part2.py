"""make_figures_v11_part2.py — V16-V18 + updated Fig 1-11 baselines

Continues from make_figures_v11.py.
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
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle, Patch, FancyArrowPatch

OUT = ROOT / "outputs" / "figures"
PLOTDATA = ROOT / "outputs" / "plot_data"

# Same SCI rcParams
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
STATE_COL = {"Normal":"#1B7837","Refractory":"#F46D43","SustainedAnomaly":"#762A83",
             "RecoveryCandidate":"#FDDBC7","Recovered":"#2166AC"}

with open(ROOT / "v11_state.pkl", "rb") as f:
    S = pickle.load(f)

SCORED = S["scored_channels"]
SUPPORT = S["support_channels"]
DO_CH = [c for c in SCORED if c.startswith("DO_")]
ORP_CH = [c for c in SCORED if c.startswith("ORP_")]
D1_v1 = S["D1_v1_scored"]
D1_v11 = S["D1_v11"]


def _finish_axes(fig):
    """Draw tick marks at both ends of every data axis (the default locator
    leaves the spine ends bare). Endpoints are added as same-size minor ticks."""
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
                continue
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


# ============================================================================
# Figure V16 — D7 multi-regime templates (NOT for D1 scoring)
# ============================================================================
print("[V16] Multi-regime templates ...")
fig = plt.figure(figsize=(13.5, 8))
gs = gridspec.GridSpec(3, 2, figure=fig, hspace=0.5, wspace=0.55,
                        height_ratios=[1.0, 1.1, 1.0])
fig.subplots_adjust(left=0.09, right=0.93)

regime_labels = S["regime_labels"]
regime_info = S["regime_info"]
templates = S["regime_templates"]
df_h = S["df_h"]
k = regime_info["k"]
cmap = plt.cm.Set2
clrs = [cmap(i / max(k-1, 1)) for i in range(k)]

# (a) Regime label timeline
ax = fig.add_subplot(gs[0, :])
for r in range(k):
    mask = regime_labels == r
    ax.fill_between(regime_labels.index, 0, mask.astype(float),
                     where=mask, alpha=0.85, color=clrs[r],
                     label=f"R{r}  ({mask.sum()} h, {mask.mean()*100:.1f}%)",
                     step="mid")
ax.set_ylim(0, 1.05); ax.set_yticks([])
ax.set_title("(a)  Regime label timeline (k-means k=4) — used for D7 templates only",
              loc="left")
ax.legend(loc="upper right", fontsize=7.5, ncol=k, framealpha=0.95)
ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))

# (b) Centers heatmap (DO/ORP only)
ax = fig.add_subplot(gs[1, 0])
do_cols = DO_CH + ORP_CH
centers_do = pd.DataFrame()
for r in range(k):
    if r in templates:
        row = {c: templates[r]["centers"].get(c, np.nan) for c in do_cols}
        centers_do[f"R{r}"] = pd.Series(row)
centers_z = centers_do.subtract(centers_do.mean(axis=1), axis=0).divide(
    centers_do.std(axis=1) + 1e-6, axis=0)
im = ax.imshow(centers_z.values, cmap="RdBu_r", aspect="auto", vmin=-2, vmax=2)
ax.set_yticks(np.arange(len(do_cols))); ax.set_yticklabels(do_cols, fontsize=7.5)
ax.set_xticks(np.arange(k)); ax.set_xticklabels([f"R{i}" for i in range(k)], fontsize=8)
cbar = plt.colorbar(im, ax=ax, fraction=0.045, pad=0.02)
cbar.set_label("z-score across regimes", fontsize=8); cbar.ax.tick_params(labelsize=7)
ax.set_title("(b)  DO/ORP regime centers (z-scored)", loc="left")
ax.grid(False)

# (c) Twin-pool symmetry
ax = fig.add_subplot(gs[1, 1])
sym_data = []
for r in range(k):
    if r in templates:
        for s in templates[r]["symmetry"]:
            sym_data.append({"regime": f"R{r}", "pair": s["pair"], "corr": s["corr"]})
sym_df = pd.DataFrame(sym_data)
if len(sym_df) > 0:
    pivot = sym_df.pivot(index="pair", columns="regime", values="corr").fillna(0)
    im = ax.imshow(pivot.values, cmap="RdYlGn", aspect="auto", vmin=-1, vmax=1)
    ax.set_yticks(np.arange(len(pivot)))
    ax.set_yticklabels(pivot.index.tolist(), fontsize=7)
    ax.set_xticks(np.arange(len(pivot.columns)))
    ax.set_xticklabels(pivot.columns.tolist(), fontsize=8)
    for i in range(len(pivot)):
        for j in range(len(pivot.columns)):
            v = pivot.values[i, j]
            ax.text(j, i, f"{v:.2f}", ha="center", va="center",
                      fontsize=7, color="white" if abs(v) > 0.6 else "black")
    cbar = plt.colorbar(im, ax=ax, fraction=0.045, pad=0.02)
    cbar.set_label("twin-pair correlation", fontsize=8); cbar.ax.tick_params(labelsize=7)
ax.set_title("(c)  Twin-pool symmetry (DO_1_*↔DO_2_*; ORP)", loc="left")
ax.grid(False)

# (d) D1 distribution per regime — violin
ax = fig.add_subplot(gs[2, :])
median_d1 = D1_v11.median(axis=1)
for r in range(k):
    mask = regime_labels == r
    if mask.sum() < 30: continue
    vals = median_d1[mask].dropna().values
    parts = ax.violinplot(vals, positions=[r], widths=0.7,
                            showmedians=True, showextrema=False)
    for body in parts["bodies"]:
        body.set_facecolor(clrs[r]); body.set_edgecolor("0.3"); body.set_alpha(0.85)
    parts["cmedians"].set_color("k"); parts["cmedians"].set_linewidth(1.2)
ax.set_xticks(range(k))
ax.set_xticklabels([f"R{i}\n({(regime_labels==i).mean()*100:.0f}%)" for i in range(k)])
ax.set_ylabel(r"Median $D_1$ across DO/ORP", fontsize=9)
ax.axhline(3, color=C["red"], ls=":", lw=0.7); ax.set_ylim(2, 5)
ax.set_title("(d)  v1.1 $D_1$ distribution per regime (template seeding mass)",
              loc="left")

fig.suptitle("Figure V16.  Multi-regime templates for D7 (offline; NOT D1 scoring)",
              fontsize=11.5, fontweight="bold", y=1.0)
save(fig, "FigV16_regime_templates",
      plot_data={"regime_centers_z": centers_z, "twin_symmetry": sym_df,
                  "regime_summary": pd.DataFrame({
                      f"R{r}": [(regime_labels==r).sum(),
                                  (regime_labels==r).mean(),
                                  templates.get(r, {}).get("n_hours_used", 0)]
                      for r in range(k)},
                      index=["n_hours", "time_pct", "n_high_quality_h"]).T})


# ============================================================================
# Figure V17 — QR/QIR side annotations + scope diagram
# ============================================================================
print("[V17] QR/QIR scope (DO/ORP only main link) ...")
fig = plt.figure(figsize=(13.5, 8))
gs = gridspec.GridSpec(3, 2, figure=fig, hspace=0.55, wspace=0.30,
                        height_ratios=[1.2, 1.0, 1.0])

# (a) Scope diagram (illustrative)
ax = fig.add_subplot(gs[0, :])
ax.set_xlim(0, 12); ax.set_ylim(0, 5)
ax.axis("off")
# Three boxes: scored, support, future extension
b1 = Rectangle((0.3, 1.3), 3.4, 3.0, facecolor="#D1E5F0", edgecolor=C["blue"], lw=1.4)
ax.add_patch(b1)
ax.text(2.0, 3.95, "SCORED MAIN LINK", ha="center", va="center",
        fontsize=10.5, fontweight="bold", color=C["navy"])
ax.text(2.0, 3.55, "(D1 v1.1)", ha="center", va="center",
        fontsize=8.5, style="italic", color=C["navy"])
ax.text(2.0, 2.4,
        "DO_1_1, DO_1_2, DO_1_3, DO_1_4\nDO_2_1, DO_2_2, DO_2_3, DO_2_4\n"
        "ORP_1_1, ORP_1_2, ORP_1_3\nORP_2_1, ORP_2_2, ORP_2_3\n"
        "(n = 14 channels)",
        ha="center", va="center", fontsize=8.0)

b2 = Rectangle((4.3, 1.3), 3.4, 3.0, facecolor="#FDDBC7", edgecolor=C["amber"], lw=1.4)
ax.add_patch(b2)
ax.text(6.0, 3.95, "SUPPORT DATA", ha="center", va="center",
        fontsize=10.5, fontweight="bold", color=C["amber"])
ax.text(6.0, 3.55, "(NOT scored)", ha="center", va="center",
        fontsize=8.5, style="italic", color=C["amber"])
ax.text(6.0, 2.4,
        "QR_1, QR_2\nQIR_1, QIR_2\n(n = 4 channels)\n\n"
        "Used for D5/D7 modelling\n+ offline annotation only",
        ha="center", va="center", fontsize=8.0)

b3 = Rectangle((8.3, 1.3), 3.4, 3.0, facecolor="#EDEDED", edgecolor=C["gray"],
                lw=1.0, linestyle="--")
ax.add_patch(b3)
ax.text(10.0, 3.95, "FUTURE EXTENSION", ha="center", va="center",
        fontsize=10.5, fontweight="bold", color=C["gray"])
ax.text(10.0, 3.55, "(disabled in v1.1)", ha="center", va="center",
        fontsize=8.5, style="italic", color=C["gray"])
ax.text(10.0, 2.4,
        "Pump status\nValve status\nRunning logs\n   ↓\nenable process-aware\nVeto-3 / RL aux",
        ha="center", va="center", fontsize=8.0, color=C["gray"])

ax.annotate("", xy=(4.3, 2.85), xytext=(3.7, 2.85),
              arrowprops=dict(arrowstyle="->", lw=1.8, color="0.4"))
ax.annotate("", xy=(8.3, 2.85), xytext=(7.7, 2.85),
              arrowprops=dict(arrowstyle="->", lw=1.5, color="0.5", linestyle="--"))
ax.text(4.0, 3.10, "feeds", ha="center", fontsize=7.5, color="0.4", fontweight="bold")
ax.text(8.0, 3.10, "future", ha="center", fontsize=7.5, color="0.5", fontweight="bold")

ax.text(6.0, 0.65, "Per QR/QIR scoping spec (Apr 2026 revision):",
         ha="center", fontsize=8.5, style="italic", color="0.3")
ax.text(6.0, 0.20, "QR/QIR are NOT scored in D1 main link. They feed D5 (mechanistic consistency), "
         "D7 (regime templates), and offline case-study annotations only.",
         ha="center", fontsize=7.5, color="0.5")
ax.set_title("(a)  D1 v1.1 scoring scope — DO/ORP only main link (n=14)", loc="left")

# (b) QR/QIR jump annotation timeline
ax = fig.add_subplot(gs[1, :])
ann = S["qr_qir_annotations"]
qr_jumps = ann["qr_jump_annotation"] != ""
qir_jumps = ann["qir_jump_annotation"] != ""
qr_per_day = qr_jumps.resample("1D").sum()
qir_per_day = qir_jumps.resample("1D").sum()
ax.bar(qr_per_day.index, qr_per_day.values, width=0.7, color=C["teal"],
        alpha=0.65, label=f"QR_* jumps (n={int(qr_jumps.sum())})", edgecolor="white")
ax.bar(qir_per_day.index, -qir_per_day.values, width=0.7, color=C["red"],
        alpha=0.65, label=f"QIR_* jumps (n={int(qir_jumps.sum())})", edgecolor="white")
ax.axhline(0, color="0.3", lw=0.5)
ax.set_ylabel("# jumps per day", fontsize=9)
ax.set_title("(b)  Driver-variable jump density timeline (offline annotation, "
              "NOT scored)", loc="left")
ax.legend(loc="upper left", fontsize=8)
ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))

# (c) QR/QIR raw timelines
ax = fig.add_subplot(gs[2, :])
for c, clr in zip(SUPPORT, [C["blue"], C["red"], C["green"], C["amber"]]):
    if c in df_h.columns:
        # Show hourly mean rolling 24h
        x = df_h[c].rolling(24, center=True, min_periods=12).mean()
        # Normalise for display
        x_norm = (x - x.median()) / (x.std() + 1e-6)
        ax.plot(x.index, x_norm.values, color=clr, lw=0.5, alpha=0.85, label=c)
ax.set_ylabel("normalised flow (z-score)", fontsize=9)
ax.set_ylim(-3, 3)
ax.set_title("(c)  QR/QIR raw timelines (z-scored, 24h rolling) — for offline reference",
              loc="left")
ax.legend(loc="upper right", fontsize=8, ncol=4)
ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))

fig.suptitle("Figure V17.  D1 v1.1 scope — DO/ORP scored, QR/QIR offline-support",
              fontsize=11.5, fontweight="bold", y=1.0)
save(fig, "FigV17_scope_qr_qir_offline",
      plot_data={"jumps_per_day": pd.DataFrame({"QR": qr_per_day, "QIR": qir_per_day}),
                  "annotations_summary": pd.Series({
                      "qr_jumps": int(qr_jumps.sum()),
                      "qir_jumps": int(qir_jumps.sum())}).to_frame("count")})


# ============================================================================
# Figure V18 — Aggregate v1.0 vs v1.1 final summary
# ============================================================================
print("[V18] Aggregate summary ...")
fig = plt.figure(figsize=(13.5, 7.5))
gs = gridspec.GridSpec(2, 3, figure=fig, hspace=0.45, wspace=0.32,
                        height_ratios=[1.0, 1.0])

# (a) Hourly D1 distribution
ax = fig.add_subplot(gs[0, 0])
v1_flat = D1_v1.values.flatten(); v11_flat = D1_v11.values.flatten()
v1_flat = v1_flat[~np.isnan(v1_flat)]
v11_flat = v11_flat[~np.isnan(v11_flat)]
bins = np.linspace(1, 5, 60)
ax.hist(v1_flat, bins=bins, color=C["gray"], alpha=0.6,
         label=f"STRICT V1 DO/ORP (μ={v1_flat.mean():.3f})", density=True)
ax.hist(v11_flat, bins=bins, color=C["blue"], alpha=0.55,
         label=f"v1.1 (μ={v11_flat.mean():.3f})", density=True)
ax.axvline(3, color=C["red"], ls=":", lw=0.7, alpha=0.7, label="grade boundary")
_dens_max = max(np.histogram(v1_flat, bins=bins, density=True)[0].max(),
                np.histogram(v11_flat, bins=bins, density=True)[0].max())
ax.set_ylim(0, _dens_max * 1.50)
ax.set_xlabel(r"Hourly $D_1$", fontsize=9); ax.set_ylabel("Density", fontsize=9)
ax.set_title("(a)  Hourly $D_1$ distribution", loc="left")
ax.legend(loc="upper left", fontsize=7.5)

# (b) Grade percentage stacked
ax = fig.add_subplot(gs[0, 1])
def grade_dist(arr):
    a = (arr >= 4.5).mean()
    b = ((arr >= 3.5) & (arr < 4.5)).mean()
    c = ((arr >= 2.5) & (arr < 3.5)).mean()
    d = ((arr >= 1.5) & (arr < 2.5)).mean()
    f = (arr < 1.5).mean()
    return [a, b, c, d, f]
gd_v1 = grade_dist(v1_flat); gd_v11 = grade_dist(v11_flat)
labels_g = ["A (≥4.5)", "B (3.5-4.5)", "C (2.5-3.5)", "D (1.5-2.5)", "F (<1.5)"]
gclrs = ["#1A9850", "#A6D96A", "#FEE08B", "#F46D43", "#9E1F1F"]
xpos = [0, 1]
bottom = np.zeros(2)
for i, (lbl, clr) in enumerate(zip(labels_g, gclrs)):
    vals = [gd_v1[i] * 100, gd_v11[i] * 100]
    ax.bar(xpos, vals, bottom=bottom, color=clr, edgecolor="white",
            label=lbl, width=0.45, alpha=0.92)
    for x, v, b in zip(xpos, vals, bottom):
        if v > 3:
            ax.text(x, b + v/2, f"{v:.1f}%", ha="center", va="center",
                     fontsize=8, fontweight="bold", color="black")
    bottom += np.array(vals)
ax.set_xticks(xpos); ax.set_xticklabels(["STRICT V1\n(DO/ORP only)", "v1.1"])
ax.set_ylabel("Grade percentage (%)", fontsize=9)
ax.set_title("(b)  Grade distribution", loc="left")
# bars sit at x=0,1 — free space on the right and put the legend there (was
# overlapping the v1.1 bar at lower-right)
ax.set_xlim(-0.55, 2.45)
ax.set_ylim(0, 100)
ax.legend(loc="center right", fontsize=7, framealpha=0.95)

# (c) State machine vs simple timer — Q_drift_eff effect
ax = fig.add_subplot(gs[0, 2])
# Compute mean Q_drift_eff vs raw Q_drift across channels
qd_v1_mean = {c: float(S["subs_v1"]["Q_drift"][c].mean()) for c in SCORED}
qd_v11_mean = {c: float(S["Q_drift_eff_dict"][c].mean()) for c in SCORED}
xs = np.arange(len(SCORED))
ax.bar(xs - 0.2, [qd_v1_mean[c] for c in SCORED], 0.4, color=C["gray"],
        alpha=0.85, label="$Q_{drift}$ raw (V1)", edgecolor="white")
ax.bar(xs + 0.2, [qd_v11_mean[c] for c in SCORED], 0.4, color=C["purple"],
        alpha=0.85, label="$Q_{drift}^{eff}$ (v1.1, α-thaw)", edgecolor="white")
ax.set_xticks(xs); ax.set_xticklabels(SCORED, rotation=45, ha="right", fontsize=7.2)
ax.set_ylabel(r"Mean $Q_{\rm drift}$", fontsize=9)
ax.axhline(3.0, color=C["amber"], ls="--", lw=0.7, alpha=0.6,
            label="neutral 3.0")
ax.set_ylim(0, 6.0)
ax.set_title("(c)  $Q_{\\rm drift}$ raw vs effective (α-thaw)", loc="left")
ax.legend(loc="upper right", fontsize=7.5)

# (d) Per-channel D1 v1 vs v11 scatter coloured by sensor type
ax = fig.add_subplot(gs[1, :2])
for c in SCORED:
    clr = C["blue"] if c.startswith("DO_") else C["green"]
    n_show = 800
    sample = np.random.RandomState(42).choice(len(D1_v1), n_show, replace=False)
    ax.scatter(D1_v1[c].values[sample], D1_v11[c].values[sample],
                color=clr, marker="o", s=4, alpha=0.18, rasterized=True)
ax.plot([1, 5], [1, 5], "k--", lw=0.7, alpha=0.7)
ax.set_xlabel("STRICT V1 hourly $D_1$", fontsize=9)
ax.set_ylabel("v1.1 hourly $D_1$", fontsize=9)
ax.set_title("(d)  Hourly $D_1$ scatter (800 samples / channel)", loc="left")
ax.set_xlim(1, 5); ax.set_ylim(1, 5)
hndl = [Line2D([], [], marker="o", color=C["blue"], linestyle="", label="DO"),
         Line2D([], [], marker="o", color=C["green"], linestyle="", label="ORP")]
ax.legend(handles=hndl, loc="upper left", fontsize=7.5)

# (e) Event count comparison
ax = fig.add_subplot(gs[1, 2])
v11_dom = {"Q_spike":0,"Q_step":0,"Q_drift":0,"Q_freeze":0,"Q_regime":0}
for _, ev in S["events_v11"].iterrows():
    c = ev["sensor_id"]
    s = pd.DataFrame({k: S["subs_v11"][c][k].loc[ev["start"]:ev["end"]]
                       for k in v11_dom})
    if len(s) == 0: continue
    dom = s.mean(axis=0).idxmin()
    v11_dom[dom] += 1
faults = ["spike","step","drift","freeze","regime"]
v11_counts = [v11_dom.get(f"Q_{f}", 0) for f in faults]
xs = np.arange(len(faults)); bw = 0.55
ax.bar(xs, v11_counts, bw, color=C["blue"], alpha=0.85,
        label=f"v1.1 (total={sum(v11_counts)})")
for i, b in enumerate(v11_counts):
    if b > 0: ax.text(i, b + 2, str(b), ha="center", fontsize=7.5)
ax.set_xticks(xs); ax.set_xticklabels(faults, fontsize=8)
ax.set_ylabel("# events", fontsize=9)
ax.set_title("(e)  Events by dominant fault (v1.1)", loc="left")
ax.legend(fontsize=7.5)

fig.suptitle("Figure V18.  D1 v1.1 vs STRICT V1 — final aggregate summary",
              fontsize=11.5, fontweight="bold", y=1.0)
save(fig, "FigV18_aggregate_summary",
      plot_data={"hourly_D1": pd.DataFrame({"v1_describe": pd.Series(v1_flat).describe(),
                                              "v11_describe": pd.Series(v11_flat).describe()}),
                  "grade_dist": pd.DataFrame({"v1": gd_v1, "v11": gd_v11}, index=labels_g),
                  "qdrift_compare": pd.DataFrame({"v1": qd_v1_mean, "v11_eff": qd_v11_mean}),
                  "fault_counts": pd.DataFrame({"v11": v11_counts}, index=faults)})


print("\n[part 2 done] V16-V18 complete.\n")
