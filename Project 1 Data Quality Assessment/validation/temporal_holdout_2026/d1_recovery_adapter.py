"""Frozen D1 recovery reference adapter with an append-only replay journal.

The checkpoint retains all past detector evidence, not a compact streaming state.
This trades computation for exact reuse of the published state-machine kernel.
"""
from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

from runtime import DIMENSIONS, PROJECT, content_hash

D1 = PROJECT / DIMENSIONS["D1"]
sys.path.insert(0, str(D1))
from src.aggregation.cooldown_state_machine import CooldownConfig, run_cooldown_state_machine
from src.aggregation.d1_aggregator import aggregate_d1_v11

FIELDS = ["Q_spike", "Q_step", "Q_regime", "Q_drift", "Q_freeze", "ks_stat",
          "w1_norm", "resid_h", "step_confirmed", "peer_residual_z"]
KERNEL_FILES = ["src/aggregation/cooldown_state_machine.py",
                "src/aggregation/d1_aggregator.py", "src/baseline/local_baseline.py"]


def fingerprint_frame(frame: pd.DataFrame) -> str:
    # Use exact float representations for the publication guard, not rounded JSON.
    safe = frame.astype(object).where(frame.notna(), None)
    payload = {"columns": list(frame.columns), "index": [t.isoformat() for t in frame.index],
               "data": safe.values.tolist()}
    return fingerprint(payload)


def fingerprint(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, allow_nan=False, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def pack_evidence(frame: pd.DataFrame) -> dict:
    return {"index": [t.isoformat() for t in frame.index], "columns": list(frame.columns),
            "data": frame.astype(object).where(frame.notna(), None).values.tolist()}


def unpack_evidence(value: dict) -> pd.DataFrame:
    frame = pd.DataFrame(value["data"], columns=value["columns"], index=pd.to_datetime(value["index"]))
    return frame.reindex(columns=FIELDS).astype(float)


def normalize_events(events: list[dict]) -> list[dict]:
    result = []
    for event in events:
        row = dict(event)
        row["timestamp"] = pd.Timestamp(row["timestamp"]).isoformat()
        row["available_at"] = pd.Timestamp(row["available_at"]).isoformat()
        if pd.Timestamp(row["available_at"]) < pd.Timestamp(row["timestamp"]):
            raise ValueError("Change point cannot be available before its event time")
        result.append(row)
    return result


def score_recovery(sensor: str, evidence: pd.DataFrame, events: list[dict],
                   cooldown: dict, aggregation: dict):
    cfg = CooldownConfig(**cooldown)
    kwargs = {name: evidence[name] for name in FIELDS if name != "Q_spike"}
    q, log, transitions = run_cooldown_state_machine(
        sensor_id=sensor, pelt_changepoints=events, cfg=cfg, **kwargs)
    score, components, veto = aggregate_d1_v11(
        evidence.Q_spike, evidence.Q_step, q, evidence.Q_freeze, evidence.Q_regime,
        state_log=log, **aggregation)
    output = log.copy()
    output["Q_drift_eff"] = q
    output["D1_total"] = score
    output["detector_evidence_complete"] = evidence.drop(columns="step_confirmed").notna().all(axis=1)
    output["D1_for_validation"] = score.where(output.detector_evidence_complete)
    for name, value in components.items():
        output[name] = value
    for name in veto.columns:
        if name != "state_name":
            output[name] = veto[name]
    output["source_window_end"] = output.index + pd.Timedelta(hours=1)
    return output, transitions


def aggregation_contract(rules: dict, state_machine: dict) -> dict:
    veto = rules["veto"]
    return {"weights": rules["aggregation"]["weights"],
            "lambda_blend": rules["aggregation"]["lambda_blend"],
            "freeze_thr": veto["freeze_threshold"], "freeze_cap": veto["freeze_cap"],
            "regime_thr": veto["regime_threshold"], "regime_cap": veto["regime_cap"],
            "veto3_step_thr": veto["veto3_step_threshold"],
            "veto3_duration_h": veto["veto3_duration_h"],
            "veto3_min_event_count": veto["veto3_min_event_count_36h"],
            "veto3_cap": veto["veto3_cap"], "sustained_cap": state_machine["sustained_anomaly_cap"]}


class FrozenD1Recovery:
    def __init__(self, sensor: str, cooldown: dict, aggregation: dict, checkpoint: dict | None = None):
        self.sensor = sensor
        self.cooldown = asdict(CooldownConfig(**cooldown))
        self.aggregation = json.loads(json.dumps(aggregation))
        self.binding = fingerprint({"sensor": sensor, "cooldown": self.cooldown,
                                    "aggregation": self.aggregation,
                                    "kernel": {name: content_hash(D1 / name) for name in KERNEL_FILES},
                                    "adapter": content_hash(Path(__file__))})
        self.history = pd.DataFrame(columns=FIELDS, index=pd.DatetimeIndex([]), dtype=float)
        self.events = []
        self.published_hash = None
        if checkpoint is not None:
            if checkpoint.get("schema") != "D1-recovery-full-journal-v1" or checkpoint.get("binding") != self.binding:
                raise ValueError("Checkpoint does not match frozen model/config/code/sensor")
            unsigned = {k: v for k, v in checkpoint.items() if k != "journal_sha256"}
            if fingerprint(unsigned) != checkpoint.get("journal_sha256"):
                raise ValueError("Checkpoint journal fingerprint mismatch")
            self.history = unpack_evidence(checkpoint["evidence"])
            self.events = normalize_events(checkpoint["events"])
            self.published_hash = checkpoint["published_hash"]

    def advance(self, evidence: pd.DataFrame, events: list[dict], *, observed_through: pd.Timestamp):
        if list(evidence.columns) != FIELDS or evidence.empty:
            raise ValueError("Supply nonempty evidence in the frozen field order")
        index = evidence.index
        if (not isinstance(index, pd.DatetimeIndex) or not index.is_unique
                or not index.is_monotonic_increasing
                or (len(index) > 1 and not (index.to_series().diff().dropna() == pd.Timedelta(hours=1)).all())):
            raise ValueError("Evidence requires a complete unique increasing hourly clock")
        if observed_through < index[-1] + pd.Timedelta(hours=1):
            raise ValueError("The last evidence hour is not closed")
        if len(self.history) and index[0] != self.history.index[-1] + pd.Timedelta(hours=1):
            raise ValueError("Cannot overlap, skip or reorder journal hours; insert explicit NA evidence")
        values = evidence.astype(float)
        if np.isinf(values.to_numpy()).any():
            raise ValueError("Infinite detector evidence is invalid")
        if not values.step_confirmed.dropna().isin([0, 1]).all():
            raise ValueError("step_confirmed must be boolean or unknown")
        for name in FIELDS[:5]:
            if not values[name].dropna().between(1, 5).all():
                raise ValueError("Quality scores must be within 1..5 or NA")
        appended = normalize_events(events)
        for event in appended:
            available = pd.Timestamp(event["available_at"])
            if available > index[-1] or (len(self.history) and available <= self.history.index[-1]):
                raise ValueError("New events must arrive in the current evidence block, never retroactively")
        if len({fingerprint(e) for e in self.events + appended}) != len(self.events) + len(appended):
            raise ValueError("Duplicate event journal entry")
        history = values if self.history.empty else pd.concat([self.history, values])
        output, transitions = score_recovery(self.sensor, history, self.events + appended,
                                             self.cooldown, self.aggregation)
        past = len(self.history)
        if past and fingerprint_frame(output.iloc[:past]) != self.published_hash:
            raise RuntimeError("Appending evidence changed published recovery outputs")
        self.history, self.events = history, self.events + appended
        self.published_hash = fingerprint_frame(output)
        return output.iloc[past:].copy(), [t for t in transitions if t["ts"] >= index[0]]

    def checkpoint(self) -> dict:
        result = {"schema": "D1-recovery-full-journal-v1", "binding": self.binding,
                  "evidence": pack_evidence(self.history), "events": self.events,
                  "published_hash": self.published_hash,
                  "state_policy": "full_history_replay_not_compact_streaming_state"}
        result["journal_sha256"] = fingerprint(result)
        return result
