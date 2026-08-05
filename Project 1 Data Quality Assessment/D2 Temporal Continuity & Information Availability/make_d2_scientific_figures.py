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
    injection = _read_validation("D2_full_pipeline_injection_response.parquet")
    first_qha_decline = float(injection.loc[
        injection["scenario"].eq("persistent_stasis_min")
        & injection["min_Q_HA"].lt(5), "severity"
    ].min())

    fig = plt.figure(figsize=(7.2, 6.2))
    grid = fig.add_gridspec(3, 2, hspace=0.58, wspace=0.32)
    axes = [fig.add_subplot(grid[row, col]) for row in range(3) for col in range(2)]
    scenarios = [
        ("true_low_oxygen_floor", "True low-DO floor", COLORS["blue"]),
        ("low_oxygen_small_fluctuation", "Resolution-limited fluctuation", COLORS["teal"]),
        ("digital_lock", "Observed hard stasis", COLORS["red"]),
        ("response_recovery_after_floor", "Response after leaving floor", COLORS["orange"]),
    ]
    for index, (scenario, title, color) in enumerate(scenarios):
        ax = axes[index]
        sub = challenge.loc[challenge["scenario"].eq(scenario)].copy().reset_index(drop=True)
        sub["minute"] = np.arange(len(sub))
        ax.axhspan(0, 0.20, color=COLORS["blue_light"], alpha=0.18)
        ax.plot(sub["minute"], sub["value"], color=color, lw=1.05)
        if sub["sensor_freeze"].any():
            flagged = sub["sensor_freeze"].astype(bool)
            ax.scatter(sub.loc[flagged, "minute"], sub.loc[flagged, "value"],
                       marker="x", s=11, lw=0.7, color=COLORS["red"], zorder=4)
        ax.set_ylim(-0.02, 0.47)
        ax.set_xlabel("Elapsed time (min)")
        ax.set_ylabel("DO (mg L$^{-1}$)")
        ax.set_title(title)
        style(ax)
        panel(ax, chr(ord("a") + index))

    hard_ax = axes[2]
    hard_ax.axvline(15, color=COLORS["grey"], ls="--", lw=0.8)
    hard_ax.axvline(first_qha_decline, color=COLORS["violet"], ls=":", lw=1.0)
    hard_ax.text(15.5, 0.42, "First hard flag\n15 min", ha="left", va="top", fontsize=5.8)
    hard_ax.text(first_qha_decline + 0.8, 0.24,
                 f"First projected\n$Q_{{HA}}$ < 5: {first_qha_decline:.0f} min",
                 ha="left", va="top", fontsize=5.8, color=COLORS["violet"])

    recovery = challenge.loc[
        challenge["scenario"].eq("response_recovery_after_floor")
    ].reset_index(drop=True)
    recovery_exit = int(np.flatnonzero(~recovery["floor_occupancy"].to_numpy())[0])
    axes[3].axvline(recovery_exit, color=COLORS["green"], ls="--", lw=0.8)
    axes[3].text(recovery_exit + 1, 0.44, "Leaves process floor",
                 color=COLORS["green"], fontsize=5.8, va="top")

    missing_ax = axes[4]
    missing = challenge.loc[
        challenge["scenario"].eq("missing_and_long_gap_not_exempt")
    ].copy().reset_index(drop=True)
    missing["minute"] = np.arange(len(missing))
    missing_ax.axhspan(0, 0.20, color=COLORS["blue_light"], alpha=0.18)
    missing_ax.plot(missing["minute"], missing["value"], color=COLORS["blue"], lw=1.05)
    for start, end in [(8, 14)]:
        missing_ax.axvspan(start - 0.5, end - 0.5, facecolor=COLORS["grey_light"],
                           edgecolor=COLORS["red"], hatch="////", alpha=0.45)
    missing_ax.fill_between(missing["minute"], 0.405, 0.445,
                            where=missing["continuity_unavailable"].astype(bool),
                            color=COLORS["orange"], step="mid")
    missing_ax.text(10.5, 0.39, "Missing + long gap", ha="center", va="top", fontsize=5.8)
    missing_ax.text(0.98, 0.53,
                    "$Q_{TI}$/$Q_{GS}$ unavailable; $Q_{HA}$ not triggered",
                    transform=missing_ax.transAxes, ha="right", va="top", fontsize=5.8,
                    bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.78,
                          "pad": 1.0})
    missing_ax.set(xlabel="Elapsed time (min)", ylabel="DO (mg L$^{-1}$)",
                   title="Process floor does not exempt missingness")
    missing_ax.set_ylim(-0.02, 0.47)
    style(missing_ax)
    panel(missing_ax, "e")

    field_ax = axes[5]
    metrics = [
        ("floor_occupancy_pct", "Floor occupancy", COLORS["blue"]),
        ("resolution_limited_pct", "Resolution limited", COLORS["teal"]),
        ("sensor_freeze_pct", "Hard stasis", COLORS["red"]),
        ("hard_stasis_severe_veto_pct", "$Q_{HA}$ Veto", COLORS["violet"]),
    ]
    offsets = (-0.18, -0.06, 0.06, 0.18)
    for (column, label, color), offset in zip(metrics, offsets):
        y = np.arange(len(observed)) + offset
        values = observed[column].to_numpy(dtype=float)
        zero = values == 0
        field_ax.scatter(values[~zero], y[~zero], color=color, edgecolor=COLORS["black"],
                         linewidth=0.35, s=28, label=label, zorder=3)
        field_ax.scatter(values[zero], y[zero], facecolor="white", edgecolor=color,
                         linewidth=1.0, s=30, zorder=4)
        for x0, y0 in zip(values[zero], y[zero]):
            field_ax.text(x0 + 0.004, y0, "0", va="center", ha="left", fontsize=5.5)
    field_ax.set_xscale("symlog", linthresh=0.02, linscale=0.8, base=10)
    field_ax.set_xlim(-0.004, 130)
    field_ax.set_yticks(range(len(observed)), observed["sensor_id"])
    field_ax.set_xlabel("Observed coverage (%)")
    field_ax.set_title("Field evidence remains separated")
    field_ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.29), ncol=2,
                    handletextpad=0.3, columnspacing=0.7)
    style(field_ax)
    panel(field_ax, "f")

    with pd.ExcelWriter(VALIDATION / "D2_Fig13_process_floor_source_data.xlsx",
                        engine="openpyxl") as writer:
        challenge.to_excel(writer, sheet_name="panels_a_e_challenges", index=False)
        observed.to_excel(writer, sheet_name="panel_f_field", index=False)
        injection.loc[injection["scenario"].eq("persistent_stasis_min")].to_excel(
            writer, sheet_name="QHA_projection", index=False
        )
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
    phase_null = _read_validation("D2_d1d2_phase_constrained_null.parquet")
    d2 = pd.read_excel(DATA / "D2_freeze_availability_events.xlsx")
    d1 = pd.read_excel(PROJECT / "D1 Sensor health" / "outputs" / "data" / "D1_event_windows.xlsx",
                       sheet_name="all_events")

    fig = plt.figure(figsize=(7.2, 4.5))
    grid = fig.add_gridspec(2, 2, height_ratios=(1.0, 1.15), hspace=0.48, wspace=0.38)
    ax_a = fig.add_subplot(grid[0, 0])
    ax_b = fig.add_subplot(grid[0, 1])
    ax_c = fig.add_subplot(grid[1, :])

    counts = [concordance["D1_events"], concordance["D2_hard_availability_events"]]
    matched = int(concordance["matched_event_pairs"])
    for xpos, value, color in zip((0, 1), counts, (COLORS["orange"], COLORS["blue"])):
        ax_a.vlines(xpos, 0, value, color=color, lw=3.0)
        ax_a.plot(xpos, value, "o", color=color, ms=6)
        ax_a.text(xpos, value + 4, f"{int(value)}", ha="center", va="bottom", fontsize=7)
    ax_a.hlines(matched, 0, 1, color=COLORS["red"], lw=1.2, ls="--")
    ax_a.plot(0.5, matched, "o", color=COLORS["red"], ms=5)
    ax_a.text(0.5, matched + 5, f"{matched} matched pairs", color=COLORS["red"],
              ha="center", fontsize=6.3, fontweight="bold")
    ax_a.set_xticks([0, 1], ["D1 sensor\nhealth", "D2 hard\navailability"])
    ax_a.set_ylabel("Number of events")
    ax_a.set_ylim(0, max(counts) * 1.16)
    ax_a.set_title("Limited one-to-one event concordance")
    ax_a.text(0.5, 0.17, "One-to-one matching tolerance = ±1 h",
              transform=ax_a.transAxes, ha="center", fontsize=5.8,
              color=COLORS["grey"],
              bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.78, "pad": 1.0})
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
    ax_b.set_title("Channel-level event counts")
    ax_b.legend(loc="lower right", ncol=3, handlelength=1.0)
    style(ax_b)
    panel(ax_b, "b")

    values = null["duration_jaccard"].to_numpy()
    phase_values = phase_null["duration_jaccard"].to_numpy()
    bins = np.linspace(0, max(values.max(), phase_values.max(), 0.022), 32)
    ax_c.hist(values, bins=bins, color=COLORS["grey_light"], edgecolor="white",
              linewidth=0.4, alpha=0.78, label="Full-period circular shift")
    ax_c.hist(phase_values, bins=bins, histtype="step", color=COLORS["blue"],
              linewidth=1.0, label="Within-phase circular shift")
    observed = float(concordance["duration_jaccard_observed"])
    ax_c.axvline(observed, color=COLORS["red"], lw=1.5,
                 label=f"Observed = {observed:.3f}")
    ax_c.axvline(float(concordance["duration_jaccard_null_median"]),
                 color=COLORS["black"], lw=0.8, ls="--")
    ax_c.axvline(float(concordance["phase_constrained_null_median"]),
                 color=COLORS["blue"], lw=0.8, ls=":")
    ax_c.set(xlabel="Duration Jaccard after sensor-specific circular shift",
             ylabel="Null replicates",
             title="Limited temporal concordance between health and hard-availability events")
    ax_c.text(0.99, 0.92,
              f"Full-period P = {concordance['circular_shift_p_upper']:.4f}\n"
              f"Within-phase P = {concordance['phase_constrained_p_upper']:.4f}\n"
              "Event matching tolerance = 1 h",
              transform=ax_c.transAxes, ha="right", va="top",
              bbox={"facecolor": "white", "edgecolor": COLORS["grey_light"], "alpha": 0.88})
    ax_c.legend(loc="upper left")
    style(ax_c)
    panel(ax_c, "c")
    save(fig, "D2_Fig16_limited_event_concordance")


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
    labels = ["Strict", "$Q_{TI}$ without\nmissing", "No $Q_{GS}$", "No $Q_{HA}$"]
    ablation = ablation.set_index("variant_id").loc[order].reset_index()

    fig = plt.figure(figsize=(7.2, 4.8))
    grid = fig.add_gridspec(2, 2, height_ratios=(0.82, 1.18), width_ratios=(0.88, 1.12),
                            hspace=0.46, wspace=0.42)
    ax_a = fig.add_subplot(grid[0, :])
    ax_b = fig.add_subplot(grid[1, 0])
    ax_c = fig.add_subplot(grid[1, 1])

    positions = {
        "Raw source": (0.0, 0.50),
        "Timestamp audit": (1.0, 0.90),
        "Missing runs": (1.0, 0.62),
        "Observed values": (1.0, 0.34),
        "Soft dynamics + peer": (1.0, 0.06),
        "Q_TI": (2.0, 0.78),
        "Q_GS": (2.0, 0.54),
        "Q_HA": (2.0, 0.30),
        "Sensitive risk": (2.0, 0.06),
    }
    node_colors = {
        "Raw source": COLORS["black"],
        "Timestamp audit": COLORS["teal"],
        "Missing runs": COLORS["orange"],
        "Observed values": COLORS["violet"],
        "Soft dynamics + peer": COLORS["grey"],
        "Q_TI": COLORS["blue"],
        "Q_GS": COLORS["orange"],
        "Q_HA": COLORS["violet"],
        "Sensitive risk": COLORS["grey"],
    }
    for edge in hierarchy.itertuples(index=False):
        x0, y0 = positions[edge.source]
        x1, y1 = positions[edge.target]
        ax_a.annotate("", xy=(x1 - 0.16, y1), xytext=(x0 + 0.16, y0),
                      arrowprops={"arrowstyle": "->", "lw": 0.75,
                                  "color": COLORS["grey"]})
    for name, (x0, y0) in positions.items():
        outcome = name in {"Q_TI", "Q_GS", "Q_HA", "Sensitive risk"}
        display_name = {
            "Q_TI": "$Q_{TI}$",
            "Q_GS": "$Q_{GS}$",
            "Q_HA": "$Q_{HA}$",
        }.get(name, name)
        ax_a.text(x0, y0, display_name, ha="center", va="center",
                  color="white" if node_colors[name] != COLORS["grey_light"] else COLORS["black"],
                  fontsize=6.2, fontweight="bold" if outcome else "normal",
                  bbox={"boxstyle": "square,pad=0.28", "facecolor": node_colors[name],
                        "edgecolor": "white", "linewidth": 0.6, "alpha": 0.96})
    ax_a.text(0.0, 0.10, "Source", ha="center", fontsize=5.8, color=COLORS["grey"])
    ax_a.text(1.0, -0.16, "Evidence branches", ha="center", fontsize=5.8, color=COLORS["grey"])
    ax_a.text(2.0, -0.16, "Production / diagnostic outputs", ha="center",
              fontsize=5.8, color=COLORS["grey"])
    ax_a.set_xlim(-0.35, 2.35)
    ax_a.set_ylim(-0.24, 1.05)
    ax_a.axis("off")
    ax_a.set_title("Shared continuity input is explicit; hard availability remains independent", pad=4)
    panel(ax_a, "a")

    pair_rows = [("Q_TI", "Q_GS"), ("Q_TI", "Q_HA"), ("Q_GS", "Q_HA")]
    metric_columns = ["pearson_r", "spearman_rho", "low_event_phi", "low_event_jaccard"]
    matrix = np.array([
        [correlation.loc[correlation["row"].eq(left) & correlation["column"].eq(right), metric].iloc[0]
         for metric in metric_columns]
        for left, right in pair_rows
    ], dtype=float)
    image = ax_b.imshow(matrix, cmap="RdBu_r", vmin=-1, vmax=1, aspect="auto")
    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            value = matrix[i, j]
            ax_b.text(j, i, "NA" if not np.isfinite(value) else f"{value:.2f}",
                      ha="center", va="center", fontsize=6.2,
                      color="white" if np.isfinite(value) and abs(value) > 0.65 else COLORS["black"])
    ax_b.set_xticks(range(4), ["Pearson\nr", "Spearman\nρ", "Low-score\nφ", "Low-score\nJaccard"])
    ax_b.set_yticks(
        range(3),
        ["$Q_{TI}$–$Q_{GS}$", "$Q_{TI}$–$Q_{HA}$", "$Q_{GS}$–$Q_{HA}$"],
    )
    effective = correlation["effective_dimension_global"].iloc[0]
    ax_b.set_title(f"Continuous and low-tail association (effective dimension {effective:.2f})")
    cbar = fig.colorbar(image, ax=ax_b, fraction=0.047, pad=0.04)
    cbar.set_label("Association")
    style(ax_b, full_frame=True)
    panel(ax_b, "b", x=-0.22, y=1.10)

    y = np.arange(len(ablation))[::-1]
    for yi, (_, row) in zip(y, ablation.iterrows()):
        color = COLORS["red"] if row["variant_id"] == "strict_production" else COLORS["blue"]
        ax_c.plot([row["low_event_ci95_low"], row["low_event_ci95_high"]],
                  [yi, yi], color=color, lw=1.1)
        ax_c.plot(row["low_event_jaccard"], yi, "o", color=color, ms=4)
    ax_c.set_yticks(y, labels)
    ax_c.set_xlim(0.72, 1.54)
    ax_c.set_xticks([0.8, 0.9, 1.0])
    ax_c.axvline(1, color=COLORS["grey"], ls=":", lw=0.8)
    ax_c.axvline(1.035, color=COLORS["grey_light"], lw=0.7)
    headers = [(1.08, "Events"), (1.19, "Δ low h"), (1.32, "Δ deficit"), (1.46, "Rank ρ")]
    for xpos, header in headers:
        ax_c.text(xpos, y.max() + 0.43, header, ha="center", va="bottom",
                  fontsize=5.3, fontweight="bold")
    for yi, (_, row) in zip(y, ablation.iterrows()):
        ax_c.text(1.08, yi, f"{int(row['candidate_events'])}", ha="center", va="center", fontsize=5.5)
        ax_c.text(1.19, yi, f"{row['delta_low_hours_per_1000h']:+.2f}", ha="center", va="center", fontsize=5.5)
        ax_c.text(1.32, yi, f"{row['delta_deficit_points_per_1000h']:+.2f}", ha="center", va="center", fontsize=5.5)
        ax_c.text(1.46, yi, f"{row['sensor_rank_spearman']:.2f}", ha="center", va="center", fontsize=5.5)
    ax_c.set_xlabel("Low-event Jaccard vs strict (cluster 95% CI)")
    ax_c.set_title("Ablation changes event identity and burden")
    style(ax_c)
    panel(ax_c, "c", x=-0.22, y=1.10)

    with pd.ExcelWriter(VALIDATION / "D2_Fig14_evidence_hierarchy_ablation_source_data.xlsx",
                        engine="openpyxl") as writer:
        hierarchy.to_excel(writer, sheet_name="panel_a_hierarchy", index=False)
        correlation.to_excel(writer, sheet_name="panel_b_correlation", index=False)
        ablation.to_excel(writer, sheet_name="panel_c_ablation", index=False)
    save(fig, "D2_Fig14_evidence_hierarchy_ablation")


def figure15_low_tail_burden() -> None:
    burden = _read_validation("D2_low_tail_burden.parquet")
    event_summary = _read_validation("D2_low_tail_event_summary.parquet")
    veto_summary = _read_validation("D2_veto_reason_summary.parquet")
    phases = list(PHASE_LABELS)
    sensors = [
        *[f"DO_1_{position}" for position in range(1, 5)],
        *[f"DO_2_{position}" for position in range(1, 5)],
        *[f"ORP_1_{position}" for position in range(1, 4)],
        *[f"ORP_2_{position}" for position in range(1, 4)],
    ]
    matrix = burden.pivot(index="sensor_id", columns="phase", values="low_hours_per_1000h").reindex(
        index=sensors, columns=phases
    )

    fig = plt.figure(figsize=(7.2, 6.0))
    grid = fig.add_gridspec(2, 3, height_ratios=(1.35, 1.0), hspace=0.58, wspace=0.42)
    ax_a = fig.add_subplot(grid[0, :])
    ax_b = fig.add_subplot(grid[1, 0])
    ax_c = fig.add_subplot(grid[1, 1])
    ax_d = fig.add_subplot(grid[1, 2])

    vmax = max(float(np.nanmax(matrix.to_numpy())), 1.0)
    image = ax_a.imshow(matrix, aspect="auto", cmap="Blues", vmin=0, vmax=vmax)
    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            value = matrix.iloc[i, j]
            label = "0" if np.isclose(value, 0) else f"{value:.1f}"
            ax_a.text(j, i, label, ha="center", va="center",
                      color="white" if value > 0.58 * vmax else COLORS["black"], fontsize=5.8)
    phase_dates = {
        "development": "Aug-Dec 2025",
        "internal_validation": "Jan-Feb 2026",
        "terminal_test": "Feb-Apr 2026",
    }
    phase_hours = burden.groupby("phase")["n_sensor_hours"].median().reindex(phases)
    ax_a.set_xticks(range(len(phases)), [
        f"{PHASE_LABELS[p]}\n{phase_dates[p]}\nn={int(phase_hours[p])} h/channel"
        for p in phases
    ])
    ax_a.set_yticks(range(len(sensors)), sensors)
    for boundary in (3.5, 7.5, 10.5):
        ax_a.axhline(boundary, color="white", lw=1.4)
    for center, label in ((1.5, "DO line 1"), (5.5, "DO line 2"),
                          (9.0, "ORP line 1"), (12.0, "ORP line 2")):
        ax_a.text(-0.12, center, label, transform=ax_a.get_yaxis_transform(),
                  ha="right", va="center", fontsize=5.5, color=COLORS["grey"])
    ax_a.set_title("Low-score hours reveal channel and phase structure")
    cbar = fig.colorbar(image, ax=ax_a, fraction=0.025, pad=0.02)
    cbar.set_label("D2 < 3 hours per 1000 sensor-hours")
    style(ax_a, full_frame=True)
    panel(ax_a, "a")

    x = np.arange(len(phases))
    width = 0.34
    for offset, (analyte, color) in zip((-width / 2, width / 2),
                                        (("DO", COLORS["blue"]), ("ORP", COLORS["red"]))):
        sub = event_summary.loc[event_summary["analyte"].eq(analyte)].set_index("phase").loc[phases]
        values = sub["events_per_1000h"].to_numpy()
        lower = values - sub["event_rate_ci95_low"].to_numpy()
        upper = sub["event_rate_ci95_high"].to_numpy() - values
        ax_b.bar(x + offset, values, width=width, facecolor="white", edgecolor=color,
                 linewidth=1.1, label=analyte)
        ax_b.errorbar(x + offset, values, yerr=np.vstack([lower, upper]), fmt="none",
                      ecolor=color, elinewidth=0.8, capsize=2)
    ax_b.set_xticks(x, ["Dev.", "Validation", "Terminal"])
    ax_b.set_ylabel("Events per 1000 sensor-hours")
    ax_b.set_title("Low-score event frequency")
    ax_b.legend(loc="upper right")
    style(ax_b)
    panel(ax_b, "b")

    duration = event_summary.loc[event_summary["analyte"].eq("ALL")].set_index("phase").loc[phases]
    duration_columns = ["duration_median_h", "duration_p95_h", "duration_max_h"]
    if (duration[duration_columns] <= 0).any().any():
        raise ValueError("Event-duration summaries must be strictly positive before log scaling.")
    for column, marker, color, label in (
        ("duration_median_h", "o", COLORS["blue"], "Median"),
        ("duration_p95_h", "^", COLORS["orange"], "P95"),
        ("duration_max_h", "D", COLORS["red"], "Maximum"),
    ):
        ax_c.plot(x, duration[column], marker=marker, color=color, lw=1.0, ms=3.5, label=label)
    ax_c.set_yscale("log")
    ax_c.set_xticks(x, ["Dev.", "Validation", "Terminal"])
    ax_c.set_ylabel("Event duration (h, log scale)")
    ax_c.set_title("Event duration distribution")
    ax_c.legend(loc="lower left")
    style(ax_c)
    panel(ax_c, "c")

    reason_order = ["Missing only", "Gap + missing", "Gap only", "Hard stasis", "Other"]
    reason_colors = [COLORS["blue"], COLORS["orange"], COLORS["teal"], COLORS["violet"], COLORS["grey"]]
    bottom = np.zeros(len(phases))
    totals = []
    for phase in phases:
        totals.append(int(veto_summary.loc[veto_summary["phase"].eq(phase), "veto_hours"].sum()))
    for reason, color in zip(reason_order, reason_colors):
        values = np.array([
            veto_summary.loc[veto_summary["phase"].eq(phase)
                             & veto_summary["reason_group"].eq(reason), "veto_share"].sum() * 100
            for phase in phases
        ])
        if np.allclose(values, 0):
            continue
        ax_d.bar(x, values, bottom=bottom, color=color, width=0.68, label=reason)
        bottom += values
    for xi, total in zip(x, totals):
        ax_d.text(xi, 102, f"n={total}", ha="center", va="bottom", fontsize=5.4)
    ax_d.set_xticks(x, ["Dev.", "Validation", "Terminal"])
    ax_d.set_ylim(0, 111)
    ax_d.set_ylabel("Veto reason share (%)")
    ax_d.set_title("Veto composition")
    ax_d.legend(loc="upper center", bbox_to_anchor=(0.5, -0.22), ncol=2,
                handlelength=1.0, columnspacing=0.7)
    style(ax_d)
    panel(ax_d, "d")

    with pd.ExcelWriter(VALIDATION / "D2_Fig15_low_tail_source_data.xlsx",
                        engine="openpyxl") as writer:
        burden.to_excel(writer, sheet_name="panel_a_burden", index=False)
        event_summary.to_excel(writer, sheet_name="panels_b_c_events", index=False)
        veto_summary.to_excel(writer, sheet_name="panel_d_veto", index=False)
    save(fig, "D2_Fig15_low_tail_reporting")


def figure18_full_pipeline_validation() -> None:
    response = _read_validation("D2_full_pipeline_injection_response.parquet")
    windows = _read_validation("D2_qha_window_sensitivity.parquet")
    fig = plt.figure(figsize=(7.2, 5.6))
    grid = fig.add_gridspec(2, 6, hspace=0.58, wspace=0.68)
    ax_a = fig.add_subplot(grid[0, 0:2])
    ax_b = fig.add_subplot(grid[0, 2:4])
    ax_c = fig.add_subplot(grid[0, 4:6])
    ax_d = fig.add_subplot(grid[1, 0:3])
    ax_e = fig.add_subplot(grid[1, 3:6])

    timestamp = response.loc[response["route"].eq("timestamp")]
    for scenario, marker, color in (
        ("duplicate", "o", COLORS["blue"]),
        ("out_of_order", "s", COLORS["orange"]),
    ):
        sub = timestamp.loc[timestamp["scenario"].eq(scenario)].sort_values("severity")
        legend_label = "Duplicate" if scenario == "duplicate" else "Out-of-order"
        ax_a.plot(sub["severity"] * 100, sub["relevant_deficit_auc"], marker=marker,
                  ms=3.5, lw=1.1, color=color, label=legend_label)
    ax_a.set(xlabel="Injected timestamp rate (%)", ylabel="$Q_{TI}$ deficit AUC",
             title="Duplicate/out-of-order\ndose response")
    ax_a.legend(loc="upper left")
    style(ax_a)
    panel(ax_a, "a", x=-0.19, y=1.12)

    irregular = timestamp.loc[timestamp["scenario"].eq("irregular_interval_sec")].sort_values("severity")
    ax_b.plot(irregular["severity"] - 60, irregular["relevant_deficit_auc"], marker="^",
              ms=3.5, lw=1.1, color=COLORS["violet"])
    ax_b.set(xlabel="Interval offset from 60 s (s)", ylabel="$Q_{TI}$ deficit AUC",
             title="Irregular-interval\ndose response")
    style(ax_b)
    panel(ax_b, "b", x=-0.19, y=1.12)

    gaps = response.loc[response["scenario"].eq("single_gap_min")]
    gap_curve = gaps.groupby("severity", as_index=False)["min_Q_GS"].mean().sort_values("severity")
    ax_c.plot(gap_curve["severity"], gap_curve["min_Q_GS"], marker="o", ms=3.5,
              lw=1.1, color=COLORS["blue"], label="DO and ORP coincide")
    repeated = response.loc[response["scenario"].eq("ten_two_minute_gaps")]
    repeated_qgs = float(repeated["min_Q_GS"].mean())
    ax_c.plot(20, repeated_qgs, marker="*", ms=7, color=COLORS["red"],
              label="10 × 2-min gaps", zorder=4)
    ax_c.set_xscale("log")
    ax_c.set(xlabel="Total or single-gap duration (min)", ylabel="Minimum $Q_{GS}$",
             title="Gap topology distinguishes\ndispersed loss")
    ax_c.set_ylim(0.8, 5.2)
    ax_c.legend(loc="lower left")
    style(ax_c)
    panel(ax_c, "c", x=-0.19, y=1.12)

    stasis = response.loc[response["scenario"].eq("persistent_stasis_min")]
    stasis_curve = stasis.groupby("severity", as_index=False)["min_Q_HA"].mean().sort_values("severity")
    ax_d.plot(stasis_curve["severity"], stasis_curve["min_Q_HA"], marker="o", ms=3.5,
              lw=1.1, color=COLORS["violet"], label="DO and ORP coincide")
    ax_d.axvline(15, color=COLORS["grey"], ls="--", lw=0.8, label="15-min eligibility gate")
    threshold_colors = {4.5: COLORS["teal"], 3.0: COLORS["orange"], 2.0: COLORS["red"]}
    threshold_rows = []
    for threshold, color in threshold_colors.items():
        eligible = stasis_curve.loc[stasis_curve["min_Q_HA"].lt(threshold)]
        crossing = float(eligible["severity"].min()) if len(eligible) else np.nan
        threshold_rows.append({"Q_HA_threshold": threshold, "first_duration_min": crossing})
        if np.isfinite(crossing):
            ax_d.axvline(crossing, color=color, ls=":", lw=0.8)
            ax_d.text(crossing, threshold + 0.12, f"{crossing:.0f} min",
                      rotation=90, ha="right", va="bottom", fontsize=5.4, color=color)
        ax_d.axhline(threshold, color=color, ls=":", lw=0.45, alpha=0.55)
    ax_d.set(xlabel="Observed persistent stasis (min)", ylabel="Minimum $Q_{HA}$",
             title="Eligibility gate and score deadbands are explicit")
    ax_d.set_ylim(0.8, 5.25)
    ax_d.legend(loc="lower left")
    style(ax_d)
    panel(ax_d, "d", x=-0.15, y=1.10)

    yerr = np.vstack([
        windows["low_event_jaccard_vs_6h"] - windows["low_event_jaccard_ci95_low"],
        windows["low_event_jaccard_ci95_high"] - windows["low_event_jaccard_vs_6h"],
    ])
    ax_e.errorbar(windows["window_h"], windows["low_event_jaccard_vs_6h"], yerr=yerr,
                  color=COLORS["blue"], marker="o", lw=1.2, ms=4, capsize=2)
    ax_e.axhline(0.75, color=COLORS["red"], ls="--", lw=0.8, label="Prespecified 0.75")
    ax_e.axvline(6, color=COLORS["grey"], ls=":", lw=0.8)
    for row in windows.itertuples(index=False):
        ax_e.text(row.window_h, row.low_event_jaccard_ci95_low - 0.045,
                  f"n={int(row.candidate_events)}\n{row.low_hour_rate * 100:.2f}% low",
                  ha="center", va="top", fontsize=5.2)
    ax_e.set(xlabel="$Q_{HA}$ trailing window (h)", ylabel="Low-event Jaccard vs 6 h",
             title="Window robustness includes event count and cluster 95% CI")
    ax_e.set_xticks([3, 6, 9, 12])
    ax_e.set_ylim(0.62, 1.05)
    ax_e.legend(loc="lower right")
    style(ax_e)
    panel(ax_e, "e", x=-0.15, y=1.10)

    with pd.ExcelWriter(VALIDATION / "D2_Fig18_full_pipeline_source_data.xlsx",
                        engine="openpyxl") as writer:
        timestamp.to_excel(writer, sheet_name="panels_a_b_timestamp", index=False)
        response.loc[response["route"].eq("gap")].to_excel(
            writer, sheet_name="panel_c_gaps", index=False
        )
        stasis.to_excel(writer, sheet_name="panel_d_stasis", index=False)
        pd.DataFrame(threshold_rows).to_excel(writer, sheet_name="panel_d_thresholds", index=False)
        windows.to_excel(writer, sheet_name="panel_e_windows", index=False)
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
