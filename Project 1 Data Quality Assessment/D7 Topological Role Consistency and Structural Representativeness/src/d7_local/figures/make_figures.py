from __future__ import annotations

from pathlib import Path

import matplotlib as mpl
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
from matplotlib.lines import Line2D
import numpy as np
import pandas as pd

from d7_common.config import resolve_paths


# Nature-figure source contract: editable text, explicit final width and Python-only rendering.
mpl.rcParams["font.family"] = "sans-serif"
mpl.rcParams["font.sans-serif"] = ["Arial", "Helvetica", "DejaVu Sans"]
mpl.rcParams["svg.fonttype"] = "none"

FIGURE_WIDTH_MM = 183.0
MM_PER_INCH = 25.4

PALETTE = {
    "ink": "#25282A",
    "neutral_dark": "#5F666B",
    "neutral_mid": "#9AA2A8",
    "neutral_light": "#D9DEE2",
    "neutral_pale": "#F2F4F5",
    "blue": "#2F6F9F",
    "blue_light": "#AFCBDC",
    "teal": "#4F9C8A",
    "green": "#4C8C5A",
    "orange": "#D28B45",
    "red": "#B65C5C",
    "red_light": "#EBCFCB",
    "gold": "#C3A13B",
    "violet": "#8064A2",
    "DO": "#2F6F9F",
    "ORP": "#B65C5C",
    "pass": "#4F9C8A",
    "blocked": "#B65C5C",
    "fail": "#B65C5C",
    "L3": "#2F6F9F",
    "L2": "#4F9C8A",
    "L1": "#D28B45",
    "L0": "#9AA2A8",
    "other": "#AAB2B8",
    "target": "#B65C5C",
}

SCORE_CMAP = LinearSegmentedColormap.from_list(
    "d7_score",
    [PALETTE["red"], PALETTE["red_light"], "#F7F7F7", PALETTE["blue_light"], PALETTE["blue"]],
)


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
                "font.family": "sans-serif",
                "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans"],
                "font.size": 7.0,
                "axes.labelsize": 7.2,
                "axes.titlesize": 7.4,
                "axes.titleweight": "normal",
                "axes.linewidth": 0.75,
                "axes.edgecolor": PALETTE["ink"],
                "axes.labelcolor": PALETTE["ink"],
                "axes.spines.top": False,
                "axes.spines.right": False,
                "xtick.labelsize": 6.6,
                "ytick.labelsize": 6.6,
                "xtick.color": PALETTE["ink"],
                "ytick.color": PALETTE["ink"],
                "xtick.major.size": 3.2,
                "ytick.major.size": 3.2,
                "xtick.major.width": 0.75,
                "ytick.major.width": 0.75,
                "xtick.minor.size": 1.8,
                "ytick.minor.size": 1.8,
                "xtick.minor.width": 0.55,
                "ytick.minor.width": 0.55,
                "xtick.direction": "out",
                "ytick.direction": "out",
                "xtick.top": False,
                "ytick.right": False,
                "legend.fontsize": 6.5,
                "legend.frameon": False,
                "legend.handlelength": 1.7,
                "legend.columnspacing": 1.1,
                "lines.linewidth": 1.05,
                "patch.linewidth": 0.65,
                "savefig.transparent": False,
                "svg.fonttype": "none",
                "pdf.fonttype": 42,
            }
        )

    @staticmethod
    def _figure_size(height_mm: float) -> tuple[float, float]:
        return FIGURE_WIDTH_MM / MM_PER_INCH, height_mm / MM_PER_INCH

    def build_all(self) -> list[Path]:
        outputs: list[Path] = []
        outputs.extend(self._figure_1())
        outputs.extend(self._figure_2())
        outputs.extend(self._figure_3())
        outputs.extend(self._figure_4())
        outputs.extend(self._figure_5())
        return outputs

    def _subset(self, figure: str, panel: str) -> pd.DataFrame:
        return self.data[(self.data["figure_id"] == figure) & (self.data["panel"] == panel)].copy()

    @staticmethod
    def _panel_label(ax: plt.Axes, label: str, *, x: float = -0.09, y: float = 1.035) -> None:
        ax.text(
            x,
            y,
            f"({label})",
            transform=ax.transAxes,
            fontsize=8.1,
            fontweight="bold",
            color=PALETTE["ink"],
            va="bottom",
            ha="left",
            clip_on=False,
        )

    @staticmethod
    def _title(ax: plt.Axes, title: str) -> None:
        ax.set_title(title, loc="left", pad=5.0, fontweight="bold", color=PALETTE["ink"])

    @staticmethod
    def _open_axes(ax: plt.Axes) -> None:
        ax.spines["left"].set_visible(True)
        ax.spines["bottom"].set_visible(True)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.tick_params(which="both", direction="out", top=False, right=False, width=0.75)

    @staticmethod
    def _boxed(ax: plt.Axes) -> None:
        for spine in ax.spines.values():
            spine.set_visible(True)
            spine.set_linewidth(0.75)
        ax.tick_params(which="both", direction="in", top=True, right=True, width=0.75)

    @staticmethod
    def _numeric_ticks(ax: plt.Axes, low: float, high: float, count: int = 5) -> None:
        ax.set_xlim(low, high)
        ax.set_xticks(np.linspace(low, high, count))

    @staticmethod
    def _datetime_ticks(ax: plt.Axes, start: pd.Timestamp, end: pd.Timestamp, count: int = 5) -> None:
        ticks = pd.to_datetime(np.linspace(start.value, end.value, count).astype(np.int64))
        ax.set_xlim(start, end)
        ax.set_xticks(ticks)
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d\n%H:%M"))

    def _save(self, fig: plt.Figure, stem: str) -> list[Path]:
        svg_path = self.paths.figure_root / f"{stem}.svg"
        pdf_path = self.paths.figure_root / f"{stem}.pdf"
        png_path = self.paths.figure_root / f"{stem}.png"
        tiff_path = self.paths.figure_root / f"{stem}.tiff"
        fig.savefig(svg_path, facecolor="white")
        fig.savefig(pdf_path, facecolor="white")
        fig.savefig(png_path, dpi=600, facecolor="white")
        fig.savefig(
            tiff_path,
            dpi=600,
            facecolor="white",
            pil_kwargs={"compression": "tiff_lzw"},
        )
        plt.close(fig)
        return [svg_path, pdf_path, png_path, tiff_path]

    def _figure_1(self) -> list[Path]:
        fig = plt.figure(figsize=self._figure_size(92), layout="constrained")
        grid = fig.add_gridspec(2, 5, width_ratios=[1.15, 1.15, 1.15, 1.0, 1.0])

        ax = fig.add_subplot(grid[:, :3])
        edges = self._subset("FigD7_1_framework", "a")
        for _, edge in edges[edges["record_type"] == "edge"].groupby("group"):
            edge = edge.sort_values("order")
            ax.plot(edge["x_numeric"], edge["value"], color=PALETTE["neutral_mid"], lw=0.9, zorder=1)
            ax.annotate(
                "",
                xy=(edge["x_numeric"].iloc[-1], edge["value"].iloc[-1]),
                xytext=(edge["x_numeric"].iloc[-2], edge["value"].iloc[-2]),
                arrowprops={
                    "arrowstyle": "-|>",
                    "color": PALETTE["neutral_mid"],
                    "lw": 0.8,
                    "mutation_scale": 6,
                },
            )
        nodes = edges[edges["record_type"] == "node"]
        for analyte, frame in nodes.groupby("group"):
            ax.scatter(
                frame["x_numeric"],
                frame["value"],
                s=29,
                marker="o" if analyte == "DO" else "s",
                facecolor=PALETTE[analyte],
                edgecolor="white",
                linewidth=0.55,
                label=analyte,
                zorder=3,
            )
        for record in nodes.itertuples(index=False):
            short_name = record.sensor_id.replace("ORP_", "O").replace("DO_", "D").replace("_", "-")
            ax.text(
                record.x_numeric,
                record.value - 0.12,
                short_name,
                ha="center",
                va="top",
                fontsize=5.8,
                color=PALETTE["ink"],
            )
        ax.text(-0.42, 0, "Line 1", ha="right", va="center", fontsize=6.6)
        ax.text(-0.42, 1, "Line 2", ha="right", va="center", fontsize=6.6)
        ax.text(1.0, 1.28, "Redox zone", ha="center", va="bottom", fontsize=6.4, color=PALETTE["neutral_dark"])
        ax.text(4.5, 1.28, "Aerobic zone", ha="center", va="bottom", fontsize=6.4, color=PALETTE["neutral_dark"])
        ax.set_xlim(-0.85, 6.35)
        ax.set_ylim(-0.42, 1.48)
        ax.set_axis_off()
        ax.legend(loc="lower center", bbox_to_anchor=(0.5, -0.03), ncol=2)
        self._title(ax, "Declared topology and parallel structural roles")
        self._panel_label(ax, "a", x=0.0, y=1.10)

        ax = fig.add_subplot(grid[0, 3:])
        status = self._subset("FigD7_1_framework", "b").sort_values("value", ascending=True)
        status_colors = {
            "limited_support": PALETTE["blue"],
            "out_of_template": PALETTE["orange"],
            "not_evaluable": PALETTE["neutral_mid"],
        }
        y = np.arange(len(status))
        ax.hlines(y, 0, status["value"], color=PALETTE["neutral_light"], lw=1.2, zorder=1)
        ax.scatter(
            status["value"],
            y,
            s=24,
            color=[status_colors.get(name, PALETTE["neutral_mid"]) for name in status["x"]],
            zorder=2,
        )
        for yi, value in zip(y, status["value"]):
            ax.text(value + 0.025, yi, f"{value:.1%}", va="center", fontsize=6.2)
        labels = status["x"].str.replace("_", " ", regex=False)
        ax.set_yticks(y, labels)
        self._numeric_ticks(ax, 0, 1, 5)
        ax.set_xlabel("Fraction of hourly sensor windows")
        self._open_axes(ax)
        self._title(ax, "Local-track applicability")
        self._panel_label(ax, "b", x=-0.13)

        ax = fig.add_subplot(grid[1, 3:])
        gates = self._subset("FigD7_1_framework", "c").sort_values("order")
        y = np.arange(len(gates))[::-1]
        ax.plot(np.zeros(len(y)), y, color=PALETTE["neutral_light"], lw=1.0, zorder=1)
        for yi, record in zip(y, gates.itertuples(index=False)):
            if record.value >= 1:
                color, state = PALETTE["teal"], "available"
            elif "Topology" in record.x:
                color, state = PALETTE["orange"], "pending"
            else:
                color, state = PALETTE["red"], "blocked"
            ax.scatter(0, yi, s=34, color=color, edgecolor="white", linewidth=0.6, zorder=2)
            ax.text(0.12, yi + 0.09, record.x, va="bottom", fontweight="bold", fontsize=6.4)
            ax.text(0.12, yi - 0.08, f"{state}: {record.annotation}", va="top", fontsize=5.8, color=PALETTE["neutral_dark"])
        ax.set_xlim(-0.08, 1.35)
        ax.set_ylim(-0.55, len(gates) - 0.45)
        ax.set_axis_off()
        self._title(ax, "Evidence boundary and release state")
        self._panel_label(ax, "c", x=0.0, y=1.10)
        return self._save(fig, "FigD7_1_framework")

    def _figure_2(self) -> list[Path]:
        fig = plt.figure(figsize=self._figure_size(122), layout="constrained")
        grid = fig.add_gridspec(2, 2, height_ratios=[1.72, 1.0], width_ratios=[1.0, 1.0])

        ax = fig.add_subplot(grid[0, :])
        heat = self._subset("FigD7_2_spatiotemporal", "a")
        heat["date"] = pd.to_datetime(heat["x"])
        sensor_order = heat[["y", "order"]].drop_duplicates().sort_values("order")["y"].tolist()
        matrix = heat.pivot(index="y", columns="date", values="value").reindex(sensor_order)
        image = ax.imshow(
            matrix.to_numpy(),
            aspect="auto",
            cmap=SCORE_CMAP,
            vmin=1,
            vmax=5,
            interpolation="nearest",
        )
        positions = np.linspace(0, len(matrix.columns) - 1, 6).round().astype(int)
        ax.set_xticks(positions, [matrix.columns[index].strftime("%b\n%Y") for index in positions])
        ax.set_yticks(np.arange(len(sensor_order)), [sensor.replace("_", "-") for sensor in sensor_order])
        do_count = sum(sensor.startswith("DO_") for sensor in sensor_order)
        if 0 < do_count < len(sensor_order):
            ax.axhline(do_count - 0.5, color="white", lw=1.15)
        ax.set_xlabel("Date")
        ax.set_ylabel("Sensor")
        colorbar = fig.colorbar(image, ax=ax, fraction=0.022, pad=0.014, ticks=[1, 2, 3, 4, 5])
        colorbar.set_label("Daily lower-quartile D7 raw score")
        colorbar.ax.tick_params(direction="in", width=0.7, length=2.6)
        self._boxed(ax)
        self._title(ax, "Low-score periods are heterogeneous across sensors and time")
        self._panel_label(ax, "a", x=-0.055)

        ax = fig.add_subplot(grid[1, 0])
        distribution = self._subset("FigD7_2_spatiotemporal", "b")
        values_by_analyte: list[np.ndarray] = []
        counts: list[int] = []
        for analyte in ["DO", "ORP"]:
            values = distribution.loc[distribution["group"] == analyte, "value"].to_numpy(dtype=float)
            n_before = len(values)
            values = values[np.isfinite(values)]
            n_after = len(values)
            values_by_analyte.append(values)
            counts.append(n_after)
            if n_after > n_before:
                raise RuntimeError("Finite-value count cannot exceed source count")
        violin = ax.violinplot(values_by_analyte, positions=[0, 1], widths=0.74, showextrema=False)
        for body, analyte in zip(violin["bodies"], ["DO", "ORP"]):
            body.set_facecolor(PALETTE[analyte])
            body.set_edgecolor("none")
            body.set_alpha(0.46)
        box = ax.boxplot(
            values_by_analyte,
            positions=[0, 1],
            widths=0.18,
            patch_artist=True,
            showfliers=False,
            medianprops={"color": PALETTE["ink"], "linewidth": 1.0},
            whiskerprops={"color": PALETTE["ink"], "linewidth": 0.75},
            capprops={"color": PALETTE["ink"], "linewidth": 0.75},
        )
        for patch in box["boxes"]:
            patch.set_facecolor("white")
            patch.set_edgecolor(PALETTE["ink"])
            patch.set_linewidth(0.75)
        ax.axhline(3.0, color=PALETTE["neutral_dark"], lw=0.75, ls="--")
        for position, count in enumerate(counts):
            ax.text(position, 5.04, f"n={count:,}", ha="center", va="bottom", fontsize=5.8)
        ax.set_xticks([0, 1], ["DO", "ORP"])
        ax.set_ylim(1, 5.22)
        ax.set_yticks([1, 2, 3, 4, 5])
        ax.set_ylabel("D7 raw score")
        self._open_axes(ax)
        self._title(ax, "Full score distributions")
        self._panel_label(ax, "b")

        ax = fig.add_subplot(grid[1, 1])
        support = self._subset("FigD7_2_spatiotemporal", "c")
        analytes = ["DO", "ORP"]
        left = np.zeros(2)
        for level in ["L3", "L2", "L1", "L0"]:
            values = np.asarray(
                [
                    support.loc[(support["x"] == analyte) & (support["group"] == level), "value"].sum()
                    for analyte in analytes
                ],
                dtype=float,
            )
            if values.sum() == 0:
                continue
            bars = ax.barh(analytes, values, left=left, height=0.48, label=level, color=PALETTE[level], edgecolor="white")
            for bar, value in zip(bars, values):
                if value >= 2:
                    ax.text(
                        bar.get_x() + bar.get_width() / 2,
                        bar.get_y() + bar.get_height() / 2,
                        f"{value:.0f}",
                        ha="center",
                        va="center",
                        fontsize=5.9,
                        color="white" if level in {"L3", "L1"} else PALETTE["ink"],
                    )
            left += values
        high = max(35.0, float(np.ceil(left.max() / 5.0) * 5.0))
        ax.set_xlim(0, high)
        ax.set_xticks([0, 10, 20, 30, high] if high > 30 else [0, 10, 20, high])
        ax.set_xlabel("Number of regime templates")
        ax.legend(title="Support tier", ncol=4, loc="lower right", bbox_to_anchor=(1.0, 1.0))
        self._open_axes(ax)
        self._title(ax, "Effective template support")
        self._panel_label(ax, "c")
        return self._save(fig, "FigD7_2_spatiotemporal")

    def _figure_3(self) -> list[Path]:
        fig = plt.figure(figsize=self._figure_size(120), layout="constrained")
        grid = fig.add_gridspec(2, 2, height_ratios=[1.55, 1.0], width_ratios=[1.05, 1.0])

        ax = fig.add_subplot(grid[0, :])
        case = self._subset("FigD7_3_evidence", "a")
        series = case[case["record_type"] == "case_timeseries"]
        interval = case[case["record_type"] == "event_interval"].sort_values("order")
        colors = {
            "D7_raw": PALETTE["ink"],
            "Q_profile": PALETTE["blue"],
            "Q_gradient": PALETTE["orange"],
            "Q_rank": PALETTE["gold"],
            "Q_rep": PALETTE["teal"],
        }
        labels = {
            "D7_raw": "D7 raw",
            "Q_profile": "Profile",
            "Q_gradient": "Gradient",
            "Q_rank": "Rank",
            "Q_rep": "Representation",
        }
        if len(interval) == 2:
            event_start, event_end = pd.to_datetime(interval["x"].tolist())
            ax.axvspan(event_start, event_end, color=PALETTE["red_light"], alpha=0.46, lw=0, zorder=0)
            ax.text(
                event_start + (event_end - event_start) / 2,
                1.08,
                "candidate event",
                ha="center",
                va="bottom",
                fontsize=5.8,
                color=PALETTE["red"],
            )
        for metric in ["Q_profile", "Q_gradient", "Q_rank", "Q_rep", "D7_raw"]:
            frame = series[series["group"] == metric]
            line, = ax.plot(
                pd.to_datetime(frame["x"]),
                frame["value"],
                color=colors[metric],
                lw=1.45 if metric == "D7_raw" else 0.95,
                label=labels[metric],
                zorder=3 if metric == "D7_raw" else 2,
            )
            if not frame.empty:
                first = frame.iloc[0]
                offset = {"D7_raw": 0.05, "Q_rep": -0.05}.get(metric, 0.0)
                ax.annotate(
                    labels[metric],
                    xy=(pd.Timestamp(first["x"]), float(first["value"]) + offset),
                    xytext=(5, 0),
                    textcoords="offset points",
                    color=line.get_color(),
                    fontsize=5.7,
                    va="center",
                    ha="left",
                    bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.74, "pad": 0.25},
                    zorder=5,
                )
        ax.axhline(3.0, color=PALETTE["neutral_dark"], lw=0.75, ls="--")
        ax.set_ylim(1, 5)
        ax.set_yticks([1, 2, 3, 4, 5])
        if not series.empty:
            dates = pd.to_datetime(series["x"])
            self._datetime_ticks(ax, dates.min(), dates.max(), 6)
        ax.set_ylabel("Quality score")
        self._open_axes(ax)
        self._title(ax, "Component evidence converges during the unlabeled low-score event")
        self._panel_label(ax, "a", x=-0.055)

        ax = fig.add_subplot(grid[1, 0])
        ranking = self._subset("FigD7_3_evidence", "b").sort_values("value", ascending=True)
        y = np.arange(len(ranking))
        colors = [PALETTE["red"] if group == "target" else PALETTE["blue_light"] for group in ranking["group"]]
        ax.hlines(y, 0, ranking["value"], color=colors, lw=1.35)
        ax.scatter(ranking["value"], y, color=colors, s=19, edgecolor="white", linewidth=0.4, zorder=2)
        ax.set_yticks(y, ranking["x"].str.replace("_", "-", regex=False))
        self._numeric_ticks(ax, 0, 1, 5)
        ax.set_xlabel("Node influence")
        self._open_axes(ax)
        self._title(ax, "Target-excluded attribution")
        self._panel_label(ax, "b")

        ax = fig.add_subplot(grid[1, 1])
        consensus = self._subset("FigD7_3_evidence", "c").sort_values("value", ascending=True)
        y = np.arange(len(consensus))
        ax.hlines(y, 0, consensus["value"], color=PALETTE["neutral_light"], lw=1.2)
        ax.scatter(consensus["value"], y, color=PALETTE["blue"], s=18, zorder=2)
        for yi, value in zip(y, consensus["value"]):
            ax.text(value + 0.02, yi, f"{value:.1%}", va="center", fontsize=5.9)
        labels = consensus["x"].str.replace("_", " ", regex=False)
        ax.set_yticks(y, labels)
        self._numeric_ticks(ax, 0, 1, 5)
        ax.set_xlabel("Fraction of pair-hours")
        self._open_axes(ax)
        self._title(ax, "D7-to-D6 consensus context")
        self._panel_label(ax, "c")
        return self._save(fig, "FigD7_3_evidence")

    def _criterion_plot(self, ax: plt.Axes, frame: pd.DataFrame) -> None:
        frame = frame.sort_values("order", ascending=False)
        y = np.arange(len(frame))
        top_y = int(y.max()) if len(y) else 0
        for yi, record in zip(y, frame.itertuples(index=False)):
            color = PALETTE["teal"] if record.group == "pass" else PALETTE["red"]
            ax.plot([record.target, record.value], [yi, yi], color=PALETTE["neutral_light"], lw=1.2, zorder=1)
            ax.scatter(record.target, yi, s=20, facecolor="white", edgecolor=PALETTE["neutral_dark"], marker="D", linewidth=0.75, zorder=2)
            ax.scatter(record.value, yi, s=24, color=color, edgecolor="white", linewidth=0.45, zorder=3)
            label_offset = -0.17 if yi == top_y else 0.17
            ax.text(
                record.value,
                yi + label_offset,
                f"{record.value:.2f}",
                va="top" if label_offset < 0 else "bottom",
                ha="center",
                fontsize=5.8,
                color=color,
            )
        labels = frame["x"].str.replace("_", " ", regex=False)
        ax.set_yticks(y, labels)
        self._numeric_ticks(ax, 0, 1, 5)
        self._open_axes(ax)

    def _figure_4(self) -> list[Path]:
        fig = plt.figure(figsize=self._figure_size(145), layout="constrained")
        grid = fig.add_gridspec(3, 2, height_ratios=[1.0, 1.0, 0.9], width_ratios=[1.12, 1.0])

        ax = fig.add_subplot(grid[:2, 0])
        acceptance = self._subset("FigD7_4_validation", "a")
        self._criterion_plot(ax, acceptance)
        ax.set_xlabel("Estimate and prespecified target")
        legend = [
            Line2D([0], [0], marker="o", color="none", markerfacecolor=PALETTE["teal"], markeredgecolor="white", markersize=5, label="Pass"),
            Line2D([0], [0], marker="o", color="none", markerfacecolor=PALETTE["red"], markeredgecolor="white", markersize=5, label="Fail"),
            Line2D([0], [0], marker="D", color="none", markerfacecolor="white", markeredgecolor=PALETTE["neutral_dark"], markersize=4.5, label="Target"),
        ]
        ax.legend(handles=legend, loc="lower right", ncol=3)
        self._title(ax, "Release criteria retain one localization failure")
        self._panel_label(ax, "a", x=-0.12)

        ax = fig.add_subplot(grid[0, 1])
        top1 = self._subset("FigD7_4_validation", "b").sort_values("value", ascending=True)
        y = np.arange(len(top1))
        ax.axvline(0.80, color=PALETTE["neutral_dark"], lw=0.75, ls="--")
        ax.hlines(y, 0, top1["value"], color=PALETTE["red_light"], lw=1.2)
        ax.scatter(top1["value"], y, color=PALETTE["red"], s=23, zorder=2)
        for yi, value in zip(y, top1["value"]):
            ax.text(value - 0.02, yi, f"{value:.2f}", va="center", ha="right", fontsize=5.8)
        ax.set_yticks(y, top1["x"].str.replace("_", " ", regex=False))
        self._numeric_ticks(ax, 0, 1, 5)
        ax.set_xlabel("Top-1 accuracy")
        self._open_axes(ax)
        self._title(ax, "Localization by injected scenario")
        self._panel_label(ax, "b", x=-0.13)

        ax = fig.add_subplot(grid[1, 1])
        negative = self._subset("FigD7_4_validation", "c").sort_values("value", ascending=True)
        y = np.arange(len(negative))
        ax.axvline(0.10, color=PALETTE["neutral_dark"], lw=0.75, ls="--")
        low = negative["value"] - negative["value_low"]
        high = negative["value_high"] - negative["value"]
        ax.errorbar(
            negative["value"],
            y,
            xerr=[low, high],
            fmt="o",
            color=PALETTE["blue"],
            ecolor=PALETTE["neutral_dark"],
            markersize=3.8,
            capsize=2.0,
            elinewidth=0.75,
        )
        ax.set_yticks(y, negative["x"].str.replace("_", " ", regex=False))
        upper = max(0.20, float(negative["value_high"].max()) * 1.08)
        self._numeric_ticks(ax, 0, upper, 5)
        ax.set_xlabel("False alarm rate (95% CI)")
        self._open_axes(ax)
        self._title(ax, "Negative-control specificity")
        self._panel_label(ax, "c", x=-0.13)

        ax = fig.add_subplot(grid[2, :])
        invariance = self._subset("FigD7_4_validation", "d").sort_values("order", ascending=False)
        self._criterion_plot(ax, invariance)
        ax.set_xlabel("Estimate and prespecified target")
        self._title(ax, "Local and sensitivity tracks remain invariant")
        self._panel_label(ax, "d", x=-0.055)
        return self._save(fig, "FigD7_4_validation")

    def _figure_5(self) -> list[Path]:
        fig = plt.figure(figsize=self._figure_size(148), layout="constrained")
        grid = fig.add_gridspec(3, 2, height_ratios=[0.78, 1.48, 0.82], width_ratios=[1.0, 1.08])

        ax = fig.add_subplot(grid[0, 0])
        support = self._subset("FigD7_5_governance", "a")
        analytes = ["DO", "ORP"]
        left = np.zeros(2)
        for level in ["L3", "L2", "L1", "L0"]:
            values = np.asarray(
                [support.loc[(support["x"] == analyte) & (support["group"] == level), "value"].sum() for analyte in analytes],
                dtype=float,
            )
            if values.sum() == 0:
                continue
            ax.barh(analytes, values, left=left, height=0.48, color=PALETTE[level], label=level, edgecolor="white")
            left += values
        high = max(35.0, float(np.ceil(left.max() / 5.0) * 5.0))
        ax.set_xlim(0, high)
        ax.set_xticks([0, 10, 20, 30, high] if high > 30 else [0, 10, 20, high])
        ax.set_xlabel("Template count")
        ax.legend(title="Support tier", ncol=4, loc="lower right", bbox_to_anchor=(1.0, 1.0))
        self._open_axes(ax)
        self._title(ax, "Support governance")
        self._panel_label(ax, "a", x=-0.13)

        ax = fig.add_subplot(grid[0, 1])
        states = self._subset("FigD7_5_governance", "b").sort_values("value", ascending=True)
        y = np.arange(len(states))
        ax.hlines(y, 0, states["value"], color=PALETTE["neutral_light"], lw=1.2)
        colors = [PALETTE["blue"] if state == "Locked" else PALETTE["orange"] for state in states["x"]]
        ax.scatter(states["value"], y, color=colors, s=20, zorder=2)
        for yi, value in zip(y, states["value"]):
            ax.text(value + 0.025, yi, f"{value:.1%}", va="center", fontsize=5.8)
        state_labels = states["x"].replace({"OODHold": "OOD hold", "SwitchCandidate": "Switch candidate", "ActiveNew": "Active new"})
        ax.set_yticks(y, state_labels)
        self._numeric_ticks(ax, 0, 1, 5)
        ax.set_xlabel("Fraction of 10-min target states")
        self._open_axes(ax)
        self._title(ax, "MAP-hysteresis occupancy")
        self._panel_label(ax, "b", x=-0.13)

        ax = fig.add_subplot(grid[1, :])
        drift = self._subset("FigD7_5_governance", "c").sort_values("value", ascending=True)
        y = np.arange(len(drift))
        colors = [PALETTE["red"] if group == "review" else PALETTE["neutral_mid"] for group in drift["group"]]
        ax.hlines(y, 0, drift["value"], color=colors, lw=1.25)
        ax.scatter(drift["value"], y, color=colors, s=18, edgecolor="white", linewidth=0.35, zorder=2)
        ax.axvline(0.35, color=PALETTE["ink"], lw=0.75, ls="--")
        ax.set_yticks(y, drift["x"].str.replace("_", "-", regex=False))
        high = max(0.50, float(np.ceil(drift["value"].max() * 2.0) / 2.0))
        self._numeric_ticks(ax, 0, high, int(high / 0.5) + 1)
        ax.set_xlabel("Candidate versus declared log-likelihood ratio")
        self._open_axes(ax)
        self._title(ax, "Topology drift remains report-only")
        self._panel_label(ax, "c", x=-0.055)

        ax = fig.add_subplot(grid[2, :])
        gates = self._subset("FigD7_5_governance", "d").sort_values("order")
        x = np.arange(len(gates), dtype=float)
        ax.plot(x, np.zeros(len(x)), color=PALETTE["neutral_light"], lw=1.2, zorder=1)
        for index, record in enumerate(gates.itertuples(index=False)):
            color = PALETTE["teal"] if record.value >= 1 else PALETTE["red"]
            ax.scatter(index, 0, s=46, color=color, edgecolor="white", linewidth=0.7, zorder=2)
            ax.text(index, -0.16, record.x, ha="center", va="top", fontsize=6.0)
            state = "passed" if record.value >= 1 else "blocked"
            ax.text(index, 0.16, state, ha="center", va="bottom", fontsize=5.7, color=color, fontweight="bold")
        ax.set_xlim(-0.35, len(gates) - 0.65)
        ax.set_ylim(-0.42, 0.42)
        ax.set_axis_off()
        self._title(ax, "Production release remains closed until all gates pass")
        self._panel_label(ax, "d", x=-0.055, y=1.0)
        return self._save(fig, "FigD7_5_governance")
