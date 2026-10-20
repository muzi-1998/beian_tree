"""Archive diagnostics explicitly do not identify the instrument refresh rate."""
from __future__ import annotations

import numpy as np
import pandas as pd


def archive_frequency_diagnostics(values: pd.Series, valid: pd.Series) -> dict:
    adjacent = values.index.to_series().diff().eq(pd.Timedelta(minutes=1)).to_numpy()
    good = valid.to_numpy(dtype=bool)
    pair = adjacent & good & np.r_[False, good[:-1]]
    same = values.eq(values.shift()).to_numpy() & pair
    groups = np.cumsum(~same)
    run_lengths = pd.Series(groups[good]).value_counts().to_numpy()
    return {"diagnostic_split": "development", "archive_rows": len(values),
            "technical_valid_rows": int(good.sum()), "adjacent_valid_pairs": int(pair.sum()),
            "unchanged_adjacent_fraction": float(same.sum() / pair.sum()) if pair.any() else None,
            "constant_run_median_archive_rows": float(np.median(run_lengths)) if len(run_lengths) else None,
            "constant_run_p95_archive_rows": float(np.quantile(run_lengths, .95)) if len(run_lengths) else None,
            "constant_run_max_archive_rows": int(run_lengths.max()) if len(run_lengths) else None,
            "native_interval_minutes": None, "sampling_cycle_minutes": None,
            "analysis_cycle_minutes": None, "write_cycle_minutes": None,
            "latency_minutes": None, "averaging_support_minutes": None,
            "fresh_count": None, "held_count": None, "imputed_count": None,
            "max_hold_age_minutes": None, "native_status": "UNKNOWN",
            "evidence": "user_confirmed_no_verifiable_metadata; aligned_archive_not_sensor_clock",
            "interpretation": "constant_runs_are_archive_patterns_not_proof_of_hold_or_native_frequency"}
