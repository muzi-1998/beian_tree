from dataclasses import replace
from pathlib import Path
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT.parent))
sys.path.insert(0, str(ROOT / "src"))
from d4.config import load_config
from d4.pipeline import _fit_and_score
from shared_data_foundation.context import fit_context, pair_support


def test_observed_lock_is_not_missing_and_full_window_is_required():
    index = pd.date_range("2025-08-01", periods=25*60, freq="min")
    raw = pd.DataFrame({"a": 1.0, "b": 2.0}, index=index)
    support = pair_support(raw, "a", "b")
    assert not support.iloc[22].raw_complete_window
    assert support.iloc[23].raw_common_fraction_24h == 1.0
    raw.loc[index[-120:], "a"] = np.nan
    assert pair_support(raw, "a", "b").iloc[-1].raw_common_fraction_24h < 1


def test_frozen_context_prefix_does_not_see_future():
    rng = np.random.default_rng(42)
    index = pd.date_range("2025-08-01", periods=100*60, freq="min")
    raw = pd.DataFrame(rng.normal(size=(len(index), 2)), index=index, columns=["a", "b"])
    left, asset = fit_context(raw, "2025-08-04", fit_start="2025-08-01", n_regimes=2)
    changed = raw.copy()
    changed.loc[changed.index >= "2025-08-04"] += 1000
    right, asset2 = fit_context(changed, "2025-08-04", fit_start="2025-08-01", n_regimes=2)
    assert asset == asset2
    pd.testing.assert_frame_equal(left.loc[:"2025-08-03"], right.loc[:"2025-08-03"])
    assert left.regime_id.iloc[:23].isna().all()


def test_score_and_reference_invariant_to_other_dimension_scores(monkeypatch):
    config = load_config(ROOT / "configs/d4.yaml", ROOT.parent)
    benchmark = dict(config.benchmark)
    benchmark.update(min_exact_independent_blocks=1, min_stratum_windows=4, min_variable_windows=4)
    benchmark["percentile_precision"] = dict(benchmark["percentile_precision"], bootstrap_repetitions=3)
    config = replace(config, benchmark=benchmark)
    n = 120
    raw = pd.DataFrame({"timestamp": pd.date_range("2025-08-04", periods=n, freq="h"),
        "variable": "DO", "regime_id": 0, "valid_fraction_common": 1.0,
        "valid_fraction_common_hours": 1.0, "raw_common_fraction_24h": 1.0,
        "raw_supported_hours_fraction": 1.0, "raw_complete_window": True,
        "context_24h_valid": True, "window_purity": 1.0, "Q_cp": 5.0, "deadband_active": False})
    for i, key in enumerate(("risk_dist", "risk_dist_w1", "risk_dist_ks", "risk_trend", "risk_var")):
        raw[key] = np.linspace(0.1, 2.0+i, n)
    def forbidden(*args, **kwargs):
        raise AssertionError("Score workbook access in core")
    monkeypatch.setattr(pd, "read_excel", forbidden)
    baseline, params, reference = _fit_and_score(raw, config)
    changed = raw.assign(D1_target=1, D1_ref=1, D2_target_veto=1, D2_ref_veto=1,
                         D2_target=1, D2_ref=1)
    revised, params2, reference2 = _fit_and_score(changed, config)
    columns = ["Q_dist", "Q_trend", "Q_var", "Q_cp", "D4_raw", "usable_for_D4", "reference_eligible"]
    pd.testing.assert_frame_equal(baseline[columns], revised[columns])
    pd.testing.assert_frame_equal(params, params2)
    assert len(reference) == len(reference2) == n
