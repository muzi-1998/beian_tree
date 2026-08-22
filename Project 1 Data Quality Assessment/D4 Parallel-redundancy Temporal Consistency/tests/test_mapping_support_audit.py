from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd


D4_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(D4_ROOT / "src"))

from d4.mapping_support_audit import (  # noqa: E402
    build_mapping_lookup,
    classify_mapping_scope,
    extract_low_tail_events,
)


def test_mapping_scope_classification_is_fail_closed() -> None:
    assert classify_mapping_scope("variable_regime_public") == "exact"
    assert classify_mapping_scope("variable_public_fallback") == "variable_fallback"
    assert classify_mapping_scope("global_public_fallback") == "global_fallback"
    assert classify_mapping_scope("unexpected") == "insufficient"


def test_mapping_lookup_requires_consistent_three_subscore_strata() -> None:
    frame = pd.DataFrame(
        {
            "variable": ["DO"] * 3,
            "regime_id": [0.0] * 3,
            "subscore": ["Q_dist", "Q_trend", "Q_var"],
            "mapping_role": ["production"] * 3,
            "mapping_scope": ["variable_regime_public"] * 3,
            "calibration_quality": ["adequate"] * 3,
            "mapping_evidence_quality": ["admitted_supported_precision"] * 3,
            "independent_blocks": [7] * 3,
            "exact_independent_blocks": [7] * 3,
            "sample_size": [120] * 3,
            "exact_stratum_size": [120] * 3,
            "percentile_precision_grade": ["supported"] * 3,
            "mapping_id": ["MAP-1", "MAP-2", "MAP-3"],
        }
    )
    lookup = build_mapping_lookup(frame)
    assert lookup.iloc[0]["mapping_support_class"] == "exact"
    assert lookup.iloc[0]["calibration_independent_blocks"] == 7
    assert lookup.iloc[0]["subscore_count"] == 3


def test_events_break_at_resampled_support_and_time_boundaries() -> None:
    frame = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(
                [
                    "2026-01-01 00:00",
                    "2026-01-01 01:00",
                    "2026-01-01 05:00",
                    "2026-01-01 06:00",
                ]
            ),
            "pair_id": ["PAIR_DO11"] * 4,
            "variable": ["DO"] * 4,
            "phase_id": ["development"] * 4,
            "mapping_support_class": [
                "exact",
                "exact",
                "variable_fallback",
                "variable_fallback",
            ],
            "usable_for_D4": [True] * 4,
            "D4_raw": [2.5, 2.4, 2.3, 2.2],
        }
    )
    events = extract_low_tail_events(frame)
    assert events["duration_h"].tolist() == [2, 2]
    assert events["mapping_support_class"].tolist() == [
        "exact",
        "variable_fallback",
    ]
