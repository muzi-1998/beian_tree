from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


def _fmt(value: float) -> str:
    return "NA" if pd.isna(value) else f"{value:.3f}"


def write_report(output_dir: Path, sap: dict) -> Path:
    data_dir = output_dir / "data"
    validation = pd.read_parquet(data_dir / "D1_challenger_validation.parquet")
    thresholds = json.loads((data_dir / "D1_challenger_thresholds.json").read_text(encoding="utf-8"))
    selected = validation.loc[
        validation["phase"].eq("internal_validation")
        & validation["resolution_mode"].eq("original_resolution")
        & validation["primary_region"].eq(True)  # noqa: E712
    ].copy()
    acceptance = sap["acceptance"]
    selected["delta_gate"] = (
        selected["recall_delta"].ge(float(acceptance["recall_delta_min"]))
        & selected["delta_ci95_low"].gt(float(acceptance["recall_delta_ci95_low_min_exclusive"]))
    )
    threshold_gate = all(not bool(item["threshold_gate_failed"]) for item in thresholds.values())
    overall_pass = bool(threshold_gate and selected["delta_gate"].all())
    lines = [
        "# D1 Challenger Detector Expert Review and Execution Report",
        "",
        f"**Decision:** {'PROMOTION ELIGIBLE' if overall_pass else 'DO NOT PROMOTE'}",
        "",
        "## Scientific boundary",
        "",
        "The run is an isolated retrospective development and terminal-shadow study. It did not modify the released D1 scores, state machine, D1 release manifest, or any D1-D5 aggregation input. The terminal segment is not external confirmation because the record has been seen by prior D1 development.",
        "",
        "The primary comparison uses the released detector score recalibrated on the same clean development history under the same event-rate ceiling. The hourly released score is discrete and cannot attain the ceiling exactly, so the closest eligible operating point at or below the ceiling is used. The released operating point is retained only as a secondary operational reference. Observed alarms in presumed-normal history are an alarm-rate proxy, not a truth-verified false-positive rate.",
        "",
        "## Prespecified result",
        "",
        "| Mechanism | Challenger recall (95% cluster CI) | Baseline under same FAR ceiling | Paired delta (95% cluster CI) | Gate |",
        "|---|---:|---:|---:|---|",
    ]
    for row in selected.sort_values("mechanism").itertuples(index=False):
        lines.append(
            f"| {row.mechanism} | {_fmt(row.challenger_recall)} ({_fmt(row.challenger_ci95_low)}-{_fmt(row.challenger_ci95_high)}) | "
            f"{_fmt(row.baseline_fixed_far_recall)} | {_fmt(row.recall_delta)} ({_fmt(row.delta_ci95_low)}-{_fmt(row.delta_ci95_high)}) | "
            f"{'PASS' if row.delta_gate else 'FAIL'} |"
        )
    lines.extend(
        [
            "",
            "## Fixed alarm-rate calibration",
            "",
            "| Track | Role | Threshold | Events/sensor-day | 95% Poisson CI |",
            "|---|---|---:|---:|---:|",
        ]
    )
    for key, item in thresholds.items():
        track, role = key.split(":")
        lines.append(
            f"| {track} | {role} | {_fmt(item['threshold'])} | {_fmt(item['far'])} | {_fmt(item['far_ci95_low'])}-{_fmt(item['far_ci95_high'])} |"
        )
    lines.extend(
        [
            "",
            "## Expert judgment",
            "",
            "1. The original proposal was scientifically defensible but over-specified where every mechanism was crossed with every sensor, regime and resolution stratum. The revised protocol keeps 96 events per mechanism while restricting hard acceptance to prespecified primary amplitude-duration regions; remaining cells are descriptive.",
            "2. A single multiscale GLR family is adequate for a challenger. A detector tournament, deep learning or per-sensor threshold optimization would be redundant and would increase multiplicity and overfitting risk.",
            "3. Minute and hourly tracks require different frozen innovations. Shifts below one hour remain pending because no frozen minute-level Section 1.1 transform exists for confirmatory use.",
            "4. DO_1_4 and DO_2_4 are excluded from ordinary Step confirmation. Their process-floor responsiveness belongs to the D2 availability contract and cannot be inferred without comparable verified excitation.",
            "5. Promotion requires future or external confirmation. Failure of a mechanism-specific gate is retained as an applicability boundary and must not be repaired by lowering the released Spike or Step thresholds on the same data.",
            "",
            "## Outputs",
            "",
            "All trial rows, exclusions, model parameters, threshold audits, applicability cells, shadow events, figure source data and SHA-256 hashes are stored under this immutable run directory.",
        ]
    )
    report_path = output_dir / "D1_challenger_expert_report.md"
    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report_path
