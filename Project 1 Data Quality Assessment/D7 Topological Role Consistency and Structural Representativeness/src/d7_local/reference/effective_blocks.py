from __future__ import annotations

import pandas as pd


class EffectiveBlockEstimator:
    """Conservative effective support based on non-overlapping calendar-day blocks."""

    def estimate(self, timestamps: pd.DatetimeIndex) -> dict[str, object]:
        index = pd.DatetimeIndex(timestamps).sort_values().unique()
        days = pd.DatetimeIndex(index.normalize().unique())
        months = pd.PeriodIndex(index, freq="M").unique()
        return {
            "n_nominal": int(len(index)),
            "n_nonoverlap_24h": int(len(days)),
            "n_effective": int(len(days)),
            "distinct_days": int(len(days)),
            "distinct_months": int(len(months)),
            "season_coverage": int(len({(month.month - 1) // 3 + 1 for month in months})),
        }
