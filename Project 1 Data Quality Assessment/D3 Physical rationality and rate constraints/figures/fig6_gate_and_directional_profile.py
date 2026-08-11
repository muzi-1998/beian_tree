"""Figure 6: site-wide D3 gate burden and scored-versus-diagnostic evidence."""
# Shared Nature contract: Arial; svg.fonttype='none'; pdf.fonttype=42; .svg .pdf .png .tiff dpi=600.
# Figure contract: formal gate outcomes are reported with uncertainty and are
# separated from contextual evidence that supports interpretation only.

from __future__ import annotations

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from _figure_data import OUT, read, sensor_order, short_sensor
from _nature_style import COLORS, ISSUE_COLORS, panel_label, save_figure, style_axis


def _wilson(success: int, total: int, z: float = 1.96) -> tuple[float, float]:
    if total == 0:
        return np.nan, np.nan
    p = success / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    half = z * np.sqrt(p * (1 - p) / total + z * z / (4 * total * total)) / denominator
    return center - half, center + half


scores = read("D3_window_scores.xlsx")
events = read("D3_physical_events.xlsx")
value = read("D3_value_evidence.xlsx")
rate = read("D3_rate_evidence.xlsx")
evaluated = scores[scores["evidence_status"].eq("sufficient")].copy()
order = sensor_order(list(evaluated["sensor_id"].unique()))
y = np.arange(len(order))

warn_rows = []
for sensor in order:
    group = evaluated.loc[evaluated["sensor_id"].eq(sensor)]
    count = int(group["operational_warning_flag"].sum())
    low, high = _wilson(count, len(group))
    warn_rows.append((sensor, count / len(group), low, high, len(group)))
warn = pd.DataFrame(warn_rows, columns=["sensor_id", "rate", "low", "high", "n"]).set_index("sensor_id")

fig, axes = plt.subplots(2, 2, figsize=(7.2, 5.7))
fig.subplots_adjust(left=0.11, right=0.98, bottom=0.11, top=0.96, wspace=0.42, hspace=0.46)

ax = axes[0, 0]
x = 100 * warn.loc[order, "rate"].to_numpy()
lower = 100 * (warn.loc[order, "rate"] - warn.loc[order, "low"]).to_numpy()
upper = 100 * (warn.loc[order, "high"] - warn.loc[order, "rate"]).to_numpy()
ax.errorbar(x, y, xerr=np.vstack([lower, upper]), fmt="o", ms=3.6, color=COLORS["amber"], ecolor=COLORS["gray"], elinewidth=0.7, capsize=1.7)
ax.set_yticks(y, [short_sensor(sensor) for sensor in order])
ax.set_xlabel("Warn windows among evaluated windows (%)")
ax.text(0.98, 0.05, "Wilson 95% CI", transform=ax.transAxes, ha="right", color=COLORS["gray"], fontsize=6.3)
ax.set_title("Channel-level operational warning burden")
style_axis(ax, grid=True)
panel_label(ax, "a")

ax = axes[0, 1]
gate_order = ["Pass", "Warn", "Fail"]
fractions = pd.crosstab(evaluated["sensor_id"], evaluated["D3_gate_status"], normalize="index").reindex(order).fillna(0)
left = np.zeros(len(order))
for label, color, hatch in zip(gate_order, [COLORS["green"], COLORS["amber"], COLORS["red"]], ["", "//", "xx"]):
    values = fractions[label].to_numpy() if label in fractions else np.zeros(len(order))
    ax.barh(y, values, left=left, height=0.68, color=color, hatch=hatch, edgecolor="white", linewidth=0.35, label=label)
    left += values
ax.set_yticks(y, [short_sensor(sensor) for sensor in order])
ax.set(xlabel="Fraction of evaluated windows", xlim=(0, 1))
ax.legend(loc="lower center", bbox_to_anchor=(0.5, 1.01), ncol=3)
ax.set_title("Pass, warning and instrument-failure states", y=1.10)
style_axis(ax)
panel_label(ax, "b")

ax = axes[1, 0]
event_labels = [
    ("instrument_range", "Instrument\nrange"),
    ("hard_bound", "Operating\nhard bound"),
    ("soft_bound", "Operating\nsoft bound"),
    ("persistent_rate_soft_only", "Persistent\nsoft-only"),
    ("persistent_rate_hard", "Persistent\nhard"),
    ("process_coherent_shock", "Process-coherent\nshock"),
]
counts = events["event_type"].value_counts()
values = [int(counts.get(key, 0)) for key, _ in event_labels]
colors = [ISSUE_COLORS.get(key, COLORS["gray"]) for key, _ in event_labels]
bars = ax.bar(range(len(event_labels)), values, color=colors, width=0.66)
ax.set_xticks(range(len(event_labels)), ["Instrument", "Hard bound", "Soft bound", "Soft-only", "Hard persistent", "Process guard"], rotation=28, ha="right")
ax.set_ylabel("Two-hour event windows")
for bar, count in zip(bars, values):
    ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height(), f"{count:,}", ha="center", va="bottom", fontsize=6.0)
ax.set_title("Event identity follows the v2.7 contract")
style_axis(ax, grid=True)
panel_label(ax, "c")

ax = axes[1, 1]
evidence = pd.DataFrame(index=order)
evidence["Hard bound"] = value.groupby("sensor_id")["hard_violation_rate"].apply(lambda x: 1000 * x.gt(0).mean())
evidence["Soft bound"] = value.groupby("sensor_id")["soft_violation_rate"].apply(lambda x: 1000 * x.gt(0).mean())
evidence["Soft-only rate"] = rate.groupby("sensor_id")["rate_soft_only_violation_rate"].apply(lambda x: 1000 * x.gt(0).mean())
evidence["Hard persistent"] = rate.groupby("sensor_id")["rate_hard_violation_rate"].apply(lambda x: 1000 * x.gt(0).mean())
evidence["Process guard"] = rate.groupby("sensor_id")["process_coherence_guarded_points"].apply(lambda x: 1000 * x.gt(0).mean())
evidence["Zero-equivalent"] = value.groupby("sensor_id")["zero_equivalent_rate"].apply(lambda x: 1000 * x.gt(0).mean())
evidence["Upper diagnostic"] = value.assign(active=~value["soft_high_scored"] & value["soft_high_violation_rate"].gt(0)).groupby("sensor_id")["active"].mean() * 1000
matrix = evidence.to_numpy(dtype=float)
vmax = max(1.0, float(np.nanpercentile(matrix, 98)))
image = ax.imshow(matrix, cmap="YlOrRd", vmin=0, vmax=vmax, aspect="auto")
ax.set_yticks(range(len(order)), [short_sensor(sensor) for sensor in order])
ax.set_xticks(range(len(evidence.columns)), [label.replace(" ", "\n") for label in evidence.columns], rotation=25, ha="right")
ax.axvline(3.5, color="white", lw=1.5, ls="--")
ax.set_title("Scored evidence vs diagnostic-only context")
style_axis(ax, full_frame=True)
fig.colorbar(image, ax=ax, fraction=0.046, pad=0.025, label="Affected windows per 1,000")
panel_label(ax, "d")

save_figure(fig, OUT, "fig6_gate_and_directional_profile")
