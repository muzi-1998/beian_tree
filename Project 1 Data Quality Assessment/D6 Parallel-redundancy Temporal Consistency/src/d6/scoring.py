from __future__ import annotations

from dataclasses import dataclass
import warnings

import numpy as np
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
    cp_shift_target: float
    cp_shift_reference: float
    d_cp: float
    deadband_active: bool
    risk_dist: float
    risk_trend: float
    risk_var: float
    risk_cp: float


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
            nan, nan, nan, False, nan, nan, nan, nan,
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

    half = len(ht) // 2
    scale_t = max(robust_iqr(ht), deadband)
    scale_r = max(robust_iqr(hr), deadband)
    cp_t = abs(float(np.nanmedian(ht[half:]) - np.nanmedian(ht[:half]))) / scale_t
    cp_r = abs(float(np.nanmedian(hr[half:]) - np.nanmedian(hr[:half]))) / scale_r
    d_cp = abs(cp_t - cp_r)

    return WindowMetrics(
        t.size, r.size, t.size / n_total, r.size / n_total,
        d_w1, d_ks, beta_t, beta_r, d_beta, iqr_t, iqr_r, d_var,
        cp_t, cp_r, d_cp, deadband_active,
        float(risk_dist), float(risk_trend), float(risk_var), float(d_cp),
    )


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
