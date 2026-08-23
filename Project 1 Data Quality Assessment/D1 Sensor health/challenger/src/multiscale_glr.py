from __future__ import annotations

import numpy as np
import pandas as pd


def multiscale_glr(
    innovation: pd.Series,
    scales: list[int] | tuple[int, ...],
) -> pd.DataFrame:
    """Two-sided Gaussian mean-shift GLR represented as |sum(u)| / sqrt(d)."""
    scores: dict[int, pd.Series] = {}
    signed: dict[int, pd.Series] = {}
    for scale in sorted(set(int(value) for value in scales)):
        window_sum = innovation.rolling(scale, min_periods=scale).sum()
        standardized = window_sum / np.sqrt(float(scale))
        signed[scale] = standardized
        scores[scale] = standardized.abs()
    score_frame = pd.DataFrame(scores, index=innovation.index)
    valid = score_frame.notna().any(axis=1)
    maximum = pd.Series(np.nan, index=innovation.index, dtype=float)
    maximum.loc[valid] = score_frame.loc[valid].max(axis=1)
    selected_scale = pd.Series(pd.NA, index=innovation.index, dtype="Int64")
    selected_scale.loc[valid] = score_frame.loc[valid].idxmax(axis=1).astype(int)
    selected_signed = pd.Series(np.nan, index=innovation.index, dtype=float)
    for scale, values in signed.items():
        mask = selected_scale.eq(scale)
        selected_signed.loc[mask] = values.loc[mask]
    direction = np.sign(selected_signed).fillna(0).astype(int)
    amplitude = selected_signed.abs() / np.sqrt(selected_scale.astype(float))
    return pd.DataFrame(
        {
            "glr_score": maximum,
            "selected_scale": selected_scale,
            "direction": direction,
            "estimated_amplitude_sigma": amplitude,
        },
        index=innovation.index,
    )
