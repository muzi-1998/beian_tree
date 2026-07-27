"""Figure 2: D3 score landscape across sensors and time."""

from __future__ import annotations

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from _figure_data import OUT, read, sensor_type, short_sensor
from _nature_style import COLORS, ISSUE_COLORS, panel_label, save_figure, style_axis


scores = read("D3_window_scores.xlsx")
scores = scores[scores["evidence_status"] == "sufficient"].copy()
scores["sensor_type"] = scores["sensor_id"].map(sensor_type)
scores["month"] = scores["ts"].dt.to_period("M").astype(str)
fig, axes = plt.subplots(2, 2, figsize=(7.2, 5.4))
fig.subplots_adjust(left=0.10, right=0.98, bottom=0.10, top=0.96, wspace=0.35, hspace=0.42)

ax = axes[0, 0]
bins = np.linspace(1, 5, 33)
for group, color in [("DO", COLORS["blue"]), ("ORP", COLORS["orange"])]:
    ax.hist(scores.loc[scores.sensor_type == group, "D3_total"], bins=bins, density=True,
            histtype="step", linewidth=1.2, color=color, label=group)
ax.set(xlabel="D3 score", ylabel="Density", xlim=(1, 5))
ax.legend(loc="upper left")
ax.set_title("Score distributions")
style_axis(ax, minor=True)
panel_label(ax, "(a)")

ax = axes[0, 1]
pivot = scores.pivot_table(index="sensor_id", columns="month", values="D3_total", aggfunc="median")
image = ax.imshow(pivot, aspect="auto", cmap="viridis", vmin=1, vmax=5)
ax.set_yticks(range(len(pivot)), [short_sensor(s) for s in pivot.index])
ax.set_xticks(range(len(pivot.columns)), [m[5:] for m in pivot.columns])
ax.set_xlabel("Month (2025-2026)")
ax.set_title("Monthly median D3")
style_axis(ax, full_frame=True)
fig.colorbar(image, ax=ax, fraction=0.045, pad=0.03, label="D3")
panel_label(ax, "(b)")

ax = axes[1, 0]
sample = scores.sample(min(9000, len(scores)), random_state=22)
value_score = 0.5 * sample.Q_value_hard + 0.2 * sample.Q_value_soft
scatter = ax.scatter(value_score, 0.3 * sample.Q_rate, c=sample.D3_total, cmap="viridis",
                     vmin=1, vmax=5, s=5, alpha=0.35, linewidths=0, rasterized=True)
ax.set(xlabel="Weighted value evidence", ylabel="Weighted rate evidence")
ax.set_title("Evidence contribution space")
style_axis(ax, minor=True)
fig.colorbar(scatter, ax=ax, fraction=0.045, pad=0.03, label="D3")
panel_label(ax, "(c)")

ax = axes[1, 1]
order = list(scores.groupby("sensor_id").D3_total.mean().sort_values().index)
issue = pd.crosstab(scores.sensor_id, scores.dominant_physical_issue, normalize="index").reindex(order).fillna(0)
left = np.zeros(len(issue))
for key in ["hard_bound", "soft_bound", "rate", "none"]:
    values = issue[key].to_numpy() if key in issue else np.zeros(len(issue))
    ax.barh(range(len(issue)), values, left=left, color=ISSUE_COLORS[key], label=key.replace("_", " "), height=0.72)
    left += values
ax.set_yticks(range(len(issue)), [short_sensor(s) for s in issue.index])
ax.set(xlabel="Fraction of evaluated windows", xlim=(0, 1))
ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.00), ncol=4, columnspacing=0.8)
ax.set_title("Dominant physical evidence", y=1.14)
style_axis(ax)
panel_label(ax, "(d)")

save_figure(fig, OUT, "fig2_score_landscape")
