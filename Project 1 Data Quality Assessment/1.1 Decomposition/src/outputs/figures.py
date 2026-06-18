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
                       COLORS, PALETTE, OKABE_ITO as OI)

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


def _daily_env(s, didx):
    """Daily min/max/mean envelope of a series, reindexed onto `didx`."""
    env = pd.Series(s).resample("1D").agg(["min", "max", "mean"]).reindex(didx)
    return env["mean"].values, env["min"].values, env["max"].values


def decomposition_overview_stack(raw, trend, seasonal, residual, innovation,
                                 out_path: Path, ylabels=None, title: str = "",
                                 plot_data_root=None, bundle_name=None):
    """FULL-SPAN daily-envelope overview of one channel's 4-level decomposition.

    Same 5 stacked panels as decomposition_stack, but over the WHOLE record:
    each panel shows the daily mean line + daily min–max envelope band, so all
    ~256 days are visible while the amplitude evolution of the zero-mean
    seasonal/residual/innovation is still conveyed (a plain daily mean would
    flatten them to ~0).
    """
    defaults = ["Raw X(t)", "Trend m(t)", "Seasonal s(t)",
                "Residual e(t)", "Innovation η(t)"]
    ylabels = ylabels or defaults
    cols = [COLORS["raw"], COLORS["trend"], COLORS["seasonal"],
            COLORS["residual"], COLORS["innov"]]
    levels = [(s, lab, c) for (s, lab, c) in
              zip([raw, trend, seasonal, residual, innovation], ylabels, cols)
              if s is not None]
    didx = pd.Series(raw).resample("1D").mean().index
    data = {"x": didx}
    panels = []
    for k, (s, lab, c) in enumerate(levels):
        m, lo, hi = _daily_env(s, didx)
        data[f"m{k}"], data[f"lo{k}"], data[f"hi{k}"] = m, lo, hi
        panels.append(dict(col=f"m{k}", lo=f"lo{k}", hi=f"hi{k}",
                           ylabel=lab, color=c, lw=0.8))
    df = pd.DataFrame(data)
    meta = dict(kind="stack", title=title or "Full-span daily overview",
                x_is_time=True, xlabel="Time", panels=panels,
                out_png=str(out_path), width=9.0, panel_h=1.25,
                left=0.165, hspace=0.16)
    render_stack(df, meta, out_path)
    if plot_data_root and bundle_name:
        dump_bundle(bundle_name, df, meta, plot_data_root)


def combined_overview_grid(rows, out_path: Path, title: str = "",
                           plot_data_root=None, bundle_name=None):
    """FULL-SPAN daily-envelope combined grid (variables × 5 components).

    Like combined_group_grid but over the whole record, each cell drawn as a
    daily mean line + daily min–max envelope band.
    """
    rows = [r for r in rows if r[1] and r[1][0] is not None
            and not pd.Series(r[1][0]).dropna().empty]
    if not rows:
        return
    didx = pd.Series(rows[0][1][0]).resample("1D").mean().index
    data = {"x": didx}
    cells, cells_lo, cells_hi, row_labels = [], [], [], []
    for i, (lab, comps) in enumerate(rows):
        row_labels.append(lab)
        cr, crl, crh = [], [], []
        for j in range(len(GRID_COMP_LABELS)):
            s = comps[j] if j < len(comps) else None
            cm, cl, ch = f"r{i}_c{j}_m", f"r{i}_c{j}_lo", f"r{i}_c{j}_hi"
            if s is None:
                nan = np.full(len(didx), np.nan)
                data[cm] = data[cl] = data[ch] = nan
            else:
                data[cm], data[cl], data[ch] = _daily_env(s, didx)
            cr.append(cm); crl.append(cl); crh.append(ch)
        cells.append(cr); cells_lo.append(crl); cells_hi.append(crh)
    df = pd.DataFrame(data)
    meta = dict(kind="grid", title=title or "Group full-span overview",
                x_is_time=True, xlabel="Time",
                row_labels=row_labels, col_labels=GRID_COMP_LABELS,
                col_colors=GRID_COMP_COLORS, cells=cells,
                cells_lo=cells_lo, cells_hi=cells_hi,
                out_png=str(out_path), width=2.25 * 5 + 1.2, row_h=1.05,
                hspace=0.28, wspace=0.30, xtick_rotation=30, x_maxticks=6)
    render_grid(df, meta, out_path)
    if plot_data_root and bundle_name:
        dump_bundle(bundle_name, df, meta, plot_data_root)


def multivar_ribbon_overview(series_list, out_path: Path, title: str = "",
                             plot_data_root=None, bundle_name=None):
    """SI bird's-eye: one boxed panel per variable, full-span daily min–max
    envelope band + daily mean line of the RAW signal. A clean multi-variable
    data-landscape overview (supplementary, not a decomposition figure).
    `series_list` = [(label, raw_series, color?)].
    """
    series_list = [t for t in series_list if t[1] is not None
                   and not pd.Series(t[1]).dropna().empty]
    if not series_list:
        return
    didx = pd.Series(series_list[0][1]).resample("1D").mean().index
    data = {"x": didx}
    panels = []
    for k, item in enumerate(series_list):
        lab, s = item[0], item[1]
        c = item[2] if len(item) > 2 and item[2] else PALETTE[k % len(PALETTE)]
        m, lo, hi = _daily_env(s, didx)
        data[f"m{k}"], data[f"lo{k}"], data[f"hi{k}"] = m, lo, hi
        panels.append(dict(col=f"m{k}", lo=f"lo{k}", hi=f"hi{k}",
                           ylabel=lab, color=c, lw=0.8))
    df = pd.DataFrame(data)
    meta = dict(kind="stack", title=title or "Full-span ribbon overview",
                x_is_time=True, xlabel="Time", panels=panels,
                out_png=str(out_path), width=9.0, panel_h=0.95,
                left=0.11, hspace=0.18)
    render_stack(df, meta, out_path)
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


def acf_band_grid(rows, out_path: Path, lag: int, band_edges, title: str = "",
                  band_colors=None, lag_unit: str = "h", annotate_after=None,
                  plot_data_root=None, bundle_name=None):
    """Before/after-whitening ACF grid for a group of variables, with bars
    coloured by lag band (plan §5.3 + daily-lag emphasis).

    rows        : [(label, acf_resid, acf_innov, conf_resid, conf_innov)] where
                  each acf_* is the sample ACF array (index 0..lag from
                  diagnostics.acf); lags 1..lag are plotted.
    band_edges  : cumulative right edges, e.g. [24, 48] (influent) or
                  [24, 48, 72] (effluent). Lags in (edge_{k-1}, edge_k] share a
                  colour; vertical dotted lines mark the interior edges.
    Layout: rows = variables, 2 columns (Before residual e(t) / After
    innovation η(t)). Full-frame.
    """
    band_colors = band_colors or ["#2166AC", "#E08214", "#1B7837", "#762A83"]
    R = len(rows)
    if R == 0:
        return
    lags = np.arange(1, lag + 1)

    def _band_of(L):
        for bi, e in enumerate(band_edges):
            if L <= e:
                return bi
        return len(band_edges) - 1
    bar_colors = [band_colors[_band_of(L)] for L in lags]

    fig, axes = plt.subplots(R, 2, figsize=(8.8, 1.0 * R + 1.5), squeeze=False,
                             sharex=True, layout="constrained")
    col_titles = ["Before — residual e(t) ACF", "After — innovation η(t) ACF"]
    for i, row in enumerate(rows):
        lab, a_res, a_inn, conf_res, conf_inn = row
        for j, (a, conf) in enumerate([(a_res, conf_res), (a_inn, conf_inn)]):
            ax = axes[i][j]
            vals = np.asarray(a, dtype=float)[1:lag + 1]
            if len(vals) < lag:
                vals = np.r_[vals, np.zeros(lag - len(vals))]
            ax.bar(lags, vals, color=bar_colors, width=0.9, linewidth=0)
            ax.axhline(0, color="k", lw=0.6)
            if conf:
                ax.axhline(conf, color="#888888", ls="--", lw=0.7)
                ax.axhline(-conf, color="#888888", ls="--", lw=0.7)
            for e in band_edges[:-1]:
                ax.axvline(e + 0.5, color="#bbbbbb", ls=":", lw=0.8)
            ax.set_xlim(0.3, lag + 0.7)
            ax.grid(True, axis="y", alpha=0.25, lw=0.4)
            ax.tick_params(labelsize=6, length=2)
            for sp in ("top", "right", "left", "bottom"):
                ax.spines[sp].set_visible(True)
            if i == 0:
                ax.set_title(col_titles[j], fontsize=9, pad=4)
            if j == 0:
                ax.set_ylabel(lab, rotation=0, ha="right", va="center",
                              fontsize=7.5, labelpad=8)
            if i == R - 1:
                ax.set_xlabel(f"lag ({lag_unit})", fontsize=8)
            if annotate_after and j == 1 and i < len(annotate_after) \
                    and annotate_after[i]:
                ax.text(0.97, 0.90, annotate_after[i], transform=ax.transAxes,
                        ha="right", va="top", fontsize=6.5, color="#555555")

    if len(band_edges) > 1:                       # multi-band -> colour legend
        from matplotlib.patches import Patch
        handles, prev = [], 0
        for bi, e in enumerate(band_edges):
            handles.append(Patch(color=band_colors[bi],
                                 label=f"lag {prev + 1}–{e} {lag_unit}"))
            prev = e
        fig.legend(handles=handles, loc="outside lower center",
                   ncol=len(band_edges), fontsize=8, frameon=False)
    fig.suptitle(title or "ACF before / after whitening", fontsize=10.5)
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=300)
    plt.close(fig)

    if plot_data_root and bundle_name:   # data-only CSV record (no replot JSON)
        root = Path(plot_data_root); root.mkdir(parents=True, exist_ok=True)
        rec = {"lag": lags}
        for lab, a_res, a_inn, *_ in rows:
            rec[f"{lab}_resid"] = np.asarray(a_res, float)[1:lag + 1]
            rec[f"{lab}_innov"] = np.asarray(a_inn, float)[1:lag + 1]
        pd.DataFrame(rec).to_csv(root / f"{bundle_name}.csv", index=False,
                                 encoding="utf-8-sig")


def _save_fig(fig, out_path: Path, vector: bool = False):
    out_path = Path(out_path); out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=300)
    if vector:
        for ext in (".pdf", ".svg"):
            fig.savefig(out_path.with_suffix(ext))
    plt.close(fig)


# ── DO manifest-driven panels (Okabe-Ito; draw into a Figure or SubFigure) ──
def _panel_a_iid(host, rows, lag=60, after_ylim=(-0.20, 0.10), heading=""):
    """(a) iid group before/after ACF. `rows`=[(label, acf_res, acf_inn, conf,
    mabsacf_res, mabsacf_inn, zone_note)]. After-column shares y so all four
    visibly collapse to ~0 (DO_1_2's MA over-correction lag-1 dip still shows);
    precise values via the mabsacf effect-size label."""
    axes = host.subplots(len(rows), 2, sharex=True, squeeze=False)
    lags = np.arange(1, lag + 1)
    for i, (lab, a_res, a_inn, conf, mab_r, mab_i, znote) in enumerate(rows):
        for j, (a, after) in enumerate([(a_res, False), (a_inn, True)]):
            ax = axes[i][j]
            ax.bar(lags, np.asarray(a, float)[1:lag + 1], color=OI["blue"],
                   width=0.9, linewidth=0)
            ax.axhline(0, color=OI["gray"], lw=0.6)
            ax.axhline(conf, color=OI["gray"], ls=":", lw=0.6)
            ax.axhline(-conf, color=OI["gray"], ls=":", lw=0.6)
            ax.grid(True, axis="y", alpha=0.25); ax.tick_params(labelsize=7)
            ax.set_ylim(*after_ylim) if after else ax.set_ylim(-0.1, 1.0)
            if i == 0:
                ax.set_title(["Before — residual e(t)",
                              "After — innovation η(t)"][j], fontsize=8.5)
            if j == 0:
                yl = lab + (f"\n({znote})" if znote else "")
                ax.set_ylabel(yl, rotation=0, ha="right", va="center", fontsize=8)
            if i == len(rows) - 1:
                ax.set_xlabel("lag (min)", fontsize=8)
            if after:
                ax.text(0.97, 0.95, f"mabsacf[1-10]: {mab_r:.2f}→{mab_i:.2f}",
                        transform=ax.transAxes, ha="right", va="top",
                        fontsize=6.5, color="#555555")
    if heading:
        host.suptitle(heading, fontsize=10)


def _panel_b_nearur(host, rows, heading=""):
    """(b) near-UR group: residual ACF slow decay (blue, neutral) + residual
    spectrum (loglog) with an f⁻² reference slope. `rows`=[(label, acf_res,
    freq_cph, power, n_eff_ratio)]."""
    R = len(rows)
    axes = host.subplots(R, 2, squeeze=False)
    for i, (lab, acf_r, freq, P, neff) in enumerate(rows):
        ax = axes[i][0]
        lags = np.arange(1, len(acf_r))
        ax.bar(lags, np.asarray(acf_r, float)[1:], color=OI["blue"], width=0.9,
               linewidth=0)
        ax.set_ylim(-0.1, 1.0); ax.grid(True, axis="y", alpha=0.25)
        ax.tick_params(labelsize=7)
        ax.set_ylabel(lab, rotation=0, ha="right", va="center", fontsize=8.5)
        ax.text(0.96, 0.92, f"near-UR red noise · robust_z\nn_eff/n≈{neff:.3f}",
                transform=ax.transAxes, ha="right", va="top", fontsize=6.3,
                color="#555555")
        if i == 0:
            ax.set_title("Residual e(t) ACF — slow monotone decay", fontsize=8.5)
        if i == R - 1:
            ax.set_xlabel("lag (min)", fontsize=8)
        ax2 = axes[i][1]
        f = np.asarray(freq, float); Pp = np.asarray(P, float)
        g = f > 0
        ax2.loglog(f[g], Pp[g], color=OI["spectrum"], lw=0.9)
        f0, P0 = f[g][1], Pp[g][1]
        ax2.loglog(f[g], P0 * (f[g] / f0) ** -2, color=OI["gray"], ls="--",
                   lw=0.8, label="f⁻² (red noise)")
        ax2.legend(fontsize=6, loc="upper right", frameon=False)
        ax2.grid(True, which="both", alpha=0.2); ax2.tick_params(labelsize=6.5)
        ax2.set_ylabel("power", fontsize=7)
        if i == 0:
            ax2.set_title("Residual spectrum — broadband, no dominant peak",
                          fontsize=8.5)
        if i == R - 1:
            ax2.set_xlabel("frequency (cycles/h)", fontsize=8)
    if heading:
        host.suptitle(heading, fontsize=10)


def _panel_c_floor(host, series, floor_thr=0.05, route_occ=0.70, heading=""):
    """(c) floor group: ECDF + near-floor occupancy-vs-threshold (blue/orange);
    route threshold as a vermillion alarm line. `series`={label: raw_array}."""
    axes = host.subplots(1, 2, squeeze=False)[0]
    cmap = {0: OI["blue"], 1: OI["orange"]}
    for k, lab in enumerate(series):
        arr = np.asarray(series[lab], float); arr = arr[~np.isnan(arr)]
        if len(arr) == 0:
            continue
        col = cmap[k % 2]
        v = np.sort(arr); y = np.arange(1, len(v) + 1) / len(v)
        axes[0].plot(v, y, color=col, lw=1.5, label=lab)
        thr = np.linspace(0, 0.5, 60); occ = [float((arr <= t).mean()) for t in thr]
        axes[1].plot(thr, occ, color=col, lw=1.5, label=lab)
        o = float((arr <= floor_thr).mean())
        axes[1].annotate(f"{o:.2f}", (floor_thr, o), color=col, fontsize=7.5,
                         xytext=(5, 0), textcoords="offset points", va="center")
    axes[0].axvline(floor_thr, color=OI["gray"], ls="--", lw=0.8)
    axes[0].set_xlim(-0.1, 1.5); axes[0].set_xlabel("DO (mg/L)", fontsize=8)
    axes[0].set_ylabel("ECDF", fontsize=8)
    axes[0].set_title("Value distribution (ECDF)", fontsize=8.5)
    axes[0].legend(fontsize=8); axes[0].grid(True, alpha=0.25)
    axes[0].tick_params(labelsize=7)
    axes[1].axvline(floor_thr, color=OI["gray"], ls="--", lw=0.8)
    axes[1].axhline(route_occ, color=OI["vermillion"], ls="--", lw=1.1)
    axes[1].text(0.34, route_occ + 0.02, f"route threshold {route_occ}",
                 color=OI["vermillion"], fontsize=7)
    axes[1].set_xlabel("floor threshold (mg/L)", fontsize=8)
    axes[1].set_ylabel("near-floor occupancy", fontsize=8)
    axes[1].set_title("Floor occupancy → floor/freeze routing", fontsize=8.5)
    axes[1].legend(fontsize=8); axes[1].grid(True, alpha=0.25)
    axes[1].tick_params(labelsize=7)
    if heading:
        host.suptitle(heading, fontsize=10)


def _panel_d_d7(host, do, positions, heading=""):
    """(d) D7: LEFT expected spatial profile (aerobic rise + post-anoxic drop,
    mean±IQR, blue/orange); RIGHT parallel-train 1#−2# difference distribution
    (median±IQR, the symmetry MONITOR — centred & tight = symmetric). `positions`
    = [(zone_label, chan_t1, chan_t2)]."""
    axes = host.subplots(1, 2, squeeze=False)[0]
    n = len(positions); x = np.arange(n); w = 0.38
    labels = [p[0] for p in positions]
    for col, off, key in [(OI["blue"], -w / 2, 1), (OI["orange"], +w / 2, 2)]:
        meds, lo, hi = [], [], []
        for p in positions:
            a = np.asarray(do[p[key]], float); a = a[~np.isnan(a)]
            if len(a):
                m = float(np.median(a)); q1, q3 = np.percentile(a, [25, 75])
            else:
                m = q1 = q3 = np.nan
            meds.append(m); lo.append(max(0.0, m - q1)); hi.append(max(0.0, q3 - m))
        axes[0].bar(x + off, meds, w, yerr=[lo, hi], capsize=2, color=col,
                    label=f"train {key}#", error_kw=dict(lw=0.7, ecolor="#555555"))
    axes[0].set_xticks(x); axes[0].set_xticklabels(labels, fontsize=7)
    axes[0].set_ylabel("DO (mg/L), median ± IQR", fontsize=8)
    axes[0].set_title("Expected spatial profile — aerobic rise + post-anoxic drop",
                      fontsize=8)
    axes[0].legend(fontsize=8); axes[0].grid(True, axis="y", alpha=0.25)
    axes[0].tick_params(labelsize=7)
    axes[0].text(0.03, 0.95, "post-anoxic floor → monitored in (c)",
                 transform=axes[0].transAxes, fontsize=6.8, color="#555555")
    meds, lo2, hi2 = [], [], []
    for p in positions:
        d = np.asarray(do[p[1]], float) - np.asarray(do[p[2]], float)
        d = d[~np.isnan(d)]
        med = float(np.median(d)) if len(d) else np.nan
        q1, q3 = (np.percentile(d, [25, 75]) if len(d) else (med, med))
        meds.append(med); lo2.append(max(0.0, med - q1)); hi2.append(max(0.0, q3 - med))
    axes[1].errorbar(x, meds, yerr=[lo2, hi2], fmt="o", color=OI["blue"],
                     capsize=3, lw=1.0, ms=4)
    axes[1].axhline(0, color=OI["gray"], ls="--", lw=0.8)
    axes[1].set_xticks(x); axes[1].set_xticklabels(labels, fontsize=7)
    axes[1].set_ylabel("1# − 2#  (mg/L, median ± IQR)", fontsize=8)
    axes[1].set_title("Parallel-train difference — the symmetry monitor",
                      fontsize=8)
    axes[1].grid(True, axis="y", alpha=0.25); axes[1].tick_params(labelsize=7)
    axes[1].text(0.03, 0.08, "centred & tight = symmetric;\ndrift/jump = "
                 "differential fault (raw series)", transform=axes[1].transAxes,
                 fontsize=6.6, color="#555555")
    if heading:
        host.suptitle(heading, fontsize=10)


def do_panel_iid(rows, out_path, lag=60, vector=False):
    fig = plt.figure(figsize=(8.8, 1.15 * len(rows) + 1.0), layout="constrained")
    _panel_a_iid(fig, rows, lag=lag, heading="Whitened DO channels (iid) — "
                 "ACF before/after whitening (lag 60)")
    _save_fig(fig, out_path, vector)


def do_panel_nearur(rows, out_path, vector=False):
    fig = plt.figure(figsize=(8.8, 1.35 * len(rows) + 1.0), layout="constrained")
    _panel_b_nearur(fig, rows, heading="Near-unit-root DO channels — "
                    "un-whitenable (NOT a whitening failure)")
    _save_fig(fig, out_path, vector)


def do_panel_floor(series, out_path, floor_thr=0.05, route_occ=0.70, vector=False):
    fig = plt.figure(figsize=(9.2, 3.6), layout="constrained")
    _panel_c_floor(fig, series, floor_thr, route_occ,
                   heading="Post-anoxic DO — floor occupancy (censoring, not dynamics)")
    _save_fig(fig, out_path, vector)


def do_panel_d7(do, positions, out_path, vector=False):
    fig = plt.figure(figsize=(9.6, 3.8), layout="constrained")
    _panel_d_d7(fig, do, positions, heading="D7 cross-channel redundancy "
                "monitors the un-whitenable DO channels")
    _save_fig(fig, out_path, vector)


def do_composite(rows_a, rows_b, series_c, do_d, positions_d, out_path,
                 lag_a=60, floor_thr=0.05, route_occ=0.70, vector=True):
    """Composite (a)–(d): one figure, four stacked panel-groups, each keeping
    its own axes. Exported as PNG + vector (PDF/SVG)."""
    fig = plt.figure(figsize=(9.6, 15.8), layout="constrained")
    sf = fig.subfigures(4, 1, height_ratios=[4.2, 3.2, 2.6, 2.9])
    _panel_a_iid(sf[0], rows_a, lag=lag_a,
                 heading="(a) Whitened DO (iid) — ACF before/after whitening (lag 60)")
    _panel_b_nearur(sf[1], rows_b, heading="(b) Near-unit-root DO (un-whitenable)"
                    " — residual ACF (lag 120) + spectrum")
    _panel_c_floor(sf[2], series_c, floor_thr, route_occ,
                   heading="(c) Post-anoxic DO — floor occupancy (censoring, not dynamics)")
    _panel_d_d7(sf[3], do_d, positions_d, heading="(d) D7 cross-channel "
                "redundancy — differential faults (common-mode drift → D5 anchor)")
    fig.suptitle("DO channels — manifest-driven handling & monitoring by class",
                 fontsize=12)
    _save_fig(fig, out_path, vector)


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
