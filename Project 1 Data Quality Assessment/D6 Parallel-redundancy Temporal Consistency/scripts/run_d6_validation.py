from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd


D6_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = D6_ROOT.parent
sys.path.insert(0, str(D6_ROOT / "src"))

from d6.config import load_config
from d6.validation import run_validation


if __name__ == "__main__":
    cfg = load_config(D6_ROOT / "configs" / "d6.yaml", PROJECT_ROOT)
    data_dir = D6_ROOT / "outputs" / "data"
    main = pd.read_excel(data_dir / "D6_main_scores.xlsx", sheet_name="main_scores")
    main["timestamp"] = pd.to_datetime(main["timestamp"])
    params = pd.read_excel(data_dir / "D6_mapping_params.xlsx", sheet_name="public_quantiles")
    outputs = run_validation(
        cfg, cfg.paths["residuals"], main, params,
        data_dir / "D6_benchmark_results.xlsx",
    )
    print(outputs["summary"].to_string(index=False))
