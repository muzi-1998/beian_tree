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
from src.d3_physical.threshold_store import ThresholdStore
from src.d3_physical.value_range_checker import ValueRangeChecker


ROOT = Path(__file__).parent.parent


def _yaml(name: str) -> dict:
    return yaml.safe_load((ROOT / "configs" / name).read_text(encoding="utf-8"))


def _thresholds() -> ThresholdStore:
    benchmark = SimpleNamespace(_fixed_tails={}, version="benchmark@v2.2.0")
    return ThresholdStore.build(
        _yaml("d3_physical_bounds.yaml"),
        _yaml("d3_rate_limits.yaml"),
        benchmark,
        version="v2.5.0",
    )


def test_freshwater_saturation_reference_is_temperature_monotone():
    values = freshwater_do_saturation_mg_l(np.array([0.0, 15.0, 30.0, np.nan, 41.0]))
    assert values[:3] == pytest.approx([14.652, 10.03418775, 7.437402], abs=1e-6)
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
    assert evidence.threshold_scope == "temperature_conditioned_position_template"


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
    assert evidence.soft_high_scored is False


def test_frozen_position_registry_has_prespecified_support():
    calibration = _yaml("d3_physical_bounds.yaml")["operational_envelope_contract"][
        "aerobic_do_temperature_conditioned_upper"
    ]["calibration"]
    assert set(calibration["alpha_by_position"]) == {"1", "2", "3"}
    assert all(
        int(value) >= int(calibration["minimum_calibration_sensor_hours"])
        for value in calibration["calibration_support_sensor_hours"].values()
    )
