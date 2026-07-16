from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


class CanonicalInputContract:
    def __init__(self, required_sensors: list[str]) -> None:
        self.required_sensors = required_sensors

    def validate(
        self,
        observations: pd.DataFrame,
        flags: pd.DataFrame,
        contract_path: Path,
    ) -> dict[str, object]:
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        if contract.get("frequency") != "1min":
            raise ValueError("D7 requires the canonical 1 min time base")
        if observations.index.has_duplicates or not observations.index.is_monotonic_increasing:
            raise ValueError("Canonical observations require a unique monotonic index")
        missing = sorted(set(self.required_sensors) - set(observations.columns))
        if missing:
            raise ValueError(f"Canonical observations are missing D7 sensors: {missing}")
        if not observations.index.equals(flags.index):
            raise ValueError("Observation and flag indices do not align")
        if list(observations.index[[0, -1]].astype(str)) != [
            str(pd.Timestamp(contract["expected_start"])),
            str(pd.Timestamp(contract["expected_end"])),
        ]:
            raise ValueError("Canonical time span does not match the time-base contract")
        return contract
