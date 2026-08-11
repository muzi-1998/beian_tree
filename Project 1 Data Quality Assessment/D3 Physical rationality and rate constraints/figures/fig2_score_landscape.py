"""Figure 2: site-wide scored and diagnostic D3 evidence landscape."""
# Shared Nature contract: Arial; svg.fonttype='none'; pdf.fonttype=42; .svg .pdf .png .tiff dpi=600.
# Figure contract: spatially ordered evidence burdens reveal which mechanisms
# affect each channel without over-centering the supplementary D3 total score.

from __future__ import annotations

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from _figure_data import OUT, read, sensor_order, short_sensor
from _nature_style import COLORS, panel_label, save_figure, style_axis


def _matrix(rows: pd.DataFrame, columns: list[str], order: list[str]) -> np.ndarray:
    return 1000 * rows.set_index("sensor_id").reindex(order)[columns].to_numpy(dtype=float)


def _draw_heatmap(ax, matrix, order, labels, title, cmap="YlOrRd"):
    vmax = max(1.0, float(np.nanpercentile(matrix, 98)))
    image = ax.imshow(matrix, cmap=cmap, vmin=0, vmax=vmax, aspect="auto")
    ax.set_yticks(range(len(order)), [short_sensor(sensor) for sensor in order])
    ax.set_xticks(range(len(labels)), labels, rotation=30, ha="right")
    for row in range(matrix.shape[0]):
        for column in range(matrix.shape[1]):
            value = matrix[row, column]
            text = "0" if np.isfinite(value) and value < 0.05 else f"{value:.1f}"
            ax.text(
                column, row, text, ha="center", va="center", fontsize=5.8,
                color="white" if value > 0.58 * vmax else COLORS["black"],
            )
    ax.set_title(title)
    style_axis(ax, full_frame=True)
    return image


scores = read("D3_window_scores.xlsx")
value = read("D3_value_evidence.xlsx")
rate = read("D3_rate_evidence.xlsx")
boundary = read("D3_boundary_diagnostics.xlsx")
evaluated = scores[scores["evidence_status"].eq("sufficient")]
order = sensor_order(list(scores["sensor_id"].unique()))

scored = pd.DataFrame({"sensor_id": order})
for name, series in {
    "Hard value": value.groupby("sensor_id")["hard_violation_rate"].apply(lambda x: x.gt(0).mean()),
    "Soft low": value.groupby("sensor_id")["soft_low_violation_rate"].apply(lambda x: x.gt(0).mean()),
    "Soft high": value.assign(active=value["soft_high_scored"] & value["soft_high_violation_rate"].gt(0)).groupby("sensor_id")["active"].mean(),
    "Soft-only rate": rate.groupby("sensor_id")["rate_soft_only_violation_rate"].apply(lambda x: x.gt(0).mean()),
    "Hard persistent": rate.groupby("sensor_id")["rate_hard_violation_rate"].apply(lambda x: x.gt(0).mean()),
}.items():
    scored[name] = scored["sensor_id"].map(series)

diagnostic = pd.DataFrame({"sensor_id": order})
for name, series in {
    "Physical low": value.groupby("sensor_id")["physical_low_violation_rate"].apply(lambda x: x.gt(0).mean()),
    "Zero-equivalent": value.groupby("sensor_id")["zero_equivalent_rate"].apply(lambda x: x.gt(0).mean()),
    "Upper diagnostic": value.assign(active=~value["soft_high_scored"] & value["soft_high_violation_rate"].gt(0)).groupby("sensor_id")["active"].mean(),
    "Process guard": rate.groupby("sensor_id")["process_coherence_guarded_points"].apply(lambda x: x.gt(0).mean()),
    "Benchmark tail": boundary.assign(active=boundary["tail_rate_low"].gt(0) | boundary["tail_rate_high"].gt(0)).groupby("sensor_id")["active"].mean(),
}.items():
    diagnostic[name] = diagnostic["sensor_id"].map(series)

fig, axes = plt.subplots(2, 2, figsize=(7.2, 5.7))
fig.subplots_adjust(left=0.11, right=0.98, bottom=0.11, top=0.96, wspace=0.40, hspace=0.48)

ax = axes[0, 0]
labels = list(scored.columns[1:])
image = _draw_heatmap(ax, _matrix(scored, labels, order), order, labels, "Scored evidence burden")
fig.colorbar(image, ax=ax, fraction=0.046, pad=0.025, label="Affected windows per 1,000")
panel_label(ax, "a")

ax = axes[0, 1]
labels = list(diagnostic.columns[1:])
image = _draw_heatmap(ax, _matrix(diagnostic, labels, order), order, labels, "Diagnostic-only context", cmap="YlGnBu")
fig.colorbar(image, ax=ax, fraction=0.046, pad=0.025, label="Affected windows per 1,000")
panel_label(ax, "b")

ax = axes[1, 0]
warn = evaluated.groupby("sensor_id")["operational_warning_flag"].mean().reindex(order)
fail = evaluated.groupby("sensor_id")["D3_gate_status"].apply(lambda x: x.eq("Fail").mean()).reindex(order)
y = np.arange(len(order))
ax.hlines(y, 0, 1000 * warn, color=COLORS["light_gray"], lw=1.3)
ax.scatter(1000 * warn, y, s=19, color=COLORS["amber"], label="Warn")
ax.scatter(1000 * fail, y, s=19, marker="s", facecolor="white", edgecolor=COLORS["red"], label="Fail")
ax.set_yticks(y, [short_sensor(sensor) for sensor in order])
ax.set_xlabel("Gate burden per 1,000 evaluated windows")
ax.legend(loc="lower right")
ax.set_title("Formal gate outcomes")
style_axis(ax, grid=True)
panel_label(ax, "c")

ax = axes[1, 1]
direction = value.groupby("sensor_id").agg(
    low=("soft_low_violation_rate", lambda x: 1000 * x.gt(0).mean()),
    high=("soft_high_violation_rate", lambda x: 1000 * x.gt(0).mean()),
).reindex(order)
y = np.arange(len(order))
ax.barh(y - 0.16, direction["low"], height=0.30, color=COLORS["purple"], label="Low side")
ax.barh(y + 0.16, direction["high"], height=0.30, color=COLORS["orange"], label="High side")
ax.set_yticks(y, [short_sensor(sensor) for sensor in order])
ax.set_xlabel("Windows with directional evidence per 1,000")
ax.legend(loc="lower right")
ax.set_title("Direction of operating-envelope departures")
style_axis(ax, grid=True)
panel_label(ax, "d")

save_figure(fig, OUT, "fig2_score_landscape")
