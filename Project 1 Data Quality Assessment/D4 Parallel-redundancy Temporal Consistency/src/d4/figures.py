from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import matplotlib as mpl
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
from matplotlib.colors import LinearSegmentedColormap
import numpy as np
import pandas as pd
from sklearn.metrics import (
    average_precision_score,
    roc_auc_score,
)

from .config import D4Config
from .figure_style import (
    KEY_LINE_WIDTH,
    PALETTE,
    configure_style,
    finalize,
    panel_label,
)


FIG_WIDTH_MM = 183
PAIR_ORDER = ["PAIR_DO11", "PAIR_DO12", "PAIR_DO13", "PAIR_DO14",
              "PAIR_ORP11", "PAIR_ORP12", "PAIR_ORP13"]
Q_COLUMNS = ["Q_dist", "Q_trend", "Q_var", "Q_cp"]
Q_LABELS = {"Q_dist": "Distribution", "Q_trend": "Trend",
            "Q_var": "Variability", "Q_cp": "Change point"}
Q_COLORS = {"Q_dist": PALETTE["blue"], "Q_trend": PALETTE["green"],
            "Q_var": PALETTE["orange"], "Q_cp": PALETTE["purple"]}
INJECTION_LABELS = {
    "unilateral_drift": "Drift",
    "unilateral_step": "Step",
    "unilateral_freeze": "Freeze",
    "unilateral_spike": "Spike (D1-owned)",
}
INJECTION_COLORS = {
    "unilateral_drift": PALETTE["blue"],
    "unilateral_step": PALETTE["orange"],
    "unilateral_freeze": PALETTE["green"],
    "unilateral_spike": PALETTE["purple"],
}


def _boxed(ax) -> None:
    for spine in ax.spines.values():
        spine.set_visible(True)


def _open(ax) -> None:
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)


def _pair_label(pair_id: str) -> str:
    return pair_id.replace("PAIR_", "")


def _pair_order(frame: pd.DataFrame) -> list[str]:
    pair_ids = frame["pair_id"]
    observed = set(pair_ids[pair_ids.notna()].astype(str))
    return [pair for pair in PAIR_ORDER if pair in observed]


def _write_source(source_dir: Path, stem: str, sheets: dict[str, pd.DataFrame]) -> None:
    source_dir.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(source_dir / f"{stem}_source_data.xlsx", engine="openpyxl") as writer:
        for name, frame in sheets.items():
            frame.to_excel(writer, sheet_name=name[:31], index=False)


def _save_publication_figure(fig, output_base: Path) -> None:
    mpl.rcParams.update({
        "font.family": "Arial",
        "svg.fonttype": "none",
        "pdf.fonttype": 42,
    })
    finalize(fig)
    svg_path = output_base.with_suffix(".svg")
    fig.savefig(svg_path, bbox_inches="tight")
    svg_text = svg_path.read_text(encoding="utf-8")
    svg_path.write_text(
        "\n".join(line.rstrip() for line in svg_text.splitlines()) + "\n",
        encoding="utf-8",
    )
    fig.savefig(output_base.with_suffix(".pdf"), bbox_inches="tight")
    fig.savefig(output_base.with_suffix(".png"), dpi=600, bbox_inches="tight")
    fig.savefig(
        output_base.with_suffix(".tiff"), dpi=600, bbox_inches="tight",
        pil_kwargs={"compression": "tiff_lzw"},
    )
    plt.close(fig)


def _week_block_interval(
    frame: pd.DataFrame,
    value_column: str,
    statistic: Callable[[pd.Series], float],
    *,
    repetitions: int = 800,
    seed: int = 20260812,
) -> tuple[float, float]:
    columns = ["timestamp", value_column]
    before_count = len(frame)
    complete = frame[columns].notna().all(axis=1)
    work = frame.loc[complete, columns].copy()
    after_count = len(work)
    if work.empty:
        return np.nan, np.nan
    work["week"] = work["timestamp"].dt.to_period("W-SUN").dt.start_time
    blocks = [group[value_column] for _, group in work.groupby("week", sort=False)]
    rng = np.random.Generator(np.random.PCG64(seed))
    estimates = []
    for _ in range(repetitions):
        sampled = rng.integers(0, len(blocks), len(blocks))
        draw = pd.concat([blocks[index] for index in sampled], ignore_index=True)
        estimates.append(float(statistic(draw)))
    return tuple(np.quantile(estimates, [0.025, 0.975]))


def _day_block_interval(
    frame: pd.DataFrame,
    metric: Callable[[pd.DataFrame], float],
    *,
    repetitions: int = 600,
    seed: int = 20260812,
) -> tuple[float, float]:
    work = frame.copy()
    work["day"] = work["timestamp"].dt.floor("D")
    blocks = [group for _, group in work.groupby("day", sort=False)]
    if not blocks:
        return np.nan, np.nan
    rng = np.random.Generator(np.random.PCG64(seed))
    values = []
    for _ in range(repetitions):
        sampled = rng.integers(0, len(blocks), len(blocks))
        draw = pd.concat([blocks[index] for index in sampled], ignore_index=True)
        values.append(float(metric(draw)))
    return tuple(np.quantile(values, [0.025, 0.975]))


def _provenance_table(params: pd.DataFrame) -> pd.DataFrame:
    frame = params[params["regime_id"].notna()].copy()
    frame["regime_id"] = frame["regime_id"].astype(int)
    return (
        frame.groupby(["variable", "regime_id"], as_index=False)
        .agg(
            sample_size=("sample_size", "min"),
            exact_stratum_size=("exact_stratum_size", "min"),
            mapping_scope=("mapping_scope", "first"),
            calibration_quality=("calibration_quality", "first"),
        )
        .sort_values(["variable", "regime_id"])
    )


def figure_1_framework(cfg: D4Config, params: pd.DataFrame, output_dir: Path, source_dir: Path) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(FIG_WIDTH_MM / 25.4, 70 / 25.4),
                             gridspec_kw={"width_ratios": [1.15, 1.55, 1.0], "wspace": 0.10})
    for ax in axes:
        ax.set_axis_off()

    pair_y = np.linspace(0.74, 0.12, len(cfg.pairs))
    axes[0].text(0.46, 1.03, "Homologous pair input", transform=axes[0].transAxes,
                 fontsize=8, fontweight="bold", ha="center", va="bottom", clip_on=False)
    for y, pair in zip(pair_y, cfg.pairs):
        color = PALETTE["blue"] if pair.variable == "DO" else PALETTE["orange"]
        axes[0].plot([0.08, 0.28], [y, y], color=color, lw=1.8, solid_capstyle="round")
        axes[0].plot([0.63, 0.83], [y, y], color=color, lw=1.8, solid_capstyle="round")
        axes[0].annotate("", xy=(0.59, y), xytext=(0.32, y),
                         arrowprops={"arrowstyle": "<->", "lw": 0.7, "color": PALETTE["gray"]})
        axes[0].text(0.18, y + 0.035, pair.target.replace("_", "-"), ha="center", fontsize=6.5)
        axes[0].text(0.73, y + 0.035, pair.reference.replace("_", "-"), ha="center", fontsize=6.5)
        axes[0].text(0.455, y - 0.045, _pair_label(pair.pair_id), ha="center", fontsize=6.5,
                     color=PALETTE["gray"])
    panel_label(axes[0], "a")

    axes[1].text(0.04, 0.96, "Independent D4 evidence chain", transform=axes[1].transAxes,
                 fontsize=8, fontweight="bold", va="top")
    boxes = [
        (0.09, 0.17, "De-periodised\nresiduals"),
        (0.28, 0.16, "24 h paired\nwindow"),
        (0.49, 0.20, "W1 / KS\nSlope / IQR / CP"),
        (0.72, 0.17, "Public quantile\nmapping"),
        (0.91, 0.12, "D4 raw"),
    ]
    for index, (x, width, label) in enumerate(boxes):
        axes[1].add_patch(mpl.patches.FancyBboxPatch(
            (x - width / 2, 0.48), width, 0.25,
            boxstyle="round,pad=0.015,rounding_size=0.018",
            transform=axes[1].transAxes, facecolor=PALETTE["pale_gray"],
            edgecolor=PALETTE["gray"], linewidth=0.7,
        ))
        axes[1].text(x, 0.605, label, transform=axes[1].transAxes,
                     ha="center", va="center", fontsize=5.8)
        if index < len(boxes) - 1:
            next_x, next_width, _ = boxes[index + 1]
            axes[1].annotate("", xy=(next_x - next_width / 2 - 0.008, 0.605),
                             xytext=(x + width / 2 + 0.01, 0.605), xycoords=axes[1].transAxes,
                             arrowprops={"arrowstyle": "->", "lw": 0.7, "color": PALETTE["black"]})
    axes[1].text(0.50, 0.34, "Distribution   Trend   Variability   Coarse structural change",
                 transform=axes[1].transAxes, ha="center", fontsize=6.3, color=PALETTE["gray"])
    axes[1].text(0.49, 0.16, "0.75 weighted mean + 0.25 minimum-subscore penalty",
                 transform=axes[1].transAxes, ha="center", fontsize=6.5,
                 bbox={"facecolor": "white", "edgecolor": PALETTE["light_gray"], "pad": 2.2})
    panel_label(axes[1], "b")

    axes[2].text(0.04, 0.96, "Dimension boundary", transform=axes[2].transAxes,
                 fontsize=8, fontweight="bold", va="top")
    roles = [
        ("D1", "Benchmark admission\nand interpretation", PALETTE["blue"]),
        ("D2", "Observability gate", PALETTE["orange"]),
        ("D4", "Independent numeric\npair asymmetry", PALETTE["green"]),
        ("D5", "Attribution guard;\nno score rewrite", PALETTE["purple"]),
    ]
    for y, (name, role, color) in zip(np.linspace(0.78, 0.22, 4), roles):
        axes[2].scatter([0.16], [y], s=90, color=color, edgecolor="white", linewidth=0.6,
                        transform=axes[2].transAxes, clip_on=False)
        axes[2].text(0.16, y, name, color="white", fontweight="bold", fontsize=6.5,
                     ha="center", va="center", transform=axes[2].transAxes)
        axes[2].text(0.30, y, role, fontsize=6.5, va="center", transform=axes[2].transAxes)
    axes[2].text(0.06, 0.05, "Detection does not establish sensor causality",
                 transform=axes[2].transAxes, fontsize=6.4, color=PALETTE["red"])
    panel_label(axes[2], "c")

    fig.subplots_adjust(left=0.035, right=0.99, top=0.94, bottom=0.05)
    stem = "FigD4_1_scientific_construct"
    _save_publication_figure(fig, output_dir / stem)
    _write_source(source_dir, stem, {
        "pair_contract": pd.DataFrame([vars(pair) for pair in cfg.pairs]),
        "aggregation": pd.DataFrame({
            "component": list(cfg.weights),
            "weight": [cfg.weights[key] for key in cfg.weights],
        }),
        "calibration_scope": _provenance_table(params),
    })


def figure_2_pair_profile(
    cfg: D4Config,
    main: pd.DataFrame,
    params: pd.DataFrame,
    output_dir: Path,
    source_dir: Path,
) -> None:
    valid = main[main["usable_for_D4"]].copy()
    pairs = _pair_order(valid)
    rows = []
    for pair in pairs:
        subset = valid[valid["pair_id"].eq(pair)]
        for q_col in Q_COLUMNS:
            low, high = _week_block_interval(subset, q_col, lambda values: values.median())
            rows.append({
                "pair_id": pair, "component": q_col,
                "median": float(subset[q_col].median()),
                "mean": float(subset[q_col].mean()),
                "ci_low": low, "ci_high": high,
                "n_windows": len(subset),
            })
    component = pd.DataFrame(rows)
    pair_summary = (
        valid.groupby("pair_id", as_index=False)
        .agg(mean_D4_raw=("D4_raw", "mean"), median_D4_raw=("D4_raw", "median"),
             p05_D4_raw=("D4_raw", lambda x: x.quantile(0.05)),
             p95_D4_raw=("D4_raw", lambda x: x.quantile(0.95)),
             low_score_rate=("D4_raw", lambda x: (x < 3.0).mean()),
             n_windows=("D4_raw", "size"))
        .set_index("pair_id").reindex(pairs).reset_index()
    )
    provenance = _provenance_table(params)
    fallback_by_variable = provenance.groupby("variable")["mapping_scope"].apply(
        lambda values: float(values.str.contains("fallback").mean())
    ).to_dict()

    fig, axes = plt.subplots(1, 3, figsize=(FIG_WIDTH_MM / 25.4, 84 / 25.4),
                             gridspec_kw={"width_ratios": [1.55, 1.0, 0.78], "wspace": 0.40})
    positions = np.arange(len(pairs))
    offsets = np.linspace(-0.24, 0.24, len(Q_COLUMNS))
    for offset, q_col in zip(offsets, Q_COLUMNS):
        frame = component[component["component"].eq(q_col)].set_index("pair_id").reindex(pairs)
        y = frame["median"].to_numpy()
        error = np.vstack([y - frame["ci_low"].to_numpy(), frame["ci_high"].to_numpy() - y])
        axes[0].errorbar(positions + offset, y, yerr=error, fmt="o", ms=3.2,
                         color=Q_COLORS[q_col], ecolor=Q_COLORS[q_col], elinewidth=0.7,
                         capsize=1.5, label=Q_LABELS[q_col])
    axes[0].plot(positions, pair_summary["mean_D4_raw"], marker="D", ms=3.2,
                 color=PALETTE["black"], lw=0, label="Mean D4 raw")
    axes[0].axhline(3.0, color=PALETTE["red"], lw=0.7, ls=(0, (3, 2)))
    axes[0].set_ylim(1, 5.15)
    axes[0].set_ylabel("Subscore or D4 raw (1-5)")
    axes[0].set_xticks(positions, [_pair_label(pair) for pair in pairs], rotation=35, ha="right")
    axes[0].legend(loc="lower left", ncol=2, columnspacing=0.8, handletextpad=0.4)
    panel_label(axes[0], "a")
    _open(axes[0])

    axes[1].hlines(positions, pair_summary["p05_D4_raw"], pair_summary["p95_D4_raw"],
                   color=PALETTE["light_gray"], lw=5.5, zorder=1)
    axes[1].scatter(pair_summary["median_D4_raw"], positions, s=25,
                    color=PALETTE["green"], edgecolor="white", linewidth=0.5, zorder=2,
                    label="Median")
    axes[1].scatter(pair_summary["mean_D4_raw"], positions, s=18, marker="D",
                    color=PALETTE["black"], zorder=3, label="Mean")
    axes[1].axvline(3.0, color=PALETTE["red"], lw=0.7, ls=(0, (3, 2)))
    axes[1].set_xlim(1, 5)
    axes[1].set_yticks(positions, [_pair_label(pair) for pair in pairs])
    axes[1].invert_yaxis()
    axes[1].set_xlabel("D4 raw (P05-P95)")
    axes[1].legend(loc="upper right", frameon=True, framealpha=0.78)
    panel_label(axes[1], "b")
    _open(axes[1])

    burden = pair_summary["low_score_rate"].to_numpy() * 100
    colors = [PALETTE["blue"] if "DO" in pair else PALETTE["orange"] for pair in pairs]
    axes[2].barh(positions, burden, color=colors, height=0.66)
    axes[2].set_yticks(positions, [_pair_label(pair) for pair in pairs])
    axes[2].invert_yaxis()
    axes[2].set_xlabel("D4 < 3 among evaluable (%)")
    for y, value, pair in zip(positions, burden, pairs):
        axes[2].text(value + 1.0, y, f"{value:.1f}", va="center", fontsize=6.5)
    axes[2].text(0.98, 0.98,
                 f"ORP: {fallback_by_variable.get('ORP', 0):.0%} of regimes use fallback",
                 transform=axes[2].transAxes, ha="right", va="top", fontsize=5.8,
                 color=PALETTE["red"],
                 bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.82, "pad": 0.8})
    axes[2].set_xlim(0, max(burden) * 1.18)
    panel_label(axes[2], "c")
    _open(axes[2])

    fig.subplots_adjust(left=0.07, right=0.99, top=0.93, bottom=0.22)
    stem = "FigD4_2_pair_mechanism_profile"
    _save_publication_figure(fig, output_dir / stem)
    _write_source(source_dir, stem, {
        "component_week_block_CI": component,
        "pair_summary": pair_summary,
        "calibration_provenance": provenance,
    })


def figure_3_burden_coverage_calibration(
    main: pd.DataFrame,
    params: pd.DataFrame,
    output_dir: Path,
    source_dir: Path,
) -> None:
    pairs = _pair_order(main)
    work = main.copy()
    work["week"] = work["timestamp"].dt.to_period("W-SUN").dt.end_time.dt.normalize()
    records = []
    for (pair, week), group in work.groupby(["pair_id", "week"], sort=True):
        usable = group["usable_for_D4"].astype(bool)
        n_usable = int(usable.sum())
        records.append({
            "pair_id": pair, "week_ending": week,
            "asymmetry_fraction": float((group.loc[usable, "D4_raw"] < 3.0).mean()) if n_usable else np.nan,
            "borderline_fraction": float(group.loc[usable, "D4_raw"].between(3.0, 3.5, inclusive="left").mean()) if n_usable else np.nan,
            "evaluable_fraction": float(usable.mean()),
            "n_windows": len(group), "n_evaluable": n_usable,
        })
    weekly = pd.DataFrame(records)
    weeks = sorted(weekly["week_ending"].drop_duplicates())
    burden = weekly.pivot(index="pair_id", columns="week_ending", values="asymmetry_fraction").reindex(index=pairs, columns=weeks)
    coverage = weekly.pivot(index="pair_id", columns="week_ending", values="evaluable_fraction").reindex(index=pairs, columns=weeks)
    provenance = _provenance_table(params)
    provenance["stratum"] = provenance["variable"] + " R" + provenance["regime_id"].astype(str)
    strata = provenance["stratum"].tolist()
    exact = provenance["exact_stratum_size"].to_numpy(dtype=float)
    support = provenance["sample_size"].to_numpy(dtype=float)
    share = np.divide(exact, support, out=np.zeros_like(exact), where=support > 0)

    fig = plt.figure(figsize=(FIG_WIDTH_MM / 25.4, 114 / 25.4))
    grid = fig.add_gridspec(3, 2, width_ratios=[1, 0.035], height_ratios=[1.25, 1.0, 0.90],
                            hspace=0.62, wspace=0.06)
    ax_a = fig.add_subplot(grid[0, 0]); cax_a = fig.add_subplot(grid[0, 1])
    ax_b = fig.add_subplot(grid[1, 0], sharex=ax_a); cax_b = fig.add_subplot(grid[1, 1])
    ax_c = fig.add_subplot(grid[2, 0]); fig.add_subplot(grid[2, 1]).set_axis_off()
    burden_cmap = LinearSegmentedColormap.from_list("burden", ["#F4F4F4", "#E69F00", "#D55E00"])
    burden_cmap.set_bad(PALETTE["mid_gray"])
    image_a = ax_a.imshow(burden.to_numpy(dtype=float), aspect="auto", interpolation="nearest",
                          cmap=burden_cmap, vmin=0, vmax=1)
    ax_a.set_yticks(np.arange(len(pairs)), [_pair_label(pair) for pair in pairs])
    plt.setp(ax_a.get_xticklabels(), visible=False)
    fig.colorbar(image_a, cax=cax_a, ticks=[0, 0.5, 1]).set_label("D4 < 3 fraction")
    panel_label(ax_a, "a"); _boxed(ax_a)
    coverage_cmap = LinearSegmentedColormap.from_list("coverage", ["#ECEFF1", "#56B4E9", "#0072B2"])
    image_b = ax_b.imshow(coverage.to_numpy(dtype=float), aspect="auto", interpolation="nearest",
                          cmap=coverage_cmap, vmin=0, vmax=1)
    ax_b.set_yticks(np.arange(len(pairs)), [_pair_label(pair) for pair in pairs])
    tick = np.linspace(0, len(weeks) - 1, 8, dtype=int)
    ax_b.set_xticks(tick, [pd.Timestamp(weeks[index]).strftime("%Y-%m-%d") for index in tick],
                    rotation=25, ha="right")
    ax_b.set_xlabel("Week ending Sunday")
    fig.colorbar(image_b, cax=cax_b, ticks=[0, 0.5, 1]).set_label("Evaluable fraction")
    panel_label(ax_b, "b"); _boxed(ax_b)

    x = np.arange(len(strata))
    bars = ax_c.bar(x, support, color=[PALETTE["blue"] if label.startswith("DO") else PALETTE["orange"] for label in strata],
                    width=0.68)
    for bar, ratio, quality in zip(bars, share, provenance["calibration_quality"]):
        if quality != "adequate":
            bar.set_hatch("///")
            bar.set_edgecolor(PALETTE["red"])
        ax_c.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + max(support) * 0.025,
                  f"{ratio:.0%} exact", ha="center", va="bottom", fontsize=6.0,
                  color=PALETTE["red"] if quality != "adequate" else PALETTE["gray"])
    ax_c.axhline(100, color=PALETTE["gray"], lw=0.7, ls=(0, (3, 2)), label="Minimum stratum support")
    ax_c.set_ylabel("Calibration windows")
    ax_c.set_xticks(x, strata)
    if np.any(support <= 0):
        raise ValueError("Calibration support must be strictly positive for the log axis")
    ax_c.set_yscale("log")
    ax_c.legend(loc="upper right")
    panel_label(ax_c, "c"); _open(ax_c)
    fig.subplots_adjust(left=0.09, right=0.94, top=0.98, bottom=0.10)
    stem = "FigD4_3_burden_coverage_calibration"
    _save_publication_figure(fig, output_dir / stem)
    _write_source(source_dir, stem, {"weekly_contract": weekly, "calibration_provenance": provenance})


def figure_4_field_cases(
    cfg: D4Config,
    main: pd.DataFrame,
    events: pd.DataFrame,
    output_dir: Path,
    source_dir: Path,
) -> None:
    residuals = pd.read_parquet(cfg.paths["residuals"])
    residuals = residuals.resample("1h").median()
    selected = []
    for pair_id in ("PAIR_DO14", "PAIR_ORP13"):
        candidate = events[events["pair_id"].eq(pair_id)].sort_values(
            ["duration_h", "min_D4_raw"], ascending=[False, True]
        ).iloc[0]
        selected.append(candidate)
    fig, axes = plt.subplots(4, 2, figsize=(FIG_WIDTH_MM / 25.4, 113 / 25.4), sharex="col",
                             gridspec_kw={"height_ratios": [1.30, 0.85, 0.82, 0.72], "hspace": 0.16, "wspace": 0.24})
    source_sheets = {}
    for column, event in enumerate(selected):
        pair = next(pair for pair in cfg.pairs if pair.pair_id == event.pair_id)
        start = pd.Timestamp(event.start_ts) - pd.Timedelta(days=2)
        end = pd.Timestamp(event.end_ts) + pd.Timedelta(days=2)
        trace = residuals.loc[start:end, [pair.target, pair.reference]].copy()
        scale_values = trace.to_numpy().ravel()
        scale_values = scale_values[np.isfinite(scale_values)]
        scale = max(float(np.median(np.abs(scale_values - np.median(scale_values))) * 1.4826), cfg.deadband[pair.variable])
        trace = trace / scale
        score = main[(main["pair_id"].eq(pair.pair_id)) & main["timestamp"].between(start, end)].copy()
        ax = axes[0, column]
        ax.plot(trace.index, trace[pair.target], color=PALETTE["blue"], lw=KEY_LINE_WIDTH,
                label=pair.target.replace("_", "-"))
        ax.plot(trace.index, trace[pair.reference], color=PALETTE["orange"], lw=KEY_LINE_WIDTH,
                label=pair.reference.replace("_", "-"))
        ax.axvspan(event.start_ts, event.end_ts, color=PALETTE["red"], alpha=0.12, lw=0)
        ax.legend(loc="lower right", bbox_to_anchor=(1.0, 1.01), ncol=2,
                  columnspacing=0.8, frameon=False, borderaxespad=0)
        ax.set_ylabel("Residual (robust z)")
        ax.set_title(f"{_pair_label(pair.pair_id)} | {event.event_id} | {int(event.duration_h)} h", loc="left", fontweight="bold")
        panel_label(ax, chr(97 + column)); _open(ax)

        ax = axes[1, column]
        ax.plot(score["timestamp"], score["D4_raw"], color=PALETTE["black"], lw=KEY_LINE_WIDTH)
        ax.fill_between(score["timestamp"], 1, score["D4_raw"], where=score["D4_raw"].lt(3),
                        color=PALETTE["red"], alpha=0.18)
        ax.axhline(3, color=PALETTE["red"], lw=0.7, ls=(0, (3, 2)))
        ax.set_ylim(1, 5); ax.set_ylabel("D4 raw")
        panel_label(ax, chr(99 + column)); _open(ax)

        ax = axes[2, column]
        for q_col in Q_COLUMNS:
            ax.plot(score["timestamp"], score[q_col], lw=0.8, color=Q_COLORS[q_col], label=Q_LABELS[q_col])
        ax.set_ylim(1, 5); ax.set_ylabel("Subscore")
        if column == 1:
            handles, labels = ax.get_legend_handles_labels()
            fig.legend(handles, labels, loc="lower center", bbox_to_anchor=(0.50, 0.050),
                       ncol=4, columnspacing=1.1, frameon=False)
        panel_label(ax, chr(101 + column)); _open(ax)

        ax = axes[3, column]
        ax.plot(score["timestamp"], score["D1_target"], color=PALETTE["blue"], lw=0.8, label="D1 target")
        ax.plot(score["timestamp"], score["D1_ref"], color=PALETTE["orange"], lw=0.8, label="D1 peer")
        d2_ok = (~score["D2_target_veto"].astype(bool) & ~score["D2_ref_veto"].astype(bool)).astype(float)
        ax.fill_between(score["timestamp"], 1, 5, where=d2_ok.lt(0.5), color=PALETTE["mid_gray"], alpha=0.35,
                        label="D2 not observable")
        ax.set_ylim(1, 5); ax.set_ylabel("Context score")
        ax.xaxis.set_major_locator(mdates.AutoDateLocator(minticks=3, maxticks=5))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))
        ax.set_xlabel("Date")
        if column == 0:
            handles, labels = ax.get_legend_handles_labels()
            fig.legend(handles, labels, loc="lower center", bbox_to_anchor=(0.50, 0.005),
                       ncol=3, columnspacing=1.1, frameon=False)
        ax.text(0.99, 0.05, "Causal attribution pending",
                transform=ax.transAxes, ha="right", va="bottom", fontsize=6.2,
                color=PALETTE["red"], bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.80, "pad": 0.15})
        panel_label(ax, chr(103 + column)); _open(ax)
        source = score[["timestamp", "pair_id", "D4_raw", *Q_COLUMNS, "D1_target", "D1_ref",
                        "D2_target_veto", "D2_ref_veto", "usable_for_D4"]].copy()
        source = source.merge(trace.reset_index().rename(columns={trace.index.name or "index": "timestamp"}),
                              on="timestamp", how="left")
        source_sheets[_pair_label(pair.pair_id)] = source
    fig.subplots_adjust(left=0.08, right=0.99, top=0.91, bottom=0.19, hspace=0.24)
    stem = "FigD4_4_formal_episode_cases"
    _save_publication_figure(fig, output_dir / stem)
    source_sheets["episode_registry"] = pd.DataFrame(selected)
    _write_source(source_dir, stem, source_sheets)


def _per_pair_auc(scores: pd.DataFrame) -> pd.DataFrame:
    rows = []
    baseline = scores[scores["injection"].eq("baseline")]
    for pair in _pair_order(scores):
        negative = baseline[baseline["pair_id"].eq(pair)]
        for injection in INJECTION_LABELS:
            positive = scores[(scores["pair_id"].eq(pair)) & scores["injection"].eq(injection)]
            combined = pd.concat([negative, positive], ignore_index=True)
            if combined["is_unilateral_fault"].nunique() < 2:
                continue
            y = combined["is_unilateral_fault"].astype(int)
            risk = combined["anomaly_score"]
            rows.append({"pair_id": pair, "injection": injection,
                         "AUROC": roc_auc_score(y, risk),
                         "AUPRC": average_precision_score(y, risk)})
    return pd.DataFrame(rows)


def figure_5_mechanism_validation(
    benchmark_path: Path,
    mechanism_summary_path: Path | None,
    output_dir: Path,
    source_dir: Path,
) -> None:
    curves = pd.read_excel(benchmark_path, sheet_name="roc_pr_curves")
    scores = pd.read_excel(benchmark_path, sheet_name="injection_scores")
    summary = pd.read_excel(benchmark_path, sheet_name="summary")
    mechanism = pd.read_parquet(mechanism_summary_path) if mechanism_summary_path and mechanism_summary_path.exists() else pd.DataFrame()
    per_pair = _per_pair_auc(scores)
    fig, axes = plt.subplots(2, 2, figsize=(FIG_WIDTH_MM / 25.4, 118 / 25.4),
                             gridspec_kw={"hspace": 0.40, "wspace": 0.32})
    # Each precision-recall curve compares one injected mechanism with its
    # matched baseline windows, so the class prevalence is exactly balanced.
    prevalence = 0.5
    for injection in INJECTION_LABELS:
        color = INJECTION_COLORS[injection]
        roc = curves[(curves["injection"].eq(injection)) & curves["curve"].eq("ROC")]
        pr = curves[(curves["injection"].eq(injection)) & curves["curve"].eq("PR")]
        subset = scores[scores["injection"].isin(["baseline", injection])]
        y = subset["is_unilateral_fault"].astype(int)
        risk = subset["anomaly_score"]
        auroc = roc_auc_score(y, risk); auprc = average_precision_score(y, risk)
        axes[0, 0].plot(roc["x"], roc["y"], color=color, lw=KEY_LINE_WIDTH,
                        label=f"{INJECTION_LABELS[injection]} ({auroc:.2f})")
        axes[0, 1].plot(pr["x"], pr["y"], color=color, lw=KEY_LINE_WIDTH,
                        label=f"{INJECTION_LABELS[injection]} ({auprc:.2f})")
    axes[0, 0].plot([0, 1], [0, 1], color=PALETTE["gray"], lw=0.7, ls=(0, (3, 2)))
    axes[0, 0].set(xlim=(0, 1), ylim=(0, 1), xlabel="False-positive rate", ylabel="True-positive rate")
    axes[0, 0].legend(loc="lower right", title="AUROC")
    axes[0, 1].axhline(prevalence, color=PALETTE["gray"], lw=0.7, ls=(0, (3, 2)),
                       label=f"Chance ({prevalence:.2f})")
    axes[0, 1].set(xlim=(0, 1), ylim=(0, 1), xlabel="Recall", ylabel="Precision")
    axes[0, 1].legend(loc="lower left", title="AUPRC")
    for index, ax in enumerate(axes[0]):
        panel_label(ax, chr(97 + index)); _boxed(ax)

    if not mechanism.empty:
        controls = mechanism[mechanism["scenario"].isin(["common_equal", "common_unequal", "opposite_direction"])]
        control_labels = ["Equal common\nnegative control", "Unequal same-direction\npositive control", "Opposite-direction\npositive control"]
        values = controls.set_index("scenario").reindex(["common_equal", "common_unequal", "opposite_direction"])
        y = values["estimate"].to_numpy(); error = np.vstack([y - values["ci95_low"], values["ci95_high"] - y])
        axes[1, 0].bar(np.arange(3), y, color=[PALETTE["green"], PALETTE["orange"], PALETTE["red"]],
                       width=0.65, yerr=error, capsize=2,
                       error_kw={"elinewidth": 0.7, "ecolor": PALETTE["gray"]})
        axes[1, 0].axhline(0.10, color=PALETTE["gray"], lw=0.7, ls=(0, (3, 2)), label="FAR limit")
        axes[1, 0].set_ylim(0, 1.08); axes[1, 0].set_ylabel("Conditional response rate")
        axes[1, 0].set_xticks(np.arange(3), control_labels)
        axes[1, 0].legend(loc="upper left")
    else:
        far = summary[summary["metric"].eq("new_false_alarm_rate")]
        axes[1, 0].bar(np.arange(len(far)), far["value"], color=PALETTE["green"])
    panel_label(axes[1, 0], "c"); _open(axes[1, 0])

    mechanisms = ["unilateral_drift", "unilateral_step", "unilateral_freeze", "unilateral_spike"]
    marker = {"unilateral_drift": "o", "unilateral_step": "s", "unilateral_freeze": "^", "unilateral_spike": "x"}
    for injection in mechanisms:
        frame = per_pair[per_pair["injection"].eq(injection)].set_index("pair_id").reindex(PAIR_ORDER)
        axes[1, 1].plot(frame["AUROC"], np.arange(len(PAIR_ORDER)), marker=marker[injection],
                        lw=0.7, ms=4, color=INJECTION_COLORS[injection], label=INJECTION_LABELS[injection])
    axes[1, 1].axvline(0.70, color=PALETTE["gray"], lw=0.7, ls=(0, (3, 2)))
    axes[1, 1].set_xlim(0.35, 1.02); axes[1, 1].set_xlabel("Per-pair AUROC")
    axes[1, 1].set_yticks(np.arange(len(PAIR_ORDER)), [_pair_label(pair) for pair in PAIR_ORDER])
    axes[1, 1].invert_yaxis()
    axes[1, 1].legend(loc="upper center", bbox_to_anchor=(0.5, -0.20),
                      ncol=2, columnspacing=0.9, frameon=False)
    panel_label(axes[1, 1], "d"); _open(axes[1, 1])
    fig.text(0.99, 0.01, "Internal injection validation; not adjudicated field accuracy",
             ha="right", va="bottom", fontsize=6.3, color=PALETTE["red"])
    fig.subplots_adjust(left=0.09, right=0.99, top=0.97, bottom=0.17)
    stem = "FigD4_5_mechanism_specificity"
    _save_publication_figure(fig, output_dir / stem)
    _write_source(source_dir, stem, {"summary": summary, "curves": curves,
                                     "per_pair_metrics": per_pair,
                                     "mechanism_controls": mechanism})


def _ablation_score(frame: pd.DataFrame, condition: str, cfg: D4Config) -> np.ndarray:
    q = frame[Q_COLUMNS].copy()
    weights = cfg.weights.copy()
    if condition == "no_deadband":
        q["Q_var"] = frame["Q_var_no_deadband"]
    elif condition.startswith("no_"):
        component = condition.removeprefix("no_")
        q = q.drop(columns=[f"Q_{component}"])
        weights.pop(component)
        total = sum(weights.values())
        weights = {key: value / total for key, value in weights.items()}
    matrix = q.to_numpy(dtype=float)
    ordered_weights = np.array([weights[column.removeprefix("Q_")] for column in q.columns])
    base = matrix @ ordered_weights
    return cfg.lambda_blend * base + (1.0 - cfg.lambda_blend) * matrix.min(axis=1)


def _mechanism_ablation(scores: pd.DataFrame, cfg: D4Config) -> pd.DataFrame:
    conditions = ["no_dist", "no_trend", "no_var", "no_cp", "no_deadband"]
    baseline = scores[scores["injection"].eq("baseline")].sort_values("window_id")
    repetitions = 600
    rng = np.random.Generator(np.random.PCG64(20260812))

    def score_by_condition(frame: pd.DataFrame, condition: str) -> np.ndarray:
        if condition == "full":
            return frame["D4_raw"].to_numpy(dtype=float)
        return _ablation_score(frame, condition, cfg)

    rows: list[dict[str, object]] = []
    for injection, label in INJECTION_LABELS.items():
        positive = scores[scores["injection"].eq(injection)].sort_values("window_id")
        if not baseline["window_id"].reset_index(drop=True).equals(
            positive["window_id"].reset_index(drop=True)
        ):
            raise ValueError(f"Unpaired injection windows for {injection}")
        n_clusters = len(baseline)
        y = np.r_[np.zeros(n_clusters, dtype=int), np.ones(n_clusters, dtype=int)]
        full_risk = 5.0 - np.r_[
            score_by_condition(baseline, "full"), score_by_condition(positive, "full")
        ]
        full_auc = float(roc_auc_score(y, full_risk))
        for condition in conditions:
            risk = 5.0 - np.r_[
                score_by_condition(baseline, condition),
                score_by_condition(positive, condition),
            ]
            point = float(roc_auc_score(y, risk) - full_auc)
            estimates = np.empty(repetitions, dtype=float)
            for iteration in range(repetitions):
                sampled = rng.integers(0, n_clusters, n_clusters)
                draw = np.r_[sampled, sampled + n_clusters]
                estimates[iteration] = (
                    roc_auc_score(y[draw], risk[draw])
                    - roc_auc_score(y[draw], full_risk[draw])
                )
            low, high = np.quantile(estimates, [0.025, 0.975])
            rows.append({
                "mechanism": label,
                "condition": condition,
                "metric": "delta_AUROC",
                "delta": point,
                "ci_low": float(low),
                "ci_high": float(high),
                "n_clusters": n_clusters,
            })

    common = scores[scores["injection"].eq("common_mode_drift")].sort_values("window_id")
    if not baseline["window_id"].reset_index(drop=True).equals(
        common["window_id"].reset_index(drop=True)
    ):
        raise ValueError("Unpaired common-mode control windows")
    n_clusters = len(baseline)
    threshold = cfg.classification["asymmetry_max"]
    full_baseline = score_by_condition(baseline, "full")
    full_common = score_by_condition(common, "full")
    full_eligible = full_baseline >= threshold
    full_far = float((full_common[full_eligible] < threshold).mean())
    for condition in conditions:
        condition_baseline = score_by_condition(baseline, condition)
        condition_common = score_by_condition(common, condition)
        condition_eligible = condition_baseline >= threshold
        condition_far = float((condition_common[condition_eligible] < threshold).mean())
        point = condition_far - full_far
        estimates = np.empty(repetitions, dtype=float)
        for iteration in range(repetitions):
            sampled = rng.integers(0, n_clusters, n_clusters)
            draw_full = full_eligible[sampled]
            draw_condition = condition_eligible[sampled]
            sampled_full_far = float((full_common[sampled][draw_full] < threshold).mean())
            sampled_condition_far = float(
                (condition_common[sampled][draw_condition] < threshold).mean()
            )
            estimates[iteration] = sampled_condition_far - sampled_full_far
        low, high = np.quantile(estimates, [0.025, 0.975])
        rows.append({
            "mechanism": "Equal common-mode control",
            "condition": condition,
            "metric": "delta_conditional_FAR",
            "delta": point,
            "ci_low": float(low),
            "ci_high": float(high),
            "n_clusters": n_clusters,
        })
    return pd.DataFrame(rows)


def figure_6_ablation_resolution(
    cfg: D4Config,
    benchmark_path: Path,
    lag_path: Path | None,
    output_dir: Path,
    source_dir: Path,
) -> None:
    scores = pd.read_excel(benchmark_path, sheet_name="injection_scores")
    delta = _mechanism_ablation(scores, cfg)
    lag = pd.read_parquet(lag_path) if lag_path and lag_path.exists() else pd.DataFrame()
    conditions = ["no_dist", "no_trend", "no_var", "no_cp", "no_deadband"]
    condition_labels = ["No distribution", "No trend", "No variability", "No change point", "No deadband"]
    fig, axes = plt.subplots(1, 3, figsize=(FIG_WIDTH_MM / 25.4, 76 / 25.4),
                             gridspec_kw={"width_ratios": [1.35, 0.92, 1.08], "wspace": 0.46})
    auc = delta[delta["metric"].eq("delta_AUROC")]
    mechanisms = list(INJECTION_LABELS.values())
    matrix = auc.pivot(index="condition", columns="mechanism", values="delta").reindex(
        index=conditions, columns=mechanisms
    )
    image = axes[0].imshow(matrix.to_numpy(), cmap="RdBu", vmin=-0.25, vmax=0.25, aspect="auto")
    for row, condition in enumerate(conditions):
        for column, mechanism in enumerate(mechanisms):
            record = auc[auc["condition"].eq(condition) & auc["mechanism"].eq(mechanism)].iloc[0]
            significant = not (record.ci_low <= 0 <= record.ci_high)
            axes[0].text(column, row, f"{record.delta:+.2f}{'*' if significant else ''}",
                         ha="center", va="center", fontsize=6.1,
                         color="white" if abs(record.delta) > 0.13 else PALETTE["black"])
    axes[0].set_xticks(np.arange(len(mechanisms)), [label.replace(" (D1-owned)", "") for label in mechanisms],
                       rotation=28, ha="right")
    axes[0].set_yticks(np.arange(len(conditions)), condition_labels)
    cbar = fig.colorbar(image, ax=axes[0], fraction=0.045, pad=0.03)
    cbar.set_label("Delta AUROC vs full")
    axes[0].text(0.0, -0.35, "* 95% cluster-bootstrap CI excludes zero",
                 transform=axes[0].transAxes, fontsize=5.8, color=PALETTE["gray"])
    panel_label(axes[0], "a"); _boxed(axes[0])

    far = delta[delta["metric"].eq("delta_conditional_FAR")].set_index("condition").reindex(conditions)
    y = np.arange(len(conditions))
    axes[1].hlines(y, far["ci_low"], far["ci_high"], color=PALETTE["mid_gray"], lw=1.2)
    axes[1].scatter(far["delta"], y, color=[PALETTE["red"] if v > 0 else PALETTE["green"] for v in far["delta"]], s=24)
    axes[1].axvline(0, color=PALETTE["black"], lw=0.7)
    axes[1].set_yticks(y, [])
    axes[1].invert_yaxis(); axes[1].set_xlabel("Delta equal-common conditional FAR")
    panel_label(axes[1], "b"); _open(axes[1])

    if not lag.empty:
        for variable, color, marker in [("DO", PALETTE["blue"], "o"), ("ORP", PALETTE["orange"], "s")]:
            frame = lag[lag["variable"].eq(variable)].sort_values("lag_minutes")
            axes[2].plot(frame["lag_minutes"], frame["mean_Qcp"], color=color, marker=marker,
                         ms=4, lw=KEY_LINE_WIDTH, label=variable)
        axes[2].axvspan(0, 30, color=PALETTE["mid_gray"], alpha=0.18, label="Sub-hour sensitivity only")
        axes[2].axvline(60, color=PALETTE["gray"], lw=0.7, ls=(0, (3, 2)), label="Hourly scale")
        axes[2].text(0.98, 0.05, "Severity monotonicity rho = 0",
                     transform=axes[2].transAxes, ha="right", va="bottom", fontsize=6.3,
                     color=PALETTE["red"])
    else:
        axes[2].text(0.5, 0.5, "Lag-response source unavailable", ha="center", va="center",
                     transform=axes[2].transAxes)
    axes[2].set_xlabel("Injected change-point lag (min)")
    axes[2].set_ylabel("Mean Qcp")
    axes[2].set_ylim(1, 5)
    axes[2].legend(loc="upper left")
    panel_label(axes[2], "c"); _open(axes[2])
    fig.subplots_adjust(left=0.10, right=0.99, top=0.94, bottom=0.21)
    stem = "FigD4_6_ablation_and_lag_resolution"
    _save_publication_figure(fig, output_dir / stem)
    _write_source(source_dir, stem, {"ablation_delta": delta, "lag_response": lag})


def supplementary_1_all_pairs(
    cfg: D4Config,
    main: pd.DataFrame,
    events: pd.DataFrame,
    output_dir: Path,
    source_dir: Path,
) -> None:
    residuals = pd.read_parquet(cfg.paths["residuals"]).resample("6h").median()
    fig, axes = plt.subplots(len(cfg.pairs), 1, figsize=(FIG_WIDTH_MM / 25.4, 178 / 25.4), sharex=True)
    source = []
    for index, (ax, pair) in enumerate(zip(axes, cfg.pairs)):
        pooled = pd.concat([residuals[pair.target], residuals[pair.reference]])
        scale = max(float((pooled - pooled.median()).abs().median() * 1.4826), cfg.deadband[pair.variable])
        target = residuals[pair.target] / scale; reference = residuals[pair.reference] / scale
        ax.plot(residuals.index, target, color=PALETTE["blue"], lw=0.75,
                label="Pool 1" if index == 0 else None)
        ax.plot(residuals.index, reference, color=PALETTE["orange"], lw=0.75,
                label="Pool 2" if index == 0 else None)
        pair_events = events[events["pair_id"].eq(pair.pair_id)]
        for event in pair_events.itertuples(index=False):
            ax.axvspan(event.start_ts, event.end_ts, color=PALETTE["red"], alpha=0.06, lw=0)
        ax.axhline(0, color=PALETTE["light_gray"], lw=0.45, zorder=0)
        ax.set_ylabel(_pair_label(pair.pair_id), rotation=0, ha="right", va="center", labelpad=22)
        panel_label(ax, chr(97 + index)); _open(ax)
        source.append(pd.DataFrame({"timestamp": residuals.index, "pair_id": pair.pair_id,
                                    "target_robust_z": target, "reference_robust_z": reference}))
    axes[0].legend(loc="lower right", ncol=2)
    axes[-1].set_xlabel("Date")
    axes[-1].xaxis.set_major_locator(mdates.MonthLocator(interval=2))
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    fig.text(0.012, 0.5, "De-periodised residual (pair-specific robust z)", rotation=90,
             ha="left", va="center", fontsize=7)
    fig.subplots_adjust(left=0.17, right=0.99, top=0.98, bottom=0.08, hspace=0.18)
    stem = "FigS1_all_pair_residual_trajectories"
    _save_publication_figure(fig, output_dir / stem)
    _write_source(source_dir, stem, {"six_hour_residuals": pd.concat(source, ignore_index=True),
                                     "formal_events": events})


def supplementary_2_trend_concordance(
    main: pd.DataFrame,
    raw: pd.DataFrame,
    output_dir: Path,
    source_dir: Path,
) -> None:
    merged = raw.merge(main[["timestamp", "pair_id", "usable_for_D4"]], on=["timestamp", "pair_id"], how="left")
    before_count = len(merged)
    complete = merged[["beta_target", "beta_reference"]].notna().all(axis=1)
    valid = merged[merged["usable_for_D4"].fillna(False) & complete].copy()
    after_count = len(valid)
    rows = []
    for pair in _pair_order(valid):
        frame = valid[valid["pair_id"].eq(pair)]
        rho = frame[["beta_target", "beta_reference"]].corr(method="spearman").iloc[0, 1]
        delta = frame["beta_target"] - frame["beta_reference"]
        low, high = _week_block_interval(frame.assign(abs_delta=delta.abs()), "abs_delta", lambda x: x.median())
        rows.append({"pair_id": pair, "spearman_rho": rho,
                     "median_abs_slope_difference": float(delta.abs().median()),
                     "ci_low": low, "ci_high": high, "n_evaluable_windows": len(frame)})
    summary = pd.DataFrame(rows)
    fig, axes = plt.subplots(1, 2, figsize=(FIG_WIDTH_MM / 25.4, 72 / 25.4), gridspec_kw={"wspace": 0.38})
    y = np.arange(len(summary))
    axes[0].scatter(summary["spearman_rho"], y, color=PALETTE["blue"], s=25)
    axes[0].axvline(0, color=PALETTE["gray"], lw=0.7)
    axes[0].set_xlim(-1, 1); axes[0].set_xlabel("Spearman slope concordance")
    axes[0].set_yticks(y, [_pair_label(pair) for pair in summary["pair_id"]]); axes[0].invert_yaxis()
    panel_label(axes[0], "a"); _open(axes[0])
    value = summary["median_abs_slope_difference"].to_numpy()
    error = np.vstack([value - summary["ci_low"], summary["ci_high"] - value])
    axes[1].errorbar(value, y, xerr=error, fmt="o", color=PALETTE["orange"], capsize=2, elinewidth=0.8)
    axes[1].set_xlabel("Median absolute slope difference")
    axes[1].set_yticks(y, [_pair_label(pair) for pair in summary["pair_id"]]); axes[1].invert_yaxis()
    panel_label(axes[1], "b"); _open(axes[1])
    fig.subplots_adjust(left=0.12, right=0.99, top=0.94, bottom=0.18)
    stem = "FigS2_trend_concordance"
    _save_publication_figure(fig, output_dir / stem)
    _write_source(source_dir, stem, {"pair_summary": summary, "evaluable_windows": valid})


def supplementary_3_integrity(
    integration_path: Path,
    output_dir: Path,
    source_dir: Path,
) -> None:
    frame = pd.read_parquet(integration_path)
    evaluable = frame[frame["finalization_allowed"]].copy()
    delta = evaluable["D4_forDQR"] - evaluable["D4_raw"]
    fig, axes = plt.subplots(1, 2, figsize=(FIG_WIDTH_MM / 25.4, 65 / 25.4), gridspec_kw={"wspace": 0.38})
    axes[0].hist(delta, bins=np.linspace(-0.05, 0.05, 21), color=PALETTE["green"], edgecolor="white")
    axes[0].set_xlabel("D4 final - D4 raw"); axes[0].set_ylabel("Finalized windows")
    axes[0].text(0.98, 0.95, f"max |delta| = {delta.abs().max():.1f}", transform=axes[0].transAxes,
                 ha="right", va="top")
    panel_label(axes[0], "a"); _open(axes[0])
    counts = frame["integration_status"].value_counts()
    axes[1].barh(np.arange(len(counts)), counts, color=PALETTE["blue"])
    axes[1].set_yticks(np.arange(len(counts)), [label.replace("_", " ") for label in counts.index])
    axes[1].invert_yaxis(); axes[1].set_xlabel("Windows")
    axes[1].set_title("D1/D5 context cannot rewrite D4 raw", loc="left", color=PALETTE["red"])
    panel_label(axes[1], "b"); _open(axes[1])
    fig.subplots_adjust(left=0.11, right=0.99, top=0.93, bottom=0.20)
    stem = "FigS3_numeric_independence_audit"
    _save_publication_figure(fig, output_dir / stem)
    _write_source(source_dir, stem, {"integrity": evaluable[["timestamp", "pair_id", "D4_raw", "D4_forDQR", "D4_numeric_adjustment"]],
                                     "status_counts": counts.rename_axis("integration_status").reset_index(name="n_windows")})


def make_all_figures(cfg: D4Config, data_dir: Path, output_dir: Path) -> None:
    configure_style()
    output_dir.mkdir(parents=True, exist_ok=True)
    source_dir = output_dir.parent / "figure_source_data"
    source_dir.mkdir(parents=True, exist_ok=True)
    main = pd.read_excel(data_dir / "D4_main_scores.xlsx", sheet_name="main_scores")
    main["timestamp"] = pd.to_datetime(main["timestamp"])
    raw = pd.read_excel(data_dir / "D4_detector_outputs_raw.xlsx", sheet_name="detector_outputs")
    raw["timestamp"] = pd.to_datetime(raw["timestamp"])
    events = pd.read_excel(data_dir / "D4_event_windows.xlsx", sheet_name="events")
    events[["start_ts", "end_ts"]] = events[["start_ts", "end_ts"]].apply(pd.to_datetime)
    params = pd.read_excel(data_dir / "D4_mapping_params.xlsx", sheet_name="public_quantiles")
    project_root = Path(__file__).resolve().parents[3]
    confirmatory = project_root / "outputs" / "confirmatory" / "D1D5V20-854e66de7e6b"
    integration = output_dir.parent / "integration" / "D4_D5_final_arbitration.parquet"

    figure_1_framework(cfg, params, output_dir, source_dir)
    figure_2_pair_profile(cfg, main, params, output_dir, source_dir)
    figure_3_burden_coverage_calibration(main, params, output_dir, source_dir)
    figure_4_field_cases(cfg, main, events, output_dir, source_dir)
    figure_5_mechanism_validation(
        data_dir / "D4_benchmark_results.xlsx",
        confirmatory / "D4_mechanism_summary.parquet",
        output_dir, source_dir,
    )
    figure_6_ablation_resolution(
        cfg,
        data_dir / "D4_benchmark_results.xlsx",
        confirmatory / "D4_lag_response.parquet",
        output_dir, source_dir,
    )
    supplementary_1_all_pairs(cfg, main, events, output_dir, source_dir)
    supplementary_2_trend_concordance(main, raw, output_dir, source_dir)
    supplementary_3_integrity(integration, output_dir, source_dir)
