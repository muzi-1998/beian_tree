from __future__ import annotations

import json
import sys
from pathlib import Path, PureWindowsPath

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from d5_common.config import resolve_paths  # noqa: E402
from d5_common.hashing import hash_object  # noqa: E402
from d5_local.outputs.manifest import sha256_file  # noqa: E402
from d5_local.publication import D5PublicationAudit  # noqa: E402


def main() -> None:
    paths = resolve_paths()
    manifest_path = paths.local_output_root / "D5_run_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    main_scores = pd.read_parquet(paths.local_output_root / "D5_main_scores_hourly.parquet")
    support = pd.read_parquet(paths.local_output_root / "D5_support_assessment.parquet")
    consensus = pd.read_parquet(paths.local_output_root / "D5_zone_consensus.parquet")
    report_interface = pd.read_parquet(
        paths.local_output_root / "D5_report_interface.parquet"
    )
    gate_interface = pd.read_parquet(
        paths.local_output_root / "D5_gate_interface.parquet"
    )
    validation = pd.read_excel(
        paths.local_output_root / "D5_validation_results.xlsx", sheet_name="acceptance"
    )
    invariance = pd.read_excel(
        paths.sensitivity_output_root / "D5_track_invariance.xlsx",
        sheet_name="track_invariance",
    )
    figure_qa = json.loads(
        (paths.figure_root / "D5_figure_qa.json").read_text(encoding="utf-8")
    )
    publication_manifest_path = (
        ROOT / "outputs" / "publication" / "D5_publication_audit_manifest.json"
    )
    publication_manifest = json.loads(
        publication_manifest_path.read_text(encoding="utf-8")
    )
    publication_hashes_valid = all(
        (ROOT / Path(*PureWindowsPath(item["relative_path"]).parts)).exists()
        and D5PublicationAudit._sha256(
            ROOT / Path(*PureWindowsPath(item["relative_path"]).parts)
        )
        == item["sha256"]
        for item in publication_manifest["files"]
    )
    d4_dependency = D5PublicationAudit().d4_dependency_status()
    orp = support[support["analyte"] == "ORP"]
    template_bundle = json.loads(
        (
            paths.local_output_root
            / "D5_spatial_templates.template_bundle.json"
        ).read_text(encoding="utf-8")
    )
    recomputed_template_hashes = {
        record["template_id"]: hash_object(
            {
                key: value
                for key, value in record.items()
                if key != "template_hash"
            }
        )
        for record in template_bundle
    }
    recorded_template_hashes = {
        record["template_id"]: record["template_hash"]
        for record in template_bundle
    }
    support_template_hashes = support.set_index("template_id")[
        "template_hash"
    ].to_dict()
    top1_passed = bool(
        validation.loc[
            validation["criterion"] == "swap_Top1", "passed"
        ].iloc[0]
    )
    sensor_veto_released = bool(
        support["sensor_veto_eligible"].any()
    )
    checks = [
        {
            "check": "main_primary_key_unique",
            "passed": not main_scores.duplicated(["timestamp", "sensor_id"]).any(),
            "detail": "timestamp+sensor_id",
        },
        {
            "check": "local_track_isolation",
            "passed": bool(
                (main_scores["track_id"] == "d5_local").all()
                and not main_scores["upstream_score_consumed"].any()
            ),
            "detail": "Local consumes no D1-D4 scores",
        },
        {
            "check": "frozen_template_hash_integrity",
            "passed": bool(
                recomputed_template_hashes == recorded_template_hashes
                and recorded_template_hashes
                == support_template_hashes
            ),
            "detail": (
                "template bundle remains immutable; postrun admission is "
                "stored in support/admission artifacts"
            ),
        },
        {
            "check": "research_topology_supports_report",
            "passed": bool(
                main_scores["research_topology_confirmed"].all()
                and main_scores["D5_report"].notna().sum()
                == main_scores["D5_report_provisional"].notna().sum()
                and main_scores["D5_report"].notna().any()
            ),
            "detail": "author-confirmed ordinal topology enables D5_report",
        },
        {
            "check": "scientific_score_independent_of_deployment_approval",
            "passed": bool(
                main_scores["D5_total"].notna().any()
                and main_scores["D5_report_score"].equals(
                    main_scores["D5_total"]
                )
                and consensus["d5_evaluable"].any()
                and not main_scores["deployment_approved"].any()
            ),
            "detail": "research score released while automated deployment remains blocked",
        },
        {
            "check": "family_support_requires_node_validation",
            "passed": bool(
                (
                    support.loc[
                        support["support_level"].eq("L3"),
                        "family_support_level",
                    ]
                    == "L3"
                ).all()
                and support.loc[
                    support["support_level"].eq("L3"),
                    "node_validation_passed",
                ].all()
                and (
                    support["family_support_level"].eq("L3").sum()
                    >= support["support_level"].eq("L3").sum()
                )
            ),
            "detail": "family evidence is shared once; node validation limits final L3",
        },
        {
            "check": "dual_interface_contract",
            "passed": bool(
                not report_interface.duplicated(
                    ["timestamp", "sensor_id"]
                ).any()
                and not gate_interface.duplicated(
                    ["timestamp", "pair_id"]
                ).any()
                and "D5_forDQR" not in report_interface
                and "D5_forDQR" not in gate_interface
            ),
            "detail": "sensor-hour score report and pair-hour decision gate are separate",
        },
        {
            "check": "process_guard_is_not_veto",
            "passed": bool(
                gate_interface["veto_active"].equals(
                    gate_interface["sensor_identity_veto_active"]
                )
                and gate_interface["attribution_suppressed"].equals(
                    gate_interface["process_coherence_guard_active"]
                )
            ),
            "detail": "process coherence suppresses attribution only",
        },
        {
            "check": "orp_validation_graded_diagonal_model",
            "passed": bool(
                (orp["profile_covariance_mode"] == "diagonal_robust_z").all()
                and np.isclose(orp["alpha_used"], 1.0).all()
                and orp["support_level"].isin(["L2", "L3"]).any()
            ),
            "detail": "model complexity and evidence maturity are separated",
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
            "check": "top1_claim_specific_gate",
            "passed": bool(
                top1_passed == sensor_veto_released
                and (
                    top1_passed
                    or not consensus["sensor_identity_veto_active"].any()
                )
            ),
            "detail": (
                f"{validation.loc[validation['criterion'] == 'swap_Top1', 'estimate'].iloc[0]:.2f} "
                "observed versus 0.80 target; only node-specific Veto is affected"
            ),
        },
        {
            "check": "track_invariance",
            "passed": bool(invariance["passed"].all()),
            "detail": "IE_track, event Jaccard and culprit rho",
        },
        {
            "check": "figure_qa",
            "passed": bool(figure_qa["passed"]),
            "detail": "SVG/PDF/600dpi PNG/TIFF and frozen plot data",
        },
        {
            "check": "publication_artifact_hash_integrity",
            "passed": bool(
                publication_hashes_valid
                and publication_manifest.get("figure_bundle_finalized", False)
            ),
            "detail": "publication tables, source data and figure bundle match manifest SHA-256",
        },
        {
            "check": "d4_publication_dependency_current",
            "passed": d4_dependency["status"] == "current",
            "detail": (
                "exact single D4 run/calibration and main-score SHA-256; status="
                f"{d4_dependency['status']}"
            ),
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
        "production_documentary_audit_and_dual_approval_pending",
        "maintenance_records_unavailable",
        "external_event_and_topology_truth_unavailable",
    ]
    if not top1_passed:
        production_blockers.append("swap_Top1_below_0.80")
    integration_blockers = []
    if d4_dependency["status"] != "current":
        integration_blockers.append("D4_publication_dependency_stale")
    qa = {
        "generated_utc": pd.Timestamp.utcnow().isoformat(),
        "run_id": main_scores["run_id"].iloc[0],
        "research_release_status": "complete_with_documented_caveats",
        "production_release_status": "blocked",
        "cross_dimension_integration_status": (
            "ready" if not integration_blockers else "blocked_stale_dependency"
        ),
        "checks": checks,
        "failed_checks": failures,
        "production_blockers": production_blockers,
        "integration_blockers": integration_blockers,
        "d4_dependency": d4_dependency,
        "artifact_count": len(inventory),
        "artifact_inventory": inventory,
    }
    qa_path = outputs_root / "D5_RELEASE_QA.json"
    qa_path.write_text(json.dumps(qa, indent=2, ensure_ascii=True), encoding="utf-8")
    manifest["finalized_utc"] = qa["generated_utc"]
    manifest["release_qa"] = {
        "research_release_status": qa["research_release_status"],
        "production_release_status": qa["production_release_status"],
        "cross_dimension_integration_status": qa[
            "cross_dimension_integration_status"
        ],
        "failed_checks": failures,
        "production_blockers": production_blockers,
        "integration_blockers": integration_blockers,
        "release_qa_path": str(qa_path.relative_to(ROOT)).replace("\\", "/"),
    }
    manifest["validation_acceptance"] = validation.to_dict("records")
    manifest["track_invariance"] = invariance.to_dict("records")
    manifest["release_artifacts"] = inventory
    manifest["acceptance"] = {
        "acceptance_status": (
            "scientific_score_released_integration_ready_deployment_blocked"
            if not integration_blockers
            else "scientific_score_released_integration_dependency_blocked"
        ),
        "failed_contracts": failures,
        "limitations": [*production_blockers, *integration_blockers],
        "release_target": "final_subscore_aggregation_with_claim_specific_gates",
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=True, default=str), encoding="utf-8"
    )
    audit_path = paths.local_output_root / "D5_audit_log.xlsx"
    workbook = pd.ExcelFile(audit_path)
    sheets = {name: pd.read_excel(audit_path, sheet_name=name) for name in workbook.sheet_names}
    sheets["publication_qa"] = pd.DataFrame(checks)
    sheets["validation_summary"] = validation
    sheets["release_inventory"] = pd.DataFrame(inventory)
    with pd.ExcelWriter(audit_path, engine="openpyxl") as writer:
        for name, frame in sheets.items():
            frame.to_excel(writer, sheet_name=name[:31], index=False)
    print(json.dumps({key: qa[key] for key in ["research_release_status", "production_release_status", "cross_dimension_integration_status", "failed_checks", "production_blockers", "integration_blockers", "artifact_count"]}, indent=2))


if __name__ == "__main__":
    main()
