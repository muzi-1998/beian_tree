"""Figure 4: rate-constraint evidence without D1 coupling."""

from __future__ import annotations

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from _figure_data import OUT, read, short_sensor
from _nature_style import COLORS, panel_label, save_figure, style_axis


rate = read("D4_rate_evidence.xlsx")
scores = read("D4_window_scores.xlsx")
rate["month"] = rate.ts.dt.to_period("M").astype(str)
fig, axes = plt.subplots(2, 2, figsize=(7.2, 5.3))
fig.subplots_adjust(left=0.10, right=0.98, bottom=0.10, top=0.96, wspace=0.36, hspace=0.42)

ax = axes[0, 0]
pivot = rate.pivot_table(index="sensor_id", columns="month", values="rate_hard_violation_rate", aggfunc="mean")
image = ax.imshow(pivot, cmap="magma_r", vmin=0, vmax=max(0.01, np.nanpercentile(pivot, 98)), aspect="auto")
ax.set_yticks(range(len(pivot)), [short_sensor(s) for s in pivot.index])
ax.set_xticks(range(len(pivot.columns)), [m[5:] for m in pivot.columns])
ax.set_xlabel("Month (2025-2026)")
ax.set_title("Hard-rate violation fraction")
style_axis(ax, full_frame=True)
fig.colorbar(image, ax=ax, fraction=0.045, pad=0.03)
panel_label(ax, "(a)")

ax = axes[0, 1]
merged = rate.merge(scores[["ts", "sensor_id", "Q_rate"]], on=["ts", "sensor_id"], how="inner")
sample = merged.sample(min(7000, len(merged)), random_state=44)
ax.scatter(sample.rate_hard_violation_rate, sample.Q_rate, s=5, alpha=0.25,
           color=COLORS["blue"], linewidths=0, rasterized=True)
curve = merged.groupby("rate_hard_violation_rate", as_index=False).Q_rate.median().sort_values("rate_hard_violation_rate")
ax.plot(curve.rate_hard_violation_rate, curve.Q_rate, color=COLORS["navy"], linewidth=1.2)
ax.set(xlabel="Hard-rate violation fraction", ylabel="Q rate", xlim=(0, max(0.12, merged.rate_hard_violation_rate.quantile(.995))), ylim=(1, 5.1))
ax.set_title("Rate evidence mapping")
style_axis(ax, minor=True)
panel_label(ax, "(b)")

ax = axes[1, 0]
runs = rate.loc[rate.rate_hard_consec_max_min > 0, "rate_hard_consec_max_min"]
if len(runs):
    bins = np.arange(0.5, min(60, runs.max()) + 1.5, 2)
    ax.hist(runs.clip(upper=60), bins=bins, color=COLORS["orange"], alpha=0.85)
ax.axvline(30, color=COLORS["red"], linestyle="--", linewidth=0.9, label="Persistent-rate veto")
ax.set(xlabel="Longest hard-rate run (min)", ylabel="Window count")
ax.legend(loc="upper right")
ax.set_title("Persistence, not isolated spikes")
style_axis(ax, grid=True)
panel_label(ax, "(c)")

ax = axes[1, 1]
top = list(rate.groupby("sensor_id").rate_hard_violation_rate.mean().nlargest(4).index)
for sensor, color in zip(top, [COLORS["red"], COLORS["orange"], COLORS["blue"], COLORS["purple"]]):
    series = rate[rate.sensor_id == sensor].set_index("ts").rate_hard_violation_rate.resample("1D").mean()
    ax.plot(series.index, series, label=short_sensor(sensor), color=color, alpha=0.9)
ax.set(xlabel="Date", ylabel="Daily hard-rate fraction")
ax.legend(loc="upper right", ncol=2)
ax.set_title("Most rate-sensitive sensors")
style_axis(ax, grid=True)
ax.tick_params(axis="x", rotation=25)
panel_label(ax, "(d)")

save_figure(fig, OUT, "fig4_rate_constraints")
