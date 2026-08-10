"""Figure 8: validation of provisional envelopes and persistent-rate ownership."""
# Shared Nature contract: Arial; font.size=7; svg.fonttype='none'; pdf.fonttype=42; .svg .pdf .tiff dpi=600.

from __future__ import annotations

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from _figure_data import OUT, read_validation, short_sensor
from _nature_style import COLORS, panel_label, save_figure, style_axis


deadband = read_validation(
    "D3_operational_envelope_diagnostics.xlsx", sheet_name="DO4_zero_eq_sensitivity"
)
direction = read_validation(
    "D3_operational_envelope_diagnostics.xlsx", sheet_name="directional_window_burden"
)
challenge = read_validation(
    "D3_rate_construct_validation.xlsx", sheet_name="challenge_matrix"
)
sensitivity = read_validation("D3_threshold_sensitivity.xlsx", sheet_name="summary")

fig, axes = plt.subplots(2, 2, figsize=(7.2, 5.4))
fig.subplots_adjust(left=0.10, right=0.98, bottom=0.11, top=0.96, wspace=0.38, hspace=0.43)

ax = axes[0, 0]
for sensor, color in zip(["DO_1_4", "DO_2_4"], [COLORS["blue"], COLORS["orange"]]):
    group = deadband[deadband.sensor_id == sensor].sort_values("zero_equivalence_low_mg_L")
    ax.plot(group.zero_equivalence_low_mg_L, 100 * group.zero_offset_warning_rate,
            marker="o", ms=4, color=color, label=short_sensor(sensor))
ax.axvline(-0.05, color=COLORS["navy"], ls="--", lw=0.9, label="Provisional tolerance")
ax.set(xlabel="Zero-equivalence lower edge (mg L$^{-1}$)", ylabel="Offset-warning observations (%)")
ax.legend(loc="upper left")
ax.set_title("DO4 zero-equivalence sensitivity")
style_axis(ax, grid=True)
panel_label(ax, "a")

ax = axes[0, 1]
orp = direction[direction.type == "ORP"].sort_values(["position", "pool"])
x = np.arange(len(orp))
ax.bar(x, 100 * orp.soft_low_window_rate, color=COLORS["purple"], label="Low-side")
ax.bar(x, 100 * orp.soft_high_window_rate, bottom=100 * orp.soft_low_window_rate,
       color=COLORS["amber"], label="High-side")
ax.set_xticks(x, [short_sensor(sensor) for sensor in orp.sensor_id], rotation=45, ha="right")
ax.set(ylabel="Windows with an excursion (%)")
ax.legend(loc="upper left")
ax.set_title("ORP3 departures are predominantly low-side")
style_axis(ax, grid=True)
panel_label(ax, "b")

ax = axes[1, 0]
labels = [
    "1-min spike", "2-min spike", "5-min block", "5-min soft", "30-min ramp",
    "Step", "Coherent ramp", "Gap recovery",
]
x = np.arange(len(challenge))
ax.bar(x - 0.26, 100 * challenge.point_hard_rate, 0.25, color=COLORS["orange"], label="Point hard")
ax.bar(x, 100 * challenge.persistent_soft_only_rate, 0.25, color=COLORS["cyan"], label="Soft-only")
ax.bar(x + 0.26, 100 * challenge.persistent_hard_rate, 0.25, color=COLORS["blue"], label="Hard persistent")
ax.set_xticks(x, labels, rotation=43, ha="right")
ax.tick_params(axis="x", labelsize=5.4)
ax.set(ylabel="Injected-window rate evidence (%)")
ax.legend(loc="upper left", ncol=1)
ax.set_title("Injected event morphology", loc="left")
style_axis(ax, grid=True)
panel_label(ax, "c", x=-0.15)

ax = axes[1, 1]
for parameter, color, marker in [
    ("operational_soft_envelope_width", COLORS["amber"], "o"),
    ("persistent_rate_limit", COLORS["blue"], "s"),
]:
    group = sensitivity[sensitivity.parameter == parameter].sort_values("multiplier")
    label = "Soft-envelope width" if parameter.startswith("operational") else "Persistent-rate limit"
    ax.plot(
        group.multiplier,
        group.event_jaccard,
        marker=marker,
        ms=4,
        color=color,
        label=label,
    )
ax.axhline(0.75, color=COLORS["red"], ls=":", lw=0.9, label="Prespecified stability reference")
ax.axvline(1.0, color=COLORS["gray"], ls="--", lw=0.8)
ax.set(xlabel="Threshold multiplier", ylabel="Event-set Jaccard", ylim=(-0.02, 1.02))
ax.legend(loc="lower left")
ax.set_title("Prespecified threshold perturbation")
style_axis(ax, grid=True)
panel_label(ax, "d")

save_figure(fig, OUT, "fig8_boundary_rate_validation")
