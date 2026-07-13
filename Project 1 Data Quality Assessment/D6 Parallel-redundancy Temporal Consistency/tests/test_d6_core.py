from __future__ import annotations

import sys
from pathlib import Path

import numpy as np


D6_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(D6_ROOT / "src"))

from d6.scoring import aggregate_scores, compute_window_metrics, score_from_quantiles


def test_identical_pair_has_zero_distance_and_variance_risk():
    values = np.sin(np.linspace(0, 4 * np.pi, 144))
    result = compute_window_metrics(values, values, deadband=0.2, points_per_hour=6)
    assert result.d_w1 == 0
    assert result.d_ks == 0
    assert result.d_var == 0
    assert result.d_cp == 0


def test_deadband_only_exempts_low_excitation_variance():
    target = np.full(144, 0.01)
    reference = np.full(144, -0.01)
    result = compute_window_metrics(target, reference, deadband=0.2, points_per_hour=6)
    assert result.deadband_active
    assert result.risk_var == 0
    assert result.risk_dist > 0


def test_pair_metrics_are_symmetric_under_sensor_swap():
    target = np.sin(np.linspace(0, 4 * np.pi, 144))
    reference = 0.8 * np.sin(np.linspace(0.2, 4 * np.pi + 0.2, 144))
    forward = compute_window_metrics(target, reference, deadband=0.2, points_per_hour=6)
    reverse = compute_window_metrics(reference, target, deadband=0.2, points_per_hour=6)
    for field in ("risk_dist", "risk_trend", "risk_var", "risk_cp"):
        assert np.isclose(getattr(forward, field), getattr(reverse, field))


def test_quantile_mapping_is_monotone_decreasing():
    values = np.array([0.1, 0.5, 1.5, 2.5, 5.0])
    scores = score_from_quantiles(values, np.array([0.5, 1.0, 2.0, 3.0]))
    assert np.all(np.diff(scores) <= 0)
    assert scores.tolist() == [5.0, 5.0, 3.0, 2.0, 1.0]


def test_noncompensatory_aggregation_preserves_low_subscore_penalty():
    base, raw = aggregate_scores(
        np.array([5.0]), np.array([5.0]), np.array([5.0]), np.array([1.0]),
        weights={"dist": 0.35, "trend": 0.25, "var": 0.20, "cp": 0.20},
        lambda_blend=0.75,
    )
    assert np.isclose(base[0], 4.2)
    assert np.isclose(raw[0], 3.4)
