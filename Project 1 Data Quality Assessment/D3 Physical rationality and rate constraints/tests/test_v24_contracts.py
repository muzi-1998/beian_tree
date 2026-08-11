from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from copy import deepcopy

import numpy as np
import pandas as pd
import pytest
import yaml

from src.common.exceptions import ConfigValidationError
from src.common.rate_utils import RATE_UTILS_VERSION, _theil_sen_slope, dx_dt_robust
from src.d3_physical.aggregator import D3Aggregator
from src.d3_physical.rate_constraint_checker import RateConstraintChecker
from src.d3_physical.scorer import D3ScoreMapper, SubScores, logistic_zero_anchored
from src.d3_physical.threshold_store import PhysicalBound, ThresholdStore
from src.d3_physical.value_range_checker import ValueRangeChecker
from src.validation.interval_scaling import scale_interval


ROOT = Path(__file__).parent.parent


def _yaml(name: str) -> dict:
    return yaml.safe_load((ROOT / "configs" / name).read_text(encoding="utf-8"))


def _thresholds() -> ThresholdStore:
    benchmark = SimpleNamespace(_fixed_tails={}, version="benchmark@v2.2.0")
    return ThresholdStore.build(
        _yaml("d3_physical_bounds.yaml"),
        _yaml("d3_rate_limits.yaml"),
        benchmark,
        version="v2.4.0",
    )


def test_zero_violation_maps_exactly_to_five():
    assert logistic_zero_anchored(0.0, x0=0.05, k=20.0) == pytest.approx(5.0)
    assert logistic_zero_anchored(0.5, x0=0.05, k=20.0) < 1.01


def test_boundary_is_not_part_of_d3_score():
    mapping = _yaml("d3_mapping.yaml")
    assert set(mapping["aggregation"]["weights"]) == {
        "Q_value_hard", "Q_value_soft", "Q_persistent_rate"
    }
    assert sum(mapping["aggregation"]["weights"].values()) == pytest.approx(1.0)
    assert mapping["diagnostics"]["boundary_behavior"]["included_in_score"] is False


def test_instrument_range_does_not_override_hard_tolerance():
    bounds = _yaml("d3_physical_bounds.yaml")["sensors"]
    for config in bounds.values():
        assert config["instrument_veto_range_low"] <= config["hard_low"]
        assert config["instrument_veto_range_high"] >= config["hard_high"]
        assert config["instrument_veto_range_low"] <= config["manufacturer_range_low"]
        assert config["instrument_veto_range_high"] >= config["manufacturer_range_high"]


def test_threshold_register_contains_one_instrument_veto_per_analyte():
    registered = _thresholds().to_dataframe()
    veto = registered.loc[registered["bound_type"] == "instrument_veto"]
    assert len(veto) == 2
    assert veto.set_index("sensor_type").loc["DO", ["low", "high"]].tolist() == [-0.2, 20.0]
    assert veto.set_index("sensor_type").loc["ORP", ["low", "high"]].tolist() == [-1500.0, 1500.0]


def test_orp_operational_excursion_is_not_an_instrument_range_failure():
    config = _yaml("d3_physical_bounds.yaml")
    benchmark = SimpleNamespace(
        _fixed_tails={},
        version="benchmark@v2.2.0",
    )
    thresholds = ThresholdStore.build(
        config,
        _yaml("d3_rate_limits.yaml"),
        benchmark,
        version="v2.4.0",
    )
    bounds = config["sensors"]["ORP"]
    evidence = ValueRangeChecker(
        thresholds,
        bounds["instrument_veto_range_low"],
        bounds["instrument_veto_range_high"],
    ).check(np.array([-600.0]), "ORP_1_3", "ORP")
    assert evidence.hard_violation_count == 1
    assert not evidence.out_of_instrument


def test_gap_safe_rate_does_not_bridge_missing_run():
    values = np.array([0.0, 1.0, np.nan, np.nan, 10.0, 11.0])
    rate, meta = dx_dt_robust(values, method="diff", smooth_window=3)
    assert np.isnan(rate[2:4]).all()
    assert rate[5] == pytest.approx(1.0)
    assert np.nanmax(np.abs(rate)) == pytest.approx(1.0)
    assert meta["n_runs"] == 2
    assert meta["version"] == RATE_UTILS_VERSION


def test_vectorized_theil_sen_matches_reference_windows():
    values = np.array([0.0, 0.2, 0.1, 0.8, 1.1, 1.0, 1.8, 2.0, 1.9])
    rate, _ = dx_dt_robust(
        values,
        method="theil_sen",
        smooth_window=5,
        hampel_window=99,
        hampel_n_sigmas=1e9,
    )
    expected = []
    for index in range(len(values)):
        low = max(0, index - 2)
        high = min(len(values), index + 3)
        expected.append(_theil_sen_slope(values[low:high]))
    assert rate == pytest.approx(expected)


def test_scorer_has_no_boundary_input():
    mapper = D3ScoreMapper(_yaml("d3_mapping.yaml"))
    value = SimpleNamespace(hard_violation_rate=0.0, soft_violation_rate=0.0)
    rate = SimpleNamespace(
        rate_soft_only_violation_rate=0.0,
        rate_hard_violation_rate=0.0,
    )
    scores = mapper.map(value, rate)
    assert scores == SubScores(5.0, 5.0, 5.0)


def test_insufficient_evidence_is_not_scored():
    aggregator = D3Aggregator(_yaml("d3_rules.yaml"), _yaml("d3_mapping.yaml"))
    value = SimpleNamespace(
        n_samples=20,
        hard_violation_rate=0.0,
        soft_violation_rate=0.0,
        consecutive_hard_max_min=0,
        out_of_instrument=False,
    )
    rate = SimpleNamespace(
        n_samples=19,
        rate_hard_consec_max_min=0,
        rate_soft_violation_rate=0.0,
        rate_soft_only_violation_rate=0.0,
        rate_hard_violation_rate=0.0,
        shock_candidate=False,
    )
    result = aggregator.aggregate(
        pd.Timestamp("2025-08-01 02:00"), "DO_1_1", "DO", SubScores(5.0, 5.0, 5.0), value, rate, 120
    )
    assert result.evidence_status == "insufficient"
    assert result.usable_tag == "not_evaluated"
    assert np.isnan(result.D3_total)


def test_persistent_rate_veto_does_not_need_d1():
    aggregator = D3Aggregator(_yaml("d3_rules.yaml"), _yaml("d3_mapping.yaml"))
    value = SimpleNamespace(
        n_samples=120,
        hard_violation_rate=0.0,
        soft_violation_rate=0.0,
        consecutive_hard_max_min=0,
        out_of_instrument=False,
    )
    rate = SimpleNamespace(
        n_samples=120,
        rate_hard_consec_max_min=31,
        rate_soft_violation_rate=0.3,
        rate_soft_only_violation_rate=0.0,
        rate_hard_violation_rate=0.3,
        shock_candidate=True,
    )
    result = aggregator.aggregate(
        pd.Timestamp("2025-08-01 02:00"), "DO_1_1", "DO", SubScores(5.0, 5.0, 2.8), value, rate, 120
    )
    assert result.veto_flag
    assert result.veto_reason == "persistent_rate"
    assert result.D3_total <= 2.5


def test_do4_zero_deadband_exempts_resolution_noise_but_not_offset():
    bounds = _yaml("d3_physical_bounds.yaml")["sensors"]["DO"]
    checker = ValueRangeChecker(
        _thresholds(),
        bounds["instrument_veto_range_low"],
        bounds["instrument_veto_range_high"],
    )
    within = checker.check(np.array([-0.03, -0.01, 0.00]), "DO_1_4", "DO")
    offset = checker.check(np.array([-0.06, -0.08]), "DO_1_4", "DO")
    hard = checker.check(np.array([-0.21]), "DO_1_4", "DO")
    assert within.soft_low_violation_count == 0
    assert within.physical_low_violation_count == 2
    assert within.zero_equivalent_count == 2
    assert within.soft_low == pytest.approx(0.0)
    assert within.effective_soft_low == pytest.approx(-0.05)
    assert within.soft_high is None
    assert within.threshold_scope == "sensor_override"
    assert offset.soft_low_violation_count == 2
    assert offset.zero_offset_warning_count == 2
    assert hard.hard_low_violation_count == 1
    assert hard.severe_negative_count == 1


def test_do4_does_not_inherit_aerobic_eight_mg_L_soft_upper():
    bounds = _yaml("d3_physical_bounds.yaml")["sensors"]["DO"]
    evidence = ValueRangeChecker(
        _thresholds(),
        bounds["instrument_veto_range_low"],
        bounds["instrument_veto_range_high"],
    ).check(np.array([0.1, 9.0, 12.0]), "DO_1_4", "DO")
    assert evidence.soft_high is None
    assert evidence.soft_high_violation_count == 0


def test_orp_interval_sensitivity_preserves_center():
    assert scale_interval(-400.0, 200.0, 1.2, anchor="center") == pytest.approx(
        (-460.0, 260.0)
    )
    assert scale_interval(0.0, 8.0, 1.2, anchor="lower") == pytest.approx(
        (0.0, 9.6)
    )
    assert scale_interval(-0.05, None, 1.2, anchor="none") == (-0.05, None)


def test_impulse_return_is_excluded_from_persistent_rate():
    config = deepcopy(_yaml("d3_rate_limits.yaml"))
    config["rate_estimator"]["method"] = "diff"
    checker = RateConstraintChecker(_thresholds(), config)
    values = np.full(120, 2.0)
    values[60] = 4.0
    evidence = checker.check(values, "DO_1_1", "DO")
    assert evidence.impulse_return_event_count == 1
    assert evidence.rate_hard_violation_rate == pytest.approx(0.0)
    assert evidence.persistent_rate_event_count == 0


def test_same_sign_ramp_triggers_persistent_rate_unless_process_guarded():
    config = deepcopy(_yaml("d3_rate_limits.yaml"))
    config["rate_estimator"]["method"] = "diff"
    checker = RateConstraintChecker(_thresholds(), config)
    values = np.full(120, 1.0)
    values[50:81] = 1.0 + np.arange(31) * 0.6
    values[81:] = values[80]
    unguarded = checker.check(values, "DO_1_1", "DO")
    guarded = checker.check(
        values,
        "DO_1_1",
        "DO",
        process_coherent_mask=np.ones(len(values), dtype=bool),
    )
    assert unguarded.rate_hard_violation_rate > 0
    assert unguarded.rate_hard_consec_max_min >= 10
    assert unguarded.persistent_rate_event_count == 1
    assert guarded.rate_hard_violation_rate == pytest.approx(0.0)
    assert guarded.process_coherence_guarded_points > 0


def test_soft_only_and_hard_persistent_episodes_are_mutually_exclusive():
    config = deepcopy(_yaml("d3_rate_limits.yaml"))
    config["rate_estimator"]["method"] = "diff"
    checker = RateConstraintChecker(_thresholds(), config)

    soft = np.full(120, 1.0)
    soft[50:56] = 1.0 + np.arange(1, 7) * 0.30
    soft[56:] = soft[55]
    soft_evidence = checker.check(soft, "DO_1_1", "DO")
    assert soft_evidence.rate_soft_only_violation_rate > 0
    assert soft_evidence.rate_hard_violation_rate == pytest.approx(0.0)

    hard = np.full(120, 1.0)
    hard[50:81] = 1.0 + np.arange(1, 32) * 0.60
    hard[81:] = hard[80]
    hard_evidence = checker.check(hard, "DO_1_1", "DO")
    assert hard_evidence.rate_hard_violation_rate > 0
    assert hard_evidence.rate_soft_only_violation_rate == pytest.approx(0.0)

    mapper = D3ScoreMapper(_yaml("d3_mapping.yaml"))
    value = SimpleNamespace(hard_violation_rate=0.0, soft_violation_rate=0.0)
    assert mapper.map(value, soft_evidence).Q_persistent_rate < 5.0
    assert mapper.map(value, hard_evidence).Q_persistent_rate < 5.0


def test_missing_recovery_jump_is_not_a_rate_event():
    config = deepcopy(_yaml("d3_rate_limits.yaml"))
    config["rate_estimator"]["method"] = "diff"
    checker = RateConstraintChecker(_thresholds(), config)
    values = np.r_[np.full(50, 2.0), np.full(10, np.nan), np.full(60, 6.0)]
    evidence = checker.check(values, "DO_1_1", "DO")
    assert evidence.rate_hard_point_violation_rate == pytest.approx(0.0)
    assert evidence.rate_hard_violation_rate == pytest.approx(0.0)


@pytest.mark.parametrize("source,ids", [("rolling_quantile", ("BW001",)), ("benchmark_quantile", ())])
def test_boundary_threshold_contract_rejects_untraceable_sources(source, ids):
    bound = PhysicalBound(
        threshold_id="TBAD",
        sensor_type="DO",
        sensor_scope="DO_1_1",
        condition_scope="all_observed_conditions",
        bound_type="boundary",
        low=0.5,
        high=None,
        unit="mg/L",
        source=source,
        benchmark_window_ids=ids,
        benchmark_version="benchmark@v2.2.0",
        context_version="fixed_physical_contract_v2.2",
        version="v2.2.0",
        validator_passed=True,
    )
    with pytest.raises(ConfigValidationError):
        ThresholdStore.validate([bound])


def test_source_layers_do_not_import_d1_or_d2_scores():
    forbidden = ("state_blackboard", "d1_streaming_stub", "q_rate_override", "cooldown_triggered_by_d1")
    source = "\n".join(
        path.read_text(encoding="utf-8").lower()
        for folder in (ROOT / "src" / "d3_physical", ROOT / "src" / "pipeline")
        for path in folder.glob("*.py")
    )
    assert not any(token in source for token in forbidden)
