"""make_d2_figures.py — D2 Temporal Continuity & Information Availability
SCI-quality figures (V2 — nature-skills spec)
  Primary output : SVG (editable vector)
  Secondary output: PNG 300 DPI
  10 figures: D2_Fig01 – D2_Fig10

Prerequisites:
    python run_d2_pipeline.py   →  produces artifacts/d2_state.pkl

Outputs (artifacts/figures/):
  D2_Fig01_overview_heatmap.{png,svg}
  D2_Fig02_subscore_violins.{png,svg}
  D2_Fig03_missing_rate_timeline.{png,svg}
  D2_Fig04_gap_severity.{png,svg}
  D2_Fig05_freeze_availability.{png,svg}
  D2_Fig06_mapping_curves.{png,svg}
  D2_Fig07_availability_profile.{png,svg}
  D2_Fig08_d1_d2_relationship.{png,svg}
  D2_Fig09_veto_analysis.{png,svg}
  D2_Fig10_calibration_summary.{png,svg}
"""
from __future__ import annotations
import pickle
import warnings
import traceback
from pathlib import Path

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import matplotlib
import matplotlib as mpl
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import matplotlib.ticker as mticker
import matplotlib.dates as mdates
from matplotlib.gridspec import GridSpec
from matplotlib.colors import LinearSegmentedColormap
from publication_style import (
    PANEL_FONTSIZE,
    PANEL_X,
    PANEL_Y,
    PALETTE as SHARED_PALETTE,
    TITLE_PAD,
    configure_publication_style,
    finalize_figure,
)

# ── 强制 rcParams（nature-skills 三行必选）────────────────────────────────────
mpl.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans", "Liberation Sans"],
    "font.size": 7,
    "svg.fonttype": "none",
    "pdf.fonttype": 42,
})
configure_publication_style()

# ── 路径 ─────────────────────────────────────────────────────────────────────
_ROOT = Path(__file__).parent
_D1   = _ROOT.parent / "D1 Sensor health"
FIGS  = _ROOT / "artifacts" / "figures"
FIGS.mkdir(parents=True, exist_ok=True)
DATA  = _ROOT / "artifacts" / "data"
DATA.mkdir(parents=True, exist_ok=True)

# ── PALETTE（nature-skills api.md 完整版）────────────────────────────────────
PAL = {
    "blue_main":      "#0F4D92",
    "blue_secondary": "#3775BA",
    "blue_light":     "#A8C8E8",
    "green_1":        "#DDF3DE",
    "green_2":        "#AADCA9",
    "green_3":        "#8BCF8B",
    "red_1":          "#F6CFCB",
    "red_2":          "#E9A6A1",
    "red_strong":     "#B64342",
    "neutral_light":  "#CFCECE",
    "neutral_mid":    "#767676",
    "neutral_dark":   "#4D3D3D",
    "neutral_black":  "#272727",
    "gold":           "#FFD500",
    "teal":           "#42949E",
    "violet":         "#9A4D8E",
    "magenta":        "#EA84DD",
    "orange":         "#E07B39",
    "improve":        "#2E9E44",  # 方向色：改善
    "degrade":        "#E53935",  # 方向色：退化
}

# ── 尺寸与字号（密集多面板规范）──────────────────────────────────────────────
PAL.update(SHARED_PALETTE)

FS   = 8        # 正文字号（密集多面板）
TS   = 9        # 子图标题字号
TK   = 7        # 刻度标签字号
LWM  = 1.0      # 主线宽
LWA  = 0.6      # 辅助线宽
LW_SP = 0.8     # Unified publication axis weight (pt)
DPI  = 600      # High-resolution review raster; SVG/PDF remain vector

# ── 语义配色 ─────────────────────────────────────────────────────────────────
C_QTI = PAL["blue_main"]
C_QGS = PAL["orange"]
C_QFA = PAL["violet"]
C_DO  = PAL["blue_main"]
C_ORP = PAL["red_strong"]

GRADE_COLOR = {
    "A": PAL["improve"],
    "B": PAL["teal"],
    "C": PAL["gold"],
    "D": PAL["orange"],
    "E": PAL["red_strong"],
}

GRADE_BANDS = [
    (4.5, 5.0, "#DDF3DE", "A"),
    (3.5, 4.5, "#EEF8EE", "B"),
    (2.5, 3.5, "#FFF8E1", "C"),
    (1.5, 2.5, "#FDECEA", "D/E"),
]

# Per-channel colours (14 ch: DO×8 + ORP×6)
_DO_HUE  = [PAL["blue_main"], PAL["blue_secondary"],
             PAL["teal"],      PAL["neutral_dark"]]
_ORP_HUE = [PAL["red_strong"], PAL["orange"], PAL["violet"]]
CH_COLORS = _DO_HUE + _DO_HUE + _ORP_HUE + _ORP_HUE
CH_LSTYLE = ["-"] * 4 + ["--"] * 4 + ["-"] * 3 + ["--"] * 3

# Engineering defaults (mirrors run_d2_pipeline.ENG_DEFAULTS)
ENG = {
    "missing_rate_breaks":    [0.005, 0.02,  0.05,  0.15],
    "irregular_rate_breaks":  [0.005, 0.02,  0.05,  0.10],
    "L_max_breaks_min":       [5,     15,    60,    360],
    "gap_count_breaks":       [2,     5,     15,    40],
    "info_empty_breaks":      [0.02,  0.08,  0.20,  0.50],
}


# ── 通用辅助函数 ──────────────────────────────────────────────────────────────

def apply_publication_style(ax, font_size: int = FS,
                             axes_linewidth: float = LW_SP) -> None:
    """Apply nature-skills publication style to an axes object."""
    ax.spines["right"].set_visible(False)
    ax.spines["top"].set_visible(False)
    ax.spines["left"].set_linewidth(axes_linewidth)
    ax.spines["bottom"].set_linewidth(axes_linewidth)
    ax.tick_params(axis="both", which="major",
                   labelsize=font_size - 1,
                   length=4, width=axes_linewidth,
                   direction="out")
    ax.yaxis.get_label().set_fontsize(font_size)
    ax.xaxis.get_label().set_fontsize(font_size)
    ax.title.set_fontsize(font_size + 1)
    leg = ax.get_legend()
    if leg is not None:
        leg.get_frame().set_visible(False)


def add_panel_label(ax, label: str, x: float = PANEL_X, y: float = PANEL_Y,
                    fontsize: float = PANEL_FONTSIZE,
                    fontweight: str = "bold") -> None:
    """Add a bold lowercase panel label to an axes."""
    normalized = label.strip().strip("()").lower()
    ax.text(x, y, f"({normalized})", transform=ax.transAxes,
            fontsize=fontsize, fontweight=fontweight,
            va="bottom", ha="right", clip_on=False,
            bbox={"facecolor": "white", "edgecolor": "none", "pad": 0.15})


def luminance(hex_color: str) -> float:
    """Perceived luminance of a hex colour (0 = black, 1 = white)."""
    c = hex_color.lstrip("#")
    r, g, b = int(c[0:2], 16) / 255, int(c[2:4], 16) / 255, int(c[4:6], 16) / 255
    return 0.299 * r + 0.587 * g + 0.114 * b


def save_fig(fig, name: str, pad: float = 2.0,
             rect: tuple[float, float, float, float] | None = None) -> None:
    """Export review PNG plus editable SVG/PDF publication masters."""
    layout_rect = rect
    if fig._suptitle is not None:
        fig._suptitle.set_y(0.995)
        layout_rect = layout_rect or (0, 0, 1, 0.97)
    if layout_rect is not None:
        fig.tight_layout(pad=pad, rect=layout_rect)
    else:
        fig.tight_layout(pad=pad)
    finalize_figure(fig)
    for fmt in ("png", "svg", "pdf"):
        p = FIGS / f"{name}.{fmt}"
        fig.savefig(p, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"  [saved] {name}.png + .svg + .pdf")


def load_state() -> dict:
    pkl = _ROOT / "artifacts" / "d2_state.pkl"
    if not pkl.exists():
        raise FileNotFoundError(
            f"State not found: {pkl}\nRun run_d2_pipeline.py first.")
    with open(pkl, "rb") as f:
        s = pickle.load(f)
    print(f"  State: {len(s['scored_channels'])} channels | "
          f"run={s.get('run_id', 'N/A')}")
    return s


def _wide(d: dict, channels: list, col: str) -> pd.DataFrame:
    frames = {}
    for ch in channels:
        if ch in d and col in d[ch].columns:
            frames[ch] = d[ch][col]
    return pd.DataFrame(frames)


def _score_cmap() -> LinearSegmentedColormap:
    colors = [
        PAL["red_strong"], PAL["red_2"], PAL["neutral_light"],
        PAL["blue_light"], PAL["blue_main"],
    ]
    return LinearSegmentedColormap.from_list("d2_score", colors, N=256)


def _piecewise(x: np.ndarray, breaks: list) -> np.ndarray:
    """Reconstruct piecewise 1–5 score from breaks list."""
    s = np.ones_like(x, dtype=float)
    b = breaks
    for s_hi, s_lo, lo, hi in [(5, 4, b[0], b[1]),
                                (4, 3, b[1], b[2]),
                                (3, 2, b[2], b[3])]:
        m = (x > lo) & (x <= hi)
        s[m] = s_hi - (s_hi - s_lo) * (x[m] - lo) / (hi - lo)
    s[x <= b[0]] = 5.0
    s[x >  b[3]] = 1.0
    return np.clip(s, 1.0, 5.0)


# ─────────────────────────────────────────────────────────────────────────────
# Fig 01: D2 Overview Heatmap
# ─────────────────────────────────────────────────────────────────────────────

def fig01_overview_heatmap(state: dict):
    channels = state["scored_channels"]
    all_D2   = state["all_D2"]

    d2w = _wide(all_D2, channels, "D2_total")
    d2d = d2w.resample("D").mean()
    mat = d2d[channels].T.values   # (14, n_days)

    fig, ax = plt.subplots(figsize=(7.2, 3.8))
    cmap = _score_cmap()
    ax.imshow(mat, aspect="auto", cmap=cmap, vmin=1, vmax=5,
              origin="upper", interpolation="nearest")

    n = len(d2d)
    periods = d2d.index.to_period("M")
    month_starts = np.r_[0, np.flatnonzero(periods[1:] != periods[:-1]) + 1]
    month_step = max(1, int(np.ceil(len(month_starts) / 7)))
    tks = month_starts[::month_step]
    ax.set_xticks(tks)
    ax.set_xticklabels(d2d.index[tks].strftime("%Y-%m"),
                       rotation=35, ha="right", fontsize=TK)

    ax.set_yticks(range(len(channels)))
    ax.set_yticklabels(channels, fontsize=TK)
    ax.tick_params(axis="both", length=3, width=1.0, direction="out")

    # Group separator lines
    for y_sep in [3.5, 7.5, 10.5]:
        ax.axhline(y=y_sep, color="white", lw=1.5)
    for y_text, label in [(1.5, "DO-P1"), (5.5, "DO-P2"),
                           (9.0, "ORP-P1"), (12.0, "ORP-P2")]:
        ax.text(
            n - 1.5, y_text, label, fontsize=TK,
            color=PAL["neutral_black"], ha="right", va="center",
            weight="bold",
            bbox={
                "boxstyle": "round,pad=0.18",
                "facecolor": "white",
                "edgecolor": PAL["neutral_mid"],
                "linewidth": 0.45,
                "alpha": 0.86,
            },
        )

    # Colorbar
    sm = plt.cm.ScalarMappable(cmap=cmap,
                                norm=plt.Normalize(vmin=1, vmax=5))
    sm.set_array([])
    cbar = fig.colorbar(sm, ax=ax, fraction=0.03, pad=0.01, aspect=30)
    cbar.set_ticks([1, 2, 3, 4, 5])
    cbar.set_ticklabels(["1", "2", "3", "4", "5"], fontsize=TK)
    cbar.set_label("D2 score", fontsize=FS)
    cbar.ax.tick_params(length=3, width=1.0, direction="out")
    for thr in [1.5, 2.5, 3.5, 4.5]:
        cbar.ax.axhline(thr, color="white", lw=0.8)

    ax.spines["right"].set_visible(False)
    ax.spines["top"].set_visible(False)
    ax.spines["left"].set_linewidth(LW_SP)
    ax.spines["bottom"].set_linewidth(LW_SP)

    ax.set_title("D2 Temporal Continuity Score — Daily Mean (14 Channels)",
                 fontsize=TS, pad=6)
    ax.set_xlabel("Date", fontsize=FS)
    ax.set_ylabel("Sensor", fontsize=FS)

    add_panel_label(ax, "A")
    save_fig(fig, "D2_Fig01_overview_heatmap")


# ─────────────────────────────────────────────────────────────────────────────
# Fig 02: Sub-score Violin Decomposition
# ─────────────────────────────────────────────────────────────────────────────

def fig02_subscore_violins(state: dict):
    channels = state["scored_channels"]
    subs_all = state["subs_all"]

    sub_cols = [("Q_TI", C_QTI, "Q$_{TI}$  (Temporal Integrity)"),
                ("Q_GS", C_QGS, "Q$_{GS}$  (Gap Severity)"),
                ("Q_FA", C_QFA, "Q$_{FA}$  (Freeze / Availability)")]

    fig, axes = plt.subplots(1, 3, figsize=(7.2, 4.25), sharey=False)
    fig.subplots_adjust(wspace=0.24)

    for ax, (col, color, title), lbl in zip(axes, sub_cols, "ABC"):
        data = [subs_all[ch][col].dropna().values
                for ch in channels
                if ch in subs_all and col in subs_all[ch].columns]
        positions = list(range(len(data)))

        parts = ax.violinplot(data, positions=positions, widths=0.72,
                              showmedians=True, showextrema=False)
        for pc in parts["bodies"]:
            pc.set_facecolor(color)
            pc.set_alpha(0.45)
            pc.set_edgecolor("none")
        parts["cmedians"].set_color(PAL["neutral_black"])
        parts["cmedians"].set_linewidth(1.0)

        # IQR box overlay
        for i, d in enumerate(data):
            if len(d) < 4:
                continue
            q25, q75 = np.percentile(d, [25, 75])
            ax.plot([i - 0.12, i + 0.12], [q25, q25], "-",
                    color=PAL["neutral_dark"], lw=0.7)
            ax.plot([i - 0.12, i + 0.12], [q75, q75], "-",
                    color=PAL["neutral_dark"], lw=0.7)
            ax.plot([i, i], [q25, q75], "-",
                    color=PAL["neutral_dark"], lw=0.7)

        # Grade threshold reference lines
        for thr, g in [(4.5, "A"), (3.5, "B"), (2.5, "C"), (1.5, "D")]:
            ax.axhline(thr, color=GRADE_COLOR[g], lw=LWA, ls="--", alpha=0.70)

        # DO / ORP group separator
        ax.axvline(x=7.5, color=PAL["neutral_mid"], lw=0.6, ls=":", alpha=0.6)
        ax.text(3.5, 5.15, "DO",  ha="center", fontsize=TK - 1,
                color=PAL["neutral_mid"])
        ax.text(10.5, 5.15, "ORP", ha="center", fontsize=TK - 1,
                color=PAL["neutral_mid"])

        ax.set_xticks(positions)
        ax.set_xticklabels(channels, rotation=90, ha="center",
                           fontsize=TK - 1.2)
        ax.set_ylim(0.8, 5.35)
        ax.set_yticks([1, 2, 3, 4, 5])
        apply_publication_style(ax, font_size=FS)
        ax.set_title(title, fontsize=TS - 0.5, pad=TITLE_PAD)
        ax.set_ylabel("Score (1 – 5)", fontsize=FS)
        ax.tick_params(axis="y", labelleft=True)
        add_panel_label(ax, lbl)

    # Shared grade legend on last panel
    handles = [plt.Line2D([0], [0], color=GRADE_COLOR[g], lw=1.2, ls="--",
                           label=f"Grade {g}") for g in ["A", "B", "C", "D"]]
    fig.legend(
        handles=handles, fontsize=TK - 0.5,
        loc="upper center", bbox_to_anchor=(0.5, 0.925),
        ncol=4, handlelength=1.2, columnspacing=1.0,
        frameon=False,
    )

    fig.suptitle("Sub-score Decomposition by Sensor Channel",
                 fontsize=TS, y=1.02)
    save_fig(
        fig, "D2_Fig02_subscore_violins", pad=1.5,
        rect=(0, 0, 1, 0.89),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Fig 03: Missing Rate Timeline
# ─────────────────────────────────────────────────────────────────────────────

def fig03_missing_rate(state: dict):
    channels = state["scored_channels"]
    subs_all = state["subs_all"]

    do_chs  = [c for c in channels if c.startswith("DO")]
    orp_chs = [c for c in channels if c.startswith("ORP")]
    do_colors  = _DO_HUE  + _DO_HUE
    do_ls      = ["-"] * 4 + ["--"] * 4
    orp_colors = _ORP_HUE + _ORP_HUE
    orp_ls     = ["-"] * 3 + ["--"] * 3

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(7.2, 4.5), sharex=True)
    fig.subplots_adjust(hspace=0.32)

    def _draw(ax, chs, group, colors, lstyles, panel_label):
        for ch, c, ls in zip(chs, colors, lstyles):
            if ch not in subs_all:
                continue
            mr = subs_all[ch]["missing_rate"].resample("D").mean() * 100
            ax.plot(mr.index, mr.values, color=c, ls=ls, lw=LWM,
                    alpha=0.85, label=ch)
        for thr, lbl in [(0.5, "0.5 %"), (2.0, "2 %"), (5.0, "5 %")]:
            ax.axhline(thr, color=PAL["neutral_mid"], lw=0.4,
                       ls=":", alpha=0.55)
            ax.text(1.0, thr, f" {lbl}",
                    fontsize=TK - 2, va="center",
                    ha="left", color=PAL["neutral_mid"],
                    transform=ax.get_yaxis_transform())
        ax.set_ylabel("Missing rate (%)", fontsize=FS)
        ax.set_title(f"{group} — Daily Mean Missing Rate",
                     fontsize=TS, pad=4)
        ax.tick_params(axis="both", length=3)
        ax.legend(ncol=4, fontsize=TK - 1.5, loc="upper left",
                  handlelength=1.0, columnspacing=0.5, frameon=False)
        ax.set_ylim(bottom=0)
        apply_publication_style(ax, font_size=FS)
        add_panel_label(ax, panel_label, x=-0.08)

    _draw(ax1, do_chs,  "DO",  do_colors,  do_ls,  "A")
    _draw(ax2, orp_chs, "ORP", orp_colors, orp_ls, "B")

    ax2.xaxis.set_major_locator(mticker.MaxNLocator(8))
    ax2.set_xlabel("Date", fontsize=FS)
    for lbl in ax2.get_xticklabels():
        lbl.set_rotation(30)
        lbl.set_ha("right")

    fig.suptitle("Missing Rate Timeline — DO & ORP Channels",
                 fontsize=TS, y=1.02)
    save_fig(fig, "D2_Fig03_missing_rate_timeline")


# ─────────────────────────────────────────────────────────────────────────────
# Fig 04: Gap Severity Analysis
# ─────────────────────────────────────────────────────────────────────────────

def fig04_gap_severity(state: dict):
    gap_df   = state["gap_df"]
    subs_all = state["subs_all"]
    channels = state["scored_channels"]

    fig = plt.figure(figsize=(7.2, 3.8))
    gs  = GridSpec(1, 2, figure=fig, wspace=0.36)
    ax1 = fig.add_subplot(gs[0])
    ax2 = fig.add_subplot(gs[1])

    # ── Panel A: gap duration histogram ──────────────────────────────────
    gap_type_colors = {
        "short_gap":    PAL["improve"],
        "medium_gap":   PAL["teal"],
        "long_gap":     PAL["orange"],
        "critical_gap": PAL["red_strong"],
    }
    durations = gap_df["duration_min"].dropna()
    if "gap_type" in gap_df.columns and len(durations) and durations.max() > 0:
        for gtype, color in gap_type_colors.items():
            sub = gap_df.loc[gap_df["gap_type"] == gtype,
                              "duration_min"].dropna()
            if len(sub):
                bins = np.logspace(np.log10(max(0.5, sub.min())),
                                   np.log10(sub.max() + 1), 18)
                ax1.hist(sub, bins=bins, color=color, alpha=0.72,
                         label=gtype.replace("_", " ").title(),
                         edgecolor="none")
    elif len(durations) and durations.max() > 0:
        bins = np.logspace(np.log10(max(0.5, durations.min())),
                           np.log10(durations.max() + 1), 25)
        ax1.hist(durations, bins=bins, color=C_DO, alpha=0.7, edgecolor="none")

    ax1.set_xscale("log")
    for xv in [5, 60, 360]:
        ax1.axvline(xv, color=PAL["neutral_mid"], lw=0.5, ls=":", alpha=0.6)
    ax1.set_xlabel("Gap duration (min)", fontsize=FS)
    ax1.set_ylabel("Count", fontsize=FS)
    ax1.set_title("Gap Duration Distribution", fontsize=TS, pad=4)
    ax1.legend(fontsize=TK - 0.5, handlelength=1.0, frameon=False)
    apply_publication_style(ax1, font_size=FS)
    add_panel_label(ax1, "A")

    # ── Panel B: daily max L_max ──────────────────────────────────────────
    lmax_df  = pd.DataFrame({ch: subs_all[ch]["L_max_min"]
                              for ch in channels if ch in subs_all})
    lmax_max  = lmax_df.resample("D").max().max(axis=1)
    lmax_mean = lmax_df.resample("D").mean().mean(axis=1)

    ax2.fill_between(lmax_max.index, lmax_max.values,
                     alpha=0.18, color=PAL["orange"])
    ax2.plot(lmax_max.index,  lmax_max.values,
             color=PAL["orange"],    lw=LWM, label="Max across channels")
    ax2.plot(lmax_mean.index, lmax_mean.values,
             color=PAL["blue_main"], lw=LWA, ls="--", label="Channel mean")

    for yv in [5, 60, 360]:
        ax2.axhline(yv, color=PAL["neutral_mid"], lw=0.4, ls=":", alpha=0.55)

    ax2.set_xlabel("Date", fontsize=FS)
    ax2.set_ylabel("L$_{max}$ (min)", fontsize=FS)
    ax2.set_title("Maximum Consecutive Gap — Daily", fontsize=TS, pad=4)
    ax2.legend(fontsize=TK - 0.5, handlelength=1.0, frameon=False)
    ax2.xaxis.set_major_locator(mticker.MaxNLocator(5))
    for lbl in ax2.get_xticklabels():
        lbl.set_rotation(30)
        lbl.set_ha("right")
    apply_publication_style(ax2, font_size=FS)
    add_panel_label(ax2, "B")

    fig.suptitle("Gap Severity Analysis", fontsize=TS, y=1.02)
    save_fig(fig, "D2_Fig04_gap_severity")


# ─────────────────────────────────────────────────────────────────────────────
# Fig 05: Freeze–Availability Events
# ─────────────────────────────────────────────────────────────────────────────

def fig05_freeze_availability(state: dict):
    channels = state["scored_channels"]
    subs_all = state["subs_all"]
    floor_chs = ["DO_1_4", "DO_2_4"]
    standard_do = [c for c in channels if c.startswith("DO") and c not in floor_chs]
    standard_orp = [c for c in channels if c.startswith("ORP")]

    fig, axes = plt.subplots(2, 2, figsize=(7.2, 5.3))
    ax1, ax2, ax3, ax4 = axes.ravel()
    fig.subplots_adjust(hspace=0.48, wspace=0.34)

    # (a) Long-term evidence separation for post-anoxic DO channels.
    metrics = [
        ("floor_occupancy", "Floor\noccupancy", PAL["blue_light"]),
        ("resolution_limited", "Resolution\nlimited", PAL["teal"]),
        ("sensor_freeze_cov", "Hard sensor\nfreeze", PAL["red_strong"]),
        ("info_empty_cov", "QFA\nunavailable", PAL["orange"]),
    ]
    x = np.arange(len(floor_chs)); width = 0.18
    profile_rows = []
    for j, (metric, label, color) in enumerate(metrics):
        vals = [float(subs_all[ch][metric].mean() * 100) for ch in floor_chs]
        xpos = x + (j - 1.5) * width
        ax1.bar(xpos, vals, width=width, color=color,
                edgecolor=PAL["neutral_dark"], linewidth=0.35,
                label=label.replace("\n", " "))
        for xp, value in zip(xpos, vals):
            precision = 2 if value < 1 else 1
            ax1.text(xp, max(value + 1.2, 1.2), f"{value:.{precision}f}",
                     ha="center", va="bottom", fontsize=TK - 1,
                     color=PAL["neutral_dark"], rotation=90 if value < 1 else 0)
        for ch, value in zip(floor_chs, vals):
            profile_rows.append({"sensor_id": ch, "metric": metric, "mean_pct": value})
    ax1.set_xticks(x)
    ax1.set_xticklabels([c.replace("_", " ") for c in floor_chs])
    ax1.set_ylabel("Time coverage (%)")
    ax1.set_ylim(0, 105)
    ax1.set_title("Post-anoxic evidence separation", pad=4)
    ax1.legend(loc="upper right", fontsize=TK - 1, ncol=2,
               handlelength=0.9, columnspacing=0.7)
    apply_publication_style(ax1)
    add_panel_label(ax1, "a", x=-0.12)

    # (b) Floor occupancy and resolution limitation remain visible diagnostics.
    ch_colors = {"DO_1_4": PAL["blue_main"], "DO_2_4": PAL["teal"]}
    daily_floor = {}
    for ch in floor_chs:
        daily_floor[f"{ch}_floor"] = subs_all[ch]["floor_occupancy"].resample("D").mean() * 100
        daily_floor[f"{ch}_resolution"] = subs_all[ch]["resolution_limited"].resample("D").mean() * 100
        ax2.plot(daily_floor[f"{ch}_floor"].index,
                 daily_floor[f"{ch}_floor"].values, color=ch_colors[ch], lw=1.0,
                 label=f"{ch.replace('_', ' ')} floor")
        ax2.plot(daily_floor[f"{ch}_resolution"].index,
                 daily_floor[f"{ch}_resolution"].values, color=ch_colors[ch], lw=0.9,
                 ls="--", label=f"{ch.replace('_', ' ')} limited")
    ax2.set_ylabel("Daily coverage (%)")
    ax2.set_ylim(0, 105)
    ax2.set_title("Process floor vs limited resolution", pad=4)
    apply_publication_style(ax2)
    leg2 = ax2.legend(loc="lower left", fontsize=TK - 1, ncol=2,
                      handlelength=1.4, columnspacing=0.7,
                      frameon=True, framealpha=0.68, facecolor="white",
                      edgecolor="none")
    leg2.set_zorder(10)
    add_panel_label(ax2, "b", x=-0.12)

    # (c) Only production QFA evidence can activate freeze_severe.
    daily_qfa = {}
    for ch in floor_chs:
        daily_qfa[ch] = subs_all[ch]["info_empty_cov"].resample("D").mean() * 100
        ax3.plot(daily_qfa[ch].index, daily_qfa[ch].values,
                 color=ch_colors[ch], lw=1.0, label=ch.replace("_", " "))
    for thr in (2.0, 8.0, 20.0):
        ax3.axhline(thr, color=PAL["neutral_mid"], lw=0.45, ls=":", alpha=0.65)
    ymax = max(22.0, float(pd.DataFrame(daily_qfa).quantile(0.995).max() * 1.15))
    ax3.set_ylim(0, min(100, ymax))
    ax3.set_ylabel("QFA unavailable (%)")
    ax3.set_title("Hard QFA evidence (6 h window)", pad=4)
    ax3.legend(loc="upper left", fontsize=TK - 1, ncol=2, handlelength=1.2)
    apply_publication_style(ax3)
    add_panel_label(ax3, "c", x=-0.12)

    # (d) Standard channels retain the established information-empty route.
    standard_daily = {}
    for label, chs, color in (("Standard DO", standard_do, C_DO),
                              ("ORP", standard_orp, C_ORP)):
        frame = pd.DataFrame({ch: subs_all[ch]["info_empty_cov"] for ch in chs}).resample("D").mean() * 100
        median = frame.median(axis=1)
        q25, q75 = frame.quantile(0.25, axis=1), frame.quantile(0.75, axis=1)
        ax4.fill_between(median.index, q25.values, q75.values, color=color, alpha=0.15)
        ax4.plot(median.index, median.values, color=color, lw=1.0, label=label)
        standard_daily[f"{label}_median"] = median
        standard_daily[f"{label}_q25"] = q25
        standard_daily[f"{label}_q75"] = q75
    ax4.set_ylim(bottom=0)
    ax4.set_ylabel("Info-empty (%)")
    ax4.set_title("Standard-route channel burden", pad=4)
    apply_publication_style(ax4)
    ax4.legend(loc="upper left", fontsize=TK - 1, ncol=2, handlelength=1.2,
               frameon=True, framealpha=0.68, facecolor="white",
               edgecolor="none")
    add_panel_label(ax4, "d", x=-0.12)

    for ax in (ax2, ax3, ax4):
        ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b"))
        ax.set_xlabel("Date")

    with pd.ExcelWriter(DATA / "D2_Fig05_source_data.xlsx", engine="openpyxl") as writer:
        pd.DataFrame(profile_rows).to_excel(writer, sheet_name="panel_a_profile", index=False)
        pd.DataFrame(daily_floor).to_excel(writer, sheet_name="panel_b_floor_daily")
        pd.DataFrame(daily_qfa).to_excel(writer, sheet_name="panel_c_qfa_daily")
        pd.DataFrame(standard_daily).to_excel(writer, sheet_name="panel_d_standard_daily")

    fig.suptitle("Process-floor diagnostics and production availability evidence",
                 fontsize=TS, y=1.02)
    save_fig(fig, "D2_Fig05_freeze_availability", pad=1.4)


# ─────────────────────────────────────────────────────────────────────────────
# Fig 06: Piecewise Mapping Curves
# ─────────────────────────────────────────────────────────────────────────────

def fig06_mapping_curves(state: dict):
    mapping = state["mapping_df"]
    labels = {
        "missing_rate": ("Missing rate", True),
        "duplicate_rate": ("Duplicate rate", True),
        "out_of_order": ("Out-of-order rate", True),
        "irregular_rate": ("Irregular rate", True),
        "L_max_min": ("L$_{max}$ (min)", False),
        "P95_gap_min": ("P95 gap (min)", False),
        "gap_run_count": ("Gap count", False),
        "info_empty_cov": ("QFA unavailable coverage", True),
    }
    sub_color = {"Q_TI": C_QTI, "Q_GS": C_QGS, "Q_FA": C_QFA}
    metrics = []
    piecewise_rows = mapping[mapping["mapping_type"] == "piecewise_linear"]
    for _, row in piecewise_rows.iterrows():
        metric = row["input_metric"]
        label, pct = labels.get(metric, (metric, False))
        breaks = [row[f"break_{i}"] for i in range(1, 5)]
        metrics.append((label, breaks, row["subscore_name"], sub_color[row["subscore_name"]], pct))

    # Zone colours: score 5→1 (best to worst)
    zone_clr = [PAL["green_1"], PAL["green_2"], PAL["gold"],
                PAL["red_2"],   PAL["red_1"]]

    ncols = 3
    fig, axes = plt.subplots(3, ncols, figsize=(7.2, 6.7))
    fig.subplots_adjust(hspace=0.62, wspace=0.44)
    axes_flat = axes.flatten()

    for i, (label, breaks, sub_lbl, color, pct) in enumerate(metrics):
        ax    = axes_flat[i]
        b     = breaks
        scale = 100.0 if pct else 1.0
        x_raw = np.linspace(0, b[3] * 1.6, 600)
        y     = _piecewise(x_raw, b)
        x_d   = x_raw * scale

        # Score-zone background
        bds = [0, b[0]*scale, b[1]*scale, b[2]*scale, b[3]*scale, b[3]*scale*1.6]
        for zi in range(5):
            ax.axvspan(bds[zi], bds[zi+1], alpha=0.12, color=zone_clr[zi])

        ax.plot(x_d, y, color=color, lw=LWM)
        for bk, sc in zip(b, [5, 4, 3, 2]):
            ax.plot(bk * scale, sc, "o", color=color, ms=3.5, zorder=5)
            ax.axvline(bk * scale, color=PAL["neutral_mid"],
                       lw=0.4, ls=":", alpha=0.45)

        unit = " (%)" if pct else ""
        ax.set_xlabel(f"{label}{unit}", fontsize=FS)
        ax.set_ylabel("Score", fontsize=FS)
        ax.set_yticks([1, 2, 3, 4, 5])
        ax.set_ylim(0.8, 5.2)
        sub_display = sub_lbl.replace("Q_TI", "Q$_{TI}$").replace("Q_GS", "Q$_{GS}$").replace("Q_FA", "Q$_{FA}$")
        ax.set_title(f"{sub_display}: {label}", fontsize=TS - 1, pad=3)
        apply_publication_style(ax, font_size=FS)
        add_panel_label(ax, chr(ord("a") + i), x=-0.12)

    # Last panel: legend
    for ax in axes_flat[len(metrics):]:
        ax.axis("off")
    ax = axes_flat[-1]
    ax.axis("off")
    handles = (
        [mpatches.Patch(fc=zone_clr[i], alpha=0.55,
                        label=f"Score {5-i} (Grade {'ABCDE'[i]})")
         for i in range(5)]
        + [plt.Line2D([0], [0], color=C_QTI, lw=1.2, label="Q$_{TI}$ curve"),
           plt.Line2D([0], [0], color=C_QGS, lw=1.2, label="Q$_{GS}$ curve"),
           plt.Line2D([0], [0], color=C_QFA, lw=1.2, label="Q$_{FA}$ curve"),
           plt.Line2D([0], [0], marker="o", ms=4, color=PAL["neutral_mid"],
                      lw=0, label="Break-point")]
    )
    ax.legend(handles=handles, fontsize=TK - 0.5, loc="center",
              frameon=True, framealpha=0.45, handlelength=1.2)
    ax.set_title("Legend", fontsize=TS - 1, pad=3)

    fig.suptitle(f"Configured Piecewise Score Mappings ({state['calib'].get('mapping_version', 'v1')})",
                 fontsize=TS, y=1.02)
    save_fig(fig, "D2_Fig06_mapping_curves", pad=1.5)


# ─────────────────────────────────────────────────────────────────────────────
# Fig 07: Sensor Availability Profile
# ─────────────────────────────────────────────────────────────────────────────

def fig07_availability_profile(state: dict):
    channels   = state["scored_channels"]
    all_D2     = state["all_D2"]

    mean_d2 = {ch: float(all_D2[ch]["D2_total"].mean())
               for ch in channels if ch in all_D2}
    grade_rates: dict[str, dict[str, float]] = {}
    for ch in channels:
        if ch not in all_D2:
            continue
        gr = all_D2[ch]["grade"]
        grade_rates[ch] = {g: float((gr == g).mean()) for g in "ABCDE"}

    ch_sorted = sorted(channels, key=lambda c: mean_d2.get(c, 0))
    n  = len(ch_sorted)
    yp = list(range(n))

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(7.2, 5.0))
    fig.subplots_adjust(wspace=0.42)

    # ── Panel A: mean D2 bar ──────────────────────────────────────────────
    bar_colors = []
    for ch in ch_sorted:
        d = mean_d2.get(ch, 3.0)
        if   d >= 4.5: bar_colors.append(GRADE_COLOR["A"])
        elif d >= 3.5: bar_colors.append(GRADE_COLOR["B"])
        elif d >= 2.5: bar_colors.append(GRADE_COLOR["C"])
        elif d >= 1.5: bar_colors.append(GRADE_COLOR["D"])
        else:          bar_colors.append(GRADE_COLOR["E"])

    ax1.barh(yp, [mean_d2.get(c, 0) for c in ch_sorted],
             color=bar_colors, height=0.68,
             edgecolor=PAL["neutral_dark"], linewidth=0.6)
    for i, ch in enumerate(ch_sorted):
        d   = mean_d2.get(ch, 0)
        clr = "white" if luminance(bar_colors[i]) < 0.5 else PAL["neutral_dark"]
        ax1.text(d + 0.06, i, f"{d:.2f}", va="center", ha="left",
                 fontsize=TK - 0.5, color=PAL["neutral_dark"])
    for thr, g in [(4.5, "A"), (3.5, "B"), (2.5, "C")]:
        ax1.axvline(thr, color=GRADE_COLOR[g], lw=0.8, ls="--", alpha=0.65)
    ax1.set_yticks(yp)
    ax1.set_yticklabels(ch_sorted, fontsize=TK)
    ax1.set_xlim(0, 5.6)
    ax1.set_xticks([1, 2, 3, 4, 5])
    ax1.set_xlabel("Mean D2 Score", fontsize=FS)
    ax1.set_title("Mean D2 Score (Ranked)", fontsize=TS, pad=4)
    apply_publication_style(ax1, font_size=FS)
    add_panel_label(ax1, "A")

    # ── Panel B: stacked grade fraction ──────────────────────────────────
    left = np.zeros(n)
    for g, gc in [("A", GRADE_COLOR["A"]), ("B", GRADE_COLOR["B"]),
                  ("C", GRADE_COLOR["C"]), ("D", GRADE_COLOR["D"]),
                  ("E", GRADE_COLOR["E"])]:
        vals = np.array([grade_rates.get(ch, {}).get(g, 0) * 100
                         for ch in ch_sorted])
        ax2.barh(yp, vals, left=left, color=gc, height=0.68,
                 label=f"Grade {g}",
                 edgecolor=PAL["neutral_dark"], linewidth=0.3)
        left += vals

    ax2.set_yticks(yp)
    ax2.set_yticklabels(ch_sorted, fontsize=TK)
    ax2.set_xlim(0, 101)
    ax2.set_xlabel("Grade distribution (%)", fontsize=FS)
    ax2.set_title("Grade Distribution", fontsize=TS, pad=4)
    apply_publication_style(ax2, font_size=FS)
    add_panel_label(ax2, "B")

    fig.suptitle("Sensor Availability Profile", fontsize=TS, y=1.02)
    handles = [
        plt.Rectangle(
            (0, 0), 1, 1, facecolor=GRADE_COLOR[g],
            edgecolor=PAL["neutral_dark"], linewidth=0.3,
            label=f"Grade {g}",
        )
        for g in "ABCDE"
    ]
    fig.legend(
        handles=handles, ncol=5, fontsize=TK - 0.5,
        loc="lower center", bbox_to_anchor=(0.5, 0.005),
        handlelength=0.8, columnspacing=0.8, frameon=False,
    )
    save_fig(
        fig, "D2_Fig07_availability_profile",
        rect=(0, 0.08, 1, 0.97),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Fig 08: D1–D2 Relationship
# ─────────────────────────────────────────────────────────────────────────────

def fig08_d1_d2_relationship(state: dict):
    channels = state["scored_channels"]
    all_D2   = state["all_D2"]
    do_chs   = [c for c in channels if c.startswith("DO")]
    orp_chs  = [c for c in channels if c.startswith("ORP")]
    D2_wide  = _wide(all_D2, channels, "D2_total")

    D1_v11 = None
    has_d1 = False
    d1_pkl = _D1 / "v11_state.pkl"
    if d1_pkl.exists():
        try:
            with open(d1_pkl, "rb") as f:
                d1s = pickle.load(f)
            D1_v11 = d1s.get("D1_v11")
            has_d1 = D1_v11 is not None and len(D1_v11) > 0
        except Exception:
            pass

    fig = plt.figure(figsize=(7.2, 3.8))
    gs  = GridSpec(1, 2, figure=fig, wspace=0.36)
    ax1 = fig.add_subplot(gs[0])
    ax2 = fig.add_subplot(gs[1])

    # ── Panel A: D1 vs D2 scatter ─────────────────────────────────────────
    if has_d1:
        common = D1_v11.index.intersection(D2_wide.index)
        d1_parts, d2_parts = [], []
        for ch in channels:
            if ch not in D1_v11.columns or ch not in D2_wide.columns:
                continue
            d1v = D1_v11.loc[common, ch].dropna()
            d2v = D2_wide.loc[d1v.index, ch].dropna()
            idx = d1v.index.intersection(d2v.index)
            if len(idx) < 2:
                continue
            d1_parts.append(d1v.loc[idx].to_numpy())
            d2_parts.append(d2v.loc[idx].to_numpy())

        if d1_parts:
            x = np.concatenate(d1_parts)
            y = np.concatenate(d2_parts)
            hb = ax1.hexbin(x, y, gridsize=34, extent=(1, 5, 1, 5),
                            mincnt=1, bins="log", cmap="viridis",
                            linewidths=0, rasterized=True)
            cb = fig.colorbar(hb, ax=ax1, fraction=0.032, pad=0.018)
            cb.set_label("Hexagon count", fontsize=TK, labelpad=2)
            cb.ax.tick_params(labelsize=TK - 1)
            rho = pd.Series(x).corr(pd.Series(y), method="spearman")
            ax1.text(0.04, 0.96, f"Spearman $\\rho$ = {rho:.2f}\n$n$ = {len(x):,}",
                     transform=ax1.transAxes, va="top", fontsize=TK)

        ax1.plot([1, 5], [1, 5], "--",
                 color=PAL["neutral_mid"], lw=0.8, alpha=0.50,
                 label="D1 = D2")
        ax1.set_xlabel("D1 Score (Sensor Health)", fontsize=FS)
        ax1.set_ylabel("D2 Score (Temporal Continuity)", fontsize=FS)
        ax1.set_xlim(0.8, 5.2)
        ax1.set_ylim(0.8, 5.2)
        ax1.set_xticks([1, 2, 3, 4, 5])
        ax1.set_yticks([1, 2, 3, 4, 5])
        ax1.set_title("D1 vs D2 (per channel-hour)", fontsize=TS, pad=4)

        # ── Panel B: time series ──────────────────────────────────────────
        D1_DO  = D1_v11[do_chs].mean(axis=1).resample("D").mean()
        D1_ORP = D1_v11[[c for c in orp_chs if c in D1_v11.columns]] \
                      .mean(axis=1).resample("D").mean()
        D2_DO  = D2_wide[do_chs].mean(axis=1).resample("D").mean()
        D2_ORP = D2_wide[orp_chs].mean(axis=1).resample("D").mean()

        ax2.plot(D1_DO.index,  D1_DO.values,  color=C_DO,  lw=LWM, ls="-",
                 label="D1 DO")
        ax2.plot(D2_DO.index,  D2_DO.values,  color=C_DO,  lw=LWM, ls="--",
                 label="D2 DO")
        ax2.plot(D1_ORP.index, D1_ORP.values, color=C_ORP, lw=LWM, ls="-",
                 label="D1 ORP")
        ax2.plot(D2_ORP.index, D2_ORP.values, color=C_ORP, lw=LWM, ls="--",
                 label="D2 ORP")
    else:
        ax1.text(0.5, 0.5,
                 "D1 state unavailable\n(v11_state.pkl not found)",
                 transform=ax1.transAxes, ha="center", va="center",
                 fontsize=FS, color=PAL["neutral_mid"], style="italic")
        ax1.set_title("D1 vs D2 Scatter", fontsize=TS, pad=4)

        D2_DO  = D2_wide[do_chs].mean(axis=1).resample("D").mean()
        D2_ORP = D2_wide[orp_chs].mean(axis=1).resample("D").mean()
        ax2.plot(D2_DO.index,  D2_DO.values,  color=C_DO,  lw=LWM,
                 label="D2 DO mean")
        ax2.plot(D2_ORP.index, D2_ORP.values, color=C_ORP, lw=LWM,
                 label="D2 ORP mean")

    ax2.set_xlabel("Date", fontsize=FS)
    ax2.set_ylabel("Score (1 – 5)", fontsize=FS, labelpad=8)
    ax2.set_title("D1 / D2 Daily Mean Time-Series", fontsize=TS, pad=4)
    ax2.set_ylim(0.8, 5.2)
    ax2.set_yticks([1, 2, 3, 4, 5])
    ax2.legend(fontsize=TK - 0.5, ncol=2, handlelength=1.0, frameon=False)
    ax2.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    ax2.tick_params(axis="y", pad=3)
    for lbl in ax2.get_xticklabels():
        lbl.set_rotation(30)
        lbl.set_ha("right")

    apply_publication_style(ax1, font_size=FS)
    apply_publication_style(ax2, font_size=FS)
    ax1.legend(
        loc="lower left", fontsize=TK - 0.5, frameon=True,
        facecolor="white", edgecolor="none", framealpha=0.78,
        handlelength=1.2,
    )
    add_panel_label(ax1, "A")
    add_panel_label(ax2, "B")

    fig.suptitle("D1 Sensor Health – D2 Temporal Continuity Relationship",
                 fontsize=TS, y=1.02)
    save_fig(fig, "D2_Fig08_d1_d2_relationship")


# ─────────────────────────────────────────────────────────────────────────────
# Fig 09: Veto Activation Analysis
# ─────────────────────────────────────────────────────────────────────────────

def fig09_veto_analysis(state: dict):
    channels = state["scored_channels"]
    all_D2   = state["all_D2"]

    veto_wide  = _wide(all_D2, channels, "veto_flag").astype(float)
    veto_daily = veto_wide.resample("D").mean() * 100   # %
    D2_wide    = _wide(all_D2, channels, "D2_total")
    D2_daily   = D2_wide.resample("D").mean()

    reason_counts: dict[str, int] = {}
    for ch in channels:
        if ch not in all_D2:
            continue
        for r in all_D2[ch]["veto_reason"]:
            if not r:
                continue
            for sub in str(r).split("|"):
                sub = sub.strip()
                if sub:
                    reason_counts[sub] = reason_counts.get(sub, 0) + 1

    fig = plt.figure(figsize=(7.2, 4.5))
    gs  = GridSpec(2, 2, figure=fig, wspace=0.42, hspace=0.55)
    ax1 = fig.add_subplot(gs[0, :])   # full-width top
    ax2 = fig.add_subplot(gs[1, 0])
    ax3 = fig.add_subplot(gs[1, 1])

    # ── Panel A: veto heatmap ─────────────────────────────────────────────
    mat   = veto_daily[channels].T.values
    cmap_v = LinearSegmentedColormap.from_list(
        "veto", ["white", PAL["orange"], PAL["red_strong"]], N=256)
    im = ax1.imshow(mat, aspect="auto", cmap=cmap_v,
                    vmin=0, vmax=100, origin="upper", interpolation="nearest")
    n    = len(veto_daily)
    step = max(1, n // 7)
    tks  = list(range(0, n, step))
    ax1.set_xticks(tks)
    ax1.set_xticklabels(veto_daily.index[tks].strftime("%b %d"),
                         rotation=30, ha="right", fontsize=TK - 0.5)
    ax1.set_yticks(range(len(channels)))
    ax1.set_yticklabels(channels, fontsize=TK - 1)
    ax1.set_title("Veto Activation Rate — Daily (%)", fontsize=TS, pad=4)
    ax1.tick_params(axis="both", length=3, width=1.0, direction="out")
    ax1.spines["right"].set_visible(False)
    ax1.spines["top"].set_visible(False)
    ax1.spines["left"].set_linewidth(LW_SP)
    ax1.spines["bottom"].set_linewidth(LW_SP)
    cbar1 = fig.colorbar(im, ax=ax1, fraction=0.025, pad=0.01, aspect=25)
    cbar1.set_label("Veto rate (%)", fontsize=FS - 1)
    cbar1.ax.tick_params(length=3, labelsize=TK - 1)
    for y_sep in [3.5, 7.5, 10.5]:
        ax1.axhline(y=y_sep, color="white", lw=1.2)
    add_panel_label(ax1, "A", x=-0.04)

    # ── Panel B: D2 mean with veto overlay ───────────────────────────────
    D2_mean   = D2_daily.mean(axis=1)
    veto_mean = veto_daily.mean(axis=1) / 100

    ax2.plot(D2_mean.index, D2_mean.values,
             color=PAL["blue_main"], lw=LWM, label="D2 system mean")
    ax2.fill_between(veto_mean.index, 1, 5,
                     where=veto_mean > 0.10, alpha=0.18,
                     color=PAL["red_strong"], label="Veto active >10 %")
    ax2.set_ylim(0.8, 5.2)
    ax2.set_yticks([1, 2, 3, 4, 5])
    ax2.set_xlabel("Date", fontsize=FS)
    ax2.set_ylabel("D2 Score", fontsize=FS)
    ax2.set_title("D2 Mean + Veto Periods", fontsize=TS - 0.5, pad=3)
    ax2.legend(fontsize=TK - 1, handlelength=1.0, frameon=False)
    ax2.xaxis.set_major_locator(mticker.MaxNLocator(4))
    for lbl in ax2.get_xticklabels():
        lbl.set_rotation(30)
        lbl.set_ha("right")
    apply_publication_style(ax2, font_size=FS)
    add_panel_label(ax2, "B")

    # ── Panel C: veto reason bar ──────────────────────────────────────────
    if reason_counts:
        items  = sorted(reason_counts.items(), key=lambda x: -x[1])
        labels = [r[0].replace("_", "\n") for r in items]
        counts = [r[1] for r in items]
        bars   = ax3.barh(range(len(labels)), counts,
                          color=PAL["orange"], alpha=0.80,
                          edgecolor=PAL["neutral_dark"], linewidth=0.5)
        ax3.set_yticks(range(len(labels)))
        ax3.set_yticklabels(labels, fontsize=TK - 0.5)
        ax3.set_xlabel("Hour count", fontsize=FS)
        ax3.set_title("Veto Reason Frequency", fontsize=TS - 0.5, pad=3)
    else:
        ax3.text(0.5, 0.5, "No veto events\nrecorded",
                 transform=ax3.transAxes, ha="center", va="center",
                 fontsize=FS, color=PAL["neutral_mid"], style="italic")
        ax3.set_title("Veto Reason Frequency", fontsize=TS - 0.5, pad=3)
    apply_publication_style(ax3, font_size=FS)
    add_panel_label(ax3, "C")

    save_fig(fig, "D2_Fig09_veto_analysis", pad=1.5)


# ─────────────────────────────────────────────────────────────────────────────
# Fig 10: Calibration & Metric Distribution Summary
# ─────────────────────────────────────────────────────────────────────────────

def fig10_calibration_summary(state: dict):
    channels = state["scored_channels"]
    subs_all = state["subs_all"]
    calib    = state["calib"]

    metric_defs = [
        ("missing_rate",   "Missing Rate",   True,  ENG["missing_rate_breaks"]),
        ("irregular_rate", "Irregular Rate", True,  ENG["irregular_rate_breaks"]),
        ("L_max_min",      "L$_{max}$",      False, ENG["L_max_breaks_min"]),
        ("gap_run_count",  "Gap Count",      False, ENG["gap_count_breaks"]),
        ("info_empty_cov", "Info-Empty",     True,  ENG["info_empty_breaks"]),
    ]

    pct_lines = [
        (5,  PAL["improve"],     ":",  "P5"),
        (25, PAL["blue_main"],   "-.", "P25"),
        (50, PAL["neutral_black"], "-", "P50"),
        (75, PAL["orange"],      "-.", "P75"),
        (95, PAL["red_strong"],  "--", "P95"),
        (99, "#8B0000",          "--", "P99"),
    ]

    fig, axes = plt.subplots(2, 3, figsize=(7.2, 5.0))
    fig.subplots_adjust(hspace=0.60, wspace=0.44)
    axes_flat = axes.flatten()

    for i, (col, label, pct, eng_brk) in enumerate(metric_defs):
        ax   = axes_flat[i]
        vals = []
        for ch in channels:
            if ch in subs_all and col in subs_all[ch].columns:
                v = subs_all[ch][col].dropna().values
                vals.append(v)
        if not vals:
            ax.set_visible(False)
            continue
        all_v = np.concatenate(vals)
        all_v = all_v[np.isfinite(all_v)]
        scale = 100.0 if pct else 1.0
        all_v_d = all_v * scale

        ordered = np.sort(all_v_d)
        cumulative = np.arange(1, len(ordered) + 1) / len(ordered) * 100
        ax.step(ordered, cumulative, where="post", color=PAL["blue_main"],
                lw=LWM)

        for p, c, ls, lbl in pct_lines:
            pv = float(np.percentile(all_v_d, p))
            ax.axvline(pv, color=c, lw=0.8, ls=ls,
                       label=f"{lbl}={pv:.{1 if pct else 0}f}")

        for bk in eng_brk:
            ax.axvline(bk * scale, color=PAL["neutral_mid"],
                       lw=0.5, ls=":", alpha=0.35)

        unit = " (%)" if pct else ""
        ax.set_xlabel(f"{label}{unit}", fontsize=FS)
        ax.set_ylabel("Cumulative probability (%)", fontsize=FS)
        ax.set_ylim(0, 101)
        xmax = max(float(np.percentile(all_v_d, 99.5)), max(eng_brk) * scale)
        ax.set_xlim(left=min(0, float(np.nanmin(all_v_d))), right=xmax * 1.05 if xmax > 0 else 1)
        ax.set_title(f"{label} ECDF", fontsize=TS - 0.5, pad=3)
        ax.legend(fontsize=TK - 2, ncol=2, handlelength=0.9,
                  columnspacing=0.4, frameon=False)
        apply_publication_style(ax, font_size=FS)
        add_panel_label(ax, "ABCDE"[i], x=-0.14)

    # Last panel: calibration metadata text box
    ax = axes_flat[5]
    ax.axis("off")
    cal_id  = calib.get("calibration_id",     "N/A")
    cal_src = calib.get("calibration_basis", "D2_internal_engineering_v1")
    bench = calib.get("benchmark_windows", {})
    n_bench = bench.get("total_benchmark_hours", 0)
    period = calib.get("effective_period", ["N/A", "N/A"])
    b_start, b_end = period[0], period[-1]
    run_dt = calib.get("generated_date", "N/A")
    mapping_version = calib.get("mapping_version", "N/A")

    info = (f"Calibration ID:\n  {cal_id}\n\n"
            f"Basis:\n  {cal_src}\n\n"
            f"Mapping:\n  {mapping_version}\n\n"
            f"Effective period:\n  {b_start}\n  to {b_end}\n\n"
            f"D1 fit hours: {n_bench}\n\n"
            f"Generated: {run_dt}")
    ax.text(0.05, 0.95, info, transform=ax.transAxes,
            fontsize=TK - 0.5, va="top", ha="left", family="monospace",
            bbox=dict(facecolor="#FAFAFA", edgecolor=PAL["neutral_light"],
                      pad=5, boxstyle="round,pad=0.4"))
    ax.set_title("Calibration Metadata", fontsize=TS - 0.5, pad=3)

    fig.suptitle("Calibration & Metric Distribution Summary",
                 fontsize=TS, y=1.02)
    save_fig(fig, "D2_Fig10_calibration_summary", pad=1.5)


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    import time
    t0 = time.time()
    print("=" * 64)
    print("D2 Figure Generation — publication bundle (PNG + SVG + PDF)")
    print("=" * 64)

    state = load_state()

    figures = [
        ("Fig01  D2 Overview Heatmap",        fig01_overview_heatmap),
        ("Fig02  Sub-score Violin Plots",      fig02_subscore_violins),
        ("Fig03  Missing Rate Timeline",       fig03_missing_rate),
        ("Fig04  Gap Severity Analysis",       fig04_gap_severity),
        ("Fig05  Freeze–Availability Events",  fig05_freeze_availability),
        ("Fig06  Piecewise Mapping Curves",    fig06_mapping_curves),
        ("Fig07  Sensor Availability Profile", fig07_availability_profile),
        ("Fig08  D1–D2 Relationship",          fig08_d1_d2_relationship),
        ("Fig09  Veto Activation Analysis",    fig09_veto_analysis),
        ("Fig10  Calibration Summary",         fig10_calibration_summary),
    ]

    ok, fail = 0, 0
    for name, fn in figures:
        print(f"\n[{name}]")
        try:
            fn(state)
            ok += 1
        except Exception as exc:
            print(f"  [ERROR] {exc}")
            traceback.print_exc()
            fail += 1

    print(f"\n{'='*64}")
    print(f"Done in {time.time()-t0:.1f}s — {ok} figures saved, {fail} failed")
    print(f"Output: {FIGS}")
    print("=" * 64)


if __name__ == "__main__":
    main()
