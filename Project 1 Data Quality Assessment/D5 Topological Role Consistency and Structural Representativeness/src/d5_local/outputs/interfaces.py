from __future__ import annotations

import pandas as pd


REPORT_COLUMNS = [
    "timestamp",
    "sensor_id",
    "analyte",
    "line_id",
    "zone_id",
    "position_order",
    "pair_id",
    "D5_report_score",
    "uncertainty",
    "confidence",
    "evaluation_status",
    "status_reason",
    "report_eligible",
    "score_eligible",
    "support_level",
    "family_support_level",
    "node_support_level",
    "node_validation_passed",
    "family_support_id",
    "model_family_id",
    "template_id_used",
    "template_hash",
    "topology_hash",
    "template_version",
    "mapping_version",
    "run_id",
    "interface_version",
    "track_id",
]


GATE_COLUMNS = [
    "timestamp",
    "pair_id",
    "target_sensor_id",
    "reference_sensor_id",
    "zone",
    "zone_consensus_label",
    "zone_consensus_strength",
    "target_D5_report",
    "reference_D5_report",
    "d5_evaluable",
    "d5_score_ready",
    "d5_action_candidate",
    "d5_action_ready",
    "support_level",
    "limited_support",
    "process_guard_candidate",
    "process_coherence_guard_active",
    "attribution_suppressed",
    "sensor_veto_candidate",
    "sensor_identity_veto_active",
    "veto_active",
    "decision_type",
    "sensor_veto_role",
    "detection_validation_passed",
    "localization_validation_passed",
    "topology_hash",
    "template_version",
    "mapping_version",
    "d5_run_id",
    "interface_version",
    "track_id",
]


def build_report_interface(main: pd.DataFrame) -> pd.DataFrame:
    missing = sorted(set(REPORT_COLUMNS).difference(main.columns))
    if missing:
        raise ValueError(f"D5 report interface is missing columns: {missing}")
    output = main[REPORT_COLUMNS].copy()
    if output.duplicated(["timestamp", "sensor_id"]).any():
        raise ValueError("D5 report interface contains duplicate sensor-hours")
    return output


def build_gate_interface(consensus: pd.DataFrame) -> pd.DataFrame:
    frame = consensus.copy()
    defaults = {
        "d5_action_ready": False,
        "detection_validation_passed": False,
        "localization_validation_passed": False,
    }
    for column, value in defaults.items():
        if column not in frame:
            frame[column] = value
    missing = sorted(set(GATE_COLUMNS).difference(frame.columns))
    if missing:
        raise ValueError(f"D5 gate interface is missing columns: {missing}")
    output = frame[GATE_COLUMNS].copy()
    if output.duplicated(["timestamp", "pair_id"]).any():
        raise ValueError("D5 gate interface contains duplicate pair-hours")
    if not output["veto_active"].equals(
        output["sensor_identity_veto_active"]
    ):
        raise ValueError(
            "Only sensor-identity evidence may activate D5 Veto"
        )
    return output
