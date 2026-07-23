"""Shared submission-grade plotting style for D4 figures."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import AutoMinorLocator


plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.sans-serif"] = ["Arial", "DejaVu Sans", "Liberation Sans"]
plt.rcParams["svg.fonttype"] = "none"
plt.rcParams["pdf.fonttype"] = 42
plt.rcParams.update(
    {
        "font.size": 7.0,
        "axes.labelsize": 7.5,
        "axes.titlesize": 8.0,
        "axes.titleweight": "bold",
        "axes.titlepad": 6.0,
        "axes.linewidth": 0.8,
        "lines.linewidth": 1.0,
        "legend.fontsize": 6.5,
        "legend.frameon": False,
        "xtick.labelsize": 6.5,
        "ytick.labelsize": 6.5,
        "xtick.major.width": 0.8,
        "ytick.major.width": 0.8,
        "xtick.minor.width": 0.6,
        "ytick.minor.width": 0.6,
        "xtick.major.size": 3.0,
        "ytick.major.size": 3.0,
        "xtick.minor.size": 1.8,
        "ytick.minor.size": 1.8,
        "figure.dpi": 150,
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.03,
        "svg.fonttype": "none",
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "axes.unicode_minus": False,
        "figure.constrained_layout.use": False,
    }
)

PANEL_X = -0.10
PANEL_Y = 1.02
PANEL_FONTSIZE = 9.0


COLORS = {
    "navy": "#2F4858",
    "blue": "#3B7EA1",
    "cyan": "#68A9B8",
    "green": "#4C956C",
    "amber": "#D59B3D",
    "orange": "#C96A3D",
    "red": "#B64B4B",
    "purple": "#7564A5",
    "pink": "#B77A8A",
    "gray": "#7B858C",
    "light_gray": "#D7DADD",
    "very_light": "#F2F3F4",
    "black": "#222222",
}

ISSUE_COLORS = {
    "none": COLORS["light_gray"],
    "hard_bound": COLORS["red"],
    "soft_bound": COLORS["amber"],
    "rate": COLORS["blue"],
    "not_evaluated": COLORS["gray"],
}


def panel_label(ax, label: str, x: float = PANEL_X, y: float = PANEL_Y) -> None:
    normalized = label.strip().strip("()").lower()
    ax.text(
        x,
        y,
        f"({normalized})",
        transform=ax.transAxes,
        fontsize=PANEL_FONTSIZE,
        fontweight="bold",
        ha="right",
        va="bottom",
        clip_on=False,
        bbox={
            "facecolor": "white",
            "edgecolor": "none",
            "alpha": 0.88,
            "pad": 0.12,
        },
    )


def style_axis(ax, *, full_frame: bool = False, minor: bool = False, grid: bool = False) -> None:
    for spine in ax.spines.values():
        spine.set_linewidth(0.8)
    ax.spines["top"].set_visible(full_frame)
    ax.spines["right"].set_visible(full_frame)
    direction = "in" if full_frame else "out"
    ax.tick_params(
        axis="both",
        which="both",
        direction=direction,
        top=full_frame,
        right=full_frame,
    )
    if minor:
        ax.xaxis.set_minor_locator(AutoMinorLocator(2))
        ax.yaxis.set_minor_locator(AutoMinorLocator(2))
    if grid:
        ax.grid(axis="y", color=COLORS["light_gray"], linewidth=0.45, alpha=0.65)
        ax.set_axisbelow(True)


def annotation_box(alpha: float = 0.78) -> dict:
    return {
        "boxstyle": "round,pad=0.18",
        "facecolor": "white",
        "edgecolor": "none",
        "alpha": alpha,
    }


def save_figure(fig, outdir: Path, stem: str) -> list[Path]:
    outdir.mkdir(parents=True, exist_ok=True)
    paths = [outdir / f"{stem}.svg", outdir / f"{stem}.pdf", outdir / f"{stem}.png"]
    fig.savefig(paths[0])
    fig.savefig(paths[1])
    fig.savefig(paths[2], dpi=600)
    plt.close(fig)
    return paths
