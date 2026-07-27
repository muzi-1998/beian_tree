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
    }
)

BLUE = "#0F4D92"
BLUE_MID = "#7884B4"
BLUE_SOFT = "#B4C0E4"
ROSE = "#C76D7E"
TEAL = "#42949E"
GOLD = "#C89B3C"
RED = "#B64342"
GRAY = "#767676"
LIGHT = "#D9D9D9"
LOG_EPSILON = np.finfo(float).tiny


def _panel_label(ax: plt.Axes, label: str) -> None:
    ax.text(
        -0.16,
        1.06,
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


def _binned_recall(frame: pd.DataFrame, column: str, bins: int = 6) -> pd.DataFrame:
    valid_mask = frame[column].notna()
    valid = frame.loc[valid_mask].copy()
    valid["bin"] = pd.qcut(valid[column], q=min(bins, valid[column].nunique()), duplicates="drop")
    output = (
        valid.groupby("bin", observed=True)
        .agg(x=(column, "median"), recall=("detected", "mean"), n=("detected", "size"))
        .reset_index(drop=True)
    )
    output["n_input"] = len(frame)
    output["n_excluded_missing_x"] = int((~valid_mask).sum())
    return output


def figure_d1(outputs: dict[str, pd.DataFrame], figure_dir: Path) -> list[Path]:
    trials = outputs["D1_injection_trials"]
    summary = outputs["D1_injection_summary"]
    fig, axes = plt.subplots(2, 2, figsize=(7.2, 5.4))
    ax = axes[0, 0]
    order = ["spike", "step", "linear_drift", "hard_freeze"]
    shown = summary.set_index("fault_type").reindex(order)
    x = np.arange(len(order))
    errors = np.vstack(
        [
            shown["event_recall"] - shown["recall_ci_low"],
            shown["recall_ci_high"] - shown["event_recall"],
        ]
    )
    ax.errorbar(
        x,
        shown["event_recall"],
        yerr=errors,
        fmt="o",
        color=BLUE,
        ecolor=BLUE_MID,
        capsize=2.5,
        lw=1.0,
        ms=4.5,
    )
    ax.axhline(0.80, color=GRAY, lw=0.8, ls="--")
    ax.set_xticks(x, ["Spike", "Step", "Drift", "Hard freeze"], rotation=18, ha="right")
    ax.set_ylim(0, 1.03)
    ax.set_ylabel("Event recall")
    ax.set_title("Core fault detection")
    _panel_label(ax, "a")

    step = trials[trials["fault_type"].eq("step")]
    ax = axes[0, 1]
    scatter = ax.scatter(
        np.clip(step["duration"].to_numpy(float), LOG_EPSILON, None),
        step["amplitude_sigma"],
        c=np.where(step["detected"], BLUE, LIGHT),
        edgecolors=np.where(step["detected"], BLUE, GRAY),
        s=15,
        linewidths=0.35,
        alpha=0.85,
    )
    ax.set_xscale("log")
    ax.set_xlabel("Injected duration (h)")
    ax.set_ylabel("Amplitude (local sigma)")
    ax.set_title("Step applicability boundary")
    ax.legend(
        handles=[
            Line2D([], [], marker="o", ls="", color=BLUE, label="Detected"),
            Line2D(
                [],
                [],
                marker="o",
                ls="",
                markerfacecolor=LIGHT,
                markeredgecolor=GRAY,
                color=GRAY,
                label="Not detected",
            ),
        ],
        loc="lower left",
    )
    _panel_label(ax, "b")

    drift = trials[trials["fault_type"].eq("linear_drift")]
    ax = axes[1, 0]
    ax.scatter(
        np.clip(drift["duration"].to_numpy(float), LOG_EPSILON, None),
        drift["amplitude_sigma"],
        c=np.where(drift["detected"], TEAL, LIGHT),
        edgecolors=np.where(drift["detected"], TEAL, GRAY),
        s=15,
        linewidths=0.35,
        alpha=0.85,
    )
    ax.set_xscale("log")
    ax.set_xlabel("Injected duration (h)")
    ax.set_ylabel("Amplitude (local sigma)")
    ax.set_title("Drift applicability boundary")
    ax.legend(
        handles=[
            Line2D([], [], marker="o", ls="", color=TEAL, label="Detected"),
            Line2D(
                [],
                [],
                marker="o",
                ls="",
                markerfacecolor=LIGHT,
                markeredgecolor=GRAY,
                color=GRAY,
                label="Not detected",
            ),
        ],
        loc="lower left",
    )
    _panel_label(ax, "c")

    ax = axes[1, 1]
    for fault, color, label in (
        ("spike", ROSE, "Spike"),
        ("hard_freeze", GOLD, "Hard freeze"),
    ):
        frame = trials[trials["fault_type"].eq(fault)]
        binned = _binned_recall(frame, "duration")
        positive_x = np.clip(
            binned["x"].to_numpy(float),
            LOG_EPSILON,
            None,
        )
        ax.plot(positive_x, binned["recall"], marker="o", ms=3.5, lw=1.2, color=color, label=label)
    ax.axhline(0.80, color=GRAY, lw=0.8, ls="--")
    ax.set_xscale("log")
    ax.set_ylim(0, 1.03)
    ax.set_xlabel("Injected duration (min)")
    ax.set_ylabel("Binned event recall")
    ax.set_title("Short-event and lock duration response")
    ax.legend(loc="lower right")
    _panel_label(ax, "d")
    fig.subplots_adjust(left=0.10, right=0.98, bottom=0.10, top=0.95, wspace=0.34, hspace=0.36)
    path = figure_dir / "FigV2_D1_mechanism_validation"
    _save(fig, path)
    return [path]


def figure_cross_dimension(
    d2: dict[str, pd.DataFrame],
    d3: dict[str, pd.DataFrame],
    d4: dict[str, pd.DataFrame],
    d5: dict[str, pd.DataFrame],
    figure_dir: Path,
) -> list[Path]:
    fig, axes = plt.subplots(2, 2, figsize=(7.2, 5.4))
    ax = axes[0, 0]
    d2_summary = d2["D2_oat_summary"]
    parameter_labels = {
            "qfa_window_hours": "QFA window",
            "hard_rle_minutes": "Hard RLE",
            "gap_break_multiplier": "Gap mapping",
    }
    colors = {
        "qfa_window_hours": BLUE,
        "hard_rle_minutes": ROSE,
        "gap_break_multiplier": TEAL,
    }
    positions = np.arange(len(d2_summary))
    ax.scatter(
        positions,
        d2_summary["event_jaccard"],
        c=d2_summary["parameter"].map(colors),
        s=22,
        zorder=3,
    )
    for parameter, frame in d2_summary.groupby("parameter", sort=False):
        group_positions = frame.index.map(
            pd.Series(positions, index=d2_summary.index)
        ).to_numpy()
        ax.plot(
            group_positions,
            frame["event_jaccard"],
            color=colors[parameter],
            lw=1.1,
            label=parameter_labels[parameter],
        )
    ax.axhline(0.75, color=GRAY, ls="--", lw=0.8)
    ax.set_ylim(0, 1.03)
    setting_labels = []
    for row in d2_summary.itertuples(index=False):
        suffix = {
            "qfa_window_hours": " h",
            "hard_rle_minutes": " min",
            "gap_break_multiplier": "x",
        }[row.parameter]
        setting_labels.append(f"{row.setting:g}{suffix}")
    ax.set_xticks(positions, setting_labels, rotation=38, ha="right")
    ax.set_xlabel("Prespecified one-at-a-time setting")
    ax.set_ylabel("Event Jaccard")
    ax.set_title("D2 parameter stability")
    ax.legend(loc="lower left")
    _panel_label(ax, "a")

    ax = axes[0, 1]
    d3_summary = d3["D3_oat_summary"]
    for parameter, frame in d3_summary.groupby("parameter"):
        label = "Soft bounds" if parameter.startswith("soft") else "Rate threshold"
        ax.plot(frame["setting"], frame["event_jaccard"], marker="o", ms=3.5, lw=1.1, label=label)
    ax.axhline(0.75, color=GRAY, ls="--", lw=0.8)
    ax.set_ylim(0, 1.03)
    ax.set_xlabel("Threshold multiplier")
    ax.set_ylabel("Warning-event Jaccard")
    ax.set_title("D3 warning sensitivity")
    ax.legend(loc="lower left")
    _panel_label(ax, "b")

    ax = axes[1, 0]
    d4_summary = d4["D4_mechanism_summary"]
    shown = d4_summary[
        d4_summary["metric"].isin(["AUROC", "conditional_new_FAR"])
    ].copy()
    shown["label"] = shown["scenario"].str.replace("_", " ", regex=False)
    colors = np.where(shown["metric"].eq("AUROC"), BLUE, ROSE)
    ax.scatter(np.arange(len(shown)), shown["estimate"], c=colors, s=24, zorder=3)
    for index, row in enumerate(shown.itertuples(index=False)):
        if hasattr(row, "ci95_low") and np.isfinite(row.ci95_low):
            ax.vlines(index, row.ci95_low, row.ci95_high, color=colors[index], lw=0.9)
    ax.axhline(0.70, color=BLUE_MID, ls="--", lw=0.8)
    ax.axhline(0.10, color=ROSE, ls=":", lw=0.8)
    ax.set_xticks(np.arange(len(shown)), shown["label"], rotation=35, ha="right")
    ax.set_ylim(0, 1.03)
    ax.set_ylabel("Estimate")
    ax.set_title("D4 mechanism discrimination")
    ax.legend(
        handles=[
            Line2D([], [], marker="o", ls="", color=BLUE, label="AUROC"),
            Line2D(
                [],
                [],
                marker="o",
                ls="",
                color=ROSE,
                label="Common-process FAR",
            ),
        ],
        loc="lower left",
    )
    _panel_label(ax, "c")

    ax = axes[1, 1]
    acceptance = d5["D5_acceptance"].copy()
    acceptance = acceptance[
        acceptance["criterion"].isin(
            [
                "swap_AUROC",
                "swap_AUPRC",
                "swap_Top1",
                "common_mode_FAR",
                "zone_coherent_FAR",
            ]
        )
    ]
    x = np.arange(len(acceptance))
    colors = np.where(acceptance["passed"], TEAL, RED)
    ax.scatter(x, acceptance["estimate"], c=colors, s=26, zorder=3)
    for index, row in enumerate(acceptance.itertuples(index=False)):
        if np.isfinite(row.ci95_low):
            ax.vlines(index, row.ci95_low, row.ci95_high, color=colors[index], lw=0.9)
    ax.set_xticks(x, acceptance["criterion"].str.replace("_", " "), rotation=35, ha="right")
    ax.set_ylim(0, 1.03)
    ax.set_ylabel("Estimate (95% CI)")
    ax.set_title("D5 locked admission criteria")
    _panel_label(ax, "d")
    fig.subplots_adjust(left=0.10, right=0.98, bottom=0.16, top=0.95, wspace=0.34, hspace=0.42)
    path = figure_dir / "FigV2_D2_D5_confirmatory_validation"
    _save(fig, path)
    return [path]


def figure_composite(
    composite: dict[str, pd.DataFrame],
    figure_dir: Path,
) -> list[Path]:
    plant = composite["WWDQS_plant_summary"].copy()
    boot = composite["WWDQS_block_bootstrap"].copy()
    node = composite["WWDQS_node_scores"].copy()
    ablation = composite["WWDQS_dimension_ablation"].copy()
    fig, axes = plt.subplots(2, 2, figsize=(7.2, 5.4))
    ax = axes[0, 0]
    ax.plot(plant["date"], plant["node_score_median"], color=BLUE, lw=1.0, label="Node")
    ax.plot(plant["date"], plant["pair_score_median"], color=ROSE, lw=1.0, label="Pair")
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b\n%Y"))
    ax.set_ylim(1, 5)
    ax.set_ylabel("Daily median score")
    ax.set_title("Retrospective node and pair products")
    ax.legend(loc="lower left")
    _panel_label(ax, "a")

    ax = axes[0, 1]
    main = boot[boot["method"].eq("main_7d")].copy()
    sensitivity = boot[boot["method"].eq("sensitivity_48h")].copy()
    x = np.arange(len(main))
    ax.errorbar(
        x - 0.08,
        main["estimate"],
        yerr=np.vstack([main["estimate"] - main["ci_low"], main["ci_high"] - main["estimate"]]),
        fmt="o",
        color=BLUE,
        capsize=2,
        ms=3.5,
        label="7 d blocks",
    )
    ax.errorbar(
        x + 0.08,
        sensitivity["estimate"],
        yerr=np.vstack(
            [
                sensitivity["estimate"] - sensitivity["ci_low"],
                sensitivity["ci_high"] - sensitivity["estimate"],
            ]
        ),
        fmt="o",
        color=TEAL,
        capsize=2,
        ms=3.5,
        label="48 h blocks",
    )
    month_labels = [
        pd.Period(value, freq="M").strftime("%b\n%Y") for value in main["month"]
    ]
    ax.set_xticks(x, month_labels)
    ax.set_ylim(1, 5)
    ax.set_ylabel("Mean node score (95% CI)")
    ax.set_title("Autocorrelation-aware uncertainty")
    ax.legend(loc="lower left")
    _panel_label(ax, "b")

    ax = axes[1, 0]
    coverage = (
        node.assign(month=node["timestamp"].dt.to_period("M").astype(str))
        .groupby(["month", "coverage_class"], as_index=False)
        .size()
    )
    pivot = coverage.pivot(index="month", columns="coverage_class", values="size").fillna(0)
    pivot = pivot.div(pivot.sum(axis=1), axis=0)
    order = [column for column in ["full", "basic", "limited", "insufficient"] if column in pivot]
    bottom = np.zeros(len(pivot))
    palette = {"full": BLUE, "basic": BLUE_SOFT, "limited": GOLD, "insufficient": LIGHT}
    for column in order:
        ax.bar(np.arange(len(pivot)), pivot[column], bottom=bottom, color=palette[column], width=0.75, label=column)
        bottom += pivot[column].to_numpy()
    coverage_labels = [
        pd.Period(value, freq="M").strftime("%b\n%Y") for value in pivot.index
    ]
    ax.set_xticks(np.arange(len(pivot)), coverage_labels)
    ax.set_ylim(0, 1)
    ax.set_ylabel("Sensor-hour fraction")
    ax.set_title("Evidence coverage")
    ax.legend(ncol=3, loc="lower left")
    _panel_label(ax, "c")

    ax = axes[1, 1]
    shown = ablation[ablation["variant"].str.startswith("without_")].copy()
    y = np.arange(len(shown))
    ax.barh(y, shown["spearman_vs_full"], color=BLUE_MID, height=0.55)
    ax.set_yticks(y, shown["variant"].str.replace("without_", "Without "))
    ax.set_xlim(0, 1.02)
    ax.set_xlabel("Spearman correlation with full node score")
    ax.set_title("Dimension ablation")
    _panel_label(ax, "d")
    fig.subplots_adjust(left=0.12, right=0.98, bottom=0.14, top=0.95, wspace=0.38, hspace=0.40)
    path = figure_dir / "FigV2_WWDQS_composite"
    _save(fig, path)
    return [path]


def write_figure_manifest(
    figure_dir: Path,
    figure_stems: list[Path],
    source_paths: list[Path],
    run_id: str,
) -> Path:
    payload = {
        "run_id": run_id,
        "backend": "python",
        "figures": [],
    }
    source_hashes = {
        path.name: sha256_file(path) for path in source_paths if path.exists()
    }
    for stem in figure_stems:
        payload["figures"].append(
            {
                "stem": stem.name,
                "contract": "quantitative_grid",
                "outputs": {
                    suffix: sha256_file(stem.with_suffix(suffix))
                    for suffix in [".svg", ".pdf", ".png", ".tiff"]
                },
                "source_data_sha256": source_hashes,
            }
        )
    path = figure_dir / "figure_manifest.json"
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path
