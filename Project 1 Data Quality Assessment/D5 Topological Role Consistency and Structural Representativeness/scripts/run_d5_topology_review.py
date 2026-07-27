from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd  # noqa: E402

from d5_common.config import D5_ROOT, load_yaml, resolve_paths  # noqa: E402
from d5_local.contracts import TopologyRegistry  # noqa: E402
from d5_local.data import SnapshotBuilder  # noqa: E402
from d5_local.outputs import D5OutputExporter  # noqa: E402
from d5_local.topology import TopologyDriftMonitor  # noqa: E402


if __name__ == "__main__":
    paths = resolve_paths()
    topology = TopologyRegistry.load(D5_ROOT / "configs" / "common")
    windows = load_yaml(D5_ROOT / "configs" / "common" / "windows.yaml")
    observations = pd.read_parquet(paths.canonical_observations)
    columns = [*topology.node_ids(), "QR_1", "QR_2", "QIR_1", "QIR_2"]
    floor = topology.nodes.loc[topology.nodes["floor_flag"], "sensor_id"].tolist()
    snapshots = SnapshotBuilder(
        windows["snapshot_main_minutes"], windows["snapshot_min_observations"]
    ).build(observations[columns], floor).values
    reference_end = snapshots.index[int(len(snapshots) * 0.70)]
    drift = TopologyDriftMonitor(topology).evaluate(snapshots, reference_end)
    D5OutputExporter(paths.local_output_root).write_dual(
        "D5_topology_drift_alerts", drift, "drift_alerts"
    )
    print(
        {
            "rows": len(drift),
            "review_alerts": int(drift["alert_level"].eq("review").sum()),
            "maximum_log_likelihood_ratio": float(drift["log_likelihood_ratio"].max()),
            "production_impact": "none",
        }
    )
