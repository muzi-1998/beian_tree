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
                "value": "D6_raw,D6_after_D1,D6_forDQR remain unchanged",
            },
            {
                "rule": "finalization",
                "value": "disabled until verified L3 D7 and approved arbitration policy",
            },
        ]
    )
    workbook = output_root / "D6_D7_aggregation_readiness.xlsx"
    with pd.ExcelWriter(workbook, engine="openpyxl") as writer:
        readiness.to_excel(writer, sheet_name="readiness", index=False)
        summary.to_excel(writer, sheet_name="summary", index=False)
        contract.to_excel(writer, sheet_name="contract", index=False)
    manifest = {
        "generated_utc": pd.Timestamp.utcnow().isoformat(),
        "d6_input": str(d6_path.relative_to(PROJECT_ROOT)),
        "d6_sha256": sha256(d6_path),
        "d7_input": str(d7_path.relative_to(PROJECT_ROOT)),
        "d7_sha256": sha256(d7_path),
        "rows": len(readiness),
        "d7_gate_ready_rows": int(readiness["d7_gate_ready"].sum()),
        "finalized_rows": int(readiness["finalization_allowed"].sum()),
        "status": "readiness_only_no_score_mutation",
    }
    manifest_path = output_root / "D6_D7_aggregation_readiness_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=True), encoding="utf-8"
    )
    print(json.dumps(manifest, indent=2))
