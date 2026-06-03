"""src/outputs/figures.py — SCI-style figures for the 1.1 deliverables.

Palette synced with the D1 project. Each figure also dumps its plot data so it
can be re-rendered. Figures produced:
  * availability heatmap (variable x time, coloured by flag)
  * 4-level decomposition (trend -> seasonal -> residual -> innovation)
  * 3-type periodicity spectrum comparison
  * ACF before/after whitening
"""
from __future__ import annotations
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.colors import ListedColormap, BoundaryNorm
from pathlib import Path

from .figstyle import (setup_style, render_stack, render_grid, dump_bundle,
                       COLORS, PALETTE)

# Full-frame (boxed) + gridded style, applied to EVERY figure in this module.
setup_style()

C = {"blue": "#2166AC", "red": "#D6604D", "green": "#4DAC26",
     "orange": "#F4A582", "purple": "#762A83", "gray": "#878787",
     "teal": "#1B7837", "amber": "#E08214", "navy": "#053061", "cyan": "#35978F"}

# flag code -> (label, colour)
FLAG_STYLE = {
    0: ("original", "#1A9850"),
    1: ("short-interp", "#A6D96A"),
    2: ("long-gap", "#878787"),
    3: ("cosine-fill", "#66BD63"),
    4: ("same-day-drop", "#D9EF8B"),
    5: ("transition", "#FEE08B"),
    6: ("hold", "#74ADD1"),
    7: ("range-violation", "#D73027"),
    8: ("IQR-outlier", "#F46D43"),
    9: ("censored", "#762A83"),
}


def availability_heatmap(flags: pd.DataFrame, out_path: Path,
                         downsample: str = "1h", title: str = ""):
    """Variable x time availability/flag heatmap (most-severe flag per cell)."""
    # downsample by taking the max flag code in each window (worst case)
    fl = flags.resample(downsample).max()
    codes = sorted(FLAG_STYLE.keys())
    cmap = ListedColormap([FLAG_STYLE[c][1] for c in codes])
    norm = BoundaryNorm([c - 0.5 for c in codes] + [codes[-1] + 0.5], cmap.N)

    fig, ax = plt.subplots(figsize=(12, max(4, 0.32 * fl.shape[1])))
    data = fl.T.values.astype(float)
    extent = [mdates.date2num(fl.index[0]), mdates.date2num(fl.index[-1]),
              0, fl.shape[1]]
    ax.imshow(data, aspect="auto", cmap=cmap, norm=norm, extent=extent,
              origin="lower", interpolation="nearest")
    ax.grid(False)
    ax.set_yticks(np.arange(fl.shape[1]) + 0.5)
    ax.set_yticklabels(fl.columns, fontsize=6)
    ax.xaxis_date()
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%m-%d"))
    ax.set_title(title or "Data availability heatmap (flag = worst per window)")
    handles = [plt.Rectangle((0, 0), 1, 1, color=FLAG_STYLE[c][1])
               for c in codes]
    labels = [FLAG_STYLE[c][0] for c in codes]
    ax.legend(handles, labels, ncol=5, fontsize=6, loc="upper center",
              bbox_to_anchor=(0.5, -0.12), frameon=False)
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def four_level_decomposition(raw, trend, seasonal, resid, innov, out_path: Path,
                             title: str = "", anomaly_span=None):
    """Four-level decomposition: (raw+trend) -> seasonal s(t) -> residual e(t)
    -> innovation eta(t). Matches plan Fig.3 趋势-周期-残差-创新."""
    fig, axes = plt.subplots(4, 1, figsize=(11, 8.5), sharex=True)
    # panel 0: raw overlaid with trend m(t)
    axes[0].plot(raw.index, raw.values, color=C["gray"], lw=0.5, alpha=0.8, label="raw X(t)")
    axes[0].plot(trend.index, trend.values, color=C["navy"], lw=1.4, label="trend m(t)")
    axes[0].legend(loc="upper right", ncol=2)
    axes[0].set_ylabel("value")
    axes[0].set_title("Raw X(t) + trend m(t)", fontsize=8, loc="left")
    # panels 1-3
    for axi, series, col, ylab, name in [
        (axes[1], seasonal, C["teal"], "seasonal", "Seasonal s(t)"),
        (axes[2], resid, C["blue"], "residual", "Residual e(t) = X - m - s"),
        (axes[3], innov, C["red"], "eta", "Innovation eta(t) (whitened)"),
    ]:
        axi.plot(series.index, series.values, color=col, lw=0.6)
        axi.set_ylabel(ylab)
        axi.set_title(name, fontsize=8, loc="left")
    if anomaly_span is not None:
        for axi in axes:
            axi.axvspan(anomaly_span[0], anomaly_span[1], color=C["amber"],
                        alpha=0.18, zorder=0)
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
    fig.suptitle(title or "Four-level decomposition", y=0.995)
    fig.tight_layout()
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def decomposition_stack(raw, trend, seasonal, residual, innovation,
                        out_path: Path, ylabels=None, title: str = "",
                        plot_data_root=None, bundle_name=None):
    """EMD/VMD-style FULL-FRAME stacked decomposition figure (plan Fig.3).

    Top panel = raw X(t); below it the additive components trend m(t) /
    seasonal s(t) / residual e(t) / whitened innovation η(t) (analogous to
    IMF_1..n + Residue). Every panel is a full box (4 spines) with a light grid
    and a shared date x-axis. `ylabels` are the (English) panel labels resolved
    by the caller (with J / AR order annotations); if omitted, defaults are used.
    Also dumps a reproducible data bundle to `plot_data_root` when given.
    """
    defaults = ["Raw X(t)", "Trend m(t)", "Seasonal s(t)",
                "Residual e(t)", "Innovation η(t)"]
    ylabels = ylabels or defaults
    cols = [COLORS["raw"], COLORS["trend"], COLORS["seasonal"],
            COLORS["residual"], COLORS["innov"]]
    levels = list(zip([raw, trend, seasonal, residual, innovation], ylabels, cols))
    levels = [(s, lab, c) for (s, lab, c) in levels if s is not None]

    idx = pd.Series(raw).index
    data = {"x": idx}
    panels = []
    for k, (s, lab, c) in enumerate(levels):
        col = f"level{k}"
        data[col] = pd.Series(s).reindex(idx).values
        panels.append(dict(col=col, ylabel=lab, color=c, lw=0.6))
    df = pd.DataFrame(data)
    meta = dict(kind="stack", title=title or "Multi-scale decomposition",
                x_is_time=True, xlabel="Time", panels=panels,
                out_png=str(out_path), width=9.0, panel_h=1.25,
                left=0.165, hspace=0.16)
    render_stack(df, meta, out_path)
    if plot_data_root and bundle_name:
        dump_bundle(bundle_name, df, meta, plot_data_root)


# component labels / colours shared by the combined decomposition grid
GRID_COMP_LABELS = ["Raw X(t)", "Trend m(t)", "Seasonal s(t)",
                    "Residual e(t)", "Innovation η(t)"]
GRID_COMP_COLORS = [COLORS["raw"], COLORS["trend"], COLORS["seasonal"],
                    COLORS["residual"], COLORS["innov"]]


def combined_group_grid(rows, out_path: Path, title: str = "",
                        plot_data_root=None, bundle_name=None):
    """Combined FULL-FRAME decomposition grid for one process group:
    rows = variables, columns = [Raw, Trend, Seasonal, Residual, Innovation].

    `rows` is [(var_label, [raw, trend, seasonal, residual, innovation])]; any
    component may be None (rendered blank). All series in a group share one
    date x-axis. Dumps a reproducible grid bundle when `plot_data_root` given.
    """
    rows = [r for r in rows if r[1] and r[1][0] is not None
            and not pd.Series(r[1][0]).dropna().empty]
    if not rows:
        return
    idx = pd.Series(rows[0][1][0]).index
    data = {"x": idx}
    cells, row_labels = [], []
    for i, (lab, comps) in enumerate(rows):
        row_labels.append(lab)
        cell_row = []
        for j in range(len(GRID_COMP_LABELS)):
            s = comps[j] if j < len(comps) else None
            col = f"r{i}_c{j}"
            if s is None:
                data[col] = np.full(len(idx), np.nan)
            else:
                data[col] = pd.Series(s).reindex(idx).values
            cell_row.append(col)
        cells.append(cell_row)
    df = pd.DataFrame(data)
    meta = dict(kind="grid", title=title or "Group decomposition grid",
                x_is_time=True, xlabel="Time",
                row_labels=row_labels, col_labels=GRID_COMP_LABELS,
                col_colors=GRID_COMP_COLORS, cells=cells,
                out_png=str(out_path), width=2.25 * 5 + 1.2,
                row_h=1.05, hspace=0.28, wspace=0.30,
                xtick_rotation=30, x_maxticks=6)
    render_grid(df, meta, out_path)
    if plot_data_root and bundle_name:
        dump_bundle(bundle_name, df, meta, plot_data_root)


def combined_group_overview(series_list, out_path: Path, title: str = "",
                            plot_data_root=None, bundle_name=None):
    """FULL-FRAME combined overview of all variables in one process group:
    one boxed panel per variable (raw X(t)), shared date x-axis. `series_list`
    is [(label, series, colour?)]; colours default to the shared PALETTE.
    Dumps a reproducible data bundle when `plot_data_root` is given.
    """
    series_list = [t for t in series_list if t[1] is not None
                   and not pd.Series(t[1]).dropna().empty]
    if not series_list:
        return
    idx = pd.Series(series_list[0][1]).index
    data = {"x": idx}
    panels = []
    for k, item in enumerate(series_list):
        lab, s = item[0], item[1]
        c = item[2] if len(item) > 2 and item[2] else PALETTE[k % len(PALETTE)]
        col = f"var{k}"
        data[col] = pd.Series(s).reindex(idx).values
        panels.append(dict(col=col, ylabel=lab, color=c, lw=0.6))
    df = pd.DataFrame(data)
    meta = dict(title=title or "Group overview", x_is_time=True, xlabel="Time",
                panels=panels, out_png=str(out_path), width=9.5,
                panel_h=1.0, left=0.115, hspace=0.16)
    render_stack(df, meta, out_path)
    if plot_data_root and bundle_name:
        dump_bundle(bundle_name, df, meta, plot_data_root)


def spectrum_comparison(spectra: dict, out_path: Path, title: str = ""):
    """spectra: {label: (freq_per_day, power)} — mark 24h/12h/168h."""
    fig, axes = plt.subplots(1, len(spectra), figsize=(4.2 * len(spectra), 3.4),
                             squeeze=False)
    for ax, (label, (freq, power)) in zip(axes[0], spectra.items()):
        ax.semilogy(freq, power, color=C["blue"], lw=0.9)
        for cyc, name, col in [(1, "24h", C["red"]), (2, "12h", C["amber"]),
                               (1 / 7, "168h", C["teal"])]:
            ax.axvline(cyc, color=col, ls="--", lw=0.9, alpha=0.8)
            ax.text(cyc, ax.get_ylim()[1], name, color=col, fontsize=6,
                    rotation=90, va="top", ha="right")
        ax.set_title(label, fontsize=9)
        ax.set_xlabel("cycles / day"); ax.set_xlim(0, 4)
    axes[0][0].set_ylabel("power (log)")
    fig.suptitle(title or "Periodicity spectrum comparison", y=1.02)
    fig.tight_layout()
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def acf_before_after(acf_resid, acf_innov, out_path: Path, title: str = "",
                     conf: float = None):
    """ACF of residual (before) vs innovation (after whitening)."""
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.3), sharey=True)
    for ax, acf, name, col in [(axes[0], acf_resid, "Residual e(t)", C["blue"]),
                               (axes[1], acf_innov, "Innovation eta(t)", C["red"])]:
        lags = np.arange(len(acf))
        ax.bar(lags, acf, color=col, width=0.8)
        if conf:
            ax.axhline(conf, color=C["gray"], ls="--", lw=0.8)
            ax.axhline(-conf, color=C["gray"], ls="--", lw=0.8)
        ax.axhline(0, color="k", lw=0.6)
        ax.set_title(name); ax.set_xlabel("lag")
    axes[0].set_ylabel("ACF")
    fig.suptitle(title or "ACF before / after whitening", y=1.02)
    fig.tight_layout()
    fig.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close(fig)
