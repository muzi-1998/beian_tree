from __future__ import annotations

import numpy as np


def empirical_quality_score(
    risk: np.ndarray,
    calibration_values: np.ndarray,
    *,
    gamma: float = 1.0,
) -> np.ndarray:
    risk = np.asarray(risk, dtype=float)
    reference = np.sort(np.asarray(calibration_values, dtype=float))
    reference = reference[np.isfinite(reference)]
    if reference.size < 20:
        return np.full(risk.shape, np.nan)
    percentile = np.searchsorted(reference, risk, side="right") / reference.size
    score = 5.0 - 4.0 * np.power(percentile, gamma)
    score[~np.isfinite(risk)] = np.nan
    return np.clip(score, 1.0, 5.0)
