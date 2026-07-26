from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from d7_common.config import D7_ROOT, load_yaml, resolve_paths
from d7_local.outputs.exporter import D7OutputExporter
from d7_local.outputs.manifest import sha256_file


def _metric(acceptance: pd.DataFrame, criterion: str) -> float:
    row = acceptance.loc[acceptance["criterion"].eq(criterion), "estimate"]
    if row.empty:
        raise ValueError(f"Missing D7 admission metric: {criterion}")
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


def _refresh_manifest(
    output_root: Path,
    main: pd.DataFrame,
    support: pd.DataFrame,
    consensus: pd.DataFrame,
    decision: dict[str, Any],
) -> None:
    path = output_root / "D7_run_manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["generated_utc"] = pd.Timestamp.utcnow().isoformat()
    manifest["scale"]["status_counts"] = (
        main["evaluation_status"].value_counts().to_dict()
    )
    manifest["scale"]["support_tier_counts"] = (
        support["support_level"].value_counts().to_dict()
    )
    manifest["scale"]["d7_total_rows"] = int(main["D7_total"].notna().sum())
    manifest["scale"]["d7_fordqr_rows"] = int(main["D7_forDQR"].notna().sum())
    manifest["scale"]["d7_interface_evaluable_rows"] = int(
        consensus["d7_evaluable"].sum()
    )
    manifest["scale"]["protective_veto_rows"] = int(
        consensus["protective_veto_active"].sum()
    )
    manifest["scale"]["sensor_veto_rows"] = int(
        consensus["sensor_veto_active"].sum()
    )
    manifest["methods"]["admission_policy"] = "d7-v2.2-claim-specific"
    manifest["methods"]["scientific_score_released"] = decision[
        "scientific_score_released"
    ]
    manifest["methods"]["protective_veto_validated"] = decision[
        "protective_veto_validated"
    ]
    manifest["methods"]["sensor_localization_validated"] = decision[
        "sensor_localization_validated"
    ]
    manifest["acceptance"] = {
        **manifest.get("acceptance", {}),
        "acceptance_status": "scientific_score_released_node_veto_gated",
        "d7_total_released": decision["scientific_score_released"],
        "protective_veto_released": decision["protective_veto_validated"],
        "sensor_veto_released": decision["sensor_localization_validated"],
        "deployment_release": False,
    }
    manifest["scientific_boundaries"] = [
        item
        for item in manifest["scientific_boundaries"]
        if "D7_total and D7_forDQR are null" not in item
    ]
    manifest["scientific_boundaries"].extend(
        [
            "D7_total and D7_forDQR are scientific scores under author-confirmed ordinal topology; deployment approval is recorded separately.",
            "Process-coherence protection may be released after detection and negative-control validation; sensor-specific hard Veto additionally requires localization validation.",
            "Maintenance provenance and dual approval constrain automated deployment, not retrospective scientific aggregation.",
        ]
    )
    artifacts = []
    for artifact in sorted(output_root.glob("D7_*")):
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


def finalize_d7_admission() -> dict[str, Any]:
    paths = resolve_paths()
    output_root = paths.local_output_root
    config = load_yaml(D7_ROOT / "configs" / "local" / "aggregation.yaml")
    veto_config = config["veto"]

    acceptance = pd.read_excel(
        output_root / "D7_validation_results.xlsx", sheet_name="acceptance"
    )
    thresholds = veto_config["detection_validation"]
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
    protective_veto_validated = all(detection_checks.values())
    top1 = _metric(acceptance, "swap_Top1")
    sensor_localization_validated = (
        protective_veto_validated
        and top1
        >= float(
            veto_config["localization_validation"]["swap_top1_min"]
        )
    )

    support = pd.read_parquet(output_root / "D7_support_assessment.parquet")
    support["swap_AUROC"] = _metric(acceptance, "swap_AUROC")
    support["swap_AUPRC"] = _metric(acceptance, "swap_AUPRC")
    support["Top1"] = top1
    support["common_mode_FAR"] = _metric(acceptance, "common_mode_FAR")
    support["zone_coherent_FAR"] = _metric(acceptance, "zone_coherent_FAR")
    support["claim_validation_status"] = np.select(
        [
            support["support_level"].eq("L3")
            & protective_veto_validated,
            support["support_level"].eq("L2"),
        ],
        [
            "action_grade_process_protection",
            "scientific_score_grade",
        ],
        default="diagnostic_grade",
    )
    support["protective_veto_eligible"] = (
        support["support_level"].eq("L3")
        & protective_veto_validated
    )
    support["sensor_veto_eligible"] = (
        support["support_level"].eq("L3")
        & sensor_localization_validated
    )
    support["veto_eligible"] = (
        support["protective_veto_eligible"]
        | support["sensor_veto_eligible"]
    )
    support["limited_support_exit_status"] = np.select(
        [
            support["sensor_veto_eligible"],
            support["protective_veto_eligible"],
            support["score_eligible"],
        ],
        [
            "sensor_action_admitted",
            "process_protection_admitted",
            "scientific_score_admitted",
        ],
        default="diagnostic_only",
    )
    exporter = D7OutputExporter(output_root)
    exporter.write_dual("D7_support_assessment", support, "support")

    consensus = pd.read_parquet(output_root / "D7_zone_consensus.parquet")
    consensus["detection_validation_passed"] = protective_veto_validated
    consensus["localization_validation_passed"] = (
        sensor_localization_validated
    )
    consensus["d7_action_ready"] = (
        consensus["d7_action_candidate"] & protective_veto_validated
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
    persistence = int(veto_config["persistence_hours"])
    consensus["protective_veto_active"] = (
        _persistent_mask(
            consensus,
            "protective_veto_candidate",
            persistence_hours=persistence,
        )
        & protective_veto_validated
    )
    consensus["sensor_veto_active"] = (
        _persistent_mask(
            consensus,
            "sensor_veto_candidate",
            persistence_hours=persistence,
            role_column="sensor_veto_role",
        )
        & sensor_localization_validated
    )
    consensus["veto_active"] = (
        consensus["protective_veto_active"]
        | consensus["sensor_veto_active"]
    )
    consensus["veto_type"] = np.select(
        [
            consensus["sensor_veto_active"],
            consensus["protective_veto_active"],
            consensus["sensor_veto_candidate"]
            & ~sensor_localization_validated,
        ],
        [
            "sensor_identity_veto",
            "process_coherence_protection",
            "sensor_localization_evidence_only",
        ],
        default="not_triggered",
    )
    exporter.write_dual("D7_zone_consensus", consensus, "zone_consensus")

    main = pd.read_parquet(output_root / "D7_main_scores_hourly.parquet")
    support_columns = support[
        [
            "template_id",
            "claim_validation_status",
            "protective_veto_eligible",
            "sensor_veto_eligible",
        ]
    ].rename(columns={"template_id": "template_id_used"})
    main = main.drop(
        columns=[
            "claim_validation_status",
            "protective_veto_eligible",
            "sensor_veto_eligible",
        ],
        errors="ignore",
    ).merge(support_columns, on="template_id_used", how="left")
    main["validation_grade"] = np.where(
        protective_veto_validated,
        "V2_detection_and_process_protection",
        "V1_scientific_score_only",
    )
    consensus_columns = consensus[
        [
            "timestamp",
            "pair_id",
            "target_sensor_id",
            "reference_sensor_id",
            "protective_veto_active",
            "sensor_veto_active",
            "sensor_veto_role",
            "veto_type",
        ]
    ]
    main = main.drop(
        columns=["protective_veto_active", "sensor_veto_active"],
        errors="ignore",
    ).merge(consensus_columns, on=["timestamp", "pair_id"], how="left")
    target_match = main["sensor_id"].eq(main["target_sensor_id"])
    reference_match = main["sensor_id"].eq(main["reference_sensor_id"])
    sensor_applies = main["sensor_veto_active"].fillna(False) & (
        (main["sensor_veto_role"].eq("target") & target_match)
        | (
            main["sensor_veto_role"].eq("reference")
            & reference_match
        )
    )
    main["protective_veto_active"] = main[
        "protective_veto_active"
    ].fillna(False)
    main["sensor_veto_active"] = sensor_applies
    main["veto_active"] = (
        main["protective_veto_active"] | main["sensor_veto_active"]
    )
    main["veto_eligible"] = (
        main["protective_veto_eligible"].fillna(False)
        | main["sensor_veto_eligible"].fillna(False)
    )
    main["veto_reason"] = np.select(
        [
            main["sensor_veto_active"],
            main["protective_veto_active"],
            main["sensor_veto_eligible"].fillna(False),
            main["protective_veto_eligible"].fillna(False),
        ],
        [
            "persistent_sensor_identity_loss",
            "persistent_process_coherence_protection",
            "eligible_not_triggered",
            "eligible_not_triggered",
        ],
        default="claim_specific_validation_or_support_not_met",
    )
    main = main.drop(
        columns=["target_sensor_id", "reference_sensor_id"],
        errors="ignore",
    )
    exporter.write_dual("D7_main_scores_hourly", main, "main_scores")

    decision = {
        "policy_version": "d7-admission-v2.2",
        "scientific_score_released": bool(main["D7_total"].notna().any()),
        "protective_veto_validated": protective_veto_validated,
        "sensor_localization_validated": sensor_localization_validated,
        "detection_checks": detection_checks,
        "swap_top1": top1,
        "l3_templates": int(support["support_level"].eq("L3").sum()),
        "d7_total_rows": int(main["D7_total"].notna().sum()),
        "d7_fordqr_rows": int(main["D7_forDQR"].notna().sum()),
        "protective_veto_rows": int(
            consensus["protective_veto_active"].sum()
        ),
        "sensor_veto_rows": int(consensus["sensor_veto_active"].sum()),
        "deployment_release": False,
    }
    (output_root / "D7_admission_decision.json").write_text(
        json.dumps(decision, indent=2, ensure_ascii=True),
        encoding="utf-8",
    )
    exporter.write_workbook(
        "D7_admission_decision",
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
