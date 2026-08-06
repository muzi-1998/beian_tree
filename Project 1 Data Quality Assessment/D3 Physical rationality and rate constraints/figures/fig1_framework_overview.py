"""Figure 1: independent D3 evidence and dimensional ownership."""
# Shared Nature contract: Arial; font.size=7; svg.fonttype='none'; pdf.fonttype=42; .svg .pdf .tiff dpi=600.

from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

from _figure_data import OUT, load_yaml
from _nature_style import COLORS, panel_label, save_figure, style_axis


def logistic_zero(value, x0, k):
    raw = 1 + 4 / (1 + np.exp(k * (value - x0)))
    baseline = 1 + 4 / (1 + np.exp(-k * x0))
    return np.clip(1 + 4 * (raw - 1) / (baseline - 1), 1, 5)


def box(ax, xy, width, height, text, color):
    patch = FancyBboxPatch(
        xy, width, height, boxstyle="round,pad=0.015,rounding_size=0.02",
        facecolor=color, edgecolor=COLORS["navy"], linewidth=0.7,
    )
    ax.add_patch(patch)
    ax.text(xy[0] + width / 2, xy[1] + height / 2, text, ha="center", va="center")


mapping = load_yaml("d3_mapping.yaml")
weights = mapping["aggregation"]["weights"]
fig, axes = plt.subplots(2, 2, figsize=(7.2, 5.2))
fig.subplots_adjust(left=0.09, right=0.98, bottom=0.09, top=0.96, wspace=0.36, hspace=0.42)

ax = axes[0, 0]
labels = ["Hard value", "Soft value", "Persistent rate"]
values = [weights["Q_value_hard"], weights["Q_value_soft"], weights["Q_persistent_rate"]]
bars = ax.bar(labels, values, color=[COLORS["red"], COLORS["amber"], COLORS["blue"]], width=0.62)
for bar, value in zip(bars, values):
    ax.text(bar.get_x() + bar.get_width() / 2, value + 0.018, f"{value:.2f}", ha="center")
ax.set_ylim(0, 0.60)
ax.set_ylabel("Aggregation weight")
ax.set_title("Independent D3 evidence")
style_axis(ax, grid=True)
panel_label(ax, "(a)")

ax = axes[0, 1]
x = np.linspace(0, 0.30, 400)
for key, color, label in [
    ("Q_value_hard", COLORS["red"], "Hard value"),
    ("Q_value_soft", COLORS["amber"], "Soft value"),
    ("Q_persistent_rate", COLORS["blue"], "Persistent rate"),
]:
    config = mapping[key]
    ax.plot(x, logistic_zero(x, config["x0"], config["k"]), color=color, label=label)
ax.scatter([0], [5], s=14, color=COLORS["black"], zorder=5)
ax.text(0.012, 4.82, "Zero violations = 5", va="top")
ax.set(xlabel="Violation fraction", ylabel="Subscore", xlim=(0, 0.30), ylim=(1, 5.1))
ax.legend(loc="upper right", ncol=1)
ax.set_title("Zero-anchored score mappings")
style_axis(ax, minor=True)
panel_label(ax, "(b)")

ax = axes[1, 0]
ax.set(xlim=(0, 1), ylim=(0, 1))
ax.axis("off")
box(ax, (0.02, 0.38), 0.25, 0.26, "Section 1.1\nraw observation grid", "#E8EEF1")
box(ax, (0.38, 0.65), 0.25, 0.22, "D1\nsensor health", "#E7F1EC")
box(ax, (0.38, 0.39), 0.25, 0.22, "D2\navailability", "#F5EFE3")
box(ax, (0.38, 0.13), 0.25, 0.22, "D3\nphysical plausibility", "#E8EEF5")
box(ax, (0.74, 0.38), 0.24, 0.26, "Downstream\nDQR integration", "#F1EAF1")
for y in (0.76, 0.50, 0.24):
    ax.annotate("", xy=(0.38, y), xytext=(0.27, 0.51), arrowprops=dict(arrowstyle="->", lw=0.8))
    ax.annotate("", xy=(0.74, 0.51), xytext=(0.63, y), arrowprops=dict(arrowstyle="->", lw=0.8))
ax.text(0.50, 0.02, "No cross-dimension score is consumed", ha="center", color=COLORS["navy"], fontweight="bold")
ax.set_title("Dimension-independent data flow")
panel_label(ax, "(c)")

ax = axes[1, 1]
matrix = np.array([[1, 0, 0], [0, 1, 0], [0, 0, 1], [0, 0, 0]])
ax.imshow(matrix, cmap="Blues", vmin=0, vmax=1, aspect="auto")
ax.set_xticks(range(3), ["D1", "D2", "D3"])
ax.set_yticks(range(4), ["Sensor\nstate", "Missingness", "Value/rate\nphysics", "Boundary\ntails"])
for i in range(matrix.shape[0]):
    for j in range(matrix.shape[1]):
        text = "Owner" if matrix[i, j] else ("Diag." if i == 3 and j == 2 else "-")
        ax.text(j, i, text, ha="center", va="center", color="white" if matrix[i, j] else COLORS["gray"])
ax.set_title("Evidence ownership contract")
style_axis(ax, full_frame=True)
panel_label(ax, "(d)")

save_figure(fig, OUT, "fig1_framework_overview")
