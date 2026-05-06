"""src/detectors/freeze_response_loss.py
Response-loss auxiliary for D1_freeze (per spec v2 §3.3 & §8).

Definition: when an upstream driver (QR or QIR flow) experiences a relative
change > rate_thr in window [t0, t0+δ], the target sensor (DO or ORP) should
respond within a sensor-specific response window:
    DO  : 10–30 min
    ORP : 30–90 min

If no response is detected (local variance below benchmark p5 OR response
gain below benchmark p10), record a 'response_loss' event. These events
contribute to Q_freeze.composite (per spec §8 weighting):
    Q_freeze = 0.30·Q_RLE + 0.25·Q_lowVar + 0.15·Q_unique
             + 0.15·Q_responseLoss + 0.15·Q_VSResidual
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from typing import Dict, List, Tuple


# Sensor-type → response window (in minutes)
RESPONSE_WIN = {
    "DO":  (10, 30),
    "ORP": (30, 90),
}


def _sensor_type(name: str) -> str:
    if name.startswith("DO_"):
        return "DO"
    if name.startswith("ORP_"):
        return "ORP"
    return "OTHER"


def _detect_driver_events(driver: pd.Series, rate_thr_pct: float = 0.10
                            ) -> pd.DatetimeIndex:
    """Find timestamps where the driver |Δrel| > rate_thr_pct."""
    baseline = driver.rolling("1h", min_periods=10).mean().abs() + 1e-6
    delta = driver.diff().abs()
    rel = delta / baseline
    triggers = rel > rate_thr_pct
    return driver.index[triggers.fillna(False)]


def _compute_response_metrics(target: pd.Series, t0: pd.Timestamp,
                                win_min: Tuple[int, int]) -> Dict:
    """Local variance and gain in response window starting at t0+win_min[0]
    and ending at t0+win_min[1]."""
    w_start = t0 + pd.Timedelta(minutes=win_min[0])
    w_end   = t0 + pd.Timedelta(minutes=win_min[1])
    seg = target.loc[w_start:w_end].dropna()
    if len(seg) < 5:
        return {"variance": np.nan, "gain": np.nan, "n": len(seg)}
    return {
        "variance": float(seg.var()),
        "gain":     float(seg.max() - seg.min()),
        "n":        len(seg),
    }


def detect_response_loss(target: pd.Series, drivers: pd.DataFrame,
                          benchmark_window: pd.DatetimeIndex = None,
                          rate_thr_pct: float = 0.10) -> pd.Series:
    """Flag minutes where target failed to respond to upstream flow change.

    Parameters
    ----------
    target : DO_*_* or ORP_*_* series at min frequency.
    drivers : DataFrame with QR/QIR series at same frequency.
    benchmark_window : DatetimeIndex of "trusted" hours used to set p5/p10
        thresholds; if None, use the full history.

    Returns
    -------
    rl_event : Boolean Series at the target's time index, True for minutes
        within an unresponsive window.
    """
    stype = _sensor_type(target.name)
    if stype == "OTHER":
        return pd.Series(False, index=target.index)
    win_min = RESPONSE_WIN[stype]

    # Aggregate driver events from all driver columns
    all_triggers = pd.DatetimeIndex([])
    for col in drivers.columns:
        all_triggers = all_triggers.union(_detect_driver_events(drivers[col],
                                                                  rate_thr_pct))
    if len(all_triggers) == 0:
        return pd.Series(False, index=target.index)

    # Benchmark thresholds: p5 of variance, p10 of gain — for "should respond"
    if benchmark_window is None:
        bench = target.dropna()
    else:
        bench = target.reindex(benchmark_window).dropna()
    if len(bench) < 100:
        return pd.Series(False, index=target.index)

    # Compute reference distribution of (variance, gain) over rolling 30-min windows
    bench_var = bench.rolling(30, min_periods=15).var()
    bench_gain = (bench.rolling(30, min_periods=15).max()
                  - bench.rolling(30, min_periods=15).min())
    var_p5 = float(bench_var.quantile(0.05))
    gain_p10 = float(bench_gain.quantile(0.10))

    # Walk through driver triggers
    flag = pd.Series(False, index=target.index)
    for t0 in all_triggers:
        m = _compute_response_metrics(target, t0, win_min)
        if np.isnan(m["variance"]) or np.isnan(m["gain"]):
            continue
        non_responsive = (m["variance"] < var_p5) and (m["gain"] < gain_p10)
        if non_responsive:
            mark_start = t0 + pd.Timedelta(minutes=win_min[0])
            mark_end   = t0 + pd.Timedelta(minutes=win_min[1])
            flag.loc[(flag.index >= mark_start) & (flag.index <= mark_end)] = True
    return flag


def aggregate_response_loss_score(rl_event_min: pd.Series,
                                   eval_window_h: int = 168,
                                   target_excess: float = 0.05) -> pd.Series:
    """Map per-min response-loss events to an hourly Q_freeze.responseLoss [1,5]."""
    hourly_rate = rl_event_min.astype(float).resample("1h").mean()
    week_rate = hourly_rate.rolling(eval_window_h, min_periods=24).mean()
    sub = (5 - 4 * week_rate / target_excess).clip(1, 5)
    return sub
