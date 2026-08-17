from __future__ import annotations

import numpy as np
import pandas as pd

from d5_local.contracts.topology_contract import TopologyRegistry


class TargetExcludedContextBuilder:
    def __init__(self, topology: TopologyRegistry) -> None:
        self.topology = topology
        self.nodes = topology.nodes.set_index("sensor_id")

    def build(self, snapshots: pd.DataFrame, target: str) -> pd.DataFrame:
        meta = self.nodes.loc[target]
        same_line = self.nodes[
            (self.nodes["line_id"] == meta["line_id"])
            & (self.nodes["analyte"] == meta["analyte"])
        ].index.difference([target])
        other_line = self.nodes[
            (self.nodes["line_id"] != meta["line_id"])
            & (self.nodes["analyte"] == meta["analyte"])
        ].index
        out = snapshots[["QR_1", "QR_2", "QIR_1", "QIR_2"]].copy()
        out["same_line_median"] = snapshots[list(same_line)].median(axis=1)
        out["same_line_dispersion"] = snapshots[list(same_line)].sub(
            out["same_line_median"], axis=0
        ).abs().median(axis=1)
        out["other_line_median"] = snapshots[list(other_line)].median(axis=1)
        out["other_line_dispersion"] = snapshots[list(other_line)].sub(
            out["other_line_median"], axis=0
        ).abs().median(axis=1)
        hour = snapshots.index.hour + snapshots.index.minute / 60.0
        day = snapshots.index.dayofyear
        out["sin_hour"] = np.sin(2 * np.pi * hour / 24.0)
        out["cos_hour"] = np.cos(2 * np.pi * hour / 24.0)
        out["sin_year"] = np.sin(2 * np.pi * day / 365.25)
        out["cos_year"] = np.cos(2 * np.pi * day / 365.25)
        if target in out.columns:
            raise RuntimeError(f"Target leakage detected in context features for {target}")
        return out


class GlobalProcessContextBuilder:
    """Build one robust process context shared by every D5 target."""

    def __init__(self, topology: TopologyRegistry) -> None:
        self.topology = topology
        self.nodes = topology.nodes.set_index("sensor_id")

    def build(self, snapshots: pd.DataFrame) -> pd.DataFrame:
        return self._build(snapshots, excluded_target=None)

    def build_excluding(
        self, snapshots: pd.DataFrame, target: str
    ) -> pd.DataFrame:
        if target not in self.nodes.index:
            raise KeyError(f"Unknown D5 target: {target}")
        return self._build(snapshots, excluded_target=target)

    def _build(
        self, snapshots: pd.DataFrame, excluded_target: str | None
    ) -> pd.DataFrame:
        out = snapshots[["QR_1", "QR_2", "QIR_1", "QIR_2"]].copy()
        for analyte in ["DO", "ORP"]:
            sensors = self.nodes[self.nodes["analyte"].eq(analyte)].index.tolist()
            if excluded_target in sensors:
                sensors.remove(excluded_target)
            values = snapshots[sensors]
            center = values.median(axis=1)
            out[f"{analyte.lower()}_pool_median"] = center
            out[f"{analyte.lower()}_pool_dispersion"] = values.sub(
                center, axis=0
            ).abs().median(axis=1)
        hour = snapshots.index.hour + snapshots.index.minute / 60.0
        day = snapshots.index.dayofyear
        out["sin_hour"] = np.sin(2 * np.pi * hour / 24.0)
        out["cos_hour"] = np.cos(2 * np.pi * hour / 24.0)
        out["sin_year"] = np.sin(2 * np.pi * day / 365.25)
        out["cos_year"] = np.cos(2 * np.pi * day / 365.25)
        return out
