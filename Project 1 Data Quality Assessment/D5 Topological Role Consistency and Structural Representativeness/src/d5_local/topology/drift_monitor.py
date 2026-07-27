from __future__ import annotations

import numpy as np
import pandas as pd

from d5_local.contracts.topology_contract import TopologyRegistry


class TopologyDriftMonitor:
    """Report-only comparison of declared neighbors with finite swap candidates.

    The monitor deliberately has no write path to the topology registry. Its output
    is evidence for manual review, never a learned production topology.
    """

    def __init__(self, topology: TopologyRegistry) -> None:
        self.topology = topology
        self.nodes = topology.nodes.set_index("sensor_id")

    def evaluate(self, snapshots: pd.DataFrame, reference_end: pd.Timestamp) -> pd.DataFrame:
        hourly = snapshots.resample("1h").median()
        reference = hourly.loc[:reference_end]
        rows: list[dict[str, object]] = []
        for target in self.nodes.index:
            declared = self._declared_neighbors(target)
            candidates = self._finite_candidates(target, declared)
            if not declared or not candidates:
                continue
            declared_loss = self._best_loss(reference, target, declared)
            for candidate in candidates:
                candidate_loss = self._pair_loss(reference[target], reference[candidate])
                gain = np.log((declared_loss + 1e-9) / (candidate_loss + 1e-9))
                rows.append(
                    {
                        "target_sensor": target,
                        "design_topology_id": self.topology.metadata["topology_version"],
                        "candidate_mapping": candidate,
                        "declared_neighbors": "|".join(declared),
                        "declared_loss": declared_loss,
                        "candidate_loss": candidate_loss,
                        "log_likelihood_ratio": float(gain),
                        "cross_context_persistence": np.nan,
                        "maintenance_consistency": "unknown_no_maintenance_registry",
                        "alert_level": "review" if gain > 0.35 else "none",
                        "review_status": "unreviewed",
                        "production_impact": "none",
                        "topology_hash": self.topology.topology_hash,
                        "track_id": "d5_local",
                    }
                )
        return pd.DataFrame(rows)

    def _declared_neighbors(self, target: str) -> list[str]:
        neighbors: set[str] = set()
        for edge in self.topology.edges.itertuples(index=False):
            if edge.source == target:
                neighbors.add(edge.target)
            elif edge.target == target:
                neighbors.add(edge.source)
        return sorted(neighbors)

    def _finite_candidates(self, target: str, declared: list[str]) -> list[str]:
        meta = self.nodes.loc[target]
        pool = self.nodes[
            (self.nodes["analyte"] == meta["analyte"])
            & (self.nodes.index != target)
        ].index
        twin = self.topology.twin_pairs
        peer: list[str] = []
        for row in twin.itertuples(index=False):
            if row.sensor_a == target:
                peer.append(row.sensor_b)
            elif row.sensor_b == target:
                peer.append(row.sensor_a)
        same_position = self.nodes[
            (self.nodes["analyte"] == meta["analyte"])
            & (self.nodes["position_id"] == meta["position_id"])
            & (self.nodes.index != target)
        ].index.tolist()
        return sorted((set(peer) | set(same_position) | set(pool)) - set(declared))[:4]

    @staticmethod
    def _pair_loss(left: pd.Series, right: pd.Series) -> float:
        valid = pd.concat([left, right], axis=1).dropna()
        if len(valid) < 24:
            return float("inf")
        target = valid.iloc[:, 0]
        candidate = valid.iloc[:, 1]
        offset = float((target - candidate).median())
        residual = target - (candidate + offset)
        target_scale = max(float((target - target.median()).abs().median()) * 1.4826, 1e-9)
        return float(np.median(np.minimum(np.abs(residual) / target_scale, 4.0)))

    def _best_loss(self, frame: pd.DataFrame, target: str, neighbors: list[str]) -> float:
        return min(self._pair_loss(frame[target], frame[node]) for node in neighbors)
