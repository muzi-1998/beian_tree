"""make_d1d2_joint_figures.py
============================
B-1  事件共现矩阵  — D2 冻结事件与 D1 故障类型的跨维度关联分析
B-2  D1–D2 评分时序对比图 — 双轴时序 + D1 事件窗口 + D2 veto 区间

出图规范：Yuan1z0825/nature-skills
  - rcParams: Arial / sans-serif, svg.fonttype='none'
  - 轴：仅左+下，无网格，legend.frameon=False
  - 颜色：PALETTE（见下）
  - DPI: 600（PNG）+ editable SVG/PDF
  - 导出：artifacts/figures/
"""
from __future__ import annotations
import pickle
import warnings
import numpy as np
import pandas as pd
import matplotlib
import matplotlib as mpl
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
import matplotlib.patches as mpatches
from matplotlib.colors import LinearSegmentedColormap
from pathlib import Path
from publication_style import (PALETTE as SHARED_PALETTE,
                               configure_publication_style, finalize_figure)

warnings.filterwarnings("ignore")
matplotlib.use("Agg")

# ── 强制 rcParams（nature-skills 规范三行）────────────────────────────────────
mpl.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans", "Liberation Sans"],
    "font.size": 7,
    "svg.fonttype": "none",
    "pdf.fonttype": 42,
})
configure_publication_style()

# ── PALETTE（nature-skills api.md）───────────────────────────────────────────
PAL = {
    "blue_main":      "#0F4D92",
    "blue_secondary": "#3775BA",
    "blue_light":     "#A8C8E8",
    "green_3":        "#8BCF8B",
    "green_2":        "#AADCA9",
    "red_strong":     "#B64342",
    "red_2":          "#E9A6A1",
    "neutral_light":  "#CFCECE",
    "neutral_mid":    "#767676",
    "neutral_dark":   "#4D4D4D",
    "neutral_black":  "#272727",
    "gold":           "#FFD700",
    "teal":           "#42949E",
    "violet":         "#9A4D8E",
    "orange":         "#E07B39",
    "improve":        "#2E9E44",
    "degrade":        "#E53935",
}

# ── 路径 ──────────────────────────────────────────────────────────────────────
PAL.update(SHARED_PALETTE)

_ROOT  = Path(__file__).parent
_D1    = _ROOT.parent / "D1 Sensor health"
D2_PKL = _ROOT / "artifacts" / "d2_state.pkl"
D1_PKL = _D1 / "v11_state.pkl"
FIG_DIR = _ROOT / "artifacts" / "figures"
FIG_DIR.mkdir(parents=True, exist_ok=True)

SCORED_CHANNELS = [
    "DO_1_1","DO_1_2","DO_1_3","DO_1_4",
    "DO_2_1","DO_2_2","DO_2_3","DO_2_4",
    "ORP_1_1","ORP_1_2","ORP_1_3",
    "ORP_2_1","ORP_2_2","ORP_2_3",
]
CH_LABELS = {ch: ch.replace("_", " ") for ch in SCORED_CHANNELS}

FAULT_ORDER   = ["Q_regime","Q_step","Q_drift","Q_spike","Q_freeze","d2_only"]
FAULT_COLORS  = {
    "Q_regime": PAL["blue_main"],
    "Q_step":   PAL["teal"],
    "Q_drift":  PAL["orange"],
    "Q_spike":  PAL["gold"],
    "Q_freeze": PAL["violet"],
    "d2_only":  PAL["neutral_light"],
}
FAULT_LABELS  = {
    "Q_regime": "D1: Regime anomaly",
    "Q_step":   "D1: Step fault",
    "Q_drift":  "D1: Drift",
    "Q_spike":  "D1: Spike",
    "Q_freeze": "D1: Freeze",
    "d2_only":  "D2 only (no D1)",
}

REL_ORDER  = ["subset","overlap","superset","d2_only","no_d1_index"]
REL_COLORS = {
    "subset":       PAL["blue_main"],
    "overlap":      PAL["teal"],
    "superset":     PAL["violet"],
    "d2_only":      PAL["neutral_light"],
    "no_d1_index":  "#E8E8E8",
}
REL_LABELS = {
    "subset":       "D2 within D1",
    "overlap":      "Overlap",
    "superset":     "D2 contains D1",
    "d2_only":      "D2 only",
    "no_d1_index":  "No D1 index",
}

# Grade band reference lines
GRADE_BANDS = [
    (4.5, 5.0, "#DDF3DE", "A"),
    (3.5, 4.5, "#EEF8EE", "B"),
    (2.5, 3.5, "#FFF8E1", "C"),
    (1.5, 2.5, "#FDECEA", "D/E"),
]


def apply_publication_style(ax, font_size: int = 9,
                             axes_linewidth: float = 0.8) -> None:
    """Apply nature-skills publication style to an axes."""
    ax.spines["right"].set_visible(False)
    ax.spines["top"].set_visible(False)
    ax.spines["left"].set_linewidth(axes_linewidth)
    ax.spines["bottom"].set_linewidth(axes_linewidth)
    ax.tick_params(axis="both", which="major",
                   labelsize=font_size, length=4, width=axes_linewidth,
                   direction="out")
    ax.yaxis.get_label().set_fontsize(font_size)
    ax.xaxis.get_label().set_fontsize(font_size)
    ax.title.set_fontsize(font_size + 1)


def add_panel_label(ax, label: str, x=-0.10, y=1.03,
                    fontsize=11, fontweight="bold") -> None:
    normalized = label.strip().strip("()").lower()
    ax.text(x, y, f"({normalized})", transform=ax.transAxes,
            fontsize=fontsize, fontweight=fontweight,
            va="bottom", ha="right", clip_on=False,
            bbox={"facecolor": "white", "edgecolor": "none", "pad": 0.15})


def luminance(hex_color: str) -> float:
    c = hex_color.lstrip("#")
    r, g, b = int(c[0:2],16)/255, int(c[2:4],16)/255, int(c[4:6],16)/255
    return 0.299*r + 0.587*g + 0.114*b


def finalize(fig, stem: str, dpi: int = 600) -> None:
    plt.tight_layout(pad=1.5)
    finalize_figure(fig)
    for fmt in ("png", "svg", "pdf"):
        out = FIG_DIR / f"{stem}.{fmt}"
        fig.savefig(out, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
    print(f"  [OK] {stem}.png + .svg + .pdf")


# ════════════════════════════════════════════════════════════════════════════
# ── Load data ────────────────────────────────────────────────────────────────
# ════════════════════════════════════════════════════════════════════════════

def load_data():
    print("Loading D2 state …")
    with open(D2_PKL, "rb") as f:
        D2 = pickle.load(f)

    print("Loading D1 state …")
    with open(D1_PKL, "rb") as f:
        D1 = pickle.load(f)

    freeze_fp = _ROOT / "artifacts" / "data" / "D2_freeze_availability_events.xlsx"
    freeze_df = pd.read_excel(freeze_fp)
    freeze_df["start_ts"] = pd.to_datetime(freeze_df["start_ts"])
    freeze_df["end_ts"]   = pd.to_datetime(freeze_df["end_ts"])

    d1_ev_fp = _D1 / "outputs" / "data" / "D1_event_windows.xlsx"
    d1_ev = pd.read_excel(d1_ev_fp, sheet_name="all_events").rename(columns={
        "start": "start_ts", "end": "end_ts",
        "dominant_fault": "fault_type",
    })
    if "event_id" not in d1_ev:
        d1_ev.insert(0, "event_id", [f"D1E_{i:05d}" for i in range(1, len(d1_ev) + 1)])
    d1_ev["start_ts"] = pd.to_datetime(d1_ev["start_ts"])
    d1_ev["end_ts"]   = pd.to_datetime(d1_ev["end_ts"])

    return D2, D1, freeze_df, d1_ev


# ════════════════════════════════════════════════════════════════════════════
# ── B-1  Event Co-occurrence Matrix ─────────────────────────────────────────
# ════════════════════════════════════════════════════════════════════════════

def make_b1(freeze_df: pd.DataFrame, D2: dict) -> None:
    """
    B-1 三面板图:
      Panel A (左宽): 各通道 D2 冻结事件 relation_to_D1 堆叠条图
      Panel B (右上): D2 事件 linked_D1_fault_type 热力图（通道×故障类型，count）
      Panel C (右下): D2 事件时长分布（按 relation_to_D1 着色的箱线图）
    """
    print("B-1: building co-occurrence data …")

    # ── 数据准备 ─────────────────────────────────────────────────────────────
    # Panel A：relation_to_D1 堆叠条图
    rel_counts = {}
    for ch in SCORED_CHANNELS:
        sub = freeze_df[freeze_df["sensor_id"] == ch]
        vc  = sub["relation_to_D1"].value_counts()
        rel_counts[ch] = {r: int(vc.get(r, 0)) for r in REL_ORDER}

    rel_df = pd.DataFrame(rel_counts, index=REL_ORDER).T  # channels × relations

    # Panel B：linked_D1_fault_type 热力图（仅链接事件）
    linked = freeze_df[freeze_df["relation_to_D1"].isin(["subset","overlap","superset"])].copy()
    linked["linked_D1_fault_type"] = linked["linked_D1_fault_type"].fillna("unknown")

    hm = pd.DataFrame(0, index=SCORED_CHANNELS, columns=FAULT_ORDER[:-1])  # excl d2_only
    for ch in SCORED_CHANNELS:
        sub = linked[linked["sensor_id"] == ch]
        vc  = sub["linked_D1_fault_type"].value_counts()
        for ft in FAULT_ORDER[:-1]:
            hm.loc[ch, ft] = int(vc.get(ft, 0))

    # Panel C：event duration by relation
    dur_data   = {r: [] for r in REL_ORDER[:4]}   # excl no_d1_index
    for r in REL_ORDER[:4]:
        dur_data[r] = freeze_df[freeze_df["relation_to_D1"]==r]["duration_min"].tolist()

    # ── 布局 ─────────────────────────────────────────────────────────────────
    fig = plt.figure(figsize=(7.2, 4.2))
    gs  = gridspec.GridSpec(2, 2, figure=fig,
                            width_ratios=[1.7, 1.0],
                            hspace=0.72, wspace=0.38)
    ax_a  = fig.add_subplot(gs[:, 0])    # 全高左列
    ax_b  = fig.add_subplot(gs[0, 1])   # 右上
    ax_c  = fig.add_subplot(gs[1, 1])   # 右下

    fs = 8   # base font size

    # ── Panel A: 堆叠条图 ──────────────────────────────────────────────────
    y_pos   = np.arange(len(SCORED_CHANNELS))
    left    = np.zeros(len(SCORED_CHANNELS))
    ch_arr  = np.array(SCORED_CHANNELS)

    for rel in REL_ORDER:
        vals = rel_df[rel].values
        bars = ax_a.barh(y_pos, vals, left=left,
                         color=REL_COLORS[rel], label=REL_LABELS[rel],
                         height=0.72, edgecolor="white", linewidth=0.5)
        left += vals

    ax_a.set_yticks(y_pos)
    ax_a.set_yticklabels([ch.replace("_"," ") for ch in SCORED_CHANNELS],
                         fontsize=fs)
    ax_a.set_xlabel("Number of D2 freeze events", fontsize=fs)
    ax_a.set_title("D2 freeze event linkage to D1\n(per channel)", fontsize=fs+1)
    ax_a.legend(loc="lower right", fontsize=fs-1, frameon=False,
                ncol=1, handlelength=1.2, handletextpad=0.4)
    apply_publication_style(ax_a, font_size=fs)
    add_panel_label(ax_a, "A", x=-0.06)

    # ── Panel B: 热力图 ───────────────────────────────────────────────────
    hm_vals = hm.values.astype(float)
    # 自定义白→蓝渐变
    cmap_b = LinearSegmentedColormap.from_list(
        "w2b", ["#F0F4FA", PAL["blue_secondary"], PAL["blue_main"]])
    im = ax_b.imshow(hm_vals, aspect="auto", cmap=cmap_b,
                     interpolation="nearest")

    ax_b.set_xticks(range(len(FAULT_ORDER[:-1])))
    ax_b.set_xticklabels(
        [f.replace("Q_","") for f in FAULT_ORDER[:-1]],
        fontsize=fs-1, rotation=30, ha="right")
    ax_b.set_yticks(range(len(SCORED_CHANNELS)))
    ax_b.set_yticklabels([ch.replace("_"," ") for ch in SCORED_CHANNELS],
                         fontsize=fs-1)
    ax_b.set_title("D1 fault type of linked events\n(count)", fontsize=fs+1)

    # 单元格数值
    vmax = hm_vals.max()
    for i in range(len(SCORED_CHANNELS)):
        for j in range(len(FAULT_ORDER)-1):
            v = int(hm_vals[i, j])
            if v > 0:
                txt_c = "white" if hm_vals[i,j] / (vmax+1e-9) > 0.5 else PAL["neutral_dark"]
                ax_b.text(j, i, str(v), ha="center", va="center",
                          fontsize=fs-2, color=txt_c)

    cb = plt.colorbar(im, ax=ax_b, fraction=0.04, pad=0.04)
    cb.ax.tick_params(labelsize=fs-2)
    cb.set_label("Count", fontsize=fs-1)
    ax_b.spines[:].set_visible(False)
    ax_b.tick_params(length=0)
    add_panel_label(ax_b, "B", x=-0.16)

    # ── Panel C: 事件时长箱线图 ───────────────────────────────────────────
    rel_plot = [r for r in REL_ORDER[:4] if len(dur_data[r]) > 0]
    box_data = [dur_data[r] for r in rel_plot]
    bx = ax_c.boxplot(box_data, vert=True, patch_artist=True,
                      widths=0.55, showfliers=False,
                      medianprops=dict(color="black", lw=2),
                      whiskerprops=dict(lw=1.2),
                      capprops=dict(lw=1.2))
    for patch, rel in zip(bx["boxes"], rel_plot):
        patch.set_facecolor(REL_COLORS[rel])
        patch.set_alpha(0.85)
        patch.set_edgecolor(PAL["neutral_dark"])

    ax_c.set_xticks(range(1, len(rel_plot)+1))
    ax_c.set_xticklabels([REL_LABELS[r] for r in rel_plot],
                         fontsize=fs-1, rotation=20, ha="right")
    ax_c.set_ylabel("Event duration (min)", fontsize=fs)
    ax_c.set_title("D2 freeze event duration\nby D1 linkage type", fontsize=fs+1)
    ax_c.set_yscale("log")
    apply_publication_style(ax_c, font_size=fs)
    add_panel_label(ax_c, "C", x=-0.16)

    finalize(fig, "D2_Fig11_B1_event_cooccurrence")


# ════════════════════════════════════════════════════════════════════════════
# ── B-2  D1–D2 Score Time-Series Comparison ─────────────────────────────────
# ════════════════════════════════════════════════════════════════════════════

def make_b2(D2: dict, D1: dict, d1_ev: pd.DataFrame) -> None:
    """
    B-2 代表性通道时序对比图（6 通道，3×2 布局）:
      - 每子图: D2_total（蓝实线）+ D1_v11（橙虚线），双轴共享 y 范围 [1,5]
      - 着色: D1 事件窗口（浅红半透明）+ D2 veto 区间（浅蓝半透明）
      - 水平参考线: A/B/C 等级边界
    选择 6 条代表性通道（DO+ORP 各 3 条，涵盖高/中/低质量）
    """
    print("B-2: building time-series comparison …")

    D1_v11 = D1["D1_v11"]
    # 代表通道：覆盖高质量（4.9），中质量（3.5-4.5），低质量（<3）
    channels_b2 = [
        "DO_1_1",  # 健康 DO
        "DO_1_4",  # 后缺氧 process-floor DO
        "DO_2_4",  # 平行后缺氧 process-floor DO
        "ORP_1_1", # 中等 ORP
        "ORP_2_1", # 低质 ORP
        "ORP_2_2", # 最低 ORP
    ]

    fig, axes = plt.subplots(3, 2, figsize=(7.2, 7.0),
                             sharex=False, sharey=False)
    axes_flat = axes.flatten()
    fs = 8

    for idx, ch in enumerate(channels_b2):
        ax = axes_flat[idx]

        # D2 hourly
        d2_ser = D2["all_D2"][ch]["D2_total"].copy()
        d2_veto = D2["all_D2"][ch]["veto_flag"].astype(bool)

        # D1 hourly (align to D2 index)
        if ch in D1_v11.columns:
            d1_ser = D1_v11[ch].reindex(d2_ser.index)
        else:
            d1_ser = pd.Series(np.nan, index=d2_ser.index)

        t = d2_ser.index

        # ── 等级色带背景 ──────────────────────────────────────────────────
        for lo, hi, clr, _ in GRADE_BANDS:
            ax.axhspan(lo, hi, color=clr, alpha=0.35, zorder=0)

        # ── D2 veto 区间着色 ──────────────────────────────────────────────
        _shade_spans(ax, t, d2_veto, PAL["blue_light"], alpha=0.30,
                     label="D2 veto" if idx==0 else None, zorder=1)

        # ── D1 异常事件窗口着色 ───────────────────────────────────────────
        ch_d1ev = d1_ev[d1_ev["sensor_id"] == ch]
        for _, ev in ch_d1ev.iterrows():
            ax.axvspan(ev["start_ts"], ev["end_ts"],
                       color=PAL["red_2"], alpha=0.22, zorder=2)

        # ── 7d 滚动均线（降噪） ───────────────────────────────────────────
        d2_smooth = d2_ser.rolling("7D", min_periods=24).mean()
        d1_smooth = d1_ser.rolling("7D", min_periods=24).mean()

        # ── 原始细线 ──────────────────────────────────────────────────────
        ax.plot(t, d2_ser.values, color=PAL["blue_secondary"],
                lw=0.4, alpha=0.3, zorder=3)
        ax.plot(t, d1_ser.values, color=PAL["orange"],
                lw=0.4, alpha=0.3, zorder=3)

        # ── 7d 粗平滑线 ───────────────────────────────────────────────────
        lbl_d2 = "D2 score (7d avg)" if idx == 0 else None
        lbl_d1 = "D1 score (7d avg)" if idx == 0 else None
        ax.plot(t, d2_smooth.values, color=PAL["blue_main"],
                lw=2.2, zorder=4, label=lbl_d2)
        ax.plot(t, d1_smooth.values, color=PAL["orange"],
                lw=2.2, zorder=4, linestyle="--", label=lbl_d1)

        # ── 等级参考线 ────────────────────────────────────────────────────
        for thresh, grade, lc in [(4.5,"A",PAL["green_3"]),
                                   (3.5,"B",PAL["gold"]),
                                   (2.5,"C",PAL["red_2"])]:
            ax.axhline(thresh, color=lc, lw=0.8, ls=":", alpha=0.7, zorder=3)
            ax.text(t[-1], thresh+0.04, grade,
                    color=lc, fontsize=fs-2, va="bottom", ha="right")

        ax.set_ylim(1.0, 5.1)
        ax.set_xlim(t[0], t[-1])

        # x 轴月份刻度
        ax.xaxis.set_major_locator(matplotlib.dates.MonthLocator(interval=2))
        ax.xaxis.set_major_formatter(matplotlib.dates.DateFormatter("%Y-%m"))
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=30, ha="right",
                 fontsize=fs-1)

        ax.set_ylabel("Score (1–5)", fontsize=fs)
        ax.set_title(f"{ch.replace('_',' ')}  "
                     f"(D2 avg={d2_ser.mean():.2f}, D1 avg={d1_ser.mean():.2f})",
                     fontsize=fs, pad=3)

        apply_publication_style(ax, font_size=fs)
        add_panel_label(ax, "ABCDEF"[idx], x=-0.10)

    # ── 共享图例 ──────────────────────────────────────────────────────────
    legend_elements = [
        mpatches.Patch(color=PAL["blue_light"], alpha=0.5, label="D2 veto window"),
        mpatches.Patch(color=PAL["red_2"],      alpha=0.4, label="D1 anomaly event"),
        plt.Line2D([0],[0], color=PAL["blue_main"], lw=2.2, label="D2 score (7d avg)"),
        plt.Line2D([0],[0], color=PAL["orange"], lw=2.2, ls="--", label="D1 score (7d avg)"),
    ]
    fig.legend(handles=legend_elements, loc="lower center",
               ncol=4, fontsize=fs, frameon=False,
               bbox_to_anchor=(0.5, -0.02))

    fig.suptitle("D1 Sensor Health vs D2 Temporal Continuity — Representative Channels",
                 fontsize=fs+2, fontweight="bold", y=1.01)

    finalize(fig, "D2_Fig12_B2_d1d2_timeseries", dpi=300)


def _shade_spans(ax, t, flag: pd.Series,
                 color: str, alpha: float = 0.3,
                 label=None, zorder=1) -> None:
    """Shade contiguous True spans on the axes."""
    in_span = False
    span_start = None
    first = True
    flag_arr = flag.values
    t_arr    = t

    for i, val in enumerate(flag_arr):
        if val and not in_span:
            in_span    = True
            span_start = t_arr[i]
        elif not val and in_span:
            in_span = False
            lbl = label if first else None
            ax.axvspan(span_start, t_arr[i],
                       color=color, alpha=alpha, zorder=zorder, label=lbl)
            first = False

    if in_span:
        lbl = label if first else None
        ax.axvspan(span_start, t_arr[-1],
                   color=color, alpha=alpha, zorder=zorder, label=lbl)


# ════════════════════════════════════════════════════════════════════════════
# ── Main ─────────────────────────────────────────────────────────────────────
# ════════════════════════════════════════════════════════════════════════════

def main():
    import time
    t0 = time.time()
    print("=" * 60)
    print("B-1 + B-2 Joint Figure Generation (nature-skills spec)")
    print("=" * 60)

    D2, D1, freeze_df, d1_ev = load_data()

    print("\n[B-1] Event co-occurrence matrix …")
    make_b1(freeze_df, D2)

    print("\n[B-2] D1–D2 time-series comparison …")
    make_b2(D2, D1, d1_ev)

    print(f"\nDone in {time.time()-t0:.1f}s.")
    print(f"Outputs: {FIG_DIR}")


if __name__ == "__main__":
    main()
