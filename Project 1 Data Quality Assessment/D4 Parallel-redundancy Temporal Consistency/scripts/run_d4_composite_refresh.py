from __future__ import annotations

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


D4_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = D4_ROOT.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.confirmatory_v2.composite import run_composite
from src.confirmatory_v2.d3_safety_gate import run_d3_sensitivity


OUTPUT_DIR = D4_ROOT / "outputs" / "integration" / "D4V151_composite_refresh"
MANIFEST_NAME = "D4V151_composite_refresh_manifest.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    for stale_manifest in OUTPUT_DIR.glob("D4V*_composite_refresh_manifest.json"):
        if stale_manifest.name != MANIFEST_NAME:
            stale_manifest.unlink()
    inputs = {
        "D1": PROJECT_ROOT / "D1 Sensor health" / "outputs" / "data" / "D1_main_scores_min.xlsx",
        "D2": PROJECT_ROOT / "D2 Temporal Continuity & Information Availability" / "artifacts" / "data" / "D2_main_scores_hourly.xlsx",
        "D3": PROJECT_ROOT / "D3 Physical rationality and rate constraints" / "outputs" / "data" / "D3_window_scores.xlsx",
        "D4": D4_ROOT / "outputs" / "data" / "D4_main_scores.xlsx",
        "D5": PROJECT_ROOT / "D5 Topological Role Consistency and Structural Representativeness" / "outputs" / "local" / "D5_report_interface.parquet",
    }
    missing = [str(path) for path in inputs.values() if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Composite refresh inputs missing: {missing}")

    d3_outputs = run_d3_sensitivity(OUTPUT_DIR)
    composite = run_composite(OUTPUT_DIR, d3_outputs["D3_safety_gate"])

    input_hashes = {name: _sha256(path) for name, path in inputs.items()}
    output_paths = sorted(OUTPUT_DIR.glob("*.parquet"))
    output_hashes = {path.name: _sha256(path) for path in output_paths}
    run_payload = json.dumps(input_hashes, sort_keys=True).encode("utf-8")
    run_id = f"D4V151-COMPOSITE-{hashlib.sha256(run_payload).hexdigest()[:12]}"

    node = composite["WWDQS_node_scores"]
    pair = composite["WWDQS_pair_scores"]
    plant = composite["WWDQS_plant_summary"]
    calibration_ids = pd.read_excel(
        inputs["D4"], sheet_name="main_scores", usecols=["calibration_id"]
    )["calibration_id"].dropna().astype(str).unique().tolist()
    coverage = node["coverage_class"].value_counts(dropna=False).to_dict()
    pair_coverage = pair["pair_coverage_class"].value_counts(dropna=False).to_dict()

    manifest = {
        "run_id": run_id,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "status": "retrospective_sha_bound_refresh_not_untouched_terminal_validation",
        "D4_numeric_source": "D4_raw",
        "D4_calibration_ids": calibration_ids,
        "formula_contract": {
            "node": "equal mean of evaluable D1, D2 and D5; at least two dimensions",
            "pair": "equal mean of target Q_node, reference Q_node and independent D4_raw",
            "D3": "non-numeric safety gate; Fail excludes high-confidence eligibility",
            "coverage": "Full and Basic are reported separately",
        },
        "input_files": {
            name: {"path": str(path.relative_to(PROJECT_ROOT)), "sha256": input_hashes[name]}
            for name, path in inputs.items()
        },
        "output_files": output_hashes,
        "row_counts": {
            "node": len(node),
            "pair": len(pair),
            "plant_day": len(plant),
        },
        "node_coverage_counts": {str(key): int(value) for key, value in coverage.items()},
        "pair_coverage_counts": {str(key): int(value) for key, value in pair_coverage.items()},
        "limitations": [
            "The refresh is retrospective and cannot create a genuinely unseen terminal period.",
            "D3 remains a safety-gate interface rather than a compensatory numeric dimension.",
            "D5 report availability controls Full versus Basic coverage and must be interpreted explicitly.",
        ],
    }
    (OUTPUT_DIR / MANIFEST_NAME).write_text(
        json.dumps(manifest, indent=2, ensure_ascii=True), encoding="utf-8"
    )

    report = f"""# D4 v1.5.1 composite refresh

- Run ID: `{run_id}`
- Status: retrospective SHA-bound refresh; not untouched terminal validation
- D4 numeric source: `D4_raw`
- D4 calibration: `{', '.join(calibration_ids)}`
- Node rows: {len(node):,}
- Pair rows: {len(pair):,}
- Plant-day rows: {len(plant):,}
- Node coverage: {json.dumps(manifest['node_coverage_counts'], sort_keys=True)}
- Pair coverage: {json.dumps(manifest['pair_coverage_counts'], sort_keys=True)}

The refresh preserves dimension independence: D1 does not alter D4 numerically,
D3 remains a non-compensatory safety gate, and D5 report availability is exposed
through separate Full and Basic coverage classes. A future untouched period is
still required for terminal confirmation.
"""
    (OUTPUT_DIR / "README.md").write_text(report, encoding="utf-8")
    print(json.dumps(manifest["row_counts"], indent=2))
    print(run_id)


if __name__ == "__main__":
    main()
