from __future__ import annotations

from dataclasses import dataclass
import warnings

import numpy as np
import pandas as pd
from scipy.stats import ks_2samp, theilslopes, wasserstein_distance


RISK_COLUMNS = ("risk_dist", "risk_trend", "risk_var", "risk_cp")


def robust_iqr(values: np.ndarray) -> float:
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if values.size < 4:
        return np.nan
    return float(np.quantile(values, 0.75) - np.quantile(values, 0.25))


def _hourly_medians(values: np.ndarray, points_per_hour: int) -> np.ndarray:
    n = len(values) // points_per_hour
    if n == 0:
        return np.asarray([], dtype=float)
    arr = values[-n * points_per_hour :].reshape(n, points_per_hour)
    with np.errstate(all="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", category=RuntimeWarning)
        return np.nanmedian(arr, axis=1)


def _theil_slope(values: np.ndarray) -> float:
    mask = np.isfinite(values)
    if mask.sum() < 8:
        return np.nan
    x = np.arange(len(values), dtype=float)[mask]
    return float(theilslopes(values[mask], x)[0])


@dataclass(frozen=True)
class WindowMetrics:
    n_target: int
    n_reference: int
    valid_fraction_target: float
    valid_fraction_reference: float
    d_w1: float
    d_ks: float
    beta_target: float
    beta_reference: float
    d_beta: float
    iqr_target: float
    iqr_reference: float
    d_var: float
    cp_strength_target: float
    cp_strength_reference: float
    d_cp: float
    cp_one_sided: bool
    deadband_active: bool
    risk_dist: float
    risk_trend: float
    risk_var: float
    risk_cp: float
    q_cp_rule: float


def compute_window_metrics(
    target: np.ndarray,
    reference: np.ndarray,
    *,
    deadband: float,
    points_per_hour: int,
) -> WindowMetrics:
    target = np.asarray(target, dtype=float)
    reference = np.asarray(reference, dtype=float)
    finite_target = np.isfinite(target)
    finite_reference = np.isfinite(reference)
    n_total = max(len(target), 1)
    t = target[finite_target]
    r = reference[finite_reference]
    iqr_t = robust_iqr(t)
    iqr_r = robust_iqr(r)
    if min(t.size, r.size) < 20:
        nan = float("nan")
        return WindowMetrics(
            t.size, r.size, t.size / n_total, r.size / n_total,
            nan, nan, nan, nan, nan, iqr_t, iqr_r, nan,
            nan, nan, nan, False, False, nan, nan, nan, nan, nan,
        )

    pooled_scale = max(np.nanmean([iqr_t, iqr_r]), deadband)
    d_w1 = float(wasserstein_distance(t, r))
    d_ks = float(ks_2samp(t, r, method="asymp").statistic)
    risk_dist = 0.60 * (d_w1 / pooled_scale) + 0.40 * d_ks

    ht = _hourly_medians(target, points_per_hour)
    hr = _hourly_medians(reference, points_per_hour)
    beta_t = _theil_slope(ht)
    beta_r = _theil_slope(hr)
    d_beta = abs(beta_t - beta_r)
    slope_scale = max(pooled_scale / max(len(ht), 1), deadband / 24.0)
    risk_trend = d_beta / slope_scale

    deadband_active = max(iqr_t, iqr_r) < deadband
    d_var = abs(np.log((iqr_t + deadband) / (iqr_r + deadband)))
    risk_var = 0.0 if deadband_active else d_var

    return WindowMetrics(
        t.size, r.size, t.size / n_total, r.size / n_total,
        d_w1, d_ks, beta_t, beta_r, d_beta, iqr_t, iqr_r, d_var,
        np.nan, np.nan, 0.0, False, deadband_active,
        float(risk_dist), float(risk_trend), float(risk_var), 0.0, 5.0,
    )


def adjacent_ks_change_timeline(
    hourly: pd.Series,
    output_index: pd.DatetimeIndex,
    *,
    auxiliary_window_days: int,
    adjacent_segment_hours: int,
    candidate_step_hours: int,
    ks_stat_min: float,
    pvalue_max: float,
    min_valid_fraction: float,
) -> pd.DataFrame:
    """Return the latest de-duplicated adjacent-KS change in each trailing window."""
    series = hourly.astype(float).sort_index()
    values = series.to_numpy(dtype=float)
    index = pd.DatetimeIndex(series.index)
    candidate_times: list[pd.Timestamp] = []
    candidate_strengths: list[float] = []
    segment = int(adjacent_segment_hours)
    minimum = max(4, int(np.ceil(segment * min_valid_fraction)))
    for split in range(segment, len(values) - segment + 1, int(candidate_step_hours)):
        left = values[split - segment:split]
        right = values[split:split + segment]
        left = left[np.isfinite(left)]
        right = right[np.isfinite(right)]
        if min(len(left), len(right)) < minimum:
            continue
        test = ks_2samp(left, right, method="asymp")
        if float(test.statistic) >= ks_stat_min and float(test.pvalue) <= pvalue_max:
            candidate_times.append(pd.Timestamp(index[split]))
            candidate_strengths.append(float(test.statistic))

    result_columns = [
        "cp_time", "cp_strength", "cp_age_h", "cp_candidates", "cp_candidate_strengths"
    ]
    result = pd.DataFrame(index=output_index, columns=result_columns)
    if not candidate_times:
        result["cp_strength"] = np.nan
        result["cp_age_h"] = np.nan
        result["cp_candidates"] = [tuple() for _ in range(len(result))]
        result["cp_candidate_strengths"] = [tuple() for _ in range(len(result))]
        return result

    # Adjacent scans around one physical transition form a short cluster. Collapse
    # each <=24 h cluster to its strongest candidate before comparing pair timing.
    clustered_times: list[pd.Timestamp] = []
    clustered_strengths: list[float] = []
    cluster_start = 0
    for position in range(1, len(candidate_times) + 1):
        cluster_end = (
            position == len(candidate_times)
            or candidate_times[position] - candidate_times[position - 1] > pd.Timedelta(hours=24)
        )
        if not cluster_end:
            continue
        local = np.asarray(candidate_strengths[cluster_start:position], dtype=float)
        maximum = float(np.nanmax(local))
        local_positions = np.flatnonzero(np.isclose(local, maximum))
        chosen = cluster_start + int(local_positions[-1])
        clustered_times.append(candidate_times[chosen])
        clustered_strengths.append(candidate_strengths[chosen])
        cluster_start = position

    times = pd.DatetimeIndex(clustered_times)
    strengths = np.asarray(clustered_strengths, dtype=float)
    lookback = pd.Timedelta(days=int(auxiliary_window_days))
    delay = pd.Timedelta(hours=segment)
    rows: list[tuple[object, ...]] = []
    for end_time in output_index:
        left = times.searchsorted(end_time - lookback, side="left")
        right = times.searchsorted(end_time - delay, side="right")
        if right <= left:
            rows.append((pd.NaT, np.nan, np.nan, tuple(), tuple()))
            continue
        chosen = right - 1
        cp_time = pd.Timestamp(times[chosen])
        age = (end_time - cp_time).total_seconds() / 3600.0
        rows.append((
            cp_time,
            float(strengths[chosen]),
            age,
            tuple(pd.Timestamp(item) for item in times[left:right]),
            tuple(float(item) for item in strengths[left:right]),
        ))
    return pd.DataFrame(rows, index=output_index, columns=result_columns)


def compare_change_points(
    target: pd.DataFrame,
    reference: pd.DataFrame,
) -> pd.DataFrame:
    """Apply the v1.2 fixed change-point timing score table."""
    selected: list[tuple[object, ...]] = []
    for row_no in range(len(target)):
        t_candidates = list(target["cp_candidates"].iloc[row_no])
        r_candidates = list(reference["cp_candidates"].iloc[row_no])
        t_strengths = list(target["cp_candidate_strengths"].iloc[row_no])
        r_strengths = list(reference["cp_candidate_strengths"].iloc[row_no])
        if t_candidates and r_candidates:
            combinations = [
                (abs((t_time - r_time).total_seconds()), -max(t_time.value, r_time.value), ti, ri)
                for ti, t_time in enumerate(t_candidates)
                for ri, r_time in enumerate(r_candidates)
            ]
            _, _, ti, ri = min(combinations)
            selected.append((t_candidates[ti], r_candidates[ri], t_strengths[ti], r_strengths[ri]))
        elif t_candidates:
            selected.append((t_candidates[-1], pd.NaT, t_strengths[-1], np.nan))
        elif r_candidates:
            selected.append((pd.NaT, r_candidates[-1], np.nan, r_strengths[-1]))
        else:
            selected.append((pd.NaT, pd.NaT, np.nan, np.nan))
    selected_frame = pd.DataFrame(
        selected,
        columns=["cp_time_target", "cp_time_reference", "cp_strength_target", "cp_strength_reference"],
        index=target.index,
    )
    t_time = pd.to_datetime(selected_frame["cp_time_target"])
    r_time = pd.to_datetime(selected_frame["cp_time_reference"])
    t_present = t_time.notna()
    r_present = r_time.notna()
    both = t_present & r_present
    one = t_present ^ r_present
    d_cp = (t_time - r_time).abs().dt.total_seconds().div(3600.0)
    end_times = pd.Series(pd.DatetimeIndex(target.index), index=target.index)
    target_age = (end_times - t_time).dt.total_seconds().div(3600.0)
    reference_age = (end_times - r_time).dt.total_seconds().div(3600.0)
    one_age = target_age.where(t_present, reference_age)
    q_cp = np.full(len(target), 5.0)
    q_cp[both & d_cp.ge(3) & d_cp.lt(12)] = 4.0
    q_cp[both & d_cp.ge(12) & d_cp.le(24)] = 3.0
    q_cp[both & d_cp.gt(24)] = 2.0
    q_cp[one & one_age.lt(24)] = 2.0
    q_cp[one & one_age.ge(24)] = 1.0
    return pd.DataFrame({
        "cp_time_target": t_time.to_numpy(),
        "cp_time_reference": r_time.to_numpy(),
        "cp_strength_target": selected_frame["cp_strength_target"].to_numpy(dtype=float),
        "cp_strength_reference": selected_frame["cp_strength_reference"].to_numpy(dtype=float),
        "cp_age_target_h": target_age.to_numpy(dtype=float),
        "cp_age_reference_h": reference_age.to_numpy(dtype=float),
        "d_cp": d_cp.fillna(0.0).to_numpy(dtype=float),
        "cp_one_sided": one.to_numpy(dtype=bool),
        "risk_cp": 5.0 - q_cp,
        "Q_cp": q_cp,
    }, index=target.index)


def apply_d1_fuse(
    d6_raw: np.ndarray,
    d1_target: np.ndarray,
    d1_reference: np.ndarray,
    evaluable: np.ndarray,
    *,
    unreliable_below: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Apply the v1.2 bilateral D1 fuse without using any D7 proxy."""
    raw = np.asarray(d6_raw, dtype=float)
    target = np.asarray(d1_target, dtype=float)
    reference = np.asarray(d1_reference, dtype=float)
    usable = np.asarray(evaluable, dtype=bool)
    available = np.isfinite(target) & np.isfinite(reference)
    target_bad = target < unreliable_below
    reference_bad = reference < unreliable_below
    state = np.select(
        [~available, target_bad & reference_bad, ~target_bad & reference_bad,
         target_bad & ~reference_bad],
        ["d1_missing", "bilateral_unreliable", "reference_unreliable", "target_suspect"],
        default="valid_pair",
    ).astype(object)
    after_d1 = raw.copy()
    after_d1[np.isin(state, ["bilateral_unreliable", "reference_unreliable"])] = 3.0
    after_d1[~usable | ~available] = np.nan
    return after_d1, state


def score_from_quantiles(values: np.ndarray, quantiles: np.ndarray) -> np.ndarray:
    values = np.asarray(values, dtype=float)
    q50, q75, q90, q975 = np.asarray(quantiles, dtype=float)
    scores = np.select(
        [values <= q50, values <= q75, values <= q90, values <= q975],
        [5.0, 4.0, 3.0, 2.0],
        default=1.0,
    )
    scores[~np.isfinite(values)] = np.nan
    return scores


def aggregate_scores(
    q_dist: np.ndarray,
    q_trend: np.ndarray,
    q_var: np.ndarray,
    q_cp: np.ndarray,
    *,
    weights: dict[str, float],
    lambda_blend: float,
) -> tuple[np.ndarray, np.ndarray]:
    matrix = np.column_stack([q_dist, q_trend, q_var, q_cp]).astype(float)
    weight_vector = np.array(
        [weights["dist"], weights["trend"], weights["var"], weights["cp"]],
        dtype=float,
    )
    base = matrix @ weight_vector
    raw = lambda_blend * base + (1.0 - lambda_blend) * np.nanmin(matrix, axis=1)
    invalid = ~np.isfinite(matrix).all(axis=1)
    base[invalid] = np.nan
    raw[invalid] = np.nan
    return base, raw
