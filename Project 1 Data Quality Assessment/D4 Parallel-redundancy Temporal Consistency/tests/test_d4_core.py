from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import numpy as np


D4_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(D4_ROOT / "src"))

from d4.scoring import (
    aggregate_scores,
    apply_d1_fuse,
    compare_change_points,
    compute_window_metrics,
    score_from_quantiles,
)
from d4.pipeline import _mapping_id, _phase_labels
from d4.config import load_config
from d4.validation import _inject, _time_block_ids
from d4.episode_validation import _event_runs, _resample_boundaries, _summary
from d4.publication import manifest_relative_path, publication_sha256


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


def test_common_support_is_invariant_to_asymmetric_extra_values():
    shared_target = np.linspace(0.0, 1.0, 120)
    shared_reference = shared_target + 0.1
    target_a = np.r_[shared_target, np.repeat(np.nan, 24)]
    reference_a = np.r_[shared_reference, np.linspace(100.0, 200.0, 24)]
    target_b = np.r_[shared_target, np.linspace(-200.0, -100.0, 24)]
    reference_b = np.r_[shared_reference, np.repeat(np.nan, 24)]
    first = compute_window_metrics(target_a, reference_a, deadband=0.2, points_per_hour=6)
    second = compute_window_metrics(target_b, reference_b, deadband=0.2, points_per_hour=6)
    assert first.n_common == second.n_common == 120
    assert np.isclose(first.risk_dist, second.risk_dist)
    assert np.isclose(first.risk_trend, second.risk_trend)
    assert np.isclose(first.risk_var, second.risk_var)


def test_common_support_provenance_detects_asymmetric_missingness():
    target = np.r_[np.arange(120, dtype=float), np.repeat(np.nan, 24)]
    reference = np.arange(144, dtype=float)
    result = compute_window_metrics(target, reference, deadband=0.2, points_per_hour=6)
    assert result.valid_fraction_target == 120 / 144
    assert result.valid_fraction_reference == 1.0
    assert result.valid_fraction_common == 120 / 144
    assert result.asymmetric_missing_fraction == 24 / 144
    assert result.support_jaccard == 120 / 144


def test_phase_contract_prevents_validation_rows_from_entering_development():
    cfg = load_config(D4_ROOT / "configs" / "d4.yaml", D4_ROOT.parent)
    timestamps = pd.Series(pd.to_datetime([
        "2026-01-24 23:00", "2026-01-25 00:00", "2026-02-01 00:00",
    ]))
    labels = _phase_labels(timestamps, cfg)
    assert labels.tolist() == ["development", "embargo", "internal_validation"]


def test_mapping_id_binds_fit_period_and_component_version():
    base = {
        "variable": "DO", "regime_id": 0, "subscore": "Q_dist",
        "risk_metric": "risk_dist", "q50": 0.1, "q75": 0.2,
        "q90": 0.3, "q97_5": 0.4, "fit_start": "2025-08-01",
        "fit_end": "2026-01-24", "common_support_policy": "synchronous",
        "distribution_component_version": "full-v1",
        "min_exact_independent_blocks": 6,
        "support_admission_rule": "minimum_windows_and_independent_7d_blocks",
    }
    changed_period = {**base, "fit_end": "2026-01-31"}
    changed_component = {**base, "distribution_component_version": "w1-only-v1"}
    assert _mapping_id(base) != _mapping_id(changed_period)
    assert _mapping_id(base) != _mapping_id(changed_component)


def test_common_change_challenges_preserve_the_predefined_mechanism_roles():
    target = np.zeros(120, dtype=float)
    reference = np.zeros(120, dtype=float)
    rng = np.random.default_rng(7)
    equal_target, equal_reference = _inject(
        target, reference, "common_mode_drift", 1.0, rng
    )
    unequal_target, unequal_reference = _inject(
        target, reference, "common_unequal", 1.0, rng
    )
    opposite_target, opposite_reference = _inject(
        target, reference, "opposite_direction", 1.0, rng
    )
    assert np.allclose(equal_target, equal_reference)
    assert unequal_target[-1] > unequal_reference[-1] > 0
    assert np.isclose(unequal_reference[-1] / unequal_target[-1], 0.4)
    assert opposite_target[-1] > 0 > opposite_reference[-1]
    assert np.isclose(opposite_target[-1], -opposite_reference[-1])


def test_bootstrap_join_cannot_merge_two_distinct_low_score_episodes():
    score = np.array([2.0, 2.0, 2.0, 2.0, 2.0, 2.0])
    evaluable = np.ones(6, dtype=bool)
    merged = _summary(score, evaluable)
    separated = _summary(
        score, evaluable, break_before=np.array([False, False, False, True, False, False])
    )
    assert merged["n_events"] == 1
    assert merged["median_duration_h"] == 6
    assert separated["n_events"] == 2
    assert separated["median_duration_h"] == 3
    assert separated["n_evaluable_hours"] == 6


def test_circular_wrap_and_resampled_block_joins_are_event_boundaries():
    sampled = np.array([8, 9, 0, 1, 2, 3, 5, 6, 7, 8, 9, 0])
    boundaries = _resample_boundaries(sampled, block_hours=6)
    assert boundaries.tolist() == [
        False, False, True, False, False, False,
        True, False, False, False, False, True,
    ]
    events = _event_runs(
        np.full(12, 2.0), np.ones(12, dtype=bool), break_before=boundaries
    )
    assert [event["duration_h"] for event in events] == [4.0, 5.0]


def test_validation_time_blocks_keep_contemporaneous_pairs_together():
    timestamps = pd.Series(pd.to_datetime([
        "2026-02-01", "2026-02-01", "2026-02-07 23:00", "2026-02-08",
    ], format="mixed"))
    blocks = _time_block_ids(timestamps, block_days=7)
    assert blocks.tolist() == [0, 0, 0, 1]


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
from d4.integration import build_d4_d5_readiness


def test_d5_arbitration_finalizes_without_mutating_independent_scores() -> None:
    d4 = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2025-08-01 00:00"]),
            "pair_id": ["PAIR_DO11"],
            "D4_raw": [4.2],
            "D4_after_D1": [4.0],
            "D4_forDQR": [np.nan],
        }
    )
    d5 = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2025-08-01 00:00"]),
            "pair_id": ["PAIR_DO11"],
            "zone_consensus_label": ["not_evaluable"],
            "zone_consensus_strength": [np.nan],
            "target_D5_report": [np.nan],
            "reference_D5_report": [np.nan],
            "d5_evaluable": [False],
            "d5_score_ready": [False],
            "d5_action_ready": [False],
            "support_level": ["L2"],
            "limited_support": [True],
            "process_coherence_guard_active": [False],
            "attribution_suppressed": [False],
            "sensor_identity_veto_active": [False],
            "veto_active": [False],
            "decision_type": ["not_triggered"],
            "sensor_veto_role": ["none"],
            "topology_hash": ["hash"],
            "template_version": ["candidate"],
            "d5_run_id": ["run"],
            "interface_version": ["d5-d4-v2.3"],
            "track_id": ["d5_local"],
        }
    )
    output = build_d4_d5_readiness(d4, d5)
    assert output.loc[0, "integration_status"] == "final_independent_D5_limited"
    assert output.loc[0, "finalization_allowed"]
    assert output.loc[0, "D4_forDQR"] == 4.2
    assert output.loc[0, "D4_numeric_adjustment"] == 0.0
    assert output.loc[0, "D4_raw"] == d4.loc[0, "D4_raw"]
    assert not output.loc[0, "D4_gate_applicable"]


def test_process_guard_suppresses_attribution_without_changing_d4_score() -> None:
    d4 = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2025-08-01 00:00"]),
            "pair_id": ["PAIR_DO11"],
            "D4_raw": [2.0],
            "D4_after_D1": [2.0],
            "D4_forDQR": [np.nan],
        }
    )
    d5 = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2025-08-01 00:00"]),
            "pair_id": ["PAIR_DO11"],
            "zone_consensus_label": ["zone_coherent_process_shift"],
            "zone_consensus_strength": [0.9],
            "target_D5_report": [2.2],
            "reference_D5_report": [2.3],
            "d5_evaluable": [True],
            "d5_score_ready": [True],
            "d5_action_ready": [True],
            "support_level": ["L3"],
            "limited_support": [False],
            "process_coherence_guard_active": [True],
            "attribution_suppressed": [True],
            "sensor_identity_veto_active": [False],
            "veto_active": [False],
            "decision_type": ["process_coherence_guard"],
            "sensor_veto_role": ["none"],
            "topology_hash": ["hash"],
            "template_version": ["admitted"],
            "d5_run_id": ["run"],
            "interface_version": ["d5-d4-v2.3"],
            "track_id": ["d5_local"],
        }
    )
    output = build_d4_d5_readiness(d4, d5)
    assert output.loc[0, "D4_forDQR"] == 2.0
    assert output.loc[0, "D4_gate_applicable"]
    assert not output.loc[0, "sensor_fault_attribution_allowed"]
    assert not output.loc[0, "veto_active"]
    assert (
        output.loc[0, "causal_attribution"]
        == "coherent_process_change_not_sensor_fault"
    )


def test_publication_text_hash_normalizes_line_endings(tmp_path) -> None:
    lf_path = tmp_path / "lf.md"
    crlf_path = tmp_path / "crlf.md"
    lf_path.write_bytes(b"heading\nbody\n")
    crlf_path.write_bytes(b"heading\r\nbody\r\n")
    assert publication_sha256(lf_path) == publication_sha256(crlf_path)


def test_publication_manifest_paths_are_cross_platform() -> None:
    assert manifest_relative_path(r"outputs\figures\figure.svg") == Path(
        "outputs", "figures", "figure.svg"
    )
