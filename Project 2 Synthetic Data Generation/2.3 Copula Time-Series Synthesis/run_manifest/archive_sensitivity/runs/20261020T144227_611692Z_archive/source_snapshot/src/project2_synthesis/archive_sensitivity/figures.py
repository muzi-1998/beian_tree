"""All-case archive diagnostics, with no scientific selection or confidence claims.

Contract: expose failures of synchronous/temporal fidelity under the authorized
retrospective context. Quantitative grid: joint tau, Q ACF and COD ACF errors at
one physical hour. Separate identity/log1p figures include all successful cases;
failures remain in the failure ledger. 183 x 133 mm; editable SVG/PDF + 600 dpi
PNG and full CSV Source Data. Seed medians are descriptive, not confidence bounds.
"""
from __future__ import annotations

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from ..runtime import write_json


def plot_diagnostics(run, diagnostics: pd.DataFrame) -> list[str]:
    if diagnostics.empty:
        raise ValueError("No successful trajectories to plot; do not generate a placeholder figure")
    plt.rcParams.update({"font.family": "sans-serif", "font.sans-serif": ["Arial", "DejaVu Sans"],
                         "font.size": 7, "svg.fonttype": "none", "pdf.fonttype": 42,
                         "axes.spines.top": False, "axes.spines.right": False, "legend.frameon": False})
    source = diagnostics.copy()
    for variable in ["Q", "COD"]:
        source[f"{variable}_acf_abs_error"] = (source[f"{variable}_acf_60m_synthetic"] - source[f"{variable}_acf_60m_reference"]).abs()
    source.to_csv(run.path("figures/archive_diagnostics_source.csv"), index=False, encoding="utf-8-sig")
    files = ["figures/archive_diagnostics_source.csv"]
    metrics = [("tau_abs_error", "|Joint tau difference|"), ("Q_acf_abs_error", "|Q ACF difference, 1 h|"),
               ("COD_acf_abs_error", "|COD ACF difference, 1 h|")]
    for kind in run.config["transform_candidates"]:
        fig, axes = plt.subplots(3, 1, figsize=(7.2047244, 5.2362205), sharex=True)
        fig.subplots_adjust(left=.14, right=.96, bottom=.10, top=.80, hspace=.32)
        sub = source[source["transform"] == kind]
        grouped = sub.groupby(["family", "p", "step_minutes"])[[m[0] for m in metrics]].median()
        for family, color in [("independence", "#8A8F98"), ("Gaussian", "#4C78A8"), ("Student_t", "#72A9A1")]:
            for order, marker, style in [(0, "o", "--"), (1, "s", "-")]:
                if (family, order) not in grouped.index.droplevel("step_minutes"):
                    continue
                values = grouped.loc[(family, order)]
                for ax, (metric, label) in zip(axes, metrics):
                    ax.plot(values.index, values[metric], marker=marker, linestyle=style, color=color,
                            linewidth=1., markersize=3., label=f"{family.replace('_', ' ')} / AR{order}")
                    ax.set_ylabel(label)
        for letter, ax in zip("abc", axes):
            ax.text(-.13, 1., letter, transform=ax.transAxes, fontweight="bold", fontsize=9)
            ax.set_xticks([5, 15, 60])
        axes[-1].set_xlabel("Archive bin width (min); no primary step selected")
        handles, labels = axes[0].get_legend_handles_labels()
        fig.legend(handles, labels, ncol=3, loc="upper center", bbox_to_anchor=(.55, .93), fontsize=6)
        fig.suptitle(f"Archive-only conditional pilot | {kind} | native refresh UNKNOWN", fontsize=9, y=.99)
        name = f"figures/archive_diagnostics_{kind}"
        fig.savefig(run.path(name + ".svg"))
        fig.savefig(run.path(name + ".pdf"))
        fig.savefig(run.path(name + ".png"), dpi=600)
        plt.close(fig)
        files.extend([name + ext for ext in [".svg", ".pdf", ".png"]])
    write_json(run.path("figures/figure_contract.json"), {
        "purpose": "archive_sensitivity", "native_support": "UNKNOWN", "archetype": "quantitative_grid",
        "size_mm": [183, 133], "backend": "python", "seed_statistic": "median_of_three_exploratory_draws; no CI",
        "source_rows": len(source), "before_exclusion": "all configured trajectories in trajectory_manifest.csv",
        "exclusion": "only failed trajectories lack numerical curves; all failures retained in ledger",
        "caption_zh": "仅相同开发期30日日历条件下的档案描述。a，同期Kendall tau差异；b、c，Q与COD一小时自相关差异。展示三尺度、两变换、两AR阶及三Copula；不选赢家，不代表独立测试、真实事件保真或过程响应。",
        "visual_QA": "PENDING", "scientific_admission": "PENDING"})
    files.append("figures/figure_contract.json")
    return files
