from __future__ import annotations

import numpy as np
import pandas as pd

from d7_local.contracts.topology_contract import TopologyRegistry


def build_zone_consensus(
    scores: pd.DataFrame,
    influence: pd.DataFrame,
    topology: TopologyRegistry,
    *,
    run_id: str,
    interface_version: str,
    template_version: str,
    mapping_version: str,
    decision_config: dict[str, object],
) -> pd.DataFrame:
    score_index = scores.set_index(["timestamp", "sensor_id"])
    influence_index = influence.set_index(["timestamp", "sensor_id"])
    rows: list[dict[str, object]] = []
    timestamps = pd.DatetimeIndex(scores["timestamp"].unique())
    nodes = topology.nodes.set_index("sensor_id")
    for pair in topology.twin_pairs.itertuples(index=False):
        target = pair.sensor_a
        reference = pair.sensor_b
        zone = str(nodes.loc[target, "zone_id"])
        zone_sensors = nodes[nodes["zone_id"] == zone].index.tolist()
        for timestamp in timestamps:
            try:
                target_score = score_index.loc[(timestamp, target)]
                reference_score = score_index.loc[(timestamp, reference)]
                target_influence = float(influence_index.loc[(timestamp, target), "influence_score"])
                reference_influence = float(
                    influence_index.loc[(timestamp, reference), "influence_score"]
                )
            except KeyError:
                continue
            zone_frame = score_index.loc[
                score_index.index.get_level_values("sensor_id").isin(zone_sensors)
                & (score_index.index.get_level_values("timestamp") == timestamp)
            ]
            abnormal_count = int((zone_frame["D7_raw"] < 3.0).sum())
            d7_evaluable = bool(
                target_score["evaluation_status"] == "evaluable"
                and reference_score["evaluation_status"] == "evaluable"
                and np.isfinite(target_score["D7_report_score"])
                and np.isfinite(reference_score["D7_report_score"])
                and topology.research_topology_confirmed
            )
            if not np.isfinite(target_score["D7_raw"]) or not np.isfinite(reference_score["D7_raw"]):
                label, strength = "not_evaluable", np.nan
            elif target_influence >= 0.65 and reference_influence < 0.40:
                label = "sensor_localized_target"
                strength = min(1.0, target_influence - reference_influence + 0.35)
            elif reference_influence >= 0.65 and target_influence < 0.40:
                label = "sensor_localized_reference"
                strength = min(1.0, reference_influence - target_influence + 0.35)
            elif target_influence >= 0.60 and reference_influence >= 0.60:
                label = "bilateral_structural_shift"
                strength = min(target_influence, reference_influence)
            elif abnormal_count >= 2:
                label = "zone_coherent_process_shift"
                strength = min(1.0, abnormal_count / max(len(zone_sensors), 1))
            elif target_score["D7_raw"] >= 3.5 and reference_score["D7_raw"] >= 3.5:
                label = "spatially_consistent"
                strength = min(1.0, min(target_score["D7_raw"], reference_score["D7_raw"]) / 5.0)
            else:
                label = "inconclusive"
                strength = 1.0 - abs(target_influence - reference_influence)
            support_level = min(
                str(target_score["support_level"]), str(reference_score["support_level"])
            )
            process_guard_candidate = bool(
                d7_evaluable
                and support_level == "L3"
                and bool(target_score["action_eligible_candidate"])
                and bool(reference_score["action_eligible_candidate"])
                and label in {
                    "zone_coherent_process_shift",
                    "bilateral_structural_shift",
                }
                and strength
                >= float(decision_config["process_guard_strength_min"])
            )
            sensor_candidate = bool(
                d7_evaluable
                and support_level == "L3"
                and bool(target_score["action_eligible_candidate"])
                and bool(reference_score["action_eligible_candidate"])
                and label in {
                    "sensor_localized_target",
                    "sensor_localized_reference",
                }
                and strength >= float(decision_config["sensor_strength_min"])
            )
            rows.append(
                {
                    "timestamp": timestamp,
                    "pair_id": pair.pair_id,
                    "target_sensor_id": target,
                    "reference_sensor_id": reference,
                    "zone": zone,
                    "zone_consensus_label": label,
                    "zone_consensus_strength": strength,
                    "target_influence": target_influence,
                    "reference_influence": reference_influence,
                    "target_D7_report": target_score["D7_report_score"],
                    "reference_D7_report": reference_score["D7_report_score"],
                    "neighbor_abnormal_count": abnormal_count,
                    "evidence_count": len(zone_frame),
                    "direction": "unknown",
                    "d7_evaluable": d7_evaluable,
                    "support_level": support_level,
                    "limited_support": bool(
                        target_score["limited_support"] or reference_score["limited_support"]
                    ),
                    "d7_score_ready": d7_evaluable,
                    "d7_action_candidate": bool(
                        d7_evaluable
                        and support_level == "L3"
                        and target_score["action_eligible_candidate"]
                        and reference_score["action_eligible_candidate"]
                    ),
                    "process_guard_candidate": process_guard_candidate,
                    "sensor_veto_candidate": sensor_candidate,
                    "process_coherence_guard_active": False,
                    "attribution_suppressed": False,
                    "sensor_identity_veto_active": False,
                    "veto_active": False,
                    "decision_type": "pending_postrun_validation",
                    "sensor_veto_role": "none",
                    "research_topology_confirmed": topology.research_topology_confirmed,
                    "production_topology_verified": topology.topology_verified,
                    "topology_hash": topology.topology_hash,
                    "template_version": template_version,
                    "mapping_version": mapping_version,
                    "d7_run_id": run_id,
                    "interface_version": interface_version,
                    "track_id": "d7_local",
                }
        )
    return pd.DataFrame(rows)
