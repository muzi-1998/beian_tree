from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
for module_name in list(sys.modules):
    if module_name == "src" or module_name.startswith("src."):
        del sys.modules[module_name]
sys.path.insert(0, str(ROOT))

from src.d2_availability.scorer import TemporalIntegrityScorer, piecewise_score
from src.utils.config_loader import load_config
from src.utils.timestamp_quality import classify_timestamp_series


CFG = load_config(ROOT / "configs", version="v2")


def test_raw_timestamp_classes_are_mutually_separated():
    timestamps = pd.Series(pd.to_datetime([
        "2026-01-01 00:00:00",
        "2026-01-01 00:01:00",
        "2026-01-01 00:01:00",
        "2026-01-01 00:00:30",
        "2026-01-01 00:01:40",
        "2026-01-01 00:04:00",
    ]))
    audited = classify_timestamp_series(timestamps)

    assert int(audited["regular"].sum()) == 1
    assert int(audited["duplicate"].sum()) == 1
    assert int(audited["out_of_order"].sum()) == 1
    assert int(audited["true_irregular"].sum()) == 1
    assert int(audited["gap_recovery"].sum()) == 1


def test_qti_conditionally_normalises_only_observed_components():
    idx = pd.DatetimeIndex([pd.Timestamp("2026-01-01 00:00:00")])
    stats = pd.DataFrame({
        "missing_rate": [0.06],
        "true_irregular_rate": [np.nan],
        "duplicate_rate": [np.nan],
        "out_of_order_rate": [np.nan],
        "source_gap_recovery_rate": [1.0],
    }, index=idx)
    scorer = TemporalIntegrityScorer(CFG)
    expected = piecewise_score(
        stats["missing_rate"], CFG.mapping.piecewise_breaks["Q_TI"]["missing_rate"]
    )

    assert np.allclose(scorer.score(stats), expected)
    assert np.allclose(scorer.observed_weight(stats), 0.65)


def test_piecewise_mapping_is_continuous_at_previous_hard_cliff():
    breaks = CFG.mapping.piecewise_breaks["Q_TI"]["missing_rate"]
    b3, b4 = breaks[3], breaks[4]
    epsilon = 1e-9
    values = pd.Series([b3 - epsilon, b3, b3 + epsilon, b4])
    scores = piecewise_score(values, breaks)

    assert abs(scores.iloc[0] - scores.iloc[2]) < 1e-6
    assert np.isclose(scores.iloc[1], 2.0)
    assert np.isclose(scores.iloc[3], 1.0)


def test_gap_recovery_is_not_a_qti_component():
    idx = pd.date_range("2026-01-01", periods=2, freq="1h")
    stats = pd.DataFrame({
        "missing_rate": 0.0,
        "true_irregular_rate": 0.0,
        "duplicate_rate": 0.0,
        "out_of_order_rate": 0.0,
        "source_gap_recovery_rate": [0.0, 1.0],
    }, index=idx)
    score = TemporalIntegrityScorer(CFG).score(stats)
    assert np.isclose(score.iloc[0], score.iloc[1])
