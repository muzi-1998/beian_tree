from __future__ import annotations

import pickle
from pathlib import Path

import numpy as np
import pandas as pd

from .common import CONFIG_ROOT, PROJECT_ROOT, event_jaccard, read_yaml


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
    gate["D3_hard_fail"] = gate["out_of_instrument"].fillna(False).astype(bool)
    gate["D3_soft_warning"] = (
        gate["hard_violation_count"].gt(0) | gate["soft_violation_count"].gt(0)
    )
    gate["D3_rate_warning"] = (
        gate["rate_soft_violation_rate"].gt(0)
        | gate["rate_hard_violation_rate"].gt(0)
    )
    gate["D3_boundary_diagnostic"] = gate["boundary_sticking_rate"].ge(0.90)
    gate["D3_gate_status"] = np.select(
        [
            gate["D3_hard_fail"],
            gate["D3_soft_warning"] | gate["D3_rate_warning"],
        ],
        ["Fail", "Warn"],
        default="Pass",
    )
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
            "versioned_robust_rate_rule",
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
        "D3_rate_warning",
        "D3_boundary_diagnostic",
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


def _window_warning_mask(
    raw: pd.DataFrame,
    evidence: pd.DataFrame,
    *,
    soft_multiplier: float = 1.0,
    rate_multiplier: float = 1.0,
) -> pd.DataFrame:
    rows = []
    for record in evidence.itertuples(index=False):
        end = pd.Timestamp(record.ts)
        start = end - pd.Timedelta(minutes=int(record.window_min))
        values = raw.loc[start:end, record.sensor_id].dropna().to_numpy(dtype=float)
        if not len(values):
            warning = False
        else:
            soft_low = float(record.soft_low) * soft_multiplier
            soft_high = float(record.soft_high) * soft_multiplier
            value_warning = bool(((values < soft_low) | (values > soft_high)).any())
            rate_limit = float(record.rate_limit_soft) * rate_multiplier
            rate_warning = bool((np.abs(np.diff(values)) > rate_limit).any())
            warning = value_warning or rate_warning
        rows.append(
            {
                "timestamp": end,
                "sensor_id": record.sensor_id,
                "warning": warning,
            }
        )
    return pd.DataFrame(rows)


def run_d3_sensitivity(output_dir: Path) -> dict[str, pd.DataFrame]:
    gate = build_safety_gate()
    threshold_register = build_threshold_register()
    main, value, rate, _ = _read_current_evidence()
    evidence = (
        main[["ts", "sensor_id", "window_min"]]
        .merge(
            value[["ts", "sensor_id", "soft_low", "soft_high"]],
            on=["ts", "sensor_id"],
        )
        .merge(
            rate[["ts", "sensor_id", "rate_limit_soft"]],
            on=["ts", "sensor_id"],
        )
    )
    with (PROJECT_ROOT / "1.1 Decomposition" / "outputs" / "_w2_checkpoint.pkl").open("rb") as handle:
        raw = pickle.load(handle)["out"]["df_min"]
    design = read_yaml(CONFIG_ROOT / "validation_design.yaml")["D3"]
    baseline = _window_warning_mask(raw, evidence)
    summaries = []
    sensor_rows = []
    for parameter, settings in (
        ("soft_boundary_multiplier", design["soft_boundary_multipliers"]),
        ("rate_threshold_multiplier", design["rate_threshold_multipliers"]),
    ):
        for setting in settings:
            kwargs = (
                {"soft_multiplier": float(setting)}
                if parameter.startswith("soft")
                else {"rate_multiplier": float(setting)}
            )
            variant = _window_warning_mask(raw, evidence, **kwargs)
            merged = baseline.merge(
                variant,
                on=["timestamp", "sensor_id"],
                suffixes=("_baseline", "_variant"),
            )
            summary = {
                "parameter": parameter,
                "setting": float(setting),
                "is_primary": float(setting) == 1.0,
                "event_jaccard": event_jaccard(
                    merged["warning_baseline"],
                    merged["warning_variant"],
                ),
                "baseline_warning_windows": int(merged["warning_baseline"].sum()),
                "variant_warning_windows": int(merged["warning_variant"].sum()),
                "warning_burden_change": int(
                    merged["warning_variant"].sum() - merged["warning_baseline"].sum()
                ),
                "analysis_unit": "nonoverlap_2h_sensor_window",
            }
            summaries.append(summary)
            grouped = (
                merged.groupby("sensor_id", as_index=False)
                .agg(
                    baseline_warning_windows=("warning_baseline", "sum"),
                    variant_warning_windows=("warning_variant", "sum"),
                )
            )
            grouped["parameter"] = parameter
            grouped["setting"] = float(setting)
            sensor_rows.append(grouped)

    oat_summary = pd.DataFrame(summaries)
    oat_summary["stable_at_jaccard_0_75"] = oat_summary["event_jaccard"].ge(0.75)
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
