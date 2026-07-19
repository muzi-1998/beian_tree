from __future__ import annotations

import numpy as np
import pandas as pd

from src.calibration.step_injection import (
    StepCalibrationConfig,
    build_injection_library,
    confirmation_gate,
    injection_library_sha256,
    logistic_quality,
)


def test_logistic_midpoint_and_monotonicity():
    score = logistic_quality([0.35, 0.55, 0.75], k=16.0, x0=0.55)
    assert score[1] == 3.0
    assert np.all(np.diff(score) < 0)


def test_confirmation_gate_keeps_less_severe_score_when_active():
    q24 = np.array([4.0, 2.0, 1.5])
    q36 = np.array([1.0, 3.0, 1.8])
    result = confirmation_gate(q24, q36)
    assert result.tolist() == [4.0, 3.0, 1.8]


def test_injection_library_excludes_non_iid_scoring_modes():
    index = pd.date_range("2026-01-01", periods=240, freq="h")
    rng = np.random.default_rng(13)
    routed = pd.DataFrame({
        "iid_sensor": rng.normal(size=240),
        "ar_sensor": rng.normal(size=240),
    }, index=index)
    normal = {channel: pd.Series(True, index=index) for channel in routed}
    cfg = StepCalibrationConfig(
        window_h=120,
        event_h=48,
        evaluation_start_h=6,
        evaluation_end_h=36,
        windows_per_channel=1,
        amplitudes_sigma=(0.0, 1.0),
    )
    library = build_injection_library(
        routed,
        normal,
        {"iid_sensor": 1.0, "ar_sensor": 0.01},
        {"iid_sensor": "iid", "ar_sensor": "autocorr_aware"},
        cfg,
    )
    assert set(library["sensor_id"]) == {"iid_sensor"}
    assert set(library["scoring_mode"]) == {"iid"}
    assert injection_library_sha256(library) == injection_library_sha256(
        library.sample(frac=1.0, random_state=2)
    )
