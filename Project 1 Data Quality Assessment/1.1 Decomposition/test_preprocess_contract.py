from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src.data.preprocess import FLAG, align_min


def test_align_min_fills_only_complete_short_runs():
    idx = pd.date_range("2026-01-01", periods=12, freq="1min")
    values = pd.Series(np.arange(12, dtype=float), index=idx)
    values.iloc[2:4] = np.nan
    values.iloc[6:11] = np.nan

    aligned, flags = align_min(values.to_frame("DO_1_1"), short_gap_min=3)

    assert aligned.iloc[2:4, 0].notna().all()
    assert (flags.iloc[2:4, 0] == FLAG["SHORT"]).all()
    assert aligned.iloc[6:11, 0].isna().all()
    assert (flags.iloc[6:11, 0] == FLAG["LONG"]).all()


def test_align_min_keeps_expected_horizon_as_missing():
    idx = pd.date_range("2026-01-01 00:00", periods=3, freq="1min")
    frame = pd.DataFrame({"DO_1_1": [1.0, 1.1, 1.2]}, index=idx)

    aligned, flags = align_min(
        frame, expected_start="2026-01-01 00:00", expected_end="2026-01-01 00:05")

    assert len(aligned) == 6
    assert aligned.iloc[-3:, 0].isna().all()
    assert (flags.iloc[-3:, 0] == FLAG["LONG"]).all()
