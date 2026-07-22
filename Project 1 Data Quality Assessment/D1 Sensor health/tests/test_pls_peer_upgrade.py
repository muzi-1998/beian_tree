from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd

from src.validation.pls_peer_upgrade import (
    PLSPeerValidationConfig,
    _has_sustained_alarm,
    _moving_block_bootstrap_median,
    validate_do24_peer_upgrade,
)


def _synthetic_frame(seed: int = 12, n: int = 24 * 90) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    process = np.cumsum(rng.normal(scale=0.08, size=n))
    second = process + rng.normal(scale=0.20, size=n)
    direct = 0.85 * process + rng.normal(scale=0.24, size=n)
    target = 0.65 * direct + 0.35 * second + rng.normal(scale=0.08, size=n)
    return pd.DataFrame(
        {"DO_2_2": second, "DO_2_3": direct, "DO_2_4": target},
        index=pd.date_range("2025-01-01", periods=n, freq="h"),
    )


def test_sustained_alarm_requires_three_consecutive_hours():
    assert not _has_sustained_alarm(np.array([3.0, 1.0, 3.0]), 2.5, 3)
    assert _has_sustained_alarm(np.array([0.0, 3.0, 3.0, 3.0]), 2.5, 3)


def test_moving_block_bootstrap_is_seed_reproducible():
    values = np.array([1.0, 2.0, 3.0, 4.0])
    first = _moving_block_bootstrap_median(values, 20, 2, np.random.default_rng(5))
    second = _moving_block_bootstrap_median(values, 20, 2, np.random.default_rng(5))
    np.testing.assert_allclose(first, second)


def test_validation_preserves_terminal_holdout_and_publishes_all_tables():
    cfg = replace(
        PLSPeerValidationConfig(),
        terminal_test_days=14,
        bootstrap_replicates=40,
        injection_window_h=24,
        injection_ramp_h=6,
        injection_amplitudes_sigma=(2.0,),
        clean_abs_z_max=20.0,
        alarm_abs_z=10.0,
    )
    result = validate_do24_peer_upgrade(_synthetic_frame(), cfg)

    split = result["split_manifest"].iloc[0]
    assert split.independent_test_n_h == 14 * 24
    assert set(result["performance_summary"].model_id) == {"M0", "M1_1", "M1_2"}
    assert len(result["hourly_predictions"]) == len(_synthetic_frame())
    assert set(result["hourly_predictions"].split) == {
        "training",
        "development",
        "terminal_test",
    }
    assert len(result["bootstrap_samples"]) == 3 * 40
    assert set(result["injection_scenarios"].injection_type) == {
        "target_drift",
        "direct_peer_drift",
        "second_order_peer_drift",
        "common_process_change",
    }
    assert result["final_model_id"] in {"M0", "M1_1", "M1_2"}
