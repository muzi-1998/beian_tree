from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shared_data_foundation.context import fit_context, pair_support
from shared_data_foundation.inference import infer_context


def test_frozen_inference_matches_training_and_future_prefix():
    index = pd.date_range("2025-08-01", periods=9*24*60, freq="min")
    rng = np.random.default_rng(7)
    raw = pd.DataFrame(rng.normal(size=(len(index), 2)), index=index, columns=["DO_1_1", "DO_2_1"])
    state, asset = fit_context(raw, "2025-08-07", fit_start="2025-08-01")
    actual = infer_context(raw, asset)
    pd.testing.assert_frame_equal(state, actual)
    prefix = infer_context(raw.loc[raw.index < "2025-08-08"], asset)
    pd.testing.assert_frame_equal(prefix, actual.loc[prefix.index])
    assert asset["D1_D2_scores_consumed"] is False
    assert asset["D5_model_replaced"] is False


def test_observed_hard_stasis_is_not_missing_support():
    index = pd.date_range("2025-08-01", periods=48*60, freq="min")
    raw = pd.DataFrame({"DO_1_4": .01, "DO_2_4": .02}, index=index)
    out = pair_support(raw, "DO_1_4", "DO_2_4")
    assert out.iloc[-1].raw_common_fraction_24h == 1
    assert out.iloc[-1].raw_supported_hours_fraction == 1
    assert out.iloc[-1].raw_complete_window
