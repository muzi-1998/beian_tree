from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import matplotlib as mpl
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from d4.figure_style import PALETTE, configure_style, finalize, panel_label


LOW_TAIL_THRESHOLD = 3.0
SCOPE_ORDER = ("exact", "variable_fallback", "global_fallback", "insufficient")
SCOPE_COLORS = {
    "exact": PALETTE["blue"],
    "variable_fallback": PALETTE["orange"],
    "global_fallback": PALETTE["red"],
    "insufficient": PALETTE["mid_gray"],
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def classify_mapping_scope(scope: object) -> str:
    value = str(scope).strip().lower()
    if value == "variable_regime_public":
        return "exact"
    if value == "variable_public_fallback":
        return "variable_fallback"
    if "global" in value and "fallback" in value:
        return "global_fallback"
    return "insufficient"


def _worst_precision(values: pd.Series) -> str:
    rank = {"supported": 0, "wide_interval": 1, "not_estimable": 2}
    normalized = values.dropna().astype(str)
    if normalized.empty:
        return "not_available"
    return max(normalized, key=lambda item: rank.get(item, 3))


def build_mapping_lookup(mapping: pd.DataFrame) -> pd.DataFrame:
    production = mapping.loc[mapping["mapping_role"].eq("production")].copy()
    strata = production.loc[production["regime_id"].notna()].copy()
    if strata.empty:
        raise RuntimeError("No regime-specific production mapping rows found")
    strata["regime_id"] = strata["regime_id"].astype(int)
    strata["mapping_support_class"] = strata["mapping_scope"].map(
        classify_mapping_scope
    )

    rows: list[dict[str, Any]] = []
    for (variable, regime_id), group in strata.groupby(
        ["variable", "regime_id"], sort=True
    ):
        scopes = group["mapping_scope"].dropna().astype(str).unique()
        classes = group["mapping_support_class"].dropna().astype(str).unique()
        if len(scopes) != 1 or len(classes) != 1:
            raise RuntimeError(
                f"Inconsistent production mapping scope for {variable}/R{regime_id}"
            )
        rows.append(
            {
                "variable": variable,
                "regime_id": int(regime_id),
                "mapping_scope": scopes[0],
                "mapping_support_class": classes[0],
                "calibration_quality": "|".join(
                    sorted(group["calibration_quality"].dropna().astype(str).unique())
                ),
                "mapping_evidence_quality": "|".join(
                    sorted(
                        group["mapping_evidence_quality"]
                        .dropna()
                        .astype(str)
                        .unique()
                    )
                ),
                "calibration_independent_blocks": int(
                    group["independent_blocks"].min()
                ),
                "calibration_exact_independent_blocks": int(
                    group["exact_independent_blocks"].min()
                ),
                "calibration_sample_size": int(group["sample_size"].min()),
                "calibration_exact_stratum_size": int(
                    group["exact_stratum_size"].min()
                ),
                "calibration_tail_precision_grade": _worst_precision(
                    group["percentile_precision_grade"]
                ),
                "subscore_count": int(group["subscore"].nunique()),
                "mapping_ids": "|".join(
                    sorted(group["mapping_id"].dropna().astype(str).unique())
                ),
            }
        )
    lookup = pd.DataFrame(rows)
    if not lookup["subscore_count"].eq(3).all():
        raise RuntimeError("Each production mapping stratum must contain three subscores")
    return lookup


def enrich_pair_hours(main: pd.DataFrame, lookup: pd.DataFrame) -> pd.DataFrame:
    frame = main.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"])
    frame["regime_id"] = pd.to_numeric(frame["regime_id"], errors="coerce").astype(
        "Int64"
    )
    frame = frame.merge(lookup, on=["variable", "regime_id"], how="left")
    frame["mapping_support_class"] = frame["mapping_support_class"].fillna(
        "insufficient"
    )
    frame["mapping_scope"] = frame["mapping_scope"].fillna("not_mapped")
    frame["D4_low_tail"] = (
        frame["usable_for_D4"].fillna(False)
        & frame["D4_raw"].notna()
        & frame["D4_raw"].lt(LOW_TAIL_THRESHOLD)
    )
    frame["month"] = frame["timestamp"].dt.to_period("M").astype(str)
    return frame


def composition_summary(
    frame: pd.DataFrame, group_columns: list[str]
) -> pd.DataFrame:
    result = (
        frame.groupby(group_columns + ["mapping_support_class"], observed=True)
        .agg(
            n_pair_hours=("timestamp", "size"),
            n_usable_pair_hours=("usable_for_D4", "sum"),
        )
        .reset_index()
    )
    denominators = result.groupby(group_columns)["n_pair_hours"].transform("sum")
    result["pair_hour_fraction"] = result["n_pair_hours"] / denominators
    return result


def outcome_summary(frame: pd.DataFrame) -> pd.DataFrame:
    usable = frame.loc[
        frame["usable_for_D4"].fillna(False) & frame["D4_raw"].notna()
    ].copy()
    return (
        usable.groupby(
            ["phase_id", "variable", "mapping_support_class"], observed=True
        )
        .agg(
            n_pair_hours=("timestamp", "size"),
            n_pairs=("pair_id", "nunique"),
            median_D4_raw=("D4_raw", "median"),
            p05_D4_raw=("D4_raw", lambda x: x.quantile(0.05)),
            p95_D4_raw=("D4_raw", lambda x: x.quantile(0.95)),
            low_tail_rate=("D4_low_tail", "mean"),
        )
        .reset_index()
    )


def extract_low_tail_events(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    usable = frame.loc[
        frame["usable_for_D4"].fillna(False) & frame["D4_raw"].notna()
    ].copy()
    for pair_id, group in usable.groupby("pair_id", sort=True):
        group = group.sort_values("timestamp").reset_index(drop=True)
        low = group["D4_raw"].lt(LOW_TAIL_THRESHOLD)
        new_run = (
            ~low.shift(fill_value=False)
            | group["timestamp"].diff().ne(pd.Timedelta(hours=1))
            | group["mapping_support_class"].ne(
                group["mapping_support_class"].shift()
            )
            | group["phase_id"].ne(group["phase_id"].shift())
        )
        run_id = new_run.cumsum()
        for _, event in group.loc[low].groupby(run_id[low]):
            rows.append(
                {
                    "pair_id": pair_id,
                    "variable": event["variable"].iloc[0],
                    "phase_id": event["phase_id"].iloc[0],
                    "mapping_support_class": event["mapping_support_class"].iloc[0],
                    "start": event["timestamp"].iloc[0],
                    "end": event["timestamp"].iloc[-1],
                    "duration_h": len(event),
                    "minimum_D4_raw": float(event["D4_raw"].min()),
                    "mean_D4_raw": float(event["D4_raw"].mean()),
                }
            )
    return pd.DataFrame(rows)


def event_summary(events: pd.DataFrame) -> pd.DataFrame:
    columns = ["phase_id", "variable", "mapping_support_class"]
    if events.empty:
        return pd.DataFrame(columns=columns)
    return (
        events.groupby(columns, observed=True)
        .agg(
            episode_count=("duration_h", "size"),
            median_duration_h=("duration_h", "median"),
            p95_duration_h=("duration_h", lambda x: x.quantile(0.95)),
            maximum_duration_h=("duration_h", "max"),
        )
        .reset_index()
    )


def pair_ranking_summary(frame: pd.DataFrame) -> pd.DataFrame:
    usable = frame.loc[
        frame["usable_for_D4"].fillna(False) & frame["D4_raw"].notna()
    ].copy()
    result = (
        usable.groupby(
            ["phase_id", "mapping_support_class", "pair_id", "variable"],
            observed=True,
        )
        .agg(
            n_pair_hours=("timestamp", "size"),
            median_D4_raw=("D4_raw", "median"),
            low_tail_rate=("D4_low_tail", "mean"),
        )
        .reset_index()
    )
    result["median_rank_within_phase_scope"] = result.groupby(
        ["phase_id", "mapping_support_class"]
    )["median_D4_raw"].rank(ascending=False, method="average")
    return result


def _write_workbook(path: Path, sheets: dict[str, pd.DataFrame]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for name, frame in sheets.items():
            frame.to_excel(writer, sheet_name=name[:31], index=False)


def make_figure(
    monthly: pd.DataFrame,
    phase: pd.DataFrame,
    outcomes: pd.DataFrame,
    events: pd.DataFrame,
    output_base: Path,
) -> None:
    configure_style()
    width_mm = 183.0
    height_mm = 128.0
    mpl.rcParams.update(
        {
            "font.family": "Arial",
            "font.size": 7.0,
            "svg.fonttype": "none",
            "pdf.fonttype": 42,
        }
    )
    fig, axes = plt.subplots(
        2, 2, figsize=(width_mm / 25.4, height_mm / 25.4)
    )

    ax = axes[0, 0]
    wide = monthly.pivot_table(
        index="month",
        columns="mapping_support_class",
        values="pair_hour_fraction",
        fill_value=0,
    ).reindex(columns=SCOPE_ORDER, fill_value=0)
    bottom = np.zeros(len(wide))
    for scope in SCOPE_ORDER:
        values = wide[scope].to_numpy(float)
        if np.any(values > 0):
            ax.bar(
                np.arange(len(wide)),
                values,
                bottom=bottom,
                width=0.78,
                color=SCOPE_COLORS[scope],
                label=scope.replace("_", " "),
            )
        bottom += values
    ax.set_xticks(np.arange(len(wide)), wide.index, rotation=45, ha="right")
    ax.set_ylim(0, 1)
    ax.set_ylabel("Pair-hour fraction")
    ax.set_title("Mapping support composition", loc="left")
    panel_label(ax, "a")

    ax = axes[0, 1]
    phase_wide = phase.pivot_table(
        index="phase_id",
        columns="mapping_support_class",
        values="pair_hour_fraction",
        fill_value=0,
    ).reindex(columns=SCOPE_ORDER, fill_value=0)
    x = np.arange(len(phase_wide))
    bottom = np.zeros(len(phase_wide))
    for scope in SCOPE_ORDER:
        values = phase_wide[scope].to_numpy(float)
        if np.any(values > 0):
            ax.bar(x, values, bottom=bottom, color=SCOPE_COLORS[scope], width=0.64)
        bottom += values
    ax.set_xticks(x, [value.replace("_", "\n") for value in phase_wide.index])
    ax.set_ylim(0, 1)
    ax.set_ylabel("Pair-hour fraction")
    ax.set_title("Prespecified phase comparison", loc="left")
    panel_label(ax, "b")

    ax = axes[1, 0]
    plot = outcomes.copy()
    categories = [
        (variable, scope)
        for variable in ("DO", "ORP")
        for scope in ("exact", "variable_fallback", "global_fallback")
        if not plot.loc[
            plot["variable"].eq(variable)
            & plot["mapping_support_class"].eq(scope)
        ].empty
    ]
    phase_order = ["development", "internal_validation"]
    for offset, phase_id in zip((-0.12, 0.12), phase_order):
        points = []
        for variable, scope in categories:
            row = plot.loc[
                plot["phase_id"].eq(phase_id)
                & plot["variable"].eq(variable)
                & plot["mapping_support_class"].eq(scope)
            ]
            points.append(row["low_tail_rate"].iloc[0] if len(row) else np.nan)
        ax.scatter(
            np.arange(len(categories)) + offset,
            points,
            s=20,
            color=PALETTE["blue"] if phase_id == "development" else PALETTE["orange"],
            label=phase_id.replace("_", " "),
            zorder=3,
        )
    ax.set_xticks(
        np.arange(len(categories)),
        [f"{variable}\n{scope.replace('_', ' ')}" for variable, scope in categories],
    )
    ax.set_ylabel("D4 < 3 pair-hour rate")
    ax.set_ylim(bottom=0)
    ax.set_title("Low-tail burden by support class", loc="left")
    ax.legend(loc="best")
    panel_label(ax, "c")

    ax = axes[1, 1]
    event_plot = events.loc[
        events["phase_id"].isin(phase_order)
        & events["mapping_support_class"].isin(
            ["exact", "variable_fallback", "global_fallback"]
        )
    ].copy()
    if event_plot.empty:
        ax.text(0.5, 0.5, "No D4 < 3 episodes", ha="center", va="center")
        ax.set_axis_off()
    else:
        event_plot["label"] = (
            event_plot["variable"]
            + "\n"
            + event_plot["mapping_support_class"].str.replace("_", " ")
        )
        labels = event_plot["label"].drop_duplicates().tolist()
        for offset, phase_id in zip((-0.12, 0.12), phase_order):
            group = event_plot.loc[event_plot["phase_id"].eq(phase_id)].set_index(
                "label"
            )
            median = np.array(
                [group.loc[label, "median_duration_h"] if label in group.index else np.nan for label in labels],
                dtype=float,
            )
            p95 = np.array(
                [group.loc[label, "p95_duration_h"] if label in group.index else np.nan for label in labels],
                dtype=float,
            )
            ax.vlines(
                np.arange(len(labels)) + offset,
                median,
                p95,
                color=PALETTE["blue"] if phase_id == "development" else PALETTE["orange"],
                lw=1.0,
            )
            ax.scatter(
                np.arange(len(labels)) + offset,
                median,
                s=20,
                color=PALETTE["blue"] if phase_id == "development" else PALETTE["orange"],
                zorder=3,
            )
        ax.set_xticks(np.arange(len(labels)), labels)
        ax.set_ylabel("Episode duration (h)\npoint: median; line: P95")
        ax.set_title("Low-tail episode persistence", loc="left")
    panel_label(ax, "d")

    handles = [
        plt.Line2D(
            [0],
            [0],
            marker="s",
            linestyle="none",
            markersize=6,
            markerfacecolor=SCOPE_COLORS[scope],
            markeredgecolor="none",
            label=scope.replace("_", " "),
        )
        for scope in SCOPE_ORDER
        if scope in monthly["mapping_support_class"].unique()
    ]
    fig.legend(handles=handles, loc="upper center", ncol=len(handles), bbox_to_anchor=(0.5, 0.99))
    fig.subplots_adjust(left=0.10, right=0.98, bottom=0.13, top=0.88, wspace=0.34, hspace=0.44)
    output_base.parent.mkdir(parents=True, exist_ok=True)
    finalize(fig)
    svg_path = output_base.with_suffix(".svg")
    fig.savefig(svg_path, bbox_inches="tight")
    svg_path.write_text(
        "\n".join(
            line.rstrip()
            for line in svg_path.read_text(encoding="utf-8").splitlines()
        )
        + "\n",
        encoding="utf-8",
    )
    fig.savefig(output_base.with_suffix(".pdf"), bbox_inches="tight")
    fig.savefig(output_base.with_suffix(".png"), dpi=600, bbox_inches="tight")
    fig.savefig(
        output_base.with_suffix(".tiff"),
        dpi=600,
        bbox_inches="tight",
        pil_kwargs={"compression": "tiff_lzw"},
    )
    plt.close(fig)


def run_mapping_support_audit(
    main_path: Path,
    mapping_path: Path,
    output_root: Path,
) -> dict[str, pd.DataFrame]:
    main = pd.read_excel(main_path, sheet_name="main_scores")
    mapping = pd.read_excel(mapping_path, sheet_name="public_quantiles")
    lookup = build_mapping_lookup(mapping)
    enriched = enrich_pair_hours(main, lookup)
    monthly = composition_summary(enriched, ["month"])
    phase = composition_summary(enriched, ["phase_id"])
    phase_variable = composition_summary(enriched, ["phase_id", "variable"])
    outcomes = outcome_summary(enriched)
    events = extract_low_tail_events(enriched)
    event_stats = event_summary(events)
    rankings = pair_ranking_summary(enriched)

    data_root = output_root / "data"
    figure_root = output_root / "figures"
    report_root = output_root / "reports"
    manifest_root = output_root / "manifests"
    source_root = output_root / "source_data"
    for path in (data_root, figure_root, report_root, manifest_root, source_root):
        path.mkdir(parents=True, exist_ok=True)

    outputs = {
        "mapping_lookup": lookup,
        "monthly_composition": monthly,
        "phase_composition": phase,
        "phase_variable_composition": phase_variable,
        "outcome_summary": outcomes,
        "events": events,
        "event_summary": event_stats,
        "pair_ranking": rankings,
    }
    enriched.to_parquet(data_root / "D4_pair_hours_with_mapping_support.parquet", index=False)
    for name, frame in outputs.items():
        frame.to_parquet(data_root / f"D4_{name}.parquet", index=False)
    _write_workbook(
        data_root / "D4_mapping_support_migration_audit.xlsx", outputs
    )
    _write_workbook(
        source_root / "D4_mapping_support_migration_figure_source_data.xlsx",
        {
            "monthly": monthly,
            "phase": phase,
            "outcomes": outcomes,
            "events": event_stats,
        },
    )
    make_figure(
        monthly,
        phase,
        outcomes,
        event_stats,
        figure_root / "D4_MappingSupportMigration",
    )

    exact_rate = float(
        enriched["mapping_support_class"].eq("exact").mean()
    )
    fallback_rate = float(
        enriched["mapping_support_class"].isin(
            ["variable_fallback", "global_fallback"]
        ).mean()
    )
    global_rate = float(
        enriched["mapping_support_class"].eq("global_fallback").mean()
    )
    report = [
        "# D4 mapping-support migration audit",
        "",
        "This audit separates score magnitude from mapping evidence maturity. It is descriptive and does not modify D4_raw, mapping thresholds, report eligibility or pair ranking rules.",
        "",
        f"- Exact variable-regime mapping: {exact_rate:.1%} of pair-hours.",
        f"- Variable/global fallback mapping: {fallback_rate:.1%} of pair-hours.",
        f"- Global fallback mapping: {global_rate:.1%} of pair-hours.",
        "- Fallback evidence is retained as metadata; exclusion from a future formal estimand requires a prospectively frozen rule and new validation data.",
        "- Event runs are broken at mapping-scope, phase and timestamp discontinuities, preventing artificial cross-boundary episode merging.",
    ]
    stable_months = monthly.loc[
        monthly["month"].between("2025-10", "2026-03")
        & monthly["mapping_support_class"].eq("exact"),
        "pair_hour_fraction",
    ]
    if len(stable_months):
        report.append(
            f"- Exact-mapping share was stable at {stable_months.min():.1%}-"
            f"{stable_months.max():.1%} from 2025-10 through 2026-03; the lower pooled "
            "validation exact share therefore reflects regime composition rather than a "
            "new late-period fallback expansion."
        )
    report.extend(
        [
            "- ORP variable-fallback rows showed greater validation low-tail burden and longer tail episodes than their development counterpart. Exact and fallback strata correspond to different regimes, so this is a stratified descriptive signal, not an estimate of a causal fallback penalty.",
            "- No global fallback was used. The small insufficient class is retained as non-comparable evidence rather than imputed or scored down.",
        ]
    )
    (report_root / "D4_mapping_support_migration_audit.md").write_text(
        "\n".join(report) + "\n", encoding="utf-8"
    )

    artifacts = []
    for path in sorted(output_root.rglob("*")):
        if path.is_file() and path.name != "D4_mapping_support_audit_manifest.json":
            artifacts.append(
                {
                    "relative_path": path.relative_to(output_root).as_posix(),
                    "sha256": sha256_file(path),
                    "size_bytes": path.stat().st_size,
                }
            )
    manifest = {
        "audit_id": "D4-MAPPING-SUPPORT-AUDIT-v1.0",
        "claim_boundary": "descriptive_mapping_evidence_audit_no_score_recalibration",
        "low_tail_threshold": LOW_TAIL_THRESHOLD,
        "inputs": {
            "D4_main_scores_sha256": sha256_file(main_path),
            "D4_mapping_params_sha256": sha256_file(mapping_path),
        },
        "summary": {
            "n_pair_hours": len(enriched),
            "exact_pair_hour_rate": exact_rate,
            "fallback_pair_hour_rate": fallback_rate,
            "global_fallback_pair_hour_rate": global_rate,
        },
        "artifacts": artifacts,
    }
    manifest_root.joinpath("D4_mapping_support_audit_manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=True), encoding="utf-8"
    )
    return {"enriched": enriched, **outputs}
