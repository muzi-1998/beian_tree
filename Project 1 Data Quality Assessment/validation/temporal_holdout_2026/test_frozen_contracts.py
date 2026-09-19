from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from frozen_context import FrozenContext
from frozen_whitener import FrozenWhitener
from causal_gap_evidence import causal_gap_evidence
from causal_change_points import causal_change_timeline
from information_time import interval_contract, select_known
from runtime import START, assert_fit_before_holdout, historical_only, require_opening_gate


def model_asset(garch):
    return {"route": "arma", "ar": [0.6, -0.1], "ma": [0.2], "intercept": 2.0,
            "garch": {"omega": 0.1, "alpha": [0.1], "beta": [0.8]} if garch else None,
            "initial_variance": 1.0, "fixed_non_garch_variance": 1.3}


@pytest.mark.parametrize("garch", [True, False])
def test_prefix_and_chunk_with_checkpoint_and_missing(garch):
    values = np.random.default_rng(905).normal(size=1200)
    values[597:606] = np.nan
    asset = model_asset(garch)
    full = FrozenWhitener(asset).transform(values)
    prefix = FrozenWhitener(asset).transform(values[:600])
    np.testing.assert_allclose(prefix, full[:600], atol=1e-12, rtol=0)
    stream = FrozenWhitener(asset)
    first = stream.transform(values[:603])
    resumed = FrozenWhitener(asset, stream.checkpoint())
    second = resumed.transform(values[603:])
    np.testing.assert_allclose(np.r_[first, second], full, atol=1e-12, rtol=0)
    assert np.isnan(full[597:606]).all()


def test_context_never_fits_future_and_rejects_feature_order():
    model = FrozenContext.from_dict({
        "feature_names": ["flow", "hour"], "fill_values": [1., 2.],
        "scaler_mean": [1., 2.], "scaler_scale": [2., 3.],
        "cluster_centers": [[0., 0.], [1., 1.]], "temperature": 1.,
        "likelihood_temperature_multiplier": 0.25, "ood_threshold": 4.,
    })
    values = pd.DataFrame({"flow": [1., np.nan, 5.], "hour": [2., 3., 4.]})
    full, _ = model.predict(values)
    prefix, _ = model.predict(values.iloc[:2])
    np.testing.assert_array_equal(prefix, full[:2])
    with pytest.raises(ValueError, match="Feature order"):
        model.predict(values[["hour", "flow"]])


def test_no_implicit_opening_when_gate_missing(tmp_path):
    with pytest.raises(RuntimeError, match="sealed"):
        require_opening_gate(tmp_path / "missing.json")


def test_component_passes_do_not_override_explicit_holdout_seal(tmp_path):
    import json
    gate = {key: "passed" for key in ["historical_replay", "prefix_invariance", "chunk_equivalence",
                                      "time_contract", "unknown_evidence", "asset_closure"]}
    gate["performance_opening_allowed"] = False
    path = tmp_path / "gate.json"
    path.write_text(json.dumps(gate))
    with pytest.raises(RuntimeError, match="sealed"):
        require_opening_gate(path)


def test_reject_future_in_fitted_asset():
    with pytest.raises(ValueError, match="cutoff"):
        assert_fit_before_holdout(pd.DatetimeIndex([START]), START - pd.Timedelta(minutes=1))


def test_history_boundary_is_exclusive():
    frame = pd.DataFrame({"x": [1., 999.]}, index=[START - pd.Timedelta(minutes=1), START])
    assert historical_only(frame).x.tolist() == [1.]


def test_bad_checkpoint_is_rejected():
    with pytest.raises(ValueError, match="checkpoint"):
        FrozenWhitener(model_asset(True), {"zi": [], "e2": [0], "s2": [1]})


def test_gap_evidence_never_completes_an_open_run_at_array_end():
    index = pd.date_range("2026-02-01", periods=70, freq="min")
    values = pd.Series(1., index=index)
    values.iloc[20:52] = np.nan
    prefix = causal_gap_evidence(values.iloc[:22])
    full = causal_gap_evidence(values)
    pd.testing.assert_frame_equal(prefix, full.iloc[:22])
    assert prefix.completed_gap_length_known_now.isna().all()
    assert not prefix.long_gap_asof.any()
    assert not full.long_gap_asof.iloc[24]
    assert full.long_gap_asof.iloc[25]
    assert full.completed_gap_length_known_now.iloc[52] == 32
    assert full.P95_completed_gap_24h_asof.iloc[51] == 0
    assert full.P95_completed_gap_24h_asof.iloc[52] == 32


def test_missing_clock_is_not_silently_a_shorter_gap():
    s = pd.Series([1., np.nan], index=pd.to_datetime(["2026-02-01 00:00", "2026-02-01 00:02"]))
    with pytest.raises(ValueError, match="grid"):
        causal_gap_evidence(s)


def test_change_points_use_only_candidates_known_at_decision_time():
    idx = pd.date_range("2026-02-01", periods=120, freq="h")
    t = np.arange(120)
    s = pd.Series(.1*np.sin(t*1.7) + np.where(t < 42, 0., np.where(t < 60, 1., 3.)), index=idx)
    kwargs = dict(auxiliary_window_days=7, adjacent_segment_hours=12, candidate_step_hours=6,
                  ks_stat_min=.35, pvalue_max=.01, min_valid_fraction=.8)
    full = causal_change_timeline(s, idx[24:], **kwargs)
    prefix = causal_change_timeline(s.iloc[:60], idx[24:61], **kwargs)
    pd.testing.assert_frame_equal(prefix, full.loc[prefix.index])
    assert pd.isna(full.loc[idx[53], "cp_time"])
    assert full.loc[idx[54], "cp_time"] == idx[42]
    # Independent day-sized calls retain the fixed scan origin and history.
    pieces = [causal_change_timeline(s.loc[s.index < stop], idx[(idx >= start) & (idx < stop)], **kwargs)
              for start, stop in [(idx[24], idx[48]), (idx[48], idx[72]), (idx[72], idx[96]),
                                  (idx[96], idx[-1] + pd.Timedelta(hours=1))]]
    pd.testing.assert_frame_equal(pd.concat(pieces), full)


def test_D5_snapshot_label_is_not_available_at():
    row = interval_contract("D5", pd.DatetimeIndex(["2026-04-14 00:00"])).iloc[0]
    assert row.base_available_at == pd.Timestamp("2026-04-14 00:10")
    assert row.interval_end_exclusive - row.interval_start == pd.Timedelta(hours=24)


def test_D3_gate_cannot_be_applied_before_window_closes():
    row = interval_contract("D3", pd.DatetimeIndex(["2026-04-14 02:00"])).iloc[0]
    assert row.interval_start == pd.Timestamp("2026-04-14")
    evidence = pd.DataFrame({"gate": ["Fail"], "available_at": [row.base_available_at],
                             "valid_until": [row.base_available_at + pd.Timedelta(hours=2)]})
    assert select_known(evidence, pd.Timestamp("2026-04-14 01:00")).empty
    assert select_known(evidence, pd.Timestamp("2026-04-14 02:00")).gate.tolist() == ["Fail"]
    assert select_known(evidence, pd.Timestamp("2026-04-14 04:00")).empty


def test_unknown_availability_cannot_be_silently_backfilled():
    with pytest.raises(ValueError, match="Explicit"):
        select_known(pd.DataFrame({"score": [5.]}), pd.Timestamp("2026-04-14"))
