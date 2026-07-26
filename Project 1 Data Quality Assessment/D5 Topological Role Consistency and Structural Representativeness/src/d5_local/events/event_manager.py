from __future__ import annotations

import json

import numpy as np
import pandas as pd


def build_events(
    scores: pd.DataFrame,
    consensus: pd.DataFrame,
    *,
    low_score_threshold: float = 3.0,
    minimum_duration_hours: int = 6,
) -> pd.DataFrame:
    consensus_index = consensus.set_index(["timestamp", "target_sensor_id"])
    rows: list[dict[str, object]] = []
    event_no = 0
    for sensor, frame in scores.sort_values("timestamp").groupby("sensor_id"):
        frame = frame.reset_index(drop=True)
        active = frame["D5_raw"].lt(low_score_threshold) & frame["D5_raw"].notna()
        group = active.ne(active.shift(fill_value=False)).cumsum()
        for _, event_frame in frame[active].groupby(group[active]):
            duration = len(event_frame)
            if duration < minimum_duration_hours:
                continue
            event_no += 1
            start = pd.Timestamp(event_frame["timestamp"].iloc[0])
            end = pd.Timestamp(event_frame["timestamp"].iloc[-1]) + pd.Timedelta(hours=1)
            labels = []
            for timestamp in event_frame["timestamp"]:
                key = (timestamp, sensor)
                if key in consensus_index.index:
                    labels.append(str(consensus_index.loc[key, "zone_consensus_label"]))
            label = pd.Series(labels).mode().iloc[0] if labels else "inconclusive"
            q_columns = ["Q_profile", "Q_gradient", "Q_rank", "Q_rep"]
            minimum_q = event_frame[q_columns].min()
            dominant = minimum_q.idxmin().replace("Q_", "")
            rows.append(
                {
                    "event_id": f"D5-EVT-{start:%Y%m}-{event_no:04d}",
                    "event_type": "single_node_identity_loss" if "sensor_localized" in label else label,
                    "start_ts": start,
                    "end_ts": end,
                    "duration_h": duration,
                    "sensor_id": sensor,
                    "zone": event_frame["zone_id"].iloc[0],
                    "pair_id": event_frame["pair_id"].iloc[0],
                    "affected_sensors": json.dumps([sensor]),
                    "affected_edges": "[]",
                    "min_D5_raw": float(event_frame["D5_raw"].min()),
                    "mean_D5_raw": float(event_frame["D5_raw"].mean()),
                    "min_D5_total": float(event_frame["D5_total"].min()) if event_frame["D5_total"].notna().any() else np.nan,
                    "mean_D5_total": float(event_frame["D5_total"].mean()) if event_frame["D5_total"].notna().any() else np.nan,
                    "min_Q_profile": float(minimum_q["Q_profile"]),
                    "min_Q_gradient": float(minimum_q["Q_gradient"]),
                    "min_Q_rank": float(minimum_q["Q_rank"]),
                    "min_Q_rep": float(minimum_q["Q_rep"]),
                    "dominant_evidence": dominant,
                    "max_influence": float(event_frame["influence_score"].max()),
                    "topk_culprits": json.dumps([sensor]),
                    "zone_consensus_label": label,
                    "zone_consensus_strength": np.nan,
                    "active_regime": event_frame["active_regime_id"].mode().iloc[0],
                    "regime_state": event_frame["regime_state"].mode().iloc[0],
                    "confidence": float(event_frame["confidence"].mean()),
                    "support_level": event_frame["support_level"].mode().iloc[0],
                    "fallback": event_frame["fallback_level"].mode().iloc[0],
                    "profile_covariance_mode": event_frame["profile_covariance_mode"].mode().iloc[0],
                    "topology_suspect": bool(
                        ~event_frame["research_topology_confirmed"].all()
                    ),
                    "production_approval_pending": bool(
                        ~event_frame["production_topology_verified"].all()
                    ),
                    "alternative_topology_id": np.nan,
                    "process_vs_sensor_ambiguity": "undetermined",
                    "review_status": "unreviewed",
                    "reviewer": np.nan,
                    "review_note": np.nan,
                    "run_id": event_frame["run_id"].iloc[0],
                    "template_version": event_frame["template_version"].iloc[0],
                    "mapping_version": event_frame["mapping_version"].iloc[0],
                    "topology_hash": event_frame["topology_hash"].iloc[0],
                }
            )
    return pd.DataFrame(rows)
