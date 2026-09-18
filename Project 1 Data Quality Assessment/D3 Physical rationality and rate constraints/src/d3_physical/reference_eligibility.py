"""Neutral reference qualification; no imports or reads of dimension scores."""
from __future__ import annotations

import numpy as np
import pandas as pd


def production_calibration_mask_from_raw(
    observed: pd.Series, temperature: pd.Series, *, imputed: pd.Series,
    time_valid: pd.Series, minimum_raw_minutes_per_hour: int = 30,
) -> pd.Series:
    if observed.index.has_duplicates or not observed.index.is_monotonic_increasing:
        raise ValueError("Reference time base must be unique and ordered")
    present = np.isfinite(observed) & ~imputed.reindex(observed.index).fillna(True)
    support = present.resample("1h").sum().ge(minimum_raw_minutes_per_hour)
    supported = support.reindex(observed.index.floor("h")).to_numpy()
    return (present & time_valid.reindex(observed.index).eq(True)
            & observed.between(0.0, 20.0) & temperature.reindex(observed.index).between(0.0, 40.0)
            & supported).rename("neutral_reference_eligible")
