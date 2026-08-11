"""Figure 1: plant topology, D3 evidence contract, and dimensional ownership."""
# Shared Nature contract: Arial; svg.fonttype='none'; pdf.fonttype=42; .svg .pdf .png .tiff dpi=600.
# Figure contract: D3 evaluates physical plausibility and persistent dynamics
# in process context while preserving numerical independence from D1 and D2.

from __future__ import annotations

import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

from _figure_data import OUT
from _nature_style import COLORS, panel_label, save_figure


def _box(ax, x, y, w, h, text, face, *, edge=COLORS["navy"], weight="normal", fontsize=7.0):
    patch = FancyBboxPatch(
        (x, y), w, h,
        boxstyle="round,pad=0.012,rounding_size=0.018",
        facecolor=face, edgecolor=edge, linewidth=0.75,
    )
    ax.add_patch(patch)
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontweight=weight, fontsize=fontsize)


fig, axes = plt.subplots(2, 2, figsize=(7.2, 5.25))
fig.subplots_adjust(left=0.055, right=0.985, bottom=0.07, top=0.96, wspace=0.22, hspace=0.34)

# a, process topology and paired sensor positions.
ax = axes[0, 0]
ax.set(xlim=(0, 1), ylim=(0, 1)); ax.axis("off")
zones = [
    (0.03, 0.19, "Anaerobic", "ORP1", "#E9EEF1"),
    (0.24, 0.21, "Anoxic mid", "ORP2", "#E7F1EC"),
    (0.47, 0.18, "Anoxic end", "ORP3", "#F5EFE3"),
    (0.67, 0.20, "Aerobic", "DO1-3", "#E8EEF5"),
    (0.89, 0.08, "Post-\nanoxic", "DO4", "#F1EAF1"),
]
for x, width, title, sensor, face in zones:
    _box(ax, x, 0.18, width, 0.64, f"{title}\n\n{sensor}", face, weight="bold")
for y, line in ((0.68, "Line 1"), (0.34, "Line 2")):
    for x in (0.13, 0.345, 0.56, 0.72, 0.78, 0.84, 0.93):
        ax.scatter(x, y, s=20, facecolor="white", edgecolor=COLORS["navy"], lw=0.75, zorder=4)
    ax.annotate("", xy=(0.975, y), xytext=(0.055, y), arrowprops=dict(arrowstyle="->", lw=0.75, color=COLORS["gray"]))
ax.text(0.03, 0.91, "Line 1", ha="left", va="center", fontsize=6.5, color=COLORS["gray"])
ax.text(0.03, 0.09, "Line 2", ha="left", va="center", fontsize=6.5, color=COLORS["gray"])
ax.set_title("Parallel biological lines and measurement positions")
panel_label(ax, "a", x=-0.04)

# b, evidence hierarchy.
ax = axes[0, 1]
ax.set(xlim=(0, 1), ylim=(0, 1)); ax.axis("off")
tiers = [
    (0.08, 0.67, "Instrument range", "Registered limits", "Fail", COLORS["red"]),
    (0.08, 0.39, "Physical plausibility", "Non-negativity and hard bounds", "Warn / Fail", COLORS["amber"]),
    (0.08, 0.11, "Operational plausibility", "Dynamic envelope and persistent rate", "Warn / diagnostic", COLORS["blue"]),
]
for x, y, title, subtitle, outcome, color in tiers:
    _box(ax, x, y, 0.64, 0.20, f"{title}\n{subtitle}", "white", edge=color, weight="bold")
    _box(ax, 0.77, y + 0.035, 0.18, 0.13, outcome, color + "22", edge=color, weight="bold")
ax.text(0.08, 0.02, "Scored evidence and diagnostic context are exported separately", color=COLORS["gray"], fontsize=6.3)
ax.set_title("Three-level physical-plausibility contract")
panel_label(ax, "b")

# c, persistent-rate route.
ax = axes[1, 0]
ax.set(xlim=(0, 1), ylim=(0, 1)); ax.axis("off")
steps = [
    ("Raw\nvalues", "#E9EEF1"),
    ("Robust\nrate", "#E8EEF5"),
    ("Impulse-return\nexclusion", "#F5EFE3"),
    ("Coherence\nguard", "#E7F1EC"),
    ("Persistent\nevidence", "#E8EEF5"),
]
for index, (label, face) in enumerate(steps):
    x = 0.02 + 0.195 * index
    _box(ax, x, 0.38, 0.16, 0.26, label, face, fontsize=6.3)
    if index < len(steps) - 1:
        ax.annotate("", xy=(x + 0.195, 0.51), xytext=(x + 0.16, 0.51), arrowprops=dict(arrowstyle="->", lw=0.8))
ax.text(0.5, 0.22, "3-9 min soft-only  |  >=10 min hard-persistent  |  >=30 min cap", ha="center", color=COLORS["navy"], fontweight="bold")
ax.text(0.5, 0.10, "Coherent multi-sensor changes remain process diagnostics, not data vetoes", ha="center", color=COLORS["gray"])
ax.set_title("Persistence and attribution define rate evidence")
panel_label(ax, "c", x=-0.04)

# d, dimensional ownership and gate output.
ax = axes[1, 1]
ax.set(xlim=(0, 1), ylim=(0, 1)); ax.axis("off")
rows = [
    (0.72, "D1", "Sensor state", COLORS["green"]),
    (0.48, "D2", "Time continuity and availability", COLORS["amber"]),
    (0.24, "D3", "Value and persistent-rate physics", COLORS["blue"]),
]
for y, dim, evidence, color in rows:
    _box(ax, 0.03, y, 0.14, 0.16, dim, color + "22", edge=color, weight="bold")
    _box(ax, 0.23, y, 0.48, 0.16, evidence, "white", edge=color, fontsize=6.3)
    ax.annotate("", xy=(0.79, y + 0.08), xytext=(0.71, y + 0.08), arrowprops=dict(arrowstyle="->", lw=0.8, color=color))
for y, label, color in ((0.70, "Pass", COLORS["green"]), (0.48, "Warn", COLORS["amber"]), (0.26, "Fail", COLORS["red"])):
    _box(ax, 0.80, y, 0.16, 0.13, label, color + "22", edge=color, weight="bold")
ax.text(0.47, 0.08, "No cross-dimension score is consumed by D3", ha="center", color=COLORS["navy"], fontweight="bold")
ax.set_title("Independent evidence ownership and downstream gate")
panel_label(ax, "d")

save_figure(fig, OUT, "fig1_framework_overview")
