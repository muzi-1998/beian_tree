"""src/outputs/figstyle.py — shared full-frame plotting style + generic stacked
renderer + plot-data bundle I/O.

The §1.1 figures use a FULL-FRAME (boxed) panel style: every subplot keeps all
four spines, a light grid, and a real date/time x-axis (cf. plan Fig.3). Labels
stay in English. This module is the single source of truth for that style so the
pipeline (`src/outputs/figures.py`) and the standalone reproduction script
(`plot_data/replot.py`) render byte-for-byte identical figures from the same
data bundle.

A *bundle* = a CSV of the plotted series + a JSON sidecar describing the panels
(column, ylabel, colour), the title, the x-axis kind and the output PNG path.
"""
from __future__ import annotations
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as mticker
from matplotlib.text import Text
import numpy as np
import pandas as pd
import re

# level / component colours (kept in English, synced with the D1 palette)
COLORS = {
    "raw":       "#34495E",   # original signal (dark slate)
    "trend":     "#2E7D32",   # trend m(t)      (green)
    "seasonal":  "#E08214",   # seasonal s(t)   (amber)
    "residual":  "#C0392B",   # residual e(t)   (red)
    "innov":     "#762A83",   # innovation η(t) (purple)
}

# Okabe-Ito colourblind-safe palette + fixed roles for the DO A–D figure set
OKABE_ITO = {
    "blue": "#0072B2",        # single-series data / train 1#
    "orange": "#E69F00",      # second series / train 2#
    "green": "#009E73",
    "vermillion": "#D55E00",  # ALARM / threshold lines ONLY (not data)
    "skyblue": "#56B4E9",
    "yellow": "#F0E442",
    "purple": "#CC79A7",
    "black": "#000000",
    "gray": "#999999",        # bands / zero / non-alarm reference lines
    "spectrum": "#1a1a2e",    # spectrum line
}

# distinct palette for multi-variable combined overviews
PALETTE = ["#2166AC", "#D6604D", "#1B7837", "#E08214", "#762A83",
           "#35978F", "#B2182B", "#053061", "#878787", "#4DAC26",
           "#9970AB", "#C51B7D"]


def setup_style() -> None:
    """Install the shared publication style for §1.1 figures."""
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans", "Liberation Sans"],
        "axes.unicode_minus": False,
        "font.size": 9, "axes.titlesize": 10, "axes.labelsize": 9,
        "xtick.labelsize": 8, "ytick.labelsize": 8, "legend.fontsize": 8,
        "figure.dpi": 150, "savefig.dpi": 600, "savefig.bbox": "tight",
        "pdf.fonttype": 42, "ps.fonttype": 42, "svg.fonttype": "none",
        # Open axes reduce visual weight in dense multi-panel figures.
        "axes.linewidth": 0.8,
        "axes.spines.top": False, "axes.spines.right": False,
        "axes.spines.left": True, "axes.spines.bottom": True,
        # ── light grid ──
        "axes.grid": True, "grid.alpha": 0.30, "grid.linewidth": 0.5,
        "grid.linestyle": "-",
        "lines.linewidth": 1.0,
        "xtick.major.width": 0.8, "ytick.major.width": 0.8,
        "xtick.minor.width": 0.8, "ytick.minor.width": 0.8,
    })


_PANEL_RE = re.compile(r"^\s*\(?([A-Za-z])\)?(?:\s*[-.:)]?\s*)$")
_TITLE_PANEL_RE = re.compile(
    r"^\s*(?:\(([A-Za-z])\)|([A-Za-z])[.):]|([a-z])\s{2,})(.*)$"
)


def _is_panel_text(ax, text) -> bool:
    if _PANEL_RE.match(text.get_text()) is None or text.get_transform() is not ax.transAxes:
        return False
    x, y = text.get_position()
    return x <= 0.12 and y >= 0.90


def _add_endpoint_ticks(ax, axis_name: str, linewidth: float = 0.8) -> None:
    """Add unlabeled ticks at both visible spine endpoints without moving limits."""
    axis = ax.xaxis if axis_name == "x" else ax.yaxis
    limits = ax.get_xlim() if axis_name == "x" else ax.get_ylim()
    lo, hi = sorted(float(v) for v in limits)
    span = hi - lo
    if not np.isfinite([lo, hi]).all() or span <= 0:
        return
    major = np.asarray(axis.get_majorticklocs(), dtype=float)
    minor = np.asarray(axis.get_minorticklocs(), dtype=float)
    present = np.r_[major[np.isfinite(major)], minor[np.isfinite(minor)]]
    tol = max(span * 1e-7, 1e-12)
    endpoints = [v for v in (lo, hi)
                 if not np.any(np.isclose(present, v, rtol=0, atol=tol))]
    if endpoints:
        inside_minor = minor[(minor >= lo - tol) & (minor <= hi + tol) & np.isfinite(minor)]
        axis.set_minor_locator(mticker.FixedLocator(np.unique(np.r_[inside_minor, endpoints])))
    if axis_name == "x":
        bottom = ax.spines["bottom"].get_visible()
        top = ax.spines["top"].get_visible()
        ax.tick_params(axis="x", which="both", width=linewidth, direction="in",
                       bottom=bottom, top=top)
        ax.tick_params(axis="x", which="minor", length=3)
    else:
        left = ax.spines["left"].get_visible()
        right = ax.spines["right"].get_visible()
        ax.tick_params(axis="y", which="both", width=linewidth, direction="in",
                       left=left, right=right)
        ax.tick_params(axis="y", which="minor", length=3)


def finalize_publication_figure(fig, auto_panel_labels: bool = True,
                                linewidth: float = 0.8) -> None:
    """Enforce typography, axes, endpoint ticks, and compact panel labels."""
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
                spine.set_linewidth(linewidth)
        _add_endpoint_ticks(ax, "x", linewidth)
        _add_endpoint_ticks(ax, "y", linewidth)
        if ax.get_label() == "<colorbar>":
            continue
        bounds = tuple(round(v, 5) for v in ax.get_position().bounds)
        if bounds in occupied:
            continue
        occupied.append(bounds)
        primary_axes.append(ax)

    for ax in primary_axes:
        for location in ("left", "center", "right"):
            title = ax.get_title(loc=location)
            match = _TITLE_PANEL_RE.match(title)
            if match:
                letter = (match.group(1) or match.group(2) or match.group(3)).lower()
                ax.set_title(f"({letter}) {match.group(4)}", loc=location)
        for text in ax.texts:
            match = _PANEL_RE.match(text.get_text()) if _is_panel_text(ax, text) else None
            if match:
                text.set_text(f"({match.group(1).lower()})")
                text.set_fontweight("bold")
                text.set_clip_on(False)

    if auto_panel_labels and 2 <= len(primary_axes) <= 12:
        for index, ax in enumerate(primary_axes):
            has_title_label = any(
                _TITLE_PANEL_RE.match(ax.get_title(loc=location)) is not None
                for location in ("left", "center", "right")
            )
            has_text_label = any(_is_panel_text(ax, text) for text in ax.texts)
            if has_title_label or has_text_label:
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


def save_publication_figure(fig, out_path, bbox_inches="tight") -> None:
    """Save a review PNG and editable SVG/PDF masters from one figure."""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    finalize_publication_figure(fig)
    for suffix in (".png", ".svg", ".pdf"):
        fig.savefig(out_path.with_suffix(suffix), dpi=600,
                    bbox_inches=bbox_inches)


def render_stack(df: pd.DataFrame, meta: dict, out_png) -> None:
    """Render a vertically-stacked, full-frame figure from a dataframe + meta.

    df   : has an 'x' column (ISO timestamps if meta['x_is_time'] else numeric)
           plus one column per panel referenced in meta['panels'].
    meta : {title, x_is_time, xlabel, panels:[{col,ylabel,color,lw?}], ...}
    """
    panels = meta["panels"]
    n = len(panels)
    x_is_time = meta.get("x_is_time", True)
    x = pd.to_datetime(df["x"]) if x_is_time else df["x"].values

    panel_h = meta.get("panel_h", 1.25)
    width = meta.get("width", 9.0)
    fig, axes = plt.subplots(n, 1, figsize=(width, panel_h * n + 0.9),
                             sharex=True)
    if n == 1:
        axes = [axes]

    for ax, p in zip(axes, panels):
        c = p.get("color", "#333333")
        lo, hi = p.get("lo"), p.get("hi")
        if lo and hi and lo in df.columns and hi in df.columns:
            ax.fill_between(x, np.asarray(df[lo], float), np.asarray(df[hi], float),
                            color=c, alpha=0.22, linewidth=0)
        y = np.asarray(df[p["col"]].values, dtype=float)
        ax.plot(x, y, color=c, lw=p.get("lw", 0.6), solid_capstyle="round")
        ax.set_ylabel(p["ylabel"], rotation=0, ha="right", va="center",
                      fontsize=8.5, labelpad=10)
        ax.margins(x=0)
        ax.grid(True, alpha=0.30, lw=0.5)
        ax.yaxis.set_major_locator(plt.MaxNLocator(4))
        ax.tick_params(axis="both", labelsize=7.5, length=3)

    if x_is_time:
        axes[-1].xaxis.set_major_locator(mdates.AutoDateLocator())
        axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
    axes[-1].set_xlabel(meta.get("xlabel", "Time"), fontsize=9)
    axes[-1].tick_params(axis="x", labelsize=7.5, rotation=0)

    fig.suptitle(meta.get("title", ""), y=0.997, fontsize=10.5)
    fig.subplots_adjust(hspace=meta.get("hspace", 0.16),
                        left=meta.get("left", 0.16), right=0.975,
                        top=meta.get("top", 0.95), bottom=meta.get("bottom", 0.07))
    save_publication_figure(fig, out_png)
    plt.close(fig)


def render_grid(df: pd.DataFrame, meta: dict, out_png) -> None:
    """Render a full-frame GRID figure: rows = variables, columns = components.

    df   : 'x' column + one column per cell (named in meta['cells']).
    meta : {title, x_is_time, xlabel, row_labels:[R], col_labels:[C],
            col_colors:[C], cells:[[colname]*C]*R, ...}
    Column headers sit on the top row, variable labels on the left column,
    a shared date x-axis on the bottom row. Every cell is a full box + grid.
    """
    row_labels = meta["row_labels"]
    col_labels = meta["col_labels"]
    colors = meta.get("col_colors", [None] * len(col_labels))
    cells = meta["cells"]
    cells_lo = meta.get("cells_lo")
    cells_hi = meta.get("cells_hi")
    x_is_time = meta.get("x_is_time", True)
    x = pd.to_datetime(df["x"]) if x_is_time else df["x"].values
    R, Cn = len(row_labels), len(col_labels)

    fig, axes = plt.subplots(R, Cn, sharex=True, squeeze=False,
                             figsize=(meta.get("width", 2.25 * Cn + 1.2),
                                      meta.get("row_h", 1.05) * R + 1.4),
                             layout="constrained")
    for i in range(R):
        for j in range(Cn):
            ax = axes[i][j]
            col = cells[i][j]
            st = meta.get("cell_styles", {}).get(f"{i}_{j}", {})
            c = st.get("color") or colors[j] or "#333333"
            if cells_lo is not None and cells_hi is not None:
                lo, hi = cells_lo[i][j], cells_hi[i][j]
                if lo and hi and lo in df.columns and hi in df.columns:
                    ax.fill_between(x, np.asarray(df[lo], float),
                                    np.asarray(df[hi], float),
                                    color=c, alpha=0.22, linewidth=0)
            if col is not None and col in df.columns:
                y = np.asarray(df[col].values, dtype=float)
                ax.plot(x, y, color=c, lw=0.5, solid_capstyle="round")
            if st.get("tag"):
                ax.text(0.96, 0.88, st["tag"], transform=ax.transAxes,
                        ha="right", va="top", fontsize=6, color="#C0392B")
            ax.margins(x=0)
            ax.grid(True, alpha=0.30, lw=0.4)
            ax.yaxis.set_major_locator(plt.MaxNLocator(3))
            ax.tick_params(axis="both", labelsize=6, length=2)
            if i == 0:
                ax.set_title(col_labels[j], fontsize=8.5, pad=4)
            if j == 0:
                ax.set_ylabel(row_labels[i], rotation=0, ha="right",
                              va="center", fontsize=8, labelpad=8)
            if i == R - 1 and x_is_time:
                # cap tick count + tilt labels so narrow grid cells don't collide
                loc = mdates.AutoDateLocator(minticks=3,
                                             maxticks=meta.get("x_maxticks", 6))
                ax.xaxis.set_major_locator(loc)
                ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
                ax.tick_params(axis="x", labelsize=6,
                               labelrotation=meta.get("xtick_rotation", 30))
                for lbl in ax.get_xticklabels():
                    lbl.set_ha("right")
                    lbl.set_rotation_mode("anchor")

    fig.suptitle(meta.get("title", ""), fontsize=11)
    fig.supxlabel(meta.get("xlabel", "Time"), fontsize=8)
    save_publication_figure(fig, out_png)
    plt.close(fig)


def dump_bundle(name: str, df: pd.DataFrame, meta: dict, plot_data_root) -> None:
    """Persist the figure's data (CSV) + render spec (JSON) for reproduction."""
    root = Path(plot_data_root)
    root.mkdir(parents=True, exist_ok=True)
    df.to_csv(root / f"{name}.csv", index=False, encoding="utf-8-sig")
    spec = dict(meta)
    spec["name"] = name
    spec["csv"] = f"{name}.csv"
    with open(root / f"{name}.json", "w", encoding="utf-8") as fh:
        json.dump(spec, fh, ensure_ascii=False, indent=2)
