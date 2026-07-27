from __future__ import annotations

from itertools import combinations
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .figure_style import PALETTE, configure_style, panel_label, save_figure


VERSION_ORDER = ("Legacy v1.2 proxy", "Current v1.3", "Restored v1.4")
VERSION_COLORS = (PALETTE["gray"], PALETTE["blue"], PALETTE["orange"])


def _load_score(path: Path, version: str, evaluable_column: str) -> pd.DataFrame:
    frame = pd.read_excel(path, sheet_name="main_scores")
    if "D4_raw" not in frame and "D6_raw" in frame:
        frame = frame.rename(columns={"D6_raw": "D4_raw"})
    frame["timestamp"] = pd.to_datetime(frame["timestamp"])
    frame["version"] = version
    frame["evaluable"] = frame[evaluable_column].astype(bool)
    return frame[["timestamp", "pair_id", "D4_raw", "evaluable", "version"]]


def _standardized_event_counts(frame: pd.DataFrame, min_hours: int = 3) -> pd.Series:
    counts: dict[str, int] = {}
    for pair_id, pair in frame.sort_values("timestamp").groupby("pair_id"):
        active = pair["evaluable"] & pair["D4_raw"].lt(3.0)
        groups = active.ne(active.shift(fill_value=False)).cumsum()
        count = 0
        for _, event in pair[active].groupby(groups[active]):
            duration = (
                (event["timestamp"].max() - event["timestamp"].min()).total_seconds() / 3600.0 + 1.0
            )
            count += int(duration >= min_hours)
        counts[pair_id] = count
    return pd.Series(counts, name="standardized_3h_events")


def _summary(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for (version, pair_id), group in frame.groupby(["version", "pair_id"], sort=False):
        valid = group.loc[group["evaluable"], "D4_raw"].dropna()
        rows.append({
            "version": version,
            "pair_id": pair_id,
            "n_rows": len(group),
            "n_evaluable": len(valid),
            "evaluable_rate": group["evaluable"].mean(),
            "mean_D4_raw": valid.mean(),
            "median_D4_raw": valid.median(),
            "p05_D4_raw": valid.quantile(0.05),
            "p25_D4_raw": valid.quantile(0.25),
            "p75_D4_raw": valid.quantile(0.75),
            "p95_D4_raw": valid.quantile(0.95),
            "low_score_rate": valid.lt(3.0).mean(),
        })
    summary = pd.DataFrame(rows)
    event_parts = []
    for version, group in frame.groupby("version", sort=False):
        event_parts.append(
            _standardized_event_counts(group).rename_axis("pair_id").reset_index().assign(version=version)
        )
    events = pd.concat(event_parts, ignore_index=True)
    return summary.merge(events, on=["version", "pair_id"], how="left")


def _aligned_comparisons(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    wide = frame.pivot_table(
        index=["timestamp", "pair_id"], columns="version", values="D4_raw", aggfunc="first"
    ).reset_index()
    rows = []
    for left, right in combinations(VERSION_ORDER, 2):
        for pair_id, group in wide.groupby("pair_id"):
            valid = group[[left, right]].dropna()
            rows.append({
                "scope": pair_id,
                "left_version": left,
                "right_version": right,
                "n_aligned": len(valid),
                "pearson_r": valid[left].corr(valid[right]),
                "spearman_rho": valid[left].corr(valid[right], method="spearman"),
                "mean_absolute_difference": (valid[left] - valid[right]).abs().mean(),
                "mean_signed_difference_right_minus_left": (valid[right] - valid[left]).mean(),
            })
        valid = wide[[left, right]].dropna()
        rows.append({
            "scope": "ALL_PAIRS",
            "left_version": left,
            "right_version": right,
            "n_aligned": len(valid),
            "pearson_r": valid[left].corr(valid[right]),
            "spearman_rho": valid[left].corr(valid[right], method="spearman"),
            "mean_absolute_difference": (valid[left] - valid[right]).abs().mean(),
            "mean_signed_difference_right_minus_left": (valid[right] - valid[left]).mean(),
        })
    return wide, pd.DataFrame(rows)


def _comparison_figure(
    summary: pd.DataFrame,
    aligned: pd.DataFrame,
    output_dir: Path,
) -> None:
    configure_style()
    pairs = summary["pair_id"].drop_duplicates().tolist()
    labels = [item.replace("PAIR_", "") for item in pairs]
    x = np.arange(len(pairs), dtype=float)
    width = 0.24
    fig, axes = plt.subplots(2, 2, figsize=(183 / 25.4, 142 / 25.4))
    fig.subplots_adjust(left=0.085, right=0.985, top=0.94, bottom=0.13, wspace=0.30, hspace=0.42)

    for offset, version, color in zip((-width, 0.0, width), VERSION_ORDER, VERSION_COLORS):
        values = summary[summary["version"].eq(version)].set_index("pair_id").reindex(pairs)
        axes[0, 0].bar(x + offset, values["mean_D4_raw"], width=width, color=color, label=version)
        axes[0, 1].bar(x + offset, values["low_score_rate"], width=width, color=color)
        axes[1, 1].bar(x + offset, values["standardized_3h_events"], width=width, color=color)
    axes[0, 0].set_ylabel("Mean D4 raw score")
    axes[0, 0].set_ylim(1, 5)
    axes[0, 0].legend(loc="upper center", bbox_to_anchor=(1.08, 1.24), ncol=3, columnspacing=0.9)
    axes[0, 1].set_ylabel("Low-score fraction (D4 raw < 3)")
    axes[0, 1].set_ylim(0, 1)
    axes[1, 1].set_ylabel("Standardized events (>=3 h)")
    for ax in (axes[0, 0], axes[0, 1], axes[1, 1]):
        ax.set_xticks(x, labels, rotation=35, ha="right")
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)

    valid = aligned[["Current v1.3", "Restored v1.4"]].dropna()
    sample = valid.iloc[::max(1, len(valid) // 12000)]
    axes[1, 0].hexbin(
        sample["Current v1.3"], sample["Restored v1.4"], gridsize=45,
        mincnt=1, cmap="Blues", extent=(1, 5, 1, 5),
    )
    axes[1, 0].plot([1, 5], [1, 5], color=PALETTE["gray"], lw=0.75, ls="--")
    correlation = valid["Current v1.3"].corr(valid["Restored v1.4"])
    axes[1, 0].text(
        0.04, 0.95, f"Pearson r = {correlation:.2f}", transform=axes[1, 0].transAxes,
        va="top", bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.72, "pad": 0.2},
    )
    axes[1, 0].set(
        xlim=(1, 5), ylim=(1, 5), xlabel="Current v1.3 D4 raw", ylabel="Restored v1.4 D4 raw"
    )
    for letter, ax in zip("abcd", axes.ravel()):
        panel_label(ax, letter)
    save_figure(fig, output_dir / "Fig_D4_three_version_sensitivity")


def run_sensitivity(d4_root: Path) -> dict[str, pd.DataFrame]:
    sources = (
        # Frozen lineage files retain the former D6 public identifier.
        ("Legacy v1.2 proxy", d4_root / "legacy" / "2026-05-30-proxy" / "D6_main_scores.xlsx", "usable_for_DQR"),
        ("Current v1.3", d4_root / "legacy" / "2026-07-13-v1.3-independent" / "D6_main_scores.xlsx", "usable_for_DQR"),
        ("Restored v1.4", d4_root / "outputs" / "data" / "D4_main_scores.xlsx", "usable_for_D4"),
    )
    combined = pd.concat(
        [_load_score(path, version, evaluable) for version, path, evaluable in sources],
        ignore_index=True,
    )
    summary = _summary(combined)
    aligned, correlations = _aligned_comparisons(combined)
    pair_wide = summary.pivot(index="pair_id", columns="version", values="mean_D4_raw").reset_index()
    pair_wide["restored_minus_legacy"] = pair_wide["Restored v1.4"] - pair_wide["Legacy v1.2 proxy"]
    pair_wide["restored_minus_current"] = pair_wide["Restored v1.4"] - pair_wide["Current v1.3"]
    method_changes = pd.DataFrame([
        {"version": "Legacy v1.2 proxy", "input": "raw minute data; internal residual", "mapping": "pooled by regime", "change_point": "legacy adjacent-KS implementation", "arbitration": "D1/D2/D5 proxies", "event_rule": "3 h"},
        {"version": "Current v1.3", "input": "formal 1.1 residual; 10-min median", "mapping": "pair-specific first 70%", "change_point": "24-h half-window shift", "arbitration": "none", "event_rule": "2 h"},
        {
            "version": "Restored v1.4",
            "input": "formal 1.1 residual; 10-min median",
            "mapping": "public variable x regime; documented fallback",
            "change_point": "7-d adjacent KS; fixed timing table",
            "arbitration": "D4 raw protected; D1 interpretive; external D5 gate",
            "event_rule": "3 h",
        },
    ])
    output_dir = d4_root / "outputs" / "comparison"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "D4_three_version_sensitivity.xlsx"
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        summary.to_excel(writer, sheet_name="pair_summary", index=False)
        pair_wide.to_excel(writer, sheet_name="pair_mean_deltas", index=False)
        correlations.to_excel(writer, sheet_name="aligned_comparisons", index=False)
        aligned.to_excel(writer, sheet_name="aligned_scores", index=False)
        method_changes.to_excel(writer, sheet_name="method_contract", index=False)
    _comparison_figure(summary, aligned, output_dir)
    return {
        "pair_summary": summary,
        "pair_mean_deltas": pair_wide,
        "aligned_comparisons": correlations,
        "method_contract": method_changes,
    }
