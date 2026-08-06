"""Export the D3 v2.2 evidence, diagnostics, scores, and audit tables."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.version import THRESHOLD_VERSION


def export_all(
    results: dict,
    thresholds_df: pd.DataFrame,
    mapping_cfg: dict,
    profile_df: pd.DataFrame,
    outdir: Path,
) -> list[Path]:
    outdir.mkdir(parents=True, exist_ok=True)
    paths = {
        "scores": outdir / "D3_window_scores.xlsx",
        "value": outdir / "D3_value_evidence.xlsx",
        "rate": outdir / "D3_rate_evidence.xlsx",
        "boundary": outdir / "D3_boundary_diagnostics.xlsx",
        "thresholds": outdir / "D3_threshold_library.xlsx",
        "events": outdir / "D3_physical_events.xlsx",
        "mapping": outdir / "D3_mapping_params.xlsx",
        "profile": outdir / "D3_sensor_summary.xlsx",
    }
    results["main_scores"].to_excel(paths["scores"], index=False)
    results["value_bounds"].to_excel(paths["value"], index=False)
    results["rate_constraint"].to_excel(paths["rate"], index=False)
    results["boundary_features"].to_excel(paths["boundary"], index=False)
    results["events"].to_excel(paths["events"], index=False)
    profile_df.to_excel(paths["profile"], index=False)

    with pd.ExcelWriter(paths["thresholds"]) as writer:
        thresholds_df.to_excel(writer, sheet_name="full_library", index=False)
        thresholds_df[thresholds_df["included_in_D3_score"]].to_excel(
            writer, sheet_name="scored_thresholds", index=False
        )
        thresholds_df[thresholds_df["bound_type"] == "boundary"].to_excel(
            writer, sheet_name="boundary_diagnostic", index=False
        )

    mapping_rows = []
    for section, values in mapping_cfg.items():
        if isinstance(values, dict):
            for parameter, value in values.items():
                mapping_rows.append({"section": section, "parameter": parameter, "value": str(value)})
        else:
            mapping_rows.append({"section": "_root", "parameter": section, "value": str(values)})
    pd.DataFrame(mapping_rows).to_excel(paths["mapping"], index=False)
    return list(paths.values())


def build_profile_summary(results: dict) -> pd.DataFrame:
    scores = results["main_scores"]
    value = results["value_bounds"]
    rate = results["rate_constraint"]
    rows = []
    for sensor, group in scores.groupby("sensor_id"):
        evaluated = group[group["evidence_status"] == "sufficient"]
        issue = evaluated["dominant_physical_issue"]
        value_sensor = value[value["sensor_id"] == sensor]
        rate_sensor = rate[rate["sensor_id"] == sensor]
        rows.append({
            "sensor_id": sensor,
            "sensor_type": "DO" if sensor.startswith("DO") else "ORP",
            "n_windows": len(group),
            "n_evaluated": len(evaluated),
            "evaluation_coverage": len(evaluated) / max(len(group), 1),
            "mean_observed_fraction": float(group["observed_fraction"].mean()),
            "mean_D3": float(evaluated["D3_total"].mean()),
            "median_D3": float(evaluated["D3_total"].median()),
            "min_D3": float(evaluated["D3_total"].min()),
            "hard_violation_dominant_rate": float((issue == "hard_bound").mean()),
            "soft_dominant_window_rate": float((issue == "soft_bound").mean()),
            "persistent_rate_dominant_window_rate": float((issue == "persistent_rate").mean()),
            "soft_low_exceedance_window_rate": float(value_sensor["soft_low_violation_rate"].gt(0).mean()),
            "soft_high_exceedance_window_rate": float(value_sensor["soft_high_violation_rate"].gt(0).mean()),
            "mean_soft_low_exceedance_rate": float(value_sensor["soft_low_violation_rate"].mean()),
            "mean_soft_high_exceedance_rate": float(value_sensor["soft_high_violation_rate"].mean()),
            "point_rate_excursion_window_rate": float(rate_sensor["rate_hard_point_violation_rate"].gt(0).mean()),
            "persistent_rate_window_rate": float(rate_sensor["rate_hard_violation_rate"].gt(0).mean()),
            "impulse_return_window_rate": float(rate_sensor["impulse_return_event_count"].gt(0).mean()),
            "process_guard_window_rate": float(rate_sensor["process_coherence_guarded_points"].gt(0).mean()),
            "veto_rate": float(evaluated["veto_flag"].mean()),
            "data_veto_rate": float(evaluated["data_veto_flag"].mean()),
            "operational_warning_rate": float(evaluated["operational_warning_flag"].mean()),
            "process_coherent_shock_rate": float(evaluated["process_coherent_shock"].mean()),
            "dominant_issue": issue.mode().iloc[0] if len(issue) else "not_evaluated",
            "threshold_version_used": THRESHOLD_VERSION,
        })
    return pd.DataFrame(rows)
