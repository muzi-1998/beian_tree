from __future__ import annotations

import pandas as pd
import pytest

from src.mapping.mapper import combine_freeze_subscores


def _series(values):
    return pd.Series(values, index=pd.date_range("2025-01-01", periods=len(values), freq="h"))


WEIGHTS = {"rle": 0.40, "low_var": 0.35, "unique": 0.25}
FLOOR_POLICY = {
    "enabled": True,
    "scoring_modes": ["floor_freeze"],
    "production_mode": "hard_rle_only",
}


def test_standard_channel_keeps_weighted_composite():
    score, mode = combine_freeze_subscores(
        _series([5.0]), _series([3.0]), _series([4.0]), WEIGHTS,
        scoring_mode="iid", floor_policy=FLOOR_POLICY,
    )
    assert mode == "weighted_composite"
    assert score.iloc[0] == pytest.approx(4.05)


def test_process_floor_is_not_penalised_by_soft_freeze_evidence():
    score, mode = combine_freeze_subscores(
        _series([5.0, 5.0]), _series([1.0, 1.5]), _series([1.0, 2.0]), WEIGHTS,
        scoring_mode="floor_freeze", floor_policy=FLOOR_POLICY,
    )
    assert mode == "floor_hard_rle_only"
    assert score.tolist() == [5.0, 5.0]


def test_process_floor_still_detects_hard_run_length_freeze():
    score, _ = combine_freeze_subscores(
        _series([5.0, 2.0, 1.0]), _series([5.0, 5.0, 5.0]),
        _series([5.0, 5.0, 5.0]), WEIGHTS,
        scoring_mode="floor_freeze", floor_policy=FLOOR_POLICY,
    )
    assert score.tolist() == [5.0, 2.0, 1.0]


def test_unknown_floor_mode_fails_closed():
    policy = dict(FLOOR_POLICY, production_mode="unsupported")
    with pytest.raises(ValueError, match="Unsupported freeze floor"):
        combine_freeze_subscores(
            _series([5.0]), _series([5.0]), _series([5.0]), WEIGHTS,
            scoring_mode="floor_freeze", floor_policy=policy,
        )
