from __future__ import annotations

from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from d5_common.config import D5_ROOT, resolve_paths


COLORS = {
    "full_reference": "#168AAD",
    "no_exogenous_context": "#E9C46A",
    "no_regime_conditioning": "#D1495B",
    "no_hysteresis": "#6C757D",
    "raw": "#168AAD",
    "report": "#D1495B",
    "Top1": "#D1495B",
    "Top2": "#168AAD",
    "MRR": "#2A9D8F",
    "AUPRC": "#2A9D8F",
}


class D5PublicationFigureBuilder:
    def __init__(self) -> None:
        self.paths = resolve_paths()
        self.audit_root = D5_ROOT / "outputs" / "publication"
        self.paths.figure_root.mkdir(parents=True, exist_ok=True)
        self._configure_style()

    @staticmethod
    def _configure_style() -> None:
        mpl.rcParams.update(
            {
                "font.family": "Arial",
                "font.size": 7.5,
                "axes.labelsize": 8,
                "axes.titlesize": 8.5,
                "axes.titleweight": "bold",
                "axes.titlepad": 6,
                "axes.linewidth": 0.8,
                "xtick.labelsize": 7,
                "ytick.labelsize": 7,
                "xtick.major.width": 0.8,
                "ytick.major.width": 0.8,
                "xtick.direction": "in",
                "ytick.direction": "in",
                "xtick.top": True,
                "ytick.right": True,
                "legend.fontsize": 6.8,
                "legend.frameon": False,
                "svg.fonttype": "none",
                "pdf.fonttype": 42,
            }
        )

    def build_all(self) -> list[Path]:
        outputs = []
        outputs.extend(self._validation_coverage())
        outputs.extend(self._complementarity())
        return outputs

    @staticmethod
    def _panel_label(ax: plt.Axes, label: str) -> None:
        ax.text(
            -0.10,
            1.02,
            f"({label})",
            transform=ax.transAxes,
            fontsize=9,
            fontweight="bold",
            ha="right",
            va="bottom",
            clip_on=False,
            bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.88, "pad": 0.1},
        )

    @staticmethod
    def _boxed(ax: plt.Axes) -> None:
        for spine in ax.spines.values():
            spine.set_visible(True)
            spine.set_linewidth(0.8)
        ax.tick_params(which="both", direction="in", top=True, right=True, width=0.8)

    def _save(self, fig: plt.Figure, stem: str) -> list[Path]:
        png = self.paths.figure_root / f"{stem}.png"
        pdf = self.paths.figure_root / f"{stem}.pdf"
        svg = self.paths.figure_root / f"{stem}.svg"
        tiff = self.paths.figure_root / f"{stem}.tiff"
        fig.savefig(png, dpi=600, bbox_inches="tight", facecolor="white")
        fig.savefig(pdf, bbox_inches="tight", facecolor="white")
        fig.savefig(svg, bbox_inches="tight", facecolor="white")
        svg.write_text(
            "\n".join(
                line.rstrip()
                for line in svg.read_text(encoding="utf-8").splitlines()
            )
            + "\n",
            encoding="utf-8",
        )
        fig.savefig(
            tiff,
            dpi=600,
            bbox_inches="tight",
            facecolor="white",
            pil_kwargs={"compression": "tiff_lzw"},
        )
        plt.close(fig)
        return [png, pdf, svg, tiff]

    def _validation_coverage(self) -> list[Path]:
        outer = pd.read_parquet(self.audit_root / "D5_outer_refit_summary.parquet")
        localization = pd.read_parquet(self.audit_root / "D5_localization.parquet")
        monthly = pd.read_parquet(self.audit_root / "D5_monthly_coverage.parquet")
        risk = pd.read_parquet(self.audit_root / "D5_risk_coverage.parquet")
        source = self.audit_root / "FigD5_6_validation_coverage_source_data.xlsx"
        with pd.ExcelWriter(source, engine="openpyxl") as writer:
            outer.to_excel(writer, sheet_name="outer_refit", index=False)
            localization.to_excel(writer, sheet_name="localization", index=False)
            monthly.to_excel(writer, sheet_name="monthly_coverage", index=False)
            risk.to_excel(writer, sheet_name="risk_coverage", index=False)

        fig, axes = plt.subplots(2, 2, figsize=(7.2, 5.5), constrained_layout=True)
        ax = axes[0, 0]
        variants = [
            "full_reference",
            "no_exogenous_context",
            "no_regime_conditioning",
            "no_hysteresis",
        ]
        labels = ["Full", "No exogenous", "No regime", "No hysteresis"]
        offsets = {"AUROC": -0.18, "AUPRC": 0.0, "Top1": 0.18}
        markers = {"AUROC": "o", "AUPRC": "s", "Top1": "^"}
        for metric, offset in offsets.items():
            frame = outer[outer["metric"].eq(metric)].set_index("variant").loc[variants]
            x = np.arange(len(variants)) + offset
            ax.errorbar(
                x,
                frame["estimate"],
                yerr=[frame["estimate"] - frame["ci95_low"], frame["ci95_high"] - frame["estimate"]],
                fmt=markers[metric],
                ms=4.2,
                capsize=2,
                lw=0.9,
                color=COLORS["full_reference"] if metric == "AUROC" else COLORS[metric],
                label=metric,
            )
        ax.axhline(0.80, color="#8A8A8A", ls="--", lw=0.8)
        ax.set_xticks(np.arange(len(variants)), labels, rotation=18, ha="right")
        ax.set_ylim(0.55, 1.02)
        ax.set_ylabel("Validation metric")
        ax.set_title("Future-month structural refits")
        ax.legend(loc="lower left", ncol=3)
        self._boxed(ax)
        self._panel_label(ax, "a")

        ax = axes[0, 1]
        frame = localization[
            localization["analyte"].eq("all")
            & localization["scenario"].isin(
                ["channel_swap", "role_substitution", "role_offset"]
            )
            & localization["metric"].isin(["Top1", "Top2", "MRR"])
        ].copy()
        scenarios = ["channel_swap", "role_substitution", "role_offset"]
        scenario_labels = ["Channel swap", "Role substitution", "Role offset"]
        for index, metric in enumerate(["Top1", "Top2", "MRR"]):
            metric_frame = frame[frame["metric"].eq(metric)].set_index("scenario").loc[scenarios]
            x = np.arange(len(scenarios)) + (index - 1) * 0.22
            ax.errorbar(
                x,
                metric_frame["estimate"],
                yerr=[
                    metric_frame["estimate"] - metric_frame["ci95_low"],
                    metric_frame["ci95_high"] - metric_frame["estimate"],
                ],
                fmt=["o", "s", "^"][index],
                color=COLORS[metric],
                ms=4.2,
                capsize=2,
                lw=0.9,
                label=metric,
            )
        ax.axhline(0.80, color="#8A8A8A", ls="--", lw=0.8)
        ax.set_xticks(np.arange(len(scenarios)), scenario_labels, rotation=16, ha="right")
        ax.set_ylim(0.25, 1.02)
        ax.set_ylabel("Localization performance")
        ax.set_title("Detection and localization boundary")
        ax.legend(loc="lower left", ncol=3)
        self._boxed(ax)
        self._panel_label(ax, "b")

        ax = axes[1, 0]
        x = np.arange(len(monthly))
        ax.plot(x, monthly["raw_score_coverage"], marker="o", ms=3.5, color=COLORS["raw"], label="Raw score")
        ax.plot(x, monthly["report_score_coverage"], marker="s", ms=3.5, color=COLORS["report"], label="Report score")
        ax.fill_between(x, 0, monthly["L1_rate"], color="#E76F51", alpha=0.16, label="L1 support")
        ax.set_xticks(x, monthly["month"].str.replace("-", "\n", regex=False))
        ax.set_ylim(0, 1.02)
        ax.set_ylabel("Fraction of sensor-hours")
        ax.set_xlabel("Calendar month")
        ax.set_title("Evidence coverage migration")
        ax.legend(loc="lower left", ncol=3)
        self._boxed(ax)
        self._panel_label(ax, "c")

        ax = axes[1, 1]
        risk_colors = {"top1": COLORS["Top1"], "top2": COLORS["Top2"], "mrr": COLORS["MRR"]}
        for metric, marker in [("top1", "o"), ("top2", "s"), ("mrr", "^")]:
            ax.plot(
                risk["retained_fraction"],
                risk[metric],
                marker=marker,
                ms=4,
                color=risk_colors[metric],
                label=metric.upper(),
            )
        ax.axhline(0.80, color="#8A8A8A", ls="--", lw=0.8)
        ax.set_xlim(1.02, 0.35)
        ax.set_ylim(0.45, 1.02)
        ax.set_xlabel("Retained controlled-injection trials")
        ax.set_ylabel("Localization performance")
        ax.set_title("Confidence-risk coverage")
        ax.legend(loc="lower right", ncol=3)
        self._boxed(ax)
        self._panel_label(ax, "d")
        return self._save(fig, "FigD5_6_validation_coverage")

    def _complementarity(self) -> list[Path]:
        dependence = pd.read_parquet(self.audit_root / "D5_d4_d5_dependence.parquet")
        composite = pd.read_parquet(self.audit_root / "D5_d4_d5_composite.parquet")
        influence = pd.read_parquet(self.audit_root / "D5_target_influence.parquet")
        support = pd.read_parquet(self.audit_root / "D5_support_sensitivity.parquet")
        source = self.audit_root / "FigD5_7_D4_D5_complementarity_source_data.xlsx"
        with pd.ExcelWriter(source, engine="openpyxl") as writer:
            dependence.to_excel(writer, sheet_name="dependence", index=False)
            composite.to_excel(writer, sheet_name="composite_ablation", index=False)
            influence.to_excel(writer, sheet_name="target_influence", index=False)
            support.to_excel(writer, sheet_name="support_sensitivity", index=False)

        fig, axes = plt.subplots(2, 2, figsize=(7.2, 5.45), constrained_layout=True)
        ax = axes[0, 0]
        metrics = ["Spearman_rho", "Kendall_tau", "partial_rank_correlation", "low_score_Jaccard"]
        labels = ["Spearman", "Kendall", "Partial rank", "Low-score\nJaccard"]
        frame = dependence.set_index("metric").loc[metrics]
        x = np.arange(len(frame))
        lower = (frame["estimate"] - frame["ci95_low"]).fillna(0)
        upper = (frame["ci95_high"] - frame["estimate"]).fillna(0)
        ax.errorbar(x, frame["estimate"], yerr=[lower, upper], fmt="o", color="#168AAD", capsize=2, lw=0.9)
        ax.axhline(0, color="#8A8A8A", lw=0.7)
        ax.set_xticks(x, labels)
        ax.set_ylim(-0.05, max(0.45, frame["estimate"].max() + 0.12))
        ax.set_ylabel("Association estimate")
        ax.set_title("D4-D5 relatedness")
        self._boxed(ax)
        self._panel_label(ax, "a")

        ax = axes[0, 1]
        y = np.arange(len(composite))
        ax.scatter(composite["spearman_vs_full"], y, color="#2A9D8F", s=30, label="Rank agreement")
        for ypos, row in zip(y, composite.itertuples(index=False)):
            ax.plot([0, row.spearman_vs_full], [ypos, ypos], color="#A8B0B8", lw=0.8, zorder=0)
            ax.text(row.spearman_vs_full + 0.015, ypos, f"P90 |Δ|={row.p90_absolute_change:.2f}", va="center", fontsize=6.5)
        ax.set_yticks(y, composite["variant"].str.replace("_", " ", regex=False))
        ax.set_xlim(0, 1.08)
        ax.set_xlabel("Spearman correlation with full pair score")
        ax.set_title("Composite leave-one-dimension sensitivity")
        self._boxed(ax)
        self._panel_label(ax, "b")

        ax = axes[1, 0]
        order = influence.sort_values(["analyte", "target_sensor"])
        x = np.arange(len(order))
        ax.plot(x, order["observed_map_disagreement_rate"], marker="o", ms=3.2, color="#168AAD", label="Leave-one-target-out")
        ax.plot(x, order["injected_ood_rate_change"], marker="s", ms=3.2, color="#D1495B", label="2.5-MAD offset: ΔOOD")
        ax.set_xticks(x, order["target_sensor"].str.replace("_", "-", regex=False), rotation=55, ha="right")
        ax.set_ylim(bottom=0)
        ax.set_ylabel("Fraction of 10-min contexts")
        ax.set_title("Bounded target influence")
        ax.legend(loc="upper left")
        self._boxed(ax)
        self._panel_label(ax, "c")

        ax = axes[1, 1]
        selected = support[
            support["L3_min_reference_coverage"].eq(0.80)
        ].copy()
        pivot = selected.pivot_table(
            index="L3_min_bootstrap_stability",
            columns="n_effective_multiplier",
            values="L3_templates",
            aggfunc="median",
        ).sort_index(ascending=False)
        image = ax.imshow(pivot, cmap="YlGnBu", vmin=0, vmax=max(3, float(pivot.max().max())), aspect="auto")
        for row in range(pivot.shape[0]):
            for column in range(pivot.shape[1]):
                ax.text(column, row, f"{pivot.iloc[row, column]:.0f}", ha="center", va="center", fontsize=7)
        ax.set_xticks(np.arange(pivot.shape[1]), [f"{value:.1f}x" for value in pivot.columns])
        ax.set_yticks(np.arange(pivot.shape[0]), [f"{value:.2f}" for value in pivot.index])
        ax.set_xlabel("Effective-block threshold")
        ax.set_ylabel("L3 stability threshold")
        ax.set_title("L3 support sensitivity")
        colorbar = fig.colorbar(image, ax=ax, fraction=0.045, pad=0.025)
        colorbar.set_label("L3 templates")
        self._boxed(ax)
        self._panel_label(ax, "d")
        return self._save(fig, "FigD5_7_D4_D5_complementarity")
