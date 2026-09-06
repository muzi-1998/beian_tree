from __future__ import annotations

import copy
import json
from dataclasses import asdict

import numpy as np
import pandas as pd
import pytest

from d1_recovery_adapter import FIELDS, CooldownConfig, FrozenD1Recovery, score_recovery
from d1_scheduled_changepoints import scheduled_candidates
from src.state.auxiliary_modules import PELTBatchCalibrator


def inputs():
    idx = pd.date_range("2025-02-01", periods=120, freq="h")
    data = pd.DataFrame(0., index=idx, columns=FIELDS)
    data[FIELDS[:5]] = 5.
    data["Q_drift"] = 4.
    data["w1_norm"] = .5
    data.loc[idx[1], "step_confirmed"] = 1
    data.loc[idx[30], "step_confirmed"] = 1
    data.loc[idx[30:80], "Q_regime"] = 1.
    data.loc[idx[39], "Q_step"] = 2.5
    data.loc[idx[85:89], ["Q_drift", "resid_h", "peer_residual_z"]] = np.nan
    cfg = asdict(CooldownConfig(step_refractory_h=3, regime_refractory_h=3,
        min_event_separation_h=2, stable_window_h=4, max_baseline_pending_h=12,
        min_recovery_streak_h=3, max_recovery_window_h=5, max_soft_fail_h=1,
        max_missing_h=1, recovered_observation_h=3, observation_max_soft_fail_h=1,
        observation_max_missing_h=1, observation_max_total_nonpass_h=1, local_scale_floor=.1))
    return data, cfg


@pytest.mark.parametrize("step", [1, 24, 37])
def test_hour_day_irregular_chunks_preserve_recovery_and_json_checkpoint(step):
    data, cfg = inputs()
    expected, transitions = score_recovery("DO_1_1", data, [], cfg, {})
    stream = FrozenD1Recovery("DO_1_1", cfg, {})
    rows, emitted = [], []
    for start in range(0, len(data), step):
        chunk = data.iloc[start:start+step]
        new, events = stream.advance(chunk, [], observed_through=chunk.index[-1]+pd.Timedelta(hours=1))
        rows.append(new)
        emitted.extend(events)
        stream = FrozenD1Recovery("DO_1_1", cfg, {}, json.loads(json.dumps(stream.checkpoint())))
    pd.testing.assert_frame_equal(pd.concat(rows), expected, check_freq=False)
    assert emitted == transitions
    assert any(t.get("episode_outcome") == "direct_recovery" for t in emitted)
    assert any(t.get("episode_outcome") == "adapted_recovery" for t in emitted)
    assert expected.D1_for_validation.loc[data.index[85:89]].isna().all()
    assert not expected.detector_evidence_complete.loc[data.index[85:89]].any()


def test_checkpoint_tampering_and_config_change_are_rejected():
    data, cfg = inputs()
    stream = FrozenD1Recovery("DO_1_1", cfg, {})
    stream.advance(data.iloc[:20], [], observed_through=data.index[20])
    saved = stream.checkpoint()
    altered = copy.deepcopy(saved)
    altered["evidence"]["data"][0][0] = 1.
    with pytest.raises(ValueError, match="fingerprint"):
        FrozenD1Recovery("DO_1_1", cfg, {}, altered)
    with pytest.raises(ValueError, match="frozen"):
        FrozenD1Recovery("DO_1_1", {**cfg, "step_refractory_h": 4}, {}, saved)
    with pytest.raises(ValueError, match="frozen"):
        FrozenD1Recovery("DO_2_1", cfg, {}, saved)


def test_unknown_incomplete_duplicate_clock_and_retroactive_event_rejected():
    data, cfg = inputs()
    stream = FrozenD1Recovery("DO_1_1", cfg, {})
    with pytest.raises(ValueError, match="not closed"):
        stream.advance(data.iloc[:20], [], observed_through=data.index[19])
    stream.advance(data.iloc[:20], [], observed_through=data.index[20])
    with pytest.raises(ValueError, match="overlap"):
        stream.advance(data.iloc[19:30], [], observed_through=data.index[30])
    with pytest.raises(ValueError, match="retroactively"):
        stream.advance(data.iloc[20:30], [{"timestamp": data.index[1], "available_at": data.index[19],
                                           "signed_magnitude": 1.}], observed_through=data.index[30])


def test_scheduled_candidates_prefix_consistent_and_no_terminal_flush():
    idx = pd.date_range("2025-01-01", periods=1600, freq="h")
    series = pd.Series(np.sin(np.arange(1600)*.7)*.03, index=idx)
    series.iloc[790:] += 3.
    full = scheduled_candidates(series, neff_ratio=1.)
    assert full
    for stop in [720, 721, 850, 1056, 1200, 1500]:
        prefix = scheduled_candidates(series.iloc[:stop], neff_ratio=1.)
        assert prefix == [e for e in full if e["available_at"] <= idx[stop-1]]
    assert scheduled_candidates(series.iloc[:850], neff_ratio=1.) == []


def test_scheduled_clock_preserves_missing_as_explicit_valid_row_policy():
    idx = pd.date_range("2025-01-01", periods=1600, freq="h")
    series = pd.Series(np.sin(np.arange(1600)*.7)*.03, index=idx)
    series.iloc[600:620] = np.nan
    series.iloc[790:] += 3.
    full = scheduled_candidates(series, neff_ratio=1.)
    prefix = scheduled_candidates(series.iloc[:1200], neff_ratio=1.)
    assert prefix == [e for e in full if e["available_at"] <= idx[1199]]
    assert scheduled_candidates(series, neff_ratio=0.) == []


def test_native_terminal_flush_is_a_reproducible_candidate_time_counterexample():
    idx = pd.date_range("2025-01-01", periods=1600, freq="h")
    series = pd.Series(np.sin(np.arange(1600)*.7)*.03, index=idx)
    series.iloc[790:] += 3.
    native = PELTBatchCalibrator().calibrate_series(series)
    prefix = PELTBatchCalibrator().calibrate_series(series.iloc[:850])
    assert prefix and prefix != [e for e in native if e["available_at"] <= idx[849]]
    assert prefix[-1]["available_at"] == idx[849]


def test_delayed_pelt_arrivals_and_consumption_survive_checkpoint():
    data, cfg = inputs()
    data.loc[data.index[1:40], "Q_regime"] = 1.
    data.loc[data.index[8], "step_confirmed"] = 1.
    events = [{"timestamp": data.index[5], "available_at": data.index[8], "signed_magnitude": 3.}]
    expected, transitions = score_recovery("DO_1_1", data, events, cfg, {})
    stream = FrozenD1Recovery("DO_1_1", cfg, {})
    first, initial = stream.advance(data.iloc[:7], [], observed_through=data.index[7])
    stream = FrozenD1Recovery("DO_1_1", cfg, {}, json.loads(json.dumps(stream.checkpoint())))
    second, later = stream.advance(data.iloc[7:], events, observed_through=data.index[-1]+pd.Timedelta(hours=1))
    pd.testing.assert_frame_equal(pd.concat([first, second]), expected, check_freq=False)
    assert initial + later == transitions
    assert expected.pelt_segment_id.notna().any()
