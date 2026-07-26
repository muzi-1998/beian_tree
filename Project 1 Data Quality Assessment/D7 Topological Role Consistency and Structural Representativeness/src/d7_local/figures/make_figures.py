from __future__ import annotations

from pathlib import Path

import matplotlib as mpl
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from d7_common.config import resolve_paths


PALETTE = {
    "DO": "#168AAD",
    "ORP": "#D1495B",
    "pass": "#2A9D8F",
    "blocked": "#9E9E9E",
    "fail": "#D1495B",
    "L3": "#2A9D8F",
    "L2": "#E9C46A",
    "L1": "#E76F51",
    "L0": "#6C757D",
    "other": "#A8B0B8",
    "target": "#D1495B",
}


class D7FigureBuilder:
    def __init__(self) -> None:
        self.paths = resolve_paths()
        self.paths.figure_root.mkdir(parents=True, exist_ok=True)
        self.data = pd.read_parquet(self.paths.plot_data_root / "D7_plot_data.parquet")
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
                "axes.titlepad": 6.0,
                "axes.linewidth": 0.8,
                "xtick.labelsize": 7,
                "ytick.labelsize": 7,
                "xtick.major.width": 0.8,
                "ytick.major.width": 0.8,
                "xtick.minor.width": 0.6,
                "ytick.minor.width": 0.6,
                "xtick.direction": "in",
                "ytick.direction": "in",
                "xtick.top": True,
                "ytick.right": True,
                "legend.fontsize": 7,
                "legend.frameon": False,
                "lines.linewidth": 1.0,
                "patch.linewidth": 0.7,
                "savefig.transparent": False,
                "svg.fonttype": "none",
                "pdf.fonttype": 42,
            }
        )

    def build_all(self) -> list[Path]:
        outputs = []
        outputs.extend(self._figure_1())
        outputs.extend(self._figure_2())
        outputs.extend(self._figure_3())
        outputs.extend(self._figure_4())
        outputs.extend(self._figure_5())
        return outputs

    def _subset(self, figure: str, panel: str) -> pd.DataFrame:
        return self.data[(self.data["figure_id"] == figure) & (self.data["panel"] == panel)].copy()

    @staticmethod
    def _panel_label(ax: plt.Axes, label: str) -> None:
        ax.text(
            -0.10,
            1.02,
            f"({label})",
            transform=ax.transAxes,
            fontsize=9,
            fontweight="bold",
            va="bottom",
            ha="right",
            clip_on=False,
            bbox={
                "facecolor": "white",
                "edgecolor": "none",
                "alpha": 0.88,
                "pad": 0.12,
            },
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
        fig.savefig(
            tiff,
            dpi=600,
            bbox_inches="tight",
            facecolor="white",
            pil_kwargs={"compression": "tiff_lzw"},
        )
        plt.close(fig)
        return [png, pdf, svg, tiff]

    def _figure_1(self) -> list[Path]:
        fig, axes = plt.subplots(
            1,
            3,
            figsize=(7.2, 3.05),
            constrained_layout=True,
            gridspec_kw={"width_ratios": [1.08, 0.94, 1.46]},
        )
        ax = axes[0]
        edges = self._subset("FigD7_1_framework", "a")
        for _, edge in edges[edges["record_type"] == "edge"].groupby("group"):
            edge = edge.sort_values("order")
            ax.plot(edge["x_numeric"], edge["value"], color="#6C757D", lw=0.9, zorder=1)
            ax.annotate(
                "",
                xy=(edge["x_numeric"].iloc[-1], edge["value"].iloc[-1]),
                xytext=(edge["x_numeric"].iloc[-2], edge["value"].iloc[-2]),
                arrowprops=dict(arrowstyle="-|>", color="#6C757D", lw=0.8, mutation_scale=7),
            )
        nodes = edges[edges["record_type"] == "node"]
        for analyte, frame in nodes.groupby("group"):
            ax.scatter(
                frame["x_numeric"], frame["value"], s=33, marker="o" if analyte == "DO" else "s",
                facecolor=PALETTE[analyte], edgecolor="white", linewidth=0.5,
                label=analyte, zorder=3,
            )
        for record in nodes.itertuples(index=False):
            ax.text(
                record.x_numeric,
                record.value + (0.10 if record.value < 0.5 else -0.10),
                record.sensor_id.replace("ORP_", "O").replace("DO_", "D").replace("_", "-"),
                ha="center",
                va="bottom" if record.value < 0.5 else "top",
                fontsize=6.0,
                bbox=dict(facecolor="white", edgecolor="none", alpha=0.68, pad=0.5),
            )
        ax.set(xlim=(-0.48, 6.48), ylim=(-0.35, 1.35), xlabel="Ordinal process position", ylabel="Parallel line")
        ax.set_xticks(np.arange(0, 7, 1))
        ax.set_yticks([0, 1], ["Line 1", "Line 2"])
        ax.legend(loc="upper center", ncol=2, bbox_to_anchor=(0.5, 1.16))
        ax.set_title("Author-confirmed topology")
        self._boxed(ax)
        self._panel_label(ax, "a")

        ax = axes[1]
        status = self._subset("FigD7_1_framework", "b").sort_values("value")
        colors = [PALETTE.get("blocked" if value > 0 else "pass", "#6C757D") for value in status["value"]]
        status_labels = status["x"].str.replace("_", " ", regex=False)
        ax.barh(status_labels, status["value"], color=colors, edgecolor="white")
        for y, value, annotation in zip(
            status_labels, status["value"], status["annotation"]
        ):
            ax.text(value + 0.012, y, annotation, va="center", fontsize=6.5)
        ax.set_xlim(0, max(1.0, status["value"].max() * 1.18))
        ax.set_xticks([0, 0.25, 0.50, 0.75, 1.0])
        ax.set_xlabel("Fraction of hourly sensor windows")
        ax.set_title("Local applicability")
        self._boxed(ax)
        self._panel_label(ax, "b")

        ax = axes[2]
        gates = self._subset("FigD7_1_framework", "c").sort_values("order")
        gate_labels = gates["x"].replace(
            {
                "Raw evidence": "Raw\nevidence",
                "Report interface": "Report\ninterface",
                "Pair action gate": "Pair action\ngate",
                "Process Guard claim": "Process Guard\nclaim",
                "Sensor Veto claim": "Sensor Veto\nclaim",
            }
        )
        ax.barh(
            gate_labels, np.ones(len(gates)),
            color=[PALETTE.get(group, "#9E9E9E") for group in gates["group"]],
            edgecolor="white",
        )
        annotation_labels = {
            "Scientific score is independent of action admission": "Scientific score independent\nof action admission",
            "Requires both nodes to pass final L3 validation": "Requires both nodes to pass\nfinal L3 validation",
            "Validated attribution suppression, not a Veto": "Validated attribution suppression;\nnot a Veto",
            "Requires validated sensor-identity localization": "Requires validated\nsensor-identity localization",
            "Documentary audit and dual approval pending": "Documentary audit and\ndual approval pending",
            "D7_raw retained when calculable": "D7 raw retained\nwhen calculable",
        }
        for y, annotation in zip(gate_labels, gates["annotation"]):
            ax.text(
                0.5,
                y,
                annotation_labels.get(annotation, annotation),
                ha="center",
                va="center",
                fontsize=5.8,
                bbox=dict(facecolor="white", edgecolor="none", alpha=0.72, pad=1.0),
            )
        ax.set_xlim(0, 1)
        ax.set_xticks([0, 1], ["Blocked", "Available"])
        ax.set_title("Boundary and action readiness")
        self._boxed(ax)
        self._panel_label(ax, "c")
        return self._save(fig, "FigD7_1_framework")

    def _figure_2(self) -> list[Path]:
        fig = plt.figure(figsize=(7.2, 5.1), constrained_layout=True)
        grid = fig.add_gridspec(2, 2, height_ratios=[1.55, 1.0])
        ax = fig.add_subplot(grid[0, :])
        heat = self._subset("FigD7_2_spatiotemporal", "a")
        heat["date"] = pd.to_datetime(heat["x"])
        sensor_order = heat[["y", "order"]].drop_duplicates().sort_values("order")["y"].tolist()
        matrix = heat.pivot(index="y", columns="date", values="value").reindex(sensor_order)
        image = ax.imshow(matrix.to_numpy(), aspect="auto", cmap="viridis", vmin=1, vmax=5, interpolation="nearest")
        positions = np.linspace(0, len(matrix.columns) - 1, 6).round().astype(int)
        ax.set_xticks(positions, [matrix.columns[i].strftime("%b\n%Y") for i in positions])
        ax.set_yticks(np.arange(len(sensor_order)), [sensor.replace("_", "-") for sensor in sensor_order])
        ax.set_xlabel("Date")
        ax.set_ylabel("Sensor")
        ax.set_title("Daily lower-quartile D7 raw score")
        colorbar = fig.colorbar(image, ax=ax, fraction=0.018, pad=0.015)
        colorbar.set_label("D7 raw (1-5)")
        self._boxed(ax)
        self._panel_label(ax, "a")

        ax = fig.add_subplot(grid[1, 0])
        distribution = self._subset("FigD7_2_spatiotemporal", "b")
        data = []
        for analyte in ["DO", "ORP"]:
            values = distribution.loc[
                distribution["group"] == analyte, "value"
            ].to_numpy(dtype=float)
            data.append(values[np.isfinite(values)])
        box = ax.boxplot(data, positions=[0, 1], widths=0.52, patch_artist=True, showfliers=False)
        for patch, analyte in zip(box["boxes"], ["DO", "ORP"]):
            patch.set_facecolor(PALETTE[analyte])
            patch.set_alpha(0.78)
        ax.axhline(3.0, color="#333333", lw=0.8, ls="--")
        ax.set_xticks([0, 1], ["DO", "ORP"])
        ax.set_ylim(1, 5)
        ax.set_yticks([1, 2, 3, 4, 5])
        ax.set_ylabel("D7 raw (1-5)")
        ax.set_title("Score distribution by analyte")
        self._boxed(ax)
        self._panel_label(ax, "b")

        ax = fig.add_subplot(grid[1, 1])
        support = self._subset("FigD7_2_spatiotemporal", "c")
        analytes = ["DO", "ORP"]
        bottom = np.zeros(2)
        for level in ["L3", "L2", "L1", "L0"]:
            values = [
                support.loc[(support["x"] == analyte) & (support["group"] == level), "value"].sum()
                for analyte in analytes
            ]
            if np.sum(values) == 0:
                continue
            ax.bar(analytes, values, bottom=bottom, label=level, color=PALETTE[level], edgecolor="white")
            bottom += np.asarray(values)
        ax.set_ylim(0, max(bottom) * 1.42)
        ax.set_ylabel("Number of regime templates")
        ax.set_title("Effective support tier")
        ax.legend(
            title="Support",
            ncol=3,
            loc="upper center",
            bbox_to_anchor=(0.5, 1.0),
            borderaxespad=0.2,
        )
        self._boxed(ax)
        self._panel_label(ax, "c")
        return self._save(fig, "FigD7_2_spatiotemporal")

    def _figure_3(self) -> list[Path]:
        fig = plt.figure(figsize=(7.2, 5.0), constrained_layout=True)
        grid = fig.add_gridspec(2, 2, height_ratios=[1.35, 1.0])
        ax = fig.add_subplot(grid[0, :])
        case = self._subset("FigD7_3_evidence", "a")
        colors = {
            "D7_raw": "#222222", "Q_profile": "#168AAD", "Q_gradient": "#E76F51",
            "Q_rank": "#E9C46A", "Q_rep": "#2A9D8F",
        }
        for metric, frame in case.groupby("group"):
            timestamps = pd.to_datetime(frame["x"])
            ax.plot(timestamps, frame["value"], color=colors[metric], label=metric.replace("_", " "))
        ax.axhline(3.0, color="#6C757D", lw=0.8, ls="--")
        ax.set_ylim(1, 5)
        ax.set_yticks([1, 2, 3, 4, 5])
        if not case.empty:
            dates = pd.to_datetime(case["x"])
            ax.set_xlim(dates.min(), dates.max())
        ax.xaxis.set_major_locator(mdates.HourLocator(interval=12))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d\n%H:%M"))
        ax.set_ylabel("Quality score (1-5)")
        ax.set_title("Unlabeled low-score case: decomposed spatial evidence")
        ax.legend(ncol=5, loc="upper center")
        self._boxed(ax)
        self._panel_label(ax, "a")

        ax = fig.add_subplot(grid[1, 0])
        ranking = self._subset("FigD7_3_evidence", "b").sort_values("order")
        sensor_order = ranking.drop_duplicates("x").sort_values("order")["x"].tolist()
        pivot = ranking.pivot_table(
            index="x", columns="group", values="value", aggfunc="sum"
        ).reindex(sensor_order).fillna(0.0)
        bottom = np.zeros(len(pivot))
        component_colors = {
            "Leave-one-out": "#168AAD",
            "Graph energy": "#E9C46A",
            "Gradient": "#E76F51",
        }
        labels = pivot.index.to_series().str.replace("_", "-", regex=False)
        for component in ["Leave-one-out", "Graph energy", "Gradient"]:
            values = pivot.get(component, pd.Series(0.0, index=pivot.index)).to_numpy()
            ax.barh(
                labels,
                values,
                left=bottom,
                color=component_colors[component],
                label=component,
                edgecolor="white",
            )
            bottom += values
        ax.set_xlim(0, 1)
        ax.set_xticks([0, 0.25, 0.50, 0.75, 1.0])
        ax.set_xlabel("Node contribution (0-1)")
        ax.set_title("Leave-one-out structural attribution")
        ax.legend(loc="upper right", fontsize=6.2)
        self._boxed(ax)
        self._panel_label(ax, "b")

        ax = fig.add_subplot(grid[1, 1])
        consensus = self._subset("FigD7_3_evidence", "c").sort_values("value")
        ax.barh(consensus["x"].str.replace("_", " ", regex=False), consensus["value"], color="#4C78A8", edgecolor="white")
        for y, value in zip(consensus["x"].str.replace("_", " ", regex=False), consensus["value"]):
            ax.text(value + 0.01, y, f"{value:.1%}", va="center", fontsize=6.5)
        ax.set_xlim(0, max(1.0, consensus["value"].max() * 1.2))
        ax.set_xticks([0, 0.25, 0.50, 0.75, 1.0])
        ax.set_xlabel("Fraction of pair-hours")
        ax.set_title("D7-to-D6 zone-consensus labels")
        self._boxed(ax)
        self._panel_label(ax, "c")
        return self._save(fig, "FigD7_3_evidence")

    def _figure_4(self) -> list[Path]:
        fig, axes = plt.subplots(2, 2, figsize=(7.2, 5.4), constrained_layout=True)
        panels = ["a", "b", "c", "d"]
        titles = ["Release acceptance metrics", "Top-1 by injected scenario", "Negative-control false alarm rate", "Local-Sensitivity track invariance"]
        ylabels = ["Estimate", "Top-1 accuracy", "False alarm rate", "Estimate"]
        for ax, panel, title, ylabel in zip(axes.flat, panels, titles, ylabels):
            frame = self._subset("FigD7_4_validation", panel).sort_values("order")
            x = np.arange(len(frame))
            bars = ax.bar(
                x,
                frame["value"],
                color=[PALETTE.get(group, "#4C78A8") for group in frame["group"]],
                edgecolor="white",
            )
            if panel in {"a", "b", "c"} and frame[["value_low", "value_high"]].notna().all(axis=1).any():
                low = frame["value"] - frame["value_low"]
                high = frame["value_high"] - frame["value"]
                valid = low.notna() & high.notna()
                ax.errorbar(
                    x[valid],
                    frame.loc[valid, "value"],
                    yerr=[low[valid], high[valid]],
                    fmt="none",
                    ecolor="#222222",
                    capsize=2,
                    lw=0.8,
                )
            for i, target in enumerate(frame["target"]):
                if np.isfinite(target):
                    ax.plot([i - 0.38, i + 0.38], [target, target], color="#222222", lw=0.8, ls="--")
            ax.set_xticks(x, frame["x"].str.replace("_", " ", regex=False), rotation=28, ha="right")
            ax.set_ylim(0, 1.05)
            ax.set_yticks([0, 0.25, 0.50, 0.75, 1.0])
            if panel == "c":
                ax.set_ylim(0, 0.25)
                ax.set_yticks([0, 0.05, 0.10, 0.15, 0.20, 0.25])
            ax.set_ylabel(ylabel)
            ax.set_title(title)
            self._boxed(ax)
            self._panel_label(ax, panel)
        return self._save(fig, "FigD7_4_validation")

    def _figure_5(self) -> list[Path]:
        fig, axes = plt.subplots(2, 2, figsize=(7.2, 5.4), constrained_layout=True)
        ax = axes[0, 0]
        support = self._subset("FigD7_5_governance", "a")
        analytes = ["DO", "ORP"]
        sources = ["Family support", "Validated node"]
        x = np.arange(len(analytes), dtype=float)
        width = 0.32
        max_total = 0.0
        for source_index, source in enumerate(sources):
            bottom = np.zeros(len(analytes))
            offset = (source_index - 0.5) * width
            for level in ["L1", "L2", "L3"]:
                values = np.asarray(
                    [
                        support.loc[
                            (support["x"] == analyte)
                            & (support["y"] == source)
                            & (support["group"] == level),
                            "value",
                        ].sum()
                        for analyte in analytes
                    ],
                    dtype=float,
                )
                ax.bar(
                    x + offset,
                    values,
                    width=width,
                    bottom=bottom,
                    color=PALETTE[level],
                    label=level if source_index == 0 else None,
                    edgecolor="white",
                )
                bottom += values
            max_total = max(max_total, float(bottom.max()))
            for xpos, total in zip(x + offset, bottom):
                ax.text(
                    xpos,
                    total + 0.8,
                    f"{int(total)}",
                    ha="center",
                    va="bottom",
                    fontsize=6.3,
                )
        ax.set_xticks(x, analytes)
        ax.set_ylabel("Template count")
        ax.set_ylim(0, max_total * 1.32)
        ax.set_title("Shared-family support and node admission")
        ax.legend(
            title="Final tier",
            ncol=3,
            loc="upper center",
            bbox_to_anchor=(0.5, 1.01),
            borderaxespad=0.1,
        )
        ax.text(
            0.02,
            0.98,
            "Left: family\nRight: node",
            transform=ax.transAxes,
            ha="left",
            va="top",
            fontsize=6.2,
            bbox=dict(facecolor="white", edgecolor="none", alpha=0.82, pad=1.0),
        )
        self._boxed(ax)
        self._panel_label(ax, "a")

        ax = axes[0, 1]
        node = self._subset("FigD7_5_governance", "b").sort_values(
            ["order", "group"]
        )
        sensor_order = (
            node[["x", "order"]]
            .drop_duplicates()
            .sort_values("order")["x"]
            .tolist()
        )
        positions = {sensor: index for index, sensor in enumerate(sensor_order)}
        metric_styles = {
            "Bootstrap stability": ("o", "#168AAD"),
            "Holdout FAR": ("s", "#D1495B"),
        }
        for metric, (marker, color) in metric_styles.items():
            frame = node[node["group"] == metric]
            ax.scatter(
                [positions[sensor] for sensor in frame["x"]],
                frame["value"],
                s=26,
                marker=marker,
                color=color,
                edgecolor="white",
                linewidth=0.5,
                label=metric,
                zorder=3,
            )
        ax.axhline(
            0.80,
            color="#168AAD",
            lw=0.8,
            ls="--",
            label="Stability threshold",
        )
        ax.axhline(
            0.15,
            color="#D1495B",
            lw=0.8,
            ls=":",
            label="FAR threshold",
        )
        ax.set_xticks(
            np.arange(len(sensor_order)),
            [sensor.replace("_", "-") for sensor in sensor_order],
            rotation=40,
            ha="right",
        )
        final_l3 = set(node.loc[node["context"] == "L3", "x"])
        for tick, sensor in zip(ax.get_xticklabels(), sensor_order):
            if sensor in final_l3:
                tick.set_fontweight("bold")
                tick.set_color(PALETTE["L3"])
        ax.set_ylim(0, 1.02)
        ax.set_yticks([0, 0.25, 0.50, 0.75, 1.0])
        ax.set_ylabel("Validation statistic")
        ax.set_title("Node-specific validation within family L3")
        ax.legend(
            ncol=2,
            loc="center",
            bbox_to_anchor=(0.60, 0.54),
            fontsize=5.8,
            columnspacing=0.8,
            handletextpad=0.4,
        )
        self._boxed(ax)
        self._panel_label(ax, "b")

        ax = axes[1, 0]
        interfaces = self._subset("FigD7_5_governance", "c").sort_values(
            "order", ascending=False
        )
        interface_colors = {
            "report": "#168AAD",
            "gate": "#E9C46A",
            "guard": "#2A9D8F",
            "veto": "#D1495B",
        }
        labels = interfaces["x"].str.replace(" active", "", regex=False)
        ax.barh(
            labels,
            interfaces["value"],
            color=[
                interface_colors.get(group, "#A8B0B8")
                for group in interfaces["group"]
            ],
            edgecolor="white",
        )
        ax.scatter(
            interfaces["value"],
            labels,
            s=20,
            color=[
                interface_colors.get(group, "#A8B0B8")
                for group in interfaces["group"]
            ],
            edgecolor="white",
            linewidth=0.5,
            zorder=3,
        )
        for label, value, annotation in zip(
            labels, interfaces["value"], interfaces["annotation"]
        ):
            ax.text(
                max(float(value) + 0.018, 0.025),
                label,
                annotation,
                va="center",
                fontsize=6.2,
            )
        ax.set_xlim(-0.03, 1.05)
        ax.set_xticks([0, 0.25, 0.50, 0.75, 1.0])
        ax.set_xlabel("Fraction of interface rows")
        ax.set_title("Report and action-interface coverage")
        self._boxed(ax)
        self._panel_label(ax, "c")

        ax = axes[1, 1]
        identity = self._subset("FigD7_5_governance", "d")
        low = float(
            min(identity["x_numeric"].min(), identity["value"].min())
        )
        high = float(
            max(identity["x_numeric"].max(), identity["value"].max())
        )
        margin = max((high - low) * 0.04, 0.05)
        ax.scatter(
            identity["x_numeric"],
            identity["value"],
            s=3,
            color="#168AAD",
            alpha=0.12,
            linewidth=0,
            rasterized=True,
        )
        ax.plot(
            [low - margin, high + margin],
            [low - margin, high + margin],
            color="#222222",
            lw=0.9,
            ls="--",
            label="Identity",
        )
        ax.set_xlim(low - margin, high + margin)
        ax.set_ylim(low - margin, high + margin)
        ax.set_aspect("equal", adjustable="box")
        ax.set_xlabel("D6 raw")
        ax.set_ylabel("D6 final for DQR")
        audit_note = identity.loc[
            identity["annotation"].astype(str).ne(""), "annotation"
        ].iloc[0]
        ax.text(
            0.04,
            0.94,
            audit_note.replace("delta", r"$\Delta$"),
            transform=ax.transAxes,
            ha="left",
            va="top",
            fontsize=6.5,
            bbox=dict(facecolor="white", edgecolor="none", alpha=0.82, pad=1.2),
        )
        ax.set_title("D6 numeric independence audit")
        ax.legend(loc="lower right")
        self._boxed(ax)
        self._panel_label(ax, "d")
        return self._save(fig, "FigD7_5_governance")
