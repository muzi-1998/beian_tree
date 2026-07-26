from __future__ import annotations

from d7_local.contracts.topology_contract import TopologyRegistry


def validate_topology(registry: TopologyRegistry) -> dict[str, object]:
    """Return the immutable release facts for the declared topology."""
    return {
        "node_count": len(registry.nodes),
        "edge_count": len(registry.edges),
        "peer_pair_count": len(registry.twin_pairs),
        "topology_hash": registry.topology_hash,
        "research_topology_confirmed": registry.research_topology_confirmed,
        "production_topology_verified": registry.topology_verified,
        "topology_verified": registry.topology_verified,
        "verification_status": registry.metadata.get("verification_status"),
        "research_evidence_version": registry.metadata.get("research_evidence_version"),
        "production_approval_status": registry.metadata.get("production_approval_status"),
    }
