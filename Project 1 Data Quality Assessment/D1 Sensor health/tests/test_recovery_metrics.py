from __future__ import annotations

import pandas as pd

from src.aggregation.recovery_metrics import (
    audit_transition_conservation,
    build_episode_table,
    build_recovery_summary,
    kaplan_meier_recovery,
)


def test_episode_metrics_distinguish_recovery_from_state_occupancy():
    index = pd.date_range("2025-01-01", periods=10, freq="h")
    log = pd.DataFrame({
        "state_name": ["Normal", "Refractory", "Refractory", "Normal", "Normal",
                       "Refractory", "BaselinePending", "RecoveryCandidate", "Recovered", "Recovered"],
        "event_id": [None, "e1", "e1", None, None, "e2", "e2", "e2", "e2", "e2"],
    }, index=index)
    transitions = [
        {"sensor_id": "S1", "ts": index[1], "from_state": "Normal", "to_state": "Refractory",
         "event_id": "e1", "event_type": "step", "trigger": "new_independent_event"},
        {"sensor_id": "S1", "ts": index[3], "from_state": "Refractory", "to_state": "Normal",
         "event_id": "e1", "event_type": "step", "episode_outcome": "direct_recovery"},
        {"sensor_id": "S1", "ts": index[5], "from_state": "Normal", "to_state": "Refractory",
         "event_id": "e2", "event_type": "regime", "trigger": "new_independent_event"},
        {"sensor_id": "S1", "ts": index[7], "from_state": "BaselinePending", "to_state": "RecoveryCandidate",
         "event_id": "e2", "event_type": "regime", "trigger": "recovery_evidence_started"},
    ]
    episodes = build_episode_table(transitions, {"S1": log})
    summary = build_recovery_summary(episodes, {"S1": log})
    overall = summary[summary["sensor_id"] == "Overall"].iloc[0]
    assert overall["n_direct_recovery"] == 1
    assert overall["n_right_censored"] == 1
    assert overall["event_recovery_rate"] == 1.0
    assert overall["recovered_state_occupancy"] == 0.2
    qa = audit_transition_conservation(episodes, transitions)
    assert bool(qa.loc[0, "all_opened_accounted"])
    km = kaplan_meier_recovery(episodes)
    assert km["cumulative_recovery"].between(0, 1).all()
