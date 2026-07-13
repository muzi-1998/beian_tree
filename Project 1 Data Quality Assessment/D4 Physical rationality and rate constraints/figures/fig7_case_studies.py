"""Figure 7: representative D4 evidence cases."""

from __future__ import annotations

import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from _figure_data import OUT, ROOT, load_yaml, read, sensor_type, short_sensor
from _nature_style import COLORS, annotation_box, panel_label, save_figure, style_axis

sys.path.insert(0, str(ROOT))
from src.data.input_loader import load_aligned_data


scores = read("D4_window_scores.xlsx")
value = read("D4_value_evidence.xlsx")
paths_cfg = load_yaml("d4_paths.yaml")
raw = load_aligned_data(paths_cfg, ROOT)

evaluated = scores[scores.evidence_status == "sufficient"].copy()
worst = evaluated.loc[evaluated.D4_total.idxmin()]
rate_pool = evaluated[(evaluated.Q_value_hard > 4.8) & (evaluated.sensor_id != worst.sensor_id)]
rate_case = rate_pool.loc[rate_pool.Q_rate.idxmin()] if len(rate_pool) else evaluated.loc[evaluated.Q_rate.idxmin()]
healthy_pool = evaluated[(evaluated.D4_total > 4.95) & ~evaluated.sensor_id.isin([worst.sensor_id, rate_case.sensor_id])]
healthy = healthy_pool.iloc[len(healthy_pool) // 2] if len(healthy_pool) else evaluated.loc[evaluated.D4_total.idxmax()]
worst_name = "Instrument-range case" if "instrument_range" in str(worst.veto_reason) else "Hard-bound case"
cases = [(worst_name, worst), ("Rate-limited case", rate_case), ("Reference case", healthy)]

fig, axes = plt.subplots(3, 2, figsize=(7.2, 6.7), gridspec_kw={"width_ratios": [2.15, 1]})
fig.subplots_adjust(left=0.10, right=0.98, bottom=0.07, top=0.97, wspace=0.30, hspace=0.48)
labels = ["(a)", "(b)", "(c)", "(d)", "(e)", "(f)"]

for row, (case_name, case) in enumerate(cases):
    sensor = case.sensor_id
    end = pd.Timestamp(case.ts)
    start = end - pd.Timedelta(hours=6)
    segment = raw.loc[start:end, sensor]
    evidence = value[(value.sensor_id == sensor) & (value.ts == end)].iloc[0]
    color = COLORS["blue"] if sensor_type(sensor) == "DO" else COLORS["orange"]

    ax = axes[row, 0]
    ax.plot(segment.index, segment, color=color, linewidth=0.9)
    ax.axhspan(evidence.soft_low, evidence.soft_high, color=COLORS["green"], alpha=0.10, label="Soft range")
    ax.axhline(evidence.hard_low, color=COLORS["red"], linestyle="--", linewidth=0.8)
    ax.axhline(evidence.hard_high, color=COLORS["red"], linestyle="--", linewidth=0.8, label="Hard limits")
    finite = segment.dropna()
    if sensor_type(sensor) == "DO":
        lower = min(float(finite.min()) if len(finite) else evidence.soft_low, evidence.soft_low) - 0.25
        upper = max(float(finite.max()) if len(finite) else evidence.soft_high, evidence.soft_high) + 0.35
        ax.set_ylim(lower, upper)
    unit = "mg L$^{-1}$" if sensor_type(sensor) == "DO" else "mV"
    ax.set(xlabel="Time", ylabel=f"{short_sensor(sensor)} ({unit})")
    ax.set_title(case_name)
    ax.legend(loc="upper left", ncol=2)
    ax.tick_params(axis="x", rotation=20)
    style_axis(ax, minor=True)
    panel_label(ax, labels[row * 2])

    ax = axes[row, 1]
    sublabels = ["Hard", "Soft", "Rate"]
    subvalues = [case.Q_value_hard, case.Q_value_soft, case.Q_rate]
    bars = ax.barh(sublabels, subvalues, color=[COLORS["red"], COLORS["amber"], COLORS["blue"]], height=0.56)
    for bar, score in zip(bars, subvalues):
        ax.text(min(score + 0.08, 4.78), bar.get_y() + bar.get_height() / 2, f"{score:.2f}", va="center",
                ha="left" if score < 4.65 else "right")
    ax.axvline(case.D4_total, color=COLORS["black"], linestyle="--", linewidth=0.9)
    reason = str(case.veto_reason) if pd.notna(case.veto_reason) else str(case.dominant_physical_issue)
    reason = reason.replace("_", " ").replace(";", "\n")
    ax.text(0.98, 0.06, f"D4 = {case.D4_total:.2f}\n{reason}",
            transform=ax.transAxes, ha="right", va="bottom", bbox=annotation_box(0.82))
    ax.set(xlabel="Quality score", xlim=(1, 5.05))
    ax.set_title("Evidence hierarchy")
    style_axis(ax, grid=True)
    panel_label(ax, labels[row * 2 + 1], x=-0.18)

save_figure(fig, OUT, "fig7_case_studies")
