from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import jsonschema
import pandas as pd

from d7_common.config import load_yaml
from d7_common.hashing import hash_object


@dataclass(frozen=True)
class TopologyRegistry:
    nodes: pd.DataFrame
    edges: pd.DataFrame
    twin_pairs: pd.DataFrame
    metadata: dict[str, Any]
    topology_hash: str
    topology_verified: bool

    @classmethod
    def load(cls, config_root: Path) -> "TopologyRegistry":
        sensors = load_yaml(config_root / "sensors.yaml")
        topology = load_yaml(config_root / "topology.yaml")
        schema = json.loads((config_root / "topology.schema.json").read_text(encoding="utf-8"))
        jsonschema.validate(topology, schema)
        nodes = pd.DataFrame(sensors["nodes"])
        edges = pd.DataFrame(topology["edges"])
        pairs = pd.DataFrame(topology["twin_pairs"])
        cls._validate_frames(nodes, edges, pairs)
        canonical = {"sensors": sensors, "topology": topology}
        topology_hash = hash_object(canonical)
        pending = canonical_as_text(canonical).count("PENDING_FIELD_VERIFICATION") > 0
        verified = topology.get("verification_status") == "verified" and not pending
        metadata = {key: value for key, value in topology.items() if key not in {"edges", "twin_pairs"}}
        return cls(nodes, edges, pairs, metadata, topology_hash, verified)

    @staticmethod
    def _validate_frames(nodes: pd.DataFrame, edges: pd.DataFrame, pairs: pd.DataFrame) -> None:
        if len(nodes) != 14 or nodes["sensor_id"].duplicated().any():
            raise ValueError("D7 topology requires exactly 14 unique DO/ORP nodes")
        node_ids = set(nodes["sensor_id"])
        if set(edges["source"]) - node_ids or set(edges["target"]) - node_ids:
            raise ValueError("Every topology edge endpoint must exist")
        if (edges["source"] == edges["target"]).any() or edges["edge_id"].duplicated().any():
            raise ValueError("Topology edges must be unique and cannot be self-loops")
        if len(pairs) != 7 or pairs["pair_id"].duplicated().any():
            raise ValueError("D7 topology requires seven unique D6 peer pairs")
        if set(pairs["sensor_a"]) | set(pairs["sensor_b"]) != node_ids:
            raise ValueError("Seven peer pairs must cover all D7 nodes exactly once")
        analyte = nodes.set_index("sensor_id")["analyte"]
        for row in pairs.itertuples(index=False):
            if analyte[row.sensor_a] != analyte[row.sensor_b]:
                raise ValueError(f"Peer analytes differ for {row.pair_id}")

    def node_ids(self) -> list[str]:
        return self.nodes["sensor_id"].tolist()


def canonical_as_text(value: object) -> str:
    return json.dumps(value, sort_keys=True, default=str)
