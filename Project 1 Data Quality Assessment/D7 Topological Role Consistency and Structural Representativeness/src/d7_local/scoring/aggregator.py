from __future__ import annotations

import numpy as np


def aggregate_scores(
    q_profile: np.ndarray,
    q_gradient: np.ndarray,
    q_rank: np.ndarray,
    q_rep: np.ndarray,
    *,
    weights: dict[str, float],
    lambda_blend: float,
) -> tuple[np.ndarray, np.ndarray]:
    matrix = np.column_stack([q_profile, q_gradient, q_rank, q_rep]).astype(float)
    weight = np.array(
        [weights["profile"], weights["gradient"], weights["rank"], weights["rep"]]
    )
    base = np.sum(matrix * weight, axis=1)
    minimum = np.ma.min(np.ma.masked_invalid(matrix[:, [0, 1, 3]]), axis=1).filled(np.nan)
    raw = lambda_blend * base + (1.0 - lambda_blend) * minimum
    invalid = ~np.isfinite(matrix).all(axis=1)
    base[invalid] = np.nan
    raw[invalid] = np.nan
    return np.clip(base, 1.0, 5.0), np.clip(raw, 1.0, 5.0)
