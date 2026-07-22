"""Availability evidence routing for standard and process-floor sensors."""
from __future__ import annotations

from typing import Optional

import pandas as pd


def route_availability_evidence(
    *,
    aligned_value: pd.Series,
    missing: pd.Series,
    long_gap: pd.Series,
    rle_run_min: pd.Series,
    rolling_iqr: pd.Series,
    low_iqr_threshold: float,
    lenient_rle_min: int,
    hard_rle_min: int,
    hard_rle_run_min: Optional[pd.Series] = None,
    availability_mode: str = "standard",
    process_floor_threshold: Optional[float] = None,
) -> pd.DataFrame:
    """Separate process-floor diagnostics from production unavailability.

    Standard channels retain the established lenient RLE/low-IQR evidence.
    Process-floor channels use only missingness, long gaps and hard RLE for
    production QFA; low IQR remains diagnostic and cannot trigger a freeze veto.
    """
    missing = missing.astype(bool)
    long_gap = long_gap.astype(bool)
    low_iqr = rolling_iqr.lt(float(low_iqr_threshold))
    hard_run = hard_rle_run_min if hard_rle_run_min is not None else rle_run_min
    sensor_freeze = hard_run.ge(int(hard_rle_min)) & ~missing & ~long_gap
    lenient_freeze = rle_run_min.ge(int(lenient_rle_min)) & ~long_gap

    if availability_mode == "process_floor":
        if process_floor_threshold is None:
            raise ValueError("process_floor_threshold is required for process_floor mode")
        floor_occupancy = aligned_value.notna() & aligned_value.le(float(process_floor_threshold))
        resolution_limited = floor_occupancy & low_iqr & ~missing
        qfa_unavailable = missing | long_gap | sensor_freeze
    elif availability_mode == "standard":
        floor_occupancy = pd.Series(False, index=aligned_value.index, dtype=bool)
        resolution_limited = pd.Series(False, index=aligned_value.index, dtype=bool)
        qfa_unavailable = (lenient_freeze | low_iqr) & ~long_gap
    else:
        raise ValueError(f"Unsupported availability_mode: {availability_mode}")

    return pd.DataFrame(
        {
            "low_iqr_diagnostic": low_iqr,
            "floor_occupancy": floor_occupancy,
            "resolution_limited": resolution_limited,
            "sensor_freeze": sensor_freeze,
            "qfa_unavailable": qfa_unavailable,
        },
        index=aligned_value.index,
    ).astype(bool)
