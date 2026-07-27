from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass(frozen=True)
class SnapshotBundle:
    values: pd.DataFrame
    observed_fraction: pd.DataFrame
    censored_mask: pd.DataFrame


class SnapshotBuilder:
    def __init__(self, minutes: int = 10, minimum_observations: int = 5) -> None:
        self.minutes = int(minutes)
        self.minimum_observations = int(minimum_observations)

    def build(self, observations: pd.DataFrame, floor_sensors: list[str]) -> SnapshotBundle:
        rule = f"{self.minutes}min"
        grouped = observations.resample(rule, label="left", closed="left")
        counts = grouped.count()
        values = grouped.median()
        values = values.where(counts >= self.minimum_observations)
        observed_fraction = counts / self.minutes
        censored = pd.DataFrame(False, index=values.index, columns=values.columns)
        for sensor in floor_sensors:
            if sensor in values:
                censored[sensor] = values[sensor].le(0.10) & values[sensor].notna()
        return SnapshotBundle(values, observed_fraction, censored)
