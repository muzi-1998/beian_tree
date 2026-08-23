from __future__ import annotations

from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import Normalize


MECHANISM_LABELS = {
    "impulse_spike": "Impulse spike",
    "short_burst": "Short burst",
    "temporary_shift": "Temporary shift",
    "persistent_step": "Persistent step",
}
COLORS = {
    "challenger": "#0072B2",
    "baseline": "#D55E00",
    "reference": "#4D4D4D",
    "gate": "#009E73",
}


def _style() -> None:
    mpl.rcParams.update(
        {
            "font.family": "Arial",
            "font.size": 7,
            "axes.labelsize": 7,
            "axes.titlesize": 7,
            "xtick.labelsize": 6.5,
            "ytick.labelsize": 6.5,
            "legend.fontsize": 6.2,
            "axes.linewidth": 0.7,
            "xtick.major.width": 0.7,
            "ytick.major.width": 0.7,
            "xtick.major.size": 3,
            "ytick.major.size": 3,
            "xtick.direction": "out",
            "ytick.direction": "out",
            "svg.fonttype": "none",
            "pdf.fonttype": 42,
            "savefig.transparent": False,
        }
    )


def _panel_label(axis: plt.Axes, label: str) -> None:
    axis.text(
        -0.14,
        1.04,
        label,
        transform=axis.transAxes,
        fontsize=8,
        fontweight="bold",
        ha="left",
        va="bottom",
        clip_on=False,
    )


def _save(fig: plt.Figure, stem: Path) -> None:
    stem.parent.mkdir(parents=True, exist_ok=True)
    svg_path = stem.with_suffix(".svg")
    fig.savefig(svg_path, bbox_inches="tight")
    svg_text = svg_path.read_text(encoding="utf-8")
    svg_path.write_text(
        "\n".join(line.rstrip() for line in svg_text.splitlines()) + "\n",
        encoding="utf-8",
    )
    fig.savefig(stem.with_suffix(".pdf"), bbox_inches="tight")
    fig.savefig(stem.with_suffix(".tiff"), dpi=600, bbox_inches="tight")
    fig.savefig(stem.with_suffix(".png"), dpi=300, bbox_inches="tight")
    plt.close(fig)


def figure_fixed_far(validation: pd.DataFrame, thresholds: dict, output_dir: Path) -> None:
    _style()
    selected = validation.loc[
        validation["phase"].eq("internal_validation")
        & validation["resolution_mode"].eq("original_resolution")
        & validation["primary_region"].eq(True)  # noqa: E712
    ].copy()
    order = list(MECHANISM_LABELS)
    selected = selected.set_index("mechanism").reindex(order)
    fig, axes = plt.subplots(1, 3, figsize=(7.2047, 2.4409), gridspec_kw={"width_ratios": [1.35, 1.0, 0.9]})
    x = np.arange(len(order))
    for offset, metric, low, high, color, label in [
        (-0.12, "baseline_fixed_far_recall", "baseline_ci95_low", "baseline_ci95_high", COLORS["baseline"], "Released score, same FAR ceiling"),
        (0.12, "challenger_recall", "challenger_ci95_low", "challenger_ci95_high", COLORS["challenger"], "Multiscale GLR"),
    ]:
        values = selected[metric].to_numpy(dtype=float)
        yerr = np.vstack([values - selected[low].to_numpy(dtype=float), selected[high].to_numpy(dtype=float) - values])
        axes[0].errorbar(x + offset, values, yerr=yerr, fmt="o", ms=4, capsize=2, lw=0.8, color=color, label=label)
    axes[0].axhline(0.8, color=COLORS["reference"], lw=0.8, ls="--", label="Prespecified 0.80")
    axes[0].set_ylabel("Timely event recall")
    axes[0].set_xticks(x, [MECHANISM_LABELS[item] for item in order], rotation=28, ha="right")
    axes[0].set_ylim(-0.03, 1.03)
    axes[0].legend(frameon=False, loc="center right", bbox_to_anchor=(0.99, 0.53))
    _panel_label(axes[0], "(a)")

    delta = selected["recall_delta"].to_numpy(dtype=float)
    delta_err = np.vstack([delta - selected["delta_ci95_low"].to_numpy(dtype=float), selected["delta_ci95_high"].to_numpy(dtype=float) - delta])
    axes[1].errorbar(x, delta, yerr=delta_err, fmt="o", ms=4, capsize=2, lw=0.8, color=COLORS["challenger"])
    axes[1].axhline(0, color=COLORS["reference"], lw=0.7)
    axes[1].axhline(0.15, color=COLORS["gate"], lw=0.8, ls="--")
    axes[1].set_ylabel("Paired recall difference")
    axes[1].set_xticks(x, [MECHANISM_LABELS[item] for item in order], rotation=28, ha="right")
    axes[1].set_ylim(min(-0.35, np.nanmin(delta_err[0] * -1 + delta) - 0.05), max(0.35, np.nanmax(delta_err[1] + delta) + 0.05))
    _panel_label(axes[1], "(b)")

    entries = [
        ("minute_glr:baseline_fixed_far", "Released minute", "#CC79A7"),
        ("hourly_glr:baseline_fixed_far", "Released hourly", "#56B4E9"),
        ("minute_glr:challenger", "GLR minute", "#CC79A7"),
        ("hourly_glr:challenger", "GLR hourly", "#56B4E9"),
    ]
    y = np.arange(len(entries))[::-1]
    values = [float(thresholds[key]["far"]) for key, _, _ in entries]
    axes[2].hlines(y, 0, values, color="#B0B0B0", lw=0.7)
    axes[2].scatter(values, y, c=[color for _, _, color in entries], s=22, zorder=3)
    axes[2].axvline(0.05, color=COLORS["gate"], lw=0.8, ls="--")
    axes[2].text(0.05, y.max() + 0.28, "Track budget", color=COLORS["gate"], fontsize=6, ha="right", va="bottom")
    axes[2].set_xlabel("Events per sensor-day")
    axes[2].set_yticks(y, [label for _, label, _ in entries])
    axes[2].set_xlim(0, 0.055)
    axes[2].set_ylim(-0.55, y.max() + 0.55)
    _panel_label(axes[2], "(c)")
    for axis in axes:
        axis.spines[["top", "right"]].set_visible(False)
    fig.subplots_adjust(left=0.07, right=0.99, bottom=0.25, top=0.94, wspace=0.48)
    _save(fig, output_dir / "FigC1_fixed_far_performance")


def figure_applicability(surface: pd.DataFrame, output_dir: Path) -> None:
    _style()
    mechanisms = list(MECHANISM_LABELS)
    analytes = ["DO", "ORP"]
    fig, axes = plt.subplots(4, 2, figsize=(5.9055, 7.0866), constrained_layout=False)
    image = None
    for row_index, mechanism in enumerate(mechanisms):
        for column_index, analyte in enumerate(analytes):
            axis = axes[row_index, column_index]
            frame = surface.loc[surface["mechanism"].eq(mechanism) & surface["analyte"].eq(analyte)].copy()
            amp_values = sorted(frame["amplitude_mid"].unique())
            duration_values = sorted(frame["duration_mid"].unique())
            matrix = np.full((len(duration_values), len(amp_values)), np.nan)
            counts = np.zeros_like(matrix)
            for _, cell in frame.iterrows():
                y = duration_values.index(cell["duration_mid"])
                x = amp_values.index(cell["amplitude_mid"])
                matrix[y, x] = cell["recall"]
                counts[y, x] = cell["n_clusters"]
            image = axis.imshow(matrix, origin="lower", aspect="auto", cmap="cividis", norm=Normalize(0, 1))
            for y in range(matrix.shape[0]):
                for x in range(matrix.shape[1]):
                    if np.isfinite(matrix[y, x]):
                        color = "white" if matrix[y, x] < 0.55 else "black"
                        axis.text(x, y, f"{matrix[y, x]:.2f}\nn={int(counts[y, x])}", ha="center", va="center", fontsize=5.5, color=color)
                    else:
                        axis.add_patch(mpl.patches.Rectangle((x - 0.5, y - 0.5), 1, 1, facecolor="#D9D9D9", hatch="////", edgecolor="#7A7A7A", linewidth=0.3))
                        axis.text(x, y, f"n={int(counts[y, x])}", ha="center", va="center", fontsize=5.2, color="#4D4D4D")
            axis.set_xticks(range(len(amp_values)), [f"{value:.2g}" for value in amp_values])
            axis.set_yticks(range(len(duration_values)), [f"{value:.2g}" for value in duration_values])
            axis.set_xlabel("Amplitude (local robust sigma)")
            axis.set_ylabel("Duration (min)" if mechanism in {"impulse_spike", "short_burst"} else "Duration (h)")
            axis.set_title(f"{MECHANISM_LABELS[mechanism]} | {analyte}", fontweight="bold", pad=3)
            axis.tick_params(direction="in", top=False, right=False)
            _panel_label(axis, f"({chr(97 + row_index * 2 + column_index)})")
    cbar_axis = fig.add_axes([0.91, 0.23, 0.018, 0.54])
    colorbar = fig.colorbar(image, cax=cbar_axis)
    colorbar.set_label("Challenger recall")
    fig.text(0.06, 0.018, "Hatched cells have fewer than five independent sensor-week clusters and are not estimated.", fontsize=6)
    fig.subplots_adjust(left=0.10, right=0.88, bottom=0.075, top=0.97, hspace=0.62, wspace=0.38)
    _save(fig, output_dir / "FigC2_applicability_surfaces")


def figure_shadow(shadow: pd.DataFrame, output_dir: Path) -> None:
    _style()
    if shadow.empty:
        return
    frame = shadow.copy()
    frame["month"] = pd.to_datetime(frame["onset"]).dt.to_period("M").astype(str)
    counts = frame.groupby(["sensor_id", "track"]).size().rename("events").reset_index()
    order = sorted(counts["sensor_id"].unique())
    fig, axis = plt.subplots(figsize=(4.7244, 2.7559))
    x = np.arange(len(order))
    for track, offset, color, label in [
        ("minute_glr", -0.18, "#56B4E9", "Minute GLR"),
        ("hourly_glr", 0.18, "#E69F00", "Hourly GLR"),
    ]:
        values = counts.loc[counts["track"].eq(track)].set_index("sensor_id")["events"].reindex(order, fill_value=0)
        axis.bar(x + offset, values, width=0.34, color=color, label=label)
    axis.set_ylabel("Unadjudicated shadow events")
    axis.set_xticks(x, order, rotation=55, ha="right")
    axis.legend(frameon=False, loc="upper right")
    axis.spines[["top", "right"]].set_visible(False)
    _panel_label(axis, "(a)")
    fig.subplots_adjust(left=0.11, right=0.98, bottom=0.31, top=0.93)
    _save(fig, output_dir / "FigC3_shadow_event_profile")


def generate_all(output_dir: Path, thresholds: dict) -> None:
    data_dir = output_dir / "data"
    figure_dir = output_dir / "figures"
    validation = pd.read_parquet(data_dir / "D1_challenger_validation.parquet")
    surface = pd.read_parquet(data_dir / "D1_challenger_applicability_surface.parquet")
    shadow = pd.read_parquet(data_dir / "D1_challenger_shadow_events.parquet")
    figure_fixed_far(validation, thresholds, figure_dir)
    figure_applicability(surface, figure_dir)
    figure_shadow(shadow, figure_dir)
