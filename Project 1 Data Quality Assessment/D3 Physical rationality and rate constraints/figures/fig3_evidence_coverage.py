"""Figure 3: D3 evaluation coverage and explicit unevaluated evidence states."""
# Shared Nature contract: Arial; font.size=7; svg.fonttype='none'; pdf.fonttype=42; .svg .pdf .png .tiff dpi=600.
# Figure contract: D3 withholds scores when window evidence is insufficient and
# reports covariate-specific evaluability rather than treating missing context as pass.

from __future__ import annotations

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from _figure_data import OUT, read, sensor_order, short_sensor
from _nature_style import COLORS, panel_label, save_figure, style_axis


scores = read("D3_window_scores.xlsx")
scores["month"] = scores["ts"].dt.to_period("M")
order = sensor_order(list(scores["sensor_id"].unique()))
months = sorted(scores["month"].unique())
month_labels = [period.to_timestamp().strftime("%b\n%Y") for period in months]

evaluated_matrix = (
    scores.assign(evaluated=scores["evidence_status"].eq("sufficient"))
    .pivot_table(index="sensor_id", columns="month", values="evaluated", aggfunc="mean")
    .reindex(index=order, columns=months)
)
observed_matrix = (
    scores.pivot_table(index="sensor_id", columns="month", values="observed_fraction", aggfunc="mean")
    .reindex(index=order, columns=months)
)

fig, axes = plt.subplots(2, 2, figsize=(7.2, 5.35))
fig.subplots_adjust(left=0.11, right=0.98, bottom=0.10, top=0.96, wspace=0.37, hspace=0.45)

ax = axes[0, 0]
image = ax.imshow(evaluated_matrix, cmap="YlGnBu", vmin=0, vmax=1, aspect="auto")
ax.set_yticks(range(len(order)), [short_sensor(sensor) for sensor in order])
ax.set_xticks(range(len(months)), month_labels)
ax.set_title("Evaluated-window coverage")
style_axis(ax, full_frame=True)
fig.colorbar(image, ax=ax, fraction=0.046, pad=0.025, label="Evaluated fraction")
panel_label(ax, "a")

ax = axes[0, 1]
image = ax.imshow(observed_matrix, cmap="viridis", vmin=0, vmax=1, aspect="auto")
ax.set_yticks(range(len(order)), [short_sensor(sensor) for sensor in order])
ax.set_xticks(range(len(months)), month_labels)
ax.set_title("Observed-minute coverage")
style_axis(ax, full_frame=True)
fig.colorbar(image, ax=ax, fraction=0.046, pad=0.025, label="Observed fraction")
panel_label(ax, "b")

ax = axes[1, 0]
labels = ["<=0.50", "0.50-0.75", "0.75-0.90", ">0.90"]
scores["coverage_bin"] = pd.cut(
    scores["observed_fraction"], [-0.001, 0.50, 0.75, 0.90, 1.001], labels=labels
)
gate = scores.groupby("coverage_bin", observed=False).agg(
    evaluated=("D3_total", lambda x: x.notna().mean()),
    n=("sensor_id", "size"),
).reindex(labels).fillna(0)
bars = ax.bar(range(len(labels)), gate["evaluated"], color=COLORS["purple"], width=0.62)
for bar, count in zip(bars, gate["n"].astype(int)):
    ax.text(bar.get_x() + bar.get_width() / 2, min(bar.get_height() + 0.04, 0.96), f"n={count:,}", ha="center", va="bottom" if bar.get_height() < 0.90 else "top", color="white" if bar.get_height() > 0.90 else COLORS["black"])
ax.set_xticks(range(len(labels)), labels)
ax.set(xlabel="Observed fraction within each 2 h window\nEvaluation requires at least 0.50 observed minutes", ylabel="Evaluated-window fraction", ylim=(0, 1.03))
ax.set_title("Explicit per-window evidence gate")
style_axis(ax, grid=True)
panel_label(ax, "c")

ax = axes[1, 1]
monthly = scores.groupby("month").agg(
    not_evaluated=("evidence_status", lambda x: x.ne("sufficient").mean()),
    temperature_unknown=("temperature_upper_status", lambda x: x.eq("temperature_unavailable").mean()),
)
x = [period.to_timestamp() for period in monthly.index]
ax.plot(x, 100 * monthly["not_evaluated"], marker="o", ms=3.2, color=COLORS["purple"], label="D3 not evaluated")
ax.plot(x, 100 * monthly["temperature_unknown"], marker="s", ms=3.2, color=COLORS["cyan"], label="Upper-envelope unknown")
ax.set_ylabel("Sensor-windows (%)")
ax.set_xticks(x[::2], [period.strftime("%b\n%Y") for period in x[::2]])
ax.legend(loc="upper left")
ax.set_title("Unevaluated evidence through time")
style_axis(ax, grid=True)
panel_label(ax, "d")

save_figure(fig, OUT, "fig3_evidence_coverage")
