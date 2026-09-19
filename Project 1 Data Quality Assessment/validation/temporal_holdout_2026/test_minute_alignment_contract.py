from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from minute_alignment_contract import BoundedMinuteAligner, align_bounded

RANGES = {"DO_1_4": [-.5, 12.], "ORP_1_3": [-550., 550.]}


def raw_data():
    idx = pd.date_range("2026-02-01 23:45", periods=100, freq="min")
    raw = pd.DataFrame({"DO_1_4": .05+np.arange(100)*.001,
                        "ORP_1_3": np.arange(100)*.1}, index=idx)
    raw.iloc[7:10] = np.nan
    raw.iloc[24:54] = np.nan
    raw.iloc[65] = 999.
    raw.iloc[64] = np.nan
    raw.iloc[66:68] = np.nan
    raw.iloc[85:87] = np.nan
    return raw


@pytest.mark.parametrize("block", [1, 7, 24, 100])
def test_bounded_delay_prefix_day_boundary_and_checkpoint(block):
    raw = raw_data()
    original = raw.copy()
    expected, expected_flags = align_bounded(raw, RANGES)
    stream = BoundedMinuteAligner(RANGES)
    parts, flags = [], []
    for start in range(0, len(raw), block):
        chunk = raw.iloc[start:start+block]
        values, status, available = stream.advance(chunk)
        assert (available <= chunk.index[-1]).all()
        parts.append(values)
        flags.append(status)
        saved = json.loads(json.dumps(stream.checkpoint(), allow_nan=False))
        stream = BoundedMinuteAligner(RANGES, checkpoint=saved)
    pd.testing.assert_frame_equal(pd.concat(parts), expected.iloc[:-3], check_freq=False)
    pd.testing.assert_frame_equal(pd.concat(flags), expected_flags.iloc[:-3], check_freq=False)
    pd.testing.assert_frame_equal(raw, original)


def test_range_invalid_cannot_split_a_long_gap_into_artificial_short_gaps():
    raw = raw_data()
    values, flags = align_bounded(raw, RANGES)
    assert values.iloc[64:68].isna().all().all()
    assert flags.iloc[65].eq(7).all()
    assert flags.iloc[[64, 66, 67]].eq(2).all().all()
    assert flags.iloc[7:10].eq(1).all().all()


def test_future_tail_cannot_change_emitted_prefix_and_no_end_flush():
    raw = raw_data()
    future = raw.copy()
    future.iloc[50:] = .08
    a, fa, _ = BoundedMinuteAligner(RANGES).advance(raw.iloc[:50])
    b, fb, _ = BoundedMinuteAligner(RANGES).advance(future)
    pd.testing.assert_frame_equal(a, b.loc[a.index])
    pd.testing.assert_frame_equal(fa, fb.loc[fa.index])
    assert a.index[-1] == raw.index[46]
    assert a.iloc[24:].isna().all().all()


def test_minute_checkpoint_policy_and_nonadjacent_chunk_fail_closed():
    raw = raw_data()
    aligner = BoundedMinuteAligner(RANGES)
    aligner.advance(raw.iloc[:40])
    with pytest.raises(ValueError, match="Checkpoint"):
        BoundedMinuteAligner(RANGES, short_gap_min=2, checkpoint=aligner.checkpoint())
    with pytest.raises(ValueError, match="adjacent"):
        aligner.advance(raw.iloc[41:])
