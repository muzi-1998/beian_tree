from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
import yaml

from src.common.exceptions import ConfigValidationError
from src.common.rate_utils import RATE_UTILS_VERSION, dx_dt_robust
from src.d4_physical.aggregator import D4Aggregator
from src.d4_physical.scorer import D4ScoreMapper, SubScores, logistic_zero_anchored
from src.d4_physical.threshold_store import PhysicalBound, ThresholdStore


ROOT = Path(__file__).parent.parent


def _yaml(name: str) -> dict:
    return yaml.safe_load((ROOT / "configs" / name).read_text(encoding="utf-8"))


def test_zero_violation_maps_exactly_to_five():
    assert logistic_zero_anchored(0.0, x0=0.05, k=20.0) == pytest.approx(5.0)
    assert logistic_zero_anchored(0.5, x0=0.05, k=20.0) < 1.01


def test_boundary_is_not_part_of_d4_score():
    mapping = _yaml("d4_mapping.yaml")
    assert set(mapping["aggregation"]["weights"]) == {"Q_value_hard", "Q_value_soft", "Q_rate"}
    assert sum(mapping["aggregation"]["weights"].values()) == pytest.approx(1.0)
    assert mapping["diagnostics"]["boundary_behavior"]["included_in_score"] is False


def test_instrument_range_does_not_override_hard_tolerance():
    bounds = _yaml("d4_physical_bounds.yaml")["sensors"]
    for config in bounds.values():
        assert config["instrument_range_low"] <= config["hard_low"]
        assert config["instrument_range_high"] >= config["hard_high"]


def test_gap_safe_rate_does_not_bridge_missing_run():
    values = np.array([0.0, 1.0, np.nan, np.nan, 10.0, 11.0])
    rate, meta = dx_dt_robust(values, method="diff", smooth_window=3)
    assert np.isnan(rate[2:4]).all()
    assert rate[5] == pytest.approx(1.0)
    assert np.nanmax(np.abs(rate)) == pytest.approx(1.0)
    assert meta["n_runs"] == 2
    assert meta["version"] == RATE_UTILS_VERSION


def test_scorer_has_no_boundary_input():
    mapper = D4ScoreMapper(_yaml("d4_mapping.yaml"))
    value = SimpleNamespace(hard_violation_rate=0.0, soft_violation_rate=0.0)
    rate = SimpleNamespace(rate_hard_violation_rate=0.0)
    scores = mapper.map(value, rate)
    assert scores == SubScores(5.0, 5.0, 5.0)


def test_insufficient_evidence_is_not_scored():
    aggregator = D4Aggregator(_yaml("d4_rules.yaml"), _yaml("d4_mapping.yaml"))
    value = SimpleNamespace(
        n_samples=20,
        hard_violation_rate=0.0,
        soft_violation_rate=0.0,
        consecutive_hard_max_min=0,
        out_of_instrument=False,
    )
    rate = SimpleNamespace(n_samples=19, rate_hard_consec_max_min=0, rate_hard_violation_rate=0.0, shock_candidate=False)
    result = aggregator.aggregate(
        pd.Timestamp("2025-08-01 02:00"), "DO_1_1", "DO", SubScores(5.0, 5.0, 5.0), value, rate, 120
    )
    assert result.evidence_status == "insufficient"
    assert result.usable_tag == "not_evaluated"
    assert np.isnan(result.D4_total)


def test_persistent_rate_veto_does_not_need_d1():
    aggregator = D4Aggregator(_yaml("d4_rules.yaml"), _yaml("d4_mapping.yaml"))
    value = SimpleNamespace(
        n_samples=120,
        hard_violation_rate=0.0,
        soft_violation_rate=0.0,
        consecutive_hard_max_min=0,
        out_of_instrument=False,
    )
    rate = SimpleNamespace(n_samples=120, rate_hard_consec_max_min=31, rate_hard_violation_rate=0.3, shock_candidate=True)
    result = aggregator.aggregate(
        pd.Timestamp("2025-08-01 02:00"), "DO_1_1", "DO", SubScores(5.0, 5.0, 2.8), value, rate, 120
    )
    assert result.veto_flag
    assert result.veto_reason == "rate_persistent"
    assert result.D4_total <= 2.5


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
        for folder in (ROOT / "src" / "d4_physical", ROOT / "src" / "pipeline")
        for path in folder.glob("*.py")
    )
    assert not any(token in source for token in forbidden)
