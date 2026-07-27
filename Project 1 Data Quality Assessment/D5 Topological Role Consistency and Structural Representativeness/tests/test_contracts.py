from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from d5_common.config import D5_ROOT, resolve_paths
from d5_local.context import GlobalProcessContextBuilder, TargetExcludedContextBuilder
from d5_local.contracts import TopologyRegistry
from d5_local.scoring import ApplicabilityGate
from d5_local.templates import SupportPolicy
from d5_local.validation import D5ValidationRunner
from d5_local.validation.admission import _merge_consensus_decisions


def topology() -> TopologyRegistry:
    return TopologyRegistry.load(D5_ROOT / "configs" / "common")


def test_declared_topology_contract() -> None:
    registry = topology()
    assert len(registry.nodes) == 14
    assert len(registry.edges) == 10
    assert len(registry.twin_pairs) == 7
    assert registry.research_topology_confirmed
    assert not registry.topology_verified
    reconciliation = registry.evidence["instrument_inventory"]["reconciliation"]
    assert reconciliation["d5_do_node_count"] == 8
    assert reconciliation["d5_orp_node_count"] == 6
    inventory = registry.evidence["instrument_inventory"]
    assert inventory["inspected_range"] == "A1:P34"
    assert "process_line" in inventory[
        "author_confirmed_not_independently_mapped_by_register"
    ]
    governance = registry.evidence["production_governance"]
    assert governance["scientific_score_status"] == (
        "released_for_retrospective_aggregation"
    )
    assert "required_before_d5_total" not in governance
    assert governance["required_before_operational_gate_or_automated_deployment"]


def test_production_verification_requires_independent_documentary_approval(
    tmp_path: Path,
) -> None:
    config_root = tmp_path / "common"
    shutil.copytree(D5_ROOT / "configs" / "common", config_root)
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
            "D5_raw": [4.0],
            "window_coverage": [1.0],
            "regime_state": ["Locked"],
            "support_level": ["L3"],
        }
    )
    output = ApplicabilityGate(
        research_topology_confirmed=True, deployment_approved=False
    ).apply(frame)
    assert output.loc[0, "evaluation_status"] == "evaluable"
    assert output.loc[0, "D5_total"] == 4.0
    assert output.loc[0, "D5_report_score"] == 4.0
    assert output.loc[0, "D5_report_provisional"] == 4.0
    assert output.loc[0, "D5_report"] == 4.0
    assert not output.loc[0, "deployment_approved"]


def test_unconfirmed_research_topology_blocks_report() -> None:
    frame = pd.DataFrame(
        {
            "Q_profile": [4.0],
            "Q_gradient": [4.0],
            "Q_rank": [4.0],
            "Q_rep": [4.0],
            "D5_raw": [4.0],
            "window_coverage": [1.0],
            "regime_state": ["Locked"],
            "support_level": ["L3"],
        }
    )
    output = ApplicabilityGate(
        research_topology_confirmed=False, deployment_approved=False
    ).apply(frame)
    assert output.loc[0, "D5_report_provisional"] == 4.0
    assert np.isnan(output.loc[0, "D5_report"])
    assert not output.loc[0, "report_eligible"]


def test_support_tiers_separate_scientific_score_from_action() -> None:
    frame = pd.DataFrame(
        {
            "Q_profile": [4.0, 4.0, 4.0],
            "Q_gradient": [4.0, 4.0, 4.0],
            "Q_rank": [4.0, 4.0, 4.0],
            "Q_rep": [4.0, 4.0, 4.0],
            "D5_raw": [4.0, 4.0, 4.0],
            "window_coverage": [1.0, 1.0, 1.0],
            "regime_state": ["Locked", "Locked", "Locked"],
            "support_level": ["L1", "L2", "L3"],
        }
    )
    output = ApplicabilityGate(
        research_topology_confirmed=True, deployment_approved=False
    ).apply(frame)
    assert output.loc[0, "evaluation_status"] == "limited_support"
    assert np.isnan(output.loc[0, "D5_report_provisional"])
    assert output.loc[1, "evaluation_status"] == "evaluable"
    assert output.loc[1, "D5_report"] == 4.0
    assert output.loc[1, "D5_total"] == 4.0
    assert not output.loc[1, "veto_eligible"]
    assert output.loc[2, "evaluation_status"] == "evaluable"
    assert output.loc[2, "D5_total"] == 4.0
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
            },
            "node_validation": {
                "L3": {
                    "min_effective_blocks": 30,
                    "min_distinct_months": 3,
                    "min_reference_coverage": 0.80,
                    "min_bootstrap_stability": 0.80,
                    "min_blocked_holdouts": 3,
                    "max_holdout_far": 0.15,
                },
                "L2": {
                    "min_effective_blocks": 20,
                    "min_distinct_months": 2,
                    "min_reference_coverage": 0.60,
                },
                "L1": {"min_effective_blocks": 10},
            },
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
    assert (
        policy.minimum_tier(
            "L3",
            policy.resolve_node(
                25,
                3,
                reference_coverage=0.95,
                bootstrap_stability=0.90,
                holdout_count=3,
                holdout_far=0.05,
            ),
        )
        == "L2"
    )


def test_wilson_interval_contains_observed_proportion() -> None:
    low, high = D5ValidationRunner._wilson_interval(45, 60)
    assert low < 0.75 < high
    assert 0.0 <= low < high <= 1.0


def test_consensus_decision_merge_is_idempotent() -> None:
    timestamp = pd.Timestamp("2025-01-01")
    main = pd.DataFrame(
        {
            "timestamp": [timestamp],
            "pair_id": ["P1"],
            "sensor_id": ["DO_1_1"],
            "sensor_veto_role": ["stale"],
            "decision_type": ["stale"],
        }
    )
    consensus = pd.DataFrame(
        {
            "timestamp": [timestamp],
            "pair_id": ["P1"],
            "target_sensor_id": ["DO_1_1"],
            "reference_sensor_id": ["DO_2_1"],
            "process_coherence_guard_active": [False],
            "attribution_suppressed": [False],
            "sensor_identity_veto_active": [False],
            "sensor_veto_role": ["none"],
            "decision_type": ["not_triggered"],
        }
    )
    once = _merge_consensus_decisions(main, consensus)
    twice = _merge_consensus_decisions(once, consensus)
    pd.testing.assert_frame_equal(once, twice)
    assert once.loc[0, "sensor_veto_role"] == "none"


def test_local_outputs_respect_claim_specific_admission() -> None:
    paths = resolve_paths()
    main = pd.read_parquet(paths.local_output_root / "D5_main_scores_hourly.parquet")
    support = pd.read_parquet(paths.local_output_root / "D5_support_assessment.parquet")
    report = pd.read_parquet(paths.local_output_root / "D5_report_interface.parquet")
    gate = pd.read_parquet(paths.local_output_root / "D5_gate_interface.parquet")
    assert not main.duplicated(["timestamp", "sensor_id"]).any()
    assert main["D5_total"].notna().any()
    assert main["D5_report_score"].equals(main["D5_total"])
    assert "D5_forDQR" not in main
    assert not report.duplicated(["timestamp", "sensor_id"]).any()
    assert not gate.duplicated(["timestamp", "pair_id"]).any()
    assert gate["veto_active"].equals(gate["sensor_identity_veto_active"])
    assert gate["attribution_suppressed"].equals(
        gate["process_coherence_guard_active"]
    )
    assert main["D5_report"].notna().sum() == main["D5_report_provisional"].notna().sum()
    assert main["D5_report"].notna().any()
    assert not main["upstream_score_consumed"].any()
    orp = support[support["analyte"] == "ORP"]
    assert orp["support_level"].isin(["L1", "L2", "L3"]).all()
    assert orp["support_level"].isin(["L2", "L3"]).any()
    assert (orp["profile_covariance_mode"] == "diagonal_robust_z").all()
    assert np.isclose(orp["alpha_used"], 1.0).all()
    l3 = support[support["support_level"].eq("L3")]
    assert l3["family_support_level"].eq("L3").all()
    assert l3["node_validation_passed"].all()


def test_sensitivity_source_does_not_import_local() -> None:
    source = (D5_ROOT / "src" / "d5_sensitivity" / "pipeline.py").read_text(encoding="utf-8")
    assert "from d5_local" not in source
    assert "import d5_local" not in source
