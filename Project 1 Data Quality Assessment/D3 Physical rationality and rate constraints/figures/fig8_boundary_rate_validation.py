"""Figure 8: controlled validation of persistent-rate ownership and robustness."""
# Shared Nature contract: Arial; svg.fonttype='none'; pdf.fonttype=42; .svg .pdf .png .tiff dpi=600.
# Figure contract: controlled morphologies and perturbations verify that D3
# responds to sustained dynamics while excluding impulses, steps, and coherent changes.

from __future__ import annotations

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from _figure_data import OUT, read_validation, sensor_order, short_sensor
from _nature_style import COLORS, panel_label, save_figure, style_axis


challenge = read_validation("D3_rate_construct_validation.xlsx", sheet_name="challenge_matrix")
dose = read_validation("D3_rate_construct_validation.xlsx", sheet_name="rate_dose_response")
overlap = read_validation("D3_rate_construct_validation.xlsx", sheet_name="D1_D3_overlap_summary")
sensitivity = read_validation("D3_threshold_sensitivity.xlsx", sheet_name="summary")

scenario_labels = {
    "single_point_spike": "1-min spike",
    "two_minute_spike": "2-min spike",
    "five_minute_block": "5-min block",
    "five_minute_soft_ramp": "5-min soft ramp",
    "thirty_minute_ramp": "30-min ramp",
    "permanent_step": "Permanent step",
    "multi_sensor_coherent_ramp": "Coherent ramp",
    "missing_recovery_jump": "Gap recovery",
}

fig, axes = plt.subplots(2, 2, figsize=(7.2, 5.55))
fig.subplots_adjust(left=0.12, right=0.98, bottom=0.10, top=0.96, wspace=0.41, hspace=0.46)

ax = axes[0, 0]
matrix = np.column_stack(
    [
        challenge["point_hard_rate"],
        challenge["persistent_soft_only_rate"],
        challenge["persistent_hard_rate"],
        challenge["impulse_return_events"].gt(0).astype(float),
        challenge["process_guarded_points"].gt(0).astype(float),
    ]
)
image = ax.imshow(matrix, cmap="Blues", vmin=0, vmax=1, aspect="auto")
ax.set_yticks(range(len(challenge)), [scenario_labels.get(value, value) for value in challenge["scenario"]])
ax.set_xticks(range(5), ["Point\nhard", "Soft-only\npersistent", "Hard\npersistent", "Impulse\nexclusion", "Process\nguard"])
for row in range(matrix.shape[0]):
    for column in range(matrix.shape[1]):
        value = matrix[row, column]
        label = "yes" if column >= 3 and value > 0 else "-" if column >= 3 else f"{value:.2f}"
        ax.text(column, row, label, ha="center", va="center", fontsize=5.9, color="white" if value > 0.55 else COLORS["black"])
ax.set_title("Fault morphology response matrix")
style_axis(ax, full_frame=True)
panel_label(ax, "a", x=-0.18)

ax = axes[0, 1]
for multiple, group in dose.groupby("hard_threshold_multiple"):
    group = group.sort_values("duration_min")
    ax.plot(group["duration_min"], group["Q_persistent_rate"], marker="o", ms=3.1, lw=0.9, label=f"{multiple:.1f}x hard limit")
ax.axvline(3, color=COLORS["cyan"], ls="--", lw=0.8, label="Soft persistence")
ax.axvline(10, color=COLORS["blue"], ls="--", lw=0.8, label="Hard persistence")
ax.axvline(30, color=COLORS["red"], ls=":", lw=0.9, label="Cap")
ax.set(xlabel="Same-direction duration (min)", ylabel=r"$Q_{persistent-rate}$", ylim=(1, 5.1))
ax.legend(loc="lower left", ncol=2)
ax.set_title("Dose-duration response")
style_axis(ax, grid=True)
panel_label(ax, "b")

ax = axes[1, 0]
group = sensitivity.loc[sensitivity["parameter"].eq("persistent_rate_limit")].sort_values("multiplier")
ax.plot(group["multiplier"], group["event_jaccard"], marker="o", ms=4, color=COLORS["blue"], label="Event Jaccard")
ax.axhline(0.75, color=COLORS["red"], ls=":", lw=0.8, label="Stability reference")
ax.axvline(1.0, color=COLORS["gray"], ls="--", lw=0.8)
ax.set(xlabel="Persistent-rate limit multiplier", ylabel="Event-set Jaccard", ylim=(0, 1.04))
ax2 = ax.twinx()
ax2.plot(group["multiplier"], group["variant_events"], marker="s", ms=3.5, mfc="white", color=COLORS["orange"], label="Event count")
ax2.set_ylabel("Detected events", color=COLORS["orange"])
ax2.tick_params(axis="y", colors=COLORS["orange"], direction="out")
ax2.spines["top"].set_visible(False)
lines, labels = ax.get_legend_handles_labels(); lines2, labels2 = ax2.get_legend_handles_labels()
ax.legend(lines + lines2, labels + labels2, loc="lower left")
ax.set_title("Prespecified rate-limit perturbation")
style_axis(ax, grid=True)
panel_label(ax, "c", x=-0.18)

ax = axes[1, 1]
sensor_rows = overlap.loc[overlap["stratum_level"].eq("sensor") & overlap["D1_construct"].isin(["Q_spike", "Q_step"])].copy()
order = sensor_order(list(sensor_rows["stratum"].unique()))
y = np.arange(len(order))
for construct, color, marker, offset in (("Q_spike", COLORS["purple"], "o", -0.12), ("Q_step", COLORS["green"], "s", 0.12)):
    group = sensor_rows.loc[sensor_rows["D1_construct"].eq(construct)].set_index("stratum").reindex(order)
    ax.scatter(group["event_jaccard"], y + offset, s=18, color=color, marker=marker, label=construct.replace("Q_", "D1 "))
ax.set_yticks(y, [short_sensor(sensor) for sensor in order])
ax.set(xlabel="Empirical event Jaccard", xlim=(-0.01, max(0.12, 1.1 * sensor_rows["event_jaccard"].max())))
ax.legend(loc="lower right")
ax.set_title("Sensor-level D1-D3 overlap")
style_axis(ax, grid=True)
panel_label(ax, "d")

save_figure(fig, OUT, "fig8_boundary_rate_validation")
