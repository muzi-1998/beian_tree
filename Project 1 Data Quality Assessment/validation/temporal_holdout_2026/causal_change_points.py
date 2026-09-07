"""Predict-only adjacent-KS candidate scan with strictly as-of de-duplication.

Inputs have hour-start labels. Decisions use an explicit available-at clock.
The scan thresholds and 24 h duplicate rule are inherited, never reselected.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import ks_2samp


def causal_change_timeline(hourly: pd.Series, available_index: pd.DatetimeIndex, *,
                           auxiliary_window_days: int, adjacent_segment_hours: int,
                           candidate_step_hours: int, ks_stat_min: float,
                           pvalue_max: float, min_valid_fraction: float) -> pd.DataFrame:
    index = hourly.index
    if not isinstance(index, pd.DatetimeIndex) or not index.is_unique or not index.is_monotonic_increasing:
        raise ValueError("A unique increasing hourly clock is required")
    if len(index) > 1 and not index.to_series().diff().iloc[1:].eq(pd.Timedelta(hours=1)).all():
        raise ValueError("Missing timestamps must be explicitly aligned as NA")
    segment = int(adjacent_segment_hours)
    if segment < 1 or candidate_step_hours < 1 or auxiliary_window_days < 1:
        raise ValueError("Positive scan intervals required")
    minimum = max(4, int(np.ceil(segment * min_valid_fraction)))
    values = hourly.to_numpy(dtype=float)
    times, strengths, known_at = [], [], []
    for split in range(segment, len(values) - segment + 1, candidate_step_hours):
        a, b = values[split-segment:split], values[split:split+segment]
        a, b = a[np.isfinite(a)], b[np.isfinite(b)]
        if min(len(a), len(b)) < minimum:
            continue
        statistic = ks_2samp(a, b, method="asymp")
        if statistic.statistic >= ks_stat_min and statistic.pvalue <= pvalue_max:
            times.append(index[split])
            strengths.append(float(statistic.statistic))
            known_at.append(index[split+segment-1] + pd.Timedelta(hours=1))
    times = pd.DatetimeIndex(times)
    known_at = pd.DatetimeIndex(known_at)
    strengths = np.asarray(strengths)
    rows = []
    lookback = pd.Timedelta(days=auxiliary_window_days)
    breaks = np.flatnonzero(np.diff(times.asi8) > pd.Timedelta(hours=24).value) + 1
    previous_n, representatives = -1, []
    for now in available_index:
        n = known_at.searchsorted(now, side="right")
        # Recompute representatives only when the observed candidate set changes.
        if n != previous_n:
            representatives, cluster_start = [], 0
            for end in [*breaks[breaks < n], n] if n else []:
                local = strengths[cluster_start:end]
                best = cluster_start + int(np.flatnonzero(np.isclose(local, local.max()))[-1])
                representatives.append(best)
                cluster_start = end
            previous_n = n
        chosen = [j for j in representatives if times[j] >= now-lookback]
        if chosen:
            last = chosen[-1]
            rows.append((times[last], strengths[last], (now-times[last]).total_seconds()/3600,
                         tuple(times[j] for j in chosen), tuple(float(strengths[j]) for j in chosen)))
        else:
            rows.append((pd.NaT, np.nan, np.nan, tuple(), tuple()))
    return pd.DataFrame(rows, index=available_index,
                        columns=["cp_time", "cp_strength", "cp_age_h", "cp_candidates", "cp_candidate_strengths"])
