from __future__ import annotations

import numpy as np
import pandas as pd

from src.event_arbitration import extract_events
from src.innovation import fit_ar1_innovation, minute_causal_innovation
from src.multiscale_glr import multiscale_glr
from src.validation import _separated_candidates


def test_minute_innovation_is_past_only() -> None:
    index = pd.date_range("2026-01-01", periods=2000, freq="min")
    baseline = pd.Series(np.sin(np.arange(len(index)) / 100), index=index)
    changed = baseline.copy()
    changed.iloc[1500:] += 10
    kwargs = dict(
        location_window=120,
        scale_window=360,
        guard=5,
        min_location=60,
        min_scale=120,
        resolution_floor_multiplier=1.5,
        fixed_resolution=0.001,
        fixed_scale_floor=0.01,
    )
    original = minute_causal_innovation(baseline, **kwargs)
    injected = minute_causal_innovation(changed, **kwargs)
    pd.testing.assert_series_equal(original.loc[:index[1499], "innovation"], injected.loc[:index[1499], "innovation"])


def test_frozen_ar1_transform_detects_shift() -> None:
    rng = np.random.default_rng(7)
    index = pd.date_range("2025-01-01", periods=600, freq="h")
    values = np.zeros(len(index))
    for position in range(1, len(values)):
        values[position] = 0.6 * values[position - 1] + rng.normal(scale=0.5)
    series = pd.Series(values, index=index, name="DO_1_1")
    eligible = pd.Series(True, index=index)
    model = fit_ar1_innovation(series.iloc[:400], eligible.iloc[:400], phi_clip=0.95)
    shifted = series.copy()
    shifted.iloc[450:475] += 3 * model.scale
    score = multiscale_glr(model.transform(shifted), [1, 2, 4, 8])["glr_score"]
    assert score.iloc[450:475].max() > score.iloc[350:400].quantile(0.99)


def test_event_merge_contract() -> None:
    index = pd.date_range("2026-01-01", periods=20, freq="min")
    score = pd.Series(0.0, index=index)
    score.iloc[[2, 3, 8]] = 5.0
    eligible = pd.Series(True, index=index)
    events = extract_events(score, threshold=4.0, eligible=eligible, merge_gap=pd.Timedelta(minutes=5))
    assert len(events) == 1
    assert events.iloc[0]["onset"] == index[2]


def test_onset_separation_contract() -> None:
    candidates = pd.date_range("2026-01-01", periods=72, freq="h")
    used = [pd.Timestamp("2026-01-02 00:00")]
    available = _separated_candidates(candidates, used, pd.Timedelta(hours=24))
    assert pd.Timestamp("2026-01-01 00:00") in available
    assert pd.Timestamp("2026-01-03 00:00") in available
    assert pd.Timestamp("2026-01-02 00:00") not in available
    assert pd.Timestamp("2026-01-02 23:00") not in available
