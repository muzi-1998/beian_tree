"""Figure 5: threshold provenance and diagnostic-only boundary evidence."""
# Shared Nature contract: Arial; svg.fonttype='none'; pdf.fonttype=42; .svg .pdf .png .tiff dpi=600.
# Figure contract: every threshold has an explicit evidence source and role;
# benchmark-tail diagnostics remain auditable but do not create a D3 subscore.

from __future__ import annotations

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from _figure_data import OUT, read, read_validation, sensor_order, short_sensor
from _nature_style import COLORS, panel_label, save_figure, style_axis


thresholds = read("D3_threshold_library.xlsx", sheet_name="full_library")
boundary = read("D3_boundary_diagnostics.xlsx")
registry = read_validation("D3_temperature_conditioned_DO_upper.xlsx", sheet_name="frozen_registry_check")
order = sensor_order(list(boundary["sensor_id"].unique()))

contracts = [
    ("DO instrument range", "instrument", True, False, True),
    ("ORP instrument range", "instrument", True, False, True),
    ("DO operating hard bounds", "prior", True, False, True),
    ("ORP operating hard bounds", "prior", True, False, True),
    ("ORP soft range", "prior", True, False, True),
    ("DO4 zero-equivalence", "resolution", True, False, True),
    ("DO persistent-rate limits", "prior", True, False, True),
    ("ORP persistent-rate limits", "prior", True, False, True),
    ("Aerobic DO dynamic upper", "site", True, True, bool(registry["registry_match"].all())),
    ("Benchmark tail / sticking", "benchmark", False, True, bool(thresholds.loc[thresholds["bound_type"].eq("boundary"), "validator_passed"].all())),
]
source_columns = ["Instrument\nregister", "Expert\nprior", "Site\ncalibrated", "Resolution\nprovisional", "Benchmark\nquantile", "Scored", "Diagnostic\noutput", "Validated\nimplementation"]
source_map = {"instrument": 0, "prior": 1, "site": 2, "resolution": 3, "benchmark": 4}
matrix = np.zeros((len(contracts), len(source_columns)))
for row, (_, source, scored, diagnostic, validated) in enumerate(contracts):
    matrix[row, source_map[source]] = 1
    matrix[row, 5] = int(scored)
    matrix[row, 6] = int(diagnostic)
    matrix[row, 7] = int(validated)

summary = boundary.groupby("sensor_id").agg(
    sticking_low=("boundary_sticking_low_rate", "mean"),
    sticking_high=("boundary_sticking_high_rate", "mean"),
    tail_low=("tail_rate_low", "mean"),
    tail_high=("tail_rate_high", "mean"),
).reindex(order)

fig = plt.figure(figsize=(7.2, 5.4))
grid = fig.add_gridspec(2, 2, height_ratios=[1.05, 1.0], left=0.16, right=0.98, bottom=0.10, top=0.96, wspace=0.37, hspace=0.48)

ax = fig.add_subplot(grid[0, :])
image = ax.imshow(matrix, cmap="Blues", vmin=0, vmax=1, aspect="auto")
ax.set_yticks(range(len(contracts)), [row[0] for row in contracts])
ax.set_xticks(range(len(source_columns)), source_columns)
for row in range(matrix.shape[0]):
    for column in range(matrix.shape[1]):
        ax.text(column, row, "X" if matrix[row, column] else "-", ha="center", va="center", fontsize=7.0, color="white" if matrix[row, column] else COLORS["light_gray"])
ax.axvline(4.5, color="white", lw=1.3)
ax.set_title("Threshold provenance, scoring role and implementation audit")
style_axis(ax, full_frame=True)
panel_label(ax, "a", x=-0.16)

ax = fig.add_subplot(grid[1, 0])
y = np.arange(len(order))
ax.barh(y - 0.16, 1000 * summary["tail_low"], height=0.30, color=COLORS["purple"], label="Lower tail")
ax.barh(y + 0.16, 1000 * summary["tail_high"], height=0.30, color=COLORS["green"], label="Upper tail")
ax.set_yticks(y, [short_sensor(sensor) for sensor in order])
ax.set_xlabel("Mean tail occupancy per 1,000 min")
ax.legend(loc="lower right")
ax.set_title("Benchmark-tail diagnostics")
style_axis(ax, grid=True)
panel_label(ax, "b", x=-0.18)

ax = fig.add_subplot(grid[1, 1])
ax.barh(y - 0.16, 1000 * summary["sticking_low"], height=0.30, color=COLORS["blue"], label="Low boundary")
ax.barh(y + 0.16, 1000 * summary["sticking_high"], height=0.30, color=COLORS["orange"], label="High boundary")
ax.set_yticks(y, [short_sensor(sensor) for sensor in order])
ax.set_xlabel("Mean boundary proximity per 1,000 min")
ax.legend(loc="lower right")
ax.text(0.98, 0.05, "Diagnostic only\nExcluded from D3 score", transform=ax.transAxes, ha="right", va="bottom", color=COLORS["gray"], fontsize=6.3)
ax.set_title("Fixed-bound proximity")
style_axis(ax, grid=True)
panel_label(ax, "c", x=-0.18)

save_figure(fig, OUT, "fig5_boundary_fixed_threshold")
