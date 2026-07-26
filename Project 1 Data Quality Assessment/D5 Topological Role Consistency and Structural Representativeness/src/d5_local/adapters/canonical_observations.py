from __future__ import annotations

import pandas as pd

from d5_common.config import D5Paths
from d5_local.contracts import CanonicalInputContract, TrackIsolationGuard


class CanonicalObservationAdapter:
    def __init__(self, paths: D5Paths, sensor_ids: list[str]) -> None:
        self.paths = paths
        self.sensor_ids = sensor_ids

    def load(self) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
        observations = pd.read_parquet(self.paths.canonical_observations)
        flags = pd.read_parquet(self.paths.canonical_flags)
        TrackIsolationGuard().validate_input_schema(observations.columns)
        contract = CanonicalInputContract(self.sensor_ids).validate(
            observations, flags, self.paths.time_base_contract
        )
        return observations, flags, contract
