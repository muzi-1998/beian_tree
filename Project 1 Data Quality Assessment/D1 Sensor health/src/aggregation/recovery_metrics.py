"""Event-level recovery metrics and censoring-aware audit tables."""
from __future__ import annotations

from math import sqrt
from typing import Dict, Iterable, List, Tuple

import numpy as np
import pandas as pd


RECOVERY_OUTCOMES = {"direct_recovery", "adapted_recovery"}


def _max_true_run(mask: Iterable[bool]) -> int:
    best = current = 0
    for value in mask:
        if bool(value):
            current += 1
            best = max(best, current)
        else:
            current = 0
    return best


def _wilson_interval(successes: int, total: int, z: float = 1.96) -> Tuple[float, float]:
    if total <= 0:
        return np.nan, np.nan
    p = successes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    half = z * sqrt((p * (1 - p) + z * z / (4 * total)) / total) / denominator
    return max(0.0, center - half), min(1.0, center + half)


def build_episode_table(
    transitions: List[Dict],
    state_logs: Dict[str, pd.DataFrame],
) -> pd.DataFrame:
    """Create one auditable row per anomaly episode."""
    ordered = sorted(transitions, key=lambda row: (row["sensor_id"], pd.Timestamp(row["ts"])))
    active: Dict[str, Dict] = {}
    completed: List[Dict] = []

    def close(sensor: str, end: pd.Timestamp, outcome: str) -> None:
        episode = active.pop(sensor, None)
        if episode is None:
            return
        episode["episode_end"] = pd.Timestamp(end)
        episode["outcome"] = outcome
        episode["right_censored"] = outcome == "right_censored"
        episode["recovered"] = outcome in RECOVERY_OUTCOMES
        completed.append(episode)

    for transition in ordered:
        sensor = transition["sensor_id"]
        ts = pd.Timestamp(transition["ts"])
        if transition.get("to_state") == "Refractory" and transition.get("trigger") == "new_independent_event":
            if sensor in active:
                close(sensor, ts, "superseded")
            active[sensor] = {
                "sensor_id": sensor,
                "episode_id": transition.get("event_id"),
                "event_type": transition.get("event_type"),
                "episode_start": ts,
                "pelt_segment_id": transition.get("pelt_segment_id"),
                "signed_magnitude": transition.get("signed_magnitude", np.nan),
            }
            continue
        outcome = transition.get("episode_outcome")
        if outcome in RECOVERY_OUTCOMES:
            close(sensor, ts, outcome)

    for sensor, episode in list(active.items()):
        log = state_logs[sensor]
        close(sensor, pd.Timestamp(log.index[-1]), "right_censored")

    if not completed:
        return pd.DataFrame(columns=[
            "sensor_id", "episode_id", "event_type", "episode_start", "episode_end",
            "outcome", "right_censored", "recovered", "followup_h", "time_to_recovery_h",
        ])

    episodes = pd.DataFrame(completed).sort_values(["sensor_id", "episode_start"]).reset_index(drop=True)
    episodes["followup_h"] = (
        episodes["episode_end"] - episodes["episode_start"]
    ).dt.total_seconds() / 3600.0
    episodes["time_to_recovery_h"] = episodes["followup_h"].where(episodes["recovered"])

    transition_frame = pd.DataFrame(ordered)
    for idx, episode in episodes.iterrows():
        sensor = episode["sensor_id"]
        event_id = episode["episode_id"]
        log = state_logs[sensor]
        event_mask = log["event_id"].eq(event_id)
        episodes.loc[idx, "candidate_entry_count"] = int((
            (transition_frame.get("sensor_id") == sensor)
            & (transition_frame.get("event_id") == event_id)
            & (transition_frame.get("to_state") == "RecoveryCandidate")
        ).sum()) if len(transition_frame) else 0
        episodes.loc[idx, "candidate_recovered_count"] = int((
            (transition_frame.get("sensor_id") == sensor)
            & (transition_frame.get("event_id") == event_id)
            & (transition_frame.get("to_state") == "Recovered")
        ).sum()) if len(transition_frame) else 0
        episodes.loc[idx, "candidate_max_contiguous_h"] = _max_true_run(
            (event_mask & log["state_name"].eq("RecoveryCandidate")).to_numpy()
        )
        episodes.loc[idx, "recovered_observation_max_h"] = _max_true_run(
            (event_mask & log["state_name"].eq("Recovered")).to_numpy()
        )

    starts = episodes[["sensor_id", "episode_start"]].copy()
    for horizon in (24, 48, 72):
        values = []
        for _, episode in episodes.iterrows():
            if not episode["recovered"]:
                values.append(np.nan)
                continue
            later = starts[
                (starts["sensor_id"] == episode["sensor_id"])
                & (starts["episode_start"] > episode["episode_end"])
                & (starts["episode_start"] <= episode["episode_end"] + pd.Timedelta(hours=horizon))
            ]
            values.append(bool(len(later)))
        episodes[f"relapse_within_{horizon}h"] = values
    return episodes


def build_recovery_summary(
    episodes: pd.DataFrame,
    state_logs: Dict[str, pd.DataFrame],
) -> pd.DataFrame:
    """Summarise recovery by channel and overall with Wilson intervals."""
    rows = []
    groups = [(sensor, frame) for sensor, frame in episodes.groupby("sensor_id")]
    groups.append(("Overall", episodes))
    for sensor, frame in groups:
        completed = frame[~frame["right_censored"]]
        recovered = completed[completed["recovered"]]
        direct = int((frame["outcome"] == "direct_recovery").sum())
        adapted = int((frame["outcome"] == "adapted_recovery").sum())
        n_completed = len(completed)
        n_recovered = len(recovered)
        low, high = _wilson_interval(n_recovered, n_completed)
        candidate_episodes = frame[frame["candidate_entry_count"] > 0]
        candidate_successes = int((candidate_episodes["outcome"] == "adapted_recovery").sum())
        candidate_attempts = int(frame["candidate_entry_count"].sum())
        candidate_reached_recovered = int(frame["candidate_recovered_count"].sum())
        selected_logs = state_logs.values() if sensor == "Overall" else [state_logs[sensor]]
        total_h = sum(len(log) for log in selected_logs)
        recovered_h = sum(log["state_name"].eq("Recovered").sum() for log in selected_logs)
        candidate_h = sum(log["state_name"].eq("RecoveryCandidate").sum() for log in selected_logs)
        row = {
            "sensor_id": sensor,
            "n_episodes": int(len(frame)),
            "n_completed": int(n_completed),
            "n_right_censored": int(frame["right_censored"].sum()),
            "n_direct_recovery": direct,
            "n_adapted_recovery": adapted,
            "n_recovered": n_recovered,
            "event_recovery_rate": n_recovered / n_completed if n_completed else np.nan,
            "event_recovery_rate_ci95_low": low,
            "event_recovery_rate_ci95_high": high,
            "median_recovery_h": recovered["time_to_recovery_h"].median() if n_recovered else np.nan,
            "candidate_episode_count": int(len(candidate_episodes)),
            "candidate_attempt_count": candidate_attempts,
            "candidate_reached_recovered_count": candidate_reached_recovered,
            "candidate_attempt_confirmation_rate": (
                candidate_reached_recovered / candidate_attempts if candidate_attempts else np.nan
            ),
            "candidate_attempt_adapted_rate": (
                candidate_successes / candidate_attempts if candidate_attempts else np.nan
            ),
            "candidate_conversion_rate": (
                candidate_successes / len(candidate_episodes) if len(candidate_episodes) else np.nan
            ),
            "candidate_max_contiguous_h": frame["candidate_max_contiguous_h"].max() if len(frame) else 0,
            "recovered_state_occupancy": recovered_h / total_h if total_h else np.nan,
            "candidate_state_occupancy": candidate_h / total_h if total_h else np.nan,
        }
        for horizon in (24, 48, 72):
            column = f"relapse_within_{horizon}h"
            observed = frame[column].dropna()
            row[f"relapse_rate_{horizon}h"] = observed.mean() if len(observed) else np.nan
        rows.append(row)
    return pd.DataFrame(rows)


def kaplan_meier_recovery(episodes: pd.DataFrame) -> pd.DataFrame:
    """Return a censoring-aware cumulative recovery curve."""
    if episodes.empty:
        return pd.DataFrame(columns=[
            "time_h", "at_risk", "n_recovered", "n_censored", "survival", "cumulative_recovery"
        ])
    durations = episodes["followup_h"].astype(float)
    observed = episodes["recovered"].astype(bool)
    survival = 1.0
    rows = []
    for time_h in sorted(durations.unique()):
        at_risk = int((durations >= time_h).sum())
        recovered = int(((durations == time_h) & observed).sum())
        censored = int(((durations == time_h) & ~observed).sum())
        if at_risk > 0:
            survival *= 1.0 - recovered / at_risk
        rows.append({
            "time_h": float(time_h),
            "at_risk": at_risk,
            "n_recovered": recovered,
            "n_censored": censored,
            "survival": survival,
            "cumulative_recovery": 1.0 - survival,
        })
    return pd.DataFrame(rows)


def audit_transition_conservation(
    episodes: pd.DataFrame,
    transitions: List[Dict],
) -> pd.DataFrame:
    """Check that every opened episode is represented exactly once."""
    opened = [row for row in transitions if row.get("to_state") == "Refractory"]
    duplicate_ids = episodes["episode_id"].duplicated().sum() if len(episodes) else 0
    return pd.DataFrame([{
        "opened_episode_count": len(opened),
        "episode_table_count": len(episodes),
        "duplicate_episode_ids": int(duplicate_ids),
        "all_opened_accounted": len(opened) == len(episodes) and duplicate_ids == 0,
        "all_episodes_terminal_or_censored": bool(
            len(episodes) == 0 or episodes["outcome"].notna().all()
        ),
    }])
