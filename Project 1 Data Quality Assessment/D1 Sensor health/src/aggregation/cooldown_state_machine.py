"""Causal event-level recovery state machine for D1 sensor health.

The public states are Normal, Refractory, BaselinePending,
SustainedAnomaly, RecoveryCandidate, and Recovered. ``Recovered`` is a
monitored observation state rather than a one-hour occupancy marker. Direct
and adapted recovery are recorded as episode outcomes in the transition log.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from src.baseline.local_baseline import find_stable_window, robust_ewma_update


@dataclass
class SensorState:
    sensor_id: str
    state_name: str = "Normal"
    event_id: Optional[str] = None
    event_type: Optional[str] = None
    event_start: Optional[pd.Timestamp] = None
    refractory_start: Optional[pd.Timestamp] = None
    refractory_end: Optional[pd.Timestamp] = None
    direct_recovery_streak: int = 0
    baseline_pending_start: Optional[pd.Timestamp] = None
    baseline_timeout_logged: bool = False
    sustained_flag: bool = False
    sustained_start: Optional[pd.Timestamp] = None
    local_baseline_version: int = 0
    local_baseline_center: Optional[float] = None
    local_baseline_scale: Optional[float] = None
    local_baseline_init_at: Optional[pd.Timestamp] = None
    recovery_streak: int = 0
    recovery_entry_streak: int = 0
    recovery_retry_not_before: Optional[pd.Timestamp] = None
    recovery_window_elapsed: int = 0
    recovery_soft_failures: int = 0
    recovery_missing: int = 0
    recovery_consecutive_soft: int = 0
    recovered_start: Optional[pd.Timestamp] = None
    observation_elapsed: int = 0
    observation_passes: int = 0
    observation_soft_failures: int = 0
    observation_missing: int = 0
    observation_consecutive_soft: int = 0
    recovery_used_contextual_regime: bool = False
    accepted_contextual_regime: bool = False
    last_recovery_check: Optional[pd.Timestamp] = None
    drift_mask_reason: str = ""
    last_event_magnitude: float = 0.0
    last_event_sign: int = 0
    last_event_ts: Optional[pd.Timestamp] = None
    pelt_segment_id: Optional[str] = None


@dataclass
class CooldownConfig:
    step_refractory_h: int = 48
    regime_refractory_h: int = 36
    drift_neutral_score: float = 3.0
    min_event_separation_h: int = 24
    magnitude_change_pct: float = 30.0
    require_direction_change: bool = False
    pelt_match_tolerance_h: int = 3
    require_pelt_for_retrigger: bool = True
    candidate_search_after_step: Tuple[int, int] = (24, 72)
    candidate_search_after_regime: Tuple[int, int] = (48, 96)
    stable_window_h: int = 24
    max_baseline_pending_h: int = 96
    drift_slope_threshold: float = 0.005
    thaw_duration_h: int = 36
    enter_recov_q_step: float = 3.0
    enter_recov_q_regime: float = 3.0
    enter_recov_q_freeze: float = 3.0
    trigger_recov_q_step: float = 2.0
    trigger_recov_q_regime: float = 2.0
    trigger_recov_q_freeze: float = 2.0
    residual_z_max: float = 1.5
    peer_z_max: float = 2.5
    allow_contextual_regime: bool = True
    use_w1_hard_gate: bool = False
    w1_norm_max: float = 1.5
    min_recovery_streak_h: int = 12
    max_recovery_window_h: int = 18
    max_soft_fail_h: int = 2
    max_missing_h: int = 4
    max_consecutive_soft_fail_h: int = 1
    recovery_entry_consecutive_h: int = 3
    recovery_retry_cooldown_h: int = 12
    recovered_observation_h: int = 24
    observation_max_soft_fail_h: int = 4
    observation_max_missing_h: int = 4
    observation_max_total_nonpass_h: int = 4
    observation_max_consecutive_soft_fail_h: int = 2
    direct_recovery_confirmation_h: int = 6
    local_scale_floor: float = 1e-6
    sustained_anomaly_cap: float = 2.5

    def __post_init__(self) -> None:
        positive_ints = {
            "step_refractory_h": self.step_refractory_h,
            "regime_refractory_h": self.regime_refractory_h,
            "stable_window_h": self.stable_window_h,
            "min_recovery_streak_h": self.min_recovery_streak_h,
            "max_recovery_window_h": self.max_recovery_window_h,
            "recovered_observation_h": self.recovered_observation_h,
            "direct_recovery_confirmation_h": self.direct_recovery_confirmation_h,
        }
        invalid = [name for name, value in positive_ints.items() if value <= 0]
        if invalid:
            raise ValueError(f"CooldownConfig values must be positive: {invalid}")
        if self.min_recovery_streak_h > self.max_recovery_window_h:
            raise ValueError("required recovery passes cannot exceed the recovery window")
        if self.recovery_entry_consecutive_h > self.min_recovery_streak_h:
            raise ValueError("entry confirmation cannot exceed required recovery passes")
        if self.observation_max_total_nonpass_h > self.recovered_observation_h:
            raise ValueError("observation non-pass allowance exceeds observation duration")
        if self.local_scale_floor <= 0:
            raise ValueError("local_scale_floor must be positive")

    @classmethod
    def from_dict(cls, data: Dict, *, local_scale_floor: float = 1e-6) -> "CooldownConfig":
        """Build and validate the production configuration from state_machine.yaml."""
        refractory = data["refractory"]
        uniqueness = data["event_uniqueness"]
        sustained = data["sustained_anomaly"]
        search = sustained["candidate_window_search"]
        recovery = data["recovery"]
        enter = recovery["enter_thresholds"]
        trigger = recovery["trigger_thresholds"]
        residual = recovery["residual_check"]
        evidence = recovery["evidence_window"]
        observation = recovery["recovered_observation"]
        return cls(
            step_refractory_h=refractory["step_h"],
            regime_refractory_h=refractory["regime_h"],
            drift_neutral_score=refractory["drift_neutral_score"],
            min_event_separation_h=uniqueness["min_separation_h"],
            magnitude_change_pct=uniqueness["magnitude_change_pct"],
            require_direction_change=uniqueness["require_direction_change"],
            pelt_match_tolerance_h=uniqueness["pelt_match_tolerance_h"],
            require_pelt_for_retrigger=uniqueness["require_pelt_for_retrigger"],
            candidate_search_after_step=tuple(search["step_after_h"]),
            candidate_search_after_regime=tuple(search["regime_after_h"]),
            stable_window_h=search["stable_window_h"],
            max_baseline_pending_h=search["max_baseline_pending_h"],
            drift_slope_threshold=sustained["baseline_init"]["drift_slope_threshold"],
            thaw_duration_h=sustained["thaw"]["duration_h"],
            enter_recov_q_step=enter["Q_step_min"],
            enter_recov_q_regime=enter["Q_regime_min"],
            enter_recov_q_freeze=enter["Q_freeze_min"],
            trigger_recov_q_step=trigger["Q_step_max"],
            trigger_recov_q_regime=trigger["Q_regime_max"],
            trigger_recov_q_freeze=trigger["Q_freeze_max"],
            residual_z_max=residual["max_z_score"],
            peer_z_max=residual["peer_z_max"],
            allow_contextual_regime=residual["allow_contextual_regime"],
            use_w1_hard_gate=residual["use_w1_hard_gate"],
            w1_norm_max=residual["max_w1_norm_diagnostic"],
            min_recovery_streak_h=evidence["required_pass_h"],
            max_recovery_window_h=evidence["max_window_h"],
            max_soft_fail_h=evidence["max_soft_fail_h"],
            max_missing_h=evidence["max_missing_h"],
            max_consecutive_soft_fail_h=evidence["max_consecutive_soft_fail_h"],
            recovery_entry_consecutive_h=evidence["entry_consecutive_h"],
            recovery_retry_cooldown_h=evidence["retry_cooldown_h"],
            recovered_observation_h=observation["duration_h"],
            observation_max_soft_fail_h=observation["max_soft_fail_h"],
            observation_max_missing_h=observation["max_missing_h"],
            observation_max_total_nonpass_h=observation["max_total_nonpass_h"],
            observation_max_consecutive_soft_fail_h=observation["max_consecutive_soft_fail_h"],
            direct_recovery_confirmation_h=recovery["direct_recovery"]["confirmation_h"],
            local_scale_floor=local_scale_floor,
            sustained_anomaly_cap=data["sustained_anomaly_cap"],
        )


def _finite(value: float) -> bool:
    return bool(np.isfinite(value))


def _series_value(series: Optional[pd.Series], i: int) -> float:
    if series is None or pd.isna(series.iat[i]):
        return float("nan")
    return float(series.iat[i])


def _signed_shift(resid: pd.Series, i: int, lookback_h: int = 12) -> float:
    current = _series_value(resid, i)
    start = max(0, i - lookback_h)
    history = resid.iloc[start:i].dropna()
    if not _finite(current) or len(history) < 3:
        return 0.0
    return float(current - np.median(history.to_numpy(dtype=float)))


def _normalise_pelt_events(events: Optional[Sequence]) -> List[Dict]:
    normalised: List[Dict] = []
    for item in events or []:
        if isinstance(item, dict):
            ts = pd.Timestamp(item["timestamp"])
            before = item.get("before_mean")
            after = item.get("after_mean")
            if before is not None and after is not None:
                signed = float(after) - float(before)
            else:
                signed = float(item.get("signed_magnitude", item.get("magnitude", 0.0)))
            available_at = pd.Timestamp(item.get("available_at", item.get("detected_at", ts)))
        else:
            ts = pd.Timestamp(item)
            signed = 0.0
            available_at = ts
        normalised.append({
            "timestamp": ts,
            "available_at": available_at,
            "signed_magnitude": signed,
            "segment_id": f"pelt_{ts.strftime('%Y%m%dT%H')}",
        })
    return sorted(normalised, key=lambda event: event["timestamp"])


def _match_pelt_event(
    ts: pd.Timestamp,
    events: Sequence[Dict],
    consumed: set,
    tolerance_h: int,
) -> Optional[Dict]:
    tolerance = pd.Timedelta(hours=tolerance_h)
    candidates = [
        event for event in events
        if event["segment_id"] not in consumed
        and event["available_at"] <= ts
        and (
            abs(event["timestamp"] - ts) <= tolerance
            or abs(event["available_at"] - ts) <= tolerance
        )
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda event: abs(event["timestamp"] - ts))


def detect_event_id(
    ts: pd.Timestamp,
    ks_stat: float,
    w1_norm: float,
    prev_state: SensorState,
    prev_event_ts: Optional[pd.Timestamp],
    prev_event_magnitude: float,
    prev_event_sign: int,
    event_type: str,
    cfg: CooldownConfig,
    *,
    signed_shift: Optional[float] = None,
    pelt_segment_id: Optional[str] = None,
    active_episode: bool = False,
) -> Optional[str]:
    """Return a new event ID only for an independent event candidate."""
    raw = signed_shift
    if raw is None or not _finite(float(raw)):
        raw = ks_stat if event_type == "step" else w1_norm
    signed = float(raw) if _finite(float(raw)) else 0.0
    magnitude = abs(signed)
    sign = int(np.sign(signed))

    if prev_event_ts is None:
        suffix = pelt_segment_id or ts.strftime("%Y%m%dT%H")
        return f"{prev_state.sensor_id}:{event_type}:{suffix}"
    elapsed_h = (ts - prev_event_ts).total_seconds() / 3600.0
    if elapsed_h < cfg.min_event_separation_h:
        return None
    if not active_episode:
        suffix = pelt_segment_id or ts.strftime("%Y%m%dT%H")
        return f"{prev_state.sensor_id}:{event_type}:{suffix}"
    if cfg.require_pelt_for_retrigger and pelt_segment_id is None:
        return None

    rel_change = abs(magnitude - prev_event_magnitude) / max(prev_event_magnitude, 1e-6)
    direction_change = sign != 0 and prev_event_sign != 0 and sign != prev_event_sign
    magnitude_change = rel_change >= cfg.magnitude_change_pct / 100.0
    independent = direction_change if cfg.require_direction_change else (direction_change or magnitude_change)
    if not independent:
        return None
    suffix = pelt_segment_id or ts.strftime("%Y%m%dT%H")
    return f"{prev_state.sensor_id}:{event_type}:{suffix}"


def alpha_schedule(hours_since_start: float, duration_h: int, schedule: str = "linear") -> float:
    if hours_since_start < 0:
        return 1.0
    if hours_since_start >= duration_h:
        return 0.0
    if schedule == "exponential":
        return float(np.exp(-3 * hours_since_start / duration_h))
    return 1.0 - hours_since_start / duration_h


def compute_q_drift_new(
    resid_value: float,
    baseline_center: float,
    baseline_scale: float,
    scale_floor: float = 1e-6,
) -> float:
    if not _finite(resid_value) or baseline_center is None or baseline_scale is None:
        return 3.0
    z = abs(resid_value - baseline_center) / max(baseline_scale, scale_floor)
    q = 1 + 4 / (1 + np.exp(1.5 * (z - 2.5)))
    return float(np.clip(q, 1, 5))


def _direct_recovery_ready(qs: float, qr: float, qf: float, cfg: CooldownConfig) -> bool:
    return (
        _finite(qs) and _finite(qr) and _finite(qf)
        and qs >= cfg.enter_recov_q_step
        and qr >= cfg.enter_recov_q_regime
        and qf >= cfg.enter_recov_q_freeze
    )


def _recovery_gate(
    qs: float,
    qr: float,
    qf: float,
    w1: float,
    rv: float,
    peer_z: float,
    state: SensorState,
    cfg: CooldownConfig,
) -> Dict:
    if state.local_baseline_center is None or state.local_baseline_scale is None or not _finite(rv):
        return {"status": "missing", "reason": "local_baseline_unavailable", "local_z": np.nan,
                "regime_acceptance": "none"}

    scale = max(state.local_baseline_scale, cfg.local_scale_floor)
    local_z = abs(rv - state.local_baseline_center) / scale
    historical_regime = _finite(qr) and qr >= cfg.enter_recov_q_regime
    contextual_regime = (
        cfg.allow_contextual_regime
        and _finite(peer_z)
        and abs(peer_z) <= cfg.peer_z_max
        and local_z < cfg.residual_z_max
    )
    regime_ok = historical_regime or contextual_regime
    regime_acceptance = "historical" if historical_regime else (
        "contextual" if contextual_regime else "none"
    )

    required_missing = not (_finite(qs) and _finite(qf))
    if not historical_regime and not _finite(peer_z):
        required_missing = required_missing or not _finite(qr)
    if cfg.use_w1_hard_gate and not _finite(w1):
        required_missing = True
    if required_missing:
        return {"status": "missing", "reason": "required_evidence_missing", "local_z": local_z,
                "regime_acceptance": regime_acceptance}

    hard_fail = (
        qs <= cfg.trigger_recov_q_step
        or qf <= cfg.trigger_recov_q_freeze
    )
    if hard_fail:
        return {"status": "hard_fail", "reason": "hard_quality_gate", "local_z": local_z,
                "regime_acceptance": regime_acceptance}

    passed = (
        qs >= cfg.enter_recov_q_step
        and qf >= cfg.enter_recov_q_freeze
        and regime_ok
        and local_z < cfg.residual_z_max
    )
    if cfg.use_w1_hard_gate:
        passed = passed and w1 < cfg.w1_norm_max
    return {
        "status": "pass" if passed else "soft_fail",
        "reason": "all_recovery_gates" if passed else "soft_quality_gate",
        "local_z": local_z,
        "regime_acceptance": regime_acceptance,
    }


def _reset_candidate(state: SensorState) -> None:
    state.recovery_streak = 0
    state.recovery_entry_streak = 0
    state.recovery_window_elapsed = 0
    state.recovery_soft_failures = 0
    state.recovery_missing = 0
    state.recovery_consecutive_soft = 0


def _reset_observation(state: SensorState) -> None:
    state.recovered_start = None
    state.observation_elapsed = 0
    state.observation_passes = 0
    state.observation_soft_failures = 0
    state.observation_missing = 0
    state.observation_consecutive_soft = 0


def _close_episode(state: SensorState, keep_contextual_baseline: bool) -> None:
    state.event_id = None
    state.event_type = None
    state.event_start = None
    state.refractory_start = None
    state.refractory_end = None
    state.direct_recovery_streak = 0
    state.baseline_pending_start = None
    state.baseline_timeout_logged = False
    state.sustained_flag = False
    state.sustained_start = None
    _reset_candidate(state)
    _reset_observation(state)
    if not keep_contextual_baseline:
        state.local_baseline_center = None
        state.local_baseline_scale = None
        state.local_baseline_init_at = None
        state.accepted_contextual_regime = False
    state.recovery_used_contextual_regime = False
    state.recovery_retry_not_before = None
    state.pelt_segment_id = None


def run_cooldown_state_machine(
    sensor_id: str,
    Q_step: pd.Series,
    Q_regime: pd.Series,
    Q_drift: pd.Series,
    Q_freeze: pd.Series,
    ks_stat: pd.Series,
    w1_norm: pd.Series,
    resid_h: pd.Series,
    pelt_changepoints: Sequence,
    step_confirmed: Optional[pd.Series] = None,
    peer_residual_z: Optional[pd.Series] = None,
    cfg: Optional[CooldownConfig] = None,
) -> Tuple[pd.Series, pd.DataFrame, List[Dict]]:
    """Run the causal D1 recovery state machine for one sensor channel."""
    cfg = cfg or CooldownConfig()
    index = Q_step.index
    n = len(index)
    state = SensorState(sensor_id=sensor_id)
    q_drift_eff = Q_drift.copy().astype(float)
    pelt_events = _normalise_pelt_events(pelt_changepoints)
    consumed_pelt: set = set()
    transitions: List[Dict] = []

    columns: Dict[str, np.ndarray] = {
        "state_name": np.empty(n, dtype=object),
        "event_id": np.empty(n, dtype=object),
        "event_type": np.empty(n, dtype=object),
        "pelt_segment_id": np.empty(n, dtype=object),
        "local_baseline_version": np.zeros(n, dtype=int),
        "local_baseline_scale": np.full(n, np.nan),
        "sustained_flag": np.zeros(n, dtype=bool),
        "recovery_streak": np.zeros(n, dtype=int),
        "recovery_entry_streak": np.zeros(n, dtype=int),
        "recovery_window_elapsed": np.zeros(n, dtype=int),
        "recovery_soft_failures": np.zeros(n, dtype=int),
        "recovery_missing": np.zeros(n, dtype=int),
        "observation_elapsed": np.zeros(n, dtype=int),
        "observation_passes": np.zeros(n, dtype=int),
        "direct_recovery_streak": np.zeros(n, dtype=int),
        "drift_mask_reason": np.empty(n, dtype=object),
        "recovery_gate_status": np.empty(n, dtype=object),
        "recovery_gate_reason": np.empty(n, dtype=object),
        "regime_acceptance": np.empty(n, dtype=object),
        "local_z": np.full(n, np.nan),
        "alpha": np.zeros(n, dtype=float),
        "step_suspicion_flag": np.zeros(n, dtype=np.int8),
        "accepted_contextual_regime": np.zeros(n, dtype=bool),
        "episode_outcome": np.empty(n, dtype=object),
    }

    for i, ts in enumerate(index):
        qs = _series_value(Q_step, i)
        qr = _series_value(Q_regime, i)
        qd = _series_value(Q_drift, i)
        qf = _series_value(Q_freeze, i)
        ks = _series_value(ks_stat, i)
        w1 = _series_value(w1_norm, i)
        rv = _series_value(resid_h, i)
        peer_z = _series_value(peer_residual_z, i)
        is_step_confirmed = (
            bool(step_confirmed.iat[i]) if step_confirmed is not None and not pd.isna(step_confirmed.iat[i])
            else (_finite(qs) and qs <= cfg.trigger_recov_q_step)
        )
        columns["step_suspicion_flag"][i] = int(_finite(qs) and qs <= 2.5)
        signed_shift = _signed_shift(resid_h, i)

        pelt_match = _match_pelt_event(ts, pelt_events, consumed_pelt, cfg.pelt_match_tolerance_h)
        new_event_type: Optional[str] = None
        if is_step_confirmed:
            new_event_type = "step"
        elif (
            _finite(qr)
            and qr <= cfg.trigger_recov_q_regime
            and (not state.accepted_contextual_regime or pelt_match is not None)
        ):
            new_event_type = "regime"

        new_event_id: Optional[str] = None
        if new_event_type is not None:
            pelt_id = pelt_match["segment_id"] if pelt_match is not None else None
            event_shift = (
                pelt_match["signed_magnitude"]
                if pelt_match is not None and pelt_match["signed_magnitude"] != 0
                else signed_shift
            )
            new_event_id = detect_event_id(
                ts, ks, w1, state, state.last_event_ts, state.last_event_magnitude,
                state.last_event_sign, new_event_type, cfg,
                signed_shift=event_shift, pelt_segment_id=pelt_id,
                active_episode=state.state_name != "Normal",
            )

        episode_outcome = ""
        if new_event_id is not None:
            previous_event_id = state.event_id
            previous_state = state.state_name
            if pelt_match is not None:
                consumed_pelt.add(pelt_match["segment_id"])
            event_shift = (
                pelt_match["signed_magnitude"]
                if pelt_match is not None and pelt_match["signed_magnitude"] != 0
                else signed_shift
            )
            state.state_name = "Refractory"
            state.event_id = new_event_id
            state.event_type = new_event_type
            state.event_start = ts
            state.refractory_start = ts
            duration = cfg.step_refractory_h if new_event_type == "step" else cfg.regime_refractory_h
            state.refractory_end = ts + pd.Timedelta(hours=duration)
            state.baseline_pending_start = None
            state.baseline_timeout_logged = False
            state.sustained_flag = False
            state.sustained_start = None
            state.local_baseline_center = None
            state.local_baseline_scale = None
            state.local_baseline_init_at = None
            state.accepted_contextual_regime = False
            state.recovery_used_contextual_regime = False
            state.recovery_retry_not_before = None
            _reset_candidate(state)
            _reset_observation(state)
            state.last_event_ts = ts
            state.last_event_magnitude = abs(float(event_shift))
            state.last_event_sign = int(np.sign(event_shift))
            state.pelt_segment_id = pelt_match["segment_id"] if pelt_match is not None else None
            state.drift_mask_reason = f"refractory_{new_event_type}_event"
            transitions.append({
                "sensor_id": sensor_id,
                "ts": ts,
                "from_state": previous_state,
                "to_state": "Refractory",
                "event_id": new_event_id,
                "event_type": new_event_type,
                "trigger": "new_independent_event",
                "pelt_segment_id": state.pelt_segment_id,
                "signed_magnitude": float(event_shift),
                "previous_event_id": previous_event_id,
                "previous_outcome": "superseded" if previous_event_id else "",
            })

        elif state.state_name == "Refractory" and ts >= state.refractory_end:
            if _direct_recovery_ready(qs, qr, qf, cfg):
                state.direct_recovery_streak += 1
                state.drift_mask_reason = "direct_recovery_confirmation"
                if state.direct_recovery_streak >= cfg.direct_recovery_confirmation_h:
                    event_id = state.event_id
                    event_start = state.event_start
                    state.state_name = "Normal"
                    episode_outcome = "direct_recovery"
                    transitions.append({
                        "sensor_id": sensor_id, "ts": ts,
                        "from_state": "Refractory", "to_state": "Normal",
                        "event_id": event_id, "event_type": state.event_type,
                        "event_start": event_start, "trigger": "direct_recovery_confirmed",
                        "direct_confirmation_h": state.direct_recovery_streak,
                        "episode_outcome": episode_outcome,
                    })
                    _close_episode(state, keep_contextual_baseline=False)
                    state.drift_mask_reason = ""
            else:
                state.direct_recovery_streak = 0
                state.state_name = "BaselinePending"
                state.baseline_pending_start = ts
                state.sustained_flag = True
                state.drift_mask_reason = "baseline_pending_causal_accumulation"
                transitions.append({
                    "sensor_id": sensor_id, "ts": ts,
                    "from_state": "Refractory", "to_state": "BaselinePending",
                    "event_id": state.event_id, "event_type": state.event_type,
                    "trigger": "anomaly_persists_baseline_pending",
                })

        elif state.state_name == "BaselinePending":
            if _direct_recovery_ready(qs, qr, qf, cfg):
                state.direct_recovery_streak += 1
                state.drift_mask_reason = "direct_recovery_confirmation_after_pending"
                if state.direct_recovery_streak >= cfg.direct_recovery_confirmation_h:
                    event_id = state.event_id
                    event_start = state.event_start
                    state.state_name = "Normal"
                    episode_outcome = "direct_recovery"
                    transitions.append({
                        "sensor_id": sensor_id, "ts": ts,
                        "from_state": "BaselinePending", "to_state": "Normal",
                        "event_id": event_id, "event_type": state.event_type,
                        "event_start": event_start, "trigger": "direct_recovery_after_pending_confirmed",
                        "direct_confirmation_h": state.direct_recovery_streak,
                        "episode_outcome": episode_outcome,
                    })
                    _close_episode(state, keep_contextual_baseline=False)
                    state.drift_mask_reason = ""
            else:
                state.direct_recovery_streak = 0
                candidate = find_stable_window(
                    resid_h, state.baseline_pending_start, ts,
                    stable_h=cfg.stable_window_h,
                    max_slope=cfg.drift_slope_threshold,
                    scale_floor=cfg.local_scale_floor,
                )
                if candidate is not None:
                    state.local_baseline_center = candidate["center"]
                    state.local_baseline_scale = candidate["scale"]
                    state.local_baseline_init_at = candidate["end"]
                    state.local_baseline_version += 1
                    state.state_name = "SustainedAnomaly"
                    state.sustained_start = ts
                    state.drift_mask_reason = "sustained_local_baseline_active"
                    transitions.append({
                        "sensor_id": sensor_id, "ts": ts,
                        "from_state": "BaselinePending", "to_state": "SustainedAnomaly",
                        "event_id": state.event_id, "event_type": state.event_type,
                        "trigger": "causal_stable_baseline_mature",
                        "baseline_center": candidate["center"],
                        "baseline_scale": candidate["scale"],
                        "baseline_raw_scale": candidate["raw_scale"],
                        "baseline_scale_floor": candidate["scale_floor"],
                        "baseline_init_window": (candidate["start"], candidate["end"]),
                    })
                else:
                    pending_h = (ts - state.baseline_pending_start).total_seconds() / 3600.0
                    if pending_h >= cfg.max_baseline_pending_h:
                        state.drift_mask_reason = "baseline_pending_right_censor_risk"
                        state.baseline_timeout_logged = True

        elif state.state_name in ("SustainedAnomaly", "RecoveryCandidate"):
            gate = _recovery_gate(qs, qr, qf, w1, rv, peer_z, state, cfg)
            state.last_recovery_check = ts
            if state.state_name == "SustainedAnomaly":
                retry_ready = (
                    state.recovery_retry_not_before is None
                    or ts >= state.recovery_retry_not_before
                )
                if gate["status"] == "pass" and retry_ready:
                    state.recovery_entry_streak += 1
                else:
                    state.recovery_entry_streak = 0
                if state.recovery_entry_streak >= cfg.recovery_entry_consecutive_h:
                    state.state_name = "RecoveryCandidate"
                    state.recovery_streak = state.recovery_entry_streak
                    state.recovery_window_elapsed = state.recovery_entry_streak
                    state.recovery_used_contextual_regime = gate["regime_acceptance"] == "contextual"
                    transitions.append({
                        "sensor_id": sensor_id, "ts": ts,
                        "from_state": "SustainedAnomaly", "to_state": "RecoveryCandidate",
                        "event_id": state.event_id, "event_type": state.event_type,
                        "trigger": "recovery_evidence_started",
                        "regime_acceptance": gate["regime_acceptance"],
                        "entry_confirmation_h": state.recovery_entry_streak,
                    })
            else:
                state.recovery_window_elapsed += 1
                if gate["status"] == "pass":
                    state.recovery_streak += 1
                    state.recovery_consecutive_soft = 0
                    state.recovery_used_contextual_regime |= gate["regime_acceptance"] == "contextual"
                elif gate["status"] == "soft_fail":
                    state.recovery_soft_failures += 1
                    state.recovery_consecutive_soft += 1
                elif gate["status"] == "missing":
                    state.recovery_missing += 1
                    state.recovery_consecutive_soft = 0

                failed = (
                    gate["status"] == "hard_fail"
                    or state.recovery_soft_failures > cfg.max_soft_fail_h
                    or state.recovery_missing > cfg.max_missing_h
                    or state.recovery_consecutive_soft > cfg.max_consecutive_soft_fail_h
                    or (
                        state.recovery_window_elapsed >= cfg.max_recovery_window_h
                        and state.recovery_streak < cfg.min_recovery_streak_h
                    )
                )
                if state.recovery_streak >= cfg.min_recovery_streak_h:
                    state.state_name = "Recovered"
                    state.recovered_start = ts
                    state.sustained_flag = False
                    state.drift_mask_reason = "recovered_observation_active"
                    transitions.append({
                        "sensor_id": sensor_id, "ts": ts,
                        "from_state": "RecoveryCandidate", "to_state": "Recovered",
                        "event_id": state.event_id, "event_type": state.event_type,
                        "trigger": "required_recovery_evidence_reached",
                        "recovery_pass_h": state.recovery_streak,
                        "recovery_window_h": state.recovery_window_elapsed,
                        "soft_fail_h": state.recovery_soft_failures,
                        "missing_h": state.recovery_missing,
                    })
                elif failed:
                    transitions.append({
                        "sensor_id": sensor_id, "ts": ts,
                        "from_state": "RecoveryCandidate", "to_state": "SustainedAnomaly",
                        "event_id": state.event_id, "event_type": state.event_type,
                        "trigger": f"recovery_candidate_failed:{gate['status']}",
                        "recovery_pass_h": state.recovery_streak,
                        "recovery_window_h": state.recovery_window_elapsed,
                        "soft_fail_h": state.recovery_soft_failures,
                        "missing_h": state.recovery_missing,
                    })
                    state.state_name = "SustainedAnomaly"
                    state.sustained_flag = True
                    _reset_candidate(state)
                    state.recovery_retry_not_before = ts + pd.Timedelta(
                        hours=cfg.recovery_retry_cooldown_h
                    )

        elif state.state_name == "Recovered":
            gate = _recovery_gate(qs, qr, qf, w1, rv, peer_z, state, cfg)
            state.last_recovery_check = ts
            state.observation_elapsed += 1
            if gate["status"] == "pass":
                state.observation_passes += 1
                state.observation_consecutive_soft = 0
                state.recovery_used_contextual_regime |= gate["regime_acceptance"] == "contextual"
            elif gate["status"] == "soft_fail":
                state.observation_soft_failures += 1
                state.observation_consecutive_soft += 1
            elif gate["status"] == "missing":
                state.observation_missing += 1
                state.observation_consecutive_soft = 0

            relapsed = (
                gate["status"] == "hard_fail"
                or state.observation_soft_failures > cfg.observation_max_soft_fail_h
                or state.observation_missing > cfg.observation_max_missing_h
                or (
                    state.observation_soft_failures + state.observation_missing
                    > cfg.observation_max_total_nonpass_h
                )
                or state.observation_consecutive_soft > cfg.observation_max_consecutive_soft_fail_h
            )
            if relapsed:
                transitions.append({
                    "sensor_id": sensor_id, "ts": ts,
                    "from_state": "Recovered", "to_state": "SustainedAnomaly",
                    "event_id": state.event_id, "event_type": state.event_type,
                    "trigger": f"recovered_observation_failed:{gate['status']}",
                    "observation_h": state.observation_elapsed,
                })
                state.state_name = "SustainedAnomaly"
                state.sustained_flag = True
                _reset_candidate(state)
                _reset_observation(state)
                state.recovery_retry_not_before = ts + pd.Timedelta(
                    hours=cfg.recovery_retry_cooldown_h
                )
            elif state.observation_elapsed >= cfg.recovered_observation_h:
                event_id = state.event_id
                event_type = state.event_type
                event_start = state.event_start
                use_context = state.recovery_used_contextual_regime
                transitions.append({
                    "sensor_id": sensor_id, "ts": ts,
                    "from_state": "Recovered", "to_state": "Normal",
                    "event_id": event_id, "event_type": event_type,
                    "event_start": event_start,
                    "trigger": "adapted_recovery_confirmed",
                    "episode_outcome": "adapted_recovery",
                    "observation_h": state.observation_elapsed,
                    "observation_pass_h": state.observation_passes,
                    "used_contextual_regime": use_context,
                })
                state.state_name = "Normal"
                state.accepted_contextual_regime = use_context
                episode_outcome = "adapted_recovery"
                _close_episode(state, keep_contextual_baseline=use_context)
                state.drift_mask_reason = (
                    "accepted_contextual_local_baseline" if use_context else ""
                )

        gate = _recovery_gate(qs, qr, qf, w1, rv, peer_z, state, cfg)
        adaptive_baseline = (
            state.state_name in ("SustainedAnomaly", "RecoveryCandidate", "Recovered")
            or (state.state_name == "Normal" and state.accepted_contextual_regime)
        )
        if state.state_name in ("Refractory", "BaselinePending"):
            q_drift_eff.iat[i] = cfg.drift_neutral_score
            columns["alpha"][i] = 1.0
        elif adaptive_baseline and state.local_baseline_center is not None:
            if state.local_baseline_init_at is not None:
                hours_since = (ts - state.local_baseline_init_at).total_seconds() / 3600.0
            else:
                hours_since = cfg.thaw_duration_h
            alpha = 0.0 if state.state_name == "Normal" else alpha_schedule(
                hours_since, cfg.thaw_duration_h, "linear"
            )
            if state.state_name == "RecoveryCandidate":
                alpha = max(0.0, alpha - 0.2)
            columns["alpha"][i] = alpha
            local_z = abs(rv - state.local_baseline_center) / max(
                state.local_baseline_scale, cfg.local_scale_floor
            ) if _finite(rv) else np.nan
            if _finite(local_z) and local_z <= 2.5 and _finite(qf) and qf >= 4.0 and _finite(qs) and qs >= 3.0:
                state.local_baseline_center, state.local_baseline_scale = robust_ewma_update(
                    state.local_baseline_center, state.local_baseline_scale, rv,
                    rate=0.05, scale_min=cfg.local_scale_floor,
                )
            q_new = compute_q_drift_new(
                rv, state.local_baseline_center, state.local_baseline_scale,
                scale_floor=cfg.local_scale_floor,
            )
            q_drift_eff.iat[i] = alpha * cfg.drift_neutral_score + (1 - alpha) * q_new
        else:
            q_drift_eff.iat[i] = qd if _finite(qd) else np.nan
            columns["alpha"][i] = 0.0

        columns["state_name"][i] = state.state_name
        columns["event_id"][i] = state.event_id
        columns["event_type"][i] = state.event_type
        columns["pelt_segment_id"][i] = state.pelt_segment_id
        columns["local_baseline_version"][i] = state.local_baseline_version
        columns["local_baseline_scale"][i] = (
            state.local_baseline_scale if state.local_baseline_scale is not None else np.nan
        )
        columns["sustained_flag"][i] = state.sustained_flag
        columns["recovery_streak"][i] = state.recovery_streak
        columns["recovery_entry_streak"][i] = state.recovery_entry_streak
        columns["recovery_window_elapsed"][i] = state.recovery_window_elapsed
        columns["recovery_soft_failures"][i] = state.recovery_soft_failures
        columns["recovery_missing"][i] = state.recovery_missing
        columns["observation_elapsed"][i] = state.observation_elapsed
        columns["observation_passes"][i] = state.observation_passes
        columns["direct_recovery_streak"][i] = state.direct_recovery_streak
        columns["drift_mask_reason"][i] = state.drift_mask_reason
        columns["recovery_gate_status"][i] = gate["status"]
        columns["recovery_gate_reason"][i] = gate["reason"]
        columns["regime_acceptance"][i] = gate["regime_acceptance"]
        columns["local_z"][i] = gate["local_z"]
        columns["accepted_contextual_regime"][i] = state.accepted_contextual_regime
        columns["episode_outcome"][i] = episode_outcome

    state_log = pd.DataFrame(columns, index=index)
    return q_drift_eff.clip(1, 5), state_log, transitions
