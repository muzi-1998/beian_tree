from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
for module_name in list(sys.modules):
    if module_name == "src" or module_name.startswith("src."):
        del sys.modules[module_name]
sys.path.insert(0, str(ROOT))

import run_d2_pipeline as d2


def test_preprocess_flags_are_channel_specific_and_long_gaps_are_not_part_filled(tmp_path):
    idx = pd.date_range("2026-01-01", periods=12, freq="1min")
    frame = pd.DataFrame({ch: np.arange(12, dtype=float) for ch in d2.SCORED_CHANNELS}, index=idx)
    frame.loc[idx[2:4], "DO_1_1"] = np.nan
    frame.loc[idx[5:12], "DO_1_2"] = np.nan
    old_key = d2.CACHE_KEY
    d2.CACHE_KEY = "unit-test-channel-mask"
    try:
        flags = d2.compute_preprocess_flags(frame.copy(), frame)
    finally:
        d2.CACHE_KEY = old_key

    assert flags["DO_1_1"]["missing"].sum() == 2
    assert flags["DO_1_2"]["missing"].sum() == 7
    assert flags["DO_1_1"].loc[idx[2:4], "aligned_value"].notna().all()
    assert flags["DO_1_2"].loc[idx[5:12], "aligned_value"].isna().all()


def test_production_subscores_equal_modular_scorers():
    idx = pd.date_range("2026-01-02", periods=4, freq="1h")
    stats = pd.DataFrame({
        "missing_rate": [0.0, 0.01, 0.06, 0.2],
        "duplicate_rate": [0.0, 0.002, 0.02, 0.1],
        "out_of_order_rate": [0.0, 0.002, 0.02, 0.1],
        "irregular_rate": [0.0, 0.01, 0.06, 0.2],
        "info_empty_cov": [0.0, 0.05, 0.25, 0.6],
        "freeze_cand_cov": 0.0,
        "sensor_freeze_cov": 0.0,
        "low_iqr_cov": 0.0,
        "soft_rle_cov": 0.0,
        "soft_stasis_cov": 0.0,
        "floor_occupancy": 0.0,
        "resolution_limited": 0.0,
        "L_max_min": [0, 10, 90, 500],
        "gap_run_count": [0, 3, 20, 50],
        "P95_gap_min": [0, 5, 40, 150],
    }, index=idx)
    stats_all = {ch: stats.copy() for ch in d2.SCORED_CHANNELS}
    rl_all = {ch: pd.Series([0.0, 0.0, 0.5, 0.5], index=idx) for ch in d2.SCORED_CHANNELS}

    produced = d2.compute_subscores(stats_all, rl_all, {})[d2.SCORED_CHANNELS[0]]
    ti = d2.TemporalIntegrityScorer(d2._d2_cfg).score(stats)
    gs = d2.GapSeverityScorer(d2._d2_cfg).score(stats)
    fa, _ = d2.FreezeAvailabilityScorer(d2._d2_cfg).score(stats, rl_all[d2.SCORED_CHANNELS[0]])

    assert np.allclose(produced["Q_TI"], ti)
    assert np.allclose(produced["Q_GS"], gs)
    assert np.allclose(produced["Q_FA"], fa)


def test_qfa_uses_configured_six_hour_window(tmp_path):
    idx = pd.date_range("2026-01-01", periods=24 * 60, freq="1min")
    base = pd.DataFrame({
        "missing": 0,
        "duplicate": 0,
        "out_of_order": 0,
        "irregular_interval": 0,
        "qfa_unavailable": np.r_[np.ones(18 * 60), np.zeros(6 * 60)],
        "sensor_freeze": 0,
        "low_iqr_diagnostic": 0,
        "soft_rle_diagnostic": 0,
        "soft_stasis": 0,
        "floor_occupancy": 0,
        "resolution_limited": 0,
    }, index=idx)
    flags = {ch: base.copy() for ch in d2.SCORED_CHANNELS}
    old_cache, old_key = d2.CACHE, d2.CACHE_KEY
    d2.CACHE, d2.CACHE_KEY = tmp_path, "unit-test-qfa-six-hour"
    try:
        stats = d2.compute_window_stats(flags)
    finally:
        d2.CACHE, d2.CACHE_KEY = old_cache, old_key

    assert d2._d2_cfg.freeze_window.length == "6h"
    assert stats["DO_1_4"]["info_empty_cov"].iloc[-1] == 0.0


def test_response_loss_peers_are_same_position_and_process_floor_is_disabled():
    for sensor in d2._d2_cfg.sensors.values():
        if sensor.response_loss_enabled:
            assert sensor.response_loss_peers
            for peer_id in sensor.response_loss_peers:
                peer = d2._d2_cfg.sensors[peer_id]
                assert peer.sensor_type == sensor.sensor_type
                assert peer.position == sensor.position
                assert peer.process_zone == sensor.process_zone

    for sensor_id in ("DO_1_4", "DO_2_4"):
        sensor = d2._d2_cfg.sensors[sensor_id]
        assert sensor.availability_mode == "process_floor"
        assert not sensor.response_loss_enabled
        assert sensor.response_loss_peers == []


def test_response_loss_is_diagnostic_only_in_production_qfa():
    idx = pd.date_range("2026-01-02", periods=3, freq="1h")
    stats = pd.DataFrame({"info_empty_cov": [0.10, 0.10, 0.10]}, index=idx)
    response_loss = pd.Series([0.0, 0.5, 1.0], index=idx)
    score, main = d2.FreezeAvailabilityScorer(d2._d2_cfg).score(
        stats, response_loss, allow_response_loss=True
    )
    assert np.allclose(score, main)


def test_study_periods_are_blocked_and_external_site_is_deferred():
    design = d2._d2_cfg.study_design
    development = design.periods["development"]
    validation = design.periods["internal_validation"]
    terminal = design.periods["terminal_test"]
    assert pd.Timestamp(development.end) < pd.Timestamp(validation.start)
    assert pd.Timestamp(validation.end) < pd.Timestamp(terminal.start)
    assert design.external_site_validation["status"] == "deferred"
