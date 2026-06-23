"""d1_aggregator.py — D1 v1.1 final aggregation.

Compliant with:
    - D1 主方案 v2 §2 (D1_base = weighted, D1_pre = λ-blend, veto rules)
    - Veto-3 修订 — signal-only mode (no QR/QIR process gate)
    - QR_QIR 修订 — only DO/ORP scored
    - Cooldown 修订 — uses state_machine output Q_drift_eff

Aggregation flow:
    1. D1_base = 0.15·Q_spike + 0.20·Q_step + 0.25·Q_drift_eff
                + 0.20·Q_freeze + 0.20·Q_regime
    2. D1_pre  = 0.70·D1_base + 0.30·min(Q_*)
    3. Veto rules:
       - Q_freeze ≤ 2.0 → D1 ≤ 2.0
       - Q_regime ≤ 2.0 → D1 ≤ 2.5
       - Veto-3 (signal-only): Q_step ≤ 2.0 ∧ duration > 24h ∧
                                state_name ∉ {Refractory} → D1 ≤ 2.5
       - SustainedAnomaly cap: state_name == SustainedAnomaly → D1 ≤ 2.5
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from typing import Tuple, Dict


_DEFAULT_WEIGHTS = {"spike": 0.15, "step": 0.20, "drift": 0.25, "freeze": 0.20, "regime": 0.20}
_DEFAULT_LAMBDA  = 0.70


def compute_veto3_eligibility(Q_step: pd.Series, state_log: pd.DataFrame,
                                step_threshold: float = 2.0,
                                duration_h: int = 36,
                                min_event_count: int = 6,
                                excluded_states=("Refractory",)) -> pd.Series:
    """Compute signal-only Veto-3 eligibility per hour.

    Rule (Veto-3 修订 §五 36h版):
        Veto3_eligible(t) = (Q_step_final ≤ 2.0)
                          ∧ (sustained for ≥ duration_h consecutive hours)
                          ∧ (step_event_count in window ≥ min_event_count)
                          ∧ (state_name ∉ {Refractory})
    """
    step_low = (Q_step <= step_threshold).astype(int)
    # 连续持续条件: rolling window 内全部小时均 ≤ threshold
    sustained = step_low.rolling(duration_h, min_periods=duration_h).sum() >= duration_h
    # 事件密度条件: rolling window 内至少 min_event_count 个小时触发（防止孤立低分点）
    event_density = step_low.rolling(duration_h, min_periods=1).sum() >= min_event_count
    excluded_mask = state_log["state_name"].isin(excluded_states)
    eligible = sustained & event_density & ~excluded_mask & step_low.astype(bool)
    return eligible.fillna(False)


def aggregate_d1_v11(Q_spike: pd.Series, Q_step: pd.Series, Q_drift_eff: pd.Series,
                     Q_freeze: pd.Series, Q_regime: pd.Series,
                     state_log: pd.DataFrame,
                     weights: Dict = None,
                     lambda_blend: float = None,
                     freeze_thr: float = 2.0, freeze_cap: float = 2.0,
                     regime_thr: float = 2.0, regime_cap: float = 2.5,
                     veto3_step_thr: float = 2.0, veto3_duration_h: int = 36,
                     veto3_min_event_count: int = 6,
                     veto3_cap: float = 2.5,
                     sustained_cap: float = 2.5,
                     ) -> Tuple[pd.Series, Dict, pd.DataFrame]:
    """v1.1 aggregation — uses Q_drift_eff (after state-machine α-thaw).

    weights and lambda_blend come from rules.yaml aggregation section;
    fall back to spec defaults when not supplied.

    Returns
    -------
    D1   : pd.Series — final hourly D1
    comp : dict — components (D1_base, D1_pre, min_q)
    vlog : DataFrame — veto log: cooldown_active (Refractory),
            veto_freeze, veto_regime, veto3_signal_only, sustained_cap, veto_active
    """
    if weights is None:
        weights = _DEFAULT_WEIGHTS
    if lambda_blend is None:
        lambda_blend = _DEFAULT_LAMBDA

    # D1_base
    D1_base = (weights["spike"]  * Q_spike +
                weights["step"]   * Q_step +
                weights["drift"]  * Q_drift_eff +
                weights["freeze"] * Q_freeze +
                weights["regime"] * Q_regime)
    # min-penalty (using Q_drift_eff, NOT raw Q_drift)
    M = pd.concat([Q_spike, Q_step, Q_drift_eff, Q_freeze, Q_regime],
                   axis=1).min(axis=1)
    D1_pre = lambda_blend * D1_base + (1 - lambda_blend) * M

    # Veto rules
    veto_freeze = (Q_freeze <= freeze_thr)
    veto_regime = (Q_regime <= regime_thr)
    # Signal-only Veto-3（Q_step 此处为 Q_step_final）
    veto3 = compute_veto3_eligibility(Q_step, state_log,
                                        step_threshold=veto3_step_thr,
                                        duration_h=veto3_duration_h,
                                        min_event_count=veto3_min_event_count,
                                        excluded_states=("Refractory",))
    # Sustained anomaly cap
    sustained_active = state_log["state_name"] == "SustainedAnomaly"

    D1 = D1_pre.copy()
    D1[veto_freeze] = D1[veto_freeze].clip(upper=freeze_cap)
    D1[veto_regime] = D1[veto_regime].clip(upper=regime_cap)
    D1[veto3] = D1[veto3].clip(upper=veto3_cap)
    D1[sustained_active] = D1[sustained_active].clip(upper=sustained_cap)
    D1 = D1.clip(1, 5)

    cooldown_active = state_log["state_name"] == "Refractory"
    veto_active = (veto_freeze | veto_regime | veto3 | sustained_active | cooldown_active)
    vlog = pd.DataFrame({
        "state_name": state_log["state_name"],
        "cooldown_active": cooldown_active.astype(int),
        "sustained_active": sustained_active.astype(int),
        "veto_freeze": veto_freeze.astype(int),
        "veto_regime": veto_regime.astype(int),
        "veto3_signal_only": veto3.astype(int),
        "veto_active": veto_active.astype(int),
    }, index=Q_step.index)

    comp = {"D1_base": D1_base, "D1_pre": D1_pre, "min_q": M}
    return D1, comp, vlog


def to_daily(D1_h: pd.DataFrame, q: float = 0.05) -> pd.DataFrame:
    return D1_h.resample("1D").quantile(q)


def to_weekly(D1_d: pd.DataFrame, op: str = "min") -> pd.DataFrame:
    return D1_d.resample("7D").min() if op == "min" else D1_d.resample("7D").mean()


def attribute_dominant_fault(subs: dict) -> pd.DataFrame:
    rows = []
    for c in subs:
        df = pd.DataFrame({k: subs[c][k] for k in
                            ["Q_spike", "Q_step", "Q_drift", "Q_freeze", "Q_regime"]})
        rows.append(df.idxmin(axis=1).rename(c))
    return pd.concat(rows, axis=1)


def extract_events(D1_h: pd.DataFrame, threshold: float = 3.0,
                    min_duration_h: int = 6) -> pd.DataFrame:
    rows = []
    for c in D1_h.columns:
        s = D1_h[c]
        below = (s < threshold).values
        i = 0; n = len(below)
        while i < n:
            if not below[i]: i += 1; continue
            j = i
            while j < n and below[j]: j += 1
            duration = j - i
            if duration >= min_duration_h:
                seg = s.iloc[i:j]
                rows.append({
                    "sensor_id": c,
                    "start": s.index[i], "end": s.index[j-1],
                    "duration_h": int(duration),
                    "min_d1": float(seg.min()),
                    "mean_d1": float(seg.mean()),
                })
            i = j
    return pd.DataFrame(rows)
