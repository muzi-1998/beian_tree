"""Figure 10: minute-resolved temperature-conditioned aerobic DO envelopes."""
# Figure contract: frozen minute-level position templates transfer in the
# independent validation period for positions 1-2, while forward and cross-line
# diagnostics expose limitations rather than widening the envelope post hoc.

from __future__ import annotations

import matplotlib as mpl
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from _figure_data import OUT, VALIDATION, read_validation, short_sensor
from _nature_style import COLORS, panel_label, style_axis


mpl.rcParams.update(
    {
        "font.family": "Arial",
        "font.sans-serif": ["Arial", "DejaVu Sans"],
        "svg.fonttype": "none",
        "pdf.fonttype": 42,
    }
)

detail = pd.read_parquet(VALIDATION / "D3_temperature_conditioned_DO_upper.parquet")
detail["ts"] = pd.to_datetime(detail["ts"])
registry = read_validation(
    "D3_temperature_conditioned_DO_upper.xlsx", sheet_name="frozen_registry_check"
)
phase = read_validation(
    "D3_temperature_conditioned_DO_upper.xlsx", sheet_name="phase_validation"
)
audit = read_validation(
    "D3_temperature_conditioned_DO_upper.xlsx", sheet_name="source_audit"
).iloc[0]

colors = {1: COLORS["blue"], 2: COLORS["green"], 3: COLORS["orange"]}
fig, axes = plt.subplots(2, 2, figsize=(7.2, 5.25))
fig.subplots_adjust(left=0.09, right=0.98, bottom=0.10, top=0.96, wspace=0.32, hspace=0.44)

# a, full source coverage and the adopted monotonic normalizer.
ax = axes[0, 0]
source = detail.drop_duplicates("ts").set_index("ts").sort_index()
daily = source[["influent_temperature_C", "Csat_reference_mg_L"]].resample("1D").median()
ax.plot(daily.index, daily["influent_temperature_C"], color=COLORS["blue"], lw=1.1)
ax.set_ylabel(r"Influent temperature proxy ($^\circ$C)")
ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
ax.xaxis.set_major_formatter(mdates.DateFormatter("%b\n%Y"))
ax2 = ax.twinx()
ax2.plot(daily.index, daily["Csat_reference_mg_L"], color=COLORS["gray"], lw=0.9, ls="--")
ax2.set_ylabel("Reference $C_{sat}$ (mg L$^{-1}$)", color=COLORS["gray"])
ax2.tick_params(axis="y", colors=COLORS["gray"], direction="out")
ax2.spines["top"].set_visible(False)
ax2.spines["right"].set_linewidth(0.8)
ax.text(
    0.03,
    0.08,
    f"Valid study-minute coverage: {100 * float(audit['study_minute_coverage']):.1f}%\n"
    f"Raw missing / invalid: {int(audit['temperature_raw_missing']):,} / "
    f"{int(audit['temperature_invalid_range']):,} min",
    transform=ax.transAxes,
    fontsize=6.2,
    color=COLORS["gray"],
    ha="left",
    va="bottom",
    bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.82, "pad": 0.15},
)
ax.set_title("Audited full-year temperature normalizer")
style_axis(ax, grid=True)
panel_label(ax, "a")

# b, minute-level robust calibration distribution and day-block uncertainty.
ax = axes[0, 1]
cal = detail.loc[
    detail["phase"].eq("calibration")
    & detail["high_quality_evaluable"]
    & detail["DO_over_Csat"].notna()
]
for position in (1, 2, 3):
    values = cal.loc[cal["position"].eq(position), "DO_over_Csat"]
    q05, q25, q50, q75, q95 = values.quantile([0.05, 0.25, 0.50, 0.75, 0.95])
    ax.plot([position, position], [q05, q95], color=colors[position], lw=1.0)
    ax.plot(
        [position, position],
        [q25, q75],
        color=colors[position],
        lw=5.0,
        solid_capstyle="butt",
    )
    ax.scatter(position, q50, s=15, color="white", edgecolor=colors[position], zorder=3)
    registered = registry.loc[registry["position"].eq(position)].iloc[0]
    frozen = float(registered["frozen_alpha"])
    yerr = np.array(
        [
            [frozen - float(registered["alpha_cluster_bootstrap_ci_low"])],
            [float(registered["alpha_cluster_bootstrap_ci_high"]) - frozen],
        ]
    )
    ax.errorbar(
        position + 0.14,
        frozen,
        yerr=yerr,
        fmt="D",
        ms=3.8,
        color=COLORS["black"],
        ecolor=COLORS["gray"],
        elinewidth=0.7,
        capsize=1.8,
        zorder=4,
    )
    label_x = position + (0.10 if position == 1 else -0.03 if position == 3 else 0.0)
    ax.text(
        label_x,
        q95 + 0.025,
        f"n={len(values):,}",
        ha="center",
        fontsize=6.0,
        color=COLORS["gray"],
    )
ax.set_xticks([1, 2, 3], ["Position 1", "Position 2", "Position 3"])
ax.set_ylabel("Minute DO / reference $C_{sat}$")
ax.scatter([], [], marker="D", s=24, color=COLORS["black"], label=r"Frozen $\alpha$ (95% block CI)")
ax.legend(loc="upper left")
ax.set_title("Position templates use day-block uncertainty")
style_axis(ax, grid=True)
panel_label(ax, "b")

# c, weekly observed upper-tail DO against the frozen dynamic envelopes.
ax = axes[1, 0]
for position in (1, 2, 3):
    group = detail.loc[detail["position"].eq(position)].copy()
    upper = (
        group.drop_duplicates("ts")
        .set_index("ts")["dynamic_upper_mg_L"]
        .resample("7D")
        .median()
    )
    ax.plot(upper.index, upper, color=colors[position], lw=1.2, label=f"P{position} envelope")
    for sensor, sensor_group in group.groupby("sensor_id"):
        observed = (
            sensor_group.set_index("ts")["DO_minute_mg_L"].resample("7D").quantile(0.95)
        )
        ax.plot(
            observed.index,
            observed,
            color=colors[position],
            lw=0.65,
            alpha=0.55,
            ls=":" if "_1_" in sensor else "--",
        )
ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
ax.xaxis.set_major_formatter(mdates.DateFormatter("%b\n%Y"))
ax.set_ylabel("DO or envelope (mg L$^{-1}$)")
ax.legend(loc="upper right", ncol=1)
ax.text(
    0.03,
    0.08,
    "Solid: frozen dynamic envelope\nDotted/dashed: line-specific weekly P95",
    transform=ax.transAxes,
    fontsize=6.0,
    color=COLORS["gray"],
    bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.82, "pad": 0.12},
)
ax.set_title("Forward data retain longitudinal differences")
style_axis(ax, grid=True)
panel_label(ax, "c")

# d, validation and locked terminal-test burden with day-block intervals.
ax = axes[1, 1]
plot = phase.loc[phase["phase"].isin(["validation", "terminal_test"])].copy()
sensors = [f"DO_{line}_{position}" for position in (1, 2, 3) for line in (1, 2)]
x = np.arange(len(sensors), dtype=float)
series = (
    ("validation", "dynamic_warning_rate_high_quality", "dynamic_warning_rate_hq_ci_low", "dynamic_warning_rate_hq_ci_high", -0.18, "o", True, "Validation: minute"),
    ("validation", "warning_2h_window_rate_high_quality", "warning_2h_window_rate_ci_low", "warning_2h_window_rate_ci_high", -0.06, "s", True, "Validation: 2 h window"),
    ("terminal_test", "dynamic_warning_rate_high_quality", "dynamic_warning_rate_hq_ci_low", "dynamic_warning_rate_hq_ci_high", 0.06, "o", False, "Terminal: minute"),
    ("terminal_test", "warning_2h_window_rate_high_quality", "warning_2h_window_rate_ci_low", "warning_2h_window_rate_ci_high", 0.18, "s", False, "Terminal: 2 h window"),
)
for phase_name, value_col, low_col, high_col, offset, marker, filled, label in series:
    group = plot.loc[plot["phase"].eq(phase_name)].set_index("sensor_id").reindex(sensors)
    rate = 100 * group[value_col].to_numpy(dtype=float)
    lower = 100 * group[low_col].to_numpy(dtype=float)
    upper = 100 * group[high_col].to_numpy(dtype=float)
    yerr = np.maximum(np.vstack([rate - lower, upper - rate]), 0.0)
    for index, sensor in enumerate(sensors):
        color = colors[int(sensor[-1])]
        ax.errorbar(
            x[index] + offset,
            rate[index],
            yerr=yerr[:, index].reshape(2, 1),
            fmt=marker,
            ms=3.5,
            mfc=color if filled else "white",
            mec=color,
            mew=0.7,
            ecolor=color,
            elinewidth=0.55,
            capsize=1.4,
            zorder=2,
        )
    ax.plot(
        [],
        [],
        marker=marker,
        ms=3.5,
        mfc=COLORS["gray"] if filled else "white",
        mec=COLORS["gray"],
        lw=0,
        label=label,
    )
ax.axhline(2.0, color=COLORS["red"], lw=0.8, ls="--", label="2% criterion")
ax.axvspan(3.5, 5.5, color=COLORS["very_light"], zorder=0)
ax.set_yscale("symlog", linthresh=0.5, linscale=0.85)
ax.set_ylim(0, 80)
ax.set_yticks([0, 0.1, 0.5, 1, 2, 5, 10, 25, 50])
ax.set_yticklabels(["0", "0.1", "0.5", "1", "2", "5", "10", "25", "50"])
ax.text(4.5, 60, "Diagnostic only", ha="center", va="top", fontsize=6.2, color=COLORS["orange"])
ax.set_xticks(x, [short_sensor(sensor) for sensor in sensors], rotation=35, ha="right")
ax.set_ylabel("High-quality warning rate (%)")
ax.legend(loc="upper left", ncol=1, fontsize=5.5)
ax.set_title("Validation passes positions 1-2; forward limits remain")
style_axis(ax, grid=True)
panel_label(ax, "d")

OUT.mkdir(parents=True, exist_ok=True)
stem = OUT / "fig10_temperature_conditioned_do_upper"
fig.savefig(f"{stem}.svg", bbox_inches="tight")
fig.savefig(f"{stem}.pdf", bbox_inches="tight")
fig.savefig(f"{stem}.png", dpi=600, bbox_inches="tight")
fig.savefig(
    f"{stem}.tiff",
    dpi=600,
    bbox_inches="tight",
    pil_kwargs={"compression": "tiff_lzw"},
)
plt.close(fig)
