"""Figure 4: persistent-rate construct and empirical D1-D3 separation."""
# Shared Nature contract: Arial; font.size=7; svg.fonttype='none'; pdf.fonttype=42; .svg .pdf .tiff dpi=600.

from __future__ import annotations

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from _figure_data import OUT, read, read_validation, short_sensor
from _nature_style import COLORS, panel_label, save_figure, style_axis


rate = read("D3_rate_evidence.xlsx")
overlap = read_validation(
    "D3_rate_construct_validation.xlsx", sheet_name="D1_D3_overlap_summary"
)
profile = (
    rate.groupby("sensor_id", as_index=False)
    .agg(
        point_windows=("rate_hard_point_violation_rate", lambda x: 1000 * x.gt(0).mean()),
        soft_only_windows=("rate_soft_only_violation_rate", lambda x: 1000 * x.gt(0).mean()),
        hard_persistent_windows=("rate_hard_violation_rate", lambda x: 1000 * x.gt(0).mean()),
        impulse_windows=("impulse_return_event_count", lambda x: 1000 * x.gt(0).mean()),
        guard_windows=("process_coherence_guarded_points", lambda x: 1000 * x.gt(0).mean()),
    )
    .sort_values("point_windows")
)

fig, axes = plt.subplots(2, 2, figsize=(7.2, 5.5))
fig.subplots_adjust(left=0.11, right=0.98, bottom=0.10, top=0.96, wspace=0.38, hspace=0.42)

ax = axes[0, 0]
y = np.arange(len(profile))
ax.hlines(y, profile.soft_only_windows, profile.point_windows, color=COLORS["light_gray"], lw=1.5)
ax.scatter(profile.point_windows, y, s=18, color=COLORS["orange"], label="Point excursion")
ax.scatter(profile.soft_only_windows, y, s=18, color=COLORS["cyan"], label="Soft-only persistent")
ax.scatter(profile.hard_persistent_windows, y, s=18, marker="s", color=COLORS["blue"], label="Hard persistent")
ax.set_yticks(y, [short_sensor(sensor) for sensor in profile.sensor_id])
ax.set(xlabel="Affected windows per 1,000", ylabel="")
ax.legend(loc="lower right")
ax.set_title("Persistence removes isolated excursions")
style_axis(ax, grid=True)
panel_label(ax, "a")

ax = axes[0, 1]
width = 0.36
x = np.arange(len(profile))
ax.bar(x - width / 2, profile.impulse_windows, width, color=COLORS["purple"], label="Impulse-return")
ax.bar(x + width / 2, profile.guard_windows, width, color=COLORS["green"], label="Process guard")
ax.set_xticks(x, [short_sensor(sensor) for sensor in profile.sensor_id], rotation=55, ha="right")
ax.set(ylabel="Excluded windows per 1,000")
ax.legend(loc="upper left")
ax.set_title("Explicit attribution exclusions")
style_axis(ax, grid=True)
panel_label(ax, "b")

ax = axes[1, 0]
raw_runs = rate.rate_hard_consec_raw_max_min.to_numpy(dtype=float)
final_runs = rate.rate_hard_consec_max_min.to_numpy(dtype=float)
maximum = max(12, int(np.nanmax(raw_runs)))
run_axis = np.arange(1, maximum + 1)
raw_survival = np.array([100 * np.mean(raw_runs >= value) for value in run_axis])
final_survival = np.array([100 * np.mean(final_runs >= value) for value in run_axis])
ax.step(run_axis[raw_survival > 0], raw_survival[raw_survival > 0], where="post",
        color=COLORS["orange"], label="Before process guard")
ax.step(run_axis[final_survival > 0], final_survival[final_survival > 0], where="post",
        color=COLORS["blue"], label="Final unguarded runs")
ax.axvline(10, color=COLORS["navy"], ls="--", lw=0.9, label="Score gate (10 min)")
ax.axvline(30, color=COLORS["red"], ls=":", lw=1.0, label="Veto gate (30 min)")
ax.set(xlabel="Same-sign hard-rate run (min)", ylabel="Windows at or above threshold (%)")
ax.set_yscale("log")  # Strictly positive survival values are filtered explicitly above.
ax.set_ylim(0.001, max(5.0, 1.2 * np.nanmax(raw_survival)))
ax.legend(loc="upper right")
ax.set_title("Duration, not amplitude alone, defines D3")
style_axis(ax, grid=True)
panel_label(ax, "c")

ax = axes[1, 1]
overall = overlap[(overlap.stratum_level == "overall") & (overlap.stratum == "all")].copy()
metrics = ["event_jaccard", "P_D3_given_D1", "P_D1_given_D3"]
labels = ["Jaccard", "P(D3 | D1)", "P(D1 | D3)"]
colors = [COLORS["blue"], COLORS["amber"]]
for offset, (row, color) in enumerate(zip(overall.itertuples(index=False), colors)):
    values = [getattr(row, metric) for metric in metrics]
    positions = np.arange(len(metrics)) + (offset - 0.5) * 0.18
    ax.scatter(positions, values, s=30, color=color, label=row.D1_construct.replace("Q_", "D1 "), zorder=3)
    ax.plot(positions, values, color=color, lw=0.8, alpha=0.7)
if overall.D3_events.sum() == 0:
    ax.text(0.98, 0.08, "No empirical D3 persistent-rate events\nconditional reverse probability not estimable",
            transform=ax.transAxes, ha="right", va="bottom", fontsize=6.2, color=COLORS["gray"])
ax.set_xticks(range(len(metrics)), labels)
ax.set(ylabel="Event concordance", ylim=(-0.02, 1.02))
ax.legend(loc="upper right")
ax.set_title("Observed D1-D3 overlap is reported, not assumed")
style_axis(ax, grid=True)
panel_label(ax, "d")

save_figure(fig, OUT, "fig4_persistent_rate_construct")
