"""Shared publication styling for D1 figures."""
from __future__ import annotations

import re

import matplotlib
import matplotlib.ticker as mticker
import numpy as np
from matplotlib.text import Text

AXIS_LINEWIDTH = 0.8
ANNOTATION_FACE_ALPHA = 0.72

# Restrained, colour-vision-safe roles shared by the active D1 figure suite.
PALETTE = {
    "blue": "#2F6F9F", "red": "#B65C5C", "green": "#4C8C5A",
    "orange": "#D28B45", "purple": "#8064A2", "gray": "#6E7478",
    "teal": "#4F9C8A", "amber": "#C3A13B", "navy": "#24465F",
    "cyan": "#73B7C9", "rose": "#C47A8A",
}
STATE_COLORS = {
    "Normal": PALETTE["green"],
    "Refractory": PALETTE["orange"],
    "SustainedAnomaly": PALETTE["purple"],
    "RecoveryCandidate": "#D8CCE4",
    "Recovered": PALETTE["blue"],
}
_PANEL_RE = re.compile(r"^\s*\(?([A-Za-z])\)?(?:\s*[-.:)]?\s*)$")
_TITLE_PANEL_RE = re.compile(
    r"^\s*(?:\(([A-Za-z])\)|([A-Za-z])[.):]|([a-z])\s{2,})(.*)$"
)


def _is_panel_text(ax, text) -> bool:
    if _PANEL_RE.match(text.get_text()) is None or text.get_transform() is not ax.transAxes:
        return False
    x, y = text.get_position()
    return x <= 0.12 and y >= 0.90


def configure_publication_style() -> None:
    matplotlib.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans", "Liberation Sans"],
        "axes.linewidth": AXIS_LINEWIDTH,
        "xtick.major.width": AXIS_LINEWIDTH,
        "ytick.major.width": AXIS_LINEWIDTH,
        "xtick.minor.width": AXIS_LINEWIDTH,
        "ytick.minor.width": AXIS_LINEWIDTH,
        "xtick.direction": "out",
        "ytick.direction": "out",
        "pdf.fonttype": 42,
        "ps.fonttype": 42,
        "svg.fonttype": "none",
    })


def _is_full_frame(ax) -> bool:
    """Return True only when all four Cartesian spines are visible."""
    return all(ax.spines[name].get_visible()
               for name in ("left", "right", "bottom", "top"))


def _add_endpoint_ticks(ax, axis_name: str) -> None:
    axis = ax.xaxis if axis_name == "x" else ax.yaxis
    limits = ax.get_xlim() if axis_name == "x" else ax.get_ylim()
    lo, hi = sorted(float(value) for value in limits)
    span = hi - lo
    if not np.isfinite([lo, hi]).all() or span <= 0:
        return
    major = np.asarray(axis.get_majorticklocs(), dtype=float)
    minor = np.asarray(axis.get_minorticklocs(), dtype=float)
    present = np.r_[major[np.isfinite(major)], minor[np.isfinite(minor)]]
    tolerance = max(span * 1e-7, 1e-12)
    endpoints = [value for value in (lo, hi)
                 if not np.any(np.isclose(present, value, rtol=0, atol=tolerance))]
    if endpoints:
        inside = minor[(minor >= lo - tolerance) & (minor <= hi + tolerance)
                       & np.isfinite(minor)]
        axis.set_minor_locator(mticker.FixedLocator(np.unique(np.r_[inside, endpoints])))
    direction = "in" if _is_full_frame(ax) else "out"
    if axis_name == "x":
        ax.tick_params(axis="x", which="both", width=AXIS_LINEWIDTH, direction=direction,
                       bottom=ax.spines["bottom"].get_visible(),
                       top=ax.spines["top"].get_visible())
        ax.tick_params(axis="x", which="minor", length=3)
    else:
        ax.tick_params(axis="y", which="both", width=AXIS_LINEWIDTH, direction=direction,
                       left=ax.spines["left"].get_visible(),
                       right=ax.spines["right"].get_visible())
        ax.tick_params(axis="y", which="minor", length=3)


def annotate_data_label(ax, text: str, xy, *, xytext=(4, 4),
                        textcoords: str = "offset points", arrow: bool = False,
                        fontsize: float = 7, alpha: float = ANNOTATION_FACE_ALPHA,
                        **kwargs):
    """Add a readable data label without fully hiding evidence beneath it."""
    arrowprops = kwargs.pop("arrowprops", None)
    if arrow and arrowprops is None:
        arrowprops = {
            "arrowstyle": "-", "color": PALETTE["gray"],
            "linewidth": 0.45, "alpha": 0.75,
        }
    return ax.annotate(
        text, xy, xytext=xytext, textcoords=textcoords,
        fontsize=fontsize, annotation_clip=False,
        bbox={"facecolor": "white", "edgecolor": "none",
              "alpha": alpha, "pad": 0.18},
        arrowprops=arrowprops, **kwargs,
    )


def finalize_figure(fig, auto_panel_labels: bool = True) -> None:
    """Enforce Arial, equal axis weights, endpoint ticks, and panel-label syntax."""
    fig.canvas.draw()
    for text in fig.findobj(match=Text):
        text.set_fontfamily("Arial")
    primary_axes = []
    occupied = []
    for ax in fig.axes:
        if not ax.axison:
            continue
        for text in ax.findobj(match=Text):
            text.set_fontfamily("Arial")
        for spine in ax.spines.values():
            if spine.get_visible():
                spine.set_linewidth(AXIS_LINEWIDTH)
        _add_endpoint_ticks(ax, "x")
        _add_endpoint_ticks(ax, "y")
        if ax.get_label() == "<colorbar>":
            continue
        bounds = tuple(round(value, 5) for value in ax.get_position().bounds)
        if bounds in occupied:
            continue
        occupied.append(bounds)
        primary_axes.append(ax)

    for ax in primary_axes:
        for location in ("left", "center", "right"):
            title_match = _TITLE_PANEL_RE.match(ax.get_title(loc=location))
            if title_match:
                letter = (title_match.group(1) or title_match.group(2)
                          or title_match.group(3)).lower()
                ax.set_title(f"({letter}) {title_match.group(4)}", loc=location)
        for text in ax.texts:
            label_match = _PANEL_RE.match(text.get_text()) if _is_panel_text(ax, text) else None
            if label_match:
                text.set_text(f"({label_match.group(1).lower()})")
                text.set_fontweight("bold")
                text.set_clip_on(False)

    if auto_panel_labels and 2 <= len(primary_axes) <= 12:
        for index, ax in enumerate(primary_axes):
            title_labeled = any(
                _TITLE_PANEL_RE.match(ax.get_title(loc=location)) is not None
                for location in ("left", "center", "right")
            )
            text_labeled = any(_is_panel_text(ax, text) for text in ax.texts)
            if title_labeled or text_labeled:
                continue
            left_title = ax.get_title(loc="left")
            if left_title:
                ax.set_title(f"({chr(97 + index)}) {left_title}", loc="left")
                continue
            ax.text(0.0, 1.02, f"({chr(97 + index)})", transform=ax.transAxes,
                    ha="left", va="bottom", fontsize=8, fontweight="bold",
                    fontfamily="Arial", clip_on=False,
                    bbox={"facecolor": "white", "edgecolor": "none", "pad": 0.15})
    fig.canvas.draw()
