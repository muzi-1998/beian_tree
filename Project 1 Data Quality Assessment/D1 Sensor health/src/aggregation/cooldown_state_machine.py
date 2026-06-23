"""cooldown_state_machine.py — D1 v1.1 5-state cooldown machine.

Compliant with: Cooldown_机制修订版正式文本_无泵状态最终版.docx

States:
    Normal              — full sub-score aggregation
    Refractory          — new event_id triggered, fixed isolation period;
                          Q_drift = neutral 3.0
    SustainedAnomaly    — Refractory ended, anomaly persists, NO new event_id;
                          local baseline rebuilt; Q_drift_eff = α·3.0 + (1-α)·Q_drift_new
    RecoveryCandidate   — local stable signs, recovery_streak accumulates
    Recovered           — recovery confirmed, return to Normal

Key principle (§三):
    1. Cooldown is triggered ONLY by NEW independent events (event_id change),
       not by sustained low score levels.
    2. SustainedAnomaly recognises persistent abnormal *steady* state; system
       must regain ability to discriminate inside the new steady state.
    3. Recovery requires hysteresis (双阈值滞回) and ≥24h continuous evidence.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Tuple

from src.baseline.local_baseline import find_stable_window, robust_ewma_update


# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class SensorState:
    """Per-sensor live state. One instance per scored channel."""
    sensor_id: str
    state_name: str = "Normal"
    event_id: Optional[str] = None
    refractory_start: Optional[pd.Timestamp] = None
    refractory_end: Optional[pd.Timestamp] = None
    sustained_flag: bool = False
    local_baseline_version: int = 0
    local_baseline_center: Optional[float] = None
    local_baseline_scale: Optional[float] = None
    local_baseline_init_at: Optional[pd.Timestamp] = None
    recovery_streak: int = 0
    last_recovery_check: Optional[pd.Timestamp] = None
    drift_mask_reason: str = ""
    last_event_magnitude: float = 0.0
    last_event_sign: int = 0
    sustained_start: Optional[pd.Timestamp] = None  # when SustainedAnomaly began


@dataclass
class CooldownConfig:
    step_refractory_h: int = 24
    regime_refractory_h: int = 36
    drift_neutral_score: float = 3.0
    min_event_separation_h: int = 12
    magnitude_change_pct: float = 30.0
    candidate_search_after_step: Tuple[int, int] = (24, 72)
    candidate_search_after_regime: Tuple[int, int] = (48, 96)
    stable_window_h: int = 24
    drift_slope_threshold: float = 0.005
    thaw_duration_h: int = 36
    enter_recov_q_step: float = 3.2
    enter_recov_q_regime: float = 3.0
    enter_recov_q_freeze: float = 3.5
    residual_z_max: float = 1.5
    w1_norm_max: float = 1.5
    min_recovery_streak_h: int = 24
    sustained_anomaly_cap: float = 2.5


# ─────────────────────────────────────────────────────────────────────────────
def detect_event_id(ts: pd.Timestamp, ks_stat: float, w1_norm: float,
                     prev_state: SensorState, prev_event_ts: Optional[pd.Timestamp],
                     prev_event_magnitude: float, prev_event_sign: int,
                     event_type: str, cfg: CooldownConfig
                     ) -> Optional[str]:
    """Return a new event_id if this is a NEW independent event, else None.

    Per §五: only NEW event_id triggers Refractory. Same persistent low score
    does NOT refresh cooldown.
    """
    # Compute current event signature
    if event_type == "step":
        magnitude = float(ks_stat) if not np.isnan(ks_stat) else 0.0
    else:  # regime
        magnitude = float(w1_norm) if not np.isnan(w1_norm) else 0.0
    sign = int(np.sign(magnitude))

    # First-ever event for this sensor
    if prev_event_ts is None or prev_event_magnitude == 0:
        return f"{event_type}_{ts.strftime('%Y%m%dT%H')}"

    # Check minimum time separation
    elapsed_h = (ts - prev_event_ts).total_seconds() / 3600.0
    if elapsed_h < cfg.min_event_separation_h:
        return None  # Not yet eligible

    # Check magnitude change OR direction flip
    if prev_event_magnitude > 0:
        rel_change = abs(magnitude - prev_event_magnitude) / max(prev_event_magnitude, 1e-6)
    else:
        rel_change = 1.0
    direction_change = (sign != 0 and prev_event_sign != 0 and sign != prev_event_sign)

    if rel_change >= cfg.magnitude_change_pct / 100 or direction_change:
        return f"{event_type}_{ts.strftime('%Y%m%dT%H')}"
    return None


def alpha_schedule(hours_since_thaw_start: float, thaw_duration_h: int,
                    schedule: str = "linear") -> float:
    """α(t): controls Q_drift mixing during thaw. α=1 → fully neutral 3.0;
    α=0 → fully use Q_drift_new from local baseline.
    """
    if hours_since_thaw_start < 0: return 1.0
    if hours_since_thaw_start >= thaw_duration_h: return 0.0
    if schedule == "linear":
        return 1.0 - hours_since_thaw_start / thaw_duration_h
    elif schedule == "exponential":
        return float(np.exp(-3 * hours_since_thaw_start / thaw_duration_h))
    return 1.0 - hours_since_thaw_start / thaw_duration_h


def compute_q_drift_new(resid_value: float, baseline_center: float,
                         baseline_scale: float) -> float:
    """Compute Q_drift_new from local baseline residual z-score."""
    if baseline_scale is None or baseline_scale <= 0:
        return 3.0
    z = abs(resid_value - baseline_center) / max(baseline_scale, 1e-3)
    # Sigmoid mapping (consistent with main scheme §3.1)
    # z=0 → Q=5; z=2 → Q≈3; z=4 → Q≈1
    q = 1 + 4 / (1 + np.exp(1.5 * (z - 2.5)))
    return float(np.clip(q, 1, 5))


# ─────────────────────────────────────────────────────────────────────────────
def run_cooldown_state_machine(sensor_id: str,
                                Q_step: pd.Series, Q_regime: pd.Series,
                                Q_drift: pd.Series, Q_freeze: pd.Series,
                                ks_stat: pd.Series, w1_norm: pd.Series,
                                resid_h: pd.Series,
                                pelt_changepoints: List[pd.Timestamp],
                                step_confirmed: pd.Series = None,
                                cfg: CooldownConfig = None,
                                ) -> Tuple[pd.Series, pd.DataFrame, List[Dict]]:
    """Apply 5-state cooldown machine to one sensor's hourly time-series.

    Returns
    -------
    Q_drift_eff : pd.Series — α-thawed effective drift score
    state_log   : DataFrame — per-hour state, event_id, baseline_version, etc.
    transitions : List[Dict] — every state-transition event for blackboard
    """
    if cfg is None:
        cfg = CooldownConfig()
    idx = Q_step.index
    n = len(idx)
    ss = SensorState(sensor_id=sensor_id)
    Q_drift_eff = Q_drift.copy().astype(float)

    # State log per hour
    state_arr = np.empty(n, dtype=object)
    event_id_arr = np.empty(n, dtype=object)
    baseline_v_arr = np.zeros(n, dtype=int)
    sustained_arr = np.zeros(n, dtype=bool)
    recov_streak_arr = np.zeros(n, dtype=int)
    drift_mask_reason_arr = np.empty(n, dtype=object)
    alpha_arr = np.zeros(n, dtype=float)
    step_suspicion_arr = np.zeros(n, dtype=np.int8)  # Q_step_24 ≤ 2.5 （仅标记）

    transitions: List[Dict] = []
    last_event_ts = None

    # PELT change-point set for batch confirmation
    pelt_set = set(pelt_changepoints) if pelt_changepoints else set()

    for i, ts in enumerate(idx):
        qs = float(Q_step.iat[i]) if not pd.isna(Q_step.iat[i]) else 5.0
        qr = float(Q_regime.iat[i]) if not pd.isna(Q_regime.iat[i]) else 5.0
        qd = float(Q_drift.iat[i]) if not pd.isna(Q_drift.iat[i]) else 5.0
        qf = float(Q_freeze.iat[i]) if not pd.isna(Q_freeze.iat[i]) else 5.0
        ks = float(ks_stat.iat[i]) if not pd.isna(ks_stat.iat[i]) else 0.0
        w1 = float(w1_norm.iat[i]) if not pd.isna(w1_norm.iat[i]) else 0.0
        rv = float(resid_h.iat[i]) if not pd.isna(resid_h.iat[i]) else 0.0

        # ── 两级 step 判定 ────────────────────────────────────────────────
        # 轻度 suspicion: Q_step_24 ≤ 2.5 → 仅记录标签，不触发 Refractory
        # 高置信 confirmed: step_confirmed[i]=True → 触发 Refractory
        if step_confirmed is not None:
            is_step_confirmed = bool(step_confirmed.iat[i]) if not pd.isna(step_confirmed.iat[i]) else False
        else:
            is_step_confirmed = (qs <= 2.0)  # 兼容旧行为
        is_step_suspicion = (qs <= 2.5)
        step_suspicion_arr[i] = np.int8(is_step_suspicion)

        # ── Detect new independent event (event_id) ──────────────────────
        new_event_id = None; new_event_type = None
        # Step event: 只有 confirmed step 才触发 Refractory
        if is_step_confirmed:
            eid = detect_event_id(ts, ks, w1, ss, last_event_ts,
                                    ss.last_event_magnitude, ss.last_event_sign,
                                    "step", cfg)
            if eid is not None and eid != ss.event_id:
                new_event_id = eid; new_event_type = "step"
        # Regime event (only check if no step new event)
        if new_event_id is None and qr <= 2.0:
            eid = detect_event_id(ts, ks, w1, ss, last_event_ts,
                                    ss.last_event_magnitude, ss.last_event_sign,
                                    "regime", cfg)
            if eid is not None and eid != ss.event_id:
                new_event_id = eid; new_event_type = "regime"

        prev_state = ss.state_name

        # ── State transitions ────────────────────────────────────────────
        if new_event_id is not None:
            # → Refractory (only triggered by NEW independent event)
            ref_h = cfg.step_refractory_h if new_event_type == "step" else cfg.regime_refractory_h
            ss.state_name = "Refractory"
            ss.event_id = new_event_id
            ss.refractory_start = ts
            ss.refractory_end = ts + pd.Timedelta(hours=ref_h)
            ss.sustained_flag = False
            ss.recovery_streak = 0
            ss.last_event_magnitude = abs(ks if new_event_type == "step" else w1)
            ss.last_event_sign = int(np.sign(ks if new_event_type == "step" else w1))
            last_event_ts = ts
            ss.drift_mask_reason = f"refractory_{new_event_type}_event"
            transitions.append({
                "sensor_id": sensor_id, "ts": ts,
                "from_state": prev_state, "to_state": "Refractory",
                "event_id": new_event_id, "event_type": new_event_type,
                "trigger": "new_independent_event",
            })
        elif ss.state_name == "Refractory":
            # Refractory continuing or ending?
            if ts >= ss.refractory_end:
                # Check if anomaly persists
                anomaly_persists = (qs <= 2.5 or qr <= 2.5 or qf <= 2.5)
                if anomaly_persists:
                    # → SustainedAnomaly: rebuild local baseline
                    ss.state_name = "SustainedAnomaly"
                    ss.sustained_flag = True
                    ss.sustained_start = ts
                    # Find stable candidate window
                    search_after = (cfg.candidate_search_after_step
                                     if "step" in (ss.event_id or "")
                                     else cfg.candidate_search_after_regime)
                    search_start = ss.refractory_end
                    search_end = ss.refractory_end + pd.Timedelta(hours=search_after[1])
                    # Use local_baseline.find_stable_window (no duplicate local copy)
                    cand = find_stable_window(
                        resid_h, search_start, search_end,
                        stable_h=cfg.stable_window_h,
                        max_slope=cfg.drift_slope_threshold)
                    if cand is not None:
                        ws_t, we_t = cand["start"], cand["end"]
                        c, sc = cand["center"], cand["scale"]
                        ss.local_baseline_center = c
                        ss.local_baseline_scale = sc
                        ss.local_baseline_init_at = we_t
                        ss.local_baseline_version += 1
                        ss.drift_mask_reason = "sustained_local_baseline_active"
                        transitions.append({
                            "sensor_id": sensor_id, "ts": ts,
                            "from_state": "Refractory", "to_state": "SustainedAnomaly",
                            "event_id": ss.event_id, "trigger": "anomaly_persists",
                            "baseline_center": c, "baseline_scale": sc,
                            "baseline_init_window": (ws_t, we_t),
                        })
                    else:
                        # No stable window yet — stay in extended Refractory
                        ss.refractory_end = ts + pd.Timedelta(hours=12)
                        ss.drift_mask_reason = "refractory_extended_no_stable_candidate"
                else:
                    # → Normal directly
                    ss.state_name = "Normal"
                    ss.sustained_flag = False
                    ss.refractory_start = ss.refractory_end = None
                    ss.drift_mask_reason = ""
                    transitions.append({
                        "sensor_id": sensor_id, "ts": ts,
                        "from_state": "Refractory", "to_state": "Normal",
                        "trigger": "refractory_done_no_persist",
                    })
            # else: still in refractory
        elif ss.state_name in ("SustainedAnomaly", "RecoveryCandidate"):
            # Check recovery conditions (双阈值滞回)
            recov_now = (qs >= cfg.enter_recov_q_step and
                          qr >= cfg.enter_recov_q_regime and
                          qf >= cfg.enter_recov_q_freeze)
            # Optional residual / W1 checks
            if ss.local_baseline_center is not None and ss.local_baseline_scale is not None:
                z = abs(rv - ss.local_baseline_center) / max(ss.local_baseline_scale, 1e-3)
                recov_now = recov_now and (z < cfg.residual_z_max)
            recov_now = recov_now and (w1 < cfg.w1_norm_max)
            # Re-trigger: if Q_step or Q_regime go below 2.0 again WITH new event_id
            # (that's handled by the new_event_id check at top)
            if recov_now:
                if ss.state_name == "SustainedAnomaly":
                    ss.state_name = "RecoveryCandidate"
                    ss.recovery_streak = 1
                    ss.last_recovery_check = ts
                    transitions.append({
                        "sensor_id": sensor_id, "ts": ts,
                        "from_state": "SustainedAnomaly", "to_state": "RecoveryCandidate",
                        "trigger": "recovery_thresholds_met",
                    })
                else:  # RecoveryCandidate
                    ss.recovery_streak += 1
                    if ss.recovery_streak >= cfg.min_recovery_streak_h:
                        # → Recovered
                        ss.state_name = "Recovered"
                        ss.sustained_flag = False
                        ss.drift_mask_reason = ""
                        transitions.append({
                            "sensor_id": sensor_id, "ts": ts,
                            "from_state": "RecoveryCandidate", "to_state": "Recovered",
                            "trigger": "min_streak_reached",
                            "recovery_streak_h": ss.recovery_streak,
                        })
            else:
                # Reset streak if conditions break
                if ss.state_name == "RecoveryCandidate":
                    ss.state_name = "SustainedAnomaly"
                    transitions.append({
                        "sensor_id": sensor_id, "ts": ts,
                        "from_state": "RecoveryCandidate", "to_state": "SustainedAnomaly",
                        "trigger": "recovery_streak_broken",
                    })
                ss.recovery_streak = 0
        elif ss.state_name == "Recovered":
            # → Normal at next step
            ss.state_name = "Normal"
            ss.sustained_flag = False
            transitions.append({
                "sensor_id": sensor_id, "ts": ts,
                "from_state": "Recovered", "to_state": "Normal",
                "trigger": "recovery_complete",
            })

        # ── Compute Q_drift_eff(t) ───────────────────────────────────────
        if ss.state_name == "Refractory":
            Q_drift_eff.iat[i] = cfg.drift_neutral_score
            alpha_arr[i] = 1.0
        elif ss.state_name == "SustainedAnomaly":
            # α(t) thaw schedule
            if ss.local_baseline_init_at is not None:
                hours_since = (ts - ss.local_baseline_init_at).total_seconds() / 3600
            else:
                hours_since = 0
            alpha = alpha_schedule(hours_since, cfg.thaw_duration_h, "linear")
            alpha_arr[i] = alpha
            if ss.local_baseline_center is not None:
                local_z = abs(rv - ss.local_baseline_center) / max(ss.local_baseline_scale, 1e-3)
                # Dirty-data gate: only update EWMA on clean readings to avoid
                # spike-induced drift of the new steady-state baseline
                if local_z <= 2.5 and qf >= 4.0 and qs >= 3.0:
                    ss.local_baseline_center, ss.local_baseline_scale = robust_ewma_update(
                        ss.local_baseline_center, ss.local_baseline_scale, rv, rate=0.05
                    )
                qd_new = compute_q_drift_new(rv, ss.local_baseline_center,
                                              ss.local_baseline_scale)
            else:
                qd_new = qd
            Q_drift_eff.iat[i] = alpha * cfg.drift_neutral_score + (1 - alpha) * qd_new
        elif ss.state_name == "RecoveryCandidate":
            # Continue α-thaw with reduced α; keep EWMA tracking with same gate
            if ss.local_baseline_init_at is not None:
                hours_since = (ts - ss.local_baseline_init_at).total_seconds() / 3600
            else:
                hours_since = cfg.thaw_duration_h
            alpha = max(0, alpha_schedule(hours_since, cfg.thaw_duration_h, "linear") - 0.2)
            alpha_arr[i] = alpha
            if ss.local_baseline_center is not None:
                local_z = abs(rv - ss.local_baseline_center) / max(ss.local_baseline_scale, 1e-3)
                if local_z <= 2.5 and qf >= 4.0 and qs >= 3.0:
                    ss.local_baseline_center, ss.local_baseline_scale = robust_ewma_update(
                        ss.local_baseline_center, ss.local_baseline_scale, rv, rate=0.05
                    )
                qd_new = compute_q_drift_new(rv, ss.local_baseline_center,
                                              ss.local_baseline_scale)
            else:
                qd_new = qd
            Q_drift_eff.iat[i] = alpha * cfg.drift_neutral_score + (1 - alpha) * qd_new
        else:  # Normal or Recovered
            Q_drift_eff.iat[i] = qd
            alpha_arr[i] = 0.0
            ss.drift_mask_reason = ""

        # Persist per-hour state
        state_arr[i] = ss.state_name
        event_id_arr[i] = ss.event_id
        baseline_v_arr[i] = ss.local_baseline_version
        sustained_arr[i] = ss.sustained_flag
        recov_streak_arr[i] = ss.recovery_streak
        drift_mask_reason_arr[i] = ss.drift_mask_reason

    state_log = pd.DataFrame({
        "state_name": state_arr,
        "event_id": event_id_arr,
        "local_baseline_version": baseline_v_arr,
        "sustained_flag": sustained_arr,
        "recovery_streak": recov_streak_arr,
        "drift_mask_reason": drift_mask_reason_arr,
        "alpha": alpha_arr,
        "step_suspicion_flag": step_suspicion_arr,  # Q_step ≤ 2.5（仅标记，不触发）
    }, index=idx)

    return Q_drift_eff.clip(1, 5), state_log, transitions
