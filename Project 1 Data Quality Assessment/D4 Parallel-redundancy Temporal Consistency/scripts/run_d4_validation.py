from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd


D4_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = D4_ROOT.parent
sys.path.insert(0, str(D4_ROOT / "src"))

from d4.config import load_config
from d4.validation import run_validation


if __name__ == "__main__":
    cfg = load_config(D4_ROOT / "configs" / "d4.yaml", PROJECT_ROOT)
    data_dir = D4_ROOT / "outputs" / "data"
    main = pd.read_excel(data_dir / "D4_main_scores.xlsx", sheet_name="main_scores")
    main["timestamp"] = pd.to_datetime(main["timestamp"])
    params = pd.read_excel(data_dir / "D4_mapping_params.xlsx", sheet_name="public_quantiles")
    outputs = run_validation(
        cfg, cfg.paths["residuals"], main, params,
        data_dir / "D4_benchmark_results.xlsx",
    )
    print(outputs["summary"].to_string(index=False))
