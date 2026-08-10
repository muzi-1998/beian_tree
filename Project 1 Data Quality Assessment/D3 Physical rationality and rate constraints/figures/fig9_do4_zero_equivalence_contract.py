"""Figure 9: DO4 zero-equivalence and post-anoxic validation contract."""
# Shared Nature contract: Arial; font.size=7; svg.fonttype='none'; pdf.fonttype=42; .svg .pdf .tiff dpi=600.

from __future__ import annotations

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from _figure_data import OUT, VALIDATION, read_validation, short_sensor
from _nature_style import COLORS, panel_label, save_figure, style_axis


views = pd.read_parquet(VALIDATION / "D3_DO4_zero_equivalence_views.parquet")
monthly = read_validation(
    "D3_operational_envelope_diagnostics.xlsx", sheet_name="DO4_monthly_zero_stability"
)
parallel = read_validation(
    "D3_operational_envelope_diagnostics.xlsx", sheet_name="DO4_parallel_line_diagnostic"
)
candidate = read_validation(
    "D3_operational_envelope_diagnostics.xlsx", sheet_name="DO4_upper_candidate"
)
monthly["month"] = pd.to_datetime(monthly["month"])
parallel["month"] = pd.to_datetime(parallel["month"])

fig, axes = plt.subplots(2, 2, figsize=(7.2, 5.3))
fig.subplots_adjust(left=0.10, right=0.98, bottom=0.11, top=0.96, wspace=0.35, hspace=0.43)

ax = axes[0, 0]
bins = np.linspace(-0.25, 0.10, 71)
for sensor, color in zip(("DO_1_4", "DO_2_4"), (COLORS["blue"], COLORS["orange"])):
    values = views.loc[views["sensor_id"].eq(sensor), "DO_raw"].to_numpy(dtype=float)
    values = values[np.isfinite(values)]
    counts, edges = np.histogram(values, bins=bins)
    frequency = 100.0 * counts / max(len(values), 1)
    ax.step(edges[:-1], frequency, where="post", color=color, label=short_sensor(sensor))
ax.axvspan(-0.25, -0.20, color=COLORS["red"], alpha=0.10)
ax.axvspan(-0.20, -0.05, color=COLORS["amber"], alpha=0.10)
ax.axvspan(-0.05, 0.00, color=COLORS["cyan"], alpha=0.13)
ax.axvline(-0.20, color=COLORS["red"], lw=0.8, ls=":")
ax.axvline(-0.05, color=COLORS["navy"], lw=0.9, ls="--")
ax.axvline(0.00, color=COLORS["black"], lw=0.8)
ax.set(xlim=(-0.25, 0.10), xlabel="Raw post-anoxic DO (mg L$^{-1}$)", ylabel="Observed minutes (%)")
ax.legend(loc="upper left")
ax.set_title("Physical zero and measurement tolerance remain distinct")
style_axis(ax, grid=True)
panel_label(ax, "a")

ax = axes[0, 1]
for sensor, color in zip(("DO_1_4", "DO_2_4"), (COLORS["blue"], COLORS["orange"])):
    group = monthly[monthly["sensor_id"].eq(sensor)].sort_values("month")
    ax.plot(group["month"], 100 * group["negative_rate"], marker="o", ms=3.5,
            color=color, label=short_sensor(sensor))
ax.set(ylabel="Observed minutes (%)")
ax.tick_params(axis="x", rotation=35)
ax.legend(loc="center right")
max_offset = 100 * monthly["zero_offset_warning_rate"].max()
ax.text(0.03, 0.13, f"Maximum offset-warning rate: {max_offset:.2f}%",
        transform=ax.transAxes, fontsize=6.2, color=COLORS["gray"], ha="left")
ax.set_title("Monthly zero-point stability")
style_axis(ax, grid=True)
panel_label(ax, "b")

ax = axes[1, 0]
ax.plot(parallel["month"], parallel["DO_1_4_median"], marker="o", ms=3.5,
        color=COLORS["blue"], label="DO-1-4")
ax.plot(parallel["month"], parallel["DO_2_4_median"], marker="s", ms=3.5,
        color=COLORS["orange"], label="DO-2-4")
ax.axhline(0.0, color=COLORS["gray"], lw=0.8, ls=":")
ax.set(ylabel="Monthly median DO (mg L$^{-1}$)")
ax.tick_params(axis="x", rotation=35)
ax.legend(loc="upper left")
ax.set_title("Parallel post-anoxic distributions are non-exchangeable")
style_axis(ax, grid=True)
panel_label(ax, "c")

ax = axes[1, 1]
usable = candidate[candidate["sensor_id"].notna()].copy()
x = np.arange(len(usable))
ax.scatter(x - 0.13, usable["calibration_p99_mg_L"], s=24, color=COLORS["blue"], label="Calibration P99")
ax.scatter(x, usable["candidate_upper_mg_L"], s=28, marker="D", color=COLORS["navy"], label="Candidate upper")
ax.scatter(x + 0.13, usable["validation_p99_mg_L"], s=24, facecolors="white",
           edgecolors=COLORS["orange"], label="Validation P99")
for position, row in enumerate(usable.itertuples(index=False)):
    upper = np.nanmax([row.calibration_p99_mg_L, row.candidate_upper_mg_L, row.validation_p99_mg_L])
    label_y = upper + 0.06 if bool(row.support_passed) else upper - 0.08
    ax.text(position, label_y, f"{int(row.calibration_hours)}/{int(row.validation_hours)} h",
            ha="center", va="bottom", fontsize=6.0, color=COLORS["gray"],
            bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.75, "pad": 0.1})
ax.set_xticks(x, [short_sensor(sensor) for sensor in usable["sensor_id"]])
ax.set(ylabel="Post-anoxic DO (mg L$^{-1}$)")
ax.legend(loc="upper left")
ax.set_title("Time-blocked upper-template support")
style_axis(ax, grid=True)
panel_label(ax, "d")

save_figure(fig, OUT, "fig9_do4_zero_equivalence_contract")
