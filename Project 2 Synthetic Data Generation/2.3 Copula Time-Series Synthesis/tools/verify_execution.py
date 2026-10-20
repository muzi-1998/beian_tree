"""Recheck actual local stage outputs and retain hash-matched source snapshots."""
from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys

import numpy as np
import pandas as pd
import pyarrow.compute as pc
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from project2_synthesis.runtime import sha256, write_json


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def main() -> None:
    states = json.loads((ROOT / "run_manifest/module_states.json").read_text(encoding="utf-8"))
    study = json.loads((ROOT / "configs/study_design.json").read_text(encoding="utf-8"))
    results = {}
    for stage in ["M01", "M02"]:
        manifest = states[stage]["manifest"]
        run_dir = ROOT / "run_manifest/runs" / manifest["run_id"]
        for item in manifest["outputs"]:
            require(sha256(ROOT / item["path"]) == item["sha256"], f"Changed published output: {item['path']}")
        # Older runs can be supplemented only if their exact hashed bytes exist.
        for relative, expected in {**manifest["code_sha256"], **manifest["config_sha256"]}.items():
            snapshot = run_dir / "source_snapshot" / relative
            if not snapshot.exists():
                source = ROOT / relative
                require(sha256(source) == expected, f"Cannot reconstruct original source: {relative}")
                snapshot.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, snapshot)
            require(sha256(snapshot) == expected, f"Source snapshot mismatch: {relative}")
        results[stage] = {"status": "PASS", "run_id": manifest["run_id"],
                          "output_hashes": "PASS", "hash_matched_source_snapshot": "PASS",
                          "snapshot_note": "post_run_supplement_verified_against_original_manifest_not_a_rerun"}
    flags = pq.read_table(ROOT / "artifacts/data/01_observation_flags.parquet",
                          columns=["observed", "held", "imputed", "available_at", "refresh_status"])
    for col in ["observed", "held", "imputed", "available_at"]:
        require(flags[col].null_count == len(flags), f"Unknown provenance incorrectly assigned: {col}")
    require(pc.all(pc.equal(flags["refresh_status"], "UNKNOWN")).as_py(), "Unexpected confirmed refresh")
    results["M01"]["unknown_provenance_cells"] = len(flags)
    audit = json.loads((ROOT / "artifacts/data/01_input_audit.json").read_text(encoding="utf-8"))
    contracts = json.loads((ROOT / "configs/module_contracts.json").read_text(encoding="utf-8"))
    raw_root = ROOT / contracts["external_inputs"]["raw_data"]["path"]
    for source in audit["sources"]:
        require(sha256(raw_root / source["file"]) == source["sha256"], "Raw hash changed after execution")
    results["M01"]["raw_source_hashes_rechecked"] = "PASS"
    frame = pd.read_parquet(ROOT / "artifacts/data/02_model_frame.parquet")
    require(frame["split"].eq("development").all(), "Holdout leaked into preparation")
    require(frame["model_admitted"].eq(False).all(), "Archive frame incorrectly admitted")
    require(frame["main_step_minutes"].isna().all(), "Main step was assigned")
    views = pd.read_parquet(ROOT / "artifacts/data/02_concentration_views.parquet")
    loads = pd.read_parquet(ROOT / "artifacts/data/02_load_ledger.parquet")
    require(views["fresh_count"].isna().all() and loads["fresh_count"].isna().all(), "Archive count became fresh count")
    paired = views.merge(loads, on=["support_id", "variable"], suffixes=("_view", "_load"), validate="one_to_one")
    require(paired["valid_archive_rows_view"].equals(paired["valid_archive_rows_load"]), "Inconsistent support")
    numerator = (paired["C_FW"] * paired["V_m3"] / 1000 - paired["L_kg"]).abs()
    error = numerator / paired["L_kg"].abs().clip(lower=1)
    max_error = float(error.max())
    require(np.isfinite(max_error) and max_error <= study["numerical_invariants"]["relative_roundtrip_error_max"], "Load identity failed")
    require(paired.loc[paired["valid_archive_rows_load"].eq(0), "L_kg"].isna().all(), "Missing exposure became zero load")
    decision = json.loads((ROOT / "artifacts/validation/02_scale_decision.json").read_text(encoding="utf-8"))
    require(decision["main_step_minutes"] is None and not decision["one_minute_admitted"] and not decision["frozen"], "Scale gate bypassed")
    for i in range(1, 13):
        report = (ROOT / f"reports/M{i:02d}_执行报告.md").read_text(encoding="utf-8")
        require(all(f"## {j}." in report for j in range(1, 9)), "Report missing required sections")
    results["M02"].update({"development_rows": len(frame), "view_ledger_pairs": len(paired),
                           "max_scaled_FW_load_error": max_error, "holdout_leakage": "PASS",
                           "main_step_gate_retained": "PASS", "all_12_reports_have_8_sections": "PASS"})
    for stage in ["M01", "M02"]:
        results[stage]["scientific_stage_acceptance"] = "PARTIAL"
    write_json(ROOT / "run_manifest/execution_verification.json", results)
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
