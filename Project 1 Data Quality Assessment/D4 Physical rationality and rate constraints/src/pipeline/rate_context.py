"""D4-local cross-sensor rate context used only as a diagnostic."""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.common.rate_utils import dx_dt_robust


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


def compute_rate_context(
    window_df: pd.DataFrame,
    sensors: list[str],
    sensor_pool_map: dict[str, int],
    rate_cfg: dict,
) -> dict[str, tuple[float, float]]:
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
    context = {}
    for sensor, target in rates.items():
        same_pool = [
            rate
            for other, rate in rates.items()
            if other != sensor
            and other.split("_")[0] == sensor.split("_")[0]
            and sensor_pool_map.get(other) == sensor_pool_map.get(sensor)
        ]
        if same_pool:
            neighbor = _positive_corr(target, _finite_column_mean(same_pool))
        else:
            neighbor = 0.0
        parts = sensor.split("_")
        parallel = 0.0
        if len(parts) == 3:
            other_pool = "2" if parts[1] == "1" else "1"
            peer = f"{parts[0]}_{other_pool}_{parts[2]}"
            if peer in rates:
                parallel = _positive_corr(target, rates[peer])
        context[sensor] = (neighbor, parallel)
    return context
