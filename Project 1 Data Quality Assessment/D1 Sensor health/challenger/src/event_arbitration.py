from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.stats import chi2


@dataclass(frozen=True)
class RateEstimate:
    count: int
    exposure_days: float
    rate: float
    ci95_low: float
    ci95_high: float


def extract_events(
    score: pd.Series,
    *,
    threshold: float,
    eligible: pd.Series,
    merge_gap: pd.Timedelta,
) -> pd.DataFrame:
    active = score.ge(threshold) & eligible.reindex(score.index).fillna(False)
    timestamps = score.index[active]
    rows: list[dict] = []
    if not len(timestamps):
        return pd.DataFrame(columns=["onset", "end", "detection_time", "max_score"])
    start = timestamps[0]
    previous = timestamps[0]
    members = [timestamps[0]]
    for timestamp in timestamps[1:]:
        if timestamp - previous > merge_gap:
            values = score.loc[members]
            rows.append(
                {
                    "onset": start,
                    "end": previous,
                    "detection_time": values.idxmax(),
                    "max_score": float(values.max()),
                }
            )
            start = timestamp
            members = [timestamp]
        else:
            members.append(timestamp)
        previous = timestamp
    values = score.loc[members]
    rows.append(
        {
            "onset": start,
            "end": previous,
            "detection_time": values.idxmax(),
            "max_score": float(values.max()),
        }
    )
    return pd.DataFrame(rows)


def poisson_rate_interval(count: int, exposure_days: float) -> RateEstimate:
    if exposure_days <= 0:
        return RateEstimate(count, exposure_days, np.nan, np.nan, np.nan)
    rate = count / exposure_days
    low = 0.0 if count == 0 else 0.5 * chi2.ppf(0.025, 2 * count) / exposure_days
    high = 0.5 * chi2.ppf(0.975, 2 * (count + 1)) / exposure_days
    return RateEstimate(count, exposure_days, float(rate), float(low), float(high))


def count_events(
    score: pd.Series,
    *,
    threshold: float,
    eligible: pd.Series,
    merge_gap: pd.Timedelta,
) -> int:
    active = score.ge(threshold) & eligible.reindex(score.index).fillna(False)
    timestamps = score.index[active]
    if not len(timestamps):
        return 0
    return int(1 + np.count_nonzero(np.diff(timestamps.asi8) > merge_gap.value))


def calibrate_event_threshold(
    scores: dict[str, pd.Series],
    eligibility: dict[str, pd.Series],
    *,
    merge_gap: pd.Timedelta,
    target_far: float,
    far_ci_high_max: float,
) -> dict[str, float | int]:
    pooled = pd.concat(
        [series.where(eligibility[sensor].reindex(series.index).fillna(False)) for sensor, series in scores.items()]
    ).dropna()
    if pooled.empty:
        raise RuntimeError("No eligible observations for threshold calibration")
    probabilities = np.unique(np.r_[np.linspace(0.97, 0.999, 50), np.linspace(0.9991, 0.99999, 40)])
    candidates = np.unique(pooled.quantile(probabilities).to_numpy(dtype=float))
    exposure_days = sum(float(mask.fillna(False).sum()) for mask in eligibility.values())
    reference_index = next(iter(scores.values())).index
    if len(reference_index) < 2:
        raise RuntimeError("At least two score timestamps are required")
    step_seconds = float(reference_index.to_series().diff().dropna().median().total_seconds())
    exposure_days *= step_seconds / 86400.0
    selected = None
    audit_rows = []
    for threshold in candidates:
        count = sum(
            count_events(
                scores[sensor],
                threshold=float(threshold),
                eligible=eligibility[sensor],
                merge_gap=merge_gap,
            )
            for sensor in scores
        )
        estimate = poisson_rate_interval(count, exposure_days)
        row = {
            "threshold": float(threshold),
            "n_events": int(count),
            "exposure_sensor_days": float(exposure_days),
            "far": estimate.rate,
            "far_ci95_low": estimate.ci95_low,
            "far_ci95_high": estimate.ci95_high,
        }
        audit_rows.append(row)
        if estimate.rate <= target_far and estimate.ci95_high <= far_ci_high_max:
            selected = row
            break
    if selected is None:
        selected = audit_rows[-1]
        selected["threshold_gate_failed"] = True
    else:
        selected["threshold_gate_failed"] = False
    selected["audit"] = audit_rows
    return selected
