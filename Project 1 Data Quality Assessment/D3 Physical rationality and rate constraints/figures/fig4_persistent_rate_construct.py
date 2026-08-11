"""Figure 4: persistent-rate construct, attribution funnel, and validity evidence."""
# Shared Nature contract: Arial; svg.fonttype='none'; pdf.fonttype=42; .svg .pdf .png .tiff dpi=600.
# Figure contract: duration and attribution, rather than point amplitude alone,
# separate D3 persistent dynamics from D1-like impulses and coherent process changes.

from __future__ import annotations

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from _figure_data import OUT, read, read_validation, sensor_order, short_sensor
from _nature_style import COLORS, panel_label, save_figure, style_axis


rate = read("D3_rate_evidence.xlsx")
dose = read_validation("D3_rate_construct_validation.xlsx", sheet_name="rate_dose_response")
overlap = read_validation("D3_rate_construct_validation.xlsx", sheet_name="D1_D3_overlap_summary")
order = sensor_order(list(rate["sensor_id"].unique()))

profile = rate.groupby("sensor_id").agg(
    point=("rate_hard_point_violation_rate", lambda x: 1000 * x.gt(0).mean()),
    soft_only=("rate_soft_only_violation_rate", lambda x: 1000 * x.gt(0).mean()),
    hard=("rate_hard_violation_rate", lambda x: 1000 * x.gt(0).mean()),
).reindex(order)

fig, axes = plt.subplots(2, 2, figsize=(7.2, 5.55))
fig.subplots_adjust(left=0.11, right=0.98, bottom=0.10, top=0.96, wspace=0.39, hspace=0.45)

ax = axes[0, 0]
y = np.arange(len(order))
ax.hlines(y, profile["soft_only"], profile["point"], color=COLORS["light_gray"], lw=1.4)
ax.scatter(profile["point"], y, s=18, color=COLORS["orange"], label="Point hard excursion")
ax.scatter(profile["soft_only"], y, s=18, color=COLORS["cyan"], label="3-9 min soft-only")
ax.scatter(profile["hard"], y, s=18, marker="s", color=COLORS["blue"], label=">=10 min hard")
ax.set_yticks(y, [short_sensor(sensor) for sensor in order])
ax.set_xlabel("Affected windows per 1,000")
ax.legend(loc="lower right")
ax.set_title("Persistence filters isolated excursions")
style_axis(ax, grid=True)
panel_label(ax, "a")

ax = axes[0, 1]
candidate = (
    rate["rate_hard_point_violation_rate"].gt(0)
    | rate["rate_soft_only_violation_rate"].gt(0)
    | rate["rate_hard_violation_rate"].gt(0)
    | rate["impulse_return_event_count"].gt(0)
    | rate["process_coherence_guarded_points"].gt(0)
)
subset = rate.loc[candidate].copy()
disposition = np.select(
    [
        subset["rate_hard_violation_rate"].gt(0),
        subset["rate_soft_only_violation_rate"].gt(0),
        subset["process_coherence_guarded_points"].gt(0),
        subset["impulse_return_event_count"].gt(0),
    ],
    ["Hard persistent", "Soft-only persistent", "Process guarded", "Impulse excluded"],
    default="Point diagnostic only",
)
counts = pd.Series(disposition).value_counts().reindex(
    ["Impulse excluded", "Process guarded", "Point diagnostic only", "Soft-only persistent", "Hard persistent"]
).fillna(0)
colors = [COLORS["purple"], COLORS["green"], COLORS["orange"], COLORS["cyan"], COLORS["blue"]]
bars = ax.barh(range(len(counts)), counts, color=colors, height=0.62)
ax.set_yticks(range(len(counts)), counts.index)
ax.set_xlabel("Mutually assigned sensor-windows")
for bar, count in zip(bars, counts):
    ax.text(bar.get_width(), bar.get_y() + bar.get_height() / 2, f" {int(count):,}", va="center", fontsize=6.2)
ax.set_title(f"Candidate attribution funnel (n={int(candidate.sum()):,})")
style_axis(ax, grid=True)
panel_label(ax, "b")

ax = axes[1, 0]
pivot = dose.pivot(index="hard_threshold_multiple", columns="duration_min", values="Q_persistent_rate").sort_index()
image = ax.imshow(pivot, cmap="viridis", vmin=1, vmax=5, origin="lower", aspect="auto")
ax.set_xticks(range(len(pivot.columns)), [f"{int(value)}" for value in pivot.columns])
ax.set_yticks(range(len(pivot.index)), [f"{value:.1f}x" for value in pivot.index])
ax.set(xlabel="Same-direction duration (min)", ylabel="Rate magnitude / hard limit")
for row in range(pivot.shape[0]):
    for column in range(pivot.shape[1]):
        value = pivot.iloc[row, column]
        ax.text(column, row, f"{value:.2f}", ha="center", va="center", fontsize=5.8, color="white" if value < 2.6 else COLORS["black"])
ax.axvline(1.5, color="white", lw=0.8, ls="--")
ax.axvline(3.5, color="white", lw=0.8, ls=":")
ax.set_title("Magnitude-duration response surface")
style_axis(ax, full_frame=True)
fig.colorbar(image, ax=ax, fraction=0.046, pad=0.025, label=r"$Q_{persistent-rate}$")
panel_label(ax, "c")

ax = axes[1, 1]
selected = overlap.loc[
    overlap["stratum_level"].isin(["overall", "analyte"])
    & overlap["D1_construct"].isin(["Q_spike", "Q_step"])
].copy()
selected["row"] = selected["D1_construct"].str.replace("Q_", "D1 ", regex=False) + " | " + selected["stratum"].replace("all", "overall")
selected = selected.set_index("row")
row_order = ["D1 spike | overall", "D1 spike | DO", "D1 spike | ORP", "D1 step | overall", "D1 step | DO", "D1 step | ORP"]
columns = ["spearman_loss", "event_jaccard", "P_D3_given_D1", "P_D1_given_D3"]
matrix = selected.reindex(row_order)[columns].to_numpy(dtype=float)
image = ax.imshow(matrix, cmap="RdBu_r", vmin=-0.2, vmax=1.0, aspect="auto")
ax.set_yticks(range(len(row_order)), row_order)
ax.set_xticks(range(4), ["Loss rho", "Jaccard", "P(D3|D1)", "P(D1|D3)"], rotation=25, ha="right")
for row in range(matrix.shape[0]):
    for column in range(matrix.shape[1]):
        value = matrix[row, column]
        ax.text(column, row, f"{value:.2f}", ha="center", va="center", fontsize=5.8, color="white" if value > 0.65 or value < -0.12 else COLORS["black"])
ax.set_title("Empirical D1-D3 concordance remains limited")
style_axis(ax, full_frame=True)
panel_label(ax, "d")

save_figure(fig, OUT, "fig4_persistent_rate_construct")
