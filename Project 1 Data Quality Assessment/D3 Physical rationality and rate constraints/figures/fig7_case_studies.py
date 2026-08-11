"""Figure 7: frozen mechanism-based D3 case studies."""
# Shared Nature contract: Arial; svg.fonttype='none'; pdf.fonttype=42; .svg .pdf .png .tiff dpi=600.
# Figure contract: predefined illustrative cases expose the zero-equivalence,
# persistent-rate, and process-coherence mechanisms without outcome-driven reselection.

from __future__ import annotations

import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from _figure_data import OUT, ROOT, VALIDATION, load_yaml, read, short_sensor
from _nature_style import COLORS, annotation_box, panel_label, save_figure, style_axis

sys.path.insert(0, str(ROOT))
from src.common.rate_utils import dx_dt_robust
from src.data.input_loader import load_aligned_data


raw = load_aligned_data(load_yaml("d3_paths.yaml"), ROOT)
cases = load_yaml("d3_figure_cases.yaml")["cases"]
rate_cfg = load_yaml("d3_rate_limits.yaml")
rate_evidence = read("D3_rate_evidence.xlsx")
scores = read("D3_window_scores.xlsx")
views = pd.read_parquet(VALIDATION / "D3_DO4_zero_equivalence_views.parquet")
views["timestamp"] = pd.to_datetime(views["timestamp"])

fig, axes = plt.subplots(3, 2, figsize=(7.2, 6.75))
fig.subplots_adjust(left=0.10, right=0.98, bottom=0.07, top=0.97, wspace=0.33, hspace=0.48)

# a-b, post-anoxic zero-equivalence.
cfg = cases["do4_zero_equivalence"]
sensor = cfg["sensor"]
end = pd.Timestamp(cfg["end_ts"]); start = end - pd.Timedelta(hours=cfg["window_hours"])
segment = views.loc[views["sensor_id"].eq(sensor) & views["timestamp"].between(start, end)].set_index("timestamp")
ax = axes[0, 0]
ax.plot(segment.index, segment["DO_raw"], color=COLORS["blue"], lw=0.9, label="Raw DO")
ax.plot(segment.index, segment["DO_physicalized"], color=COLORS["gray"], lw=0.8, ls="--", label="Process-only physicalized view")
ax.axhspan(-0.05, 0.0, color=COLORS["cyan"], alpha=0.16, label="Zero-equivalent")
ax.axhspan(-0.20, -0.05, color=COLORS["amber"], alpha=0.12, label="Offset warning")
ax.axhline(0.0, color=COLORS["black"], lw=0.75)
ax.set(ylabel=f"{short_sensor(sensor)} (mg L$^{{-1}}$)")
ax.legend(loc="lower right", ncol=2)
ax.set_title("Post-anoxic near-zero measurement")
style_axis(ax, grid=True)
panel_label(ax, "a")

ax = axes[0, 1]
flags = ["DO_zero_equivalent_flag", "DO_zero_offset_warning_flag", "DO_severe_negative_flag"]
labels = ["Zero-equivalent", "Offset warning", "Severe negative"]
colors = [COLORS["cyan"], COLORS["amber"], COLORS["red"]]
for index, (column, label, color) in enumerate(zip(flags, labels, colors)):
    ax.fill_between(segment.index, index, index + 0.72, where=segment[column].to_numpy(dtype=bool), color=color, alpha=0.85, step="mid")
ax.set_yticks(np.arange(3) + 0.36, labels)
ax.set_ylim(-0.1, 3.0)
ax.text(0.98, 0.94, "Negative raw values retained\nNo soft-bound penalty inside [-0.05, 0)", transform=ax.transAxes, ha="right", va="top", bbox=annotation_box(0.82), fontsize=6.2)
ax.set_title("Measurement state remains explicit")
style_axis(ax)
panel_label(ax, "b")

# c-d, persistent soft ramp.
cfg = cases["persistent_soft_ramp"]
sensor = cfg["sensor"]
end = pd.Timestamp(cfg["end_ts"]); start = end - pd.Timedelta(hours=cfg["window_hours"])
series = raw.loc[start:end, sensor]
rate_values, _ = dx_dt_robust(series, **rate_cfg["rate_estimator"])
soft_limit = float(rate_cfg["rate_limits"]["ORP"]["rate_soft"])
hard_limit = float(rate_cfg["rate_limits"]["ORP"]["rate_hard"])
ax = axes[1, 0]
ax.plot(series.index, series, color=COLORS["orange"], lw=0.9)
ax.set_ylabel(f"{short_sensor(sensor)} (mV)")
ax.set_title("Persistent ORP ramp")
style_axis(ax, grid=True)
panel_label(ax, "c")

ax = axes[1, 1]
ax.plot(series.index, rate_values, color=COLORS["blue"], lw=0.9, label="Robust rate")
for limit, color, label in ((soft_limit, COLORS["cyan"], "Soft limit"), (hard_limit, COLORS["red"], "Hard limit")):
    ax.axhline(limit, color=color, lw=0.8, ls="--", label=label)
    ax.axhline(-limit, color=color, lw=0.8, ls="--")
case_rate = rate_evidence.loc[rate_evidence["sensor_id"].eq(sensor) & rate_evidence["ts"].eq(end)].iloc[0]
case_score = scores.loc[scores["sensor_id"].eq(sensor) & scores["ts"].eq(end)].iloc[0]
ax.text(0.98, 0.08, f"Longest hard run: {int(case_rate.rate_hard_consec_max_min)} min\nQ persistent-rate: {case_score.Q_persistent_rate:.2f}", transform=ax.transAxes, ha="right", va="bottom", bbox=annotation_box(0.82), fontsize=6.2)
ax.set_ylabel("Robust rate (mV min$^{-1}$)")
ax.legend(loc="upper left")
ax.set_title("Duration-tiered rate evidence")
style_axis(ax, grid=True)
panel_label(ax, "d")

# e-f, coherent process change.
cfg = cases["process_coherent_change"]
sensors = cfg["sensors"]
end = pd.Timestamp(cfg["end_ts"]); start = end - pd.Timedelta(hours=cfg["window_hours"])
palette = [COLORS["blue"], COLORS["green"], COLORS["orange"]]
ax = axes[2, 0]
for sensor, color in zip(sensors, palette):
    series = raw.loc[start:end, sensor]
    scale = float(series.std()) or 1.0
    ax.plot(series.index, (series - series.mean()) / scale, color=color, lw=0.9, label=short_sensor(sensor))
ax.set_ylabel("Within-case standardized DO")
ax.legend(loc="upper left", ncol=3)
ax.set_title("Synchronous multi-sensor process change")
style_axis(ax, grid=True)
panel_label(ax, "e")

ax = axes[2, 1]
hard_do = float(rate_cfg["rate_limits"]["DO"]["rate_hard"])
for sensor, color in zip(sensors, palette):
    series = raw.loc[start:end, sensor]
    rate_values, _ = dx_dt_robust(series, **rate_cfg["rate_estimator"])
    ax.plot(series.index, rate_values / hard_do, color=color, lw=0.9, label=short_sensor(sensor))
ax.axhline(1.0, color=COLORS["red"], lw=0.8, ls="--")
ax.axhline(-1.0, color=COLORS["red"], lw=0.8, ls="--")
ax.text(0.98, 0.08, "Coherent change retained as process context\nAttribution guard, not Veto", transform=ax.transAxes, ha="right", va="bottom", bbox=annotation_box(0.82), fontsize=6.2)
ax.set_ylabel("Robust rate / hard limit")
ax.set_title("Process-coherence guard")
style_axis(ax, grid=True)
panel_label(ax, "f")

for ax in axes.flat:
    ax.tick_params(axis="x", rotation=18)

save_figure(fig, OUT, "fig7_case_studies")
