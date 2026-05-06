"""src/outputs/figure_classC_dim_matrix.py
The Class C 8-dimension DQR matrix figure, in the same visual format
as the user's reference image (Score axis × Weight×Dimension axis).
"""
from __future__ import annotations
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, FancyBboxPatch
from pathlib import Path

# Per Class C v1.1 weights from the implementation plan
CLASS_C_DIMS = [
    ("D1", "Sensor health\n(fault spectrum)",   0.22, "fault\nspectrum"),
    ("D7", "Spatial / twin-pool\nrepresentativeness", 0.25, "twin-pool\nsymmetry"),
    ("D2", "Completeness\n(missing + freeze)",     0.15, "missing\n+ freeze"),
    ("D6", "Multi-source\nconsistency",     0.10, "cross-pool\nKS"),
    ("D4", "Physical\nrationality",          0.10, "range +\nrate-of-change"),
    ("D8", "Metrological\ntraceability",     0.08, "DO=3, ORP=2\n(constant)"),
    ("D5", "Mass\nbalance",                  0.05, "QR/QIR\nratio"),
    ("D3", "Time-resolution\nmatch",         0.05, "min-level =>\nQ_D3 = 5"),
]

# Sort by weight descending (so heaviest is on the left)
CLASS_C_DIMS = sorted(CLASS_C_DIMS, key=lambda r: r[2], reverse=True)


def make_class_c_dim_matrix(out_path: Path):
    n = len(CLASS_C_DIMS)
    fig, ax = plt.subplots(figsize=(13, 7))
    ax.set_xlim(-0.6, n + 0.5)
    ax.set_ylim(-1.6, 6.5)
    ax.axis("off")

    cell_w, cell_h = 1.0, 1.0
    pad = 0.07

    # Top weight banner colours (saturated blues, decreasing alpha by rank)
    weight_colors = ["#1A5490", "#2874A6", "#3498DB", "#5499C7",
                     "#7FB3D5", "#A9CCE3", "#D4E6F1", "#EBF5FB"]

    # WEIGHT row (header)
    for i, (code, label, w, sub) in enumerate(CLASS_C_DIMS):
        rect = FancyBboxPatch(
            (i + 0.5 + pad, 5 + pad),
            cell_w - 2 * pad, cell_h - 2 * pad,
            boxstyle="round,pad=0.02,rounding_size=0.05",
            facecolor=weight_colors[i], edgecolor="white", lw=1.2,
        )
        ax.add_patch(rect)
        ax.text(i + 1, 5.5, f"{w:.2f}", ha="center", va="center",
                color="white", fontsize=14, fontweight="bold")

    # 5 score rows (5 → 1)
    score_colors = ["#E74C3C", "#EC7063", "#F1948A", "#F5B7B1", "#FADBD8"]
    for s_idx, score in enumerate([5, 4, 3, 2, 1]):
        # Left score label
        rect_l = FancyBboxPatch(
            (-0.05 + pad, (4 - s_idx) + pad),
            0.55 - 2 * pad, cell_h - 2 * pad,
            boxstyle="round,pad=0.02,rounding_size=0.04",
            facecolor=score_colors[s_idx],
            edgecolor="white", lw=1.0,
        )
        ax.add_patch(rect_l)
        ax.text(0.225, (4 - s_idx) + 0.5, str(score), ha="center", va="center",
                color="white", fontsize=12, fontweight="bold")
        # 8 grey cells per row
        for d_idx in range(n):
            rect = FancyBboxPatch(
                (d_idx + 0.5 + pad, (4 - s_idx) + pad),
                cell_w - 2 * pad, cell_h - 2 * pad,
                boxstyle="round,pad=0.02,rounding_size=0.04",
                facecolor="#ECF0F1", edgecolor="#BDC3C7", lw=0.7,
            )
            ax.add_patch(rect)

    # Bottom dimension labels (yellow)
    for i, (code, label, w, sub) in enumerate(CLASS_C_DIMS):
        rect = FancyBboxPatch(
            (i + 0.5 + pad, -0.5 + pad),
            cell_w - 2 * pad, 0.45 - 2 * pad,
            boxstyle="round,pad=0.02,rounding_size=0.04",
            facecolor="#F9E79F", edgecolor="white", lw=1.0,
        )
        ax.add_patch(rect)
        ax.text(i + 1, -0.27, code, ha="center", va="center",
                fontsize=9.5, color="#5D4037", fontweight="bold")
        ax.text(i + 1, -0.85, label, ha="center", va="center",
                fontsize=7.5, color="#5D4037")

    # Outer dashed brackets
    ax.text(-0.3, 2.5, "Score", ha="center", va="center", fontsize=12,
            fontweight="bold", color="#34495E", rotation=90)
    ax.text(n / 2 + 0.5, 6.3, "Weight",  ha="center", va="center",
            fontsize=13, fontweight="bold", color="#34495E")
    ax.text(n / 2 + 0.5, -1.30, "Dimension", ha="center", va="center",
            fontsize=12, fontweight="bold", color="#5D4037")
    ax.text(n / 2 + 0.5, 6.0, "(higher = more important)",
            ha="center", va="center", fontsize=8, style="italic",
            color="#7F8C8D")

    # Outer dashed boxes (Score axis box, Weight+Dimension box) — visual mimic
    # Outer dashed rectangle
    outer = Rectangle((0.5 - 0.05, -0.55), n + 0.1, 6.05,
                      facecolor="none", edgecolor="#7F8C8D", lw=1.0,
                      linestyle="--", alpha=0.6)
    ax.add_patch(outer)
    score_box = Rectangle((-0.4, 0 - 0.05), 1.0, 5.05,
                          facecolor="none", edgecolor="#7F8C8D", lw=1.0,
                          linestyle="--", alpha=0.6)
    ax.add_patch(score_box)

    # Notes at bottom
    note = ("Class C v1.1 weights — derived from min-level data (D3 originally 0.10) " 
            "with extra resolution channelled into D1 and D6 (twin-pool consistency).")
    ax.text(n / 2 + 0.5, -1.50, note, ha="center", va="center",
            fontsize=7.5, color="#566573", style="italic")

    fig.suptitle("Class C-minDQR — 8-dimension quality-rating matrix\n"
                 "(reference style; weights sorted descending)",
                 fontsize=12, fontweight="bold", y=0.99)
    plt.tight_layout()
    plt.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close()

    # Plot data
    df = pd.DataFrame([{
        "rank": i + 1,
        "code": code, "label": label.replace("\n", " "),
        "weight": w, "primary_method": sub.replace("\n", " "),
    } for i, (code, label, w, sub) in enumerate(CLASS_C_DIMS)])
    return out_path, df


if __name__ == "__main__":
    p, d = make_class_c_dim_matrix(Path("/tmp/test_classC.png"))
    print(p, d)
