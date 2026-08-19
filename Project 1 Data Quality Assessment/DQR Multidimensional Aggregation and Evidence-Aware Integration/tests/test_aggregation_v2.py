from __future__ import annotations

import numpy as np
import pandas as pd

from dqr_aggregation.common import OUTPUT_ROOT, expand_end_exclusive_windows, load_config
from dqr_aggregation.pipeline import resolve_release_status, verify_frozen_inputs


def test_d3_end_exclusive_two_hour_window_maps_to_preceding_hours() -> None:
    source = pd.DataFrame(
        {
            "timestamp": [pd.Timestamp("2026-01-01 02:00")],
            "sensor_id": ["DO_1_1"],
            "window_min": [120],
            "D3_gate_status": ["Warn"],
        }
    )
    expanded = expand_end_exclusive_windows(source)
    assert expanded["timestamp"].tolist() == [
        pd.Timestamp("2026-01-01 00:00"),
        pd.Timestamp("2026-01-01 01:00"),
    ]
    assert expanded["source_window_end_exclusive"].nunique() == 1


def test_frozen_input_registry_is_current() -> None:
    registry = verify_frozen_inputs(load_config())
    assert registry["sha256_match"].all()


def test_released_node_and_pair_formulas() -> None:
    node = pd.read_parquet(OUTPUT_ROOT / "data" / "DQR_node_hourly.parquet")
    pair = pd.read_parquet(OUTPUT_ROOT / "data" / "DQR_pair_hourly.parquet")
    valid = node["Q_node_full"].notna()
    expected = node.loc[valid, ["D1_total", "D2_total", "D5_report_score"]].mean(axis=1)
    assert np.allclose(node.loc[valid, "Q_node_full"], expected, rtol=0, atol=1e-12)
    valid = pair["Q_pair_full"].notna()
    expected = pair.loc[
        valid, ["left_Q_node_full", "right_Q_node_full", "D4_raw"]
    ].mean(axis=1)
    assert np.allclose(pair.loc[valid, "Q_pair_full"], expected, rtol=0, atol=1e-12)


def test_dimension_roles_and_missing_semantics() -> None:
    frame = pd.read_parquet(OUTPUT_ROOT / "data" / "DQR_dimension_long.parquet")
    assert frame.loc[frame["dimension"].eq("D3"), "score_1to5"].isna().all()
    assert frame.loc[frame["dimension"].eq("D4"), "object_type"].eq("pair").all()
    missing_d5 = frame["dimension"].eq("D5") & ~frame["report_eligible"]
    assert frame.loc[missing_d5, "score_1to5"].isna().all()


def test_d3_gate_status_has_fail_closed_precedence() -> None:
    quality = pd.Series([4.2, 4.2, 4.2, 4.2, np.nan, np.nan])
    gate = pd.Series(["Pass", "Warn", "Fail", "NotEvaluated", "Fail", "Pass"])
    coverage = pd.Series(["full", "full", "full", "full", "limited", "limited"])
    status = resolve_release_status(quality, gate, coverage)
    assert status.tolist() == [
        "full_evidence",
        "gate_warn",
        "gate_fail",
        "gate_not_evaluated",
        "gate_fail",
        "not_evaluable",
    ]


def test_d3_gate_does_not_overwrite_diagnostic_quality() -> None:
    quality = pd.Series([2.4, np.nan], name="Q")
    original = quality.copy(deep=True)
    resolve_release_status(
        quality,
        pd.Series(["Fail", "Fail"]),
        pd.Series(["full", "limited"]),
    )
    pd.testing.assert_series_equal(quality, original)
