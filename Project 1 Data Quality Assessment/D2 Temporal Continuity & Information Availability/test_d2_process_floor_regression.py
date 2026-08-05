from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src.d2_availability.process_floor import route_availability_evidence
from src.utils.config_loader import load_config


def _run(
    values: list[float | None],
    *,
    long_gap_positions: tuple[int, ...] = (),
) -> pd.DataFrame:
    idx = pd.date_range("2026-01-01", periods=len(values), freq="1min")
    s = pd.Series(values, index=idx, dtype=float)
    missing = s.isna()
    observed_diff = s.diff().abs().fillna(1.0)
    same = observed_diff.lt(0.01) & ~missing & ~missing.shift(1, fill_value=True)
    groups = same.ne(same.shift(fill_value=False)).cumsum()
    hard_rle = same.astype(int) * (same.groupby(groups).cumcount() + 1)
    q75 = s.rolling("30min", min_periods=15).quantile(0.75)
    q25 = s.rolling("30min", min_periods=15).quantile(0.25)
    iqr = (q75 - q25).fillna(1.0)
    long_gap = pd.Series(False, index=idx)
    if long_gap_positions:
        long_gap.iloc[list(long_gap_positions)] = True
    return route_availability_evidence(
        aligned_value=s,
        missing=missing,
        long_gap=long_gap,
        rle_run_min=hard_rle,
        hard_rle_run_min=hard_rle,
        rolling_iqr=iqr,
        low_iqr_threshold=0.02,
        lenient_rle_min=3,
        hard_rle_min=15,
        availability_mode="process_floor",
        process_floor_threshold=0.20,
    )


def test_true_low_oxygen_floor_is_resolution_limited_not_unavailable():
    out = _run(([0.00, 0.01, 0.00, 0.02] * 20))
    assert out["floor_occupancy"].iloc[-30:].all()
    assert out["resolution_limited"].iloc[-30:].all()
    assert not out["sensor_freeze"].any()
    assert not out["qfa_unavailable"].any()


def test_digital_lock_triggers_hard_sensor_freeze_after_fifteen_minutes():
    out = _run([0.00] * 30)
    assert out["sensor_freeze"].iloc[-1]
    assert out["qfa_unavailable"].iloc[-1]
    assert not out["sensor_freeze"].iloc[10]


def test_low_oxygen_small_fluctuations_do_not_trigger_freeze():
    out = _run(([0.04, 0.05, 0.04, 0.06] * 20))
    assert out["resolution_limited"].iloc[-20:].all()
    assert not out["sensor_freeze"].any()
    assert not out["qfa_unavailable"].any()


def test_normal_response_recovers_immediately_after_leaving_floor():
    values = [0.00] * 20 + ([0.32, 0.38, 0.35, 0.42] * 10)
    out = _run(values)
    assert out["sensor_freeze"].iloc[18]
    assert not out["sensor_freeze"].iloc[20]
    assert not out["floor_occupancy"].iloc[-20:].any()
    assert not out["qfa_unavailable"].iloc[-20:].any()


def test_missing_and_long_gap_are_not_exempted_by_process_floor():
    values = (
        [0.04, 0.05] * 4
        + [None] * 6
        + [0.04, 0.05] * 5
        + [0.05, 0.06] * 5
    )
    out = _run(values, long_gap_positions=tuple(range(8, 14)))
    assert out["continuity_unavailable"].iloc[8:14].all()
    assert all(pd.isna(values[index]) for index in range(8, 14))
    assert not out["hard_availability_loss"].iloc[8:14].any()
    assert not out["qfa_unavailable"].iloc[8:14].any()
    assert not out["sensor_freeze"].iloc[8:14].any()


def _run_standard(values: list[float | None]) -> pd.DataFrame:
    idx = pd.date_range("2026-01-01", periods=len(values), freq="1min")
    s = pd.Series(values, index=idx, dtype=float)
    missing = s.isna()
    observed_diff = s.diff().abs().fillna(1.0)
    same = observed_diff.lt(0.5) & ~missing & ~missing.shift(1, fill_value=True)
    groups = same.ne(same.shift(fill_value=False)).cumsum()
    rle = same.astype(int) * (same.groupby(groups).cumcount() + 1)
    q75 = s.rolling("30min", min_periods=15).quantile(0.75)
    q25 = s.rolling("30min", min_periods=15).quantile(0.25)
    iqr = (q75 - q25).fillna(2.0)
    return route_availability_evidence(
        aligned_value=s,
        missing=missing,
        long_gap=pd.Series(False, index=idx),
        rle_run_min=rle,
        hard_rle_run_min=rle,
        rolling_iqr=iqr,
        low_iqr_threshold=1.0,
        lenient_rle_min=3,
        hard_rle_min=15,
        availability_mode="standard",
    )
def test_both_post_anoxic_do_channels_use_process_floor_route():
    cfg = load_config(ROOT / "configs", version="v1")
    for sensor_id in ("DO_1_4", "DO_2_4"):
        sensor = cfg.sensors[sensor_id]
        assert sensor.availability_mode == "process_floor"
        assert sensor.process_zone == "post_anoxic"
        assert sensor.process_floor_threshold == 0.20
        assert sensor.response_loss_enabled is False


def test_standard_soft_stasis_is_diagnostic_not_production_unavailability():
    out = _run_standard(([100.0, 100.5, 100.0, 100.5] * 10))
    assert out["soft_stasis"].iloc[-20:].all()
    assert not out["sensor_freeze"].any()
    assert not out["qfa_unavailable"].any()


def test_standard_hard_stasis_remains_production_unavailability():
    out = _run_standard([100.0] * 30)
    assert out["sensor_freeze"].iloc[-1]
    assert out["qfa_unavailable"].iloc[-1]
    assert not out["qfa_unavailable"].iloc[10]
