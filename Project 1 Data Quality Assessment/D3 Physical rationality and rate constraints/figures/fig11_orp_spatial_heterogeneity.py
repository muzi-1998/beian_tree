"""Figure 11: ORP position and parallel-line heterogeneity."""
# Shared Nature contract: Arial; svg.fonttype='none'; pdf.fonttype=42; .svg .pdf .png .tiff dpi=600.
# Figure contract: ORP operating distributions vary by process position and
# parallel line, so the common soft range remains provisional and diagnostic.

from __future__ import annotations

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from _figure_data import OUT, read_validation, short_sensor
from _nature_style import COLORS, panel_label, save_figure, style_axis


path = "D3_operational_envelope_diagnostics.xlsx"
distribution = read_validation(path, sheet_name="ORP_position_distribution")
seasonal = read_validation(path, sheet_name="ORP_position_season_envelope")
directional = read_validation(path, sheet_name="directional_window_burden")
effects = read_validation(path, sheet_name="ORP_parallel_position_effect")
order = [f"ORP_{line}_{position}" for position in (1, 2, 3) for line in (1, 2)]
colors = {1: COLORS["blue"], 2: COLORS["orange"]}

fig, axes = plt.subplots(2, 2, figsize=(7.2, 5.4))
fig.subplots_adjust(left=0.11, right=0.98, bottom=0.10, top=0.96, wspace=0.41, hspace=0.45)

ax = axes[0, 0]
plot = distribution.set_index("sensor_id").reindex(order)
x = np.arange(len(order))
for index, row in enumerate(plot.itertuples()):
    line = int(row.pool)
    ax.plot([index, index], [row.p01_mV, row.p99_mV], color=colors[line], lw=0.8)
    ax.plot([index, index], [row.q25_mV, row.q75_mV], color=colors[line], lw=5.0, solid_capstyle="butt")
    ax.scatter(index, row.median_mV, s=16, facecolor="white", edgecolor=colors[line], zorder=3)
ax.axhline(-400, color=COLORS["purple"], lw=0.8, ls="--", label="Provisional low bound")
ax.axhline(200, color=COLORS["amber"], lw=0.8, ls="--", label="Provisional high bound")
ax.set_xticks(x, [short_sensor(sensor) for sensor in order], rotation=35, ha="right")
ax.set_ylabel("ORP (mV)")
ax.legend(loc="lower left")
ax.set_title("Full-period position distributions")
style_axis(ax, grid=True)
panel_label(ax, "a")

ax = axes[0, 1]
season_order = ["summer", "transition", "winter"]
season_x = np.arange(len(season_order))
for sensor in order:
    group = seasonal.loc[seasonal["sensor_id"].eq(sensor)].set_index("season").reindex(season_order)
    line = int(sensor.split("_")[1]); position = int(sensor.split("_")[2])
    color = [COLORS["blue"], COLORS["green"], COLORS["orange"]][position - 1]
    ax.plot(season_x, group["median"], marker="o" if line == 1 else "s", ms=3.2, lw=0.85, color=color, ls="-" if line == 1 else "--")
    ax.text(2.04, group.loc["winter", "median"], short_sensor(sensor), color=color, va="center", fontsize=5.9)
ax.set_xticks(season_x, [value.title() for value in season_order])
ax.set_ylabel("Seasonal median ORP (mV)")
ax.set_xlim(-0.05, 2.52)
ax.set_title("Season and position interact")
style_axis(ax, grid=True)
panel_label(ax, "b")

ax = axes[1, 0]
orp = directional.loc[directional["type"].eq("ORP")].set_index("sensor_id").reindex(order)
x = np.arange(len(order))
ax.bar(x - 0.16, 100 * orp["soft_low_window_rate"], width=0.31, color=COLORS["purple"], label="Below -400 mV")
ax.bar(x + 0.16, 100 * orp["soft_high_window_rate"], width=0.31, color=COLORS["amber"], label="Above 200 mV")
ax.set_xticks(x, [short_sensor(sensor) for sensor in order], rotation=35, ha="right")
ax.set_ylabel("Windows with directional evidence (%)")
ax.legend(loc="upper left")
ax.set_title("Departure direction is position-specific")
style_axis(ax, grid=True)
panel_label(ax, "c")

ax = axes[1, 1]
x = np.arange(len(effects))
estimate = effects["median_line1_minus_line2_mV"].to_numpy(dtype=float)
lower = estimate - effects["day_block_ci_low_mV"].to_numpy(dtype=float)
upper = effects["day_block_ci_high_mV"].to_numpy(dtype=float) - estimate
ax.errorbar(x, estimate, yerr=np.maximum(np.vstack([lower, upper]), 0), fmt="o", ms=4, color=COLORS["blue"], ecolor=COLORS["gray"], elinewidth=0.8, capsize=2)
ax.axhline(0, color=COLORS["black"], lw=0.8, ls="--")
for index, row in enumerate(effects.itertuples(index=False)):
    positive = row.median_line1_minus_line2_mV >= 0
    label_x = index if positive else index + 0.10
    label_y = row.day_block_ci_high_mV + 10 if positive else row.median_line1_minus_line2_mV - 5
    ax.text(label_x, label_y, f"robust d={row.robust_standardized_difference:.2f}", ha="center" if positive else "left", va="bottom" if positive else "top", fontsize=6.0, color=COLORS["gray"])
ax.set_xticks(x, ["Anaerobic\nORP1", "Anoxic mid\nORP2", "Anoxic end\nORP3"])
ax.set_ylabel("Median Line 1 - Line 2 (mV)")
ax.set_title("Parallel-line differences with day-block CI")
style_axis(ax, grid=True)
panel_label(ax, "d")

save_figure(fig, OUT, "fig11_orp_spatial_heterogeneity")
