from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from d7_common.config import resolve_paths  # noqa: E402
from d7_local.outputs.manifest import sha256_file  # noqa: E402


def main() -> None:
    paths = resolve_paths()
    manifest_path = paths.local_output_root / "D7_run_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    main_scores = pd.read_parquet(paths.local_output_root / "D7_main_scores_hourly.parquet")
    support = pd.read_parquet(paths.local_output_root / "D7_support_assessment.parquet")
    consensus = pd.read_parquet(paths.local_output_root / "D7_zone_consensus.parquet")
    validation = pd.read_excel(
        paths.local_output_root / "D7_validation_results.xlsx", sheet_name="acceptance"
    )
    invariance = pd.read_excel(
        paths.sensitivity_output_root / "D7_track_invariance.xlsx",
        sheet_name="track_invariance",
    )
    figure_qa = json.loads(
        (paths.figure_root / "D7_figure_qa.json").read_text(encoding="utf-8")
    )
    orp = support[support["analyte"] == "ORP"]
    checks = [
        {
            "check": "main_primary_key_unique",
            "passed": not main_scores.duplicated(["timestamp", "sensor_id"]).any(),
            "detail": "timestamp+sensor_id",
        },
        {
            "check": "local_track_isolation",
            "passed": bool(
                (main_scores["track_id"] == "d7_local").all()
                and not main_scores["upstream_score_consumed"].any()
            ),
            "detail": "Local consumes no D1-D6 scores",
        },
        {
            "check": "unverified_topology_blocks_total",
            "passed": bool(
                main_scores["D7_total"].isna().all()
                and main_scores["D7_forDQR"].isna().all()
                and not consensus["d7_evaluable"].any()
            ),
            "detail": "D7_total/D7_forDQR/D6 final arbitration blocked",
        },
        {
            "check": "orp_l1_diagonal_alpha1",
            "passed": bool(
                (orp["support_level"] == "L1").all()
                and (orp["profile_covariance_mode"] == "diagonal_robust_z").all()
                and np.isclose(orp["alpha_used"], 1.0).all()
            ),
            "detail": "forced initial ORP support policy",
        },
        {
            "check": "validation_nonlocalization_gates",
            "passed": bool(
                validation.loc[
                    validation["criterion"].isin(
                        ["swap_AUROC", "swap_AUPRC", "common_mode_FAR", "zone_coherent_FAR", "switch_chatter_rate"]
                    ),
                    "passed",
                ].all()
            ),
            "detail": "detection, negative controls and chatter",
        },
        {
            "check": "top1_release_gate",
            "passed": bool(
                validation.loc[validation["criterion"] == "swap_Top1", "passed"].iloc[0]
            ),
            "detail": "0.75 observed versus 0.80 target",
        },
        {
            "check": "track_invariance",
            "passed": bool(invariance["passed"].all()),
            "detail": "IE_track, event Jaccard and culprit rho",
        },
        {
            "check": "figure_qa",
            "passed": bool(figure_qa["passed"]),
            "detail": "SVG/PDF/600dpi PNG and frozen plot data",
        },
    ]
    outputs_root = ROOT / "outputs"
    inventory = []
    for path in sorted(outputs_root.rglob("*")):
        if not path.is_file() or path == manifest_path:
            continue
        inventory.append(
            {
                "path": str(path.relative_to(ROOT)).replace("\\", "/"),
                "size": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    failures = [row["check"] for row in checks if not row["passed"]]
    production_blockers = [
        "field_topology_and_asset_mapping_unverified",
        "effective_support_insufficient_for_gating",
        "swap_Top1_below_0.80",
        "external_event_and_topology_truth_unavailable",
    ]
    qa = {
        "generated_utc": pd.Timestamp.utcnow().isoformat(),
        "run_id": main_scores["run_id"].iloc[0],
        "research_release_status": "complete_with_documented_caveats",
        "production_release_status": "blocked",
        "checks": checks,
        "failed_checks": failures,
        "production_blockers": production_blockers,
        "artifact_count": len(inventory),
        "artifact_inventory": inventory,
    }
    qa_path = outputs_root / "D7_RELEASE_QA.json"
    qa_path.write_text(json.dumps(qa, indent=2, ensure_ascii=True), encoding="utf-8")
    manifest["finalized_utc"] = qa["generated_utc"]
    manifest["release_qa"] = {
        "research_release_status": qa["research_release_status"],
        "production_release_status": qa["production_release_status"],
        "failed_checks": failures,
        "production_blockers": production_blockers,
        "release_qa_path": str(qa_path.relative_to(ROOT)).replace("\\", "/"),
    }
    manifest["validation_acceptance"] = validation.to_dict("records")
    manifest["track_invariance"] = invariance.to_dict("records")
    manifest["release_artifacts"] = inventory
    manifest["acceptance"] = {
        "acceptance_status": "research_complete_production_blocked",
        "failed_contracts": failures,
        "limitations": production_blockers,
        "release_target": "research_review_branch",
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=True, default=str), encoding="utf-8"
    )
    audit_path = paths.local_output_root / "D7_audit_log.xlsx"
    workbook = pd.ExcelFile(audit_path)
    sheets = {name: pd.read_excel(audit_path, sheet_name=name) for name in workbook.sheet_names}
    sheets["publication_qa"] = pd.DataFrame(checks)
    sheets["validation_summary"] = validation
    sheets["release_inventory"] = pd.DataFrame(inventory)
    with pd.ExcelWriter(audit_path, engine="openpyxl") as writer:
        for name, frame in sheets.items():
            frame.to_excel(writer, sheet_name=name[:31], index=False)
    print(json.dumps({key: qa[key] for key in ["research_release_status", "production_release_status", "failed_checks", "production_blockers", "artifact_count"]}, indent=2))


if __name__ == "__main__":
    main()
