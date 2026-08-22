from __future__ import annotations

import sys
from pathlib import Path


D4_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(D4_ROOT / "src"))

from d4.mapping_support_audit import run_mapping_support_audit  # noqa: E402


if __name__ == "__main__":
    outputs = run_mapping_support_audit(
        D4_ROOT / "outputs" / "data" / "D4_main_scores.xlsx",
        D4_ROOT / "outputs" / "data" / "D4_mapping_params.xlsx",
        D4_ROOT / "outputs" / "audit" / "mapping_support_migration",
    )
    summary = outputs["phase_composition"]
    print(summary.to_string(index=False))
