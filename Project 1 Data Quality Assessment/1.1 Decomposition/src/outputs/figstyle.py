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
import numpy as np
import pandas as pd

# level / component colours (kept in English, synced with the D1 palette)
COLORS = {
    "raw":       "#34495E",   # original signal (dark slate)
    "trend":     "#2E7D32",   # trend m(t)      (green)
    "seasonal":  "#E08214",   # seasonal s(t)   (amber)
    "residual":  "#C0392B",   # residual e(t)   (red)
    "innov":     "#762A83",   # innovation η(t) (purple)
}

# distinct palette for multi-variable combined overviews
PALETTE = ["#2166AC", "#D6604D", "#1B7837", "#E08214", "#762A83",
           "#35978F", "#B2182B", "#053061", "#878787", "#4DAC26",
           "#9970AB", "#C51B7D"]


def setup_style() -> None:
    """Install the full-frame, gridded, English style globally."""
    plt.rcParams.update({
        "font.family": "sans-serif",
        "font.sans-serif": ["DejaVu Sans", "Arial", "Liberation Sans"],
        "axes.unicode_minus": False,
        "font.size": 9, "axes.titlesize": 10, "axes.labelsize": 9,
        "xtick.labelsize": 8, "ytick.labelsize": 8, "legend.fontsize": 8,
        "figure.dpi": 150, "savefig.dpi": 300, "savefig.bbox": "tight",
        # ── full frame: ALL four spines on every axes ──
        "axes.linewidth": 0.9,
        "axes.spines.top": True, "axes.spines.right": True,
        "axes.spines.left": True, "axes.spines.bottom": True,
        # ── light grid ──
        "axes.grid": True, "grid.alpha": 0.30, "grid.linewidth": 0.5,
        "grid.linestyle": "-",
        "lines.linewidth": 1.0,
    })


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
        # full frame already on via rcParams; ensure it for this axes too
        for sp in ("top", "right", "left", "bottom"):
            ax.spines[sp].set_visible(True)

    if x_is_time:
        axes[-1].xaxis.set_major_locator(mdates.AutoDateLocator())
        axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
    axes[-1].set_xlabel(meta.get("xlabel", "Time"), fontsize=9)
    axes[-1].tick_params(axis="x", labelsize=7.5, rotation=0)

    fig.suptitle(meta.get("title", ""), y=0.997, fontsize=10.5)
    fig.subplots_adjust(hspace=meta.get("hspace", 0.16),
                        left=meta.get("left", 0.16), right=0.975,
                        top=meta.get("top", 0.95), bottom=meta.get("bottom", 0.07))
    Path(out_png).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=300, bbox_inches="tight")
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
            c = colors[j] or "#333333"
            if cells_lo is not None and cells_hi is not None:
                lo, hi = cells_lo[i][j], cells_hi[i][j]
                if lo and hi and lo in df.columns and hi in df.columns:
                    ax.fill_between(x, np.asarray(df[lo], float),
                                    np.asarray(df[hi], float),
                                    color=c, alpha=0.22, linewidth=0)
            if col is not None and col in df.columns:
                y = np.asarray(df[col].values, dtype=float)
                ax.plot(x, y, color=c, lw=0.5, solid_capstyle="round")
            ax.margins(x=0)
            ax.grid(True, alpha=0.30, lw=0.4)
            ax.yaxis.set_major_locator(plt.MaxNLocator(3))
            ax.tick_params(axis="both", labelsize=6, length=2)
            for sp in ("top", "right", "left", "bottom"):
                ax.spines[sp].set_visible(True)
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
    Path(out_png).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=300)
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
