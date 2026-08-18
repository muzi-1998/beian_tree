from __future__ import annotations

import sys
from pathlib import Path


D4_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(D4_ROOT / "src"))

from d4.method_sensitivity import run_method_sensitivity


if __name__ == "__main__":
    outputs = run_method_sensitivity(
        D4_ROOT / "legacy" / "2026-07-26-v1.4-canonical" / "D4_main_scores.xlsx",
        D4_ROOT / "outputs" / "data" / "D4_main_scores.xlsx",
        D4_ROOT / "outputs" / "comparison" / "D4_v14_v151_method_sensitivity.xlsx",
    )
    print(outputs["pair_score_comparison"].to_string(index=False))
