"""analysis_11/workflow_diagram.py — revised §1.1 decomposition→whitening→§1.2
workflow diagram, drawing the innovations the plain flowchart hides:

  differentiated per-process-group decomposition · strict causal (block-wise
  harmonic re-fit + backward trend + trailing STL) · sufficiency feedback loop ·
  data-driven model selection (ADF/KPSS, LRD/ARFIMA gate) · ARMA/GARCH whitening
  · acceptance gate with THREE tracks (innovation / robust_z / censored_z) ·
  whiteness_manifest routing · downstream three-caliber division of labour
  (raw-min → spike/freeze; residual → drift/FF-PCA; innovation → step/regime/PELT).

Output: outputs/figures/fig_W0_workflow.png (+ .pdf).  Static/conceptual — no data.
"""
from __future__ import annotations
from pathlib import Path
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

ROOT = Path(__file__).resolve().parents[1]
FIG = ROOT / "outputs" / "figures"
FIG.mkdir(parents=True, exist_ok=True)

C = {"pre": "#B7D9A8", "orig": "#AED4F0", "decomp": "#E7897F", "trend": "#8CC98F",
     "seas": "#F0C27A", "resid": "#E3A6A0", "select": "#F6C99A", "whiten": "#EF9A5A",
     "gate": "#C9B7DE", "iid": "#B7A0CE", "auto": "#8FC7E8", "floor": "#C4C4C4",
     "manifest": "#D9CBE8", "regime": "#A8D5B5", "dqr": "#C7E29A",
     "cal_raw": "#F2C14E", "cal_res": "#7FB3D5", "cal_inn": "#B7A0CE", "edge": "#333"}
LOOP = "#B26A00"


def box(ax, cx, cy, w, h, text, fc, fs=8.4, ec=None, ls="-", txt_c="#111"):
    ax.add_patch(FancyBboxPatch((cx - w / 2, cy - h / 2), w, h,
                 boxstyle="round,pad=0.15,rounding_size=0.6", linewidth=1.1,
                 facecolor=fc, edgecolor=ec or C["edge"], linestyle=ls, zorder=2))
    ax.text(cx, cy, text, ha="center", va="center", fontsize=fs, fontweight="bold",
            color=txt_c, zorder=3, linespacing=1.22)


def arrow(ax, p1, p2, color=None, lw=1.7, ls="-", rad=0.0):
    ax.add_patch(FancyArrowPatch(p1, p2, arrowstyle="-|>", mutation_scale=14, lw=lw,
                 color=color or C["edge"], linestyle=ls, zorder=1,
                 connectionstyle=f"arc3,rad={rad}", shrinkA=1, shrinkB=1))


def main():
    plt.rcParams.update({"font.family": "sans-serif",
                         "font.sans-serif": ["DejaVu Sans", "Arial"],
                         "axes.unicode_minus": False})
    fig, ax = plt.subplots(figsize=(11.6, 13.6))
    ax.set_xlim(0, 100); ax.set_ylim(0, 100); ax.axis("off")
    CX = 50   # main spine

    # 1 preprocessing
    box(ax, CX, 96.7, 80, 4.4,
        "Data collection & preprocessing\n(mark-not-clean · multi-rate NATIVE alignment to 1-min clock · Tobit left-censoring)", fs=8.6, fc=C["pre"])
    arrow(ax, (CX, 94.5), (CX, 92.7))
    box(ax, CX, 90.9, 30, 3.4, "Original sequences  $X_k(t)$", C["orig"], fs=9.2)
    arrow(ax, (CX, 89.2), (CX, 87.4))

    # 2 differentiated decomposition
    box(ax, CX, 83.8, 92, 6.2,
        "①  DIFFERENTIATED additive decomposition   $X_k(t)=m_k(t)+s_k(t)+e_k(t)$   ·   strict CAUSAL / rolling\n"
        "per process group — own candidate periods · adaptive harmonic order · STL iters · censoring:\n"
        "aerobic-DO · post-anoxic-DO · anoxic-ORP · recycle-flow · influent(+flow) · effluent", C["decomp"], fs=8.4)
    arrow(ax, (22, 80.7), (20, 73.6)); arrow(ax, (CX, 80.7), (CX, 73.6)); arrow(ax, (78, 80.7), (80, 73.6))

    # three components
    box(ax, 20, 70.8, 25, 4.6, "trend  $m_k(t)$\n②  causal BACKWARD\nrolling mean (deseason'd)", C["trend"], fs=7.9)
    ax.text(34.5, 70.8, "+", ha="center", va="center", fontsize=16, fontweight="bold")
    box(ax, CX, 70.8, 27, 4.6, "seasonal  $s_k(t)$\n③  harmonic (block-refit)\n+ iterative STL + sub-hourly", C["seas"], fs=7.7)
    ax.text(65.5, 70.8, "+", ha="center", va="center", fontsize=16, fontweight="bold")
    box(ax, 80, 70.8, 25, 4.6, "residual  $e_k(t)$\n(de-trended,\nde-seasonalised)", C["resid"], fs=7.9)

    # m,s → regime/baseline (left)
    arrow(ax, (20, 68.5), (9, 63.0), color="#4a4a4a", rad=0.2)
    arrow(ax, (39, 70.8), (16, 62.5), color="#4a4a4a", ls=(0, (2, 2)), rad=0.25)
    box(ax, 9.5, 60.2, 16, 5.0, "Regime /\nbaseline\n( m , s )", C["regime"], fs=8.0, ec="#4a4a4a")

    # 4 sufficiency loop (residual → peak-ratio check → iterate STL / proceed)
    arrow(ax, (80, 68.5), (60, 63.4), rad=0.08)                    # residual → check
    box(ax, CX, 61.0, 44, 3.8, "④  sufficiency check:  residual local spectral peak-ratio < 2 ?", "#FFFFFF", fs=8.0, ec="#888")
    arrow(ax, (40, 62.2), (46, 68.5), color=LOOP, ls=(0, (4, 2)), rad=-0.35)   # loop back to STL
    ax.text(33.5, 65.6, "no →\niterate STL", ha="center", va="center", fontsize=7.2, color=LOOP, style="italic")
    arrow(ax, (CX, 59.1), (CX, 56.9))
    ax.text(CX + 2.4, 58.0, "yes (clean)", ha="left", va="center", fontsize=7.2, color="#333", style="italic")

    # 5-7 model selection → GARCH → acceptance gate
    box(ax, CX, 54.4, 66, 4.2,
        "⑤  data-driven model selection:  ADF + KPSS → integer d · seasonal D · LRD (GPH / R-S) → ARFIMA gate", C["select"], fs=7.9)
    arrow(ax, (CX, 52.3), (CX, 50.6))
    box(ax, CX, 48.7, 40, 3.4, "⑥  ARMA / GARCH residual whitening", C["whiten"], fs=8.6)
    arrow(ax, (CX, 47.0), (CX, 45.3))
    box(ax, CX, 43.0, 62, 4.0,
        "⑦  ACCEPTANCE GATE  —  stationary·invertible roots  +  windowed-LB pass  +  variance ratio", C["gate"], fs=8.0)

    # 8 three tracks
    arrow(ax, (32, 41.0), (22, 36.4), rad=0.05); arrow(ax, (CX, 41.0), (CX, 36.4)); arrow(ax, (68, 41.0), (78, 36.4), rad=-0.05)
    box(ax, 22, 33.6, 30, 4.8, "iid  (29 ch, pass gate)\n→ innovation  $\\eta_k(t)$\n(white i.i.d.)", C["iid"], fs=7.7)
    box(ax, CX, 33.6, 30, 4.8, "autocorr_aware  (3 near-UR)\n→ robust_z\n(not white · + $n_{\\rm eff}$)", C["auto"], fs=7.7)
    box(ax, 78, 33.6, 30, 4.8, "floor_freeze  (DO_1_4)\n→ censored_z\n(Tobit floor)", C["floor"], fs=7.7)
    arrow(ax, (22, 31.2), (34, 27.9), rad=0.05); arrow(ax, (CX, 31.2), (CX, 27.9)); arrow(ax, (78, 31.2), (66, 27.9), rad=-0.05)

    # manifest routing
    box(ax, CX, 25.7, 76, 3.8,
        "⑧  whiteness_manifest  —  per-channel routing  ( scoring_mode · $n_{\\rm eff}$ · innov_kind )", C["manifest"], fs=8.4)
    arrow(ax, (CX, 23.8), (CX, 22.0))

    # 9 WW-DQR + three-caliber
    box(ax, CX, 20.2, 92, 3.2, "⑨  WW-DQR  /  §1.2  D1 sensor-health scoring  —  manifest-keyed, three-caliber input", C["dqr"], fs=9.0)
    arrow(ax, (25, 18.6), (25, 15.4)); arrow(ax, (CX, 18.6), (CX, 15.4)); arrow(ax, (75, 18.6), (75, 15.4))
    box(ax, 25, 12.4, 29, 5.0, "RAW 1-min signal\n→ Spike (Hampel)\n· Freeze (rules)", C["cal_raw"], fs=7.6)
    box(ax, CX, 12.4, 29, 5.0, "§1.1 residual $e(t)$ (1-h)\n→ Drift-PLS · FF-PCA\n(multivariate, robust)", C["cal_res"], fs=7.6)
    box(ax, 75, 12.4, 29, 5.0, "§1.1 innovation / routed (1-h)\n→ Step-KS · Regime-KS · PELT\n(i.i.d.-sensitive, $\\times\\sqrt{n_{\\rm eff}}$)", C["cal_inn"], fs=7.6)

    # regime/baseline dashed → DQR
    arrow(ax, (9.5, 57.7), (9.5, 20.2), color="#4a4a4a", ls=(0, (5, 3)))
    arrow(ax, (9.5, 20.2), (14, 20.2), color="#4a4a4a", ls=(0, (5, 3)))

    ax.text(CX, 4.0,
            "① differentiated grouping   ② causal trend   ③ block-refit + iterative STL   ④ sufficiency loop   "
            "⑤–⑦ model-selection + GARCH + 3-track acceptance gate   ⑧ manifest routing   ⑨ three-caliber downstream",
            ha="center", va="center", fontsize=7.4, style="italic", color="#444")
    ax.set_title("Figure 1.  §1.1 differentiated decomposition → whitening → §1.2 DQR workflow (revised)",
                 fontsize=12.5, fontweight="bold", pad=8)

    fig.subplots_adjust(left=0.02, right=0.98, top=0.955, bottom=0.02)
    for ext in ("png", "pdf"):
        fig.savefig(FIG / f"fig_W0_workflow.{ext}", dpi=300, bbox_inches="tight")
    plt.close(fig)
    print("wrote fig_W0_workflow.png / .pdf")


if __name__ == "__main__":
    main()
