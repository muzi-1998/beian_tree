"""Generate current-result D1 validation figures V17-V18.

The former V16 fixed-k regime clustering panel is intentionally excluded from
the formal D1 bundle. It was an unvalidated D5 exploratory construct rather
than a D1 sensor-health result.
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
from publication_style import (PALETTE as C, STATE_COLORS as STATE_COL,
                               configure_publication_style, finalize_figure,
                               positive_data_ylim, save_publication_bundle)

OUT = ROOT / "outputs" / "figures"
PLOTDATA = ROOT / "outputs" / "plot_data"
OUT.mkdir(parents=True, exist_ok=True)
PLOTDATA.mkdir(parents=True, exist_ok=True)

# Same SCI rcParams
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
SUPPORT = S["support_channels"]
DO_CH = [c for c in SCORED if c.startswith("DO_")]
ORP_CH = [c for c in SCORED if c.startswith("ORP_")]
D1_v11 = S["D1_v11"]
df_h = S["df_h"]


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


# ============================================================================
# Figure V17 — QR/QIR side annotations + scope diagram
# ============================================================================
print("[V17] QR/QIR scope (DO/ORP only main link) ...")
fig = plt.figure(figsize=(7.2, 6.3))
gs = gridspec.GridSpec(3, 2, figure=fig, hspace=0.55, wspace=0.30,
                        height_ratios=[1.2, 1.0, 1.0])
fig.subplots_adjust(right=0.80, top=0.91, bottom=0.08)

# (a) Scope diagram (illustrative)
ax = fig.add_subplot(gs[0, :])
ax.set_xlim(0, 12); ax.set_ylim(0, 5)
ax.axis("off")
# Three boxes: scored, support, future extension
b1 = Rectangle((0.3, 1.3), 3.4, 3.0, facecolor="#D1E5F0", edgecolor=C["blue"], lw=1.4)
ax.add_patch(b1)
ax.text(2.0, 3.95, "SCORED MAIN LINK", ha="center", va="center",
        fontsize=10.5, fontweight="bold", color=C["navy"])
ax.text(2.0, 2.55,
        "DO pools 1-2: 8 channels\nORP pools 1-2: 6 channels\n\n"
        "Only these channels enter $D_1$\n(n = 14)",
        ha="center", va="center", fontsize=8.0)

b2 = Rectangle((4.3, 1.3), 3.4, 3.0, facecolor="#FDDBC7", edgecolor=C["amber"], lw=1.4)
ax.add_patch(b2)
ax.text(6.0, 3.95, "SUPPORT DATA", ha="center", va="center",
        fontsize=10.5, fontweight="bold", color=C["amber"])
ax.text(6.0, 2.55,
        "QR: 2 channels\nQIR: 2 channels\n\n"
        "Offline D5/D5 context\n(n = 4)",
        ha="center", va="center", fontsize=8.0)

b3 = Rectangle((8.3, 1.3), 3.4, 3.0, facecolor="#EDEDED", edgecolor=C["gray"],
                lw=1.0, linestyle="--")
ax.add_patch(b3)
ax.text(10.0, 3.95, "FUTURE EXTENSION", ha="center", va="center",
        fontsize=10.5, fontweight="bold", color=C["gray"])
ax.text(10.0, 2.55,
        "Pump state\nValve state\nOperating logs\n\nProcess-aware extension",
        ha="center", va="center", fontsize=8.0, color=C["gray"])

ax.annotate("", xy=(4.3, 2.85), xytext=(3.7, 2.85),
              arrowprops=dict(arrowstyle="->", lw=1.8, color="0.4"))
ax.annotate("", xy=(8.3, 2.85), xytext=(7.7, 2.85),
              arrowprops=dict(arrowstyle="->", lw=1.5, color="0.5", linestyle="--"))
ax.text(6.0, 0.45,
        "QR/QIR provide offline context only; they never enter the D1 score.",
        ha="center", fontsize=7.8, style="italic", color="0.35")
ax.set_title("(a) Data roles in final D1 scoring", loc="left")

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
_jump_max = max(float(qr_per_day.max()), float(qir_per_day.max()), 1.0)
ax.set_ylim(-1.08 * _jump_max, 1.08 * _jump_max)
ax.set_title("(b)  Driver-variable jump density timeline (offline annotation, "
              "NOT scored)", loc="left")
ax.legend(loc="center left", bbox_to_anchor=(1.01, 0.5), fontsize=6.8,
          frameon=False, borderaxespad=0)
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
ax.legend(loc="center left", bbox_to_anchor=(1.01, 0.5), fontsize=6.8,
          ncol=1, frameon=False, borderaxespad=0)
ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))

fig.suptitle("Figure V17. D1 scoring scope and offline support data",
              fontsize=9.8, fontweight="bold", y=0.995)
save(fig, "FigV17_scope_qr_qir_offline",
      plot_data={"jumps_per_day": pd.DataFrame({"QR": qr_per_day, "QIR": qir_per_day}),
                  "annotations_summary": pd.Series({
                      "qr_jumps": int(qr_jumps.sum()),
                      "qir_jumps": int(qir_jumps.sum())}).to_frame("count")})


# ============================================================================
# Figure V18 — current D1 distribution and event burden
# ============================================================================
print("[V18] Current D1 distribution and event burden ...")
final_flat = D1_v11.to_numpy().ravel()
final_flat = final_flat[np.isfinite(final_flat)]

def grade_dist(arr):
    return [
        float((arr >= 4.5).mean()),
        float(((arr >= 3.5) & (arr < 4.5)).mean()),
        float(((arr >= 2.5) & (arr < 3.5)).mean()),
        float(((arr >= 1.5) & (arr < 2.5)).mean()),
        float((arr < 1.5).mean()),
    ]

grade_labels = ["A (>=4.5)", "B (3.5-4.5)", "C (2.5-3.5)",
                "D (1.5-2.5)", "F (<1.5)"]
grade_colors = ["#1A9850", "#A6D96A", "#FEE08B", "#F46D33", "#9E1F1F"]
grade_pct = np.asarray(grade_dist(final_flat)) * 100

qdrift_rows = []
for channel in SCORED:
    values = pd.Series(S["Q_drift_eff_dict"][channel]).dropna()
    qdrift_rows.append({
        "channel": channel,
        "median": float(values.median()),
        "q25": float(values.quantile(0.25)),
        "q75": float(values.quantile(0.75)),
    })
qdrift_summary = pd.DataFrame(qdrift_rows).sort_values("median")

events = S["events_v11"].copy()
event_burden = pd.DataFrame(index=SCORED)
event_burden["event_count"] = events.groupby("sensor_id").size().reindex(SCORED, fill_value=0)
event_burden["event_hours"] = (
    events.groupby("sensor_id")["duration_h"].sum().reindex(SCORED, fill_value=0.0)
)
event_burden["event_hours_pct"] = event_burden["event_hours"] / len(D1_v11) * 100
event_burden["D1_lt_3_pct"] = (D1_v11 < 3.0).mean().reindex(SCORED) * 100
event_burden["mean_D1"] = D1_v11.mean().reindex(SCORED)
event_burden["analyte"] = ["DO" if c.startswith("DO_") else "ORP" for c in SCORED]

dominant = {name: 0 for name in ["Q_spike", "Q_step", "Q_drift", "Q_freeze", "Q_regime"]}
for _, event in events.iterrows():
    channel = event["sensor_id"]
    evidence = pd.DataFrame({
        name: S["subs_v11"][channel][name].loc[event["start"]:event["end"]]
        for name in dominant
    })
    if not evidence.empty:
        dominant[evidence.mean(axis=0).idxmin()] += 1
faults = ["spike", "step", "drift", "freeze", "regime"]
fault_counts = np.asarray([dominant[f"Q_{fault}"] for fault in faults])

fig = plt.figure(figsize=(7.2, 5.95))
gs = gridspec.GridSpec(2, 3, figure=fig, hspace=0.48, wspace=0.56,
                        height_ratios=[1.0, 1.25])
fig.subplots_adjust(top=0.91, bottom=0.09, left=0.10, right=0.97)

# (a) Current hourly score distribution
ax = fig.add_subplot(gs[0, 0])
bins = np.linspace(1, 5, 60)
ax.hist(final_flat, bins=bins, color=C["blue"], alpha=0.72,
        density=True, edgecolor="white", linewidth=0.2)
for threshold in (1.5, 2.5, 3.5, 4.5):
    ax.axvline(threshold, color="0.45", ls=":", lw=0.65, alpha=0.7)
density_max = np.histogram(final_flat, bins=bins, density=True)[0].max()
ax.set_ylim(0, density_max * 1.10)
ax.set_xlim(1, 5)
ax.set_xlabel(r"Hourly $D_1$", fontsize=8.6)
ax.set_ylabel("Density", fontsize=8.6)
ax.set_title("(a) Final score distribution", loc="left")
ax.text(
    0.04, 0.94, f"mean = {final_flat.mean():.3f}", transform=ax.transAxes,
    ha="left", va="top", fontsize=6.8,
    bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.72,
          "pad": 1.0},
)

# (b) Current grade composition
ax = fig.add_subplot(gs[0, 1])
y = np.arange(len(grade_labels))
ax.barh(y, grade_pct, color=grade_colors, edgecolor="white", linewidth=0.5)
ax.set_yticks(y)
ax.set_yticklabels(grade_labels, fontsize=7.1)
ax.invert_yaxis()
ax.set_xlabel("All sensor-hours (%)", fontsize=8.6)
ax.set_title("(b) Grade composition", loc="left")
ax.set_xlim(0, max(1.0, float(grade_pct.max()) * 1.18))
for yi, value in zip(y, grade_pct):
    ax.text(value + max(grade_pct.max() * 0.015, 0.05), yi, f"{value:.1f}%",
            va="center", fontsize=6.7)

# (c) Event counts classified by weakest sub-score
ax = fig.add_subplot(gs[0, 2])
x = np.arange(len(faults))
ax.bar(x, fault_counts, color=[C["blue"], C["amber"], C["purple"],
                               C["teal"], C["red"]],
       alpha=0.86, edgecolor="white", linewidth=0.5)
ax.set_xticks(x)
ax.set_xticklabels(faults, rotation=30, ha="right", fontsize=7.1)
ax.set_ylabel("Event count", fontsize=8.6)
ax.set_ylim(*positive_data_ylim(fault_counts, headroom=0.18, minimum_upper=1.0))
ax.set_title(f"(c) Dominant evidence (n={int(fault_counts.sum())})", loc="left")
for xi, value in zip(x, fault_counts):
    if value > 0:
        ax.text(xi, value + max(float(fault_counts.max()) * 0.025, 0.05),
                str(int(value)), ha="center", fontsize=6.8)

# (d) Final state-conditioned drift score by channel
ax = fig.add_subplot(gs[1, :2])
y = np.arange(len(qdrift_summary))
for yi, row in enumerate(qdrift_summary.itertuples()):
    color = C["blue"] if row.channel.startswith("DO_") else C["green"]
    marker = "o" if row.channel.startswith("DO_") else "s"
    ax.errorbar(
        row.median, yi,
        xerr=[[row.median - row.q25], [row.q75 - row.median]],
        fmt=marker, color=color, ecolor=color, ms=4.5, elinewidth=1.0,
        capsize=2.0, markeredgecolor="white", markeredgewidth=0.45,
    )
ax.axvline(3.0, color=C["amber"], ls="--", lw=0.75, label="neutral = 3.0")
ax.set_yticks(y)
ax.set_yticklabels(qdrift_summary["channel"].tolist(), fontsize=7.1)
ax.set_xlim(1, 5)
ax.set_xlabel(r"Median $Q_{\rm drift}^{eff}$ (interquartile range)", fontsize=8.6)
ax.set_title("(d) State-conditioned drift evidence", loc="left")
ax.legend(
    handles=[
        Line2D([], [], marker="o", color=C["blue"], linestyle="", label="DO"),
        Line2D([], [], marker="s", color=C["green"], linestyle="", label="ORP"),
        Line2D([], [], color=C["amber"], ls="--", lw=0.75, label="neutral = 3.0"),
    ], loc="upper left", bbox_to_anchor=(0.01, 0.985), ncol=1,
    fontsize=6.1, frameon=True, framealpha=0.72,
    facecolor="white", edgecolor="none", borderaxespad=0,
)

# (e) Per-channel event frequency and occupied duration
ax = fig.add_subplot(gs[1, 2])
for analyte, color, marker in [("DO", C["blue"], "o"), ("ORP", C["green"], "s")]:
    subset = event_burden[event_burden["analyte"] == analyte]
    sizes = 18 + 2.0 * subset["D1_lt_3_pct"].clip(upper=35)
    ax.scatter(
        subset["event_count"], subset["event_hours_pct"], s=sizes,
        color=color, marker=marker, alpha=0.78, edgecolor="white",
        linewidth=0.5, label=analyte, zorder=3,
    )
label_channels = event_burden.sort_values(
    ["event_hours_pct", "event_count"], ascending=False
).head(4).index
offsets = [(4, 4), (4, -9), (-28, 5), (-28, -9)]
for channel, offset in zip(label_channels, offsets):
    row = event_burden.loc[channel]
    ax.annotate(
        channel, (row["event_count"], row["event_hours_pct"]),
        xytext=offset, textcoords="offset points", fontsize=6.0,
        bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.72,
              "pad": 0.8},
        arrowprops={"arrowstyle": "-", "color": "0.45", "lw": 0.4},
        annotation_clip=False,
    )
ax.set_xlabel("Event count", fontsize=8.6)
ax.set_ylabel("Event duration / record (%)", fontsize=8.6)
ax.set_xlim(-0.5, max(1.0, float(event_burden["event_count"].max()) + 2.0))
ax.set_ylim(*positive_data_ylim(event_burden["event_hours_pct"],
                                 headroom=0.22, minimum_upper=0.5))
ax.set_title("(e) Channel-level event burden", loc="left")
ax.legend(loc="upper left", fontsize=6.3, frameon=False)

fig.suptitle("Figure V18. Current D1 distribution and event burden",
              fontsize=9.8, fontweight="bold", y=0.995)
save(
    fig, "FigV18_current_D1_event_summary",
    plot_data={
        "hourly_D1_describe": pd.Series(final_flat).describe().to_frame("final_D1"),
        "grade_distribution": pd.DataFrame({"percentage": grade_pct}, index=grade_labels),
        "qdrift_summary": qdrift_summary.set_index("channel"),
        "event_burden": event_burden,
        "fault_counts": pd.DataFrame({"count": fault_counts}, index=faults),
    },
)


print("\n[part 2 done] V17-V18 complete.\n")
try:
    from generate_expert_report_v11 import maybe_update_report
    maybe_update_report()
except Exception as exc:
    print(f"[auto-report] skipped: {exc}")
