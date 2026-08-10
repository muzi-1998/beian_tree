"""Figure 10: time-blocked temperature-conditioned aerobic DO envelopes."""
# Figure contract: time-blocked position-shared envelopes transfer for positions
# 1-2, whereas position 3 remains diagnostic after failed temporal stability.

from __future__ import annotations

import numpy as np
import pandas as pd
import matplotlib as mpl
import matplotlib.dates as mdates
import matplotlib.pyplot as plt

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


def wilson_interval(events: int, total: int, z: float = 1.96) -> tuple[float, float]:
    if total <= 0:
        return np.nan, np.nan
    p = events / total
    denominator = 1.0 + z**2 / total
    center = (p + z**2 / (2.0 * total)) / denominator
    half = z * np.sqrt(p * (1.0 - p) / total + z**2 / (4.0 * total**2)) / denominator
    return center - half, center + half


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

# a, full source coverage and temperature normalizer.
ax = axes[0, 0]
source = detail.drop_duplicates("ts").set_index("ts").sort_index()
daily = source[["influent_temperature_C", "Csat_reference_mg_L"]].resample("1D").median()
ax.plot(daily.index, daily["influent_temperature_C"], color=COLORS["blue"], lw=1.1)
ax.set(ylabel="Influent temperature proxy (°C)")
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
    f"Valid study-hour coverage: {100 * float(audit['study_hour_coverage']):.1f}%\n"
    f"Raw missing / invalid: {int(audit['temperature_raw_missing']):,} / "
    f"{int(audit['temperature_invalid_range']):,} min",
    transform=ax.transAxes,
    fontsize=6.2,
    color=COLORS["gray"],
    ha="left",
    va="bottom",
    bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.82, "pad": 0.15},
)
ax.set_title("Complete time axis with audited temperature evidence")
style_axis(ax, grid=True)
panel_label(ax, "a")

# b, robust calibration distribution and frozen alpha.
ax = axes[0, 1]
cal = detail.loc[
    detail["phase"].eq("calibration")
    & detail["high_quality_filter_pass"]
    & detail["DO_over_Csat"].notna()
]
for position in (1, 2, 3):
    values = cal.loc[cal["position"].eq(position), "DO_over_Csat"]
    q05, q25, q50, q75, q95 = values.quantile([0.05, 0.25, 0.50, 0.75, 0.95])
    ax.plot([position, position], [q05, q95], color=colors[position], lw=1.0)
    ax.plot([position, position], [q25, q75], color=colors[position], lw=5.0, solid_capstyle="butt")
    ax.scatter(position, q50, s=15, color="white", edgecolor=colors[position], zorder=3)
    frozen = registry.loc[registry["position"].eq(position), "frozen_alpha"].iloc[0]
    ax.scatter(position + 0.14, frozen, marker="D", s=24, color=COLORS["black"], zorder=4)
    label_x = position + (0.10 if position == 1 else -0.03 if position == 3 else 0.0)
    ax.text(label_x, q95 + 0.025, f"n={len(values):,}", ha="center", fontsize=6.0, color=COLORS["gray"])
ax.set_xticks([1, 2, 3], ["Position 1", "Position 2", "Position 3"])
ax.set(ylabel="Hourly DO / reference $C_{sat}$")
ax.scatter([], [], marker="D", s=24, color=COLORS["black"], label="Frozen $\\alpha$")
ax.legend(loc="upper left")
ax.set_title("Parallel lines share a position-specific calibration")
style_axis(ax, grid=True)
panel_label(ax, "b")

# c, weekly observed upper-tail DO against the dynamic envelopes.
ax = axes[1, 0]
for position in (1, 2, 3):
    group = detail.loc[detail["position"].eq(position)].copy()
    upper = group.drop_duplicates("ts").set_index("ts")["dynamic_upper_mg_L"].resample("7D").median()
    ax.plot(upper.index, upper, color=colors[position], lw=1.2, label=f"P{position} envelope")
    for sensor, sensor_group in group.groupby("sensor_id"):
        observed = sensor_group.set_index("ts")["DO_hourly_mean_mg_L"].resample("7D").quantile(0.95)
        ax.plot(observed.index, observed, color=colors[position], lw=0.65, alpha=0.55, ls=":" if "_1_" in sensor else "--")
ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
ax.xaxis.set_major_formatter(mdates.DateFormatter("%b\n%Y"))
ax.set(ylabel="DO or envelope (mg L$^{-1}$)")
ax.legend(loc="upper right", ncol=1)
ax.text(
    0.03,
    0.08,
    "Solid: dynamic envelope\nDotted/dashed: line-specific weekly P95",
    transform=ax.transAxes,
    fontsize=6.0,
    color=COLORS["gray"],
    bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.82, "pad": 0.12},
)
ax.set_title("Dynamic envelopes preserve longitudinal process differences")
style_axis(ax, grid=True)
panel_label(ax, "c")

# d, independent validation and terminal-test false-warning burden.
ax = axes[1, 1]
plot = phase.loc[phase["phase"].isin(["validation", "terminal_test"])].copy()
sensors = [f"DO_{line}_{position}" for position in (1, 2, 3) for line in (1, 2)]
x = np.arange(len(sensors), dtype=float)
offsets = {"validation": -0.11, "terminal_test": 0.11}
markers = {"validation": "o", "terminal_test": "s"}
for phase_name in ("validation", "terminal_test"):
    group = plot.loc[plot["phase"].eq(phase_name)].set_index("sensor_id").reindex(sensors)
    rate = group["dynamic_warning_rate_high_quality"].to_numpy(dtype=float)
    lower, upper = [], []
    for row in group.itertuples():
        lo, hi = wilson_interval(
            int(row.dynamic_warning_count_high_quality), int(row.n_high_quality_hours)
        )
        lower.append(lo)
        upper.append(hi)
    yerr = np.maximum(
        np.vstack([rate - np.asarray(lower), np.asarray(upper) - rate]),
        0.0,
    )
    face = [colors[int(sensor[-1])] for sensor in sensors]
    ax.errorbar(x + offsets[phase_name], 100 * rate, yerr=100 * yerr, fmt="none",
                ecolor=COLORS["gray"], elinewidth=0.7, capsize=1.8, zorder=1)
    ax.scatter(x + offsets[phase_name], 100 * rate, s=24, marker=markers[phase_name],
               c=face, edgecolor="white", linewidth=0.45, zorder=2, label=phase_name.replace("_", " ").title())
ax.axhline(2.0, color=COLORS["red"], lw=0.8, ls="--", label="2% promotion criterion")
ax.axvspan(3.5, 5.5, color=COLORS["very_light"], zorder=0)
ax.text(4.5, ax.get_ylim()[1] * 0.90, "Diagnostic only", ha="center", va="top", fontsize=6.2, color=COLORS["orange"])
ax.set_xticks(x, [short_sensor(sensor) for sensor in sensors], rotation=35, ha="right")
ax.set(ylabel="High-quality warning rate (%)")
ax.legend(loc="upper left", ncol=1)
ax.set_title("Temporal transfer supports positions 1–2, not position 3")
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
