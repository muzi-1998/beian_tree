"""src/outputs/figure_maker.py
SCI publication-grade figures for D1 FSD module.

All figures match the project's existing palette (adaptive_s1_pca_spe_EN.py).
Plot data is also saved to Excel for self-replotting.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.ticker import AutoMinorLocator
from matplotlib.patches import Patch, Rectangle
from pathlib import Path


# ── SCI Publication Style (sync with adaptive_s1_*.py) ────────────────────
plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 9,
    "axes.titlesize": 10, "axes.labelsize": 9,
    "xtick.labelsize": 8, "ytick.labelsize": 8, "legend.fontsize": 8,
    "figure.dpi": 150, "savefig.dpi": 300, "savefig.bbox": "tight",
    "axes.linewidth": 0.8, "axes.grid": True, "grid.alpha": 0.25,
    "grid.linewidth": 0.5, "lines.linewidth": 1.0,
    "axes.spines.top": False, "axes.spines.right": False,
})

C = {
    "blue":   "#2166AC", "red":    "#D6604D", "green":  "#4DAC26",
    "orange": "#F4A582", "purple": "#762A83", "gray":   "#878787",
    "teal":   "#1B7837", "amber":  "#E08214", "navy":   "#053061",
    "cyan":   "#35978F",
}

# Colour map for fault types (consistent across all figures)
FAULT_COLOR = {
    "spike":  C["red"],
    "step":   C["amber"],
    "drift":  C["blue"],
    "freeze": C["purple"],
    "regime": C["teal"],
}

# Heat colour map for D1 grading
D1_CMAP = "RdYlGn"  # red→yellow→green for low→high quality


# ─────────────────────────────────────────────────────────────────────────
# Fig 1. D1 dimension matrix (analogous to user's reference image)
# ─────────────────────────────────────────────────────────────────────────
def fig1_d1_dimension_matrix(R, out_path: Path):
    """Schematic of 5 sub-scores × 5 score levels with their weights."""
    weights = R["cfg"].rules.aggregation.weights
    dims = ["Q_spike", "Q_step", "Q_drift", "Q_freeze", "Q_regime"]
    dim_labels = ["spike", "step", "drift", "freeze", "regime"]
    w_vals = [weights[d] for d in dims]

    fig, ax = plt.subplots(figsize=(11, 5.5))
    ax.set_xlim(0, len(dims) + 1)
    ax.set_ylim(0, 6)
    ax.axis("off")

    # Header colour bands by weight
    weight_colors = ["#21618C", "#2980B9", "#3498DB", "#5DADE2", "#85C1E9"]
    sorted_idx = np.argsort(w_vals)[::-1]
    color_map = dict(zip(sorted_idx, weight_colors))

    cell_w, cell_h = 1.0, 1.0
    pad = 0.05
    # weight header
    for i, (d, lab, w_val) in enumerate(zip(dims, dim_labels, w_vals)):
        rect = Rectangle((i + 0.5 + pad, 5 + pad), cell_w - 2 * pad, cell_h - 2 * pad,
                         facecolor=color_map[i], alpha=0.85, edgecolor="white", lw=1.5,
                         transform=ax.transData)
        ax.add_patch(rect)
        ax.text(i + 1, 5.5, f"{w_val:.2f}", ha="center", va="center",
                color="white", fontsize=12, fontweight="bold")

    # 5 score rows × 5 dims  — colour: green for high, red for low
    score_label_color = ["#85929E", "#A6ACAF", "#CACFD2", "#D5D8DC", "#E5E7E9"]
    for s_idx, score in enumerate([5, 4, 3, 2, 1]):
        # left score label (pink-red for low scores)
        score_color = ["#C0392B", "#E74C3C", "#F1948A", "#F8BBD0", "#F5B7B1"][4 - s_idx]
        rect_l = Rectangle((0 + pad, (4 - s_idx) + pad),
                           0.5 - 2 * pad, cell_h - 2 * pad,
                           facecolor=score_color, alpha=0.85, edgecolor="white", lw=1.0)
        ax.add_patch(rect_l)
        ax.text(0.25, (4 - s_idx) + 0.5, str(score), ha="center", va="center",
                color="white", fontsize=11, fontweight="bold")
        # 5 cells per row
        for d_idx in range(len(dims)):
            rect = Rectangle((d_idx + 0.5 + pad, (4 - s_idx) + pad),
                             cell_w - 2 * pad, cell_h - 2 * pad,
                             facecolor="#ECF0F1", edgecolor="#BDC3C7", lw=0.8)
            ax.add_patch(rect)

    # x-axis dimension labels (yellow band)
    for i, lab in enumerate(dim_labels):
        rect = Rectangle((i + 0.5 + pad, 0 - 0.6 + pad),
                         cell_w - 2 * pad, 0.5 - 2 * pad,
                         facecolor="#F9E79F", edgecolor="white", lw=1.0)
        ax.add_patch(rect)
        ax.text(i + 1, -0.35, lab, ha="center", va="center",
                fontsize=10, color="#5D4037")

    # Outer brackets
    ax.text(0.05, 2.5, "Score", ha="right", va="center", fontsize=11, fontweight="bold",
            color="#34495E")
    ax.text(3.0, 6.4, "Weight", ha="center", va="center", fontsize=12, fontweight="bold",
            color="#34495E")
    ax.text(3.0, -0.95, "Dimension (sub-score)", ha="center", va="center",
            fontsize=11, fontweight="bold", color="#5D4037")
    ax.text(3.0, -1.3, f"D1_total = λ·Σwᵢ·Qᵢ + (1-λ)·min(Qᵢ),  λ = {R['cfg'].rules.aggregation.lambda_blend}",
            ha="center", va="center", fontsize=9, style="italic", color="#5D4037")

    fig.suptitle("Fig. 1 — D1 Fault-Spectrum Decomposition: 5 sub-scores × 5 score levels with mixing weights",
                 fontsize=11, fontweight="bold", y=0.97)
    plt.tight_layout()
    plt.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close()

    # Plot data
    plot_data = pd.DataFrame({
        "dimension": dim_labels, "weight": w_vals,
        "rank": [int(np.where(np.argsort(w_vals)[::-1] == i)[0][0]) + 1
                 for i in range(len(dims))],
    })
    return out_path, plot_data


# ─────────────────────────────────────────────────────────────────────────
# Fig 2. Per-channel monthly heatmap of D1_total
# ─────────────────────────────────────────────────────────────────────────
def fig2_monthly_heatmap(R, out_path: Path):
    """18 channels × monthly mean D1_total."""
    d1_d = R["D1_h"].resample("1D").mean()
    monthly = d1_d.resample("MS").mean().T  # channels × months

    fig, ax = plt.subplots(figsize=(11, 6))
    im = ax.imshow(monthly.values, cmap=D1_CMAP, vmin=1, vmax=5,
                   aspect="auto", interpolation="nearest")

    ax.set_xticks(range(len(monthly.columns)))
    ax.set_xticklabels([d.strftime("%Y-%m") for d in monthly.columns],
                       rotation=45, ha="right")
    ax.set_yticks(range(len(monthly.index)))
    ax.set_yticklabels(monthly.index, fontsize=8)
    # Colour different sensor groups
    for i, s in enumerate(monthly.index):
        if s.startswith("DO_"):
            ax.get_yticklabels()[i].set_color(C["blue"])
        elif s.startswith("ORP_"):
            ax.get_yticklabels()[i].set_color(C["teal"])
        else:
            ax.get_yticklabels()[i].set_color(C["red"])

    cbar = plt.colorbar(im, ax=ax, label="D1_total (1=poor, 5=excellent)",
                        shrink=0.85)
    cbar.ax.tick_params(labelsize=8)
    # Cell annotations
    for i in range(monthly.shape[0]):
        for j in range(monthly.shape[1]):
            v = monthly.values[i, j]
            if not np.isnan(v):
                txt_color = "white" if v < 2.5 else "black"
                ax.text(j, i, f"{v:.1f}", ha="center", va="center",
                        color=txt_color, fontsize=7)

    ax.set_title("Fig. 2 — Monthly mean D1_total per channel (Aug 2025 – Apr 2026)",
                 fontsize=11, fontweight="bold")
    ax.set_xlabel("Month")
    ax.set_ylabel("Channel  (blue=DO, teal=ORP, red=Flow)")
    plt.tight_layout()
    plt.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close()
    return out_path, monthly


# ─────────────────────────────────────────────────────────────────────────
# Fig 3. Sub-score time-series for the 4 case sensors
# ─────────────────────────────────────────────────────────────────────────
def fig3_case_subscores(R, case_sensors, out_path: Path):
    """For each case sensor: 6-row stacked plot — 5 sub-scores + D1_total."""
    fig, axes = plt.subplots(len(case_sensors), 1,
                             figsize=(12, 2.4 * len(case_sensors)),
                             sharex=True)
    if len(case_sensors) == 1:
        axes = [axes]

    plot_data = {}
    for ax, c in zip(axes, case_sensors):
        if c not in R["D1_h"].columns:
            ax.text(0.5, 0.5, f"{c}: N/A", ha="center", transform=ax.transAxes)
            continue
        s = R["subs"][c]
        d1 = R["D1_h"][c]
        # Plot 5 sub-scores faintly, D1_total bold
        ax.plot(s["Q_spike"].index,  s["Q_spike"].values,  color=FAULT_COLOR["spike"],  alpha=0.5, lw=0.7, label="Q_spike")
        ax.plot(s["Q_step"].index,   s["Q_step"].values,   color=FAULT_COLOR["step"],   alpha=0.5, lw=0.7, label="Q_step")
        ax.plot(s["Q_drift"].index,  s["Q_drift"].values,  color=FAULT_COLOR["drift"],  alpha=0.5, lw=0.7, label="Q_drift")
        ax.plot(s["Q_freeze"].index, s["Q_freeze"].values, color=FAULT_COLOR["freeze"], alpha=0.5, lw=0.7, label="Q_freeze")
        ax.plot(s["Q_regime"].index, s["Q_regime"].values, color=FAULT_COLOR["regime"], alpha=0.5, lw=0.7, label="Q_regime")
        ax.plot(d1.index, d1.values, color="black", lw=1.4, label="D1_total")

        # Reference lines at grade thresholds
        ax.axhline(3.0, color="gray", lw=0.6, ls="--", alpha=0.6)
        ax.axhline(2.0, color="gray", lw=0.6, ls=":", alpha=0.5)

        ax.set_ylim(0.8, 5.2)
        ax.set_yticks([1, 2, 3, 4, 5])
        ax.set_ylabel(f"{c}\nD1 score")
        ax.text(0.01, 0.95, f"{c}  (mean D1 = {d1.mean():.2f}, low<3 = {(d1<3).mean()*100:.0f}%)",
                transform=ax.transAxes, va="top", fontsize=8, fontweight="bold")
        ax.xaxis.set_major_locator(mdates.MonthLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
        ax.xaxis.set_minor_locator(mdates.WeekdayLocator())

        plot_data[c] = pd.DataFrame({
            "ts": s["Q_spike"].index,
            "Q_spike":  s["Q_spike"].values,
            "Q_step":   s["Q_step"].values,
            "Q_drift":  s["Q_drift"].values,
            "Q_freeze": s["Q_freeze"].values,
            "Q_regime": s["Q_regime"].values,
            "D1_total": d1.values,
        })

    axes[0].legend(ncol=6, loc="upper right", fontsize=7, framealpha=0.9)
    axes[-1].set_xlabel("Date")
    fig.suptitle("Fig. 3 — Sub-score and D1_total trajectories for case-study sensors",
                 fontsize=11, fontweight="bold", y=1.005)
    plt.tight_layout()
    plt.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close()
    return out_path, plot_data


# ─────────────────────────────────────────────────────────────────────────
# Fig 4. Sub-score distribution (violin) per channel — diagnostic profile
# ─────────────────────────────────────────────────────────────────────────
def fig4_subscore_distribution(R, out_path: Path):
    fig, axes = plt.subplots(1, 5, figsize=(15, 4.5), sharey=True)

    qnames = ["Q_spike", "Q_step", "Q_drift", "Q_freeze", "Q_regime"]
    fault_keys = ["spike", "step", "drift", "freeze", "regime"]
    chans = list(R["D1_h"].columns)

    for ax, qn, fk in zip(axes, qnames, fault_keys):
        data = [R["subs"][c][qn].dropna().values for c in chans]
        # Violin, narrower
        parts = ax.violinplot(data, positions=range(len(chans)),
                              widths=0.85, showmedians=True, showextrema=False)
        for pc in parts["bodies"]:
            pc.set_facecolor(FAULT_COLOR[fk])
            pc.set_edgecolor("black"); pc.set_alpha(0.55)
        if "cmedians" in parts:
            parts["cmedians"].set_color("black")
            parts["cmedians"].set_linewidth(1.0)
        ax.set_xticks(range(len(chans)))
        ax.set_xticklabels(chans, rotation=90, fontsize=7)
        ax.set_title(qn, fontsize=10, fontweight="bold", color=FAULT_COLOR[fk])
        ax.axhline(3.0, color="gray", ls="--", lw=0.6, alpha=0.6)
        ax.set_ylim(0.8, 5.2)
        if ax is axes[0]:
            ax.set_ylabel("Sub-score (1=poor, 5=excellent)")

    fig.suptitle("Fig. 4 — Sub-score distribution per channel (8.4-month window)",
                 fontsize=11, fontweight="bold", y=1.02)
    plt.tight_layout()
    plt.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close()

    # Plot data: per-channel quantiles
    rows = []
    for qn in qnames:
        for c in chans:
            x = R["subs"][c][qn].dropna()
            rows.append({
                "subscore": qn, "sensor_id": c,
                "mean": x.mean(), "median": x.median(),
                "p05": x.quantile(0.05), "p25": x.quantile(0.25),
                "p75": x.quantile(0.75), "p95": x.quantile(0.95),
            })
    return out_path, pd.DataFrame(rows)


# ─────────────────────────────────────────────────────────────────────────
# Fig 5. Mapping function curves
# ─────────────────────────────────────────────────────────────────────────
def fig5_mapping_curves(R, out_path: Path):
    from mapping import apply_mapping
    cfg_m = R["cfg"].mapping
    fig, axes = plt.subplots(2, 3, figsize=(13, 7))

    # spike (piecewise)
    ax = axes[0, 0]
    x = np.linspace(0, 0.25, 200)
    y = apply_mapping(pd.Series(x), cfg_m.spike)
    ax.plot(x, y, color=FAULT_COLOR["spike"], lw=2)
    ax.fill_between(x, 1, y, alpha=0.18, color=FAULT_COLOR["spike"])
    ax.set_title("Q_spike  (piecewise)", color=FAULT_COLOR["spike"])
    ax.set_xlabel("spike rate over 6h"); ax.set_ylabel("Quality score")
    ax.set_ylim(0.8, 5.2); ax.axhline(3, color="gray", ls="--", lw=0.6, alpha=0.6)

    # step (logistic)
    ax = axes[0, 1]
    x = np.linspace(0, 1, 200)
    y = apply_mapping(pd.Series(x), cfg_m.step)
    ax.plot(x, y, color=FAULT_COLOR["step"], lw=2)
    ax.fill_between(x, 1, y, alpha=0.18, color=FAULT_COLOR["step"])
    ax.set_title("Q_step  (logistic, k={:.0f}, x₀={:.2f})".format(cfg_m.step.k, cfg_m.step.x0),
                 color=FAULT_COLOR["step"])
    ax.set_xlabel("KS statistic"); ax.set_ylabel("Quality score")
    ax.set_ylim(0.8, 5.2); ax.axhline(3, color="gray", ls="--", lw=0.6, alpha=0.6)

    # drift (logistic)
    ax = axes[0, 2]
    x = np.linspace(0, 8, 200)
    y = apply_mapping(pd.Series(x), cfg_m.drift)
    ax.plot(x, y, color=FAULT_COLOR["drift"], lw=2)
    ax.fill_between(x, 1, y, alpha=0.18, color=FAULT_COLOR["drift"])
    ax.set_title("Q_drift  (logistic, k={:.1f}, x₀={:.1f})".format(cfg_m.drift.k, cfg_m.drift.x0),
                 color=FAULT_COLOR["drift"])
    ax.set_xlabel("|PLS residual| / σ_baseline"); ax.set_ylabel("Quality score")
    ax.set_ylim(0.8, 5.2); ax.axhline(3, color="gray", ls="--", lw=0.6, alpha=0.6)

    # freeze.rle
    ax = axes[1, 0]
    x = np.linspace(0, 600, 400)
    y = apply_mapping(pd.Series(x), cfg_m.freeze.rle)
    ax.plot(x, y, color=FAULT_COLOR["freeze"], lw=2, label="Q_freeze.rle")
    # freeze.lowvar
    x2 = np.linspace(0.001, 1.5, 200)
    y2 = apply_mapping(pd.Series(x2), cfg_m.freeze.low_var)
    ax2 = ax.twiny()
    ax2.plot(x2, y2, color=C["purple"], lw=2, ls="--", alpha=0.85,
             label="Q_freeze.low_var")
    ax2.set_xlabel("rel_var (= roll_std / ref_std)", color=C["purple"], fontsize=8)
    ax2.tick_params(axis="x", labelcolor=C["purple"], labelsize=7)
    ax.set_title("Q_freeze components", color=FAULT_COLOR["freeze"])
    ax.set_xlabel("RLE max run length (min)"); ax.set_ylabel("Quality score")
    ax.set_ylim(0.8, 5.2); ax.axhline(3, color="gray", ls="--", lw=0.6, alpha=0.6)
    ax.legend(loc="upper right", fontsize=7); ax2.legend(loc="upper right",
              bbox_to_anchor=(1, 0.85), fontsize=7)

    # freeze.unique
    ax = axes[1, 1]
    x = np.linspace(0, 0.5, 200)
    y = apply_mapping(pd.Series(x), cfg_m.freeze.unique)
    ax.plot(x, y, color=FAULT_COLOR["freeze"], lw=2)
    ax.fill_between(x, 1, y, alpha=0.18, color=FAULT_COLOR["freeze"])
    ax.set_title("Q_freeze.unique  (logistic, inverted)", color=FAULT_COLOR["freeze"])
    ax.set_xlabel("unique value ratio in 60-min window")
    ax.set_ylabel("Quality score")
    ax.set_ylim(0.8, 5.2); ax.axhline(3, color="gray", ls="--", lw=0.6, alpha=0.6)

    # regime (logistic)
    ax = axes[1, 2]
    x = np.linspace(0, 10, 200)
    y = apply_mapping(pd.Series(x), cfg_m.regime)
    ax.plot(x, y, color=FAULT_COLOR["regime"], lw=2)
    ax.fill_between(x, 1, y, alpha=0.18, color=FAULT_COLOR["regime"])
    ax.set_title("Q_regime  (logistic, k={:.1f}, x₀={:.1f})".format(cfg_m.regime.k, cfg_m.regime.x0),
                 color=FAULT_COLOR["regime"])
    ax.set_xlabel("W₁ distance / bootstrap baseline"); ax.set_ylabel("Quality score")
    ax.set_ylim(0.8, 5.2); ax.axhline(3, color="gray", ls="--", lw=0.6, alpha=0.6)

    fig.suptitle("Fig. 5 — Detector-to-Score Mapping Functions (D1 sub-scores)",
                 fontsize=11, fontweight="bold", y=1.0)
    plt.tight_layout()
    plt.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close()

    # Plot data
    out_dfs = []
    for q, cfg in [("Q_spike", cfg_m.spike), ("Q_step", cfg_m.step),
                   ("Q_drift", cfg_m.drift), ("Q_regime", cfg_m.regime)]:
        x = np.linspace(0, 10, 200)
        y = apply_mapping(pd.Series(x), cfg)
        out_dfs.append(pd.DataFrame({"subscore": q, "x_metric": x, "Q_score": y}))
    return out_path, pd.concat(out_dfs, ignore_index=True)


# ─────────────────────────────────────────────────────────────────────────
# Fig 6. Dominant fault type per channel (stacked bars)
# ─────────────────────────────────────────────────────────────────────────
def fig6_dominant_fault_breakdown(R, out_path: Path):
    dom = R["dominant"]
    chans = list(R["D1_h"].columns)
    fault_order = ["spike", "step", "drift", "freeze", "regime"]
    counts = pd.crosstab(dom["sensor_id"], dom["dominant_fault"])
    # Reindex to ensure all sensors and faults are present
    counts = counts.reindex(index=chans, columns=fault_order, fill_value=0)
    pcts = counts.div(counts.sum(axis=1), axis=0) * 100

    fig, ax = plt.subplots(figsize=(11, 5.5))
    bottom = np.zeros(len(chans))
    for fk in fault_order:
        ax.bar(chans, pcts[fk], bottom=bottom,
               color=FAULT_COLOR[fk], alpha=0.85,
               edgecolor="white", lw=0.5, label=fk)
        bottom += pcts[fk].values
    ax.set_ylabel("Time fraction (%)  with this fault as dominant")
    ax.set_xlabel("Channel")
    ax.set_xticks(range(len(chans)))
    ax.set_xticklabels(chans, rotation=90, fontsize=8)
    ax.legend(title="Dominant fault",
              loc="upper center", bbox_to_anchor=(0.5, -0.20),
              ncol=5, frameon=False)
    ax.set_ylim(0, 100)
    ax.set_title("Fig. 6 — Dominant fault-type composition per channel",
                 fontsize=11, fontweight="bold")
    plt.tight_layout()
    plt.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close()
    return out_path, counts


# ─────────────────────────────────────────────────────────────────────────
# Fig 7. Daily D1_total time-series, all 18 channels
# ─────────────────────────────────────────────────────────────────────────
def fig7_daily_timeseries(R, out_path: Path):
    d1_d = R["D1_d"]
    chans = list(d1_d.columns)
    # Group by sensor type
    do_chans   = [c for c in chans if c.startswith("DO_")]
    orp_chans  = [c for c in chans if c.startswith("ORP_")]
    flow_chans = [c for c in chans if c.startswith("Q")]

    fig, axes = plt.subplots(3, 1, figsize=(12, 8.5), sharex=True)

    cmap_do  = plt.cm.Blues(np.linspace(0.35, 0.95, len(do_chans)))
    cmap_orp = plt.cm.Greens(np.linspace(0.35, 0.95, len(orp_chans)))
    cmap_flw = plt.cm.OrRd(np.linspace(0.35, 0.95, len(flow_chans)))

    for ax, group, cmap, label in [
        (axes[0], do_chans,   cmap_do,  "DO"),
        (axes[1], orp_chans,  cmap_orp, "ORP"),
        (axes[2], flow_chans, cmap_flw, "Flow"),
    ]:
        for i, c in enumerate(group):
            ax.plot(d1_d.index, d1_d[c], color=cmap[i], lw=1.0, label=c, alpha=0.85)
        ax.axhline(3.0, color="gray", ls="--", lw=0.6, alpha=0.6, label="usable threshold")
        ax.axhline(2.0, color=C["red"], ls=":", lw=0.6, alpha=0.5)
        ax.set_ylim(0.8, 5.2); ax.set_yticks([1, 2, 3, 4, 5])
        ax.set_ylabel(f"{label}\nD1_daily (q05)")
        ax.legend(loc="upper right", fontsize=7, ncol=4, framealpha=0.9)
        ax.set_title(f"{label} channels — daily 5%-quantile of hourly D1_total",
                     fontsize=10, fontweight="bold", loc="left")
    axes[-1].set_xlabel("Date")
    axes[-1].xaxis.set_major_locator(mdates.MonthLocator())
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))

    fig.suptitle("Fig. 7 — Daily 5%-quantile D1_total trajectories by sensor group",
                 fontsize=11, fontweight="bold", y=1.0)
    plt.tight_layout()
    plt.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close()
    return out_path, d1_d


# ─────────────────────────────────────────────────────────────────────────
# Fig 8. Veto / cooldown frequency per channel
# ─────────────────────────────────────────────────────────────────────────
def fig8_veto_cooldown(R, out_path: Path):
    chans = list(R["D1_h"].columns)
    rows = []
    for c in chans:
        v = R["veto_logs"][c]
        rows.append({
            "sensor_id": c,
            "veto_freeze_rate":         float(v["veto_freeze"].mean()),
            "veto_regime_rate":         float(v["veto_regime"].mean()),
            "veto_step_sustained_rate": float(v["veto_step_sustained"].mean()),
            "cooldown_drift_rate":      float(v["cooldown_drift"].mean()),
        })
    df = pd.DataFrame(rows)
    df_pct = df.copy()
    for col in df.columns:
        if col != "sensor_id":
            df_pct[col] = df_pct[col] * 100

    fig, ax = plt.subplots(figsize=(11, 5))
    x = np.arange(len(chans))
    w = 0.20
    ax.bar(x - 1.5*w, df_pct["veto_freeze_rate"],         w, color=FAULT_COLOR["freeze"], alpha=0.85, label="freeze veto")
    ax.bar(x - 0.5*w, df_pct["veto_regime_rate"],         w, color=FAULT_COLOR["regime"], alpha=0.85, label="regime veto")
    ax.bar(x + 0.5*w, df_pct["veto_step_sustained_rate"], w, color=FAULT_COLOR["step"],   alpha=0.85, label="step-sustained veto")
    ax.bar(x + 1.5*w, df_pct["cooldown_drift_rate"],      w, color=C["gray"],             alpha=0.85, label="drift cooldown")
    ax.set_xticks(x); ax.set_xticklabels(chans, rotation=90, fontsize=8)
    ax.set_ylabel("Activation rate (% of hourly steps)")
    ax.set_xlabel("Channel")
    ax.set_title("Fig. 8 — Veto / cooldown rule activation frequency per channel",
                 fontsize=11, fontweight="bold")
    ax.legend(ncol=4, loc="upper center", bbox_to_anchor=(0.5, -0.25), frameon=False)
    plt.tight_layout()
    plt.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close()
    return out_path, df_pct


# ─────────────────────────────────────────────────────────────────────────
# Master figure runner
# ─────────────────────────────────────────────────────────────────────────
def make_all_figures(R, fig_dir: str, plot_data_dir: str,
                     case_sensors=("DO_2_3", "ORP_1_3", "ORP_2_2", "QR_2")):
    fdir = Path(fig_dir);     fdir.mkdir(parents=True, exist_ok=True)
    pdir = Path(plot_data_dir); pdir.mkdir(parents=True, exist_ok=True)

    paths = {}
    plot_data_collection = {}

    print("    Fig 1: D1 dimension matrix ...")
    p, d = fig1_d1_dimension_matrix(R, fdir / "Fig1_D1_dimension_matrix.png")
    paths["fig1"] = p; plot_data_collection["fig1_dimensions"] = d

    print("    Fig 2: monthly heatmap ...")
    p, d = fig2_monthly_heatmap(R, fdir / "Fig2_monthly_heatmap.png")
    paths["fig2"] = p; plot_data_collection["fig2_monthly"] = d

    print("    Fig 3: case-sensor sub-score time-series ...")
    p, d = fig3_case_subscores(R, list(case_sensors), fdir / "Fig3_case_subscores.png")
    paths["fig3"] = p
    for cn, dfc in d.items():
        plot_data_collection[f"fig3_case_{cn}"] = dfc

    print("    Fig 4: sub-score violin distribution ...")
    p, d = fig4_subscore_distribution(R, fdir / "Fig4_subscore_distribution.png")
    paths["fig4"] = p; plot_data_collection["fig4_distribution"] = d

    print("    Fig 5: mapping function curves ...")
    p, d = fig5_mapping_curves(R, fdir / "Fig5_mapping_curves.png")
    paths["fig5"] = p; plot_data_collection["fig5_mapping_curves"] = d

    print("    Fig 6: dominant fault breakdown ...")
    p, d = fig6_dominant_fault_breakdown(R, fdir / "Fig6_dominant_fault.png")
    paths["fig6"] = p; plot_data_collection["fig6_dominant_fault"] = d

    print("    Fig 7: daily time-series ...")
    p, d = fig7_daily_timeseries(R, fdir / "Fig7_daily_timeseries.png")
    paths["fig7"] = p; plot_data_collection["fig7_daily"] = d

    print("    Fig 8: veto/cooldown activation ...")
    p, d = fig8_veto_cooldown(R, fdir / "Fig8_veto_cooldown.png")
    paths["fig8"] = p; plot_data_collection["fig8_veto"] = d

    # Strict-V1 specific figures
    try:
        from .figure_strict_v1 import (fig9_harmonic_demo, fig10_two_tier_regime,
                                        fig11_pls_peer_audit)
        if "baseline_min" in R and "seasonal_min" in R:
            print("    Fig 9: harmonic decomposition demo ...")
            p, d = fig9_harmonic_demo(R, fdir / "Fig9_harmonic_demo.png")
            paths["fig9"] = p; plot_data_collection["fig9_harmonic"] = d
        print("    Fig 10: two-tier regime breakdown ...")
        p, d = fig10_two_tier_regime(R, fdir / "Fig10_two_tier_regime.png")
        paths["fig10"] = p; plot_data_collection["fig10_two_tier"] = d
        print("    Fig 11: PLS engineered peer matrix ...")
        p, d = fig11_pls_peer_audit(R, fdir / "Fig11_pls_peer_audit.png")
        paths["fig11"] = p; plot_data_collection["fig11_pls_peers"] = d
    except Exception as e:
        print(f"    Strict-V1 figures skipped: {e}")

    # Save plot data to Excel (one workbook with one sheet per figure)
    plot_data_path = pdir / "all_plot_data.xlsx"
    with pd.ExcelWriter(plot_data_path, engine="openpyxl") as w:
        for sheet, df in plot_data_collection.items():
            sheet_name = sheet[:31]
            if isinstance(df, pd.DataFrame):
                df.to_excel(w, sheet_name=sheet_name)
            else:
                pd.DataFrame(df).to_excel(w, sheet_name=sheet_name)
    print(f"    Plot data → {plot_data_path}")
    paths["plot_data"] = plot_data_path

    return paths
