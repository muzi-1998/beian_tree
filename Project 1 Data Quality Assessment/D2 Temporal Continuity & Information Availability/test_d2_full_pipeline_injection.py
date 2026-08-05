from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src.d2_availability.challenge import evaluate_raw_series
from src.utils.config_loader import load_config


CFG = load_config(ROOT / "configs", version="v2")
START = pd.Timestamp("2026-01-01 00:00")
END = pd.Timestamp("2026-01-03 23:59")


def _baseline(sensor_id: str = "DO_1_1") -> pd.DataFrame:
    index = pd.date_range(START, END, freq="1min")
    phase = np.arange(len(index), dtype=float)
    if sensor_id.startswith("ORP"):
        value = (-120 + 18 * np.sin(2 * np.pi * phase / 360)
                 + 3 * np.sin(phase / 19) + (phase % 2) * 1.5)
        value = np.round(value * 2) / 2
    else:
        value = (1.8 + 0.35 * np.sin(2 * np.pi * phase / 360)
                 + 0.05 * np.sin(phase / 17) + (phase % 2) * 0.03)
        value = np.round(value, 2)
    return pd.DataFrame({"timestamp": index, "value": value})


def test_timestamp_faults_are_counted_before_sorting_and_alignment():
    raw = _baseline()
    duplicate = raw.iloc[[1800]].copy()
    challenged = pd.concat([raw.iloc[:1801], duplicate, raw.iloc[1801:]], ignore_index=True)
    swap = challenged.iloc[[2000, 2001]].copy()
    challenged.iloc[2000] = swap.iloc[1]
    challenged.iloc[2001] = swap.iloc[0]
    result = evaluate_raw_series(
        challenged, CFG, expected_start=START, expected_end=END
    )
    assert result["audit"]["duplicate"].sum() >= 1
    assert result["audit"]["out_of_order"].sum() >= 1


def test_thirty_minute_gap_penalises_continuity_but_not_hard_availability():
    raw = _baseline()
    onset = pd.Timestamp("2026-01-02 12:00")
    challenged = raw.loc[
        ~raw["timestamp"].between(onset, onset + pd.Timedelta(minutes=29))
    ]
    result = evaluate_raw_series(
        challenged, CFG, expected_start=START, expected_end=END
    )
    scored = result["scores"].loc[onset.ceil("h"):onset + pd.Timedelta(hours=6)]
    assert scored["Q_GS"].min() < 5.0
    assert scored["Q_TI"].min() < 5.0
    assert scored["Q_HA"].dropna().eq(5.0).all()
    assert not result["routed"].loc[onset:onset + pd.Timedelta(minutes=29), "hard_availability_loss"].any()


def test_thirty_minute_observed_stasis_penalises_qha_only_and_recovers():
    raw = _baseline()
    onset = pd.Timestamp("2026-01-02 12:00")
    mask = raw["timestamp"].between(onset, onset + pd.Timedelta(minutes=29))
    raw.loc[mask, "value"] = float(raw.loc[mask, "value"].iloc[0])
    result = evaluate_raw_series(raw, CFG, expected_start=START, expected_end=END)
    challenged = result["scores"].loc[onset.ceil("h"):onset + pd.Timedelta(hours=6)]
    assert challenged["Q_HA"].min() < 5.0
    assert challenged["Q_TI"].dropna().eq(5.0).all()
    assert challenged["Q_GS"].dropna().eq(5.0).all()
    assert not result["routed"].loc[
        onset + pd.Timedelta(minutes=30):, "hard_availability_loss"
    ].any()


def test_process_floor_small_variation_is_not_hard_stasis():
    raw = _baseline("DO_1_4")
    onset = pd.Timestamp("2026-01-02 12:00")
    mask = raw["timestamp"].between(onset, onset + pd.Timedelta(hours=2))
    raw.loc[mask, "value"] = np.resize([0.04, 0.05, 0.04, 0.06], int(mask.sum()))
    result = evaluate_raw_series(
        raw, CFG, expected_start=START, expected_end=END, sensor_id="DO_1_4"
    )
    route = result["routed"].loc[mask.to_numpy()]
    assert route["resolution_limited"].any()
    assert not route["hard_availability_loss"].any()
