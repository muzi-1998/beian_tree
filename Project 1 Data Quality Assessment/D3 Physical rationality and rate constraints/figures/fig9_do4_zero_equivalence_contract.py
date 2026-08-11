"""Figure 9: post-anoxic DO zero-equivalence and parallel-line audit."""
# Shared Nature contract: Arial; svg.fonttype='none'; pdf.fonttype=42; .svg .pdf .png .tiff dpi=600.
# Figure contract: physical zero, measurement tolerance, and between-line
# heterogeneity remain distinct, with the latter quantified by block uncertainty.

from __future__ import annotations

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from mpl_toolkits.axes_grid1.inset_locator import inset_axes

from _figure_data import OUT, VALIDATION, read_validation, short_sensor
from _nature_style import COLORS, panel_label, save_figure, style_axis


views = pd.read_parquet(VALIDATION / "D3_DO4_zero_equivalence_views.parquet")
monthly = read_validation("D3_operational_envelope_diagnostics.xlsx", sheet_name="DO4_monthly_zero_stability")
parallel = read_validation("D3_operational_envelope_diagnostics.xlsx", sheet_name="DO4_parallel_line_diagnostic")
candidate = read_validation("D3_operational_envelope_diagnostics.xlsx", sheet_name="DO4_upper_candidate")
monthly["month"] = pd.to_datetime(monthly["month"])
parallel["month"] = pd.to_datetime(parallel["month"])

fig, axes = plt.subplots(2, 2, figsize=(7.2, 5.4))
fig.subplots_adjust(left=0.10, right=0.98, bottom=0.10, top=0.96, wspace=0.38, hspace=0.45)

ax = axes[0, 0]
colors = {"DO_1_4": COLORS["blue"], "DO_2_4": COLORS["orange"]}
ecdf_values = {}
for sensor in colors:
    raw_values = views.loc[views["sensor_id"].eq(sensor), "DO_raw"].to_numpy(dtype=float)
    ecdf_values[sensor] = np.sort(raw_values[np.isfinite(raw_values)])
for sensor, color in colors.items():
    values = ecdf_values[sensor]
    ecdf = np.arange(1, len(values) + 1) / len(values)
    ax.plot(values, ecdf, color=color, lw=1.0, label=f"{short_sensor(sensor)} (n={len(values):,})")
ax.set(xlabel="Raw post-anoxic DO (mg L$^{-1}$)", ylabel="Empirical cumulative probability")
ax.legend(loc="lower right")
ax.set_title("Full post-anoxic DO distributions")
style_axis(ax, grid=True)
inset = inset_axes(ax, width="48%", height="48%", loc="center right", borderpad=1.2)
for sensor, color in colors.items():
    values = ecdf_values[sensor]
    ecdf = np.arange(1, len(values) + 1) / len(values)
    inset.plot(values, ecdf, color=color, lw=0.8)
inset.axvspan(-0.05, 0.0, color=COLORS["cyan"], alpha=0.16)
inset.axvline(-0.20, color=COLORS["red"], lw=0.6, ls=":")
inset.axvline(-0.05, color=COLORS["navy"], lw=0.7, ls="--")
inset.axvline(0.0, color=COLORS["black"], lw=0.6)
inset.set_xlim(-0.25, 0.10)
inset.set_title("Near-zero zoom", fontsize=6.5)
inset.tick_params(labelsize=5.8, direction="in", top=True, right=True)
for spine in inset.spines.values(): spine.set_linewidth(0.7)
panel_label(ax, "a")

ax = axes[0, 1]
for sensor, color in colors.items():
    group = monthly.loc[monthly["sensor_id"].eq(sensor)].sort_values("month")
    ax.plot(group["month"], 100 * group["negative_rate"], marker="o", ms=3.2, color=color, label=short_sensor(sensor))
ax.set_ylabel("Negative raw minutes (%)")
ax.legend(loc="center right")
ax.set_title("Monthly zero-point stability")
style_axis(ax, grid=True)
ax.tick_params(axis="x", rotation=30)
panel_label(ax, "b")

ax = axes[1, 0]
x = np.arange(len(parallel))
estimate = parallel["paired_delta_median_mg_L"].to_numpy(dtype=float)
lower = estimate - parallel["paired_delta_day_block_ci_low"].to_numpy(dtype=float)
upper = parallel["paired_delta_day_block_ci_high"].to_numpy(dtype=float) - estimate
ax.errorbar(x, estimate, yerr=np.maximum(np.vstack([lower, upper]), 0), fmt="o", ms=3.6, color=COLORS["purple"], ecolor=COLORS["gray"], elinewidth=0.7, capsize=1.7)
ax.axhline(0.0, color=COLORS["black"], lw=0.8, ls="--")
ax.set_xticks(x[::2], [value.strftime("%b\n%Y") for value in parallel["month"].iloc[::2]])
ax.set_ylabel(r"Median $DO_{1,4}-DO_{2,4}$ (mg L$^{-1}$)")
ax.text(0.98, 0.06, "Calendar-day block bootstrap 95% CI", transform=ax.transAxes, ha="right", color=COLORS["gray"], fontsize=6.2)
ax.set_title("Parallel-line difference is quantified")
style_axis(ax, grid=True)
panel_label(ax, "c")

ax = axes[1, 1]
usable = candidate[candidate["sensor_id"].notna()].copy()
x = np.arange(len(usable))
ax.scatter(x - 0.13, usable["calibration_p99_mg_L"], s=24, color=COLORS["blue"], label="Calibration P99")
ax.scatter(x, usable["candidate_upper_mg_L"], s=28, marker="D", color=COLORS["navy"], label="Candidate upper")
ax.scatter(x + 0.13, usable["validation_p99_mg_L"], s=24, facecolors="white", edgecolors=COLORS["orange"], label="Validation P99")
for position, row in enumerate(usable.itertuples(index=False)):
    upper_value = np.nanmax([row.calibration_p99_mg_L, row.candidate_upper_mg_L, row.validation_p99_mg_L])
    label_y = upper_value + 0.05 if bool(row.support_passed) else upper_value - 0.08
    ax.text(position, label_y, "support passed" if bool(row.support_passed) else "support insufficient", ha="center", va="bottom", fontsize=5.9, color=COLORS["green"] if bool(row.support_passed) else COLORS["red"])
ax.set_xticks(x, [short_sensor(sensor) for sensor in usable["sensor_id"]])
ax.set_ylabel("Post-anoxic DO (mg L$^{-1}$)")
ax.legend(loc="upper left")
ax.set_title("Upper templates remain candidate-only")
style_axis(ax, grid=True)
panel_label(ax, "d")

save_figure(fig, OUT, "fig9_do4_zero_equivalence_contract")
