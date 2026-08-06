"""Figure 3: evidence coverage and not-evaluated behavior."""
# Shared Nature contract: Arial; font.size=7; svg.fonttype='none'; pdf.fonttype=42; .svg .pdf .tiff dpi=600.

from __future__ import annotations

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from _figure_data import OUT, read, short_sensor
from _nature_style import COLORS, panel_label, save_figure, style_axis


scores = read("D3_window_scores.xlsx")
scores["month"] = scores.ts.dt.to_period("M").astype(str)
profile = read("D3_sensor_summary.xlsx")
order = list(profile.sort_values("evaluation_coverage").sensor_id)
fig, axes = plt.subplots(2, 2, figsize=(7.2, 5.3))
fig.subplots_adjust(left=0.11, right=0.98, bottom=0.10, top=0.96, wspace=0.36, hspace=0.42)

ax = axes[0, 0]
p = profile.set_index("sensor_id").loc[order]
ax.barh(range(len(p)), p.evaluation_coverage, color=COLORS["green"], height=0.68)
ax.set_yticks(range(len(p)), [short_sensor(s) for s in p.index])
ax.axvline(0.5, color=COLORS["red"], linestyle="--", linewidth=0.8, label="Minimum evidence")
ax.set(xlabel="Evaluated-window fraction", xlim=(0, 1.01))
ax.legend(loc="lower right")
ax.set_title("Evaluation coverage")
style_axis(ax, grid=True)
panel_label(ax, "(a)")

ax = axes[0, 1]
coverage = scores.pivot_table(index="sensor_id", columns="month", values="observed_fraction", aggfunc="mean").reindex(order)
image = ax.imshow(coverage, cmap="YlGnBu", vmin=0, vmax=1, aspect="auto")
ax.set_yticks(range(len(coverage)), [short_sensor(s) for s in coverage.index])
ax.set_xticks(range(len(coverage.columns)), [m[5:] for m in coverage.columns])
ax.set_xlabel("Month (2025-2026)")
ax.set_title("Mean observed fraction")
style_axis(ax, full_frame=True)
fig.colorbar(image, ax=ax, fraction=0.045, pad=0.03, label="Observed fraction")
panel_label(ax, "(b)")

ax = axes[1, 0]
labels = ["<=0.50", "0.50-0.75", "0.75-0.90", ">0.90"]
scores["coverage_bin"] = pd.cut(scores.observed_fraction, [-.001, .5, .75, .9, 1.001], labels=labels)
gate = scores.groupby("coverage_bin", observed=False).agg(
    evaluated=("D3_total", lambda x: x.notna().mean()), n=("sensor_id", "size")
).reindex(labels).fillna(0)
bars = ax.bar(range(len(labels)), gate.evaluated, color=COLORS["purple"], width=0.62)
for bar, count in zip(bars, gate.n.astype(int)):
    ax.text(bar.get_x() + bar.get_width()/2, min(bar.get_height()+.04, .96), f"n={count:,}",
            ha="center", va="bottom" if bar.get_height() < .9 else "top",
            color="white" if bar.get_height() > .9 else COLORS["black"])
ax.set_xticks(range(len(labels)), labels)
ax.set(xlabel="Observed fraction", ylabel="Evaluated-window fraction", ylim=(0, 1.03))
ax.set_title("Explicit evidence gate")
style_axis(ax, grid=True)
panel_label(ax, "(c)")

ax = axes[1, 1]
daily = scores.assign(day=scores.ts.dt.floor("D")).groupby("day").agg(
    evaluated=("D3_total", lambda x: x.notna().mean()), observed=("observed_fraction", "mean")
)
ax.plot(daily.index, daily.evaluated, color=COLORS["purple"], label="Evaluated")
ax.plot(daily.index, daily.observed, color=COLORS["cyan"], label="Observed")
ax.set(xlabel="Date", ylabel="Daily fraction", ylim=(0, 1.03))
ax.legend(loc="lower left", ncol=2)
ax.set_title("Coverage through time")
style_axis(ax, grid=True)
ax.tick_params(axis="x", rotation=25)
panel_label(ax, "(d)")

save_figure(fig, OUT, "fig3_evidence_coverage")
