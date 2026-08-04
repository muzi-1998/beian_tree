"""Nature-style confirmatory figures for the frozen D2 V2 release."""
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
    "Q_FA": COLORS["violet"],
    "D2_total": COLORS["black"],
}


def style(ax, full_frame: bool = False) -> None:
    ax.tick_params(axis="both", which="both", direction="out", length=3.2, width=0.8)
    for spine in ax.spines.values():
        spine.set_linewidth(0.8)
    if not full_frame:
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)


def panel(ax, letter: str) -> None:
    ax.text(-0.11, 1.025, f"({letter})", transform=ax.transAxes,
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
        ("qfa_unavailable_pct", "QFA unavailable", COLORS["orange"]),
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
             title="Threshold changes interpretation, not production QFA")
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
              f"Enrichment = {concordance['duration_jaccard_enrichment']:.2f}×\n"
              f"Monte Carlo P = {concordance['circular_shift_p_upper']:.4f}",
              transform=ax_c.transAxes, ha="right", va="top",
              bbox={"facecolor": "white", "edgecolor": COLORS["grey_light"], "alpha": 0.88})
    ax_c.legend(loc="upper left")
    style(ax_c)
    panel(ax_c, "c")
    save(fig, "D2_Fig16_d1_d2_construct_separation")


def main() -> None:
    with (ROOT / "artifacts" / "d2_state.pkl").open("rb") as handle:
        state = pickle.load(handle)
    print(f"run={state['run_id']} calibration={state['calibration_id']}")
    figure13_process_floor()
    figure14_robustness()
    figure15_tail_risk()
    figure16_construct_separation()


if __name__ == "__main__":
    main()
