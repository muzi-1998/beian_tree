from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from d5_common.config import D5_ROOT, load_yaml, resolve_paths
from d5_local.outputs import (
    D5OutputExporter,
    build_gate_interface,
    build_report_interface,
)
from d5_local.outputs.manifest import sha256_file


def _metric(acceptance: pd.DataFrame, criterion: str) -> float:
    row = acceptance.loc[acceptance["criterion"].eq(criterion), "estimate"]
    if row.empty:
        raise ValueError(f"Missing D5 admission metric: {criterion}")
    return float(row.iloc[0])


def _persistent_mask(
    frame: pd.DataFrame,
    candidate_column: str,
    *,
    persistence_hours: int,
    role_column: str | None = None,
) -> pd.Series:
    ordered = frame.sort_values(["pair_id", "timestamp"]).copy()
    candidate = ordered[candidate_column].fillna(False).astype(bool)
    gap = ordered.groupby("pair_id")["timestamp"].diff().ne(pd.Timedelta(hours=1))
    role_change = (
        ordered.groupby("pair_id")[role_column].shift().ne(ordered[role_column])
        if role_column
        else False
    )
    new_run = ~candidate | gap | role_change
    run_id = new_run.groupby(ordered["pair_id"]).cumsum()
    run_position = candidate.astype(int).groupby(
        [ordered["pair_id"], run_id]
    ).cumsum()
    active = candidate & run_position.ge(int(persistence_hours))
    return active.reindex(frame.index, fill_value=False)


def _merge_consensus_decisions(
    main: pd.DataFrame,
    consensus_columns: pd.DataFrame,
) -> pd.DataFrame:
    decision_columns = [
        "target_sensor_id",
        "reference_sensor_id",
        "process_coherence_guard_active",
        "attribution_suppressed",
        "sensor_identity_veto_active",
        "sensor_veto_role",
        "decision_type",
    ]
    return main.drop(columns=decision_columns, errors="ignore").merge(
        consensus_columns,
        on=["timestamp", "pair_id"],
        how="left",
        validate="many_to_one",
    )


def _refresh_manifest(
    output_root: Path,
    main: pd.DataFrame,
    support: pd.DataFrame,
    consensus: pd.DataFrame,
    decision: dict[str, Any],
) -> None:
    path = output_root / "D5_run_manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["generated_utc"] = pd.Timestamp.utcnow().isoformat()
    manifest["scale"]["status_counts"] = (
        main["evaluation_status"].value_counts().to_dict()
    )
    manifest["scale"]["support_tier_counts"] = (
        support["support_level"].value_counts().to_dict()
    )
    manifest["scale"]["d5_total_rows"] = int(main["D5_total"].notna().sum())
    manifest["scale"]["d5_report_rows"] = int(
        main["D5_report_score"].notna().sum()
    )
    manifest["scale"]["d5_interface_evaluable_rows"] = int(
        consensus["d5_evaluable"].sum()
    )
    manifest["scale"]["process_guard_rows"] = int(
        consensus["process_coherence_guard_active"].sum()
    )
    manifest["scale"]["sensor_veto_rows"] = int(
        consensus["sensor_identity_veto_active"].sum()
    )
    manifest["methods"]["admission_policy"] = (
        "d5-v2.3-family-node-dual-interface"
    )
    manifest["methods"]["scientific_score_released"] = decision[
        "scientific_score_released"
    ]
    manifest["methods"]["process_guard_validated"] = decision[
        "process_guard_validated"
    ]
    manifest["methods"]["sensor_localization_validated"] = decision[
        "sensor_localization_validated"
    ]
    manifest["acceptance"] = {
        **manifest.get("acceptance", {}),
        "acceptance_status": (
            "scientific_report_released_guard_and_node_veto_gated"
        ),
        "d5_total_released": decision["scientific_score_released"],
        "process_guard_released": decision["process_guard_validated"],
        "sensor_veto_released": decision["sensor_localization_validated"],
        "deployment_release": False,
    }
    manifest["scientific_boundaries"] = [
        item
        for item in manifest["scientific_boundaries"]
        if "D5_total and D5_forDQR are null" not in item
    ]
    manifest["scientific_boundaries"].extend(
        [
            "D5_report_score is the retrospective scientific interface under author-confirmed ordinal topology; deployment approval is recorded separately.",
            "The D5 gate interface contains action and attribution states only and does not replace any D4 numeric score.",
            "Process coherence is an attribution guard, not a Veto; sensor-specific hard Veto additionally requires localization validation.",
            "Maintenance provenance and dual approval constrain automated deployment, not retrospective scientific aggregation.",
        ]
    )
    artifacts = []
    for artifact in sorted(output_root.glob("D5_*")):
        if artifact.name == path.name or not artifact.is_file():
            continue
        artifacts.append(
            {
                "path": artifact.name,
                "role": next(
                    (
                        row["role"]
                        for row in manifest.get("artifacts", [])
                        if row["path"] == artifact.name
                    ),
                    "auditable_research_artifact",
                ),
                "size": artifact.stat().st_size,
                "sha256": sha256_file(artifact),
                "schema_version": manifest["schema_version"],
            }
        )
    manifest["artifacts"] = artifacts
    path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=True, default=str),
        encoding="utf-8",
    )


def finalize_d5_admission() -> dict[str, Any]:
    paths = resolve_paths()
    output_root = paths.local_output_root
    config = load_yaml(D5_ROOT / "configs" / "local" / "aggregation.yaml")
    decision_config = config["decision"]

    acceptance = pd.read_excel(
        output_root / "D5_validation_results.xlsx", sheet_name="acceptance"
    )
    thresholds = decision_config["detection_validation"]
    detection_checks = {
        "swap_AUROC": _metric(acceptance, "swap_AUROC")
        >= float(thresholds["swap_auroc_min"]),
        "swap_AUPRC": _metric(acceptance, "swap_AUPRC")
        >= float(thresholds["swap_auprc_min"]),
        "common_mode_FAR": _metric(acceptance, "common_mode_FAR")
        <= float(thresholds["common_mode_far_max"]),
        "zone_coherent_FAR": _metric(acceptance, "zone_coherent_FAR")
        <= float(thresholds["zone_coherent_far_max"]),
        "switch_chatter_rate": _metric(acceptance, "switch_chatter_rate")
        <= float(thresholds["switch_chatter_max"]),
    }
    process_guard_validated = all(detection_checks.values())
    top1 = _metric(acceptance, "swap_Top1")
    sensor_localization_validated = (
        process_guard_validated
        and top1
        >= float(
            decision_config["localization_validation"]["swap_top1_min"]
        )
    )

    support = pd.read_parquet(output_root / "D5_support_assessment.parquet")
    support["swap_AUROC"] = _metric(acceptance, "swap_AUROC")
    support["swap_AUPRC"] = _metric(acceptance, "swap_AUPRC")
    support["Top1"] = top1
    support["common_mode_FAR"] = _metric(acceptance, "common_mode_FAR")
    support["zone_coherent_FAR"] = _metric(acceptance, "zone_coherent_FAR")
    support["claim_validation_status"] = np.select(
        [
            support["support_level"].eq("L3")
            & support["node_validation_passed"]
            & process_guard_validated,
            support["support_level"].eq("L2"),
        ],
        [
            "action_grade_process_guard",
            "scientific_score_grade",
        ],
        default="diagnostic_grade",
    )
    support["process_guard_eligible"] = (
        support["support_level"].eq("L3")
        & support["node_validation_passed"]
        & process_guard_validated
    )
    support["sensor_veto_eligible"] = (
        support["support_level"].eq("L3")
        & support["node_validation_passed"]
        & sensor_localization_validated
    )
    support["veto_eligible"] = support["sensor_veto_eligible"]
    support["limited_support_exit_status"] = np.select(
        [
            support["sensor_veto_eligible"],
            support["process_guard_eligible"],
            support["score_eligible"],
        ],
        [
            "sensor_action_admitted",
            "process_guard_admitted",
            "scientific_score_admitted",
        ],
        default="diagnostic_only",
    )
    exporter = D5OutputExporter(output_root)
    exporter.write_dual("D5_support_assessment", support, "support")

    consensus = pd.read_parquet(output_root / "D5_zone_consensus.parquet")
    consensus["detection_validation_passed"] = process_guard_validated
    consensus["localization_validation_passed"] = (
        sensor_localization_validated
    )
    consensus["d5_action_ready"] = (
        consensus["d5_action_candidate"] & process_guard_validated
    )
    consensus["sensor_veto_role"] = np.select(
        [
            consensus["zone_consensus_label"].eq(
                "sensor_localized_target"
            ),
            consensus["zone_consensus_label"].eq(
                "sensor_localized_reference"
            ),
        ],
        ["target", "reference"],
        default="none",
    )
    persistence = int(decision_config["persistence_hours"])
    consensus["process_coherence_guard_active"] = (
        _persistent_mask(
            consensus,
            "process_guard_candidate",
            persistence_hours=persistence,
        )
        & process_guard_validated
    )
    consensus["attribution_suppressed"] = consensus[
        "process_coherence_guard_active"
    ]
    consensus["sensor_identity_veto_active"] = (
        _persistent_mask(
            consensus,
            "sensor_veto_candidate",
            persistence_hours=persistence,
            role_column="sensor_veto_role",
        )
        & sensor_localization_validated
    )
    consensus["veto_active"] = consensus["sensor_identity_veto_active"]
    consensus["decision_type"] = np.select(
        [
            consensus["sensor_identity_veto_active"],
            consensus["process_coherence_guard_active"],
            consensus["sensor_veto_candidate"]
            & ~sensor_localization_validated,
        ],
        [
            "sensor_identity_veto",
            "process_coherence_guard",
            "sensor_localization_evidence_only",
        ],
        default="not_triggered",
    )
    exporter.write_dual("D5_zone_consensus", consensus, "zone_consensus")

    main = pd.read_parquet(output_root / "D5_main_scores_hourly.parquet")
    support_columns = support[
        [
            "template_id",
            "claim_validation_status",
            "process_guard_eligible",
            "sensor_veto_eligible",
        ]
    ].rename(columns={"template_id": "template_id_used"})
    main = main.drop(
        columns=[
            "claim_validation_status",
            "process_guard_eligible",
            "sensor_veto_eligible",
        ],
        errors="ignore",
    ).merge(support_columns, on="template_id_used", how="left")
    main["validation_grade"] = np.where(
        process_guard_validated,
        "V3_detection_and_process_guard",
        "V1_scientific_score_only",
    )
    consensus_columns = consensus[
        [
            "timestamp",
            "pair_id",
            "target_sensor_id",
            "reference_sensor_id",
            "process_coherence_guard_active",
            "attribution_suppressed",
            "sensor_identity_veto_active",
            "sensor_veto_role",
            "decision_type",
        ]
    ]
    main = _merge_consensus_decisions(main, consensus_columns)
    target_match = main["sensor_id"].eq(main["target_sensor_id"])
    reference_match = main["sensor_id"].eq(main["reference_sensor_id"])
    sensor_applies = main["sensor_identity_veto_active"].fillna(False) & (
        (main["sensor_veto_role"].eq("target") & target_match)
        | (
            main["sensor_veto_role"].eq("reference")
            & reference_match
        )
    )
    main["process_coherence_guard_active"] = main[
        "process_coherence_guard_active"
    ].fillna(False)
    main["attribution_suppressed"] = main[
        "attribution_suppressed"
    ].fillna(False)
    main["sensor_identity_veto_active"] = sensor_applies
    main["veto_active"] = main["sensor_identity_veto_active"]
    main["veto_eligible"] = main["sensor_veto_eligible"].fillna(False)
    main["veto_reason"] = np.select(
        [
            main["sensor_identity_veto_active"],
            main["sensor_veto_eligible"].fillna(False),
        ],
        [
            "persistent_sensor_identity_loss",
            "eligible_not_triggered",
        ],
        default="claim_specific_validation_or_support_not_met",
    )
    main = main.drop(
        columns=["target_sensor_id", "reference_sensor_id"],
        errors="ignore",
    )
    exporter.write_dual("D5_main_scores_hourly", main, "main_scores")
    exporter.write_dual(
        "D5_report_interface",
        build_report_interface(main),
        "report_interface",
    )
    exporter.write_dual(
        "D5_gate_interface",
        build_gate_interface(consensus),
        "gate_interface",
    )

    decision = {
        "policy_version": "d5-admission-v2.3",
        "scientific_score_released": bool(main["D5_total"].notna().any()),
        "process_guard_validated": process_guard_validated,
        "sensor_localization_validated": sensor_localization_validated,
        "detection_checks": detection_checks,
        "swap_top1": top1,
        "l3_templates": int(support["support_level"].eq("L3").sum()),
        "family_l3_templates": int(
            support["family_support_level"].eq("L3").sum()
        ),
        "node_validated_l3_templates": int(
            support["node_validation_passed"].sum()
        ),
        "d5_total_rows": int(main["D5_total"].notna().sum()),
        "d5_report_rows": int(main["D5_report_score"].notna().sum()),
        "process_guard_rows": int(
            consensus["process_coherence_guard_active"].sum()
        ),
        "sensor_veto_rows": int(
            consensus["sensor_identity_veto_active"].sum()
        ),
        "deployment_release": False,
    }
    (output_root / "D5_admission_decision.json").write_text(
        json.dumps(decision, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )
    exporter.write_workbook(
        "D5_admission_decision",
        {
            "decision": pd.DataFrame(
                [
                    {
                        key: value
                        for key, value in decision.items()
                        if not isinstance(value, dict)
                    }
                ]
            ),
            "detection_checks": pd.DataFrame(
                [
                    {"criterion": key, "passed": value}
                    for key, value in detection_checks.items()
                ]
            ),
        },
    )
    _refresh_manifest(output_root, main, support, consensus, decision)
    return decision
