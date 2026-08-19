from __future__ import annotations

from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import FancyBboxPatch
import numpy as np
import pandas as pd

from d5_common.config import resolve_paths
from d5_local.figures.figure_style import (
    PALETTE as BASE_PALETTE,
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


PALETTE = {
    "DO": BASE_PALETTE["blue"],
    "ORP": BASE_PALETTE["red"],
    "pass": BASE_PALETTE["teal"],
    "blocked": BASE_PALETTE["gray"],
    "fail": BASE_PALETTE["red"],
    "L3": BASE_PALETTE["teal"],
    "L2": BASE_PALETTE["gold"],
    "L1": BASE_PALETTE["orange"],
    "L0": BASE_PALETTE["gray"],
    "other": BASE_PALETTE["light_gray"],
    "target": BASE_PALETTE["red"],
}


class D5FigureBuilder:
    def __init__(self) -> None:
        self.paths = resolve_paths()
        self.paths.figure_root.mkdir(parents=True, exist_ok=True)
        self.data = pd.read_parquet(self.paths.plot_data_root / "D5_plot_data.parquet")
        configure_style()

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
        panel_label(ax, label)

    @staticmethod
    def _boxed(ax: plt.Axes) -> None:
        style_axes(ax, boxed=True)

    @staticmethod
    def _open(ax: plt.Axes) -> None:
        style_axes(ax, boxed=False)

    def _save(self, fig: plt.Figure, stem: str) -> list[Path]:
        return save_figure(fig, self.paths.figure_root, stem)

    def _figure_1(self) -> list[Path]:
        fig = plt.figure(figsize=(PROFILE.width_in, 4.05), layout="constrained")
        grid = fig.add_gridspec(
            2,
            2,
            width_ratios=[1.38, 1.0],
            height_ratios=[0.88, 1.12],
            hspace=0.24,
        )
        ax = fig.add_subplot(grid[:, 0])
        edges = self._subset("FigD5_1_framework", "a")
        for _, edge in edges[edges["record_type"] == "edge"].groupby("group"):
            edge = edge.sort_values("order")
            if str(edge["context"].iloc[0]) == "parallel_peer":
                ax.plot(
                    edge["x_numeric"], edge["value"], color=BASE_PALETTE["navy"],
                    lw=0.85, ls=(0, (3, 2)), alpha=0.9, zorder=1,
                )
            else:
                ax.annotate(
                    "", xy=(edge["x_numeric"].iloc[-1], edge["value"].iloc[-1]),
                    xytext=(edge["x_numeric"].iloc[-2], edge["value"].iloc[-2]),
                    arrowprops=dict(
                        arrowstyle="-|>", color=BASE_PALETTE["gray"], lw=0.9,
                        mutation_scale=7, shrinkA=6, shrinkB=6,
                    ),
                    zorder=1,
                )
        nodes = edges[edges["record_type"] == "node"]
        for analyte, frame in nodes.groupby("group"):
            ax.scatter(
                frame["x_numeric"], frame["value"], s=38, marker="o" if analyte == "DO" else "s",
                facecolor=PALETTE[analyte], edgecolor="white", linewidth=0.5,
                label=analyte, zorder=3,
            )
        for record in nodes.itertuples(index=False):
            ax.text(
                record.x_numeric,
                record.value + (0.085 if record.value < 0.5 else -0.085),
                record.sensor_id,
                ha="center",
                va="bottom" if record.value < 0.5 else "top",
                fontsize=5.5,
                bbox=dict(facecolor="white", edgecolor="none", alpha=0.76, pad=0.35),
            )
        zone_labels = [
            "Anaerobic", "Anoxic 1", "Anoxic 2", "Aerobic 1", "Aerobic 2",
            "Aerobic 3", "Post-anoxic",
        ]
        ax.set(xlim=(-0.48, 6.48), ylim=(-0.34, 1.34), xlabel="Process zone", ylabel="Parallel treatment line")
        ax.set_xticks(np.arange(0, 7, 1), zone_labels, rotation=36, ha="right")
        ax.set_yticks([0, 1], ["Line 1", "Line 2"])
        ax.legend(
            handles=[
                Line2D([], [], marker="o", ls="none", color=PALETTE["DO"], label="DO"),
                Line2D([], [], marker="s", ls="none", color=PALETTE["ORP"], label="ORP"),
                Line2D([], [], color=BASE_PALETTE["gray"], lw=0.9, label="Longitudinal"),
                Line2D([], [], color=BASE_PALETTE["navy"], lw=0.9, ls=(0, (3, 2)), label="Parallel peer"),
            ],
            loc="upper center", ncol=2, bbox_to_anchor=(0.5, 1.01),
        )
        ax.set_title("Research-confirmed topology")
        ax.text(0.99, 0.02, "Schematic, not to scale", transform=ax.transAxes, ha="right", va="bottom", fontsize=5.3, color=BASE_PALETTE["gray"])
        self._boxed(ax)
        self._panel_label(ax, "a")

        ax = fig.add_subplot(grid[0, 1])
        status = self._subset("FigD5_1_framework", "b")
        status_order = ["evaluable", "limited_support", "out_of_template", "not_evaluable"]
        status_colors = {
            "evaluable": BASE_PALETTE["teal"], "limited_support": BASE_PALETTE["gold"],
            "out_of_template": BASE_PALETTE["red"], "not_evaluable": BASE_PALETTE["gray"],
        }
        analytes = ["DO", "ORP", "All"]
        left = np.zeros(len(analytes))
        for name in status_order:
            values = [
                float(status.loc[status["x"].eq(analyte) & status["group"].eq(name), "value"].sum())
                for analyte in analytes
            ]
            ax.barh(analytes, values, left=left, color=status_colors[name], edgecolor="white", label=name.replace("_", " "))
            left += np.asarray(values)
        ax.set_xlim(0, 1)
        ax.set_xticks([0, 0.5, 1.0])
        ax.set_xlabel("")
        ax.set_title("Applicability by analyte")
        ax.legend(
            loc="upper center",
            bbox_to_anchor=(0.5, -0.18),
            ncol=2,
            fontsize=5.5,
            columnspacing=1.1,
            handlelength=1.5,
        )
        self._open(ax)
        self._panel_label(ax, "b")

        ax = fig.add_subplot(grid[1, 1])
        stages = self._subset("FigD5_1_framework", "c").sort_values("order")
        ax.set_xlim(-0.10, 1.85)
        ax.set_ylim(-0.05, 2.72)
        positions = [
            (0.35, 2.30),
            (1.40, 2.30),
            (1.40, 1.35),
            (0.35, 1.35),
            (0.35, 0.40),
            (1.40, 0.40),
        ]
        stage_colors = ["#E7F2F7", "#E7F2F7", "#E8F3EF", "#FFF2D8", "#FCE7EA", "#ECEFF2"]
        short_annotations = [
            "QR/QIR + clock",
            "Frozen assignment",
            "Position + peer",
            "Profile | gradient\nrank | representation",
            "Continuous score (1-5)",
            "Eligible or abstain",
        ]
        for index, (record, (xpos, ypos)) in enumerate(zip(stages.itertuples(index=False), positions)):
            ax.add_patch(FancyBboxPatch(
                (xpos - 0.43, ypos - 0.27), 0.86, 0.54,
                boxstyle="round,pad=0.02,rounding_size=0.025",
                facecolor=stage_colors[index], edgecolor="#646A70", lw=0.65,
            ))
            ax.text(xpos, ypos + 0.10, record.x, ha="center", va="center", fontsize=5.0, fontweight="bold")
            ax.text(xpos, ypos - 0.12, short_annotations[index], ha="center", va="center", fontsize=5.0)
        for start_pos, end_pos in zip(positions[:-1], positions[1:]):
            ax.annotate("", xy=end_pos, xytext=start_pos, arrowprops=dict(arrowstyle="-|>", lw=0.7, color=BASE_PALETTE["gray"], shrinkA=27, shrinkB=27))
        ax.set_title("Regime-conditioned scoring pipeline")
        ax.axis("off")
        self._panel_label(ax, "c")
        return self._save(fig, "FigD5_1_framework")

    def _figure_2(self) -> list[Path]:
        fig = plt.figure(figsize=(PROFILE.width_in, 5.15), layout="constrained")
        grid = fig.add_gridspec(2, 2, height_ratios=[1.55, 1.0])
        top = grid[0, :].subgridspec(2, 1, height_ratios=[9.0, 0.85], hspace=0.04)
        ax = fig.add_subplot(top[0])
        heat_all = self._subset("FigD5_2_spatiotemporal", "a")
        heat = heat_all[heat_all["record_type"].eq("daily_p25")].copy()
        heat["date"] = pd.to_datetime(heat["x"])
        sensor_order = heat[["y", "order"]].drop_duplicates().sort_values("order")["y"].tolist()
        matrix = heat.pivot(index="y", columns="date", values="value").reindex(sensor_order)
        image = ax.imshow(matrix.to_numpy(), aspect="auto", cmap="viridis", vmin=1, vmax=5, interpolation="nearest")
        eligibility = heat_all[heat_all["record_type"].eq("report_eligible_rate")].copy()
        eligibility["date"] = pd.to_datetime(eligibility["x"])
        eligibility_matrix = eligibility.pivot(index="y", columns="date", values="value").reindex(index=sensor_order, columns=matrix.columns)
        masked = np.ma.masked_where(
            eligibility_matrix.to_numpy() >= 0.50,
            np.ones_like(eligibility_matrix.to_numpy()),
        )
        ax.imshow(masked, aspect="auto", cmap="Greys", vmin=0, vmax=1, alpha=0.58, interpolation="nearest")
        month_periods = pd.DatetimeIndex(matrix.columns).to_period("M")
        positions = np.flatnonzero(~month_periods.duplicated())
        ax.set_xticks(positions, [])
        ax.set_yticks(np.arange(len(sensor_order)), sensor_order)
        ax.set_ylabel("Sensor")
        ax.set_title("D5 score and report eligibility")
        cases = heat_all[heat_all["record_type"].eq("case_window")].sort_values("x_numeric")
        for label, record in zip(["A", "B", "C"], cases.itertuples(index=False)):
            start = pd.Timestamp(record.x).floor("D")
            end = pd.to_datetime(record.value, unit="s").floor("D")
            x0 = int(np.argmin(np.abs(matrix.columns - start)))
            x1 = int(np.argmin(np.abs(matrix.columns - end)))
            ax.axvspan(x0 - 0.5, x1 + 0.5, facecolor="none", edgecolor="white", hatch="////", lw=0.7)
            ax.text(
                (x0 + x1) / 2,
                0.16,
                label,
                ha="center",
                va="center",
                fontsize=5.7,
                fontweight="bold",
                color="white",
                bbox={
                    "facecolor": BASE_PALETTE["dark"],
                    "edgecolor": "none",
                    "alpha": 0.78,
                    "pad": 0.25,
                },
            )
        colorbar = fig.colorbar(image, ax=ax, fraction=0.018, pad=0.015)
        colorbar.set_label("D5 raw (1–5); 3 = analysis reference")
        self._boxed(ax)
        self._panel_label(ax, "a")

        ribbon_ax = fig.add_subplot(top[1], sharex=ax)
        dates = matrix.columns
        report_daily = eligibility.groupby("date")["value"].mean().reindex(dates).fillna(0.0)
        ood = heat_all[heat_all["record_type"].eq("ood_rate")].copy()
        ood["date"] = pd.to_datetime(ood["x"])
        ood_daily = ood.groupby("date")["value"].mean().reindex(dates).fillna(0.0)
        rgba = np.zeros((2, len(dates), 4))
        rgba[0] = plt.get_cmap("Greens")(0.15 + 0.75 * report_daily.to_numpy())
        rgba[1] = plt.get_cmap("Reds")(0.08 + 0.82 * ood_daily.to_numpy())
        ribbon_ax.imshow(rgba, aspect="auto", interpolation="nearest")
        ribbon_ax.set_yticks([0, 1], ["Report", "OOD"])
        ribbon_ax.set_xticks(positions, [matrix.columns[i].strftime("%b\n%Y") for i in positions])
        ribbon_ax.set_xlabel("Date")
        ribbon_ax.text(
            0.995,
            1.13,
            "Gray heatmap overlay: <50% report-eligible",
            transform=ribbon_ax.transAxes,
            ha="right",
            va="bottom",
            fontsize=5.2,
            color=BASE_PALETTE["gray"],
        )
        self._boxed(ribbon_ax)

        ax = fig.add_subplot(grid[1, 0])
        distribution = self._subset("FigD5_2_spatiotemporal", "b").sort_values("order").reset_index(drop=True)
        for analyte, frame in distribution.groupby("group"):
            indices = frame.index.to_numpy()
            ax.errorbar(
                frame["value"], indices,
                xerr=[frame["value"] - frame["value_low"], frame["value_high"] - frame["value"]],
                fmt="none", ecolor=PALETTE[analyte], elinewidth=1.1, capsize=0, alpha=0.8,
            )
            ax.scatter(
                frame["value"], indices, s=18 + 95 * frame["target"].to_numpy(float),
                color=PALETTE[analyte], edgecolor="white", linewidth=0.45, label=analyte, zorder=3,
            )
        ax.axvline(3.0, color=BASE_PALETTE["gray"], lw=0.8, ls="--")
        ax.set_yticks(np.arange(len(distribution)), distribution["sensor_id"])
        ax.invert_yaxis()
        ax.set_xlim(1, 5)
        ax.set_xticks([1, 2, 3, 4, 5])
        ax.set_xlabel("D5 raw median and IQR")
        ax.set_title("Sensor-level score profile")
        ax.legend(
            handles=[
                Line2D([], [], marker="o", ls="none", color=PALETTE["DO"], label="DO"),
                Line2D([], [], marker="o", ls="none", color=PALETTE["ORP"], label="ORP"),
                Line2D([], [], marker="o", ls="none", color=BASE_PALETTE["gray"], markersize=4, label="10% <3"),
                Line2D([], [], marker="o", ls="none", color=BASE_PALETTE["gray"], markersize=7, label="50% <3"),
            ],
            loc="upper right", ncol=1,
        )
        self._open(ax)
        self._panel_label(ax, "b")

        ax = fig.add_subplot(grid[1, 1])
        monthly = self._subset("FigD5_2_spatiotemporal", "c")
        months = monthly["x"].drop_duplicates().tolist()
        colors = {"Report coverage": BASE_PALETTE["teal"], "OOD": BASE_PALETTE["red"], "L1 support": BASE_PALETTE["gold"]}
        markers = {"Report coverage": "o", "OOD": "s", "L1 support": "^"}
        for metric in ["Report coverage", "OOD", "L1 support"]:
            frame = monthly[monthly["group"].eq(metric)].set_index("x").reindex(months)
            ax.plot(np.arange(len(months)), frame["value"], marker=markers[metric], ms=3.2, color=colors[metric], label=metric)
        ax.set_xticks(np.arange(len(months)), [month.replace("-", "\n") for month in months])
        ax.set_ylim(0, 1.02)
        ax.set_ylabel("Fraction of sensor-hours")
        ax.set_title("Evidence availability over time")
        ax.legend(
            loc="upper left",
            ncol=2,
            frameon=True,
            facecolor="white",
            edgecolor="none",
            framealpha=0.78,
        )
        self._open(ax)
        self._panel_label(ax, "c")
        return self._save(fig, "FigD5_2_spatiotemporal")

    def _figure_3(self) -> list[Path]:
        fig = plt.figure(figsize=(PROFILE.width_in, 6.0), layout="constrained")
        grid = fig.add_gridspec(4, 2, height_ratios=[1.0, 0.13, 1.0, 1.18])
        case = self._subset("FigD5_3_evidence", "a")
        raw = case[case["record_type"].eq("raw_timeseries")].copy()
        event_window = case[case["record_type"].eq("event_window")].iloc[0]
        event_start = pd.Timestamp(event_window["x"])
        event_end = pd.to_datetime(event_window["value"], unit="s")

        ax = fig.add_subplot(grid[0, :])
        raw_colors = {
            "Target": BASE_PALETTE["red"],
            "Parallel peer": BASE_PALETTE["blue"],
            "Same-line neighbor": BASE_PALETTE["teal"],
        }
        for role in ["Target", "Parallel peer", "Same-line neighbor"]:
            frame = raw[raw["group"].eq(role)]
            ax.plot(pd.to_datetime(frame["x"]), frame["value"], color=raw_colors[role], label=f"{role}: {frame['sensor_id'].iloc[0]}")
        reference = case[case["record_type"].eq("raw_reference")]
        if not reference.empty:
            ref = reference.iloc[0]
            ax.axhspan(ref["value_low"], ref["value_high"], color=BASE_PALETTE["gold"], alpha=0.18, label="Role-template ±1 robust scale")
            ax.axhline(ref["value"], color=BASE_PALETTE["gold"], lw=0.8, ls="--")
        ax.axvspan(event_start, event_end, color=BASE_PALETTE["red"], alpha=0.10, label="Unlabeled candidate window")
        analyte_label = next((str(value) for value in raw["analyte"] if pd.notna(value)), "Analyte")
        ax.set_ylabel(f"{analyte_label} raw value")
        ax.set_title("Raw target, parallel peer and same-line neighbor")
        ax.tick_params(labelbottom=False)
        ax.legend(loc="upper center", ncol=3)
        self._open(ax)
        self._panel_label(ax, "a")

        strip_ax = fig.add_subplot(grid[1, :], sharex=ax)
        regime = case[case["record_type"].eq("regime_strip")].copy()
        regime_times = pd.to_datetime(regime["x"])
        strip_ax.scatter(
            regime_times, np.zeros(len(regime)), c=regime["value"], cmap="tab10",
            vmin=0, vmax=max(3, float(regime["value"].max())), marker="s", s=11,
        )
        ood = regime["group"].eq("OODHold")
        if ood.any():
            strip_ax.scatter(regime_times[ood], np.zeros(int(ood.sum())), facecolors="none", edgecolors=BASE_PALETTE["red"], marker="s", s=16, linewidths=0.6)
        strip_ax.set_yticks([0], ["Regime / OOD"])
        strip_ax.tick_params(labelbottom=False, length=0)
        for spine in strip_ax.spines.values():
            spine.set_visible(False)

        ax = fig.add_subplot(grid[2, :], sharex=ax)
        scores = case[case["record_type"].eq("case_timeseries")]
        colors = {
            "D5_raw": BASE_PALETTE["dark"], "Q_profile": BASE_PALETTE["blue"],
            "Q_gradient": BASE_PALETTE["orange"], "Q_rank": BASE_PALETTE["gold"],
            "Q_rep": BASE_PALETTE["teal"],
        }
        for metric, frame in scores.groupby("group"):
            timestamps = pd.to_datetime(frame["x"])
            ax.plot(timestamps, frame["value"], color=colors[metric], label=metric.replace("_", " "))
        ax.axvspan(event_start, event_end, color=BASE_PALETTE["red"], alpha=0.10)
        ax.axhline(3.0, color=BASE_PALETTE["gray"], lw=0.8, ls="--")
        ax.set_ylim(1, 5)
        ax.set_yticks([1, 2, 3, 4, 5])
        ax.xaxis.set_major_locator(mdates.HourLocator(interval=12))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d\n%H:%M"))
        ax.set_ylabel("Quality score (1-5)")
        ax.set_title("Component-score response")
        ax.legend(ncol=5, loc="upper center")
        self._open(ax)

        ax = fig.add_subplot(grid[3, 0])
        ranking = self._subset("FigD5_3_evidence", "b").sort_values("order")
        sensor_order = ranking.drop_duplicates("x").sort_values("order")["x"].tolist()
        pivot = ranking.pivot_table(
            index="x", columns="group", values="value", aggfunc="sum"
        ).reindex(sensor_order).fillna(0.0)
        pivot = pivot.assign(total=pivot.sum(axis=1)).nlargest(10, "total").sort_values("total").drop(columns="total")
        bottom = np.zeros(len(pivot))
        component_colors = {
            "Leave-one-out": BASE_PALETTE["blue"],
            "Graph energy": BASE_PALETTE["gold"],
            "Gradient": BASE_PALETTE["orange"],
        }
        labels = pivot.index.to_series()
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
        ax.set_xlabel("Node contribution (0-1; descriptive, non-causal)")
        ax.set_title("Normalized diagnostic contribution")
        ax.legend(loc="lower right")
        self._open(ax)
        self._panel_label(ax, "b")

        ax = fig.add_subplot(grid[3, 1])
        topology = self._subset("FigD5_3_evidence", "c")
        edge_data = topology[topology["record_type"].eq("topology_edge")]
        for _, edge in edge_data.groupby("x"):
            edge = edge.sort_values("order")
            residual = float(edge["value"].iloc[0])
            peer = str(edge["group"].iloc[0]) == "parallel_peer"
            ax.plot(
                edge["x_numeric"], edge["y"].astype(float),
                color=BASE_PALETTE["navy"] if peer else BASE_PALETTE["orange"],
                ls=(0, (3, 2)) if peer else "-",
                lw=0.55 + 1.45 * min(residual, 3.0) / 3.0,
                alpha=0.45 + 0.45 * min(residual, 3.0) / 3.0,
                zorder=1,
            )
        nodes = topology[topology["record_type"].eq("topology_node")]
        max_value = max(float(nodes["value"].max()), 1e-6)
        scatter = ax.scatter(
            nodes["x_numeric"], nodes["y"].astype(float), c=nodes["value"],
            cmap="viridis", vmin=0, vmax=max_value, s=40, edgecolor="white", linewidth=0.5, zorder=3,
        )
        target = nodes[nodes["group"].eq("target")]
        ax.scatter(target["x_numeric"], target["y"].astype(float), facecolors="none", edgecolors=BASE_PALETTE["red"], s=70, linewidth=1.0, zorder=4)
        for record in nodes.itertuples(index=False):
            ax.text(record.x_numeric, float(record.y) + (0.10 if float(record.y) < 0.5 else -0.10), record.sensor_id, ha="center", va="bottom" if float(record.y) < 0.5 else "top", fontsize=5.0)
        ax.set_xlim(-0.45, 6.45)
        ax.set_ylim(-0.35, 1.35)
        ax.set_xticks(np.arange(7), ["Ana", "Anx1", "Anx2", "Aer1", "Aer2", "Aer3", "Post"], rotation=30, ha="right")
        ax.set_yticks([0, 1], ["Line 1", "Line 2"])
        ax.set_xlabel("Process position")
        ax.set_title("Event-time topology residual map")
        colorbar = fig.colorbar(scatter, ax=ax, fraction=0.05, pad=0.02)
        colorbar.set_label("Normalized |structural residual|")
        self._boxed(ax)
        self._panel_label(ax, "c")
        return self._save(fig, "FigD5_3_evidence")

    def _figure_4(self) -> list[Path]:
        fig, axes = plt.subplots(2, 2, figsize=(PROFILE.width_in, 5.35), layout="constrained")
        panels = ["a", "b", "c", "d"]
        titles = ["Criterion margins", "Top-1 by scenario", "Negative-control FAR", "Track-invariance margins"]
        ylabels = ["Margin (pass > 0)", "Top-1 accuracy", "False alarm rate", "Margin (pass > 0)"]
        for ax, panel, title, ylabel in zip(axes.flat, panels, titles, ylabels):
            frame = self._subset("FigD5_4_validation", panel).sort_values("order")
            x = np.arange(len(frame))
            margin_panel = panel in {"a", "d"}
            values = frame["value"].copy()
            low_values = frame["value_low"].copy()
            high_values = frame["value_high"].copy()
            if margin_panel:
                lower_better = frame["x"].str.contains("FAR|chatter|IE_track", case=False, regex=True)
                values = np.where(lower_better, frame["target"] - frame["value"], frame["value"] - frame["target"])
                low_values = np.where(lower_better, frame["target"] - frame["value_high"], frame["value_low"] - frame["target"])
                high_values = np.where(lower_better, frame["target"] - frame["value_low"], frame["value_high"] - frame["target"])
            bars = ax.bar(
                x,
                values,
                color=[PALETTE.get(group, "#4C78A8") for group in frame["group"]],
                edgecolor="white",
            )
            if panel in {"a", "b", "c"} and frame[["value_low", "value_high"]].notna().all(axis=1).any():
                low = np.asarray(values, dtype=float) - np.asarray(low_values, dtype=float)
                high = np.asarray(high_values, dtype=float) - np.asarray(values, dtype=float)
                valid = np.isfinite(low) & np.isfinite(high)
                ax.errorbar(
                    x[valid],
                    np.asarray(values)[valid],
                    yerr=[low[valid], high[valid]],
                    fmt="none",
                    ecolor="#222222",
                    capsize=2,
                    lw=0.8,
                )
            if margin_panel:
                ax.axhline(0, color=BASE_PALETTE["gray"], lw=0.8, ls="--")
            else:
                for i, target in enumerate(frame["target"]):
                    if np.isfinite(target):
                        ax.plot([i - 0.38, i + 0.38], [target, target], color="#222222", lw=0.8, ls="--")
            ax.set_xticks(x, frame["x"].str.replace("_", " ", regex=False), rotation=28, ha="right")
            if margin_panel:
                span = max(0.05, float(np.nanmax(np.abs(values))) * 1.25)
                ax.set_ylim(-span, span)
            else:
                ax.set_ylim(0, 1.05)
                ax.set_yticks([0, 0.25, 0.50, 0.75, 1.0])
            if panel == "c":
                ax.set_ylim(0, 0.25)
                ax.set_yticks([0, 0.05, 0.10, 0.15, 0.20, 0.25])
            ax.set_ylabel(ylabel)
            ax.set_title(title)
            self._open(ax)
            self._panel_label(ax, panel)
        return self._save(fig, "FigD5_4_validation")

    def _figure_5(self) -> list[Path]:
        fig, axes = plt.subplots(2, 2, figsize=(PROFILE.width_in, 5.35), layout="constrained")
        ax = axes[0, 0]
        support = self._subset("FigD5_5_governance", "a")
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
        ax.set_title("Family-to-node support")
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
        self._open(ax)
        self._panel_label(ax, "a")

        ax = axes[0, 1]
        node = self._subset("FigD5_5_governance", "b").sort_values(
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
            sensor_order,
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
        ax.set_title("Node-level L3 admission")
        ax.legend(
            ncol=2,
            loc="center",
            bbox_to_anchor=(0.60, 0.54),
            fontsize=5.8,
            columnspacing=0.8,
            handletextpad=0.4,
        )
        self._open(ax)
        self._panel_label(ax, "b")

        ax = axes[1, 0]
        interfaces = self._subset("FigD5_5_governance", "c").sort_values(
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
        ax.set_title("Report and action interfaces")
        self._open(ax)
        self._panel_label(ax, "c")

        ax = axes[1, 1]
        identity = self._subset("FigD5_5_governance", "d")
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
        ax.set_xlabel("D4 raw")
        ax.set_ylabel("D4 final for DQR")
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
        ax.set_title("D4 no-overwrite audit")
        ax.legend(loc="lower right")
        self._boxed(ax)
        self._panel_label(ax, "d")
        return self._save(fig, "FigD5_5_governance")
