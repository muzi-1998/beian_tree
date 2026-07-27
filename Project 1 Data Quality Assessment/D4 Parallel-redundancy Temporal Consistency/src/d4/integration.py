from __future__ import annotations

import numpy as np
import pandas as pd


D5_REQUIRED_COLUMNS = {
    "timestamp",
    "pair_id",
    "zone_consensus_label",
    "zone_consensus_strength",
    "target_D5_report",
    "reference_D5_report",
    "d5_evaluable",
    "d5_score_ready",
    "d5_action_ready",
    "support_level",
    "limited_support",
    "process_coherence_guard_active",
    "attribution_suppressed",
    "sensor_identity_veto_active",
    "veto_active",
    "decision_type",
    "sensor_veto_role",
    "topology_hash",
    "template_version",
    "d5_run_id",
    "interface_version",
    "track_id",
}


def build_d4_d5_readiness(
    d4_main: pd.DataFrame, d5_consensus: pd.DataFrame
) -> pd.DataFrame:
    missing = sorted(D5_REQUIRED_COLUMNS.difference(d5_consensus.columns))
    if missing:
        raise ValueError(f"D5 interface is missing required columns: {missing}")
    if not d5_consensus["track_id"].eq("d5_local").all():
        raise ValueError("Only the isolated d5_local track may enter D4 readiness review")

    protected = [
        column
        for column in ["D4_raw", "D4_after_D1"]
        if column in d4_main
    ]
    before = d4_main[protected].copy()
    d4 = d4_main.copy()
    d4["timestamp"] = pd.to_datetime(d4["timestamp"])
    d5 = d5_consensus[
        [
            "timestamp",
            "pair_id",
            "zone_consensus_label",
            "zone_consensus_strength",
            "target_D5_report",
            "reference_D5_report",
            "d5_evaluable",
            "d5_score_ready",
            "d5_action_ready",
            "support_level",
            "limited_support",
            "process_coherence_guard_active",
            "attribution_suppressed",
            "sensor_identity_veto_active",
            "veto_active",
            "decision_type",
            "sensor_veto_role",
            "topology_hash",
            "template_version",
            "d5_run_id",
            "interface_version",
            "track_id",
        ]
    ].copy()
    d5["timestamp"] = pd.to_datetime(d5["timestamp"])
    if d5.duplicated(["timestamp", "pair_id"]).any():
        raise ValueError("D5 interface contains duplicate timestamp-pair rows")

    output = d4.merge(d5, on=["timestamp", "pair_id"], how="left", validate="many_to_one")
    output["d5_interface_matched"] = output["d5_run_id"].notna()
    output["d5_context_available"] = (
        output["d5_interface_matched"]
        & output["d5_score_ready"].fillna(False)
    )
    output["d5_gate_ready"] = (
        output["d5_interface_matched"]
        & output["d5_action_ready"].fillna(False)
    )
    output["integration_status"] = np.select(
        [
            ~output["d5_interface_matched"],
            output["sensor_identity_veto_active"].fillna(False),
            output["process_coherence_guard_active"].fillna(False),
            output["d5_gate_ready"],
            output["d5_context_available"],
        ],
        [
            "final_independent_D5_unavailable",
            "final_sensor_localized",
            "final_process_coherence_guarded",
            "final_with_D5_action_context",
            "final_with_D5_report_context",
        ],
        default="final_independent_D5_limited",
    )
    d4_own_evaluable = (
        output["usable_for_D4"].fillna(False)
        if "usable_for_D4" in output
        else output["D4_raw"].notna()
    )
    output["D4_own_evaluable"] = d4_own_evaluable
    output["D4_forDQR_candidate"] = output["D4_raw"]
    output["finalization_allowed"] = (
        output["D4_forDQR_candidate"].notna() & d4_own_evaluable
    )
    output["D4_forDQR"] = output["D4_forDQR_candidate"].where(
        output["finalization_allowed"]
    )
    output["D4_forDQR_is_final"] = output["finalization_allowed"]
    output["D4_forDQR_status"] = np.where(
        output["finalization_allowed"],
        output["integration_status"],
        "not_evaluable_by_D4_own_contract",
    )
    output["D4_gate_applicable"] = (
        output["finalization_allowed"]
        & output["d5_gate_ready"]
    )
    output["D4_numeric_adjustment"] = np.where(
        output["finalization_allowed"],
        output["D4_forDQR"] - output["D4_raw"],
        np.nan,
    )
    output["causal_attribution"] = np.select(
        [
            output["sensor_identity_veto_active"].fillna(False)
            & output["sensor_veto_role"].eq("target"),
            output["sensor_identity_veto_active"].fillna(False)
            & output["sensor_veto_role"].eq("reference"),
            output["process_coherence_guard_active"].fillna(False),
            output["d5_gate_ready"],
            output["d5_context_available"],
        ],
        [
            "target_sensor_structural_identity_loss",
            "reference_sensor_structural_identity_loss",
            "coherent_process_change_not_sensor_fault",
            "D5_action_context_available_no_trigger",
            "D5_report_context_available_no_action",
        ],
        default="unresolved_pair_inconsistency",
    )
    output["node_allocation_status"] = np.select(
        [
            output["sensor_identity_veto_active"].fillna(False),
            output["process_coherence_guard_active"].fillna(False),
        ],
        [
            output["sensor_veto_role"].fillna("none"),
            "none_process_guarded",
        ],
        default="none",
    )
    output["sensor_fault_attribution_allowed"] = (
        output["D4_gate_applicable"]
        & ~output["process_coherence_guard_active"].fillna(False)
    )
    output["D1_context_available"] = (
        output["D1_target"].notna() & output["D1_ref"].notna()
        if {"D1_target", "D1_ref"}.issubset(output.columns)
        else False
    )
    output["D1_interpretation_status"] = (
        output["fuse_state"]
        if "fuse_state" in output
        else "not_available"
    )
    if not before.reset_index(drop=True).equals(
        output[protected].reset_index(drop=True)
    ):
        raise RuntimeError("D4 protected score columns changed during D5 readiness review")
    return output
