from __future__ import annotations

import numpy as np
import pandas as pd


D7_REQUIRED_COLUMNS = {
    "timestamp",
    "pair_id",
    "zone_consensus_label",
    "zone_consensus_strength",
    "d7_evaluable",
    "support_level",
    "limited_support",
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

    protected = ["D6_raw", "D6_after_D1", "D6_forDQR"]
    before = d6_main[protected].copy()
    d6 = d6_main.copy()
    d6["timestamp"] = pd.to_datetime(d6["timestamp"])
    d7 = d7_consensus[
        [
            "timestamp",
            "pair_id",
            "zone_consensus_label",
            "zone_consensus_strength",
            "d7_evaluable",
            "support_level",
            "limited_support",
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
        & output["d7_evaluable"].fillna(False)
        & output["support_level"].eq("L3")
        & ~output["limited_support"].fillna(True)
    )
    output["integration_status"] = np.select(
        [
            ~output["d7_interface_matched"],
            output["d7_gate_ready"],
        ],
        [
            "missing_D7_interface_row",
            "ready_for_D7_arbitration_policy_test",
        ],
        default="pending_D7_topology_or_support",
    )
    output["finalization_allowed"] = False
    output["D6_forDQR_candidate"] = np.nan
    output["node_allocation_status"] = np.where(
        output["d7_gate_ready"],
        "requires_preapproved_arbitration_policy",
        "not_authorized_without_verified_D7",
    )
    if not before.reset_index(drop=True).equals(
        output[protected].reset_index(drop=True)
    ):
        raise RuntimeError("D6 protected score columns changed during D7 readiness review")
    return output
