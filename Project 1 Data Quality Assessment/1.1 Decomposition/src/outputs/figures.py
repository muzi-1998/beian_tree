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

plt.rcParams.update({
    "font.family": "DejaVu Sans", "font.size": 9,
    "axes.titlesize": 10, "axes.labelsize": 9,
    "xtick.labelsize": 8, "ytick.labelsize": 8, "legend.fontsize": 8,
    "figure.dpi": 150, "savefig.dpi": 300, "savefig.bbox": "tight",
    "axes.linewidth": 0.8, "axes.grid": True, "grid.alpha": 0.25,
    "grid.linewidth": 0.5, "lines.linewidth": 1.0,
    "axes.spines.top": False, "axes.spines.right": False,
})

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
