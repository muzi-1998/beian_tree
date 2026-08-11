from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .common import PROJECT_ROOT, event_jaccard, read_yaml


D3_ROOT = PROJECT_ROOT / "D3 Physical rationality and rate constraints"


def _read_current_evidence() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    data = D3_ROOT / "outputs" / "data"
    main = pd.read_excel(data / "D3_window_scores.xlsx")
    value = pd.read_excel(data / "D3_value_evidence.xlsx")
    rate = pd.read_excel(data / "D3_rate_evidence.xlsx")
    boundary = pd.read_excel(data / "D3_boundary_diagnostics.xlsx")
    for frame in (main, value, rate, boundary):
        frame["ts"] = pd.to_datetime(frame["ts"])
    return main, value, rate, boundary


def build_safety_gate() -> pd.DataFrame:
    main, value, rate, boundary = _read_current_evidence()
    gate = (
        main.merge(value, on=["ts", "sensor_id", "run_id"], suffixes=("", "_value"))
        .merge(rate, on=["ts", "sensor_id", "run_id"], suffixes=("", "_rate"))
        .merge(
            boundary[
                [
                    "ts",
                    "sensor_id",
                    "boundary_sticking_rate",
                    "boundary_dominant_reason",
                ]
            ],
            on=["ts", "sensor_id"],
            how="left",
        )
    )
    gate["D3_hard_fail"] = gate["data_veto_flag"].fillna(False).astype(bool)
    gate["D3_soft_warning"] = (
        gate["hard_violation_count"].gt(0) | gate["soft_violation_count"].gt(0)
    )
    gate["D3_zero_equivalent_present"] = gate["zero_equivalent_count"].gt(0)
    gate["D3_zero_offset_warning"] = gate["zero_offset_warning_count"].gt(0)
    gate["D3_rate_warning"] = (
        gate["rate_soft_violation_rate"].gt(0)
        | gate["rate_hard_violation_rate"].gt(0)
    )
    gate["D3_process_coherence_guard"] = gate[
        "process_coherence_guarded_points"
    ].gt(0)
    gate["D3_boundary_diagnostic"] = gate["boundary_sticking_rate"].ge(0.90)
    gate["D3_gate_status"] = gate["D3_gate_status"].fillna("NotEvaluated")
    gate["D3_total_legacy"] = gate["D3_total"]
    gate["threshold_source"] = np.select(
        [
            gate["D3_hard_fail"],
            gate["D3_soft_warning"],
            gate["D3_rate_warning"],
        ],
        [
            "verified_installation_register",
            "versioned_expert_operational_rule",
            "provisional_persistent_same_sign_rate_rule",
        ],
        default="none",
    )
    gate["evidence_grade"] = np.where(gate["D3_hard_fail"], "A", "B")
    gate["gate_reason"] = np.select(
        [
            gate["D3_hard_fail"],
            gate["D3_soft_warning"] & gate["D3_rate_warning"],
            gate["D3_soft_warning"],
            gate["D3_rate_warning"],
        ],
        [
            "instrument_range",
            "process_value_and_rate_warning",
            "process_value_warning",
            "rate_warning",
        ],
        default="none",
    )
    gate["window_start"] = gate["ts"] - pd.to_timedelta(
        gate["window_min"], unit="min"
    )
    gate["window_end_exclusive"] = gate["ts"]
    gate["timestamp_role"] = "window_end_exclusive"
    columns = [
        "ts",
        "sensor_id",
        "window_min",
        "window_start",
        "window_end_exclusive",
        "timestamp_role",
        "D3_gate_status",
        "D3_hard_fail",
        "D3_soft_warning",
        "D3_zero_equivalent_present",
        "D3_zero_offset_warning",
        "D3_rate_warning",
        "D3_boundary_diagnostic",
        "D3_process_coherence_guard",
        "gate_reason",
        "threshold_source",
        "evidence_grade",
        "D3_total_legacy",
        "run_id",
    ]
    return gate[columns].rename(columns={"ts": "timestamp"})


def build_threshold_register() -> pd.DataFrame:
    thresholds = pd.read_excel(D3_ROOT / "outputs" / "data" / "D3_threshold_library.xlsx")
    bounds = read_yaml(D3_ROOT / "configs" / "d3_physical_bounds.yaml")
    instrument_rows = []
    for sensor_type, definition in bounds["sensors"].items():
        instrument_rows.append(
            {
                "threshold_id": f"INST-{sensor_type}",
                "sensor_type": sensor_type,
                "sensor_scope": f"all_{sensor_type}",
                "condition_scope": "all_observed_conditions",
                "bound_type": "instrument_range",
                "low": definition["manufacturer_range_low"],
                "high": definition["manufacturer_range_high"],
                "unit": definition["unit"],
                "source": bounds["sources"]["instrument_register"]["source_id"],
                "version": bounds["version"],
                "included_in_D3_score": False,
                "validator_passed": True,
                "evidence_grade": "A",
                "approval_status": "register_verified",
                "aggregation_effect": "non_compensatory_fail",
            }
        )
    thresholds["evidence_grade"] = "B"
    thresholds["approval_status"] = np.where(
        thresholds["source"].astype(str).str.contains("expert", case=False),
        "pending_site_expert_approval",
        "versioned_source_present",
    )
    thresholds["aggregation_effect"] = "warning_only"
    common = sorted(set(thresholds.columns) | set(pd.DataFrame(instrument_rows).columns))
    return pd.concat(
        [
            thresholds.reindex(columns=common),
            pd.DataFrame(instrument_rows).reindex(columns=common),
        ],
        ignore_index=True,
    )


def run_d3_sensitivity(output_dir: Path) -> dict[str, pd.DataFrame]:
    gate = build_safety_gate()
    threshold_register = build_threshold_register()
    sensitivity_path = D3_ROOT / "outputs" / "validation" / "D3_threshold_sensitivity.xlsx"
    canonical_summary = pd.read_excel(sensitivity_path, sheet_name="summary")
    canonical_detail = pd.read_excel(sensitivity_path, sheet_name="sampled_windows")
    parameter_names = {
        "operational_soft_envelope_width": "soft_boundary_multiplier",
        "persistent_rate_limit": "rate_threshold_multiplier",
    }
    oat_summary = canonical_summary.rename(
        columns={"multiplier": "setting"}
    ).copy()
    oat_summary["parameter"] = oat_summary["parameter"].map(parameter_names)
    oat_summary["is_primary"] = oat_summary["setting"].eq(1.0)
    oat_summary["baseline_warning_windows"] = oat_summary["baseline_events"]
    oat_summary["variant_warning_windows"] = oat_summary["variant_events"]
    oat_summary["warning_burden_change"] = (
        oat_summary["variant_events"] - oat_summary["baseline_events"]
    )
    oat_summary["analysis_unit"] = "stratified_monthly_nonoverlap_2h_sensor_window"
    oat_summary["stable_at_jaccard_0_75"] = oat_summary["event_jaccard"].ge(0.75)
    versions = canonical_detail["sensitivity_code_version"].dropna().unique()
    if len(versions) != 1:
        raise ValueError(f"D3 sensitivity must have one canonical code version; got {versions}")
    oat_summary["sensitivity_code_version"] = versions[0]

    sensor_rows = []
    for canonical_parameter, parameter_frame in canonical_detail.groupby("parameter"):
        event_column = (
            "warning"
            if canonical_parameter == "operational_soft_envelope_width"
            else "persistent_event"
        )
        baseline = parameter_frame.loc[
            parameter_frame["multiplier"].eq(1.0),
            ["timestamp", "sensor_id", event_column],
        ].rename(columns={event_column: "warning_baseline"})
        for setting, variant in parameter_frame.groupby("multiplier"):
            merged = variant.merge(
                baseline, on=["timestamp", "sensor_id"], how="inner"
            ).rename(columns={event_column: "warning_variant"})
            grouped = (
                merged.groupby("sensor_id", as_index=False)
                .agg(
                    baseline_warning_windows=("warning_baseline", "sum"),
                    variant_warning_windows=("warning_variant", "sum"),
                )
            )
            grouped["parameter"] = parameter_names[canonical_parameter]
            grouped["setting"] = float(setting)
            grouped["sensitivity_code_version"] = versions[0]
            grouped["event_jaccard"] = grouped.apply(
                lambda row: event_jaccard(
                    merged.loc[merged["sensor_id"].eq(row["sensor_id"]), "warning_baseline"],
                    merged.loc[merged["sensor_id"].eq(row["sensor_id"]), "warning_variant"],
                ),
                axis=1,
            )
            sensor_rows.append(grouped)

    oat_by_sensor = pd.concat(sensor_rows, ignore_index=True)
    outputs = {
        "D3_safety_gate": gate,
        "D3_threshold_register_v2": threshold_register,
        "D3_oat_summary": oat_summary,
        "D3_oat_by_sensor": oat_by_sensor,
    }
    for name, frame in outputs.items():
        frame.to_parquet(output_dir / f"{name}.parquet", index=False)
    return outputs
