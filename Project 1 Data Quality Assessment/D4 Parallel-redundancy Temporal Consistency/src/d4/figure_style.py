from __future__ import annotations

import matplotlib as mpl
import matplotlib.ticker as mticker
import matplotlib.pyplot as plt
import numpy as np


AXIS_WIDTH = 0.8
PANEL_X = -0.10
PANEL_Y = 1.02
PANEL_FONTSIZE = 9.0
TITLE_PAD = 6.0
PALETTE = {
    "blue": "#2F6F9F", "orange": "#D28B45", "green": "#4C8C5A",
    "red": "#B65C5C", "purple": "#8064A2", "gray": "#6E7478",
    "light_gray": "#D5DADD", "teal": "#4F9C8A", "amber": "#C3A13B",
}


def configure_style() -> None:
    mpl.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans", "Liberation Sans"],
        "font.size": 7,
        "axes.labelsize": 7,
        "axes.titlesize": 7,
        "axes.titlepad": TITLE_PAD,
        "axes.linewidth": AXIS_WIDTH,
        "xtick.labelsize": 6.5,
        "ytick.labelsize": 6.5,
        "xtick.major.width": AXIS_WIDTH,
        "ytick.major.width": AXIS_WIDTH,
        "xtick.minor.width": AXIS_WIDTH,
        "ytick.minor.width": AXIS_WIDTH,
        "xtick.direction": "out",
        "ytick.direction": "out",
        "legend.frameon": False,
        "svg.fonttype": "none",
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
    })


def _full_frame(ax) -> bool:
    return all(ax.spines[name].get_visible() for name in ("left", "right", "top", "bottom"))


def _endpoint_ticks(ax, axis_name: str) -> None:
    axis = ax.xaxis if axis_name == "x" else ax.yaxis
    limits = ax.get_xlim() if axis_name == "x" else ax.get_ylim()
    lo, hi = sorted(map(float, limits))
    span = hi - lo
    if not np.isfinite([lo, hi]).all() or span <= 0:
        return
    locations = np.r_[axis.get_majorticklocs(), axis.get_minorticklocs()]
    tolerance = max(span * 1e-7, 1e-12)
    missing = [end for end in (lo, hi) if not np.any(np.isclose(locations, end, atol=tolerance, rtol=0))]
    if missing:
        minor = np.asarray(axis.get_minorticklocs(), dtype=float)
        minor = minor[(minor >= lo - tolerance) & (minor <= hi + tolerance)]
        axis.set_minor_locator(mticker.FixedLocator(np.unique(np.r_[minor, missing])))
    direction = "in" if _full_frame(ax) else "out"
    ax.tick_params(axis=axis_name, which="both", direction=direction, width=AXIS_WIDTH)
    ax.tick_params(axis=axis_name, which="minor", length=2.5)


def panel_label(ax, letter: str) -> None:
    ax.text(
        PANEL_X, PANEL_Y, f"({letter.lower()})", transform=ax.transAxes,
        ha="right", va="bottom", fontsize=PANEL_FONTSIZE,
        fontweight="bold", clip_on=False,
        bbox={
            "facecolor": "white", "edgecolor": "none",
            "alpha": 0.88, "pad": 0.12,
        },
    )


def annotate(ax, text: str, xy: tuple[float, float], *, xytext=(4, 4)):
    return ax.annotate(
        text, xy=xy, xytext=xytext, textcoords="offset points", fontsize=6.5,
        bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.72, "pad": 0.15},
        arrowprops={"arrowstyle": "-", "color": PALETTE["gray"], "linewidth": 0.45},
    )


def finalize(fig, auto_panel_labels: bool = False) -> None:
    fig.canvas.draw()
    for ax in fig.axes:
        if not ax.axison:
            continue
        for spine in ax.spines.values():
            if spine.get_visible():
                spine.set_linewidth(AXIS_WIDTH)
        _endpoint_ticks(ax, "x")
        _endpoint_ticks(ax, "y")
    fig.canvas.draw()


def save_figure(fig, output_base) -> None:
    finalize(fig)
    fig.savefig(output_base.with_suffix(".svg"), bbox_inches="tight")
    fig.savefig(output_base.with_suffix(".pdf"), bbox_inches="tight")
    fig.savefig(output_base.with_suffix(".png"), dpi=600, bbox_inches="tight")
    plt.close(fig)
