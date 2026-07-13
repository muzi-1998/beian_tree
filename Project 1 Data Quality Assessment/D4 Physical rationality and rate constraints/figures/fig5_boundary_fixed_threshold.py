"""Figure 5: fixed boundary diagnostics excluded from D4 scoring."""

from __future__ import annotations

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from _figure_data import OUT, read, short_sensor
from _nature_style import COLORS, annotation_box, panel_label, save_figure, style_axis


boundary = read("D4_boundary_diagnostics.xlsx")
scores = read("D4_window_scores.xlsx")
thresholds = read("D4_threshold_library.xlsx", sheet_name="full_library")
summary = boundary.groupby("sensor_id").agg(
    sticking_low=("boundary_sticking_low_rate", "mean"),
    sticking_high=("boundary_sticking_high_rate", "mean"),
    tail_low=("tail_rate_low", "mean"),
    tail_high=("tail_rate_high", "mean"),
)
summary["D4"] = scores.groupby("sensor_id").D4_total.mean()
order = list(summary.sort_values("sticking_low").index)
y = np.arange(len(order))
fig, axes = plt.subplots(2, 2, figsize=(7.2, 5.4))
fig.subplots_adjust(left=0.11, right=0.98, bottom=0.10, top=0.96, wspace=0.38, hspace=0.42)

ax = axes[0, 0]
s = summary.loc[order]
ax.barh(y, s.sticking_low, color=COLORS["blue"], height=0.68, label="Low boundary")
ax.barh(y, s.sticking_high, left=s.sticking_low, color=COLORS["orange"], height=0.68, label="High boundary")
ax.set_yticks(y, [short_sensor(v) for v in order])
ax.set(xlabel="Mean boundary-sticking fraction", xlim=(0, min(1, max(.05, (s.sticking_low+s.sticking_high).max()*1.08))))
ax.legend(loc="lower right", bbox_to_anchor=(1.0, 1.00), ncol=2, columnspacing=0.8)
ax.set_title("Fixed hard-bound proximity", loc="left", y=1.12)
style_axis(ax, grid=True)
panel_label(ax, "(a)")

ax = axes[0, 1]
ax.barh(y - 0.18, s.tail_low, height=0.34, color=COLORS["purple"], label="Lower tail")
ax.barh(y + 0.18, s.tail_high, height=0.34, color=COLORS["green"], label="Upper tail")
ax.set_yticks(y, [short_sensor(v) for v in order])
ax.set_xlabel("Mean benchmark-tail occupancy")
ax.legend(loc="lower right", bbox_to_anchor=(1.0, 1.00), ncol=2, columnspacing=0.8)
ax.set_title("Benchmark-derived tail diagnostics", loc="left", y=1.12)
style_axis(ax, grid=True)
panel_label(ax, "(b)")

ax = axes[1, 0]
occupancy = s.tail_low + s.tail_high
ax.scatter(occupancy, s.D4, s=22, color=COLORS["cyan"], edgecolor="white", linewidth=0.4)
offsets = [(4, -14), (-50, -2), (-46, 12)]
for sensor, offset in zip(occupancy.nlargest(3).index, offsets):
    ax.annotate(short_sensor(sensor), (occupancy[sensor], s.loc[sensor, "D4"]),
                xytext=offset, textcoords="offset points", bbox=annotation_box(0.72),
                arrowprops=dict(arrowstyle="-", color=COLORS["gray"], lw=0.5))
ax.set(xlabel="Total tail occupancy", ylabel="Mean D4", ylim=(1, 5.1))
ax.set_title("Diagnostic association only")
style_axis(ax, minor=True)
panel_label(ax, "(c)")

ax = axes[1, 1]
bounds = thresholds[thresholds.bound_type == "boundary"]
counts = bounds.sensor_type.value_counts().reindex(["DO", "ORP"]).fillna(0)
bars = ax.bar(counts.index, counts.values, color=[COLORS["blue"], COLORS["orange"]], width=0.58)
for bar, value in zip(bars, counts.values):
    ax.text(bar.get_x()+bar.get_width()/2, value+0.4, f"{int(value)}", ha="center")
ax.text(0.98, 0.95, "Benchmark quantiles\nExcluded from D4 score", transform=ax.transAxes, ha="right", va="top",
        fontweight="bold", color=COLORS["red"], bbox=annotation_box(0.82))
ax.set(xlabel="Sensor type", ylabel="Threshold count")
ax.set_title("Auditable threshold provenance")
style_axis(ax, grid=True)
panel_label(ax, "(d)")

save_figure(fig, OUT, "fig5_boundary_fixed_threshold")
