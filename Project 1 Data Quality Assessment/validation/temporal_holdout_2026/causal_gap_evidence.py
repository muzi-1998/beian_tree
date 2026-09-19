"""As-of gap evidence. Retrospective episode lengths are a different estimand."""
from __future__ import annotations

import numpy as np
import pandas as pd


def causal_gap_evidence(values: pd.Series, long_after_minutes: int = 5) -> pd.DataFrame:
    if not isinstance(values.index, pd.DatetimeIndex) or not values.index.is_unique:
        raise ValueError("Unique minute timestamps are required")
    if len(values) > 1 and not values.index.to_series().diff().iloc[1:].eq(pd.Timedelta(minutes=1)).all():
        raise ValueError("Complete increasing one-minute grid required")
    if long_after_minutes < 1:
        raise ValueError("Gap threshold must be positive")
    missing = values.isna()
    group = missing.ne(missing.shift(fill_value=False)).cumsum()
    elapsed = missing.groupby(group).cumsum().astype(int)
    ended_now = ~missing & missing.shift(fill_value=False)
    completed = elapsed.shift(1).where(ended_now)
    return pd.DataFrame({
        "missing": missing, "gap_elapsed_minutes": elapsed,
        "long_gap_asof": missing & elapsed.gt(long_after_minutes),
        "gap_in_progress": missing,
        "completed_gap_length_known_now": completed,
        "P95_completed_gap_24h_asof": completed.rolling("24h", min_periods=1).quantile(.95).fillna(0),
    }, index=values.index)
