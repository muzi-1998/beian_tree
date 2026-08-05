"""Nature-style confirmatory figures for the D2 strict/sensitive release."""
from __future__ import annotations

import pickle
import warnings
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


plt.rcParams["font.family"] = "sans-serif"
plt.rcParams["font.sans-serif"] = ["Arial", "Helvetica", "DejaVu Sans", "Liberation Sans"]
plt.rcParams['svg.fonttype'] = 'none'
mpl.rcParams.update({
    "svg.fonttype": "none",
    "pdf.fonttype": 42,
    "font.size": 7,
    "axes.linewidth": 0.8,
    "axes.titlesize": 8,
    "axes.labelsize": 7,
    "xtick.labelsize": 6.5,
    "ytick.labelsize": 6.5,
    "legend.fontsize": 6.5,
    "legend.frameon": False,
})


ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
VALIDATION = ROOT / "artifacts" / "validation"
DATA = ROOT / "artifacts" / "data"
FIGURES = ROOT / "artifacts" / "figures"
FIGURES.mkdir(parents=True, exist_ok=True)

COLORS = {
    "blue": "#0F4D92",
    "blue_light": "#A8C8E8",
    "teal": "#42949E",
    "orange": "#E07B39",
    "red": "#B64342",
    "red_light": "#E9A6A1",
    "violet": "#9A4D8E",
    "grey": "#767676",
    "grey_light": "#D8D8D8",
    "black": "#272727",
    "green": "#2E7D32",
}
PHASE_LABELS = {
    "development": "Development",
    "internal_validation": "Internal validation",
    "terminal_test": "Terminal test",
}
METRIC_COLORS = {
    "Q_TI": COLORS["blue"],
    "Q_GS": COLORS["orange"],
    "Q_HA": COLORS["violet"],
    "D2_total": COLORS["black"],
}


def style(ax, full_frame: bool = False) -> None:
    ax.tick_params(axis="both", which="both", direction="out", length=3.2, width=0.8)
    for spine in ax.spines.values():
        spine.set_linewidth(0.8)
    if not full_frame:
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)


def panel(ax, letter: str, *, x: float = -0.10, y: float = 1.06) -> None:
    ax.text(x, y, f"({letter})", transform=ax.transAxes,
            ha="right", va="bottom", fontsize=8, fontweight="bold",
            clip_on=False)


def save(fig: plt.Figure, stem: str) -> None:
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="This figure includes Axes that are not compatible with tight_layout",
        )
        fig.tight_layout(pad=1.1)
    for suffix in ("svg", "pdf", "png", "tiff"):
        fig.savefig(FIGURES / f"{stem}.{suffix}", dpi=600, bbox_inches="tight")
    plt.close(fig)
    print(f"[saved] {stem}.svg/.pdf/.png/.tiff")


def _read_validation(name: str) -> pd.DataFrame:
    return pd.read_parquet(VALIDATION / name)


def figure13_process_floor() -> None:
    workbook = DATA / "D2_process_floor_casebook.xlsx"
    challenge = pd.read_excel(workbook, sheet_name="challenge_timeseries")
    observed = pd.read_excel(workbook, sheet_name="observed_channels")
    threshold = _read_validation("D2_threshold_sensitivity.parquet")
    floor_sensitivity = threshold.loc[
        threshold["parameter"].eq("process_floor_threshold_mg_L")
    ].sort_values("setting")

    fig = plt.figure(figsize=(7.2, 4.6))
    grid = fig.add_gridspec(2, 2, height_ratios=(1.35, 1.0), hspace=0.48, wspace=0.36)
    ax_a = fig.add_subplot(grid[0, :])
    ax_b = fig.add_subplot(grid[1, 0])
    ax_c = fig.add_subplot(grid[1, 1])

    scenarios = [
        ("true_low_oxygen_floor", "True low-DO floor", COLORS["blue"]),
        ("digital_lock", "Digital lock", COLORS["red"]),
        ("low_oxygen_small_fluctuation", "Low-DO fluctuation", COLORS["teal"]),
        ("response_recovery_after_floor", "Recovery after floor", COLORS["orange"]),
    ]
    ax_a.axhspan(0, 0.20, color=COLORS["blue_light"], alpha=0.22,
                 label="Process-floor range")
    for scenario, label, color in scenarios:
        sub = challenge.loc[challenge["scenario"].eq(scenario)].copy()
        sub["minute"] = np.arange(len(sub))
        ax_a.plot(sub["minute"], sub["value"], color=color, lw=1.15, label=label)
        flagged = sub["qfa_unavailable"].astype(bool)
        ax_a.scatter(sub.loc[flagged, "minute"], sub.loc[flagged, "value"],
                     marker="x", s=12, lw=0.7, color=COLORS["red"], zorder=4)
    ax_a.set(xlabel="Elapsed time (min)", ylabel="DO (mg L$^{-1}$)",
             title="Mechanism challenge: process floor is distinct from hard unavailability")
    ax_a.set_ylim(-0.02, 0.47)
    ax_a.legend(ncol=3, loc="upper left", handlelength=1.8, columnspacing=0.9)
    style(ax_a)
    panel(ax_a, "a")

    metrics = [
        ("floor_occupancy_pct", "Floor occupancy", COLORS["blue_light"]),
        ("resolution_limited_pct", "Resolution limited", COLORS["teal"]),
        ("sensor_freeze_pct", "Hard freeze", COLORS["red"]),
        ("qfa_unavailable_pct", "Hard unavailable", COLORS["orange"]),
    ]
    offsets = (-0.18, -0.06, 0.06, 0.18)
    for (column, label, color), offset in zip(metrics, offsets):
        y = np.arange(len(observed)) + offset
        values = observed[column].clip(lower=0.005)
        ax_b.scatter(values, y, color=color, edgecolor=COLORS["black"],
                     linewidth=0.35, s=28, label=label, zorder=3)
    ax_b.set_xscale("log")
    ax_b.set_xlim(0.005, 130)
    ax_b.set_yticks(range(len(observed)))
    ax_b.set_yticklabels(observed["sensor_id"])
    ax_b.set_xlabel("Observed time coverage (%)")
    ax_b.set_title("Orders-of-magnitude evidence separation")
    ax_b.legend(loc="upper center", bbox_to_anchor=(0.5, -0.30), ncol=2,
                handletextpad=0.3, columnspacing=0.8)
    style(ax_b)
    panel(ax_b, "b")

    x = floor_sensitivity["setting"].to_numpy()
    y = floor_sensitivity["diagnostic_fraction"].to_numpy() * 100
    ax_c.plot(x, y, color=COLORS["blue"], marker="o", ms=4, lw=1.2)
    for index, (xi, yi) in enumerate(zip(x, y)):
        if index == 0:
            horizontal_alignment = "left"
        elif index == len(x) - 1:
            horizontal_alignment = "right"
        else:
            horizontal_alignment = "center"
        ax_c.text(
            xi,
            yi + 1.2,
            f"{yi:.1f}%",
            ha=horizontal_alignment,
            va="bottom",
            fontsize=6.5,
        )
    ax_c.set(xlabel="Diagnostic floor threshold (mg L$^{-1}$)",
             ylabel="Floor occupancy (%)",
             title="Threshold changes interpretation, not production QHA")
    ax_c.set_ylim(0, 100)
    ax_c.text(0.03, 0.08, "Production score unchanged",
              transform=ax_c.transAxes, color=COLORS["green"], fontsize=6.5,
              bbox={"facecolor": "white", "edgecolor": COLORS["grey_light"], "alpha": 0.85})
    style(ax_c)
    panel(ax_c, "c")
    save(fig, "D2_Fig13_process_floor_contract")


def figure14_robustness() -> None:
    summary = _read_validation("D2_weight_lambda_summary.parquet")
    thresholds = _read_validation("D2_threshold_sensitivity.parquet")
    order = ["equal", "primary_qfa_040", "qfa_enhanced_050"]
    fig, axes = plt.subplots(2, 2, figsize=(7.2, 5.1))
    ax_a, ax_b, ax_c, ax_d = axes.ravel()

    matrix = summary.pivot(index="weight_id", columns="lambda", values="low_hour_jaccard").reindex(order)
    image = ax_a.imshow(matrix.to_numpy(), vmin=0.90, vmax=1.00, cmap="Blues", aspect="auto")
    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            value = matrix.iloc[i, j]
            ax_a.text(j, i, f"{value:.3f}", ha="center", va="center",
                      color="white" if value > 0.96 else COLORS["black"], fontsize=6.5)
    ax_a.set_xticks(range(matrix.shape[1]), [f"λ={x:.1f}" for x in matrix.columns])
    ax_a.set_yticks(range(3), ["Equal", "QFA 0.40", "QFA 0.50"])
    ax_a.set_title("Low-score-hour agreement with primary model")
    colorbar = fig.colorbar(image, ax=ax_a, fraction=0.045, pad=0.03)
    colorbar.set_label("Jaccard index")
    style(ax_a, full_frame=True)
    panel(ax_a, "a")

    plot = summary.sort_values(["weight_id", "lambda"]).reset_index(drop=True)
    weight_labels = {
        "equal": "Equal",
        "primary_qfa_040": "QFA 0.40",
        "qfa_enhanced_050": "QFA 0.50",
    }
    labels = [
        f"{weight_labels[row['weight_id']]}, λ={row['lambda']:.1f}"
        for _, row in plot.iterrows()
    ]
    y = np.arange(len(plot))[::-1]
    colors = [COLORS["red"] if v == "primary_qfa_040__lambda_070" else COLORS["blue"]
              for v in plot["variant_id"]]
    for yi, (_, row), color in zip(y, plot.iterrows(), colors):
        ax_b.plot([row["low_event_ci95_low"], row["low_event_ci95_high"]], [yi, yi], color=color, lw=1.0)
        ax_b.plot(row["low_event_jaccard"], yi, "o", color=color, ms=3.6)
    ax_b.set_yticks(y, labels)
    ax_b.set_xlim(0.68, 1.02)
    ax_b.axvline(1, color=COLORS["grey"], ls=":", lw=0.7)
    ax_b.set_xlabel("Event Jaccard (sensor-month cluster 95% CI)")
    ax_b.set_title("Event boundaries are stable except at extreme λ")
    style(ax_b)
    panel(ax_b, "b")

    for yi, (_, row), color in zip(y, plot.iterrows(), colors):
        ax_c.plot([row["channel_rank_ci95_low"], row["channel_rank_ci95_high"]], [yi, yi], color=color, lw=1.0)
        ax_c.plot(row["channel_rank_spearman"], yi, "o", color=color, ms=3.6)
    ax_c.set_yticks(y, labels)
    ax_c.set_xlim(0.965, 1.002)
    ax_c.axvline(1, color=COLORS["grey"], ls=":", lw=0.7)
    ax_c.set_xlabel("Spearman ρ (sensor-month cluster 95% CI)")
    ax_c.set_title("Channel ranking is invariant")
    style(ax_c)
    panel(ax_c, "c")

    for parameter, color, label in (
        ("Q_TI_break_multiplier", COLORS["blue"], "QTI"),
        ("Q_GS_break_multiplier", COLORS["orange"], "QGS"),
    ):
        sub = thresholds.loc[thresholds["parameter"].eq(parameter)].sort_values("setting")
        ax_d.plot(sub["setting"], sub["low_hour_rate"] * 100,
                  marker="o", ms=4, lw=1.2, color=color, label=label)
    ax_d.set(xlabel="Prespecified break multiplier", ylabel="Low-score hours (%)",
             title="Mapping perturbation has negligible influence")
    ax_d.legend(loc="best")
    style(ax_d)
    panel(ax_d, "d")
    save(fig, "D2_Fig14_aggregation_robustness")


def figure15_tail_risk() -> None:
    summary = _read_validation("D2_distribution_summary.parquet")
    daily = _read_validation("D2_daily_summary.parquet")
    effects = _read_validation("D2_analyte_effects.parquet")
    dates = pd.to_datetime(daily["date"])
    daily["phase"] = np.select(
        [dates.le("2025-12-31"), dates.le("2026-02-21")],
        ["development", "internal_validation"],
        default="terminal_test",
    )
    phases = list(PHASE_LABELS)
    fig, axes = plt.subplots(2, 2, figsize=(7.2, 5.0))
    ax_a, ax_b, ax_c, ax_d = axes.ravel()

    d2_summary = summary.loc[summary["metric"].eq("D2_total")]
    x = np.arange(len(phases))
    for analyte, color, offset in (("DO", COLORS["blue"], -0.12), ("ORP", COLORS["red"], 0.12)):
        med, low, high = [], [], []
        for phase in phases:
            values = d2_summary.loc[
                d2_summary["phase"].eq(phase) & d2_summary["analyte"].eq(analyte),
                "low_rate_lt3",
            ] * 100
            med.append(values.median())
            low.append(values.median() - values.quantile(0.25))
            high.append(values.quantile(0.75) - values.median())
        ax_a.errorbar(x + offset, med, yerr=np.vstack([low, high]), fmt="o",
                      color=color, capsize=2, lw=0.9, ms=4, label=analyte)
    ax_a.set_xticks(x, [PHASE_LABELS[p].replace(" ", "\n") for p in phases])
    ax_a.set_ylabel("D2 < 3 hours (%)")
    ax_a.set_title("Low-tail burden across locked study phases")
    ax_a.legend(loc="best")
    style(ax_a)
    panel(ax_a, "a")

    metric_order = ["Q_TI", "Q_GS", "Q_FA", "D2_total"]
    width = 0.34
    for j, (analyte, edge) in enumerate((("DO", COLORS["blue"]), ("ORP", COLORS["red"]))):
        values = []
        for metric in metric_order:
            values.append(summary.loc[
                summary["analyte"].eq(analyte) & summary["metric"].eq(metric),
                "low_rate_lt3",
            ].mean() * 100)
        ax_b.bar(np.arange(4) + (j - 0.5) * width, values, width=width,
                 facecolor="white", edgecolor=edge, linewidth=1.1, label=analyte)
    ax_b.set_xticks(range(4), ["QTI", "QGS", "QFA", "D2"])
    ax_b.set_ylabel("Hours below 3 (%)")
    ax_b.set_title("Subscore-specific low-tail frequency")
    ax_b.legend(loc="best")
    style(ax_b)
    panel(ax_b, "b")

    event_day = np.zeros((2, len(phases)))
    for i, analyte in enumerate(("DO", "ORP")):
        for j, phase in enumerate(phases):
            values = daily.loc[
                daily["phase"].eq(phase) & daily["analyte"].eq(analyte)
                & daily["metric"].eq("D2_total"), "daily_min",
            ]
            valid = values.loc[values.notna()]
            event_day[i, j] = valid.lt(3).mean() * 100
    vmax = max(float(event_day.max()), 1.0)
    ax_c.imshow(event_day, cmap="Blues", vmin=0, vmax=vmax, aspect="auto")
    for i in range(event_day.shape[0]):
        for j in range(event_day.shape[1]):
            value = event_day[i, j]
            ax_c.text(j, i, f"{value:.1f}%", ha="center", va="center",
                      color="white" if value > 0.60 * vmax else COLORS["black"], fontsize=7)
    ax_c.set_xticks(range(len(phases)), [PHASE_LABELS[p].replace(" ", "\n") for p in phases])
    ax_c.set_yticks(range(2), ["DO", "ORP"])
    ax_c.set_title("Sensor-days containing at least one D2 < 3 hour")
    style(ax_c, full_frame=True)
    panel(ax_c, "c")

    effect_plot = effects.set_index("metric").loc[metric_order].reset_index()
    y = np.arange(len(effect_plot))[::-1]
    for yi, row in zip(y, effect_plot.itertuples()):
        ax_d.plot([row.block_ci95_low, row.block_ci95_high], [yi, yi],
                  color=METRIC_COLORS[row.metric], lw=1.1)
        ax_d.plot(row.ORP_minus_DO_mean, yi, "o", color=METRIC_COLORS[row.metric], ms=4)
    ax_d.axvline(0, color=COLORS["grey"], ls="--", lw=0.8)
    ax_d.set_yticks(y, ["QTI", "QGS", "QFA", "D2"])
    ax_d.set_xlabel("ORP − DO mean score (month-block 95% CI)")
    ax_d.set_title("No material analyte-specific score penalty")
    style(ax_d)
    panel(ax_d, "d")
    save(fig, "D2_Fig15_low_tail_reporting")


def figure16_construct_separation() -> None:
    concordance = _read_validation("D2_d1d2_concordance.parquet").iloc[0]
    pairs = _read_validation("D2_d1d2_event_pairs.parquet")
    null = _read_validation("D2_d1d2_circular_null.parquet")
    d2 = pd.read_excel(DATA / "D2_freeze_availability_events.xlsx")
    d1 = pd.read_excel(PROJECT / "D1 Sensor health" / "outputs" / "data" / "D1_event_windows.xlsx",
                       sheet_name="all_events")

    fig = plt.figure(figsize=(7.2, 4.5))
    grid = fig.add_gridspec(2, 2, height_ratios=(1.0, 1.15), hspace=0.48, wspace=0.38)
    ax_a = fig.add_subplot(grid[0, 0])
    ax_b = fig.add_subplot(grid[0, 1])
    ax_c = fig.add_subplot(grid[1, :])

    counts = [concordance["D1_events"], concordance["D2_hard_availability_events"],
              concordance["matched_event_pairs"]]
    bars = ax_a.bar([0, 1, 2], counts,
                    color=[COLORS["orange"], COLORS["blue"], COLORS["red"]], width=0.66)
    ax_a.set_xticks([0, 1, 2], ["D1 health", "D2 hard\navailability", "Matched"])
    ax_a.set_ylabel("Number of events")
    ax_a.set_title("Only five event pairs match one-to-one")
    for bar, value in zip(bars, counts):
        ax_a.text(bar.get_x() + bar.get_width() / 2, value + 3, f"{int(value)}",
                  ha="center", va="bottom", fontsize=7)
    style(ax_a)
    panel(ax_a, "a")

    sensors = sorted(set(d1["sensor_id"]) | set(d2["sensor_id"]))
    d1_counts = d1["sensor_id"].value_counts().reindex(sensors, fill_value=0)
    d2_counts = d2["sensor_id"].value_counts().reindex(sensors, fill_value=0)
    match_counts = pairs["sensor_id"].value_counts().reindex(sensors, fill_value=0)
    y = np.arange(len(sensors))
    ax_b.barh(y + 0.17, d1_counts, height=0.30, color=COLORS["orange"], label="D1")
    ax_b.barh(y - 0.17, d2_counts, height=0.30, color=COLORS["blue"], label="D2")
    ax_b.scatter(match_counts, y, marker="|", s=45, color=COLORS["red"], label="Matched", zorder=4)
    ax_b.set_yticks(y, sensors)
    ax_b.set_xlabel("Events per sensor")
    ax_b.set_title("Separation persists across channels")
    ax_b.legend(loc="lower right", ncol=3, handlelength=1.0)
    style(ax_b)
    panel(ax_b, "b")

    values = null["duration_jaccard"].to_numpy()
    ax_c.hist(values, bins=28, color=COLORS["grey_light"], edgecolor="white", linewidth=0.4)
    observed = float(concordance["duration_jaccard_observed"])
    ax_c.axvline(observed, color=COLORS["red"], lw=1.5,
                 label=f"Observed = {observed:.3f}")
    ax_c.axvline(float(concordance["duration_jaccard_null_median"]),
                 color=COLORS["black"], lw=1.0, ls="--", label="Null median")
    ax_c.set(xlabel="Duration Jaccard after sensor-specific circular shift",
             ylabel="Null replicates",
             title="Temporal overlap exceeds chance but remains small in absolute magnitude")
    ax_c.text(0.99, 0.92,
              f"Null mean = {concordance['duration_jaccard_null_mean']:.4f}\n"
              f"Monte Carlo P = {concordance['circular_shift_p_upper']:.4f}",
              transform=ax_c.transAxes, ha="right", va="top",
              bbox={"facecolor": "white", "edgecolor": COLORS["grey_light"], "alpha": 0.88})
    ax_c.legend(loc="upper left")
    style(ax_c)
    panel(ax_c, "c")
    save(fig, "D2_Fig16_d1_d2_construct_separation")


def _continuous_piecewise(x: np.ndarray, breaks: list[float]) -> np.ndarray:
    score = np.ones_like(x, dtype=float)
    b0, b1, b2, b3, b4 = breaks
    score[x <= b0] = 5.0
    for high, low, left, right in (
        (5, 4, b0, b1), (4, 3, b1, b2),
        (3, 2, b2, b3), (2, 1, b3, b4),
    ):
        mask = x.gt(left) & x.le(right) if isinstance(x, pd.Series) else ((x > left) & (x <= right))
        score[mask] = high - (high - low) * (x[mask] - left) / (right - left)
    score[x > b4] = 1.0
    return score


def figure17_timestamp_qti(state: dict) -> None:
    audit = state["timestamp_audit"]
    summary = audit["summary"].copy()
    qti = _read_validation("D2_qti_component_audit.parquet")
    mapping = state["mapping_df"]

    event_cols = ["true_irregular_count", "duplicate_count", "out_of_order_count", "gap_recovery_count"]
    event_labels = ["True irregular", "Duplicate", "Out of order", "Gap recovery"]
    source_order = [s for s in ("DO", "ORP", "FLOW") if s in set(summary["source"])]
    event_table = summary.set_index("source").loc[source_order, event_cols]

    weights = pd.DataFrame({
        "component": ["Missing", "True irregular", "Duplicate", "Out of order"],
        "weight": [0.65, 0.25, 0.05, 0.05],
    })
    deficit_cols = [
        "weighted_deficit_missing", "weighted_deficit_true_irregular",
        "weighted_deficit_duplicate", "weighted_deficit_out_of_order",
    ]
    deficit = qti.groupby("analyte", as_index=False)[deficit_cols].mean()

    fig, axes = plt.subplots(2, 2, figsize=(7.2, 4.8))
    fig.subplots_adjust(hspace=0.52, wspace=0.36)
    ax_a, ax_b, ax_c, ax_d = axes.ravel()

    x = np.arange(len(source_order))
    width = 0.18
    event_colors = [COLORS["teal"], COLORS["orange"], COLORS["violet"], COLORS["red"]]
    for i, (column, label, color) in enumerate(zip(event_cols, event_labels, event_colors)):
        values = event_table[column].to_numpy(dtype=float)
        bars = ax_a.bar(x + (i - 1.5) * width, values, width, color=color, label=label)
        ax_a.bar_label(bars, fmt="%.0f", fontsize=5.8, padding=1)
    ax_a.set_xticks(x, source_order)
    ax_a.set_ylabel("Raw-source event count")
    ax_a.set_ylim(0, max(32, float(event_table.to_numpy().max()) * 1.18))
    ax_a.set_title("Pre-alignment timestamp audit", pad=4)
    ax_a.legend(loc="upper left", ncol=2, columnspacing=0.8, handlelength=1.1)
    style(ax_a)
    panel(ax_a, "a")

    bars = ax_b.barh(weights["component"], weights["weight"],
                     color=[COLORS["blue"], COLORS["teal"], COLORS["orange"], COLORS["violet"]])
    ax_b.bar_label(bars, labels=[f"{value:.0%}" for value in weights["weight"]],
                   fontsize=6, padding=2)
    ax_b.set_xlim(0, 0.73)
    ax_b.set_xlabel("Prespecified Q$_{TI}$ weight")
    ax_b.set_title("Conditionally normalised evidence weights", pad=4)
    ax_b.invert_yaxis()
    style(ax_b)
    panel(ax_b, "b")

    components = ["Missing", "True irregular", "Duplicate", "Out of order"]
    component_colors = [COLORS["blue"], COLORS["teal"], COLORS["orange"], COLORS["violet"]]
    analytes = deficit["analyte"].tolist()
    x = np.arange(len(analytes))
    for i, (column, label, color) in enumerate(zip(deficit_cols, components, component_colors)):
        ax_c.bar(x + (i - 1.5) * width, deficit[column], width, color=color, label=label)
    ax_c.set_xticks(x, analytes)
    ax_c.set_ylabel("Mean weighted score deficit")
    ax_c.set_title("Attribution of Q$_{TI}$ loss", pad=4)
    ax_c.legend(loc="upper right", ncol=2, columnspacing=0.7, handlelength=1.0)
    style(ax_c)
    panel(ax_c, "c")

    qti_rows = mapping.loc[
        mapping["subscore_name"].eq("Q_TI")
        & mapping["mapping_type"].eq("piecewise_linear")
    ]
    curve_data = []
    curve_labels = {
        "missing_rate": "Missing",
        "true_irregular_rate": "True irregular",
        "duplicate_rate": "Duplicate",
        "out_of_order_rate": "Out of order",
    }
    line_styles = ["-", "--", "-.", ":"]
    for (_, row), line_style, color in zip(qti_rows.iterrows(), line_styles, component_colors):
        breaks = [float(row[f"break_{i}"]) for i in range(1, 6)]
        values = np.linspace(0, breaks[-1] * 1.12, 300)
        scores = _continuous_piecewise(values, breaks)
        label = curve_labels.get(row["input_metric"], row["input_metric"])
        ax_d.plot(values * 100, scores, color=color, linestyle=line_style, linewidth=1.2, label=label)
        curve_data.extend({"metric": label, "rate": v, "score": s} for v, s in zip(values, scores))
    ax_d.set_xlabel("Observed rate (%)")
    ax_d.set_ylabel("Component score")
    ax_d.set_yticks([1, 2, 3, 4, 5])
    ax_d.set_ylim(0.9, 5.1)
    ax_d.set_title("Continuous tail mapping", pad=4)
    ax_d.legend(loc="upper right")
    style(ax_d)
    panel(ax_d, "d")

    source_book = VALIDATION / "D2_Fig17_timestamp_qti_source_data.xlsx"
    with pd.ExcelWriter(source_book, engine="openpyxl") as writer:
        event_table.reset_index().to_excel(writer, sheet_name="panel_a_events", index=False)
        weights.to_excel(writer, sheet_name="panel_b_weights", index=False)
        deficit.to_excel(writer, sheet_name="panel_c_deficits", index=False)
        pd.DataFrame(curve_data).to_excel(writer, sheet_name="panel_d_mapping", index=False)
    save(fig, "D2_Fig17_timestamp_qti_audit")


def figure14_evidence_redundancy() -> None:
    correlation = _read_validation("D2_evidence_redundancy_correlation.parquet")
    ablation = _read_validation("D2_evidence_redundancy_ablation.parquet")
    hierarchy = _read_validation("D2_evidence_hierarchy.parquet")
    order = ["strict_production", "without_QTI_missing", "without_QGS", "without_QHA"]
    labels = ["Strict", "QTI without\nmissing", "No QGS", "No QHA"]
    ablation = ablation.set_index("variant_id").loc[order].reset_index()

    fig = plt.figure(figsize=(7.2, 4.6))
    grid = fig.add_gridspec(2, 2, height_ratios=(0.72, 1.28), hspace=0.44, wspace=0.58)
    ax_a = fig.add_subplot(grid[0, :])
    ax_b = fig.add_subplot(grid[1, 0])
    ax_c = fig.add_subplot(grid[1, 1])

    hierarchy_colors = [COLORS["teal"], COLORS["blue"], COLORS["orange"],
                        COLORS["violet"], COLORS["grey_light"]]
    role_labels = {
        "Q_TI": "QTI",
        "Q_GS": "QGS",
        "Q_HA": "QHA",
        "D2_Sensitive_risk": "Sensitive risk",
    }
    evidence_labels = {
        "Q_timestamp": "Source timestamp",
        "missing coverage": "Missing coverage",
        "gap duration/topology": "Gap duration /\ntopology",
        "observed hard stasis": "Observed hard\nstasis",
        "soft dynamics + comparable peer": "Soft dynamics +\ncomparable peer",
    }
    for i, row in hierarchy.iterrows():
        ax_a.scatter(i, 0, s=430, marker="s", color=hierarchy_colors[i],
                     edgecolor="white", linewidth=1.0, zorder=3)
        ax_a.text(i, 0.02, role_labels.get(row["production_role"], row["production_role"]),
                  ha="center", va="center",
                  fontsize=7, fontweight="bold")
        ax_a.text(i, -0.20, evidence_labels.get(row["evidence"], row["evidence"]), ha="center",
                  va="top", fontsize=6.2)
        if i < len(hierarchy) - 1:
            ax_a.annotate("", xy=(i + 0.68, 0), xytext=(i + 0.32, 0),
                          arrowprops={"arrowstyle": "->", "lw": 0.8,
                                      "color": COLORS["grey"]})
    ax_a.set_xlim(-0.55, len(hierarchy) - 0.45)
    ax_a.set_ylim(-0.48, 0.26)
    ax_a.axis("off")
    ax_a.set_title("Source timing, channel continuity and observed hard stasis remain explicit", pad=4)
    panel(ax_a, "a")

    matrix = correlation.pivot(index="row", columns="column", values="pearson_r").loc[
        ["Q_TI", "Q_GS", "Q_HA"], ["Q_TI", "Q_GS", "Q_HA"]
    ]
    image = ax_b.imshow(matrix, cmap="RdBu_r", vmin=-1, vmax=1, aspect="equal")
    for i in range(3):
        for j in range(3):
            value = matrix.iloc[i, j]
            ax_b.text(j, i, f"{value:.2f}", ha="center", va="center",
                      color="white" if abs(value) > 0.65 else COLORS["black"])
    ax_b.set_xticks(range(3), ["QTI", "QGS", "QHA"])
    ax_b.set_yticks(range(3), ["QTI", "QGS", "QHA"])
    effective = correlation["effective_dimension_global"].iloc[0]
    ax_b.set_title(f"Evidence correlation; effective dimension = {effective:.2f}")
    cbar = fig.colorbar(image, ax=ax_b, fraction=0.047, pad=0.04)
    cbar.set_label("r")
    style(ax_b, full_frame=True)
    panel(ax_b, "b", x=-0.22, y=1.10)

    y = np.arange(len(ablation))[::-1]
    for yi, (_, row) in zip(y, ablation.iterrows()):
        color = COLORS["red"] if row["variant_id"] == "strict_production" else COLORS["blue"]
        ax_c.plot([row["low_event_ci95_low"], row["low_event_ci95_high"]],
                  [yi, yi], color=color, lw=1.1)
        ax_c.plot(row["low_event_jaccard"], yi, "o", color=color, ms=4)
    ax_c.set_yticks(y, labels)
    ax_c.set_xlim(0, 1.03)
    ax_c.axvline(1, color=COLORS["grey"], ls=":", lw=0.8)
    ax_c.set_xlabel("Low-event Jaccard vs strict (cluster 95% CI)")
    ax_c.set_title("Ablation tests event identity, not score spread")
    style(ax_c)
    panel(ax_c, "c", x=-0.22, y=1.10)

    with pd.ExcelWriter(VALIDATION / "D2_Fig14_evidence_redundancy_source_data.xlsx",
                        engine="openpyxl") as writer:
        hierarchy.to_excel(writer, sheet_name="panel_a_hierarchy", index=False)
        correlation.to_excel(writer, sheet_name="panel_b_correlation", index=False)
        ablation.to_excel(writer, sheet_name="panel_c_ablation", index=False)
    save(fig, "D2_Fig14_aggregation_robustness")


def figure15_low_tail_burden() -> None:
    burden = _read_validation("D2_low_tail_burden.parquet")
    impact = _read_validation("D2_raw_vs_score_event_impact.parquet")
    sensitive = _read_validation("D2_sensitive_diagnostic_summary.parquet")
    phases = list(PHASE_LABELS)
    sensors = sorted(burden["sensor_id"].unique())
    matrix = burden.pivot(index="sensor_id", columns="phase", values="low_hours_per_1000h").reindex(
        index=sensors, columns=phases
    )

    fig = plt.figure(figsize=(7.2, 5.2))
    grid = fig.add_gridspec(2, 2, height_ratios=(1.25, 1.0), hspace=0.55, wspace=0.38)
    ax_a = fig.add_subplot(grid[0, :])
    ax_b = fig.add_subplot(grid[1, 0])
    ax_c = fig.add_subplot(grid[1, 1])

    vmax = max(float(np.nanmax(matrix.to_numpy())), 1.0)
    image = ax_a.imshow(matrix, aspect="auto", cmap="Blues", vmin=0, vmax=vmax)
    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            value = matrix.iloc[i, j]
            ax_a.text(j, i, f"{value:.1f}", ha="center", va="center",
                      color="white" if value > 0.58 * vmax else COLORS["black"], fontsize=5.8)
    ax_a.set_xticks(range(len(phases)), [PHASE_LABELS[p] for p in phases])
    ax_a.set_yticks(range(len(sensors)), sensors)
    ax_a.set_title("Low-score burden exposes temporal and channel structure hidden by the 4.96 mean")
    cbar = fig.colorbar(image, ax=ax_a, fraction=0.025, pad=0.02)
    cbar.set_label("D2 < 3 hours per 1000 sensor-hours")
    style(ax_a, full_frame=True)
    panel(ax_a, "a")

    phase_summary = burden.groupby("phase", as_index=False).agg(
        deficit=("deficit_points_per_1000h", "median"),
        veto=("veto_hours_per_1000h", "median"),
    ).set_index("phase").loc[phases]
    x = np.arange(len(phases))
    ax_b.plot(x, phase_summary["deficit"], marker="o", color=COLORS["blue"],
              lw=1.2, label="Score deficit")
    ax_b.plot(x, phase_summary["veto"], marker="s", color=COLORS["red"],
              lw=1.2, label="Veto hours")
    ax_b.set_xticks(x, [PHASE_LABELS[p].replace(" ", "\n") for p in phases])
    ax_b.set_ylabel("Burden per 1000 sensor-hours")
    ax_b.set_title("Locked phases differ in low-tail burden")
    ax_b.legend(loc="upper right")
    style(ax_b)
    panel(ax_b, "b")

    diag = sensitive.groupby("analyte", as_index=False)[[
        "intrinsic_soft_hour_rate", "joint_soft_hour_rate",
        "sustained_quasi_freeze_hour_rate", "production_Q_HA_low_rate",
    ]].mean()
    labels = ["Intrinsic low\ndynamics", "Joint soft\nevidence",
              "Sustained\nsuspect", "Production\nQHA < 3"]
    width = 0.34
    for i, (analyte, color) in enumerate((("DO", COLORS["blue"]), ("ORP", COLORS["red"]))):
        row = diag.loc[diag["analyte"].eq(analyte)].iloc[0]
        values = row.iloc[1:].to_numpy(dtype=float) * 100
        ax_c.bar(np.arange(4) + (i - 0.5) * width, values, width=width,
                 facecolor="white", edgecolor=color, linewidth=1.1, label=analyte)
    ax_c.set_xticks(range(4), labels)
    ax_c.set_ylabel("Sensor-hours (%)")
    ax_c.set_title("Independent corroboration filters soft dynamics")
    ax_c.legend(loc="upper right")
    style(ax_c)
    panel(ax_c, "c")

    with pd.ExcelWriter(VALIDATION / "D2_Fig15_low_tail_source_data.xlsx",
                        engine="openpyxl") as writer:
        burden.to_excel(writer, sheet_name="panel_a_burden", index=False)
        phase_summary.reset_index().to_excel(writer, sheet_name="panel_b_phase", index=False)
        diag.to_excel(writer, sheet_name="panel_c_sensitive", index=False)
        impact.to_excel(writer, sheet_name="event_duration_audit", index=False)
    save(fig, "D2_Fig15_low_tail_reporting")


def figure18_full_pipeline_validation() -> None:
    response = _read_validation("D2_full_pipeline_injection_response.parquet")
    windows = _read_validation("D2_qha_window_sensitivity.parquet")
    fig, axes = plt.subplots(2, 2, figsize=(7.2, 5.0))
    ax_a, ax_b, ax_c, ax_d = axes.ravel()

    timestamp = response.loc[response["route"].eq("timestamp")]
    for scenario, marker, color in (
        ("duplicate", "o", COLORS["blue"]),
        ("out_of_order", "s", COLORS["orange"]),
    ):
        sub = timestamp.loc[timestamp["scenario"].eq(scenario)].sort_values("severity")
        ax_a.plot(sub["severity"] * 100, sub["relevant_deficit_auc"], marker=marker,
                  ms=3.5, lw=1.1, color=color, label=scenario.replace("_", " ").title())
    irregular = timestamp.loc[timestamp["scenario"].eq("irregular_interval_sec")].sort_values("severity")
    ax_a.plot(irregular["severity"] - 60, irregular["relevant_deficit_auc"], marker="^",
              ms=3.5, lw=1.1, color=COLORS["violet"], label="Interval offset (s)")
    ax_a.set(xlabel="Injected rate (%) or interval offset (s)", ylabel="QTI deficit AUC",
             title="Raw timestamp defects show dose response")
    ax_a.legend(loc="upper left")
    style(ax_a)
    panel(ax_a, "a")

    gaps = response.loc[response["scenario"].eq("single_gap_min")]
    gap_curve = gaps.groupby("severity", as_index=False)["min_Q_GS"].mean().sort_values("severity")
    ax_b.plot(gap_curve["severity"], gap_curve["min_Q_GS"], marker="o", ms=3.5,
              lw=1.1, color=COLORS["blue"], label="DO and ORP coincide")
    ax_b.set_xscale("log")
    ax_b.set(xlabel="Single gap duration (min)", ylabel="Minimum QGS",
             title="Gap duration is routed to continuity topology")
    ax_b.set_ylim(0.8, 5.2)
    ax_b.legend(loc="lower left")
    style(ax_b)
    panel(ax_b, "b")

    stasis = response.loc[response["scenario"].eq("persistent_stasis_min")]
    stasis_curve = stasis.groupby("severity", as_index=False)["min_Q_HA"].mean().sort_values("severity")
    ax_c.plot(stasis_curve["severity"], stasis_curve["min_Q_HA"], marker="o", ms=3.5,
              lw=1.1, color=COLORS["violet"], label="DO and ORP coincide")
    ax_c.axvline(15, color=COLORS["grey"], ls="--", lw=0.8, label="Production threshold")
    ax_c.set(xlabel="Observed persistent stasis (min)", ylabel="Minimum QHA",
             title="Coverage deadband follows the persistence gate")
    ax_c.set_ylim(0.8, 5.2)
    ax_c.legend(loc="lower left")
    style(ax_c)
    panel(ax_c, "c")

    ax_d.plot(windows["window_h"], windows["low_event_jaccard_vs_6h"],
              color=COLORS["blue"], marker="o", lw=1.2, ms=4)
    ax_d.axhline(0.75, color=COLORS["red"], ls="--", lw=0.8, label="Prespecified 0.75")
    ax_d.axvline(6, color=COLORS["grey"], ls=":", lw=0.8)
    ax_d.set(xlabel="QHA trailing window (h)", ylabel="Low-event Jaccard vs 6 h",
             title="V4 window robustness is tested on the hard-only route")
    ax_d.set_xticks([3, 6, 9, 12])
    ax_d.set_ylim(0, 1.05)
    ax_d.legend(loc="lower right")
    style(ax_d)
    panel(ax_d, "d")

    with pd.ExcelWriter(VALIDATION / "D2_Fig18_full_pipeline_source_data.xlsx",
                        engine="openpyxl") as writer:
        response.to_excel(writer, sheet_name="panels_a_c_injection", index=False)
        windows.to_excel(writer, sheet_name="panel_d_windows", index=False)
    save(fig, "D2_Fig18_full_pipeline_validation")


def main() -> None:
    with (ROOT / "artifacts" / "d2_state.pkl").open("rb") as handle:
        state = pickle.load(handle)
    print(f"run={state['run_id']} calibration={state['calibration_id']}")
    figure13_process_floor()
    figure14_evidence_redundancy()
    figure15_low_tail_burden()
    figure16_construct_separation()
    figure17_timestamp_qti(state)
    figure18_full_pipeline_validation()


if __name__ == "__main__":
    main()
