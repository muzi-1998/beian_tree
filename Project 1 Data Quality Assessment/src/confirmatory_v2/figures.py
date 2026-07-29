from __future__ import annotations

import json
from pathlib import Path

import matplotlib as mpl
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D

from .common import sha256_file


mpl.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "Helvetica", "DejaVu Sans", "sans-serif"],
        "svg.fonttype": "none",
        "pdf.fonttype": 42,
        "font.size": 7,
        "axes.titlesize": 8,
        "axes.labelsize": 7,
        "xtick.labelsize": 6.5,
        "ytick.labelsize": 6.5,
        "axes.linewidth": 0.8,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "legend.frameon": False,
        "legend.fontsize": 6.5,
        "xtick.direction": "out",
        "ytick.direction": "out",
        "xtick.major.width": 0.8,
        "ytick.major.width": 0.8,
        "xtick.major.size": 3.0,
        "ytick.major.size": 3.0,
    }
)

BLUE = "#0F4D92"
BLUE_2 = "#3775BA"
BLUE_MID = "#7884B4"
BLUE_SOFT = "#B4C0E4"
ROSE = "#C76D7E"
TEAL = "#42949E"
GOLD = "#C89B3C"
RED = "#B64342"
GRAY = "#767676"
DARK = "#3F3F3F"
LIGHT = "#D9D9D9"
VERY_LIGHT = "#F2F2F2"
DETECTION_CMAP = mpl.colors.LinearSegmentedColormap.from_list(
    "detection_probability",
    ["#F4F5F8", "#B4C0E4", "#3775BA", "#0F4D92"],
)


def _panel_label(ax: plt.Axes, label: str) -> None:
    ax.text(
        -0.14,
        1.04,
        f"({label})",
        transform=ax.transAxes,
        ha="left",
        va="bottom",
        fontsize=8,
        fontweight="bold",
        clip_on=False,
    )


def _save(fig: plt.Figure, path: Path) -> None:
    fig.savefig(path.with_suffix(".svg"), bbox_inches="tight")
    fig.savefig(path.with_suffix(".pdf"), bbox_inches="tight")
    fig.savefig(path.with_suffix(".png"), dpi=600, bbox_inches="tight")
    fig.savefig(
        path.with_suffix(".tiff"),
        dpi=600,
        bbox_inches="tight",
        pil_kwargs={"compression": "tiff_lzw"},
    )
    plt.close(fig)


def _write_source_data(path: Path, tables: dict[str, pd.DataFrame]) -> Path:
    source_path = path.parent / f"{path.name}_source_data.xlsx"
    with pd.ExcelWriter(source_path, engine="openpyxl") as writer:
        for sheet_name, frame in tables.items():
            frame.to_excel(writer, sheet_name=sheet_name[:31], index=False)
    return source_path


def _interval_error(frame: pd.DataFrame, estimate: str = "estimate") -> np.ndarray:
    return np.vstack(
        [
            np.maximum(frame[estimate] - frame["ci95_low"], 0.0),
            np.maximum(frame["ci95_high"] - frame[estimate], 0.0),
        ]
    )


def figure_d1(outputs: dict[str, pd.DataFrame], figure_dir: Path) -> list[Path]:
    applicability = outputs["D1_applicability_map"].copy()
    shown = applicability[
        applicability["route"].eq("all_routes")
        & applicability["resolution_mode"].eq("original")
    ].copy()
    faults = [
        ("spike", "Spike"),
        ("step", "Step"),
        ("linear_drift", "Linear drift"),
    ]
    analytes = ["DO", "ORP"]
    fig, axes = plt.subplots(3, 2, figsize=(7.2, 6.3))
    panel_index = 0
    image = None
    for row_index, (fault, fault_label) in enumerate(faults):
        for column_index, analyte in enumerate(analytes):
            ax = axes[row_index, column_index]
            frame = shown[
                shown["fault_type"].eq(fault)
                & shown["analyte"].eq(analyte)
            ].copy()
            matrix = frame.pivot(
                index="amplitude_bin",
                columns="duration_bin",
                values="detection_probability",
            ).sort_index()
            image = ax.imshow(
                matrix.to_numpy(),
                origin="lower",
                aspect="auto",
                vmin=0,
                vmax=1,
                cmap=DETECTION_CMAP,
                interpolation="nearest",
            )
            cell_lookup = frame.set_index(["amplitude_bin", "duration_bin"])
            for y_index, amplitude_bin in enumerate(matrix.index):
                for x_index, duration_bin in enumerate(matrix.columns):
                    key = (amplitude_bin, duration_bin)
                    if key not in cell_lookup.index:
                        continue
                    cell = cell_lookup.loc[key]
                    value = float(cell["detection_probability"])
                    color = "white" if value >= 0.62 else DARK
                    ax.text(
                        x_index,
                        y_index,
                        f"{value:.2f}",
                        ha="center",
                        va="center",
                        color=color,
                        fontsize=6.2,
                    )
            x_labels = []
            for duration_bin in matrix.columns:
                cell = frame[frame["duration_bin"].eq(duration_bin)].iloc[0]
                x_labels.append(
                    f"{cell.duration_low:.1f}\n{cell.duration_high:.1f}"
                )
            y_labels = []
            for amplitude_bin in matrix.index:
                cell = frame[frame["amplitude_bin"].eq(amplitude_bin)].iloc[0]
                y_labels.append(
                    f"{cell.amplitude_low_sigma:.1f}-{cell.amplitude_high_sigma:.1f}"
                )
            ax.set_xticks(np.arange(len(x_labels)), x_labels)
            ax.set_yticks(np.arange(len(y_labels)), y_labels)
            unit = str(frame["duration_unit"].iloc[0])
            ax.set_xlabel(f"Duration range ({unit})")
            ax.set_ylabel("Amplitude range (local sigma)")
            ax.set_title(f"{fault_label}, {analyte}")
            _panel_label(ax, chr(ord("a") + panel_index))
            panel_index += 1
    colorbar = fig.colorbar(
        image,
        ax=axes,
        fraction=0.022,
        pad=0.025,
        aspect=35,
    )
    colorbar.set_label("Detection probability")
    colorbar.set_ticks([0, 0.25, 0.5, 0.75, 1.0])
    fig.subplots_adjust(
        left=0.11,
        right=0.90,
        bottom=0.08,
        top=0.97,
        wspace=0.27,
        hspace=0.45,
    )
    path = figure_dir / "FigV2_D1_applicability_boundary"
    _save(fig, path)
    _write_source_data(
        path,
        {
            "amplitude_duration": shown,
            "high_amplitude": outputs["D1_high_amplitude_summary"],
            "raw_domain_audit": outputs["D1_raw_endpoint_summary"],
        },
    )
    return [path]


def _d2_setting_label(row) -> str:
    suffix = {
        "qfa_window_hours": " h",
        "hard_rle_minutes": " min",
        "gap_break_multiplier": "x",
    }[row.parameter]
    return f"{row.setting:g}{suffix}"


def figure_d2(outputs: dict[str, pd.DataFrame], figure_dir: Path) -> list[Path]:
    summary = outputs["D2_oat_summary"].copy().reset_index(drop=True)
    parameter_order = [
        "qfa_window_hours",
        "hard_rle_minutes",
        "gap_break_multiplier",
    ]
    labels = {
        "qfa_window_hours": "QFA window",
        "hard_rle_minutes": "Hard RLE",
        "gap_break_multiplier": "Gap mapping",
    }
    colors = {
        "qfa_window_hours": BLUE,
        "hard_rle_minutes": TEAL,
        "gap_break_multiplier": ROSE,
    }
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 2.75))
    positions = np.arange(len(summary))
    setting_labels = [_d2_setting_label(row) for row in summary.itertuples()]
    for ax, metric, title, threshold in (
        (
            axes[0],
            "channel_rank_spearman",
            "Channel ranking remains stable",
            0.90,
        ),
        (
            axes[1],
            "event_jaccard",
            "Event boundaries are parameter-sensitive",
            0.75,
        ),
    ):
        for parameter in parameter_order:
            frame = summary[summary["parameter"].eq(parameter)]
            group_positions = frame.index.to_numpy()
            ax.plot(
                group_positions,
                frame[metric],
                marker="o",
                ms=3.8,
                lw=1.15,
                color=colors[parameter],
                label=labels[parameter],
            )
        ax.axhline(threshold, color=GRAY, lw=0.8, ls="--")
        ax.set_xticks(positions, setting_labels, rotation=38, ha="right")
        ax.set_ylim(0, 1.03)
        ax.set_xlabel("Prespecified one-at-a-time setting")
        ax.set_ylabel(
            "Channel-rank Spearman"
            if metric == "channel_rank_spearman"
            else "Event Jaccard"
        )
        ax.set_title(title)
    axes[0].legend(loc="lower left")
    _panel_label(axes[0], "a")
    _panel_label(axes[1], "b")
    fig.subplots_adjust(
        left=0.09,
        right=0.985,
        bottom=0.28,
        top=0.90,
        wspace=0.30,
    )
    path = figure_dir / "FigV2_D2_oat_stability"
    _save(fig, path)
    _write_source_data(
        path,
        {
            "oat_summary": summary,
            "sensor_detail": outputs["D2_oat_by_sensor"],
            "floor_challenges": outputs["D2_process_floor_challenges"],
        },
    )
    return [path]


def figure_d3(outputs: dict[str, pd.DataFrame], figure_dir: Path) -> list[Path]:
    gate = outputs["D3_safety_gate"].copy()
    gate["analyte"] = gate["sensor_id"].str.split("_").str[0]
    composition = (
        gate.groupby(["analyte", "D3_gate_status"], as_index=False)
        .size()
        .rename(columns={"size": "windows"})
    )
    composition["fraction"] = composition["windows"] / composition.groupby(
        "analyte"
    )["windows"].transform("sum")
    oat = outputs["D3_oat_summary"].copy()
    fig, axes = plt.subplots(1, 3, figsize=(7.2, 2.7))

    ax = axes[0]
    pivot = composition.pivot(
        index="analyte",
        columns="D3_gate_status",
        values="fraction",
    ).fillna(0)
    status_order = ["Pass", "Warn", "Fail"]
    palette = {"Pass": BLUE, "Warn": GOLD, "Fail": RED}
    bottom = np.zeros(len(pivot))
    for status in status_order:
        values = (
            pivot[status].to_numpy() if status in pivot.columns else np.zeros(len(pivot))
        )
        ax.bar(
            np.arange(len(pivot)),
            values,
            bottom=bottom,
            color=palette[status],
            width=0.62,
            label=status,
        )
        bottom += values
    ax.set_xticks(np.arange(len(pivot)), pivot.index)
    ax.set_ylim(0, 1)
    ax.set_ylabel("Window fraction")
    ax.set_title("Independent Safety Gate")
    ax.legend(
        ncol=3,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.16),
        frameon=False,
        handletextpad=0.45,
        columnspacing=0.8,
    )
    _panel_label(ax, "a")

    ax = axes[1]
    parameter_styles = {
        "soft_boundary_multiplier": (BLUE, "Soft value bounds"),
        "rate_threshold_multiplier": (TEAL, "Rate threshold"),
    }
    for parameter, (color, label) in parameter_styles.items():
        frame = oat[oat["parameter"].eq(parameter)]
        ax.plot(
            frame["setting"],
            frame["event_jaccard"],
            marker="o",
            ms=3.8,
            lw=1.15,
            color=color,
            label=label,
        )
    ax.axhline(0.75, color=GRAY, ls="--", lw=0.8)
    ax.set_ylim(0, 1.03)
    ax.set_xlabel("Threshold multiplier")
    ax.set_ylabel("Warning-event Jaccard")
    ax.set_title("Event-boundary sensitivity")
    ax.legend(loc="lower left")
    _panel_label(ax, "b")

    ax = axes[2]
    burden = oat.copy()
    burden["label"] = burden.apply(
        lambda row: (
            f"Value {row.setting:g}x"
            if row.parameter.startswith("soft")
            else f"Rate {row.setting:g}x"
        ),
        axis=1,
    )
    colors = np.where(
        burden["warning_burden_change"].gt(0),
        ROSE,
        np.where(burden["warning_burden_change"].lt(0), TEAL, LIGHT),
    )
    y = np.arange(len(burden))
    ax.barh(y, burden["warning_burden_change"], color=colors, height=0.58)
    ax.axvline(0, color=GRAY, lw=0.8)
    ax.set_yticks(y, burden["label"])
    ax.set_xlabel("Change in warning windows")
    ax.set_title("Warning burden")
    _panel_label(ax, "c")

    fig.subplots_adjust(
        left=0.08,
        right=0.985,
        bottom=0.23,
        top=0.89,
        wspace=0.42,
    )
    path = figure_dir / "FigV2_D3_safety_gate"
    _save(fig, path)
    _write_source_data(
        path,
        {
            "gate_composition": composition,
            "oat_summary": oat,
            "threshold_register": outputs["D3_threshold_register_v2"],
        },
    )
    return [path]


def figure_d4_d5(
    d4: dict[str, pd.DataFrame],
    d5: dict[str, pd.DataFrame],
    figure_dir: Path,
) -> list[Path]:
    summary = d4["D4_mechanism_summary"].copy()
    lag = d4["D4_lag_response"].copy()
    fold = d5["D5_outer_refit_fold_metrics"].copy()
    variant_order = [
        "full_reference",
        "no_exogenous_context",
        "no_regime_conditioning",
        "no_hysteresis",
    ]
    variant_labels = {
        "full_reference": "Full",
        "no_exogenous_context": "No exogenous",
        "no_regime_conditioning": "No regime",
        "no_hysteresis": "No hysteresis",
    }
    variant_colors = {
        "full_reference": BLUE,
        "no_exogenous_context": BLUE_2,
        "no_regime_conditioning": BLUE_MID,
        "no_hysteresis": BLUE_SOFT,
    }
    fig, axes = plt.subplots(2, 2, figsize=(7.2, 5.3))

    ax = axes[0, 0]
    mechanism = summary[summary["metric"].eq("AUROC")].copy()
    mechanism["label"] = (
        mechanism["scenario"]
        .str.replace("target_", "Target\n", regex=False)
        .str.replace("peer_", "Peer\n", regex=False)
    )
    x = np.arange(len(mechanism))
    ax.errorbar(
        x,
        mechanism["estimate"],
        yerr=_interval_error(mechanism),
        fmt="o",
        ms=4,
        color=BLUE,
        ecolor=BLUE_MID,
        capsize=2,
        lw=0.9,
    )
    common = summary[
        summary["metric"].isin(
            ["conditional_new_FAR", "asymmetry_detection_rate"]
        )
    ].copy()
    for offset, row in enumerate(common.itertuples(index=False)):
        position = len(mechanism) + offset
        color = ROSE if row.metric == "conditional_new_FAR" else TEAL
        ax.errorbar(
            position,
            row.estimate,
            yerr=np.array(
                [
                    [max(row.estimate - row.ci95_low, 0)],
                    [max(row.ci95_high - row.estimate, 0)],
                ]
            ),
            fmt="s",
            ms=3.8,
            color=color,
            ecolor=color,
            capsize=2,
            lw=0.9,
        )
    labels = mechanism["label"].tolist() + [
        value.replace("_", "\n") for value in common["scenario"]
    ]
    ax.set_xticks(np.arange(len(labels)), labels, rotation=28, ha="right")
    ax.set_ylim(0, 1.03)
    ax.set_ylabel("Estimate (cluster-bootstrap 95% CI)")
    ax.set_title("D4 detection and process controls")
    ax.legend(
        handles=[
            Line2D([], [], marker="o", ls="", color=BLUE, label="Fault AUROC"),
            Line2D([], [], marker="s", ls="", color=ROSE, label="Common FAR"),
            Line2D([], [], marker="s", ls="", color=TEAL, label="Asymmetry"),
        ],
        loc="lower left",
    )
    _panel_label(ax, "a")

    ax = axes[0, 1]
    for variable, color, marker in (
        ("DO", BLUE, "o"),
        ("ORP", ROSE, "s"),
    ):
        frame = lag[lag["variable"].eq(variable)].sort_values("lag_minutes")
        ax.plot(
            frame["lag_minutes"],
            5.0 - frame["mean_D4"],
            color=color,
            marker=marker,
            ms=3.8,
            lw=1.15,
            label=variable,
        )
        subhour = frame[frame["reporting_role"].str.startswith("supplementary")]
        ax.scatter(
            subhour["lag_minutes"],
            5.0 - subhour["mean_D4"],
            facecolors="white",
            edgecolors=color,
            marker=marker,
            s=24,
            zorder=4,
        )
    ax.axvspan(0, 30, color=VERY_LIGHT, zorder=0)
    ax.set_xlabel("Injected peer lag (min)")
    ax.set_ylabel("D4 anomaly severity (5 - D4)")
    ax.set_title("Lag response; subhour region is sensitivity-only")
    ax.legend(loc="upper left")
    _panel_label(ax, "b")

    ax = axes[1, 0]
    detection = fold[fold["metric"].isin(["AUROC", "AUPRC"])].copy()
    offsets = {"AUROC": -0.11, "AUPRC": 0.11}
    markers = {"AUROC": "o", "AUPRC": "s"}
    for variant_index, variant in enumerate(variant_order):
        frame = detection[detection["variant"].eq(variant)]
        for metric in ["AUROC", "AUPRC"]:
            metric_frame = frame[frame["metric"].eq(metric)]
            x_values = np.full(len(metric_frame), variant_index + offsets[metric])
            ax.scatter(
                x_values,
                metric_frame["estimate"],
                marker=markers[metric],
                s=20,
                facecolors=(
                    variant_colors[variant] if metric == "AUROC" else "white"
                ),
                edgecolors=variant_colors[variant],
                linewidths=0.8,
                alpha=0.9,
            )
            ax.hlines(
                metric_frame["estimate"].mean(),
                variant_index + offsets[metric] - 0.07,
                variant_index + offsets[metric] + 0.07,
                color=DARK,
                lw=1.3,
            )
    ax.axhline(0.90, color=GRAY, ls="--", lw=0.8)
    ax.axhline(0.80, color=GRAY, ls=":", lw=0.8)
    ax.set_xticks(
        np.arange(len(variant_order)),
        [variant_labels[value] for value in variant_order],
        rotation=25,
        ha="right",
    )
    ax.set_ylim(0, 1.03)
    ax.set_ylabel("Future-month fold estimate")
    ax.set_title("D5 detection under full outer refit")
    ax.legend(
        handles=[
            Line2D([], [], marker="o", ls="", color=DARK, label="AUROC"),
            Line2D(
                [],
                [],
                marker="s",
                ls="",
                color=DARK,
                markerfacecolor="white",
                label="AUPRC",
            ),
        ],
        loc="lower left",
    )
    _panel_label(ax, "c")

    ax = axes[1, 1]
    top1 = fold[fold["metric"].eq("Top1")]
    for variant_index, variant in enumerate(variant_order):
        frame = top1[top1["variant"].eq(variant)]
        jitter = np.linspace(-0.06, 0.06, max(len(frame), 1))
        ax.scatter(
            variant_index + jitter[: len(frame)],
            frame["estimate"],
            s=20,
            color=variant_colors[variant],
            edgecolors=DARK,
            linewidths=0.3,
        )
        ax.hlines(
            frame["estimate"].mean(),
            variant_index - 0.14,
            variant_index + 0.14,
            color=DARK,
            lw=1.3,
        )
    ax.axhline(0.80, color=RED, ls="--", lw=0.8)
    ax.set_xticks(
        np.arange(len(variant_order)),
        [variant_labels[value] for value in variant_order],
        rotation=25,
        ha="right",
    )
    ax.set_ylim(0, 1.03)
    ax.set_ylabel("Top-1 localization")
    ax.set_title("Detection does not imply localization")
    _panel_label(ax, "d")

    fig.subplots_adjust(
        left=0.10,
        right=0.985,
        bottom=0.15,
        top=0.94,
        wspace=0.31,
        hspace=0.43,
    )
    path = figure_dir / "FigV2_D4_D5_mechanism_localization"
    _save(fig, path)
    _write_source_data(
        path,
        {
            "D4_mechanism": summary,
            "D4_lag": lag,
            "D5_outer_folds": fold,
            "D5_outer_summary": d5["D5_outer_refit_summary"],
        },
    )
    return [path]


def figure_composite(
    composite: dict[str, pd.DataFrame],
    figure_dir: Path,
) -> list[Path]:
    plant = composite["WWDQS_plant_summary"].copy()
    boot = composite["WWDQS_block_bootstrap"].copy()
    node = composite["WWDQS_node_scores"].copy()
    ablation = composite["WWDQS_dimension_ablation"].copy()
    fig, axes = plt.subplots(2, 2, figsize=(7.2, 5.25))

    ax = axes[0, 0]
    ax.plot(
        plant["date"],
        plant["node_score_full_median"],
        color=BLUE,
        lw=1.05,
        label="Full",
    )
    ax.plot(
        plant["date"],
        plant["node_score_basic_median"],
        color=ROSE,
        lw=0.95,
        label="Basic",
    )
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b\n%Y"))
    ax.set_ylim(1, 5)
    ax.set_ylabel("Daily median node score")
    ax.set_title("Coverage-stratified quality trajectories")
    ax.legend(loc="lower left")
    _panel_label(ax, "a")

    ax = axes[0, 1]
    months = sorted(boot["month"].unique())
    month_positions = {month: index for index, month in enumerate(months)}
    for coverage_class, color, marker in (
        ("full", BLUE, "o"),
        ("basic", ROSE, "s"),
    ):
        for method, offset, fill in (
            ("main_7d", -0.08, color),
            ("sensitivity_48h", 0.08, "white"),
        ):
            frame = boot[
                boot["coverage_class"].eq(coverage_class)
                & boot["method"].eq(method)
            ].copy()
            x = np.array([month_positions[value] for value in frame["month"]]) + offset
            ax.errorbar(
                x,
                frame["estimate"],
                yerr=np.vstack(
                    [
                        frame["estimate"] - frame["ci_low"],
                        frame["ci_high"] - frame["estimate"],
                    ]
                ),
                fmt=marker,
                mfc=fill,
                mec=color,
                color=color,
                ms=3.4,
                capsize=1.8,
                lw=0.8,
            )
    ax.set_xticks(
        np.arange(len(months)),
        [pd.Period(value, freq="M").strftime("%b\n%Y") for value in months],
    )
    ax.set_ylim(1, 5)
    ax.set_ylabel("Mean node score (95% CI)")
    ax.set_title("Block-bootstrap uncertainty by coverage")
    ax.legend(
        handles=[
            Line2D([], [], marker="o", ls="", color=BLUE, label="Full, 7 d"),
            Line2D([], [], marker="s", ls="", color=ROSE, label="Basic, 7 d"),
            Line2D(
                [],
                [],
                marker="o",
                ls="",
                color=GRAY,
                markerfacecolor="white",
                label="48 h sensitivity",
            ),
        ],
        loc="lower left",
    )
    _panel_label(ax, "b")

    ax = axes[1, 0]
    coverage = (
        node.assign(month=node["timestamp"].dt.to_period("M").astype(str))
        .groupby(["month", "coverage_class"], as_index=False)
        .size()
    )
    pivot = coverage.pivot(
        index="month",
        columns="coverage_class",
        values="size",
    ).fillna(0)
    pivot = pivot.div(pivot.sum(axis=1), axis=0)
    order = [
        column
        for column in ["full", "basic", "limited", "insufficient"]
        if column in pivot
    ]
    bottom = np.zeros(len(pivot))
    palette = {
        "full": BLUE,
        "basic": BLUE_SOFT,
        "limited": GOLD,
        "insufficient": LIGHT,
    }
    for column in order:
        ax.bar(
            np.arange(len(pivot)),
            pivot[column],
            bottom=bottom,
            color=palette[column],
            width=0.72,
            label=column.capitalize(),
        )
        bottom += pivot[column].to_numpy()
    ax.set_xticks(
        np.arange(len(pivot)),
        [pd.Period(value, freq="M").strftime("%b\n%Y") for value in pivot.index],
    )
    ax.set_ylim(0, 1)
    ax.set_ylabel("Sensor-hour fraction")
    ax.set_title("Coverage, not score, explains eligibility shifts")
    ax.legend(
        ncol=len(order),
        loc="upper center",
        bbox_to_anchor=(0.5, -0.22),
        frameon=False,
        handletextpad=0.45,
        columnspacing=0.8,
    )
    _panel_label(ax, "c")

    ax = axes[1, 1]
    shown = ablation[ablation["variant"].str.startswith("without_")].copy()
    y = np.arange(len(shown))
    colors = [BLUE, BLUE_MID, BLUE_SOFT][: len(shown)]
    ax.barh(y, shown["spearman_vs_full"], color=colors, height=0.56)
    ax.set_yticks(
        y,
        shown["variant"].str.replace("without_", "Without ", regex=False),
    )
    ax.set_xlim(0, 1.02)
    ax.set_xlabel("Spearman correlation with Full score")
    ax.set_title("Complete-case dimension ablation")
    _panel_label(ax, "d")

    fig.subplots_adjust(
        left=0.11,
        right=0.985,
        bottom=0.16,
        top=0.94,
        wspace=0.35,
        hspace=0.38,
    )
    path = figure_dir / "FigV2_WWDQS_full_basic"
    _save(fig, path)
    _write_source_data(
        path,
        {
            "plant_summary": plant,
            "block_bootstrap": boot,
            "coverage_counts": coverage,
            "dimension_ablation": ablation,
        },
    )
    return [path]


def write_figure_manifest(
    figure_dir: Path,
    figure_stems: list[Path],
    source_paths: list[Path],
    run_id: str,
) -> Path:
    payload = {
        "run_id": run_id,
        "backends": {
            "quantitative_figures": "python_matplotlib",
            "framework": "scientific_illustrator_powerpoint",
        },
        "figures": [],
    }
    run_source_hashes = {
        path.name: sha256_file(path) for path in source_paths if path.exists()
    }
    for stem in figure_stems:
        source_data = stem.parent / f"{stem.name}_source_data.xlsx"
        outputs = {}
        for suffix in [".svg", ".pdf", ".png", ".tiff", ".pptx"]:
            candidate = stem.with_suffix(suffix)
            if candidate.exists():
                outputs[suffix] = sha256_file(candidate)
        payload["figures"].append(
            {
                "stem": stem.name,
                "contract": (
                    "schematic_led_composite"
                    if "framework" in stem.name.lower()
                    else "quantitative_grid"
                ),
                "outputs": outputs,
                "source_data": (
                    {
                        "file": source_data.name,
                        "sha256": sha256_file(source_data),
                    }
                    if source_data.exists()
                    else None
                ),
                "run_source_sha256": run_source_hashes,
            }
        )
    path = figure_dir / "figure_manifest.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path
