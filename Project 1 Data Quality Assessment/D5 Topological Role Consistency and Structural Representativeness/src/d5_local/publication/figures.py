from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np
import pandas as pd

from d5_common.config import D5_ROOT, resolve_paths
from d5_local.figures.figure_style import (
    PALETTE,
    PROFILE,
    configure_style,
    panel_label,
    save_figure,
    style_axes,
)


# Source-visible publication contract; execution is centralized in figure_style.py.
NATURE_WIDTH_MM = 183.0
NATURE_RASTER_DPI = 600
NATURE_PREFLIGHT_CONTRACT = {
    "font.family": "Arial",
    "font.size": 7.0,
    "svg.fonttype": "none",
    "pdf.fonttype": 42,
    "vector_exports": (".svg", ".pdf"),
    "raster_exports": (".png", ".tiff"),
}


COLORS = {
    "full_reference": PALETTE["blue"],
    "no_exogenous_context": PALETTE["gold"],
    "no_regime_conditioning": PALETTE["red"],
    "no_hysteresis": PALETTE["gray"],
    "raw": PALETTE["blue"],
    "report": PALETTE["red"],
    "Top1": PALETTE["red"],
    "Top2": PALETTE["blue"],
    "MRR": PALETTE["teal"],
    "AUPRC": PALETTE["teal"],
}


class D5PublicationFigureBuilder:
    def __init__(self) -> None:
        self.paths = resolve_paths()
        self.audit_root = D5_ROOT / "outputs" / "publication"
        self.paths.figure_root.mkdir(parents=True, exist_ok=True)
        configure_style()

    def build_all(self) -> list[Path]:
        outputs = []
        outputs.extend(self._validation_coverage())
        outputs.extend(self._complementarity())
        outputs.extend(self._dimension_availability())
        outputs.extend(self._target_support_robustness())
        return outputs

    @staticmethod
    def _panel_label(ax: plt.Axes, label: str) -> None:
        panel_label(ax, label)

    @staticmethod
    def _boxed(ax: plt.Axes) -> None:
        style_axes(ax, boxed=True)

    @staticmethod
    def _open(ax: plt.Axes) -> None:
        style_axes(ax, boxed=False)

    def _save(self, fig: plt.Figure, stem: str) -> list[Path]:
        return save_figure(fig, self.paths.figure_root, stem)

    def _validation_coverage(self) -> list[Path]:
        outer = pd.read_parquet(self.audit_root / "D5_outer_refit_summary.parquet")
        localization = pd.read_parquet(self.audit_root / "D5_localization.parquet")
        monthly = pd.read_parquet(self.audit_root / "D5_monthly_coverage.parquet")
        risk = pd.read_parquet(self.audit_root / "D5_risk_coverage.parquet")
        trials = pd.read_excel(
            self.paths.local_output_root / "D5_validation_results.xlsx",
            sheet_name="injection_trials",
        )
        hops = (
            trials.assign(
                hop_class=np.select(
                    [trials["topological_hop_error"].eq(0), trials["topological_hop_error"].eq(1)],
                    ["0 (correct node)", "1 hop"],
                    default="2+ hops",
                )
            )["hop_class"]
            .value_counts()
            .reindex(["0 (correct node)", "1 hop", "2+ hops"], fill_value=0)
            .rename_axis("hop_class")
            .reset_index(name="n_trials")
        )
        hops["fraction"] = hops["n_trials"] / len(trials)
        source = self.audit_root / "FigD5_6_validation_coverage_source_data.xlsx"
        with pd.ExcelWriter(source, engine="openpyxl") as writer:
            outer.to_excel(writer, sheet_name="outer_refit", index=False)
            localization.to_excel(writer, sheet_name="localization", index=False)
            hops.to_excel(writer, sheet_name="topological_hops", index=False)
            monthly.to_excel(writer, sheet_name="monthly_coverage", index=False)
            risk.to_excel(writer, sheet_name="risk_coverage", index=False)

        fig = plt.figure(figsize=(PROFILE.width_in, 5.45), layout="constrained")
        grid = fig.add_gridspec(2, 2)
        ax = fig.add_subplot(grid[0, 0])
        variants = [
            "full_reference",
            "no_exogenous_context",
            "no_regime_conditioning",
            "no_hysteresis",
        ]
        labels = ["Full", "No exogenous", "No regime", "No hysteresis"]
        offsets = {"AUROC": -0.18, "AUPRC": 0.0, "Top1": 0.18}
        markers = {"AUROC": "o", "AUPRC": "s", "Top1": "^"}
        criteria = {"AUROC": 0.90, "AUPRC": 0.80, "Top1": 0.80}
        for metric, offset in offsets.items():
            frame = outer[outer["metric"].eq(metric)].set_index("variant").loc[variants]
            x = np.arange(len(variants)) + offset
            estimate = frame["estimate"] - criteria[metric]
            low = frame["ci95_low"] - criteria[metric]
            high = frame["ci95_high"] - criteria[metric]
            ax.errorbar(
                x,
                estimate,
                yerr=[
                    estimate - low,
                    high - estimate,
                ],
                fmt=markers[metric],
                ms=4.2,
                capsize=2,
                lw=0.9,
                color=(
                    COLORS["full_reference"]
                    if metric == "AUROC"
                    else COLORS[metric]
                ),
                label=metric,
            )
        ax.axhline(0, color=PALETTE["gray"], ls="--", lw=0.8)
        ax.set_xticks(np.arange(len(variants)), labels, rotation=18, ha="right")
        ax.set_ylabel("Estimate minus prespecified criterion")
        ax.set_title("Future-month criterion margins")
        ax.legend(loc="lower left", ncol=3)
        ax.text(0.98, 0.03, "n = 6 outer month folds", transform=ax.transAxes, ha="right", va="bottom", fontsize=5.4, color=PALETTE["gray"])
        self._open(ax)
        self._panel_label(ax, "a")

        localization_grid = grid[0, 1].subgridspec(1, 2, width_ratios=[1.35, 0.85], wspace=0.10)
        ax = fig.add_subplot(localization_grid[0, 0])
        frame = localization[
            localization["analyte"].eq("all")
            & localization["scenario"].isin(
                ["channel_swap", "role_substitution", "role_offset"]
            )
            & localization["metric"].eq("Top1")
        ].copy()
        scenarios = ["channel_swap", "role_substitution", "role_offset"]
        scenario_labels = ["Channel swap", "Role substitution", "Role offset"]
        frame = frame.set_index("scenario").loc[scenarios]
        y = np.arange(len(scenarios))
        ax.errorbar(
            frame["estimate"], y,
            xerr=[frame["estimate"] - frame["ci95_low"], frame["ci95_high"] - frame["estimate"]],
            fmt="o", color=COLORS["Top1"], ms=4.2, capsize=2, lw=0.9,
        )
        ax.axvline(0.80, color=PALETTE["gray"], ls="--", lw=0.8)
        ax.set_yticks(y, scenario_labels)
        ax.invert_yaxis()
        ax.set_xlim(0.25, 1.02)
        ax.set_xlabel("Top-1 localization")
        ax.set_title("Top-1 localization")
        self._open(ax)
        self._panel_label(ax, "b")

        hop_ax = fig.add_subplot(localization_grid[0, 1])
        hop_ax.barh(hops["hop_class"], hops["fraction"], color=[PALETTE["teal"], PALETTE["gold"], PALETTE["red"]], edgecolor="white")
        for ypos, row in enumerate(hops.itertuples(index=False)):
            hop_ax.text(row.fraction + 0.015, ypos, f"{row.fraction:.0%}\n(n={row.n_trials})", va="center", fontsize=5.2)
        hop_ax.set_xlim(0, max(0.8, float(hops["fraction"].max()) * 1.22))
        hop_ax.set_xlabel("Trial fraction")
        hop_ax.set_title("Hop error")
        self._open(hop_ax)

        ax = fig.add_subplot(grid[1, 0])
        x = np.arange(len(monthly))
        ax.plot(
            x,
            monthly["raw_score_coverage"],
            marker="o",
            ms=3.5,
            color=COLORS["raw"],
            label="Raw score",
        )
        ax.plot(
            x,
            monthly["report_score_coverage"],
            marker="s",
            ms=3.5,
            color=COLORS["report"],
            label="Report score",
        )
        ax.plot(
            x,
            monthly["ood_rate"],
            marker="^",
            ms=3.5,
            color=PALETTE["red"],
            ls=(0, (3, 2)),
            label="Out of template",
        )
        ax.fill_between(
            x,
            0,
            monthly["L1_rate"],
            color=PALETTE["gold"],
            alpha=0.16,
            label="L1 support",
        )
        ax.set_xticks(x, monthly["month"].str.replace("-", "\n", regex=False))
        ax.set_ylim(0, 1.02)
        ax.set_ylabel("Fraction of sensor-hours")
        ax.set_xlabel("Calendar month")
        ax.set_title("Evidence coverage and OOD")
        ax.legend(loc="upper center", ncol=2)
        self._open(ax)
        self._panel_label(ax, "c")

        ax = fig.add_subplot(grid[1, 1])
        ax.errorbar(
            risk["retained_fraction"], risk["top1"],
            yerr=[risk["top1"] - risk["top1_ci95_low"], risk["top1_ci95_high"] - risk["top1"]],
            marker="o", ms=4, color=COLORS["Top1"], capsize=2, lw=1.0,
        )
        ax.axhline(0.80, color=PALETTE["gray"], ls="--", lw=0.8)
        for row in risk.itertuples(index=False):
            ax.text(row.retained_fraction, row.top1_ci95_high + 0.025, f"n={row.n_trials}", ha="center", va="bottom", fontsize=5.2)
        ax.set_xlim(1.02, 0.35)
        ax.set_ylim(0.30, 1.02)
        ax.set_xlabel("Retained controlled perturbations")
        ax.set_ylabel("Top-1 localization")
        ax.set_title("Selective localization sensitivity")
        ax.text(
            0.03, 0.04, "Confidence is not calibrated\nfor selective localization",
            transform=ax.transAxes, ha="left", va="bottom", fontsize=5.3,
            bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.82, "pad": 0.25},
        )
        self._open(ax)
        self._panel_label(ax, "d")
        return self._save(fig, "FigD5_6_validation_coverage")

    def _complementarity(self) -> list[Path]:
        dependence = pd.read_parquet(
            self.audit_root / "D5_d4_d5_dependence.parquet"
        )
        stratified = pd.read_parquet(
            self.audit_root / "D5_d4_d5_stratified_rho.parquet"
        )
        composite = pd.read_parquet(
            self.audit_root / "D5_d4_d5_composite.parquet"
        )
        joint = pd.read_parquet(
            self.audit_root / "D5_d4_d5_joint_sample.parquet"
        )
        low_tail = pd.read_parquet(
            self.audit_root / "D5_d4_d5_low_tail_overlap.parquet"
        )
        source = self.audit_root / "FigD5_7_D4_D5_complementarity_source_data.xlsx"
        with pd.ExcelWriter(source, engine="openpyxl") as writer:
            dependence.to_excel(writer, sheet_name="dependence", index=False)
            stratified.to_excel(writer, sheet_name="stratified_rho", index=False)
            joint.to_excel(writer, sheet_name="joint_density_sample", index=False)
            low_tail.to_excel(writer, sheet_name="low_tail_overlap", index=False)
            composite.to_excel(writer, sheet_name="composite_ablation", index=False)

        fig, axes = plt.subplots(2, 2, figsize=(PROFILE.width_in, 6.05), layout="constrained")
        ax = axes[0, 0]
        report_joint = joint[joint["overlap_scope"].eq("D5_report_score")]
        density = ax.hexbin(
            report_joint["D4_raw"], report_joint["D5_score"], gridsize=28,
            extent=(1, 5, 1, 5), mincnt=1, bins="log", cmap="Blues",
        )
        ax.axvline(3.0, color=PALETTE["gray"], lw=0.7, ls="--")
        ax.axhline(3.0, color=PALETTE["gray"], lw=0.7, ls="--")
        report_metrics = dependence[dependence["overlap_scope"].eq("D5_report_score")].set_index("metric")
        raw_metrics = dependence[dependence["overlap_scope"].eq("D5_raw_calculable")].set_index("metric")
        ax.text(
            0.03, 0.97,
            "Report rho = " + f"{report_metrics.loc['Spearman_rho', 'estimate']:.3f}\n"
            + "Raw rho = " + f"{raw_metrics.loc['Spearman_rho', 'estimate']:.3f}\n"
            + "Partial rank (descriptive) = " + f"{report_metrics.loc['partial_rank_correlation', 'estimate']:.3f}",
            transform=ax.transAxes, ha="left", va="top", fontsize=5.4,
            bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.82, "pad": 0.25},
        )
        ax.set_xlim(1, 5)
        ax.set_ylim(1, 5)
        ax.set_xlabel("D4 raw")
        ax.set_ylabel("D5 pair report score")
        ax.set_title("Joint D4-D5 score structure")
        colorbar = fig.colorbar(density, ax=ax, fraction=0.045, pad=0.02)
        colorbar.set_label("Pair-hours per hexagon (log)")
        self._boxed(ax)
        self._panel_label(ax, "a")

        self._plot_stratified_rho(
            axes[0, 1], stratified, ["analyte", "pair"], "Analyte and pair strata"
        )
        self._panel_label(axes[0, 1], "b")
        self._plot_stratified_rho(
            axes[1, 0], stratified, ["regime", "month"], "Regime and month strata"
        )
        self._panel_label(axes[1, 0], "c")

        ax = axes[1, 1]
        overlap = low_tail[low_tail["overlap_scope"].eq("D5_report_score")].set_index("category")
        category_matrix = np.array(
            [
                [overlap.loc["neither_low", "fraction"], overlap.loc["D5_only_low", "fraction"]],
                [overlap.loc["D4_only_low", "fraction"], overlap.loc["both_low", "fraction"]],
            ]
        )
        count_matrix = np.array(
            [
                [overlap.loc["neither_low", "count"], overlap.loc["D5_only_low", "count"]],
                [overlap.loc["D4_only_low", "count"], overlap.loc["both_low", "count"]],
            ]
        )
        image = ax.imshow(category_matrix, cmap="Blues", vmin=0, vmax=max(0.5, float(category_matrix.max())))
        for row in range(2):
            for column in range(2):
                ax.text(column, row, f"{category_matrix[row, column]:.1%}\n(n={count_matrix[row, column]:,})", ha="center", va="center", fontsize=6)
        ax.set_xticks([0, 1], ["D5 >= 3", "D5 < 3"])
        ax.set_yticks([0, 1], ["D4 >= 3", "D4 < 3"])
        ax.set_title("Low-tail overlap")
        ax.text(0.98, 0.02, "3 = analysis reference", transform=ax.transAxes, ha="right", va="bottom", fontsize=5.2, color=PALETTE["gray"])
        self._boxed(ax)
        self._panel_label(ax, "d")
        return self._save(fig, "FigD5_7_D4_D5_complementarity")

    def _plot_stratified_rho(
        self,
        ax: plt.Axes,
        stratified: pd.DataFrame,
        stratum_types: list[str],
        title: str,
    ) -> None:
        frame = stratified[
            stratified["stratum_type"].isin(stratum_types)
            & stratified["descriptive_estimable"]
        ].copy()
        frame["display"] = (
            frame["stratum_type"].str.title()
            + ": "
            + frame["stratum_value"].astype(str)
        )
        order = frame[["stratum_type", "stratum_value", "display"]].drop_duplicates()
        order["type_order"] = order["stratum_type"].map(
            {value: index for index, value in enumerate(stratum_types)}
        )
        order = order.sort_values(["type_order", "stratum_value"])
        labels = order["display"].tolist()
        y_positions = {label: index for index, label in enumerate(labels)}
        for scope, label, color, marker, offset in [
            ("D5_report_score", "Report score", COLORS["report"], "o", -0.12),
            ("D5_raw_calculable", "Raw calculable", COLORS["raw"], "s", 0.12),
        ]:
            selected = frame[frame["overlap_scope"].eq(scope)]
            for row in selected.itertuples(index=False):
                y = y_positions[row.display] + offset
                if row.inferential_estimable:
                    xerr = np.array(
                        [
                            [row.spearman_rho - row.ci95_low],
                            [row.ci95_high - row.spearman_rho],
                        ]
                    )
                    ax.errorbar(
                        row.spearman_rho,
                        y,
                        xerr=xerr,
                        fmt=marker,
                        color=color,
                        ms=3.2,
                        lw=0.7,
                        capsize=1.5,
                    )
                else:
                    ax.scatter(
                        row.spearman_rho,
                        y,
                        marker=marker,
                        facecolors="none",
                        edgecolors=color,
                        s=18,
                        linewidths=0.8,
                    )
        ax.axvspan(-0.30, 0.30, color=PALETTE["gray"], alpha=0.10, zorder=-2)
        ax.axvline(-0.30, color=PALETTE["gray"], lw=0.5, ls=":")
        ax.axvline(0.30, color=PALETTE["gray"], lw=0.5, ls=":")
        ax.axvline(0, color="#8A8A8A", lw=0.7)
        ax.set_yticks(np.arange(len(labels)), labels)
        ax.invert_yaxis()
        ax.set_xlim(-1.0, 1.0)
        ax.set_xlabel("Spearman rho")
        ax.set_title(title)
        ax.text(
            0.02,
            0.98,
            "Circle: report | square: raw\nOpen: descriptive only",
            transform=ax.transAxes,
            ha="left",
            va="top",
            fontsize=5.8,
            color="#5F6368",
            bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.85, "pad": 0.2},
        )
        self._open(ax)

    def _target_support_robustness(self) -> list[Path]:
        influence = pd.read_parquet(
            self.audit_root / "D5_target_influence.parquet"
        )
        support = pd.read_parquet(
            self.audit_root / "D5_support_sensitivity.parquet"
        )
        source = (
            self.audit_root
            / "FigD5_9_target_support_robustness_source_data.xlsx"
        )
        with pd.ExcelWriter(source, engine="openpyxl") as writer:
            influence.to_excel(writer, sheet_name="target_influence", index=False)
            support.to_excel(writer, sheet_name="support_sensitivity", index=False)

        fig = plt.figure(figsize=(PROFILE.width_in, 3.25), layout="constrained")
        grid = fig.add_gridspec(1, 2, width_ratios=[1.12, 1.0])
        ax = fig.add_subplot(grid[0, 0])
        order = influence.sort_values(["analyte", "target_sensor"])
        x = np.arange(len(order))
        ax.plot(
            x,
            order["observed_map_disagreement_rate"],
            marker="o",
            ms=3.2,
            color=COLORS["raw"],
            label="Regime disagreement: whole period",
        )
        ax.plot(
            x,
            order["postreference_map_disagreement_rate"],
            marker="o",
            markerfacecolor="white",
            ms=3.8,
            ls=(0, (3, 2)),
            color=COLORS["raw"],
            label="Regime disagreement: post-reference",
        )
        ax.plot(
            x,
            order["injected_ood_rate_change"],
            marker="s",
            ms=3.2,
            color=COLORS["report"],
            label="2.5-MAD offset: delta OOD",
        )
        ax.set_xticks(x, order["target_sensor"], rotation=55, ha="right")
        ax.set_ylim(bottom=0)
        ax.set_ylabel("Fraction of 10-min contexts")
        ax.set_title("Target-influence sensitivity")
        ax.legend(loc="upper left")
        self._open(ax)
        self._panel_label(ax, "a")

        sensitivity_grid = grid[0, 1].subgridspec(1, 3, wspace=0.08)
        vmax = max(3, float(support["L3_templates"].max()))
        image = None
        axes = []
        for index, coverage in enumerate([0.70, 0.80, 0.90]):
            ax = fig.add_subplot(sensitivity_grid[0, index])
            axes.append(ax)
            selected = support[np.isclose(support["L3_min_reference_coverage"], coverage)].copy()
            pivot = selected.pivot_table(
                index="L3_min_bootstrap_stability",
                columns="n_effective_multiplier",
                values="L3_templates",
                aggfunc="median",
            ).sort_index(ascending=False)
            image = ax.imshow(pivot, cmap="YlGnBu", vmin=0, vmax=vmax, aspect="auto")
            for row in range(pivot.shape[0]):
                for column in range(pivot.shape[1]):
                    ax.text(column, row, f"{pivot.iloc[row, column]:.0f}", ha="center", va="center", fontsize=6)
            ax.set_xticks(np.arange(pivot.shape[1]), [f"{value:.1f}x" for value in pivot.columns], rotation=35, ha="right")
            if index == 0:
                ax.set_yticks(np.arange(pivot.shape[0]), [f"{value:.2f}" for value in pivot.index])
                ax.set_ylabel("Stability threshold")
                ax.text(
                    -0.32,
                    1.015,
                    "(b)",
                    transform=ax.transAxes,
                    fontsize=PROFILE.panel_label_pt,
                    fontweight="bold",
                    va="bottom",
                    ha="right",
                    clip_on=False,
                )
            else:
                ax.set_yticks(np.arange(pivot.shape[0]), [])
            ax.set_xlabel("Effective blocks")
            ax.set_title(f"Coverage {coverage:.2f}")
            self._boxed(ax)
        colorbar = fig.colorbar(image, ax=axes, fraction=0.035, pad=0.018)
        colorbar.set_label("L3 templates")
        return self._save(fig, "FigD5_9_target_support_robustness")

    def _dimension_availability(self) -> list[Path]:
        table = pd.read_parquet(
            self.audit_root / "D5_dimension_availability.parquet"
        )
        monthly = table[~table["scope"].eq("overall")].copy()
        source = (
            self.audit_root
            / "FigD5_8_dimension_availability_sensitivity_source_data.xlsx"
        )
        with pd.ExcelWriter(source, engine="openpyxl") as writer:
            table.to_excel(writer, sheet_name="dimension_availability", index=False)

        x = np.arange(len(monthly))
        labels = [pd.Period(value).strftime("%b\n%Y") for value in monthly["scope"]]
        fig, axes = plt.subplots(2, 2, figsize=(PROFILE.width_in, 5.35), layout="constrained")

        ax = axes[0, 0]
        ax.plot(
            x,
            monthly["availability_aware_median"],
            marker="o",
            ms=3.5,
            color=COLORS["raw"],
            label="Availability-aware: all eligible",
        )
        ax.plot(x, monthly["fixed_dimension_median"], marker="s", ms=3.5, color=COLORS["report"], label="Fixed dimensions: complete evidence")
        ax.plot(
            x, monthly["availability_aware_complete_median"], marker="o", ms=5.0,
            markerfacecolor="none", markeredgecolor=COLORS["raw"], ls="none",
            label="Availability-aware on matched complete cases",
        )
        ax.set_xticks(x, labels)
        ax.set_ylim(1.0, 5.05)
        ax.set_ylabel("Monthly median WW-DQS sensitivity score")
        ax.set_title("Estimands are not interchangeable")
        ax.legend(loc="lower left")
        self._open(ax)
        self._panel_label(ax, "a")

        ax = axes[0, 1]
        for column, label, color, marker in [
            ("availability_aware_coverage", "Availability-aware", "#2A9D8F", "o"),
            ("complete_evidence_coverage", "Complete evidence", COLORS["report"], "s"),
            ("D5_available_rate", "D5 available", COLORS["raw"], "^"),
        ]:
            ax.plot(
                x, monthly[column], marker=marker, ms=3.5, color=color, label=label
            )
        ax.set_xticks(x, labels)
        ax.set_ylim(0, 1.02)
        ax.set_ylabel("Fraction of sensor-hours")
        ax.set_title("Dimension availability")
        ax.legend(loc="lower left")
        self._open(ax)
        self._panel_label(ax, "b")

        ax = axes[1, 0]
        bottom = np.zeros(len(monthly))
        for column, label, color in [
            ("dimension_1_rate", "1 dimension", "#D9E2E8"),
            ("dimension_2_rate", "2 dimensions", "#90C2D1"),
            ("dimension_3_rate", "3 dimensions", "#168AAD"),
        ]:
            values = monthly[column].to_numpy(float)
            ax.bar(x, values, bottom=bottom, color=color, width=0.72, label=label)
            bottom += values
        ax.set_xticks(x, labels)
        ax.set_ylim(0, 1.0)
        ax.set_ylabel("Fraction of sensor-hours")
        ax.set_title("Effective dimension count")
        ax.legend(
            loc="upper left",
            bbox_to_anchor=(0.0, -0.20),
            ncol=3,
            borderaxespad=0,
        )
        self._open(ax)
        self._panel_label(ax, "c")

        ax = axes[1, 1]
        shifts = monthly["descriptive_median_shift_all_minus_fixed"]
        colors = np.where(shifts.ge(0), "#2A9D8F", "#D1495B")
        ax.bar(x, shifts, color=colors, width=0.68)
        missing = shifts.isna().to_numpy()
        ax.scatter(x[missing], np.zeros(missing.sum()), marker="x", color="#6C757D", s=22)
        for position in x[missing]:
            ax.text(position, 0.018, "NA", ha="center", va="bottom", fontsize=6.5, color="#6C757D")
        ax.axhline(0, color="#6C757D", lw=0.8)
        ax.set_xticks(x, labels)
        ax.set_ylabel("Median shift: available minus fixed")
        ax.set_title("Evidence-composition sensitivity")
        ax.text(
            0.02, 0.96, "Matched complete-case difference = 0",
            transform=ax.transAxes, ha="left", va="top", fontsize=5.4,
            bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.82, "pad": 0.2},
        )
        self._open(ax)
        self._panel_label(ax, "d")
        return self._save(fig, "FigD5_8_dimension_availability_sensitivity")
