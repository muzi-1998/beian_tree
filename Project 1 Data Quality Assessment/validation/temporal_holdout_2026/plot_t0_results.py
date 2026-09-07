"""Frozen later-period coverage and natural burden, not fault detection accuracy.

Quantitative grids, 183 mm, Arial, editable SVG/PDF, 600 dpi TIFF.
All 14 channels and four calendar-month segments are retained. No interpolation
across unavailable Full estimates; summary cells use their explicit denominators.
"""
from __future__ import annotations

import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
import numpy as np
import pandas as pd

from runtime import OUTPUT, START, END, write_json

SOURCE = OUTPUT / "source_data/T0"
FIGURES = OUTPUT / "figures"
plt.rcParams.update({"font.family": "sans-serif", "font.sans-serif": ["Arial"], "font.size": 7,
    "axes.titlesize": 8, "axes.labelsize": 7, "xtick.labelsize": 7, "ytick.labelsize": 7,
    "axes.linewidth": .8, "lines.linewidth": 1, "axes.spines.top": False, "axes.spines.right": False,
    "xtick.direction": "out", "ytick.direction": "out", "svg.fonttype": "none", "pdf.fonttype": 42,
    "legend.frameon": False, "legend.fontsize": 7, "savefig.facecolor": "white"})
COLORS = dict(report_available="#267F85", L1_limited="#99AEC8", OOD="#CB8A83",
    current_observation_missing="#555C66", context_incomplete="#C2BDCA", other_not_evaluable="#E2E4E7")
LABELS = dict(report_available="Report available", L1_limited="L1 support", OOD="OOD",
    current_observation_missing="Missing observation", context_incomplete="Incomplete context",
    other_not_evaluable="Other unavailable")


def panel(ax, letter, title):
    ax.set_title(title, loc="left", pad=9)
    ax.annotate(f"({letter})", (0, 1), xycoords="axes fraction", xytext=(-19, 9),
                textcoords="offset points", fontsize=8, fontweight="bold", va="bottom")
    ax.tick_params(width=.8, length=3)


def save(fig, name):
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    outside = []
    for text in fig.findobj(matplotlib.text.Text):
        if text.get_visible() and text.get_text():
            box = text.get_window_extent(renderer)
            if box.width and box.height and (box.x0 < -1 or box.y0 < -1 or box.x1 > fig.bbox.x1+1 or box.y1 > fig.bbox.y1+1):
                outside.append(text.get_text())
    if outside:
        raise RuntimeError(f"Text outside figure: {outside}")
    fig.savefig(FIGURES / f"{name}.svg")
    fig.savefig(FIGURES / f"{name}.pdf")
    fig.savefig(FIGURES / f"{name}.png", dpi=300)
    fig.savefig(FIGURES / f"{name}.tiff", dpi=600, pil_kwargs={"compression": "tiff_lzw"})
    plt.close(fig)
    return dict(name=name, width_mm=183, font="Arial", editable_text=True, tiff_dpi=600,
        outside_canvas_text=outside, interpretation="natural outcomes; not field truth", visual_review="pending")


def coverage():
    frame = pd.read_csv(SOURCE / "DQR_monthly_coverage.csv")
    frame["D5_percent"] = 100*frame.D5_hours/frame.nominal_hours
    sensors = sorted(frame.sensor_id.unique(), key=lambda s: (s.startswith("ORP"), s))
    months = sorted(frame.month.unique())
    matrix = frame.pivot(index="sensor_id", columns="month", values="D5_percent").reindex(index=sensors, columns=months)
    fig = plt.figure(figsize=(183/25.4, 169/25.4))
    grid = fig.add_gridspec(2, 2, left=.14, right=.90, bottom=.18, top=.93, wspace=.43, hspace=.7,
                          height_ratios=[1.4, 1])
    ax = fig.add_subplot(grid[0, :])
    cmap = LinearSegmentedColormap.from_list("report_coverage", ["#F4F5F6", "#AED1D3", "#267F85"])
    image = ax.imshow(matrix, cmap=cmap, vmin=0, vmax=100, aspect="auto", interpolation="nearest")
    ax.set_xticks(range(4), ["2026-04\n14-30", "2026-05\n01-31", "2026-06\n01-30", "2026-07\n01-30"])
    ax.set_yticks(range(14), sensors)
    ax.tick_params(length=0)
    for y in range(14):
        for x in range(4):
            value = matrix.iloc[y, x]
            ax.text(x, y, "0" if value == 0 else f"{value:.1f}", ha="center", va="center", fontsize=7,
                    color="white" if value > 65 else "#222222")
    ax.axhline(3.5, color="white", lw=1)
    ax.axhline(7.5, color="white", lw=2)
    ax.axhline(10.5, color="white", lw=1)
    panel(ax, "a", "D5 report-eligible coverage by channel (%)")
    colorbar = fig.colorbar(image, ax=ax, fraction=.025, pad=.015, ticks=[0, 25, 50, 75, 100])
    colorbar.set_label("Nominal sensor-hours (%)")
    reasons = pd.read_csv(SOURCE / "D5_coverage_reasons.csv")
    grouped = reasons.groupby(["month", "report_availability_reason"]).hours.sum().unstack(fill_value=0).reindex(months)
    grouped = grouped.div(grouped.sum(axis=1), axis=0)*100
    ax = fig.add_subplot(grid[1, 0])
    bottom = np.zeros(4)
    for name, color in COLORS.items():
        values = grouped.get(name, pd.Series(0., index=months)).to_numpy()
        ax.bar(range(4), values, bottom=bottom, color=color, width=.62, edgecolor="white", linewidth=.3)
        bottom += values
    ax.set_xticks(range(4), [m[-2:] for m in months])
    ax.set_xlabel("Month in 2026")
    ax.set_ylim(0, 100)
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.set_ylabel("Nominal sensor-hours (%)")
    panel(ax, "b", "Why D5 is unavailable")
    ax = fig.add_subplot(grid[1, 1])
    grouped = frame.groupby("month")[["nominal_hours", "core_hours", "full_hours"]].sum().reindex(months)
    fractions = [grouped.full_hours/grouped.nominal_hours,
                 (grouped.core_hours-grouped.full_hours)/grouped.nominal_hours,
                 (grouped.nominal_hours-grouped.core_hours)/grouped.nominal_hours]
    bottom = np.zeros(4)
    for values, color, label in zip(fractions, ["#267F85", "#99AEC8", "#D8DBDF"], ["Full", "Basic", "Core unavailable"]):
        ax.bar(range(4), values*100, bottom=bottom, width=.62, color=color, label=label, edgecolor="white", linewidth=.3)
        bottom += values.to_numpy()*100
    ax.set_xticks(range(4), [m[-2:] for m in months])
    ax.set_xlabel("Month in 2026")
    ax.set_ylim(0, 100)
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.set_ylabel("Nominal sensor-hours (%)")
    ax.legend(loc="upper center", bbox_to_anchor=(.5, -.30), ncol=1, borderaxespad=0, labelspacing=.25)
    panel(ax, "c", "DQR evidence composition")
    fig.legend(handles=[Patch(facecolor=color, label=LABELS[name]) for name, color in COLORS.items()],
               loc="lower left", bbox_to_anchor=(.08, .018), ncol=3, columnspacing=1.5, handlelength=1.2)
    return save(fig, "Holdout_H3_frozen_coverage_boundary")


def outcomes():
    daily = pd.read_csv(SOURCE / "DQR_daily_quality_coverage.csv", parse_dates=["day"])
    burden = pd.read_csv(SOURCE / "channel_burden.csv")
    fig, axes = plt.subplots(2, 2, figsize=(183/25.4, 175/25.4), gridspec_kw={"height_ratios": [1, 1.15]})
    fig.subplots_adjust(left=.14, right=.97, bottom=.105, top=.90, wspace=.5, hspace=.64)
    fields = ["core_plant_hour_mean", "available_plant_hour_mean", "full_plant_hour_mean"]
    colors = ["#303D4D", "#267F85", "#B85F58"]
    styles = ["-", "--", ":"]
    for ax, level, letter in zip(axes[0], ["node", "pair"], ["a", "b"]):
        data = daily.loc[daily.level.eq(level)]
        for field, color, style in zip(fields, colors, styles):
            ax.plot(data.day, data[field], color=color, ls=style, lw=1.05,
                    marker="." if field == fields[-1] else None, ms=2)
        ax.set_ylim(1, 5)
        ax.set_yticks([1, 2, 3, 4, 5])
        ax.set_xlim(START, END-pd.Timedelta(days=1))
        ax.xaxis.set_major_locator(mdates.MonthLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
        ax.set_ylabel("Quality score (1-5)")
        panel(ax, letter, f"{level.title()}: fixed and varying evidence")
    fig.legend(handles=[Line2D([], [], color=c, ls=s, label=l) for c, s, l in zip(colors, styles,
        ["Fixed core", "Availability-aware", "Full evidence only"])],
        loc="upper center", bbox_to_anchor=(.53, .985), ncol=3)
    ax = axes[1, 0]
    data = burden.loc[burden.dimension.eq("D2")].sort_values("object_id")
    y = np.arange(len(data))
    low = data.low_hours_per_1000_evaluated.to_numpy()
    veto = (1000*data.veto_hours/data.evaluated_hours).to_numpy()
    ax.hlines(y, np.minimum(low, veto), np.maximum(low, veto), color="#BEC4CA", lw=1)
    ax.scatter(low, y-.08, color="#267F85", s=14, label="D2 < 3")
    ax.scatter(veto, y+.08, color="#B85F58", marker="s", s=11, label="Veto")
    ax.set_yticks(y, data.object_id)
    ax.invert_yaxis()
    ax.set_ylim(len(y)-.5, -.5)
    limit = max(10, np.ceil(max(low.max(), veto.max())/10)*10)
    ax.set_xlim(0, limit)
    ax.set_xticks(np.linspace(0, limit, 5))
    ax.set_xlabel("Hours per 1,000 evaluated\nsensor-hours")
    ax.legend(loc="upper left", bbox_to_anchor=(0, -.22), ncol=2)
    panel(ax, "c", "Hard-availability burden")
    ax = axes[1, 1]
    data = burden.loc[burden.dimension.eq("D4")].sort_values("object_id")
    y = np.arange(len(data))
    ax.scatter(data.low_hours_per_1000_evaluated, y, color="#657EA3", s=23)
    pair_labels = []
    for s in data.object_id:
        kind = "ORP" if "ORP" in s else "DO"
        pair_labels.append(f"{kind}_1_{s[-1]} / {kind}_2_{s[-1]}")
    ax.set_yticks(y, pair_labels)
    ax.set_ylim(len(y)-.5, -.5)
    ax.set_xlim(0, 1000)
    ax.set_xticks([0, 250, 500, 750, 1000])
    ax.set_xlabel("D4 < 3 hours per 1,000 evaluated\npair-hours")
    panel(ax, "d", "Relational low-tail burden")
    return save(fig, "Holdout_H4_time_aligned_quality_burden")


def main():
    FIGURES.mkdir(parents=True, exist_ok=True)
    write_json(OUTPUT / "T0_results/T0_figure_qa.json", {"figures": [coverage(), outcomes()],
        "data_scope": "all nominal later-period channels; finite scores use evaluated denominators",
        "intervals": "descriptive values, no inferential intervals claimed", "backend": "Python matplotlib"})


if __name__ == "__main__":
    main()
