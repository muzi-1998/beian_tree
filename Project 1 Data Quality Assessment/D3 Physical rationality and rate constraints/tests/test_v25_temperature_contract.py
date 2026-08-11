from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
import yaml

from src.data.input_loader import align_temperature_to_grid, load_temperature_proxy
from src.d3_physical.do_temperature_envelope import (
    freshwater_do_saturation_mg_l,
    temperature_conditioned_upper,
)
from src.d3_physical.aggregator import D3Aggregator
from src.d3_physical.scorer import SubScores
from src.d3_physical.threshold_store import ThresholdStore
from src.d3_physical.value_range_checker import ValueRangeChecker
from src.validation.d3_validation import (
    _legacy_v23_rate_score,
    _operational_envelope_family,
)
from src.validation.do_temperature_validation import _alpha_uncertainty_scenarios


ROOT = Path(__file__).parent.parent


def _yaml(name: str) -> dict:
    return yaml.safe_load((ROOT / "configs" / name).read_text(encoding="utf-8"))


def _thresholds() -> ThresholdStore:
    benchmark = SimpleNamespace(_fixed_tails={}, version="benchmark@v2.2.0")
    return ThresholdStore.build(
        _yaml("d3_physical_bounds.yaml"),
        _yaml("d3_rate_limits.yaml"),
        benchmark,
        version="v2.7.0",
    )


def test_freshwater_saturation_reference_is_temperature_monotone():
    values = freshwater_do_saturation_mg_l(np.array([0.0, 15.0, 30.0, np.nan, 41.0]))
    assert values[:3] == pytest.approx(
        [14.6208337002, 10.0838583410, 7.5587960478], abs=1e-9
    )
    assert np.all(np.diff(values[:3]) < 0)
    assert np.isnan(values[3:]).all()


def test_temperature_source_is_complete_minute_and_aligned_without_extrapolation():
    paths = _yaml("d3_paths.yaml")
    temperature = load_temperature_proxy(paths, ROOT)
    assert temperature.index.min() == pd.Timestamp("2025-08-01 00:00:00")
    assert temperature.index.max() == pd.Timestamp("2026-07-30 23:59:00")
    assert len(temperature) == 524160
    assert temperature.attrs["raw_missing_count"] == 4205
    assert temperature.attrs["invalid_range_count"] == 8
    target = pd.DatetimeIndex(
        [
            "2025-07-31 23:59:00",
            "2025-08-01 00:00:00",
            "2025-08-01 00:01:00",
            "2026-07-31 00:00:00",
        ]
    )
    aligned = align_temperature_to_grid(temperature, target)
    assert np.isnan(aligned.iloc[0])
    assert aligned.iloc[1] == pytest.approx(temperature.iloc[0])
    assert aligned.iloc[2] == pytest.approx(temperature.iloc[1])
    assert np.isnan(aligned.iloc[3])


def test_dynamic_upper_uses_shared_position_alpha_and_excludes_do4():
    contract = _yaml("d3_physical_bounds.yaml")["operational_envelope_contract"][
        "aerobic_do_temperature_conditioned_upper"
    ]
    temperature = np.array([10.0, 20.0])
    upper_1, status_1 = temperature_conditioned_upper(
        temperature,
        {"type": "DO", "position": 1, "process_zone": "aerobic"},
        contract,
    )
    upper_2, _ = temperature_conditioned_upper(
        temperature,
        {"type": "DO", "position": 2, "process_zone": "aerobic"},
        contract,
    )
    do4, status_4 = temperature_conditioned_upper(
        temperature,
        {"type": "DO", "position": 4, "process_zone": "post_anoxic"},
        contract,
    )
    assert status_1 == "evaluated"
    assert not np.allclose(upper_1, upper_2)
    assert do4 is None and status_4 == "not_applicable"


def test_dynamic_upper_reports_partial_temperature_coverage():
    contract = _yaml("d3_physical_bounds.yaml")["operational_envelope_contract"][
        "aerobic_do_temperature_conditioned_upper"
    ]
    upper, status = temperature_conditioned_upper(
        np.array([20.0, np.nan]),
        {"type": "DO", "position": 1, "process_zone": "aerobic"},
        contract,
    )
    assert np.isfinite(upper[0]) and np.isnan(upper[1])
    assert status == "partially_evaluated"


def test_dynamic_high_only_scores_evaluable_minutes():
    bounds = _yaml("d3_physical_bounds.yaml")["sensors"]["DO"]
    checker = ValueRangeChecker(
        _thresholds(),
        bounds["instrument_veto_range_low"],
        bounds["instrument_veto_range_high"],
    )
    evidence = checker.check(
        np.array([2.0, 3.0, 4.0, np.nan]),
        "DO_1_1",
        "DO",
        dynamic_soft_high=np.array([2.5, np.nan, 3.5, 3.0]),
        soft_high_mode="temperature_conditioned_influent_proxy",
    )
    assert evidence.soft_high_evaluable_count == 2
    assert evidence.soft_high_evaluable_fraction == pytest.approx(2 / 3)
    assert evidence.soft_high_violation_count == 1
    assert evidence.soft_high_violation_rate_evaluable == pytest.approx(0.5)
    assert evidence.soft_high_violation_rate == pytest.approx(1 / 3)
    assert evidence.soft_violation_rate == pytest.approx(0.5)
    assert evidence.soft_state_determinable_count == 2
    assert evidence.soft_state_determinable_fraction == pytest.approx(2 / 3)
    assert (
        evidence.soft_violation_rate_denominator
        == "dynamic_union_on_determinable_minutes"
    )
    assert evidence.threshold_scope == "temperature_conditioned_position_template"


def test_dynamic_soft_union_keeps_low_evidence_with_missing_temperature():
    bounds = _yaml("d3_physical_bounds.yaml")["sensors"]["DO"]
    checker = ValueRangeChecker(
        _thresholds(),
        bounds["instrument_veto_range_low"],
        bounds["instrument_veto_range_high"],
    )
    evidence = checker.check(
        np.array([-0.10, 3.0, 4.0]),
        "DO_1_1",
        "DO",
        dynamic_soft_high=np.array([np.nan, np.nan, 3.5]),
        soft_high_mode="temperature_conditioned_influent_proxy",
    )
    assert evidence.soft_low_violation_count == 1
    assert evidence.soft_high_violation_count == 1
    assert evidence.soft_state_determinable_count == 2
    assert evidence.soft_state_determinable_fraction == pytest.approx(2 / 3)
    assert evidence.soft_violation_rate == pytest.approx(1.0)


def test_diagnostic_only_dynamic_high_is_exported_but_not_scored():
    bounds = _yaml("d3_physical_bounds.yaml")["sensors"]["DO"]
    checker = ValueRangeChecker(
        _thresholds(),
        bounds["instrument_veto_range_low"],
        bounds["instrument_veto_range_high"],
    )
    evidence = checker.check(
        np.array([6.0, 6.0]),
        "DO_2_3",
        "DO",
        dynamic_soft_high=np.array([5.0, 5.0]),
        soft_high_mode="temperature_conditioned_influent_proxy",
        score_soft_high=False,
    )
    assert evidence.soft_high_violation_count == 2
    assert evidence.soft_violation_count == 0
    assert evidence.soft_violation_rate == pytest.approx(0.0)
    assert evidence.soft_state_determinable_fraction == pytest.approx(1.0)
    assert (
        evidence.soft_violation_rate_denominator
        == "scored_low_side_on_observed_minutes"
    )
    assert evidence.soft_high_scored is False


def test_frozen_position_registry_has_prespecified_support():
    calibration = _yaml("d3_physical_bounds.yaml")["operational_envelope_contract"][
        "aerobic_do_temperature_conditioned_upper"
    ]["calibration"]
    assert set(calibration["alpha_by_position"]) == {"1", "2", "3"}
    assert all(
        int(value) >= int(calibration["minimum_calibration_sensor_minutes"])
        for value in calibration["calibration_support_sensor_minutes"].values()
    )
    assert "Q_drift" in calibration["quality_filter"]
    assert calibration["resolution"] == "minute_calibration_minute_validation_minute_production"


def test_legacy_rate_reconstruction_uses_point_violation_mapping():
    rules = _yaml("d3_rules.yaml")
    assert _legacy_v23_rate_score(0.0, rules) == pytest.approx(5.0)
    assert _legacy_v23_rate_score(0.20, rules) < 2.0


def test_do4_uses_dedicated_route_and_cannot_enter_orp_envelope():
    assert _operational_envelope_family("DO_1_1") == "aerobic_do"
    assert _operational_envelope_family("DO_1_4") == "dedicated_route"
    assert _operational_envelope_family("DO_2_4") == "dedicated_route"
    assert _operational_envelope_family("ORP_1_3") == "orp"


def test_alpha_interval_scenarios_propagate_monotonically():
    index = pd.date_range("2026-02-01", periods=120, freq="min")
    detail = pd.DataFrame(
        {
            "ts": index,
            "sensor_id": "DO_1_1",
            "position": 1,
            "phase": "validation",
            "DO_minute_mg_L": 3.0,
            "Csat_reference_mg_L": 10.0,
            "upper_evaluable": True,
            "high_quality_evaluable": True,
            "high_quality_filter_pass": True,
            "dynamic_upper_mg_L": 3.0,
            "dynamic_warning": False,
        }
    )
    registry = pd.DataFrame(
        {
            "position": [1],
            "alpha_cluster_bootstrap_ci_low": [0.25],
            "frozen_alpha": [0.30],
            "alpha_cluster_bootstrap_ci_high": [0.35],
        }
    )
    calibration = {
        "bootstrap": {"replicates": 10, "seed": 7},
        "validation_window": {
            "minutes": 120,
            "minimum_high_quality_minutes": 60,
            "warning_if_exceedance_rate_gt": 0.02,
        },
        "scored_positions": ["1"],
    }
    result = _alpha_uncertainty_scenarios(detail, registry, calibration)
    rates = result.set_index("alpha_scenario")["dynamic_warning_rate_high_quality"]
    assert rates["bootstrap_lower"] >= rates["point_estimate"]
    assert rates["point_estimate"] >= rates["bootstrap_upper"]
    assert set(result["sensitivity_role"]) == {
        "bootstrap_interval_propagation_not_production_parameter_selection"
    }


def test_unknown_soft_state_is_not_reported_as_sufficient_or_pass():
    aggregator = D3Aggregator(_yaml("d3_rules.yaml"), _yaml("d3_mapping.yaml"))
    value = SimpleNamespace(
        n_samples=120,
        out_of_instrument=False,
        hard_violation_rate=0.0,
        soft_violation_rate=np.nan,
        consecutive_hard_max_min=0,
    )
    rate = SimpleNamespace(
        n_samples=120,
        shock_candidate=False,
        rate_hard_violation_rate=0.0,
        rate_soft_violation_rate=0.0,
        rate_soft_only_violation_rate=0.0,
        rate_hard_consec_max_min=0,
    )
    result = aggregator.aggregate(
        pd.Timestamp("2026-01-01"),
        "DO_1_1",
        "DO",
        SubScores(5.0, np.nan, 5.0, 5.0, 5.0),
        value,
        rate,
        expected_samples=120,
    )
    assert result.evidence_status == "context_unavailable"
    assert result.D3_gate_status == "NotEvaluated"
    assert result.usable_tag == "not_evaluated"
    assert np.isnan(result.D3_total)
