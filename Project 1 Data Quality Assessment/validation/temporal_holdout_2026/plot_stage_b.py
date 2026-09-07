"""Nature-style historical/synthetic timing audit, no future-period performance."""
from __future__ import annotations

import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.colors import ListedColormap
from matplotlib.lines import Line2D
from matplotlib.text import Text
import numpy as np
import pandas as pd

from runtime import OUTPUT, write_json

WIDTH_INCHES = 183 / 25.4
BLUE, RED, GRAY = "#287A9F", "#BF593F", "#646A70"
plt.rcParams.update({"font.family": "Arial", "font.size": 7,
                     "axes.titlesize": 7, "axes.labelsize": 7,
                     "xtick.labelsize": 7, "ytick.labelsize": 7,
                     "legend.fontsize": 7, "axes.linewidth": .8,
                     "lines.linewidth": 1.1, "svg.fonttype": "none", "pdf.fonttype": 42,
                     "xtick.direction": "out", "ytick.direction": "out",
                     "axes.spines.top": False, "axes.spines.right": False,
                     "savefig.facecolor": "white"})
QA = []


def panel(ax, letter, title):
    ax.annotate(f"({letter})", (0, 1), xycoords="axes fraction", xytext=(-26, 17),
                textcoords="offset points", fontsize=8, weight="bold", ha="left", va="baseline")
    ax.set_title(title, loc="left", pad=17)
    ax.tick_params(width=.8, length=3, top=False, right=False)


def export(fig, name):
    target = OUTPUT / "figures"
    target.mkdir(parents=True, exist_ok=True)
    fig.canvas.draw()
    renderer = fig.canvas.get_renderer()
    outside = []
    for artist in fig.findobj(Text):
        if artist.get_visible() and artist.get_text():
            bbox = artist.get_window_extent(renderer)
            if bbox.width and bbox.height and (bbox.x0 < -.5 or bbox.y0 < -.5 or
                                              bbox.x1 > fig.bbox.x1+.5 or bbox.y1 > fig.bbox.y1+.5):
                outside.append(artist.get_text())
    if outside:
        raise ValueError(f"Text outside canvas: {name}: {outside}")
    svg_path = target / f"{name}.svg"
    fig.savefig(svg_path)
    svg_lines = svg_path.read_text(encoding="utf-8").splitlines()
    svg_path.write_text("\n".join(line.rstrip() for line in svg_lines) + "\n", encoding="utf-8", newline="\n")
    fig.savefig(target / f"{name}.pdf")
    fig.savefig(target / f"{name}.png", dpi=300)
    fig.savefig(target / f"{name}.tiff", dpi=600, pil_kwargs={"compression": "tiff_lzw"})
    QA.append({"figure": name, "width_mm": fig.get_figwidth()*25.4,
               "height_mm": fig.get_figheight()*25.4, "outside_canvas_text": outside,
               "Arial_font_resolved": font_manager.findfont("Arial", fallback_to_default=False),
               "raster_dpi": 600, "editable_svg_text": True,
               "visual_review": "manual_inspection_record_in_stage_B_manifest", "future_scores_used": False})
    plt.close(fig)


def temporal_scope():
    fig, axes = plt.subplots(2, 1, figsize=(WIDTH_INCHES, 142/25.4), gridspec_kw={"height_ratios": [1., 1.2]})
    fig.subplots_adjust(left=.21, right=.97, bottom=.09, top=.9, hspace=.72)
    ax = axes[0]
    panel(ax, "a", "Frozen historical basis and unopened later period")
    rows = pd.read_csv(OUTPUT / "source_data/validation_timeline.csv")
    for i, row in rows.iterrows():
        x0, x1 = [mdates.date2num(pd.Timestamp(row[k])) for k in ["start", "end_exclusive"]]
        ax.barh(2-i, x1-x0, left=x0, height=.43, color=[BLUE, GRAY, "#E2E5E8"][i],
                edgecolor=[BLUE, GRAY, GRAY][i], linewidth=.8)
    start, end = pd.Timestamp("2025-08-01"), pd.Timestamp("2026-07-31")
    ax.set_xlim(start, end)
    ax.set_ylim(-.6, 2.8)
    ax.set_yticks([2, 1, 0], rows.series)
    ticks = pd.to_datetime(["2025-08-01", "2025-11-01", "2026-02-01", "2026-04-14", "2026-07-31"])
    ax.set_xticks(ticks)
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
    ax.tick_params(axis="x", labelsize=6)
    ax.axvline(pd.Timestamp("2026-04-14"), color=GRAY, lw=.8, ls="--")
    ax.text(mdates.date2num(pd.Timestamp("2026-06-06")), 0, "108 d: scoring sealed", ha="center", va="center")
    ax.text(mdates.date2num(pd.Timestamp("2026-01-27")), 1.40, "Reference endpoint: 2026-01-27 04:30", ha="center", fontsize=6)
    ax.set_xlabel("Calendar date (Asia/Shanghai)")
    ax = axes[1]
    panel(ax, "b", "Source-window closure relative to the output label")
    table = pd.read_csv(OUTPUT / "source_data/information_intervals.csv")
    y = np.arange(len(table))[::-1]
    for yy, row in zip(y, table.itertuples()):
        delay = row.closure_delay_minutes
        ax.plot([0, delay], [yy, yy], color="#B7BBC0", lw=1)
        ax.scatter([delay], [yy], color=BLUE, marker="D", s=22, zorder=3, clip_on=False)
        ax.text(delay+2, yy, f"+{delay:.0f} min", va="center", fontsize=7)
    ax.set_xlim(0, 75)
    ax.set_xticks([0, 10, 30, 60, 75])
    ax.set_ylim(-.55, 4.55)
    ax.set_yticks(y, table.dimension)
    ax.set_xlabel("Minimum closure delay from label (min)")
    ax.text(.97, .48, "D1 short-gap transform: +3 min\nFurther processing latency is additional", transform=ax.transAxes,
            ha="right", va="center", fontsize=6)
    export(fig, "Holdout_H1_scope_information_clock")


def counterexamples():
    fig, axes = plt.subplots(2, 2, figsize=(WIDTH_INCHES, 165/25.4))
    fig.subplots_adjust(left=.145, right=.98, bottom=.085, top=.90, hspace=.72, wspace=.55)
    ax = axes[0, 0]
    panel(ax, "a", "D2: a gap is not known in advance")
    gap = pd.read_csv(OUTPUT / "audit/D2_gap_timing_case.csv", parse_dates=["timestamp"])
    x = (gap.timestamp - pd.Timestamp("2026-02-03")).dt.total_seconds()/60
    matrix = np.array([1-gap.raw_observed, gap.legacy_full_long_gap,
                       gap.legacy_prefix_long_gap, gap.causal_long_gap_asof], dtype=float)
    cmap = ListedColormap(["#DFE3E6", BLUE])
    cmap.set_bad("white")
    ax.imshow(np.ma.masked_invalid(matrix), cmap=cmap, vmin=0, vmax=1, aspect="auto",
              interpolation="nearest", extent=[x.iloc[0], x.iloc[-1]+1, 3.5, -.5])
    for boundary in [.5, 1.5, 2.5]:
        ax.axhline(boundary, color="white", lw=1)
    ax.set_yticks([0, 1, 2, 3], ["Missing raw", "Full-series gap", "Prefix-only gap", "As-of gap"])
    ax.set_xticks([-12, 0, 20, 41])
    ax.set_xlim(-12, 41)
    ax.axvline(0, color=RED, ls="--", lw=1)
    ax.set_xlabel("Minutes from prefix cutoff")
    ax.text(.5, -.27, "Blue: true; light grey: false; white: not observed", transform=ax.transAxes,
            ha="center", fontsize=5.8)
    ax = axes[0, 1]
    panel(ax, "b", "D4: future candidates alter past scores")
    cp = pd.read_csv(OUTPUT / "audit/D4_cp_timing_case.csv")
    ax.plot(cp.hours_from_start, cp.legacy_full_Q_cp, color=GRAY, drawstyle="steps-post", label="Full-series")
    ax.plot(cp.hours_from_start, cp.asof_oracle_Q_cp, color=BLUE, drawstyle="steps-post", label="As-of candidate")
    ax.plot(cp.hours_from_start, cp.legacy_prefix_Q_cp, color=RED, ls="--", drawstyle="steps-post", label="Prefix only")
    ax.axvline(60, color=RED, ls=":", lw=.8)
    ax.set_xlim(24, 119)
    ax.set_xticks([24, 48, 72, 96, 119])
    ax.set_ylim(.7, 5.3)
    ax.set_yticks([1, 2, 3, 4, 5])
    ax.set_ylabel("Change-point score, Q_cp")
    ax.set_xlabel("Synthetic elapsed time (h)")
    ax.legend(loc="upper center", bbox_to_anchor=(.5, -.22), ncol=3, borderaxespad=0,
              fontsize=5.8, frameon=False, handlelength=1.6, columnspacing=.8)
    summary = pd.read_csv(OUTPUT / "audit/D4_historical_CP_timing_summary.csv")
    y = np.arange(len(summary))[::-1]
    pair_names = summary.pair_id.str.replace("PAIR_", "", regex=False)
    ax = axes[1, 0]
    panel(ax, "c", "Old-period change-point score differences")
    rate = 100*summary.changed_Q_cp_hours/summary.n_pair_hours
    ax.hlines(y, 0, rate, color="#C5C9CD", lw=1)
    ax.scatter(rate, y, s=20, marker="o", color=BLUE)
    ax.set_yticks(y, pair_names)
    ax.set_ylim(-.65, 6.65)
    ax.set_xlim(0, 40)
    ax.set_xticks([0, 10, 20, 30, 40])
    for yy, x, count in zip(y, rate, summary.changed_Q_cp_hours):
        ax.text(x+1, yy, f"{count:,}", va="center", fontsize=6)
    ax.set_xlabel("Changed Q_cp (% of all pair-hours)")
    ax = axes[1, 1]
    panel(ax, "d", "Low-tail flips with other evidence fixed")
    rate = 100*summary.low_tail_flip_hours/summary.common_evaluable_hours
    ax.hlines(y, 0, rate, color="#C5C9CD", lw=1)
    ax.scatter(rate, y, s=22, marker="s", color=RED)
    for yy, x, count in zip(y, rate, summary.low_tail_flip_hours):
        ax.text(x+.3, yy, f"{count:,}", va="center", fontsize=6)
    ax.set_yticks(y, pair_names)
    ax.set_ylim(-.65, 6.65)
    ax.set_xlim(0, 13)
    ax.set_xticks([0, 3, 6, 9, 13])
    ax.set_xlabel("Crossing D4 = 3 (% common support)")
    export(fig, "Holdout_H2_causality_counterexamples")


if __name__ == "__main__":
    temporal_scope()
    counterexamples()
    write_json(OUTPUT / "figure_qa.json", {"backend": "Python", "figures": QA,
                                           "scientific_validation_passed": False})
