from __future__ import annotations

import numpy as np
import pandas as pd


D7_REQUIRED_COLUMNS = {
    "timestamp",
    "pair_id",
    "zone_consensus_label",
    "zone_consensus_strength",
    "target_D7",
    "reference_D7",
    "d7_evaluable",
    "d7_score_ready",
    "d7_action_ready",
    "support_level",
    "limited_support",
    "protective_veto_active",
    "sensor_veto_active",
    "veto_type",
    "sensor_veto_role",
    "topology_hash",
    "template_version",
    "d7_run_id",
    "interface_version",
    "track_id",
}


def build_d6_d7_readiness(
    d6_main: pd.DataFrame, d7_consensus: pd.DataFrame
) -> pd.DataFrame:
    missing = sorted(D7_REQUIRED_COLUMNS.difference(d7_consensus.columns))
    if missing:
        raise ValueError(f"D7 interface is missing required columns: {missing}")
    if not d7_consensus["track_id"].eq("d7_local").all():
        raise ValueError("Only the isolated d7_local track may enter D6 readiness review")

    protected = ["D6_raw", "D6_after_D1"]
    before = d6_main[protected].copy()
    d6 = d6_main.copy()
    d6["timestamp"] = pd.to_datetime(d6["timestamp"])
    d7 = d7_consensus[
        [
            "timestamp",
            "pair_id",
            "zone_consensus_label",
            "zone_consensus_strength",
            "target_D7",
            "reference_D7",
            "d7_evaluable",
            "d7_score_ready",
            "d7_action_ready",
            "support_level",
            "limited_support",
            "protective_veto_active",
            "sensor_veto_active",
            "veto_type",
            "sensor_veto_role",
            "topology_hash",
            "template_version",
            "d7_run_id",
            "interface_version",
            "track_id",
        ]
    ].copy()
    d7["timestamp"] = pd.to_datetime(d7["timestamp"])
    if d7.duplicated(["timestamp", "pair_id"]).any():
        raise ValueError("D7 interface contains duplicate timestamp-pair rows")

    output = d6.merge(d7, on=["timestamp", "pair_id"], how="left", validate="many_to_one")
    output["d7_interface_matched"] = output["d7_run_id"].notna()
    output["d7_gate_ready"] = (
        output["d7_interface_matched"]
        & output["d7_score_ready"].fillna(False)
    )
    output["integration_status"] = np.select(
        [
            ~output["d7_interface_matched"],
            output["protective_veto_active"].fillna(False),
            output["sensor_veto_active"].fillna(False),
            output["d7_gate_ready"],
        ],
        [
            "final_independent_D7_unavailable",
            "final_process_coherence_protected",
            "final_sensor_localized",
            "final_with_D7_context",
        ],
        default="final_independent_D7_limited",
    )
    output["D6_forDQR_candidate"] = output["D6_after_D1"]
    output["finalization_allowed"] = output["D6_forDQR_candidate"].notna()
    output["D6_forDQR"] = output["D6_forDQR_candidate"].where(
        output["finalization_allowed"]
    )
    output["D6_forDQR_is_final"] = output["finalization_allowed"]
    output["D6_forDQR_status"] = np.where(
        output["finalization_allowed"],
        output["integration_status"],
        "not_evaluable_or_D1_missing",
    )
    output["D6_gate_applicable"] = (
        output["finalization_allowed"]
        & output["d7_gate_ready"]
        & ~output["protective_veto_active"].fillna(False)
    )
    output["D6_numeric_adjustment"] = np.where(
        output["finalization_allowed"], 0.0, np.nan
    )
    output["causal_attribution"] = np.select(
        [
            output["sensor_veto_active"].fillna(False)
            & output["sensor_veto_role"].eq("target"),
            output["sensor_veto_active"].fillna(False)
            & output["sensor_veto_role"].eq("reference"),
            output["protective_veto_active"].fillna(False),
            output["d7_gate_ready"],
        ],
        [
            "target_sensor_structural_identity_loss",
            "reference_sensor_structural_identity_loss",
            "coherent_process_change_not_sensor_fault",
            "D7_context_available_no_action",
        ],
        default="unresolved_pair_inconsistency",
    )
    output["node_allocation_status"] = np.select(
        [
            output["sensor_veto_active"].fillna(False),
            output["protective_veto_active"].fillna(False),
        ],
        [
            output["sensor_veto_role"].fillna("none"),
            "none_process_protected",
        ],
        default="none",
    )
    if not before.reset_index(drop=True).equals(
        output[protected].reset_index(drop=True)
    ):
        raise RuntimeError("D6 protected score columns changed during D7 readiness review")
    return output
