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
    evidence: dict[str, Any]
    topology_hash: str
    research_topology_confirmed: bool
    topology_verified: bool

    @classmethod
    def load(cls, config_root: Path) -> "TopologyRegistry":
        sensors = load_yaml(config_root / "sensors.yaml")
        topology = load_yaml(config_root / "topology.yaml")
        evidence = load_yaml(config_root / "topology_evidence.yaml")
        schema = json.loads((config_root / "topology.schema.json").read_text(encoding="utf-8"))
        jsonschema.validate(topology, schema)
        nodes = pd.DataFrame(sensors["nodes"])
        edges = pd.DataFrame(topology["edges"])
        pairs = pd.DataFrame(topology["twin_pairs"])
        cls._validate_frames(nodes, edges, pairs)
        research_confirmed = cls._validate_research_evidence(nodes, topology, evidence)
        canonical = {"sensors": sensors, "topology": topology, "evidence": evidence}
        topology_hash = hash_object(canonical)
        reviewer = str(topology.get("reviewer", "")).strip()
        approver = str(topology.get("approver", "")).strip()
        source_record = str(topology.get("source_drawing_id", "")).strip()
        maintenance_status = str(topology.get("maintenance_record_status", "")).strip()
        evidence_production_status = str(
            evidence.get("production_governance", {}).get("status", "")
        ).strip()
        pending_approval = "PENDING_PRODUCTION_APPROVAL" in canonical_as_text(canonical)
        verified = bool(
            topology.get("verification_status") == "verified"
            and topology.get("production_approval_status") == "approved"
            and evidence_production_status == "approved"
            and not pending_approval
            and reviewer
            and approver
            and reviewer != approver
            and not reviewer.startswith("PENDING_")
            and not approver.startswith("PENDING_")
            and source_record
            and not source_record.startswith(("PENDING_", "NOT_PROVIDED_"))
            and maintenance_status
            and not maintenance_status.startswith(("pending", "unavailable"))
        )
        metadata = {key: value for key, value in topology.items() if key not in {"edges", "twin_pairs"}}
        return cls(
            nodes,
            edges,
            pairs,
            metadata,
            evidence,
            topology_hash,
            research_confirmed,
            verified,
        )

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

    @staticmethod
    def _validate_research_evidence(
        nodes: pd.DataFrame, topology: dict[str, Any], evidence: dict[str, Any]
    ) -> bool:
        confirmation = evidence.get("research_confirmation", {})
        scope = confirmation.get("scope", {})
        required_scope = {
            "process_line",
            "process_zone",
            "longitudinal_order",
            "scada_to_physical_point_one_to_one",
            "no_probe_or_channel_change_during_study",
        }
        scope_complete = required_scope.issubset(scope) and all(
            bool(scope[key]) for key in required_scope
        )
        inventory = evidence.get("instrument_inventory", {})
        reconciliation = inventory.get("reconciliation", {})
        expected_do = int((nodes["analyte"] == "DO").sum())
        expected_orp = int((nodes["analyte"] == "ORP").sum())
        inventory_reconciled = bool(
            int(reconciliation.get("d7_do_node_count", -1)) == expected_do
            and int(reconciliation.get("d7_orp_node_count", -1)) == expected_orp
            and int(inventory.get("biological_pool", {}).get("DO", {}).get("listed_count", -1))
            == expected_do
            and int(inventory.get("biological_pool", {}).get("ORP", {}).get("listed_count", -1))
            == expected_orp
            and reconciliation.get("status") == "analyte_count_reconciled"
        )
        evidence_version_matches = (
            topology.get("research_evidence_version") == evidence.get("evidence_version")
        )
        confirmed = bool(
            topology.get("research_confirmation_status") == "author_confirmed"
            and confirmation.get("status") == "author_confirmed"
            and scope_complete
            and inventory_reconciled
            and evidence_version_matches
        )
        if topology.get("verification_status") == "research_confirmed_production_pending" and not confirmed:
            raise ValueError("Research-confirmed topology requires complete reconciled evidence")
        return confirmed

    def node_ids(self) -> list[str]:
        return self.nodes["sensor_id"].tolist()


def canonical_as_text(value: object) -> str:
    return json.dumps(value, sort_keys=True, default=str)
