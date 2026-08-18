from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "src"))

from d4.integration import build_d4_d5_readiness  # noqa: E402


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    if path.suffix.lower() in {".json", ".md", ".svg", ".txt", ".yaml", ".yml"}:
        content = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        digest.update(content)
        return digest.hexdigest()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


if __name__ == "__main__":
    d4_path = ROOT / "outputs" / "data" / "D4_main_scores.xlsx"
    d5_path = (
        PROJECT_ROOT
        / "D5 Topological Role Consistency and Structural Representativeness"
        / "outputs"
        / "local"
        / "D5_gate_interface.parquet"
    )
    output_root = ROOT / "outputs" / "integration"
    output_root.mkdir(parents=True, exist_ok=True)
    d4 = pd.read_excel(d4_path, sheet_name="main_scores")
    d5 = pd.read_parquet(d5_path)
    core_preintegration_nonnull = int(d4["D4_forDQR"].notna().sum())
    readiness = build_d4_d5_readiness(d4, d5)
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
                "value": "D4=edge/pair temporal consistency; D5=node/zone structure",
            },
            {
                "rule": "protected_columns",
                "value": "D4_raw is the sole D4 numeric source; D4_after_D1 is retained for historical sensitivity only",
            },
            {
                "rule": "finalization",
                "value": "D4 finalizes from D4_raw; D1 and D5 change interpretation and action governance only",
            },
            {
                "rule": "process_guard",
                "value": "validated coherent-process evidence suppresses sensor-fault attribution without acting as Veto",
            },
        ]
    )
    workbook = output_root / "D4_D5_aggregation_readiness.xlsx"
    with pd.ExcelWriter(workbook, engine="openpyxl") as writer:
        readiness.to_excel(writer, sheet_name="readiness", index=False)
        summary.to_excel(writer, sheet_name="summary", index=False)
        contract.to_excel(writer, sheet_name="contract", index=False)
    final_parquet = output_root / "D4_D5_final_arbitration.parquet"
    readiness.to_parquet(final_parquet, index=False)
    status_lines = "\n".join(
        f"- `{row.integration_status}`: {int(row.rows):,} rows"
        for row in summary.itertuples(index=False)
    )
    report = f"""# D4-D5 Final Arbitration Report

Generated: {pd.Timestamp.utcnow().isoformat()}

## Decision

D4 is finalized non-destructively from `D4_raw`. D1 is retained as explanatory
sensor-health context and never changes the D4 numeric dimension. The D5 report
interface provides scientific structural scores, while the separate gate
interface provides process-coherence Guard, node/zone attribution and
sensor-identity Veto only when the corresponding validation claim has passed.

## Current release

- Input rows: {len(readiness):,}
- Core pre-integration `D4_forDQR` non-null rows: {core_preintegration_nonnull:,} (intentional placeholder; not the published integration output)
- Integration-finalized `D4_forDQR` rows: {int(readiness["finalization_allowed"].sum()):,}
- D5 report-context-ready pair-hours: {int(readiness["d5_context_available"].sum()):,}
- D5 gate/action-ready pair-hours: {int(readiness["d5_gate_ready"].sum()):,}
- D4 sensor-gate-applicable rows: {int(readiness["D4_gate_applicable"].sum()):,}
- Process-coherence Guard rows: {int(readiness["process_coherence_guard_active"].fillna(False).sum()):,}
- Sensor-specific Veto rows: {int(readiness["sensor_identity_veto_active"].fillna(False).sum()):,}
- Maximum absolute numeric adjustment: {float(readiness["D4_numeric_adjustment"].abs().max()):.6g}

## Integration states

{status_lines}

## Interpretation boundary

Missing D5 evidence does not erase or reduce D4. Process-coherent D5 evidence
may suppress sensor-fault attribution while preserving the D4 temporal
consistency score and remains explicitly distinct from Veto. Sensor-specific
hard Veto is unavailable unless the
localization claim passes its prespecified threshold. Production automation
still requires documentary governance and is separate from retrospective
scientific aggregation.

The zero-valued core pre-integration field and the finalized integration field
are different lifecycle stages. The former is deliberately withheld inside the
independent D4 core; the latter is generated non-destructively from `D4_raw` by
this integration layer.
"""
    report_path = output_root / "D4_D5_FINAL_ARBITRATION_REPORT.md"
    report_path.write_text(report, encoding="utf-8")
    manifest = {
        "generated_utc": pd.Timestamp.utcnow().isoformat(),
        "d4_input": str(d4_path.relative_to(PROJECT_ROOT)),
        "d4_sha256": sha256(d4_path),
        "d5_input": str(d5_path.relative_to(PROJECT_ROOT)),
        "d5_sha256": sha256(d5_path),
        "rows": len(readiness),
        "d5_gate_ready_rows": int(readiness["d5_gate_ready"].sum()),
        "d5_report_context_ready_rows": int(
            readiness["d5_context_available"].sum()
        ),
        "core_final_D4_forDQR_preintegration_nonnull": core_preintegration_nonnull,
        "integration_final_D4_forDQR_nonnull": int(
            readiness["finalization_allowed"].sum()
        ),
        "finalized_rows": int(readiness["finalization_allowed"].sum()),
        "gate_applicable_rows": int(readiness["D4_gate_applicable"].sum()),
        "process_guard_rows": int(
            readiness["process_coherence_guard_active"].fillna(False).sum()
        ),
        "sensor_veto_rows": int(
            readiness["sensor_identity_veto_active"].fillna(False).sum()
        ),
        "max_abs_numeric_adjustment": float(
            readiness["D4_numeric_adjustment"].abs().max()
        ),
        "final_output": str(final_parquet.relative_to(PROJECT_ROOT)),
        "report": str(report_path.relative_to(PROJECT_ROOT)),
        "report_sha256": sha256(report_path),
        "sha256_policy": "canonical_lf_for_text_raw_bytes_for_binary",
        "numeric_source": "D4_raw",
        "d1_role": "interpretation_only",
        "status": "final_independent_D4_with_dual_D5_interfaces",
    }
    manifest_path = output_root / "D4_D5_aggregation_readiness_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=True), encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2))
