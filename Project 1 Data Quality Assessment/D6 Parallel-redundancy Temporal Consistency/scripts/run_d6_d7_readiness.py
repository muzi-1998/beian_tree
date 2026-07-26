from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

from d6.integration import build_d6_d7_readiness  # noqa: E402


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


if __name__ == "__main__":
    d6_path = ROOT / "outputs" / "data" / "D6_main_scores.xlsx"
    d7_path = (
        PROJECT_ROOT
        / "D7 Topological Role Consistency and Structural Representativeness"
        / "outputs"
        / "local"
        / "D7_zone_consensus.parquet"
    )
    output_root = ROOT / "outputs" / "integration"
    output_root.mkdir(parents=True, exist_ok=True)
    d6 = pd.read_excel(d6_path, sheet_name="main_scores")
    d7 = pd.read_parquet(d7_path)
    readiness = build_d6_d7_readiness(d6, d7)
    summary = (
        readiness.groupby("integration_status", dropna=False)
        .size()
        .rename("rows")
        .reset_index()
    )
    contract = pd.DataFrame(
        [
            {
                "rule": "hierarchical_scope",
                "value": "D6=edge/pair temporal consistency; D7=node/zone structure",
            },
            {
                "rule": "protected_columns",
                "value": "D6_raw and D6_after_D1 remain unchanged; D6_forDQR is the non-destructive final copy",
            },
            {
                "rule": "finalization",
                "value": "D6 finalizes independently; D7 changes gate applicability and attribution only",
            },
            {
                "rule": "process_protection",
                "value": "validated coherent-process evidence disables sensor-fault gating without changing the D6 numeric score",
            },
        ]
    )
    workbook = output_root / "D6_D7_aggregation_readiness.xlsx"
    with pd.ExcelWriter(workbook, engine="openpyxl") as writer:
        readiness.to_excel(writer, sheet_name="readiness", index=False)
        summary.to_excel(writer, sheet_name="summary", index=False)
        contract.to_excel(writer, sheet_name="contract", index=False)
    final_parquet = output_root / "D6_D7_final_arbitration.parquet"
    readiness.to_parquet(final_parquet, index=False)
    status_lines = "\n".join(
        f"- `{row.integration_status}`: {int(row.rows):,} rows"
        for row in summary.itertuples(index=False)
    )
    report = f"""# D6-D7 Final Arbitration Report

Generated: {pd.Timestamp.utcnow().isoformat()}

## Decision

D6 is finalized non-destructively from `D6_after_D1`. D7 does not modify the
numeric D6 score. It determines whether sensor-fault gating is applicable,
provides node/zone attribution, and can activate claim-specific process
protection or sensor-identity Veto only when the corresponding validation claim
has passed.

## Current release

- Input rows: {len(readiness):,}
- Finalized `D6_forDQR` rows: {int(readiness["finalization_allowed"].sum()):,}
- D7 score-ready rows: {int(readiness["d7_gate_ready"].sum()):,}
- D6 sensor-gate-applicable rows: {int(readiness["D6_gate_applicable"].sum()):,}
- Process-protection rows: {int(readiness["protective_veto_active"].fillna(False).sum()):,}
- Sensor-specific Veto rows: {int(readiness["sensor_veto_active"].fillna(False).sum()):,}
- Maximum absolute numeric adjustment: {float(readiness["D6_numeric_adjustment"].abs().max()):.6g}

## Integration states

{status_lines}

## Interpretation boundary

Missing D7 evidence does not erase or reduce D6. Process-coherent D7 evidence
may suspend sensor-fault attribution while preserving the D6 temporal
consistency score. Sensor-specific hard Veto is unavailable unless the
localization claim passes its prespecified threshold. Production automation
still requires documentary governance and is separate from retrospective
scientific aggregation.
"""
    report_path = output_root / "D6_D7_FINAL_ARBITRATION_REPORT.md"
    report_path.write_text(report, encoding="utf-8")
    manifest = {
        "generated_utc": pd.Timestamp.utcnow().isoformat(),
        "d6_input": str(d6_path.relative_to(PROJECT_ROOT)),
        "d6_sha256": sha256(d6_path),
        "d7_input": str(d7_path.relative_to(PROJECT_ROOT)),
        "d7_sha256": sha256(d7_path),
        "rows": len(readiness),
        "d7_gate_ready_rows": int(readiness["d7_gate_ready"].sum()),
        "finalized_rows": int(readiness["finalization_allowed"].sum()),
        "gate_applicable_rows": int(readiness["D6_gate_applicable"].sum()),
        "protective_veto_rows": int(
            readiness["protective_veto_active"].fillna(False).sum()
        ),
        "sensor_veto_rows": int(
            readiness["sensor_veto_active"].fillna(False).sum()
        ),
        "max_abs_numeric_adjustment": float(
            readiness["D6_numeric_adjustment"].abs().max()
        ),
        "final_output": str(final_parquet.relative_to(PROJECT_ROOT)),
        "report": str(report_path.relative_to(PROJECT_ROOT)),
        "report_sha256": sha256(report_path),
        "status": "final_non_destructive_D6_with_claim_specific_D7_arbitration",
    }
    manifest_path = output_root / "D6_D7_aggregation_readiness_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=True), encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2))
