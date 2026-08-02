from __future__ import annotations

import pickle
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import ks_2samp, wasserstein_distance

from .common import CONFIG_ROOT, PROJECT_ROOT, read_yaml


D2_ROOT = PROJECT_ROOT / "D2 Temporal Continuity & Information Availability"
D5_ROOT = (
    PROJECT_ROOT
    / "D5 Topological Role Consistency and Structural Representativeness"
)
RAW_PATH = (
    PROJECT_ROOT
    / "1.1 Decomposition"
    / "outputs"
    / "parquet"
    / "time_base_1min_raw.parquet"
)


def _standardized_mean_difference(
    full: np.ndarray,
    basic: np.ndarray,
) -> float:
    pooled_variance = (
        np.nanvar(full, ddof=1) + np.nanvar(basic, ddof=1)
    ) / 2.0
    if not np.isfinite(pooled_variance) or pooled_variance <= 0:
        return 0.0 if np.isclose(np.nanmean(full), np.nanmean(basic)) else np.nan
    return float((np.nanmean(full) - np.nanmean(basic)) / np.sqrt(pooled_variance))


def _hourly_raw_long(sensor_ids: list[str]) -> pd.DataFrame:
    raw = pd.read_parquet(RAW_PATH, columns=sensor_ids)
    frames = []
    for sensor_id in sensor_ids:
        hourly_value = raw[sensor_id].resample("1h").median()
        missing_rate = raw[sensor_id].isna().resample("1h").mean()
        center = float(hourly_value.median())
        mad = float((hourly_value - center).abs().median())
        scale = max(1.4826 * mad, np.finfo(float).eps)
        frames.append(
            pd.DataFrame(
                {
                    "timestamp": hourly_value.index,
                    "sensor_id": sensor_id,
                    "raw_value": hourly_value.to_numpy(),
                    "raw_value_sensor_z": (
                        (hourly_value - center) / scale
                    ).to_numpy(),
                    "missing_rate": missing_rate.to_numpy(),
                }
            )
        )
    return pd.concat(frames, ignore_index=True)


def _process_floor_hourly() -> pd.DataFrame:
    with (D2_ROOT / "artifacts" / "d2_state.pkl").open("rb") as handle:
        state = pickle.load(handle)
    frames = []
    for sensor_id in ("DO_1_4", "DO_2_4"):
        frame = state["subs_all"][sensor_id][
            ["floor_occupancy", "resolution_limited"]
        ].copy()
        frame.insert(0, "sensor_id", sensor_id)
        frame.insert(0, "timestamp", frame.index)
        frames.append(frame.reset_index(drop=True))
    return pd.concat(frames, ignore_index=True)


def _build_audit(node: pd.DataFrame) -> pd.DataFrame:
    audit = node.copy()
    audit["timestamp"] = pd.to_datetime(audit["timestamp"])
    context = pd.read_parquet(
        D5_ROOT / "outputs" / "local" / "D5_main_scores_hourly.parquet",
        columns=[
            "timestamp",
            "sensor_id",
            "analyte",
            "line_id",
            "zone_id",
            "position_order",
            "active_regime_id",
            "ood_distance",
            "regime_state",
            "status_reason",
            "family_support_level",
            "node_support_level",
        ],
    )
    context["timestamp"] = pd.to_datetime(context["timestamp"])
    audit = audit.merge(
        context,
        on=["timestamp", "sensor_id"],
        how="left",
        validate="one_to_one",
    )
    sensor_ids = sorted(audit["sensor_id"].dropna().unique())
    audit = audit.merge(
        _hourly_raw_long(sensor_ids),
        on=["timestamp", "sensor_id"],
        how="left",
        validate="one_to_one",
    )
    audit = audit.merge(
        _process_floor_hourly(),
        on=["timestamp", "sensor_id"],
        how="left",
        validate="one_to_one",
    )
    audit["month"] = audit["timestamp"].dt.to_period("M").astype(str)
    audit["process_position"] = (
        audit["zone_id"].fillna("unknown").astype(str)
        + "|P"
        + audit["position_order"].fillna(-1).astype(int).astype(str)
    )
    audit["ood_status"] = np.where(
        audit["regime_state"].eq("OODHold"),
        "OOD",
        "not_OOD",
    )
    audit["D3_warn"] = audit["D3_gate_status"].eq("Warn").astype(float)
    audit["process_floor_sensor"] = audit["sensor_id"].isin(
        ["DO_1_4", "DO_2_4"]
    )
    audit["process_floor_occupancy"] = audit["floor_occupancy"]
    audit["month_sensor"] = audit["month"] + "|" + audit["sensor_id"]
    audit["missing_dimension_pattern"] = (
        "D1="
        + audit["evaluable_D1"].astype(int).astype(str)
        + "|D2="
        + audit["evaluable_D2"].astype(int).astype(str)
        + "|D5="
        + audit["evaluable_D5"].astype(int).astype(str)
    )
    return audit


def _coverage_strata(
    audit: pd.DataFrame,
    strata: list[str],
) -> pd.DataFrame:
    frames = []
    for stratum in strata:
        frame = audit[[stratum, "coverage_class"]].copy()
        frame[stratum] = frame[stratum].fillna("missing").astype(str)
        grouped = (
            frame.groupby([stratum, "coverage_class"], as_index=False)
            .size()
            .rename(columns={stratum: "stratum_value", "size": "sensor_hours"})
        )
        grouped.insert(0, "stratum", stratum)
        grouped["within_stratum_fraction"] = grouped["sensor_hours"] / grouped.groupby(
            "stratum_value"
        )["sensor_hours"].transform("sum")
        grouped["within_coverage_fraction"] = grouped["sensor_hours"] / grouped.groupby(
            "coverage_class"
        )["sensor_hours"].transform("sum")
        frames.append(grouped)
    return pd.concat(frames, ignore_index=True)


def _balance_table(
    audit: pd.DataFrame,
    *,
    metrics: list[str],
    conditional_groups: list[str],
    minimum_hours: int,
    material_threshold: float,
) -> pd.DataFrame:
    rows = []
    group_specs = [("overall", pd.Series("all", index=audit.index))]
    group_specs.extend(
        (column, audit[column].fillna("missing").astype(str))
        for column in conditional_groups
    )
    for group_type, labels in group_specs:
        for group_value in labels.drop_duplicates():
            frame = audit[labels.eq(group_value)]
            for metric in metrics:
                full = frame.loc[
                    frame["coverage_class"].eq("full"),
                    metric,
                ].dropna().to_numpy(float)
                basic = frame.loc[
                    frame["coverage_class"].eq("basic"),
                    metric,
                ].dropna().to_numpy(float)
                if min(len(full), len(basic)) < minimum_hours:
                    continue
                smd = _standardized_mean_difference(full, basic)
                rows.append(
                    {
                        "group_type": group_type,
                        "group_value": str(group_value),
                        "metric": metric,
                        "n_full": len(full),
                        "n_basic": len(basic),
                        "mean_full": float(np.mean(full)),
                        "mean_basic": float(np.mean(basic)),
                        "difference_full_minus_basic": float(
                            np.mean(full) - np.mean(basic)
                        ),
                        "standardized_mean_difference": smd,
                        "absolute_smd": abs(smd) if np.isfinite(smd) else np.nan,
                        "material_abs_smd": bool(
                            np.isfinite(smd) and abs(smd) >= material_threshold
                        ),
                        "wasserstein_distance": float(
                            wasserstein_distance(full, basic)
                        ),
                        "ks_statistic_descriptive": float(
                            ks_2samp(full, basic).statistic
                        ),
                        "inference_role": (
                            "selection_balance_effect_size;"
                            "Wasserstein_and_KS_descriptive_only"
                        ),
                    }
                )
    return pd.DataFrame(rows)


def _monthly_paired_bootstrap(
    balance: pd.DataFrame,
    *,
    repetitions: int,
    rng: np.random.Generator,
) -> pd.DataFrame:
    rows = []
    monthly = balance[balance["group_type"].eq("month")].copy()
    for metric, frame in monthly.groupby("metric"):
        values = frame["difference_full_minus_basic"].to_numpy(float)
        if len(values) == 0:
            continue
        draws = np.empty(repetitions, dtype=float)
        for index in range(repetitions):
            sample = values[rng.integers(0, len(values), size=len(values))]
            draws[index] = float(np.mean(sample))
        rows.append(
            {
                "metric": metric,
                "mean_monthly_paired_difference_full_minus_basic": float(
                    np.mean(values)
                ),
                "ci95_low": float(np.quantile(draws, 0.025)),
                "ci95_high": float(np.quantile(draws, 0.975)),
                "n_paired_months": len(values),
                "analysis_unit": "calendar_month",
                "ci_method": "paired_calendar_month_cluster_bootstrap",
            }
        )
    return pd.DataFrame(rows)


def _selection_summary(
    audit: pd.DataFrame,
    strata: pd.DataFrame,
    balance: pd.DataFrame,
) -> pd.DataFrame:
    counts = audit["coverage_class"].value_counts()

    def coverage_share(stratum: str, value: str, coverage: str) -> float:
        selected = strata[
            strata["stratum"].eq(stratum)
            & strata["stratum_value"].eq(value)
            & strata["coverage_class"].eq(coverage)
        ]
        return (
            float(selected["within_coverage_fraction"].iloc[0])
            if not selected.empty
            else 0.0
        )

    overall = balance[balance["group_type"].eq("overall")]
    material = overall[overall["material_abs_smd"]]
    full_months = strata[
        strata["stratum"].eq("month")
        & strata["coverage_class"].eq("full")
    ]
    all_months = audit["month"].nunique()
    rows = [
        {
            "indicator": "full_sensor_hours",
            "value": int(counts.get("full", 0)),
            "interpretation": "complete D1-D2-D5 evidence subset",
        },
        {
            "indicator": "basic_sensor_hours",
            "value": int(counts.get("basic", 0)),
            "interpretation": "two-dimension extension subset",
        },
        {
            "indicator": "basic_OOD_share",
            "value": coverage_share("ood_status", "OOD", "basic"),
            "interpretation": "OOD concentration within Basic",
        },
        {
            "indicator": "full_OOD_share",
            "value": coverage_share("ood_status", "OOD", "full"),
            "interpretation": "OOD concentration within Full",
        },
        {
            "indicator": "basic_L1_share",
            "value": coverage_share("support_level", "L1", "basic"),
            "interpretation": "lowest D5 support concentration within Basic",
        },
        {
            "indicator": "full_L1_share",
            "value": coverage_share("support_level", "L1", "full"),
            "interpretation": "lowest D5 support concentration within Full",
        },
        {
            "indicator": "months_without_full_coverage",
            "value": int(all_months - full_months["stratum_value"].nunique()),
            "interpretation": "temporal coverage limitation",
        },
        {
            "indicator": "material_overall_balance_metrics",
            "value": int(len(material)),
            "interpretation": ",".join(material["metric"]) or "none",
        },
    ]
    return pd.DataFrame(rows)


def _write_conclusion(
    output_dir: Path,
    summary: pd.DataFrame,
    balance: pd.DataFrame,
) -> Path:
    values = summary.set_index("indicator")["value"]
    overall = balance[balance["group_type"].eq("overall")].set_index("metric")
    d1_smd = float(overall.loc["D1_total", "standardized_mean_difference"])
    d2_smd = float(overall.loc["D2_total", "standardized_mean_difference"])
    conclusion = [
        "# D5 coverage-selection limitation",
        "",
        "## Confirmatory conclusion",
        "",
        f"Full coverage contains {int(values['full_sensor_hours']):,} sensor-hours and "
        f"Basic contains {int(values['basic_sensor_hours']):,}. "
        f"Basic includes {float(values['basic_OOD_share']):.1%} OOD hours versus "
        f"{float(values['full_OOD_share']):.1%} in Full, and "
        f"{float(values['basic_L1_share']):.1%} L1-support hours versus "
        f"{float(values['full_L1_share']):.1%} in Full.",
        "",
        f"The pooled standardized Full-minus-Basic differences are {d1_smd:.3f} "
        f"for D1 and {d2_smd:.3f} for D2. "
        f"{int(values['months_without_full_coverage'])} calendar months have no "
        "Full observations.",
        "",
        "Full is therefore a complete-evidence subset selected by calendar time, "
        "regime/OOD state and D5 support. It must be reported as the primary "
        "complete-case estimand and must not be generalized to all sensor-hours. "
        "Basic remains a separately labelled extension analysis; Limited and "
        "Insufficient rows are excluded from formal composite comparisons.",
        "",
        "Wasserstein distance and KS statistics are descriptive diagnostics only. "
        "This audit does not alter D5 scores or production eligibility.",
    ]
    path = output_dir / "D5_COVERAGE_LIMITATION_CONCLUSION.md"
    path.write_text("\n".join(conclusion) + "\n", encoding="utf-8")
    return path


def run_coverage_selection(
    output_dir: Path,
    node: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    design = read_yaml(CONFIG_ROOT / "validation_design.yaml")["D5"][
        "coverage_selection"
    ]
    sap = read_yaml(CONFIG_ROOT / "statistical_analysis_plan_v2.yaml")
    repetitions = int(sap["uncertainty"]["repetitions"])
    rng = np.random.default_rng(int(sap["uncertainty"]["seed"]))
    audit = _build_audit(node)
    strata = _coverage_strata(audit, list(design["strata"]))
    balance = _balance_table(
        audit,
        metrics=list(design["balance_metrics"]),
        conditional_groups=list(design["conditional_groups"]),
        minimum_hours=int(design["minimum_hours_per_coverage_group"]),
        material_threshold=float(design["material_smd_threshold"]),
    )
    paired = _monthly_paired_bootstrap(
        balance,
        repetitions=repetitions,
        rng=rng,
    )
    summary = _selection_summary(audit, strata, balance)

    audit.to_parquet(
        output_dir / "D5_coverage_selection_audit.parquet",
        index=False,
    )
    with pd.ExcelWriter(
        output_dir / "D5_full_basic_balance_table.xlsx",
        engine="openpyxl",
    ) as writer:
        strata.to_excel(writer, sheet_name="coverage_strata", index=False)
        balance.to_excel(writer, sheet_name="conditional_balance", index=False)
        paired.to_excel(writer, sheet_name="monthly_paired_CI", index=False)
        summary.to_excel(writer, sheet_name="selection_summary", index=False)
    _write_conclusion(output_dir, summary, balance)

    outputs = {
        "D5_coverage_selection_audit": audit,
        "D5_coverage_strata": strata,
        "D5_full_basic_balance": balance,
        "D5_monthly_paired_balance": paired,
        "D5_coverage_selection_summary": summary,
    }
    for name, frame in outputs.items():
        if name != "D5_coverage_selection_audit":
            frame.to_parquet(output_dir / f"{name}.parquet", index=False)
    return outputs
