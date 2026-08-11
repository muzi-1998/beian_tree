"""Figure 10: calibrated temperature-conditioned aerobic DO upper envelopes."""
# Shared Nature contract: Arial; svg.fonttype='none'; pdf.fonttype=42; .svg .pdf .png .tiff dpi=600.
# Figure contract: minute-level position templates are frozen before validation;
# uncertainty and failed transfer are propagated rather than tuned away.

from __future__ import annotations

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from _figure_data import OUT, VALIDATION, read_validation, short_sensor
from _nature_style import COLORS, panel_label, save_figure, style_axis


detail = pd.read_parquet(VALIDATION / "D3_temperature_conditioned_DO_upper.parquet")
registry = read_validation("D3_temperature_conditioned_DO_upper.xlsx", sheet_name="frozen_registry_check")
phase = read_validation("D3_temperature_conditioned_DO_upper.xlsx", sheet_name="phase_validation")
alpha_ci = read_validation("D3_temperature_conditioned_DO_upper.xlsx", sheet_name="alpha_CI_scenarios")
comparison = read_validation("D3_temperature_conditioned_DO_upper.xlsx", sheet_name="envelope_comparison")

position_colors = {1: COLORS["blue"], 2: COLORS["green"], 3: COLORS["orange"]}
sensors = [f"DO_{line}_{position}" for position in (1, 2, 3) for line in (1, 2)]
x = np.arange(len(sensors), dtype=float)


def _warning_rate_axis(ax):
    ax.set_yscale("symlog", linthresh=0.2, linscale=0.85)
    ax.set_ylim(0, 80)
    ticks = [0, 0.1, 0.5, 1, 2, 5, 10, 25, 50]
    ax.set_yticks(ticks)
    ax.set_yticklabels([str(value) for value in ticks])

fig, axes = plt.subplots(2, 2, figsize=(7.2, 5.4))
fig.subplots_adjust(left=0.10, right=0.98, bottom=0.11, top=0.96, wspace=0.39, hspace=0.46)

# a, calibration distribution and frozen alpha uncertainty.
ax = axes[0, 0]
cal = detail.loc[detail["phase"].eq("calibration") & detail["high_quality_evaluable"] & detail["DO_over_Csat"].notna()]
for position in (1, 2, 3):
    values = cal.loc[cal["position"].eq(position), "DO_over_Csat"]
    q05, q25, q50, q75, q95 = values.quantile([0.05, 0.25, 0.50, 0.75, 0.95])
    color = position_colors[position]
    ax.plot([position, position], [q05, q95], color=color, lw=1.0)
    ax.plot([position, position], [q25, q75], color=color, lw=5.0, solid_capstyle="butt")
    ax.scatter(position, q50, s=15, color="white", edgecolor=color, zorder=3)
    row = registry.loc[registry["position"].eq(position)].iloc[0]
    frozen = float(row["frozen_alpha"])
    yerr = np.array([[frozen - float(row["alpha_cluster_bootstrap_ci_low"])], [float(row["alpha_cluster_bootstrap_ci_high"]) - frozen]])
    ax.errorbar(position + 0.14, frozen, yerr=yerr, fmt="D", ms=3.8, color=COLORS["black"], ecolor=COLORS["gray"], elinewidth=0.7, capsize=1.8)
ax.set_xticks([1, 2, 3], ["Position 1", "Position 2", "Position 3"])
ax.set_ylabel("Minute DO / reference $C_{sat}$")
ax.scatter([], [], marker="D", s=24, color=COLORS["black"], label=r"Frozen $\alpha$ (95% day-block CI)")
ax.legend(loc="upper left")
ax.set_title("Minute calibration and frozen uncertainty")
style_axis(ax, grid=True)
panel_label(ax, "a")

# b, direct fixed-versus-dynamic comparison in independent validation.
ax = axes[0, 1]
validation = comparison.loc[comparison["phase"].eq("validation")]
for model, color, marker, offset, label in (
    ("temperature_conditioned", COLORS["blue"], "o", -0.10, "Temperature-conditioned"),
    ("fixed_8_mg_L", COLORS["gray"], "s", 0.10, "Fixed 8 mg L$^{-1}$"),
):
    group = validation.loc[validation["envelope_model"].eq(model)].set_index("sensor_id").reindex(sensors)
    ax.scatter(x + offset, 100 * group["warning_2h_window_rate_high_quality"], s=20, marker=marker, color=color if model == "temperature_conditioned" else "white", edgecolor=color, label=label, zorder=3)
ax.axhline(2.0, color=COLORS["red"], lw=0.8, ls="--", label="2% criterion")
ax.axvspan(3.5, 5.5, color=COLORS["very_light"], zorder=0)
_warning_rate_axis(ax)
ax.set_xticks(x, [short_sensor(sensor) for sensor in sensors], rotation=35, ha="right")
ax.set_ylabel("Validation 2 h warning windows (%)")
ax.legend(loc="upper left")
ax.text(4.5, 48, "Diagnostic only", ha="center", color=COLORS["orange"], fontsize=6.2)
ax.set_title("Fixed 8 mg L$^{-1}$ masks position-specific burden")
style_axis(ax, grid=True)
panel_label(ax, "b")

# c, alpha interval endpoint propagation.
ax = axes[1, 0]
scenario_style = {
    "bootstrap_lower": (COLORS["red"], "^", "Lower 95% endpoint"),
    "point_estimate": (COLORS["blue"], "o", "Frozen point estimate"),
    "bootstrap_upper": (COLORS["green"], "v", "Upper 95% endpoint"),
}
scenario_offsets = {"bootstrap_lower": -0.16, "point_estimate": 0.0, "bootstrap_upper": 0.16}
for scenario, (color, marker, label) in scenario_style.items():
    group = alpha_ci.loc[alpha_ci["phase"].eq("validation") & alpha_ci["alpha_scenario"].eq(scenario)].set_index("sensor_id").reindex(sensors)
    ax.scatter(x + scenario_offsets[scenario], 100 * group["warning_2h_window_rate_high_quality"], s=20, marker=marker, facecolor=color if scenario == "point_estimate" else "white", edgecolor=color, label=label)
ax.axhline(2.0, color=COLORS["red"], lw=0.8, ls="--")
ax.axvspan(3.5, 5.5, color=COLORS["very_light"], zorder=0)
_warning_rate_axis(ax)
ax.set_xticks(x, [short_sensor(sensor) for sensor in sensors], rotation=35, ha="right")
ax.set_ylabel("Validation 2 h warning windows (%)")
ax.legend(loc="center left", bbox_to_anchor=(0.02, 0.55))
ax.set_title(r"Warning burden reflects $\alpha$ uncertainty")
style_axis(ax, grid=True)
panel_label(ax, "c")

# d, locked validation and terminal-test transfer with day-block intervals.
ax = axes[1, 1]
plot = phase.loc[phase["phase"].isin(["validation", "terminal_test"])]
for phase_name, color, marker, offset, filled, label in (
    ("validation", COLORS["blue"], "o", -0.11, True, "Independent validation"),
    ("terminal_test", COLORS["orange"], "s", 0.11, False, "Locked terminal test"),
):
    group = plot.loc[plot["phase"].eq(phase_name)].set_index("sensor_id").reindex(sensors)
    rate = 100 * group["warning_2h_window_rate_high_quality"].to_numpy(dtype=float)
    lower = 100 * group["warning_2h_window_rate_ci_low"].to_numpy(dtype=float)
    upper = 100 * group["warning_2h_window_rate_ci_high"].to_numpy(dtype=float)
    errors = np.maximum(np.vstack([rate - lower, upper - rate]), 0)
    ax.errorbar(x + offset, rate, yerr=errors, fmt=marker, ms=3.5, mfc=color if filled else "white", mec=color, ecolor=color, elinewidth=0.55, capsize=1.4, label=label)
ax.axhline(2.0, color=COLORS["red"], lw=0.8, ls="--", label="2% criterion")
ax.axvspan(3.5, 5.5, color=COLORS["very_light"], zorder=0)
_warning_rate_axis(ax)
ax.set_xticks(x, [short_sensor(sensor) for sensor in sensors], rotation=35, ha="right")
ax.set_ylabel("High-quality 2 h warning windows (%)")
ax.legend(loc="upper left")
ax.text(0.98, 0.07, "Position 3 remains\ndiagnostic only", transform=ax.transAxes, ha="right", va="bottom", color=COLORS["orange"], fontsize=6.2, bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.78, "pad": 0.1})
ax.set_title("Failed transfer is retained, not tuned away")
style_axis(ax, grid=True)
panel_label(ax, "d")

save_figure(fig, OUT, "fig10_temperature_conditioned_do_upper")
