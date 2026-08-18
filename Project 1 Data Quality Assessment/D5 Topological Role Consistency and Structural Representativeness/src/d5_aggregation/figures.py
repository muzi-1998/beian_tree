from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import fitz
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.patches import FancyBboxPatch
from PIL import Image

from d5_local.figures.figure_style import (
    PALETTE,
    PROFILE,
    configure_style,
    panel_label,
    save_figure,
    style_axes,
)

from .common import PROJECT_ROOT, write_json
from .reports import write_workbook


STEMS = [
    "DQR_Fig01_hierarchical_contract",
    "DQR_Fig02_evidence_availability",
    "DQR_Fig03_construct_complementarity",
    "DQR_Fig04_aggregation_robustness",
    "DQR_Fig05_representative_cases",
]

FIGURE_WIDTH_MM = 183.0
RASTER_DPI = 600
SUBMISSION_RASTER_EXTENSION = ".tiff"
plt.rcParams.update({"svg.fonttype": "none", "pdf.fonttype": 42})


def _display_sensor(value: str) -> str:
    return str(value).replace("_", "-")


def _new_figure(height_mm: float, *, columns: int = 1, rows: int = 1):
    fig, axes = plt.subplots(
        rows,
        columns,
        figsize=(FIGURE_WIDTH_MM / 25.4, height_mm / 25.4),
        constrained_layout=True,
        squeeze=False,
    )
    fig.set_constrained_layout_pads(w_pad=0.035, h_pad=0.035, wspace=0.045, hspace=0.055)
    return fig, axes


def _box(ax, xy, width, height, text, color, *, fontsize=6.6, bold=False):
    patch = FancyBboxPatch(
        xy,
        width,
        height,
        boxstyle="round,pad=0.008,rounding_size=0.012",
        linewidth=0.8,
        edgecolor=color,
        facecolor="white",
        transform=ax.transAxes,
    )
    ax.add_patch(patch)
    ax.text(
        xy[0] + width / 2,
        xy[1] + height / 2,
        text,
        transform=ax.transAxes,
        ha="center",
        va="center",
        fontsize=fontsize,
        fontweight="bold" if bold else "normal",
        color=PALETTE["dark"],
    )


def _arrow(ax, start, end, color=PALETTE["gray"]):
    ax.annotate(
        "",
        xy=end,
        xytext=start,
        xycoords=ax.transAxes,
        textcoords=ax.transAxes,
        arrowprops={"arrowstyle": "-|>", "lw": 0.8, "color": color},
    )


def _figure_1(
    figure_root: Path,
    source_root: Path,
    node: pd.DataFrame,
    pair: pd.DataFrame,
) -> list[Path]:
    fig, axes = _new_figure(104, columns=2)
    ax = axes[0, 0]
    ax.set_axis_off()
    panel_label(ax, "a")
    ax.set_title("Hierarchical evidence contract", loc="left")
    colors = [PALETTE["blue"], PALETTE["teal"], PALETTE["gold"]]
    for x, label, color in zip((0.02, 0.20, 0.38), ("D1\nhealth", "D2\ncontinuity", "D5\nstructure"), colors):
        _box(ax, (x, 0.71), 0.14, 0.13, label, color, bold=True)
        _arrow(ax, (x + 0.07, 0.70), (0.28, 0.57), color)
    _box(ax, (0.18, 0.43), 0.25, 0.14, "Node quality\nQnode + Enode", PALETTE["navy"], bold=True)
    _box(ax, (0.57, 0.71), 0.14, 0.13, "D4\npair relation", PALETTE["red"], bold=True)
    _arrow(ax, (0.64, 0.70), (0.64, 0.57), PALETTE["red"])
    _box(ax, (0.52, 0.43), 0.25, 0.14, "Pair quality\nQpair + Epair", PALETTE["navy"], bold=True)
    _arrow(ax, (0.43, 0.50), (0.52, 0.50))
    _box(ax, (0.80, 0.43), 0.17, 0.14, "D3 safety\ngate", PALETTE["orange"], bold=True)
    _box(ax, (0.33, 0.15), 0.38, 0.14, "Release status\nquality + evidence + gate", PALETTE["dark"], bold=True)
    _arrow(ax, (0.30, 0.43), (0.43, 0.29))
    _arrow(ax, (0.64, 0.43), (0.59, 0.29))
    _arrow(ax, (0.88, 0.43), (0.69, 0.25), PALETTE["orange"])
    ax.text(
        0.02,
        0.02,
        "D4 remains pair-level; D3 is never averaged; missing D5 is not a low score.",
        transform=ax.transAxes,
        fontsize=6.1,
        color=PALETTE["gray"],
    )

    ax = axes[0, 1]
    panel_label(ax, "b")
    ax.set_title("Quality and evidence are separate quantities", loc="left")
    valid = node["Q_node_available"].notna()
    hb = ax.hexbin(
        node.loc[valid, "E_node"],
        node.loc[valid, "Q_node_available"],
        gridsize=(10, 34),
        mincnt=1,
        cmap="Blues",
        linewidths=0,
        bins="log",
    )
    ax.axhline(3.0, color=PALETTE["red"], lw=0.8, ls="--")
    ax.axvline(1.0, color=PALETTE["navy"], lw=0.8, ls=":")
    ax.text(0.68, 3.08, "low-tail threshold", color=PALETTE["red"], fontsize=6.0)
    ax.set_xlim(0.30, 1.04)
    ax.set_ylim(1.0, 5.05)
    ax.set_xticks([1 / 3, 2 / 3, 1.0], ["1/3", "2/3", "1"])
    ax.set_xlabel("Evidence completeness, $E_{node}$")
    ax.set_ylabel("Availability-aware quality, $Q_{node}$")
    style_axes(ax)
    cbar = fig.colorbar(hb, ax=ax, pad=0.02, fraction=0.05)
    cbar.set_label("Sensor-hours (log scale)")
    cbar.outline.set_linewidth(0.6)
    source = node.loc[
        valid,
        ["timestamp", "sensor_id", "analyte", "Q_node_available", "Q_node_full", "E_node", "coverage_class", "D3_gate_status"],
    ]
    write_workbook(
        source_root / "DQR_Fig01_source_data.xlsx",
        {
            "quality_evidence_plane": source,
            "contract": pd.DataFrame(
                {
                    "element": ["node", "pair", "gate", "release"],
                    "definition": [
                        "D1+D2+eligible D5",
                        "left node+right node+native D4",
                        "D3 Pass/Warn/Fail/NotEvaluated",
                        "quality and evidence reported separately",
                    ],
                }
            ),
        },
    )
    return save_figure(fig, figure_root, STEMS[0])


def _figure_2(
    figure_root: Path,
    source_root: Path,
    node: pd.DataFrame,
    monthly: pd.DataFrame,
) -> list[Path]:
    fig, axes = _new_figure(154, columns=2, rows=2)
    all_nodes = monthly.loc[
        (monthly["object_type"] == "node")
        & (monthly["aggregation_level"] == "all_nodes")
    ].sort_values("month")
    labels = pd.to_datetime(all_nodes["month"]).dt.strftime("%b\n%Y")
    x = np.arange(len(all_nodes))
    ax = axes[0, 0]
    panel_label(ax, "a")
    ax.set_title("Node evidence coverage", loc="left")
    bottom = np.zeros(len(all_nodes))
    for column, label, color in (
        ("full_rate", "Full", PALETTE["blue"]),
        ("basic_rate", "Basic", PALETTE["gold"]),
        ("limited_rate", "Limited", PALETTE["red"]),
        ("insufficient_rate", "Insufficient", PALETTE["light_gray"]),
    ):
        values = all_nodes[column].to_numpy(float)
        ax.bar(x, values, bottom=bottom, width=0.72, color=color, label=label)
        bottom += values
    ax.set_xticks(x, labels)
    ax.set_ylim(0, 1.02)
    ax.set_ylabel("Fraction of sensor-hours")
    ax.legend(ncol=2, loc="lower left", bbox_to_anchor=(0.0, 1.01))
    style_axes(ax)

    ax = axes[0, 1]
    panel_label(ax, "b")
    ax.set_title("D5 report availability and OOD burden", loc="left")
    ax.plot(x, all_nodes["D5_report_rate"], marker="o", ms=3, color=PALETTE["blue"], label="D5 report eligible")
    ax.plot(x, all_nodes["D5_ood_rate"], marker="s", ms=3, color=PALETTE["red"], label="D5 out of template")
    ax.set_xticks(x, labels)
    ax.set_ylim(0, 1.02)
    ax.set_ylabel("Fraction of sensor-hours")
    ax.legend(loc="upper right")
    style_axes(ax)

    source = node.copy()
    source["month"] = source["timestamp"].dt.to_period("M").astype(str)
    quality = source.groupby("month", observed=True).agg(
        Q_full_median=("Q_node_full", "median"),
        Q_available_median=("Q_node_available", "median"),
        E_node_median=("E_node", "median"),
        E_node_p25=("E_node", lambda s: s.quantile(0.25)),
        E_node_p75=("E_node", lambda s: s.quantile(0.75)),
        n_sensor_hours=("timestamp", "size"),
    ).reset_index()
    xq = np.arange(len(quality))
    qlabels = pd.to_datetime(quality["month"]).dt.strftime("%b\n%Y")
    ax = axes[1, 0]
    panel_label(ax, "c")
    ax.set_title("Distinct temporal estimands", loc="left")
    ax.plot(xq, quality["Q_full_median"], marker="o", ms=3, color=PALETTE["blue"], label="Full")
    ax.plot(xq, quality["Q_available_median"], marker="s", ms=3, color=PALETTE["orange"], label="Availability-aware")
    ax.set_xticks(xq, qlabels)
    ax.set_ylim(3.5, 5.02)
    ax.set_ylabel("Monthly median node quality")
    ax.legend(loc="lower left")
    style_axes(ax)

    ax = axes[1, 1]
    panel_label(ax, "d")
    ax.set_title("Evidence completeness", loc="left")
    ax.fill_between(xq, quality["E_node_p25"], quality["E_node_p75"], color=PALETTE["blue"], alpha=0.18, linewidth=0)
    ax.plot(xq, quality["E_node_median"], marker="o", ms=3, color=PALETTE["navy"])
    ax.set_xticks(xq, qlabels)
    ax.set_ylim(0.3, 1.03)
    ax.set_ylabel("$E_{node}$ (median and IQR)")
    style_axes(ax)
    write_workbook(
        source_root / "DQR_Fig02_source_data.xlsx",
        {"monthly_coverage": all_nodes, "monthly_quality_evidence": quality},
    )
    return save_figure(fig, figure_root, STEMS[1])


def _matrix(construct: pd.DataFrame, value: str) -> pd.DataFrame:
    dimensions = ["D1", "D2", "D4", "D5_report"]
    matrix = pd.DataFrame(np.eye(4), index=dimensions, columns=dimensions)
    source = construct.loc[construct["scope"] == "pairwise_complete_formal_scores"]
    for _, row in source.iterrows():
        matrix.loc[row["left"], row["right"]] = row[value]
        matrix.loc[row["right"], row["left"]] = row[value]
    return matrix


def _draw_matrix(ax, matrix: pd.DataFrame, *, title: str, vmin: float, vmax: float, cmap: str):
    image = ax.imshow(matrix.to_numpy(float), vmin=vmin, vmax=vmax, cmap=cmap, aspect="auto")
    labels = [value.replace("_report", " report") for value in matrix.index]
    ax.set_xticks(range(len(labels)), labels, rotation=30, ha="right")
    ax.set_yticks(range(len(labels)), labels)
    for row in range(len(labels)):
        for column in range(len(labels)):
            value = matrix.iloc[row, column]
            color = "white" if value > (vmin + vmax) / 2 else PALETTE["dark"]
            ax.text(column, row, f"{value:.2f}", ha="center", va="center", fontsize=6.1, color=color)
    ax.set_title(title, loc="left")
    ax.tick_params(which="both", length=0)
    for spine in ax.spines.values():
        spine.set_visible(False)
    return image


def _figure_3(
    config: dict[str, Any],
    figure_root: Path,
    source_root: Path,
    construct: pd.DataFrame,
) -> list[Path]:
    fig, axes = _new_figure(158, columns=2, rows=2)
    rho = _matrix(construct, "spearman")
    jaccard = _matrix(construct, "low_tail_jaccard")
    ax = axes[0, 0]
    panel_label(ax, "a")
    image = _draw_matrix(ax, rho, title="Pairwise score association", vmin=-0.2, vmax=1, cmap="RdBu_r")
    cbar = fig.colorbar(image, ax=ax, pad=0.02, fraction=0.05)
    cbar.set_label("Spearman $\\rho$")
    cbar.outline.set_linewidth(0.6)
    ax = axes[0, 1]
    panel_label(ax, "b")
    image = _draw_matrix(ax, jaccard, title="Low-tail event overlap", vmin=0, vmax=1, cmap="Blues")
    cbar = fig.colorbar(image, ax=ax, pad=0.02, fraction=0.05)
    cbar.set_label("Jaccard")
    cbar.outline.set_linewidth(0.6)

    dual = construct.loc[construct["scope"] == "D4_D5_dual_scope"].copy()
    ax = axes[1, 0]
    panel_label(ax, "c")
    ax.set_title("D4-D5 dual-scope association and overlap", loc="left")
    y = np.arange(len(dual))
    for offset, metric, low, high, label, color in (
        (-0.10, "spearman", "spearman_ci_low", "spearman_ci_high", "Spearman $\\rho$", PALETTE["navy"]),
        (0.10, "low_tail_jaccard", "jaccard_ci_low", "jaccard_ci_high", "Low-tail Jaccard", PALETTE["orange"]),
    ):
        error = np.vstack([dual[metric] - dual[low], dual[high] - dual[metric]])
        ax.errorbar(
            dual[metric],
            y + offset,
            xerr=error,
            fmt="o",
            color=color,
            capsize=2,
            label=label,
        )
    ax.axvline(0, color=PALETTE["gray"], lw=0.7)
    ax.set_yticks(y, ["Formal D5 report", "D5 raw calculable"])
    ax.set_xlim(-0.15, 0.5)
    ax.set_xlabel("Association or overlap (7 d block 95% CI)")
    ax.legend(loc="lower right")
    style_axes(ax)

    strat_path = PROJECT_ROOT / config["inputs"]["D5"]["stratified_dependence_path"]
    stratified = pd.read_parquet(strat_path)
    selected = stratified.loc[
        stratified["stratum_type"].isin(["analyte", "pair"])
        & stratified["descriptive_estimable"]
    ].copy()
    selected["label"] = selected["stratum_type"] + ": " + selected["stratum_value"].astype(str).map(_display_sensor)
    selected = selected.sort_values(["stratum_type", "stratum_value", "overlap_scope"])
    label_order = list(dict.fromkeys(selected["label"]))
    positions = {label: index for index, label in enumerate(label_order)}
    ax = axes[1, 1]
    panel_label(ax, "d")
    ax.set_title("D4-D5 association across analytes and pairs", loc="left")
    for offset, (scope, frame) in zip((-0.12, 0.12), selected.groupby("overlap_scope", sort=True)):
        ys = np.array([positions[value] for value in frame["label"]], dtype=float) + offset
        inferential = frame["inferential_estimable"].astype(bool)
        ax.scatter(frame["spearman_rho"], ys, s=16, label=scope.replace("_", " "), zorder=3)
        valid_ci = inferential & frame["ci95_low"].notna() & frame["ci95_high"].notna()
        if valid_ci.any():
            subset = frame.loc[valid_ci]
            y_ci = np.array([positions[value] for value in subset["label"]], dtype=float) + offset
            ax.hlines(y_ci, subset["ci95_low"], subset["ci95_high"], lw=0.8)
    ax.axvline(0, color=PALETTE["gray"], lw=0.7)
    ax.set_yticks(range(len(label_order)), label_order)
    ax.invert_yaxis()
    ax.set_xlim(-0.45, 0.65)
    ax.set_xlabel("Spearman $\\rho$")
    ax.legend(loc="lower right")
    style_axes(ax)
    write_workbook(
        source_root / "DQR_Fig03_source_data.xlsx",
        {
            "spearman_matrix": rho.reset_index(names="dimension"),
            "low_tail_jaccard": jaccard.reset_index(names="dimension"),
            "D4_D5_dual_scope": dual,
            "D4_D5_stratified": selected,
        },
    )
    return save_figure(fig, figure_root, STEMS[2])


def _figure_4(
    figure_root: Path,
    source_root: Path,
    aggregators: pd.DataFrame,
    weight_draws: pd.DataFrame,
    ablation: pd.DataFrame,
) -> list[Path]:
    fig, axes = _new_figure(151, columns=2, rows=2)
    order = ["arithmetic_equal_weight", "geometric_equal_weight", "soft_min_tau_0.5", "hard_min"]
    display = ["Arithmetic", "Geometric", "Soft minimum", "Hard minimum"]
    colors = {"node": PALETTE["blue"], "pair": PALETTE["orange"]}
    ax = axes[0, 0]
    panel_label(ax, "a")
    ax.set_title("Rank agreement with the primary estimator", loc="left")
    for offset, (scope, frame) in zip((-0.11, 0.11), aggregators.groupby("scope", sort=True)):
        frame = frame.set_index("aggregator").reindex(order)
        ax.scatter(frame["spearman_vs_arithmetic"], np.arange(4) + offset, s=20, color=colors[scope], label=scope.capitalize())
    ax.set_yticks(np.arange(4), display)
    ax.invert_yaxis()
    ax.set_xlim(0.75, 1.01)
    ax.set_xlabel("Spearman $\\rho$")
    ax.legend(loc="lower left")
    style_axes(ax)

    ax = axes[0, 1]
    panel_label(ax, "b")
    ax.set_title("Estimator-dependent low-tail burden", loc="left")
    width = 0.36
    for offset, (scope, frame) in zip((-width / 2, width / 2), aggregators.groupby("scope", sort=True)):
        frame = frame.set_index("aggregator").reindex(order)
        ax.bar(np.arange(4) + offset, 100 * frame["low_tail_rate"], width=width, color=colors[scope], label=scope.capitalize())
    ax.set_xticks(np.arange(4), display, rotation=25, ha="right")
    ax.set_ylabel("Low-tail hours (%)")
    ax.legend(loc="upper left")
    style_axes(ax)

    ax = axes[1, 0]
    panel_label(ax, "c")
    ax.set_title("Constrained weight sensitivity", loc="left")
    for scope, frame in weight_draws.groupby("scope", sort=True):
        ax.scatter(
            frame["spearman_vs_equal"],
            100 * frame["decision_flip_rate_at_3"],
            s=7,
            alpha=0.30,
            color=colors[scope],
            label=scope.capitalize(),
            rasterized=True,
        )
    ax.set_xlabel("Spearman $\\rho$ vs equal weights")
    ax.set_ylabel("Decision flips at Q < 3 (%)")
    ax.legend(loc="upper left")
    style_axes(ax)

    ax = axes[1, 1]
    panel_label(ax, "d")
    ax.set_title("Leave-one-component-out sensitivity", loc="left")
    for scope, frame in ablation.groupby("scope", sort=True):
        ax.scatter(
            frame["spearman_vs_full"],
            100 * frame["decision_flip_rate_at_3"],
            s=24,
            color=colors[scope],
            label=scope.capitalize(),
        )
        offsets = {
            "D1": (4, 4),
            "D2": (-18, 5),
            "D5": (4, 4),
            "D4": (4, 5),
            "left_node": (-30, -11),
            "right_node": (4, 5),
        }
        labels = {"left_node": "Left node", "right_node": "Right node"}
        for _, row in frame.iterrows():
            dx, dy = offsets.get(str(row["removed_component"]), (3, 3))
            ax.annotate(
                labels.get(str(row["removed_component"]), str(row["removed_component"])),
                (row["spearman_vs_full"], 100 * row["decision_flip_rate_at_3"]),
                xytext=(dx, dy),
                textcoords="offset points",
                fontsize=5.8,
            )
    ax.set_xlabel("Spearman $\\rho$ vs full estimator")
    ax.set_ylabel("Decision flips at Q < 3 (%)")
    ax.legend(loc="upper left")
    style_axes(ax)
    write_workbook(
        source_root / "DQR_Fig04_source_data.xlsx",
        {"aggregator_comparison": aggregators, "weight_draws": weight_draws, "dimension_ablation": ablation},
    )
    return save_figure(fig, figure_root, STEMS[3])


def _case_definitions(config: dict[str, Any], node: pd.DataFrame, pair: pd.DataFrame) -> list[dict[str, Any]]:
    case_path = PROJECT_ROOT / config["inputs"]["D5"]["case_path"]
    index = pd.read_excel(case_path, sheet_name="case_index")
    index["center_timestamp"] = pd.to_datetime(index["center_timestamp"])
    cases: list[dict[str, Any]] = []
    normal = node.loc[
        node["coverage_class"].eq("full")
        & node["D3_gate_status"].eq("Pass")
        & node["sensor_id"].eq("DO_1_2")
    ].sort_values("Q_node_full", ascending=False).iloc[0]
    cases.append(
        {
            "case_id": "stable_complete_evidence",
            "sensor_id": normal["sensor_id"],
            "center_timestamp": normal["timestamp"],
            "case_type": "Stable complete evidence",
            "truth_status": "algorithmic_reference_not_field_truth",
        }
    )
    for _, row in index.head(2).iterrows():
        cases.append(row.to_dict())
    low_pair = pair.loc[pair["Q_pair_available"].notna()].sort_values("Q_pair_available").iloc[0]
    cases.append(
        {
            "case_id": "lowest_pair_available",
            "sensor_id": low_pair["sensor_id"],
            "center_timestamp": low_pair["timestamp"],
            "case_type": "Pair-level low tail",
            "truth_status": "algorithmic_case_not_field_truth",
        }
    )
    return cases[:4]


def _shade_gate(ax, frame: pd.DataFrame) -> None:
    for status, color, hatch in (
        ("Warn", PALETTE["gold"], None),
        ("NotEvaluated", PALETTE["light_gray"], "///"),
        ("Fail", PALETTE["red"], None),
    ):
        selected = frame.loc[frame["D3_gate_status"].eq(status), "timestamp"]
        for stamp in selected:
            ax.axvspan(
                stamp,
                stamp + pd.Timedelta(hours=1),
                color=color,
                alpha=0.16 if status != "Fail" else 0.22,
                hatch=hatch,
                linewidth=0,
                zorder=0,
            )


def _figure_5(
    config: dict[str, Any],
    figure_root: Path,
    source_root: Path,
    node: pd.DataFrame,
    pair: pd.DataFrame,
) -> list[Path]:
    fig, axes = _new_figure(162, columns=2, rows=2)
    cases = _case_definitions(config, node, pair)
    source_sheets: dict[str, pd.DataFrame] = {"case_index": pd.DataFrame(cases)}
    handles = []
    labels = []
    for index, (ax, case) in enumerate(zip(axes.ravel(), cases)):
        panel_label(ax, chr(ord("a") + index))
        center = pd.Timestamp(case["center_timestamp"])
        sensor = str(case["sensor_id"])
        start = center - pd.Timedelta(hours=36)
        end = center + pd.Timedelta(hours=36)
        frame = node.loc[
            node["sensor_id"].eq(sensor) & node["timestamp"].between(start, end)
        ].copy()
        valid_pair_ids = frame.loc[frame["pair_id"].notna(), "pair_id"]
        pair_id = valid_pair_ids.iloc[0] if len(valid_pair_ids) else None
        pair_frame = pair.loc[
            pair["pair_id"].eq(pair_id) & pair["timestamp"].between(start, end),
            ["timestamp", "D4_raw", "Q_pair_available"],
        ]
        frame = frame.merge(pair_frame, on="timestamp", how="left")
        _shade_gate(ax, frame)
        line_specs = (
            ("D1_total", "D1", PALETTE["blue"], "-"),
            ("D2_total", "D2", PALETTE["teal"], "-"),
            ("D5_report_score", "D5 report", PALETTE["gold"], "-"),
            ("Q_node_available", "Node available", PALETTE["dark"], "-"),
            ("D4_raw", "D4 raw", PALETTE["red"], "--"),
        )
        for column, label, color, linestyle in line_specs:
            line = ax.plot(frame["timestamp"], frame[column], color=color, ls=linestyle, label=label, lw=0.95)[0]
            if index == 0:
                handles.append(line)
                labels.append(label)
        ax.axvline(center, color=PALETTE["gray"], ls=":", lw=0.8)
        ax.axhline(3.0, color=PALETTE["red"], ls="--", lw=0.6, alpha=0.7)
        ax.set_ylim(1.0, 5.05)
        ax.set_ylabel("Quality score")
        ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=3, maxticks=5))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d\n%H:%M"))
        case_title = str(case["case_type"]).replace("_", " ").strip().capitalize()
        ax.set_title(
            f"{case_title} | {_display_sensor(sensor)} | {center:%Y-%m-%d %H:%M}",
            loc="left",
            fontsize=6.6,
        )
        style_axes(ax)
        source_sheets[f"case_{index + 1}"] = frame[
            [
                "timestamp",
                "sensor_id",
                "pair_id",
                "D1_total",
                "D2_total",
                "D5_report_score",
                "D5_raw",
                "D4_raw",
                "Q_node_full",
                "Q_node_available",
                "Q_pair_available",
                "E_node",
                "coverage_class",
                "D3_gate_status",
            ]
        ]
    fig.legend(handles, labels, ncol=5, loc="outside upper center")
    write_workbook(source_root / "DQR_Fig05_source_data.xlsx", source_sheets)
    return save_figure(fig, figure_root, STEMS[4])


def build_all_figures(
    config: dict[str, Any],
    *,
    output_root: Path,
    node: pd.DataFrame,
    pair: pd.DataFrame,
    monthly: pd.DataFrame,
    aggregators: pd.DataFrame,
    weight_draws: pd.DataFrame,
    ablation: pd.DataFrame,
    construct: pd.DataFrame,
) -> list[Path]:
    configure_style()
    figure_root = output_root / "figures"
    source_root = output_root / "source_data"
    paths: list[Path] = []
    paths.extend(_figure_1(figure_root, source_root, node, pair))
    paths.extend(_figure_2(figure_root, source_root, node, monthly))
    paths.extend(_figure_3(config, figure_root, source_root, construct))
    paths.extend(_figure_4(figure_root, source_root, aggregators, weight_draws, ablation))
    paths.extend(_figure_5(config, figure_root, source_root, node, pair))
    return paths


def run_figure_qa(figure_root: Path, report_path: Path) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    for stem in STEMS:
        for suffix in ("png", "pdf", "svg", SUBMISSION_RASTER_EXTENSION.lstrip(".")):
            path = figure_root / f"{stem}.{suffix}"
            checks.append(
                {
                    "figure": stem,
                    "format": suffix,
                    "exists": path.exists(),
                    "size_bytes": path.stat().st_size if path.exists() else 0,
                }
            )
        png_path = figure_root / f"{stem}.png"
        if png_path.exists():
            with Image.open(png_path) as image:
                array = np.asarray(image.convert("L"))
                record = next(item for item in checks if item["figure"] == stem and item["format"] == "png")
                record["width_px"] = image.width
                record["height_px"] = image.height
                record["nonblank_std"] = float(array.std())
                record["width_contract_passed"] = abs(image.width - 4323) <= 4
                record["nonblank_passed"] = bool(array.std() > 3)
        pdf_path = figure_root / f"{stem}.pdf"
        if pdf_path.exists():
            document = fitz.open(pdf_path)
            rect = document[0].rect
            width_mm = rect.width * 25.4 / 72.0
            height_mm = rect.height * 25.4 / 72.0
            document.close()
            record = next(item for item in checks if item["figure"] == stem and item["format"] == "pdf")
            record["width_mm"] = width_mm
            record["height_mm"] = height_mm
            record["size_contract_passed"] = abs(width_mm - 183.0) <= 0.5 and height_mm <= 170.0
        svg_path = figure_root / f"{stem}.svg"
        if svg_path.exists():
            svg = svg_path.read_text(encoding="utf-8")
            record = next(item for item in checks if item["figure"] == stem and item["format"] == "svg")
            record["arial_declared"] = "Arial" in svg
            record["editable_text_present"] = "<text" in svg
    frame = pd.DataFrame(checks)
    required = ["exists", "size_bytes"]
    passed = bool(frame["exists"].all() and frame["size_bytes"].gt(1000).all())
    for column in ("width_contract_passed", "nonblank_passed", "size_contract_passed", "arial_declared", "editable_text_present"):
        if column in frame:
            observed = frame.loc[frame[column].notna(), column]
            passed = passed and bool(observed.all())
    payload = {
        "passed": passed,
        "contract": {
            "width_mm": 183.0,
            "max_height_mm": 170.0,
            "raster_dpi": 600,
            "font": "Arial",
            "formats": ["png", "pdf", "svg", "tiff"],
        },
        "figures": checks,
        "pending_figures": {
            "DQR_Fig06_prospective_validation": "pending_unscored_future_holdout",
            "DQR_Fig07_downstream_validation": "pending_no_frozen_endpoint_bundle",
        },
    }
    write_json(report_path, payload)
    if not passed:
        raise RuntimeError("Aggregation figure QA failed; inspect DQR_figure_qa.json")
    return payload
