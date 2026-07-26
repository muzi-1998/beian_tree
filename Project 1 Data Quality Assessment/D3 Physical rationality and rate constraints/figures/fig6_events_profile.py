"""Figure 6: sensor profiles and physical-event burden."""

from __future__ import annotations

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from _figure_data import OUT, read, short_sensor
from _nature_style import COLORS, ISSUE_COLORS, panel_label, save_figure, style_axis


scores = read("D3_window_scores.xlsx")
events = read("D3_physical_events.xlsx")
profile = read("D3_sensor_summary.xlsx").sort_values("mean_D3")
order = list(profile.sensor_id)
y = np.arange(len(order))
fig, axes = plt.subplots(2, 2, figsize=(7.2, 5.5))
fig.subplots_adjust(left=0.11, right=0.98, bottom=0.10, top=0.96, wspace=0.38, hspace=0.42)

ax = axes[0, 0]
ax.hlines(y, profile.min_D3, profile.mean_D3, color=COLORS["light_gray"], linewidth=2.2)
ax.scatter(profile.min_D3, y, s=16, color=COLORS["red"], label="Minimum", zorder=3)
ax.scatter(profile.mean_D3, y, s=19, color=COLORS["blue"], label="Mean", zorder=3)
ax.set_yticks(y, [short_sensor(s) for s in order])
ax.set(xlabel="D3 score", xlim=(1, 5.05))
ax.legend(loc="lower right")
ax.set_title("Sensor-level score profiles")
style_axis(ax, grid=True)
panel_label(ax, "(a)")

ax = axes[0, 1]
evaluated = scores[scores.evidence_status == "sufficient"]
categories = pd.cut(evaluated.D3_total, [0, 1.6, 2.5, 3.5, 5.01], labels=["Invalid", "Review", "Report", "Train"])
fractions = pd.crosstab(evaluated.sensor_id, categories, normalize="index").reindex(order).fillna(0)
left = np.zeros(len(fractions))
for label, color in [("Invalid", COLORS["red"]), ("Review", COLORS["orange"]),
                     ("Report", COLORS["amber"]), ("Train", COLORS["green"])]:
    values = fractions[label].to_numpy() if label in fractions else np.zeros(len(fractions))
    ax.barh(y, values, left=left, height=0.68, color=color, label=label)
    left += values
ax.set_yticks(y, [short_sensor(s) for s in order])
ax.set(xlabel="Fraction of evaluated windows", xlim=(0, 1))
ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.00), ncol=4, columnspacing=0.8)
ax.set_title("Operational usability classes", y=1.14)
style_axis(ax)
panel_label(ax, "(b)")

ax = axes[1, 0]
event_counts = events.event_type.value_counts() if len(events) else pd.Series(dtype=int)
event_order = [item for item in ["instrument_range", "hard_bound", "rate_violation", "soft_bound", "low_quality_window"] if item in event_counts]
colors = [COLORS["red"] if name == "instrument_range" else ISSUE_COLORS.get(name, COLORS["gray"]) for name in event_order]
ax.bar(range(len(event_order)), event_counts.reindex(event_order), color=colors, width=0.65)
ax.set_xticks(range(len(event_order)), [name.replace("_", "\n") for name in event_order])
ax.set(ylabel="Event-window count")
if len(event_counts) and event_counts.min() > 0:
    ax.set_yscale("log")
ax.set_title("Physical event composition")
style_axis(ax, grid=True)
panel_label(ax, "(c)")

ax = axes[1, 1]
if len(events):
    events["month"] = pd.to_datetime(events.start_ts).dt.to_period("M").astype(str)
    calendar = events.pivot_table(index="sensor_id", columns="month", values="event_id", aggfunc="count", fill_value=0).reindex(order)
else:
    calendar = pd.DataFrame(0, index=order, columns=["none"])
image = ax.imshow(np.log1p(calendar), cmap="YlOrRd", aspect="auto")
ax.set_yticks(range(len(calendar)), [short_sensor(s) for s in calendar.index])
ax.set_xticks(range(len(calendar.columns)), [m[5:] if len(m) >= 7 else m for m in calendar.columns])
ax.set_xlabel("Month (2025-2026)")
ax.set_title("Event burden through time")
style_axis(ax, full_frame=True)
fig.colorbar(image, ax=ax, fraction=0.045, pad=0.03, label="log(1 + events)")
panel_label(ax, "(d)")

save_figure(fig, OUT, "fig6_events_profile")
