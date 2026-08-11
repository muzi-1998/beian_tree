"""D3-local event-level rate context for process-coherence attribution."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from src.common.rate_utils import dx_dt_robust


@dataclass(frozen=True)
class RateContext:
    neighbor_sync_score: float
    parallel_sync_score: float
    coherent_mask: np.ndarray
    coherent_peer_count: np.ndarray
    rate_series: np.ndarray


def _positive_corr(a: np.ndarray, b: np.ndarray) -> float:
    mask = np.isfinite(a) & np.isfinite(b)
    if mask.sum() < 10:
        return 0.0
    finite_a = a[mask]
    finite_b = b[mask]
    if np.ptp(finite_a) == 0 or np.ptp(finite_b) == 0:
        return 0.0
    corr = np.corrcoef(finite_a, finite_b)[0, 1]
    return float(max(0.0, corr)) if np.isfinite(corr) else 0.0


def _finite_column_mean(arrays: list[np.ndarray]) -> np.ndarray:
    stacked = np.stack(arrays)
    finite = np.isfinite(stacked)
    counts = finite.sum(axis=0)
    totals = np.where(finite, stacked, 0.0).sum(axis=0)
    result = np.full(stacked.shape[1], np.nan, dtype=float)
    np.divide(totals, counts, out=result, where=counts > 0)
    return result


def _shift(values: np.ndarray, lag: int) -> np.ndarray:
    shifted = np.full(len(values), np.nan, dtype=float)
    if lag == 0:
        shifted[:] = values
    elif lag > 0:
        shifted[:-lag] = values[lag:]
    else:
        shifted[-lag:] = values[:lag]
    return shifted


def _same_sign_overlap(
    target: np.ndarray,
    peer: np.ndarray,
    target_limit: float,
    peer_limit: float,
    max_lag: int,
) -> np.ndarray:
    active_target = np.isfinite(target) & (np.abs(target) > target_limit)
    overlap = np.zeros(len(target), dtype=bool)
    for lag in range(-max_lag, max_lag + 1):
        aligned = _shift(peer, lag)
        overlap |= (
            active_target
            & np.isfinite(aligned)
            & (np.abs(aligned) > peer_limit)
            & (np.sign(target) == np.sign(aligned))
        )
    return overlap


def compute_rate_context(
    window_df: pd.DataFrame,
    sensors: list[str],
    sensor_pool_map: dict[str, int],
    rate_cfg: dict,
) -> dict[str, RateContext]:
    estimator = rate_cfg["rate_estimator"]
    rates = {
        sensor: dx_dt_robust(
            window_df[sensor].to_numpy(),
            method=estimator["method"],
            smooth_window=estimator["smooth_window"],
            hampel_window=estimator["hampel_window"],
            hampel_n_sigmas=estimator["hampel_n_sigmas"],
        )[0]
        for sensor in sensors
        if sensor in window_df
    }
    guard_cfg = rate_cfg.get("process_coherence_guard", {})
    guard_enabled = bool(guard_cfg.get("enabled", False))
    max_lag = int(guard_cfg.get("max_lag_min", 0))
    min_same_line = int(guard_cfg.get("minimum_same_line_peer_count", 2))
    exact_parallel_sufficient = bool(
        guard_cfg.get("exact_parallel_peer_sufficient", True)
    )
    context: dict[str, RateContext] = {}
    for sensor, target in rates.items():
        sensor_type = sensor.split("_", 1)[0]
        target_limit = float(rate_cfg["rate_limits"][sensor_type]["rate_soft"])
        same_pool_items = [
            (other, rate)
            for other, rate in rates.items()
            if other != sensor
            and other.split("_")[0] == sensor.split("_")[0]
            and sensor_pool_map.get(other) == sensor_pool_map.get(sensor)
        ]
        if same_pool_items:
            neighbor = _positive_corr(
                target, _finite_column_mean([rate for _, rate in same_pool_items])
            )
        else:
            neighbor = 0.0
        same_line_count = np.zeros(len(target), dtype=int)
        for other, peer_rate in same_pool_items:
            peer_type = other.split("_", 1)[0]
            peer_limit = float(rate_cfg["rate_limits"][peer_type]["rate_soft"])
            same_line_count += _same_sign_overlap(
                target, peer_rate, target_limit, peer_limit, max_lag
            ).astype(int)

        parts = sensor.split("_")
        parallel = 0.0
        parallel_overlap = np.zeros(len(target), dtype=bool)
        if len(parts) == 3:
            other_pool = "2" if parts[1] == "1" else "1"
            peer = f"{parts[0]}_{other_pool}_{parts[2]}"
            if peer in rates:
                parallel = _positive_corr(target, rates[peer])
                peer_limit = float(rate_cfg["rate_limits"][sensor_type]["rate_soft"])
                parallel_overlap = _same_sign_overlap(
                    target, rates[peer], target_limit, peer_limit, max_lag
                )
        coherent = np.zeros(len(target), dtype=bool)
        if guard_enabled:
            coherent = same_line_count >= min_same_line
            if exact_parallel_sufficient:
                coherent |= parallel_overlap
        peer_count = same_line_count + parallel_overlap.astype(int)
        context[sensor] = RateContext(
            neighbor_sync_score=neighbor,
            parallel_sync_score=parallel,
            coherent_mask=coherent,
            coherent_peer_count=peer_count,
            rate_series=target,
        )
    return context
