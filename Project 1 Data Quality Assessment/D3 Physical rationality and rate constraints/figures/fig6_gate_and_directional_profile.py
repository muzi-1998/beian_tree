"""Figure 6: D3 score, gate, event, and directional-boundary profiles."""
# Shared Nature contract: Arial; font.size=7; svg.fonttype='none'; pdf.fonttype=42; .svg .pdf .tiff dpi=600.

from __future__ import annotations

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from _figure_data import OUT, read, short_sensor
from _nature_style import COLORS, ISSUE_COLORS, panel_label, save_figure, style_axis


scores = read("D3_window_scores.xlsx")
events = read("D3_physical_events.xlsx")
value = read("D3_value_evidence.xlsx")
evaluated = scores[scores.evidence_status == "sufficient"].copy()
summary = (
    evaluated.groupby("sensor_id").D3_total.quantile([0.05, 0.5, 0.95])
    .unstack()
    .rename(columns={0.05: "p05", 0.5: "median", 0.95: "p95"})
)
summary["mean"] = evaluated.groupby("sensor_id").D3_total.mean()
summary = summary.sort_values("median")
order = list(summary.index)
y = np.arange(len(order))

fig, axes = plt.subplots(2, 2, figsize=(7.2, 5.6))
fig.subplots_adjust(left=0.11, right=0.98, bottom=0.10, top=0.96, wspace=0.40, hspace=0.43)

ax = axes[0, 0]
ax.hlines(y, summary.p05, summary.p95, color=COLORS["light_gray"], lw=2.2)
ax.scatter(summary["median"], y, s=20, color=COLORS["blue"], label="Median", zorder=3)
ax.scatter(summary["mean"], y, s=17, facecolors="white", edgecolors=COLORS["navy"], label="Mean", zorder=3)
ax.set_yticks(y, [short_sensor(sensor) for sensor in order])
ax.set(xlabel="Supplementary D3 plausibility score", xlim=(1, 5.05))
ax.legend(loc="lower right")
ax.set_title("Observed operating-plausibility profile")
style_axis(ax, grid=True)
panel_label(ax, "a")

ax = axes[0, 1]
gate_order = ["Pass", "Warn", "Fail"]
fractions = pd.crosstab(evaluated.sensor_id, evaluated.D3_gate_status, normalize="index").reindex(order).fillna(0)
left = np.zeros(len(fractions))
for label, color in zip(gate_order, [COLORS["green"], COLORS["amber"], COLORS["red"]]):
    values = fractions[label].to_numpy() if label in fractions else np.zeros(len(fractions))
    ax.barh(y, values, left=left, height=0.68, color=color, label=label)
    left += values
ax.set_yticks(y, [short_sensor(sensor) for sensor in order])
ax.set(xlabel="Fraction of evaluated windows", xlim=(0, 1))
ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.01), ncol=3)
ax.set_title("Fail is reserved for instrument-range evidence", y=1.12)
style_axis(ax)
panel_label(ax, "b")

ax = axes[1, 0]
event_counts = events.event_type.value_counts() if len(events) else pd.Series(dtype=int)
event_order = [
    item for item in
    ["instrument_range", "hard_bound", "soft_bound", "persistent_rate", "process_coherent_shock", "low_quality_window"]
    if item in event_counts
]
colors = [
    COLORS["green"] if name == "process_coherent_shock" else ISSUE_COLORS.get(name, COLORS["gray"])
    for name in event_order
]
bars = ax.bar(range(len(event_order)), event_counts.reindex(event_order), color=colors, width=0.65)
ax.set_xticks(range(len(event_order)), [name.replace("_", "\n") for name in event_order])
ax.set(ylabel="Two-hour event windows")
for bar, count in zip(bars, event_counts.reindex(event_order)):
    ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(), f"{int(count)}", ha="center", va="bottom", fontsize=6)
ax.set_title("Operational warnings and guarded shocks")
style_axis(ax, grid=True)
panel_label(ax, "c")

ax = axes[1, 1]
direction = (
    value.groupby("sensor_id")[["soft_low_violation_rate", "soft_high_violation_rate"]]
    .mean()
    .reindex(order)
)
matrix = 100 * direction.to_numpy()
vmax = max(1.0, float(np.nanmax(matrix)))
image = ax.imshow(matrix, cmap="YlOrRd", vmin=0, vmax=vmax, aspect="auto")
ax.set_yticks(range(len(order)), [short_sensor(sensor) for sensor in order])
ax.set_xticks([0, 1], ["Below soft low", "Above soft high"])
for row in range(matrix.shape[0]):
    for column in range(matrix.shape[1]):
        value_text = matrix[row, column]
        ax.text(column, row, f"{value_text:.1f}", ha="center", va="center",
                fontsize=6, color="white" if value_text > 0.55 * vmax else COLORS["black"])
ax.set_title("Direction of provisional soft-bound excursions")
style_axis(ax, full_frame=True)
fig.colorbar(image, ax=ax, fraction=0.045, pad=0.03, label="Observed minutes (%)")
panel_label(ax, "d")

save_figure(fig, OUT, "fig6_gate_and_directional_profile")
