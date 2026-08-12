from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd


D4_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(D4_ROOT / "src"))

from d4.config import load_config
from d4.figures import _ablation_score, _provenance_table


def test_ablation_score_reweights_remaining_components() -> None:
    cfg = load_config(D4_ROOT / "configs" / "d4.yaml", D4_ROOT.parent)
    frame = pd.DataFrame(
        {
            "Q_dist": [1.0],
            "Q_trend": [4.0],
            "Q_var": [5.0],
            "Q_cp": [3.0],
            "Q_var_no_deadband": [2.0],
        }
    )
    score = _ablation_score(frame, "no_dist", cfg)
    expected_base = (0.25 * 4.0 + 0.20 * 5.0 + 0.20 * 3.0) / 0.65
    expected = cfg.lambda_blend * expected_base + (1 - cfg.lambda_blend) * 3.0
    assert np.isclose(score[0], expected)


def test_calibration_provenance_retains_public_scope_and_support() -> None:
    params = pd.DataFrame(
        {
            "variable": ["DO", "DO", "ORP"],
            "regime_id": [0, 0, 1],
            "sample_size": [100, 120, 80],
            "exact_stratum_size": [100, 110, 20],
            "mapping_scope": ["variable_regime", "variable_regime", "variable_fallback"],
            "calibration_quality": ["adequate", "adequate", "limited"],
        }
    )
    output = _provenance_table(params)
    do_row = output[(output["variable"] == "DO") & (output["regime_id"] == 0)].iloc[0]
    orp_row = output[(output["variable"] == "ORP") & (output["regime_id"] == 1)].iloc[0]
    assert do_row["sample_size"] == 100
    assert do_row["exact_stratum_size"] == 100
    assert orp_row["mapping_scope"] == "variable_fallback"
    assert orp_row["calibration_quality"] == "limited"
