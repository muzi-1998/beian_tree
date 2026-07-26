from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import numpy as np


D6_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(D6_ROOT / "src"))

from d6.scoring import (
    aggregate_scores,
    apply_d1_fuse,
    compare_change_points,
    compute_window_metrics,
    score_from_quantiles,
)


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


def test_change_point_comparison_matches_nearest_pair_event():
    end = pd.DatetimeIndex([pd.Timestamp("2026-01-08 00:00")])
    target = pd.DataFrame({
        "cp_time": [pd.Timestamp("2026-01-07")],
        "cp_strength": [0.8],
        "cp_age_h": [24.0],
        "cp_candidates": [(pd.Timestamp("2026-01-03"), pd.Timestamp("2026-01-07"))],
        "cp_candidate_strengths": [(0.7, 0.8)],
    }, index=end)
    reference = pd.DataFrame({
        "cp_time": [pd.Timestamp("2026-01-06")],
        "cp_strength": [0.9],
        "cp_age_h": [48.0],
        "cp_candidates": [(pd.Timestamp("2026-01-03 02:00"), pd.Timestamp("2026-01-06"))],
        "cp_candidate_strengths": [(0.75, 0.9)],
    }, index=end)
    result = compare_change_points(target, reference)
    assert result.loc[end[0], "d_cp"] == 2.0
    assert result.loc[end[0], "Q_cp"] == 5.0


def test_change_point_one_sided_duration_uses_v12_fixed_scores():
    end = pd.DatetimeIndex([pd.Timestamp("2026-01-08 00:00")])
    target = pd.DataFrame({
        "cp_time": [pd.Timestamp("2026-01-07 18:00")],
        "cp_strength": [0.8],
        "cp_age_h": [6.0],
        "cp_candidates": [(pd.Timestamp("2026-01-07 18:00"),)],
        "cp_candidate_strengths": [(0.8,)],
    }, index=end)
    reference = pd.DataFrame({
        "cp_time": [pd.NaT], "cp_strength": [np.nan], "cp_age_h": [np.nan],
        "cp_candidates": [tuple()], "cp_candidate_strengths": [tuple()],
    }, index=end)
    result = compare_change_points(target, reference)
    assert result.loc[end[0], "cp_one_sided"]
    assert result.loc[end[0], "Q_cp"] == 2.0


def test_d1_fuse_preserves_raw_and_neutralizes_unreliable_reference():
    score, state = apply_d1_fuse(
        np.array([2.0, 2.0, 2.0, 2.0]),
        np.array([4.5, 4.5, 2.0, 2.0]),
        np.array([4.5, 2.0, 4.5, 2.0]),
        np.ones(4, dtype=bool),
        unreliable_below=2.5,
    )
    assert state.tolist() == [
        "valid_pair", "reference_unreliable", "target_suspect", "bilateral_unreliable"
    ]
    assert score.tolist() == [2.0, 3.0, 2.0, 3.0]
from d6.integration import build_d6_d7_readiness


def test_d7_arbitration_finalizes_without_mutating_independent_scores() -> None:
    d6 = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2025-08-01 00:00"]),
            "pair_id": ["PAIR_DO11"],
            "D6_raw": [4.2],
            "D6_after_D1": [4.0],
            "D6_forDQR": [np.nan],
        }
    )
    d7 = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2025-08-01 00:00"]),
            "pair_id": ["PAIR_DO11"],
            "zone_consensus_label": ["not_evaluable"],
            "zone_consensus_strength": [np.nan],
            "target_D7": [np.nan],
            "reference_D7": [np.nan],
            "d7_evaluable": [False],
            "d7_score_ready": [False],
            "d7_action_ready": [False],
            "support_level": ["L2"],
            "limited_support": [True],
            "protective_veto_active": [False],
            "sensor_veto_active": [False],
            "veto_type": ["not_triggered"],
            "sensor_veto_role": ["none"],
            "topology_hash": ["hash"],
            "template_version": ["candidate"],
            "d7_run_id": ["run"],
            "interface_version": ["d7-d6-v2.2"],
            "track_id": ["d7_local"],
        }
    )
    output = build_d6_d7_readiness(d6, d7)
    assert output.loc[0, "integration_status"] == "final_independent_D7_limited"
    assert output.loc[0, "finalization_allowed"]
    assert output.loc[0, "D6_forDQR"] == 4.0
    assert output.loc[0, "D6_numeric_adjustment"] == 0.0
    assert output.loc[0, "D6_raw"] == d6.loc[0, "D6_raw"]
    assert not output.loc[0, "D6_gate_applicable"]


def test_process_protection_disables_gate_without_changing_d6_score() -> None:
    d6 = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2025-08-01 00:00"]),
            "pair_id": ["PAIR_DO11"],
            "D6_raw": [2.0],
            "D6_after_D1": [2.0],
            "D6_forDQR": [np.nan],
        }
    )
    d7 = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2025-08-01 00:00"]),
            "pair_id": ["PAIR_DO11"],
            "zone_consensus_label": ["zone_coherent_process_shift"],
            "zone_consensus_strength": [0.9],
            "target_D7": [2.2],
            "reference_D7": [2.3],
            "d7_evaluable": [True],
            "d7_score_ready": [True],
            "d7_action_ready": [True],
            "support_level": ["L3"],
            "limited_support": [False],
            "protective_veto_active": [True],
            "sensor_veto_active": [False],
            "veto_type": ["process_coherence_protection"],
            "sensor_veto_role": ["none"],
            "topology_hash": ["hash"],
            "template_version": ["admitted"],
            "d7_run_id": ["run"],
            "interface_version": ["d7-d6-v2.2"],
            "track_id": ["d7_local"],
        }
    )
    output = build_d6_d7_readiness(d6, d7)
    assert output.loc[0, "D6_forDQR"] == 2.0
    assert not output.loc[0, "D6_gate_applicable"]
    assert (
        output.loc[0, "causal_attribution"]
        == "coherent_process_change_not_sensor_fault"
    )
