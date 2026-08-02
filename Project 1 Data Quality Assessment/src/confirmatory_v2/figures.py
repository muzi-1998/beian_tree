from __future__ import annotations

import json
from pathlib import Path

import matplotlib as mpl
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.patches import Patch, Rectangle

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
BALANCE_CMAP = mpl.colors.LinearSegmentedColormap.from_list(
    "full_basic_balance",
    ["#B64342", "#F4F5F8", "#0F4D92"],
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


def _draw_detection_surface(
    ax: plt.Axes,
    frame: pd.DataFrame,
    *,
    value_column: str,
    amplitude_axis: bool,
) -> mpl.image.AxesImage:
    if amplitude_axis:
        matrix = frame.pivot(
            index="amplitude_bin",
            columns="duration_bin",
            values=value_column,
        ).sort_index()
        support = frame.pivot(
            index="amplitude_bin",
            columns="duration_bin",
            values="cell_support",
        ).reindex(index=matrix.index, columns=matrix.columns)
        lookup = frame.set_index(["amplitude_bin", "duration_bin"])
    else:
        matrix = (
            frame.set_index("duration_bin")[[value_column]]
            .T.sort_index(axis=1)
        )
        support = (
            frame.set_index("duration_bin")[["cell_support"]]
            .T.reindex(columns=matrix.columns)
        )
        lookup = frame.set_index("duration_bin")
    masked = np.ma.masked_where(
        support.to_numpy() != "sufficient",
        matrix.to_numpy(dtype=float),
    )
    cmap = DETECTION_CMAP.copy()
    cmap.set_bad(LIGHT)
    image = ax.imshow(
        masked,
        origin="lower",
        aspect="auto",
        vmin=0,
        vmax=1,
        cmap=cmap,
        interpolation="nearest",
    )
    for y_index, row_key in enumerate(matrix.index):
        for x_index, column_key in enumerate(matrix.columns):
            cell = (
                lookup.loc[(row_key, column_key)]
                if amplitude_axis
                else lookup.loc[column_key]
            )
            sufficient = str(cell["cell_support"]) == "sufficient"
            if not sufficient:
                ax.add_patch(
                    Rectangle(
                        (x_index - 0.5, y_index - 0.5),
                        1,
                        1,
                        facecolor="none",
                        edgecolor=GRAY,
                        hatch="////",
                        lw=0.0,
                    )
                )
                label = f"n={int(cell['n_independent_clusters'])}"
                text_color = DARK
            else:
                value = float(cell[value_column])
                label = (
                    f"{value:.2f}\n"
                    f"[{float(cell['ci95_low']):.2f},"
                    f"{float(cell['ci95_high']):.2f}]\n"
                    f"n={int(cell['n_independent_clusters'])}"
                )
                text_color = "white" if value >= 0.62 else DARK
                edge_color = TEAL if value >= 0.80 else RED
                ax.add_patch(
                    Rectangle(
                        (x_index - 0.46, y_index - 0.46),
                        0.92,
                        0.92,
                        fill=False,
                        edgecolor=edge_color,
                        lw=0.9,
                    )
                )
            ax.text(
                x_index,
                y_index,
                label,
                ha="center",
                va="center",
                color=text_color,
                fontsize=5.0,
                linespacing=0.95,
            )
    x_labels = []
    for duration_bin in matrix.columns:
        cell = frame[frame["duration_bin"].eq(duration_bin)].iloc[0]
        x_labels.append(f"{cell.duration_low:.1f}\n{cell.duration_high:.1f}")
    ax.set_xticks(np.arange(len(x_labels)), x_labels)
    if amplitude_axis:
        y_labels = []
        for amplitude_bin in matrix.index:
            cell = frame[frame["amplitude_bin"].eq(amplitude_bin)].iloc[0]
            y_labels.append(
                f"{cell.amplitude_low_sigma:.1f}-"
                f"{cell.amplitude_high_sigma:.1f}"
            )
        ax.set_yticks(np.arange(len(y_labels)), y_labels)
        ax.set_ylabel("Amplitude (local sigma)")
    else:
        ax.set_yticks([0], ["Not defined"])
        ax.set_ylabel("Injected amplitude")
    ax.set_xlabel(
        f"Duration ({str(frame['duration_unit'].iloc[0])})"
    )
    return image


def _figure_d1_fault_surface(
    outputs: dict[str, pd.DataFrame],
    figure_dir: Path,
    fault: str,
) -> Path:
    amplitude_axis = fault != "hard_freeze"
    source = (
        outputs["D1_detection_surface"]
        if amplitude_axis
        else outputs["D1_duration_response"]
    )
    shown = source[
        source["fault_type"].eq(fault)
        & source["route"].eq("all_routes")
    ].copy()
    if amplitude_axis:
        fig, axes = plt.subplots(2, 2, figsize=(7.2, 4.5), squeeze=False)
    else:
        fig, axes = plt.subplots(2, 2, figsize=(7.2, 3.85), squeeze=False)
    image = None
    panels = [
        ("DO", "original", "DO, native resolution"),
        ("DO", "degraded_2x", "DO, exploratory 2x"),
        ("ORP", "original", "ORP, native resolution"),
        ("ORP", "degraded_2x", "ORP, exploratory 2x"),
    ]
    for panel_index, (analyte, resolution, title) in enumerate(panels):
        row, column = divmod(panel_index, 2)
        ax = axes[row, column]
        frame = shown[
            shown["analyte"].eq(analyte)
            & shown["resolution_mode"].eq(resolution)
        ].copy()
        image = _draw_detection_surface(
            ax,
            frame,
            value_column=(
                "detection_probability"
                if amplitude_axis
                else "event_recall"
            ),
            amplitude_axis=amplitude_axis,
        )
        ax.set_title(title)
        _panel_label(ax, chr(ord("a") + panel_index))
    fig.legend(
        handles=[
            Patch(
                facecolor="none",
                edgecolor=TEAL,
                label="Recall >= 0.80",
            ),
            Patch(
                facecolor="none",
                edgecolor=RED,
                label="Recall < 0.80",
            ),
            Patch(
                facecolor=LIGHT,
                edgecolor=GRAY,
                hatch="////",
                label="Insufficient clusters",
            ),
        ],
        loc="lower center",
        ncol=3,
        frameon=False,
        bbox_to_anchor=(0.5, 0.0),
    )
    fig.subplots_adjust(
        left=0.10,
        right=0.88,
        bottom=0.19 if amplitude_axis else 0.21,
        top=0.94,
        wspace=0.32,
        hspace=0.47 if amplitude_axis else 0.58,
    )
    colorbar_axis = fig.add_axes(
        [0.91, 0.23 if amplitude_axis else 0.24, 0.014, 0.64]
    )
    colorbar = fig.colorbar(image, cax=colorbar_axis)
    colorbar.set_label("Cluster-bootstrap recall")
    colorbar.set_ticks([0, 0.25, 0.5, 0.75, 1.0])
    path = figure_dir / f"FigV2_D1_{fault}_detection_surface"
    _save(fig, path)
    _write_source_data(
        path,
        {
            "surface": shown,
            "exclusions": outputs["D1_excluded_injection_trials"][
                outputs["D1_excluded_injection_trials"]["fault_type"].eq(fault)
            ],
        },
    )
    return path


def _figure_d1_route_raw(
    outputs: dict[str, pd.DataFrame],
    figure_dir: Path,
) -> Path:
    concordance = outputs["D1_raw_route_concordance"].copy()
    pooled = outputs["D1_raw_endpoint_summary"].copy()
    fault_order = ["spike", "step", "linear_drift", "hard_freeze"]
    fault_labels = ["Spike", "Step", "Drift", "Freeze"]
    fault_markers = {
        "spike": "o",
        "step": "s",
        "linear_drift": "^",
        "hard_freeze": "D",
    }
    fig, axes = plt.subplots(1, 2, figsize=(7.2, 2.8))
    ax = axes[0]
    ax.plot([0, 1], [0, 1], color=GRAY, ls="--", lw=0.8)
    for fault in fault_order:
        frame = concordance[concordance["fault_type"].eq(fault)]
        for analyte, color in (("DO", BLUE), ("ORP", ROSE)):
            subset = frame[frame["analyte"].eq(analyte)]
            ax.scatter(
                subset["route_level_recall"],
                subset["raw_domain_recall"],
                s=18 + 36 * subset["detection_agreement"],
                marker=fault_markers[fault],
                facecolor=color,
                edgecolor="white",
                linewidth=0.45,
                alpha=0.85,
            )
    ax.set_xlim(-0.03, 1.03)
    ax.set_ylim(-0.03, 1.03)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel("Route-level recall")
    ax.set_ylabel("Raw-domain frozen-route recall")
    ax.set_title("Agreement across analyte and route")
    ax.legend(
        handles=[
            Line2D([], [], marker="o", ls="", color=BLUE, label="DO"),
            Line2D([], [], marker="o", ls="", color=ROSE, label="ORP"),
            *[
                Line2D(
                    [],
                    [],
                    marker=fault_markers[fault],
                    ls="",
                    color=DARK,
                    label=label,
                )
                for fault, label in zip(fault_order, fault_labels)
            ],
        ],
        ncol=2,
        loc="lower right",
    )
    _panel_label(ax, "a")

    ax = axes[1]
    ordered = pooled.set_index("fault_type").loc[fault_order].reset_index()
    y = np.arange(len(ordered))
    ax.plot(
        ordered["route_level_recall_same_scenarios"],
        y,
        "o",
        color=BLUE,
        ms=4,
        label="Route-level",
    )
    ax.errorbar(
        ordered["raw_domain_recall"],
        y,
        xerr=np.vstack(
            [
                ordered["raw_domain_recall"] - ordered["recall_ci_low"],
                ordered["recall_ci_high"] - ordered["raw_domain_recall"],
            ]
        ),
        fmt="s",
        color=ROSE,
        ecolor=ROSE,
        capsize=2,
        ms=3.8,
        lw=0.8,
        label="Raw-domain (95% CI)",
    )
    for row in ordered.itertuples(index=False):
        position = fault_order.index(row.fault_type)
        ax.text(
            0.02,
            position + 0.24,
            f"agreement={row.detection_agreement:.2f}",
            fontsize=5.8,
            color=DARK,
        )
    ax.set_yticks(y, fault_labels)
    ax.set_xlim(0, 1.03)
    ax.axvline(0.80, color=GRAY, ls=":", lw=0.8)
    ax.set_xlabel("Recall on matched scenarios")
    ax.set_title("Pooled endpoint concordance")
    ax.legend(loc="lower right")
    _panel_label(ax, "b")
    fig.subplots_adjust(
        left=0.10,
        right=0.985,
        bottom=0.18,
        top=0.90,
        wspace=0.34,
    )
    path = figure_dir / "FigV2_D1_route_raw_agreement"
    _save(fig, path)
    _write_source_data(
        path,
        {
            "route_raw_by_stratum": concordance,
            "pooled_endpoint": pooled,
        },
    )
    return path


def figure_d1(outputs: dict[str, pd.DataFrame], figure_dir: Path) -> list[Path]:
    paths = [
        _figure_d1_fault_surface(outputs, figure_dir, "spike"),
        _figure_d1_fault_surface(outputs, figure_dir, "step"),
        _figure_d1_fault_surface(outputs, figure_dir, "linear_drift"),
        _figure_d1_fault_surface(outputs, figure_dir, "hard_freeze"),
        _figure_d1_route_raw(outputs, figure_dir),
    ]
    return paths


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
    casebook = outputs["D2_process_floor_casebook"].copy()
    scenario_order = [
        "true_low_oxygen_floor",
        "digital_lock",
        "response_recovery_after_floor",
        "missing_and_long_gap_not_exempt",
    ]
    scenario_titles = {
        "true_low_oxygen_floor": "True low-oxygen floor",
        "digital_lock": "Exact digital lock",
        "response_recovery_after_floor": "Response after leaving floor",
        "missing_and_long_gap_not_exempt": "Missing and long-gap evidence",
    }
    fig, axes = plt.subplots(2, 2, figsize=(7.2, 4.4), sharey=False)
    for panel_index, scenario in enumerate(scenario_order):
        ax = axes.ravel()[panel_index]
        frame = casebook[casebook["scenario"].eq(scenario)].copy()
        frame["elapsed_min"] = np.arange(len(frame))
        ax.plot(
            frame["elapsed_min"],
            frame["value"],
            color=BLUE,
            lw=1.05,
            label="Observed DO",
        )
        ax.axhline(
            0.20,
            color=GOLD,
            ls="--",
            lw=0.8,
            label="Process-floor threshold",
        )
        unavailable = frame["qfa_unavailable"].astype(bool).to_numpy()
        ax.fill_between(
            frame["elapsed_min"],
            0,
            1,
            where=unavailable,
            transform=ax.get_xaxis_transform(),
            color=RED,
            alpha=0.10,
            step="mid",
            label="QFA unavailable",
        )
        frozen = frame["sensor_freeze"].astype(bool)
        if frozen.any():
            ax.scatter(
                frame.loc[frozen, "elapsed_min"],
                frame.loc[frozen, "value"],
                marker="x",
                color=RED,
                s=14,
                lw=0.8,
                label="Hard digital freeze",
                zorder=4,
            )
        ax.set_xlabel("Elapsed time (min)")
        ax.set_ylabel("DO (mg L$^{-1}$)")
        ax.set_title(scenario_titles[scenario])
        _panel_label(ax, chr(ord("a") + panel_index))
    handles, labels = axes.ravel()[1].get_legend_handles_labels()
    by_label = dict(zip(labels, handles))
    fig.legend(
        by_label.values(),
        by_label.keys(),
        loc="lower center",
        ncol=4,
        bbox_to_anchor=(0.5, 0.0),
    )
    fig.subplots_adjust(
        left=0.10,
        right=0.985,
        bottom=0.17,
        top=0.92,
        wspace=0.28,
        hspace=0.48,
    )
    contract_path = figure_dir / "FigV2_D2_process_floor_contract"
    _save(fig, contract_path)
    _write_source_data(
        contract_path,
        {
            "contract_checks": outputs["D2_process_floor_contract_checks"],
            "casebook": casebook,
            "observed_channels": outputs[
                "D2_process_floor_observed_channels"
            ],
            "semantic_contract": outputs[
                "D2_process_floor_semantic_contract"
            ],
        },
    )
    return [path, contract_path]


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
            "D4_common_change_contract": d4[
                "D4_common_change_contract"
            ],
            "D4_lag": lag,
            "D5_outer_folds": fold,
            "D5_outer_summary": d5["D5_outer_refit_summary"],
            "D5_paired_fold_deltas": d5[
                "D5_outer_refit_paired_deltas"
            ],
            "D5_paired_delta_summary": d5[
                "D5_outer_refit_paired_delta_summary"
            ],
        },
    )
    return [path]


def figure_d5_coverage_selection(
    coverage: dict[str, pd.DataFrame],
    figure_dir: Path,
) -> list[Path]:
    strata = coverage["D5_coverage_strata"].copy()
    balance = coverage["D5_full_basic_balance"].copy()
    paired = coverage["D5_monthly_paired_balance"].copy()

    monthly = strata[strata["stratum"].eq("month")].pivot(
        index="stratum_value",
        columns="coverage_class",
        values="within_stratum_fraction",
    ).fillna(0)
    monthly = monthly.sort_index()
    fig, ax = plt.subplots(1, 1, figsize=(7.2, 2.65))
    coverage_styles = {
        "full": (BLUE, "o", "Full"),
        "basic": (ROSE, "s", "Basic"),
        "limited": (GOLD, "^", "Limited"),
        "insufficient": (GRAY, "D", "Insufficient"),
    }
    x = pd.to_datetime(monthly.index)
    for coverage_class, (color, marker, label) in coverage_styles.items():
        values = (
            monthly[coverage_class]
            if coverage_class in monthly.columns
            else np.zeros(len(monthly))
        )
        ax.plot(
            x,
            values,
            color=color,
            marker=marker,
            ms=3.4,
            lw=1.15,
            label=label,
        )
    ax.set_ylim(0, 1.03)
    ax.set_ylabel("Sensor-hour fraction")
    ax.set_xlabel("Calendar month")
    fig.suptitle(
        "Complete evidence coverage is temporally selected",
        y=0.98,
    )
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=1))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b\n%Y"))
    ax.legend(
        loc="lower center",
        ncol=4,
        bbox_to_anchor=(0.5, 1.01),
    )
    fig.subplots_adjust(left=0.09, right=0.985, bottom=0.25, top=0.80)
    monthly_path = figure_dir / "FigV2_D5_full_basic_monthly_coverage"
    _save(fig, monthly_path)
    _write_source_data(
        monthly_path,
        {"monthly_coverage": strata[strata["stratum"].eq("month")]},
    )

    fig, axes = plt.subplots(
        1,
        3,
        figsize=(7.2, 3.05),
        gridspec_kw={"width_ratios": [0.95, 1.35, 1.05]},
    )
    overall = balance[balance["group_type"].eq("overall")].copy()
    metric_order = [
        "D1_total",
        "D2_total",
        "missing_rate",
        "process_floor_occupancy",
        "D3_warn",
        "raw_value_sensor_z",
    ]
    metric_labels = {
        "D1_total": "D1 score",
        "D2_total": "D2 score",
        "missing_rate": "Missing rate",
        "process_floor_occupancy": "Process floor",
        "D3_warn": "D3 Warn",
        "raw_value_sensor_z": "Raw value z",
    }
    overall = overall.set_index("metric").reindex(metric_order).dropna(
        subset=["standardized_mean_difference"]
    )
    y = np.arange(len(overall))
    colors = np.where(
        overall["standardized_mean_difference"].ge(0),
        BLUE,
        ROSE,
    )
    axes[0].barh(
        y,
        overall["standardized_mean_difference"],
        color=colors,
        height=0.58,
    )
    axes[0].axvline(0, color=DARK, lw=0.8)
    axes[0].axvline(0.10, color=GRAY, ls="--", lw=0.7)
    axes[0].axvline(-0.10, color=GRAY, ls="--", lw=0.7)
    axes[0].set_yticks(
        y,
        [metric_labels[value] for value in overall.index],
    )
    axes[0].invert_yaxis()
    axes[0].set_xlabel("SMD (Full - Basic)")
    axes[0].set_title("Overall balance")
    _panel_label(axes[0], "a")

    month_balance = balance[
        balance["group_type"].eq("month")
        & balance["metric"].isin(metric_order)
    ].pivot(
        index="metric",
        columns="group_value",
        values="standardized_mean_difference",
    ).reindex(
        index=metric_order,
        columns=monthly.index,
    )
    month_balance = month_balance.dropna(how="all")
    limit = max(
        0.2,
        float(np.nanquantile(np.abs(month_balance.to_numpy()), 0.95)),
    )
    balance_cmap = BALANCE_CMAP.copy()
    balance_cmap.set_bad(LIGHT)
    balance_values = month_balance.to_numpy(float)
    image = axes[1].imshow(
        np.ma.masked_invalid(balance_values),
        aspect="auto",
        cmap=balance_cmap,
        vmin=-limit,
        vmax=limit,
        interpolation="nearest",
    )
    axes[1].set_yticks(
        np.arange(len(month_balance)),
        [metric_labels[value] for value in month_balance.index],
    )
    axes[1].set_xticks(
        np.arange(len(month_balance.columns)),
        [
            pd.Timestamp(value).strftime("%Y-%m")
            for value in month_balance.columns
        ],
        rotation=55,
        ha="right",
        fontsize=5.5,
    )
    axes[1].set_xlabel("Calendar month")
    axes[1].set_title("Conditional balance")
    for row_index, column_index in zip(
        *np.where(~np.isfinite(balance_values))
    ):
        axes[1].add_patch(
            Rectangle(
                (column_index - 0.5, row_index - 0.5),
                1,
                1,
                facecolor="none",
                edgecolor=GRAY,
                hatch="////",
                lw=0.0,
            )
        )
    colorbar = fig.colorbar(
        image,
        ax=axes[1],
        fraction=0.047,
        pad=0.03,
    )
    colorbar.set_label("SMD")
    _panel_label(axes[1], "b")

    selected = strata[
        strata["coverage_class"].eq("full")
        & strata["stratum"].isin(
            ["active_regime_id", "ood_status", "support_level"]
        )
    ].copy()
    selected["label"] = (
        selected["stratum"]
        .map(
            {
                "active_regime_id": "Regime ",
                "ood_status": "",
                "support_level": "Support ",
            }
        )
        + selected["stratum_value"]
    )
    order = (
        [f"Regime {value}" for value in ["0", "1", "2", "3"]]
        + ["not_OOD", "OOD"]
        + [f"Support {value}" for value in ["L1", "L2", "L3"]]
    )
    full_fraction = selected.set_index("label")[
        "within_stratum_fraction"
    ].to_dict()
    selected = pd.DataFrame(
        {
            "label": order,
            "within_stratum_fraction": [
                float(full_fraction.get(label, 0.0))
                for label in order
            ],
            "stratum": (
                ["active_regime_id"] * 4
                + ["ood_status"] * 2
                + ["support_level"] * 3
            ),
        }
    )
    selected["display_label"] = selected["label"].replace(
        {"not_OOD": "Not OOD"}
    )
    y = np.arange(len(selected))
    colors = selected["stratum"].map(
        {
            "active_regime_id": BLUE_2,
            "ood_status": ROSE,
            "support_level": TEAL,
        }
    )
    axes[2].barh(
        y,
        selected["within_stratum_fraction"],
        color=colors,
        height=0.58,
    )
    axes[2].set_yticks(y, selected["display_label"].astype(str))
    axes[2].invert_yaxis()
    axes[2].set_xlim(0, 1)
    axes[2].set_xlabel("Full fraction within stratum")
    axes[2].set_title("Coverage mechanism")
    for row_index, value in enumerate(
        selected["within_stratum_fraction"]
    ):
        if np.isclose(value, 0.0):
            axes[2].text(
                0.02,
                row_index,
                "0",
                va="center",
                ha="left",
                fontsize=5.8,
                color=DARK,
            )
    _panel_label(axes[2], "c")

    fig.subplots_adjust(
        left=0.09,
        right=0.985,
        bottom=0.28,
        top=0.88,
        wspace=0.58,
    )
    balance_path = figure_dir / "FigV2_D5_full_basic_conditional_balance"
    _save(fig, balance_path)
    _write_source_data(
        balance_path,
        {
            "conditional_balance": balance,
            "coverage_strata": strata,
            "monthly_paired_CI": paired,
        },
    )
    return [monthly_path, balance_path]


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
