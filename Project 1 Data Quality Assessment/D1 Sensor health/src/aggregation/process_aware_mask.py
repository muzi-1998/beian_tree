"""src/aggregation/process_aware_mask.py
Process-aware step masking — distinguish operational pump on/off cycles
from genuine sensor faults.

Problem (v1.0 finding): QR/QIR sensors get high cooldown rate because pump
cycles produce frequent KS-significant step events. These are real process
behaviour, not sensor pathology.

Algorithm:
    For each Q_step ≤ 2.0 trigger on flow channels, look for an opposite-sign
    step within `pair_window_h`. If a paired step is found AND the magnitudes
    match within ±25%, the pair is classified as a pump cycle and Q_step is
    held at neutral (3.0) for the affected hours.

Outputs:
    - Updated Q_step (with flow-channel masking applied)
    - Mask events written to state-blackboard ('process_mask_pump_cycle')
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from typing import Dict, List


FLOW_CHANNELS = ("QR_1", "QR_2", "QIR_1", "QIR_2")


def detect_pump_cycles(df_h: pd.DataFrame, sensor_id: str,
                        rate_thr_pct: float = 0.20,
                        pair_window_h: int = 6,
                        magnitude_tol: float = 0.25) -> List[Dict]:
    """Identify pump on/off cycle pairs in a hourly flow series.

    Parameters
    ----------
    df_h : DataFrame  hourly mean of raw flow values (NOT residuals).
    sensor_id : flow channel name (must be in FLOW_CHANNELS).
    rate_thr_pct : minimum |Δrate|/baseline to qualify as a step trigger.
    pair_window_h : window to look for the opposite-sign matching step.
    magnitude_tol : max relative magnitude difference for two steps to pair.

    Returns
    -------
    cycles : list of {'on_time','off_time','magnitude','direction'} dicts.
    """
    if sensor_id not in df_h.columns:
        return []
    x = df_h[sensor_id].ffill().fillna(0).values
    n = len(x)
    # 24-h rolling baseline for relative-rate comparison
    baseline = pd.Series(x).rolling(24, min_periods=12).mean().abs().fillna(method="bfill").values + 1e-6
    # Step triggers: |Δx| / baseline > threshold
    dx = np.abs(np.diff(x, prepend=x[0]))
    step_trigger = (dx / baseline) > rate_thr_pct

    # Sign of each step
    sign = np.sign(np.diff(x, prepend=x[0]))

    cycles = []
    for i in range(n):
        if not step_trigger[i]:
            continue
        # Look forward up to pair_window_h for opposite-sign step of similar magnitude
        for j in range(i + 1, min(i + pair_window_h + 1, n)):
            if not step_trigger[j]:
                continue
            if sign[j] != -sign[i]:
                continue
            mag_i = abs(np.diff(x, prepend=x[0])[i])
            mag_j = abs(np.diff(x, prepend=x[0])[j])
            rel_diff = abs(mag_i - mag_j) / max(mag_i, mag_j, 1e-6)
            if rel_diff <= magnitude_tol:
                cycles.append({
                    "sensor_id": sensor_id,
                    "on_time":  df_h.index[i] if sign[i] > 0 else df_h.index[j],
                    "off_time": df_h.index[j] if sign[i] > 0 else df_h.index[i],
                    "magnitude": float(mag_i),
                    "duration_h": int(j - i),
                })
                break
    return cycles


def build_process_mask(df_h: pd.DataFrame, time_index: pd.DatetimeIndex,
                        flow_channels: tuple = FLOW_CHANNELS,
                        pad_h: int = 2) -> Dict[str, pd.Series]:
    """Build per-channel boolean mask: True = step is a pump cycle, mask Q_step.

    Returns
    -------
    masks : {channel: Series[Boolean]} aligned to time_index.
    """
    masks = {c: pd.Series(False, index=time_index) for c in flow_channels}
    for c in flow_channels:
        cycles = detect_pump_cycles(df_h, c)
        for cyc in cycles:
            t_start = cyc["on_time"] - pd.Timedelta(hours=pad_h)
            t_end   = cyc["off_time"] + pd.Timedelta(hours=pad_h)
            mask_range = (time_index >= t_start) & (time_index <= t_end)
            masks[c].loc[mask_range] = True
    return masks


def apply_process_mask(Q_step: pd.Series, mask: pd.Series,
                        neutral_score: float = 3.0) -> pd.Series:
    """Replace Q_step with neutral_score where mask is True."""
    out = Q_step.copy()
    out[mask] = neutral_score
    return out


def collect_blackboard_events(masks: Dict[str, pd.Series], df_h: pd.DataFrame
                                ) -> List[Dict]:
    """Convert masks into blackboard flag events for audit/replay."""
    events = []
    for c, m in masks.items():
        # Identify contiguous True spans
        diff = m.astype(int).diff().fillna(0)
        starts = m.index[diff == 1]
        ends   = m.index[diff == -1]
        if m.iloc[0]:
            starts = pd.DatetimeIndex([m.index[0]]).append(starts)
        if m.iloc[-1]:
            ends = ends.append(pd.DatetimeIndex([m.index[-1]]))
        for s, e in zip(starts, ends):
            events.append({
                "sensor_id": c,
                "flag_name": "process_mask_pump_cycle",
                "value": {"reason": "paired step (pump on/off)",
                          "duration_h": int((e - s).total_seconds() / 3600)},
                "start_time": s,
                "expire_at": e,
                "source": "process_aware_mask",
            })
    return events
