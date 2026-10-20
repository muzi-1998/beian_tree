"""Quantitative archive audit figures, without model or native-frequency claims.

Contract: show technical support and nominal arithmetic consequences; two-panel
quantitative grids, development diagnostics except M01 mechanical split counts.
All relevant variables/profiles retained. Rows are archive records, not independent
replicates; no inferential intervals/tests. 183 x 88 mm, editable SVG/PDF + PNG,
CSV source, white background. Unknown native support is explicit in both figures.
"""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from ..runtime import Execution, write_json


def plot_audit(ctx: Execution, stage: str) -> None:
    plt.rcParams.update({"font.family": "sans-serif", "font.sans-serif": ["Arial", "DejaVu Sans"],
                         "font.size": 7, "svg.fonttype": "none", "pdf.fonttype": 42,
                         "axes.spines.top": False, "axes.spines.right": False, "axes.linewidth": .7,
                         "legend.frameon": False})
    fig, axes = plt.subplots(1, 2, figsize=(7.2047244, 3.4645669))  # 183 x 88 mm
    fig.subplots_adjust(left=.1, right=.97, bottom=.25, top=.82, wspace=.43)
    if stage == "M01":
        source = pd.read_csv(ctx.output_dir / "validation/01_technical_quality.csv")
        variables = list(source["variable"].unique())
        x = np.arange(len(variables))
        splits = ["development", "validation", "terminal_test"]
        for i, (split, color) in enumerate(zip(splits, ["#4C78A8", "#72A9A1", "#B7BCC4"])):
            sub = source[source["split"] == split].set_index("variable").reindex(variables)
            percent = 100 * sub["technical_valid_rows"] / sub["archive_rows"]
            axes[0].bar(x + (i - 1) * .25, percent, width=.25, color=color, label=split.replace("terminal_", ""))
        axes[0].set_xticks(x, variables, rotation=55, ha="right")
        axes[0].set_ylabel("Technically valid archive rows (%)")
        axes[0].set_ylim(0, 105)
        axes[0].legend(loc="lower left", fontsize=6)
        frequency = pd.read_csv(ctx.output_dir / "validation/01_native_frequency.csv")
        axes[1].bar(np.arange(len(frequency)), 100 * frequency["unchanged_adjacent_fraction"], color="#4C78A8")
        axes[1].set_xticks(np.arange(len(frequency)), frequency["variable"], rotation=55, ha="right")
        axes[1].set_ylabel("Unchanged adjacent valid pairs (%)")
        axes[1].set_ylim(0, 105)
        axes[1].set_title("Development archive patterns", fontsize=8)
        ctx.output("figures/M01_frequency_source.csv").write_bytes((ctx.output_dir / "validation/01_native_frequency.csv").read_bytes())
        title = "Archive audit | Native refresh UNKNOWN"
        caption = "a，三切分机械有效行比例；b，开发集相邻有效档案值未改变比例。不是保持率、刷新周期或独立测量数。全七通道均保留；无推断检验和独立重复数。"
    else:
        source = pd.read_csv(ctx.output_dir / "validation/02_scale_comparison.csv")
        for profile, color, marker in [("Q_COD_T", "#4C78A8", "o"), ("Q_COD_NH4_TN_T", "#72A9A1", "s")]:
            sub = source[source["support_profile"] == profile]
            label = "Q/COD/T" if profile == "Q_COD_T" else "Q/COD/NH4/TN/T"
            y = 100 * sub["full_technical_archive_bins"] / sub["nominal_archive_bins"]
            axes[0].plot(sub["step_minutes"], y, marker=marker, color=color, label=label)
            axes[1].plot(sub["step_minutes"], sub["median_abs_C_FW_minus_C_TW"], marker=marker, color=color)
        for ax in axes:
            ax.set_xticks([5, 15, 60])
            ax.set_xlabel("Candidate bin width (min)")
        axes[0].set_ylabel("Full technical archive bins (%)")
        axes[0].set_ylim(0, 105)
        axes[0].legend(loc="lower left", fontsize=6)
        axes[1].set_ylabel("Median |C_FW - C_TW| (mg/L)")
        title = "Development archive arithmetic | Main step PENDING"
        caption = "a，两种共同支持下完整技术档案窗口比例；b，相应全部浓度变量合并的 |C_FW−C_TW| 中位数，仅展示两个视图不相等。跨支持不作物理效果比较；无原生峰损失或尺度优选主张。"
    source.to_csv(ctx.output(f"figures/{stage}_audit_source.csv"), index=False, encoding="utf-8-sig")
    for label, ax in zip(["a", "b"], axes):
        ax.text(-.16, 1.05, label, transform=ax.transAxes, fontweight="bold", fontsize=9)
    fig.suptitle(title, fontsize=9, y=.95)
    fig.savefig(ctx.output(f"figures/{stage}_audit.svg"))
    fig.savefig(ctx.output(f"figures/{stage}_audit.pdf"))
    fig.savefig(ctx.output(f"figures/{stage}_audit.png"), dpi=600)
    plt.close(fig)
    write_json(ctx.output(f"figures/{stage}_figure_qa.json"), {**ctx.metadata(), "backend": "python",
               "archetype": "quantitative_grid", "size_mm": [183, 88], "editable_text": True,
               "caption_zh": caption, "independent_replicates": "UNKNOWN; archive rows are not independent observations",
               "inferential_statistics": "not_applicable; descriptive technical audit only",
               "data_exclusion": "M01 all seven mapped channels; M02 development only per protocol, technical common support explicitly tabulated",
               "visual_inspection": "PENDING", "scientific_admission": "PENDING"})
