from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from d7_common.config import D7_ROOT, resolve_paths
from d7_local.context import TargetExcludedContextBuilder
from d7_local.contracts import TopologyRegistry
from d7_local.scoring import ApplicabilityGate


def topology() -> TopologyRegistry:
    return TopologyRegistry.load(D7_ROOT / "configs" / "common")


def test_declared_topology_contract() -> None:
    registry = topology()
    assert len(registry.nodes) == 14
    assert len(registry.edges) == 10
    assert len(registry.twin_pairs) == 7
    assert not registry.topology_verified


def test_target_excluded_context_has_no_target() -> None:
    registry = topology()
    index = pd.date_range("2025-08-01", periods=4, freq="10min")
    columns = [*registry.node_ids(), "QR_1", "QR_2", "QIR_1", "QIR_2"]
    snapshots = pd.DataFrame(1.0, index=index, columns=columns)
    for sensor in registry.node_ids():
        features = TargetExcludedContextBuilder(registry).build(snapshots, sensor)
        assert sensor not in features.columns


def test_unverified_topology_blocks_total() -> None:
    frame = pd.DataFrame(
        {
            "Q_profile": [4.0],
            "Q_gradient": [4.0],
            "Q_rank": [4.0],
            "Q_rep": [4.0],
            "D7_raw": [4.0],
            "window_coverage": [1.0],
            "regime_state": ["Locked"],
            "support_level": ["L3"],
        }
    )
    output = ApplicabilityGate(topology_verified=False).apply(frame)
    assert output.loc[0, "evaluation_status"] == "report_only"
    assert np.isnan(output.loc[0, "D7_total"])
    assert np.isnan(output.loc[0, "D7_forDQR"])


def test_local_outputs_respect_gating_and_orp_policy() -> None:
    paths = resolve_paths()
    main = pd.read_parquet(paths.local_output_root / "D7_main_scores_hourly.parquet")
    support = pd.read_parquet(paths.local_output_root / "D7_support_assessment.parquet")
    assert not main.duplicated(["timestamp", "sensor_id"]).any()
    assert main["D7_total"].isna().all()
    assert main["D7_forDQR"].isna().all()
    assert not main["upstream_score_consumed"].any()
    orp = support[support["analyte"] == "ORP"]
    assert (orp["support_level"] == "L1").all()
    assert (orp["profile_covariance_mode"] == "diagonal_robust_z").all()
    assert np.isclose(orp["alpha_used"], 1.0).all()


def test_sensitivity_source_does_not_import_local() -> None:
    source = (D7_ROOT / "src" / "d7_sensitivity" / "pipeline.py").read_text(encoding="utf-8")
    assert "from d7_local" not in source
    assert "import d7_local" not in source
