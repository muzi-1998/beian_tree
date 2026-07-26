from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from d7_common.config import D7_ROOT, resolve_paths
from d7_local.context import GlobalProcessContextBuilder, TargetExcludedContextBuilder
from d7_local.contracts import TopologyRegistry
from d7_local.scoring import ApplicabilityGate
from d7_local.templates import SupportPolicy
from d7_local.validation import D7ValidationRunner


def topology() -> TopologyRegistry:
    return TopologyRegistry.load(D7_ROOT / "configs" / "common")


def test_declared_topology_contract() -> None:
    registry = topology()
    assert len(registry.nodes) == 14
    assert len(registry.edges) == 10
    assert len(registry.twin_pairs) == 7
    assert registry.research_topology_confirmed
    assert not registry.topology_verified
    reconciliation = registry.evidence["instrument_inventory"]["reconciliation"]
    assert reconciliation["d7_do_node_count"] == 8
    assert reconciliation["d7_orp_node_count"] == 6


def test_production_verification_requires_independent_documentary_approval(
    tmp_path: Path,
) -> None:
    config_root = tmp_path / "common"
    shutil.copytree(D7_ROOT / "configs" / "common", config_root)
    topology_path = config_root / "topology.yaml"
    evidence_path = config_root / "topology_evidence.yaml"
    topology_config = yaml.safe_load(topology_path.read_text(encoding="utf-8"))
    evidence_config = yaml.safe_load(evidence_path.read_text(encoding="utf-8"))
    topology_config.update(
        {
            "verification_status": "verified",
            "production_approval_status": "approved",
            "source_drawing_id": "CONTROLLED-RECORD-001",
            "reviewer": "reviewer_a",
            "approver": "reviewer_a",
            "maintenance_record_status": "reviewed_or_exception_approved",
        }
    )
    evidence_config["production_governance"]["status"] = "approved"
    topology_path.write_text(
        yaml.safe_dump(topology_config, sort_keys=False), encoding="utf-8"
    )
    evidence_path.write_text(
        yaml.safe_dump(evidence_config, sort_keys=False), encoding="utf-8"
    )
    assert not TopologyRegistry.load(config_root).topology_verified

    topology_config["approver"] = "approver_b"
    topology_path.write_text(
        yaml.safe_dump(topology_config, sort_keys=False), encoding="utf-8"
    )
    assert TopologyRegistry.load(config_root).topology_verified


def test_target_excluded_context_has_no_target() -> None:
    registry = topology()
    index = pd.date_range("2025-08-01", periods=4, freq="10min")
    columns = [*registry.node_ids(), "QR_1", "QR_2", "QIR_1", "QIR_2"]
    snapshots = pd.DataFrame(1.0, index=index, columns=columns)
    for sensor in registry.node_ids():
        features = TargetExcludedContextBuilder(registry).build(snapshots, sensor)
        assert sensor not in features.columns


def test_global_context_is_shared_and_robust_to_one_extreme_sensor() -> None:
    registry = topology()
    index = pd.date_range("2025-08-01", periods=4, freq="10min")
    columns = [*registry.node_ids(), "QR_1", "QR_2", "QIR_1", "QIR_2"]
    snapshots = pd.DataFrame(1.0, index=index, columns=columns)
    baseline = GlobalProcessContextBuilder(registry).build(snapshots)
    snapshots.loc[index[0], "DO_1_1"] = 1000.0
    perturbed = GlobalProcessContextBuilder(registry).build(snapshots)
    assert baseline.columns.tolist() == perturbed.columns.tolist()
    assert perturbed.loc[index[0], "do_pool_median"] == 1.0


def test_research_topology_enables_scientific_score_without_deployment() -> None:
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
    output = ApplicabilityGate(
        research_topology_confirmed=True, deployment_approved=False
    ).apply(frame)
    assert output.loc[0, "evaluation_status"] == "evaluable"
    assert output.loc[0, "D7_total"] == 4.0
    assert output.loc[0, "D7_forDQR"] == 4.0
    assert output.loc[0, "D7_report_provisional"] == 4.0
    assert output.loc[0, "D7_report"] == 4.0
    assert not output.loc[0, "deployment_approved"]


def test_unconfirmed_research_topology_blocks_report() -> None:
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
    output = ApplicabilityGate(
        research_topology_confirmed=False, deployment_approved=False
    ).apply(frame)
    assert output.loc[0, "D7_report_provisional"] == 4.0
    assert np.isnan(output.loc[0, "D7_report"])
    assert not output.loc[0, "report_eligible"]


def test_support_tiers_separate_scientific_score_from_action() -> None:
    frame = pd.DataFrame(
        {
            "Q_profile": [4.0, 4.0, 4.0],
            "Q_gradient": [4.0, 4.0, 4.0],
            "Q_rank": [4.0, 4.0, 4.0],
            "Q_rep": [4.0, 4.0, 4.0],
            "D7_raw": [4.0, 4.0, 4.0],
            "window_coverage": [1.0, 1.0, 1.0],
            "regime_state": ["Locked", "Locked", "Locked"],
            "support_level": ["L1", "L2", "L3"],
        }
    )
    output = ApplicabilityGate(
        research_topology_confirmed=True, deployment_approved=False
    ).apply(frame)
    assert output.loc[0, "evaluation_status"] == "limited_support"
    assert np.isnan(output.loc[0, "D7_report_provisional"])
    assert output.loc[1, "evaluation_status"] == "evaluable"
    assert output.loc[1, "D7_report"] == 4.0
    assert output.loc[1, "D7_total"] == 4.0
    assert not output.loc[1, "veto_eligible"]
    assert output.loc[2, "evaluation_status"] == "evaluable"
    assert output.loc[2, "D7_total"] == 4.0
    assert output.loc[2, "action_eligible_candidate"]
    assert not output.loc[2, "veto_eligible"]


def test_l3_support_is_validation_graded_not_covariance_graded() -> None:
    policy = SupportPolicy(
        {
            "thresholds": {
                "L3": {
                    "min_effective_blocks": 60,
                    "min_distinct_months": 3,
                    "min_bootstrap_stability": 0.85,
                    "min_blocked_holdouts": 3,
                    "max_holdout_far": 0.10,
                },
                "L2": {
                    "min_effective_blocks": 40,
                    "min_distinct_months": 2,
                },
                "L1": {"min_effective_blocks": 20},
            }
        }
    )
    assert (
        policy.resolve(
            71,
            3,
            bootstrap_stability=0.90,
            holdout_count=3,
            holdout_far=0.05,
        )
        == "L3"
    )
    assert (
        policy.resolve(
            71,
            3,
            bootstrap_stability=0.80,
            holdout_count=3,
            holdout_far=0.05,
        )
        == "L2"
    )


def test_wilson_interval_contains_observed_proportion() -> None:
    low, high = D7ValidationRunner._wilson_interval(45, 60)
    assert low < 0.75 < high
    assert 0.0 <= low < high <= 1.0


def test_local_outputs_respect_claim_specific_admission() -> None:
    paths = resolve_paths()
    main = pd.read_parquet(paths.local_output_root / "D7_main_scores_hourly.parquet")
    support = pd.read_parquet(paths.local_output_root / "D7_support_assessment.parquet")
    assert not main.duplicated(["timestamp", "sensor_id"]).any()
    assert main["D7_total"].notna().any()
    assert main["D7_forDQR"].notna().sum() == main["D7_total"].notna().sum()
    assert main["D7_report"].notna().sum() == main["D7_report_provisional"].notna().sum()
    assert main["D7_report"].notna().any()
    assert not main["upstream_score_consumed"].any()
    orp = support[support["analyte"] == "ORP"]
    assert orp["support_level"].isin(["L1", "L2", "L3"]).all()
    assert orp["support_level"].isin(["L2", "L3"]).any()
    assert (orp["profile_covariance_mode"] == "diagonal_robust_z").all()
    assert np.isclose(orp["alpha_used"], 1.0).all()


def test_sensitivity_source_does_not_import_local() -> None:
    source = (D7_ROOT / "src" / "d7_sensitivity" / "pipeline.py").read_text(encoding="utf-8")
    assert "from d7_local" not in source
    assert "import d7_local" not in source
