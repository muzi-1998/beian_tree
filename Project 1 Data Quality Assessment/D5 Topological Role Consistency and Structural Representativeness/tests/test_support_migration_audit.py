from __future__ import annotations

import pandas as pd

from d5_common.config import D5_ROOT
from d5_local.publication.support_migration import (
    AuditBoundary,
    D5SupportMigrationAudit,
)


def test_plant_global_regime_deduplicates_sensor_rows() -> None:
    timestamps = pd.date_range("2026-01-01", periods=2, freq="10min")
    regime = pd.DataFrame(
        {
            "timestamp": timestamps.repeat(2),
            "sensor_id": ["A", "B", "A", "B"],
            "active_regime_id": [0, 0, 2, 2],
            "regime_state": ["Locked"] * 4,
            "map_probability": [0.9] * 4,
            "ood_distance": [1.0] * 4,
        }
    )
    plant = D5SupportMigrationAudit._plant_global(regime)
    assert len(plant) == 2
    assert plant["active_regime_id"].tolist() == [0, 2]


def test_l1_blockers_use_only_l2_admission_contract() -> None:
    audit = D5SupportMigrationAudit(D5_ROOT)
    template = pd.DataFrame(
        {
            "support_level": ["L1"],
            "family_n_effective": [29],
            "family_distinct_months": [2],
            "node_n_effective": [29],
            "node_distinct_months": [2],
            "node_reference_coverage": [0.999],
            "family_bootstrap_stability": [0.1],
            "family_holdout_far": [1.0],
        }
    )
    result = audit._l1_to_l2_blockers(template)
    assert result.loc[0, "blocker_set"] == "family_days"
    assert result.loc[0, "primary_blocker"] == "family_days"


def test_family_day_counterfactual_preserves_ood_and_missing_evidence() -> None:
    audit = D5SupportMigrationAudit(D5_ROOT)
    boundary = AuditBoundary(
        reference_fraction=0.70,
        reference_end=pd.Timestamp("2026-01-27 04:30"),
        embargo_hours=168,
        support_audit_post_start=pd.Timestamp("2026-02-03 04:30"),
        controlled_validation_start=pd.Timestamp("2026-01-29 00:00"),
    )
    timestamps = pd.date_range("2026-02-04", periods=3, freq="1h")
    main = pd.DataFrame(
        {
            "timestamp": timestamps,
            "sensor_id": ["DO_1_1"] * 3,
            "active_regime_id": [2] * 3,
            "D5_raw": [4.0, 4.0, None],
            "window_coverage": [1.0, 1.0, 0.5],
            "regime_state": ["Locked", "OODHold", "Locked"],
            "research_topology_confirmed": [True] * 3,
            "report_eligible": [False] * 3,
        }
    )
    templates = pd.DataFrame(
        {
            "sensor_id": ["DO_1_1"],
            "active_regime_id": [2],
            "support_level": ["L1"],
            "family_n_effective": [29],
            "family_distinct_months": [2],
            "node_n_effective": [29],
            "node_distinct_months": [2],
            "node_reference_coverage": [0.999],
        }
    )
    result = audit._counterfactual_coverage(main, templates, boundary).set_index(
        "scenario"
    )
    assert result.loc["Current", "report_coverage"] == 0.0
    assert result.loc["Family days repaired", "report_coverage"] == 1 / 3
    assert result.loc["All L2 support repaired", "report_coverage"] == 1 / 3


def test_current_release_is_reference_horizon_dominated() -> None:
    tables, metadata = D5SupportMigrationAudit(D5_ROOT).run()
    blockers = tables["03_L1_to_L2_blockers"]
    post_shift = tables["01b_pre_post_regime_shift"].set_index("regime_label")
    counterfactual = tables["06_counterfactual_coverage"].set_index("scenario")
    assert metadata["reference_end"] == "2026-01-27T04:30:00"
    assert metadata["support_audit_post_start"] == "2026-02-03T04:30:00"
    assert metadata["controlled_validation_start"] == "2026-01-29T00:00:00"
    assert post_shift.loc["R2", "post_occupancy"] == 1.0
    assert len(blockers) == 14
    assert blockers["blocker_set"].eq("family_days").all()
    assert counterfactual.loc["Family days repaired", "report_coverage"] > 0.90


def test_loss_attribution_separates_support_ood_and_incomplete_evidence() -> None:
    tables, _ = D5SupportMigrationAudit(D5_ROOT).run()
    attribution = tables["05_coverage_loss_attribution"].set_index("loss_class")
    assert int(attribution.loc["limited_support", "loss_sensor_hours"]) == 21_588
    assert int(attribution.loc["out_of_template", "loss_sensor_hours"]) == 1_834
    assert int(attribution.loc["not_evaluable", "loss_sensor_hours"]) == 28
    assert int(attribution["loss_sensor_hours"].sum()) == 23_450
    assert abs(
        float(attribution["coverage_percentage_point_contribution"].sum()) - 100.0
    ) < 1e-10


def test_reference_horizon_table_is_not_presented_as_effective_support() -> None:
    tables, _ = D5SupportMigrationAudit(D5_ROOT).run()
    horizon = tables["07_reference_horizon_sensitivity"]
    assert not horizon["effective_support_recalculated"].any()
    assert horizon["scope"].str.contains("upper_bound", regex=False).all()


def test_support_audit_manifest_binds_code_and_configuration() -> None:
    _, metadata = D5SupportMigrationAudit(D5_ROOT).run()
    sources = set(metadata["source_sha256"])
    assert "src/d5_local/publication/support_migration.py" in sources
    assert "scripts/run_d5_support_migration_audit.py" in sources
    assert "configs/local/templates.yaml" in sources
