from __future__ import annotations

import sys
from pathlib import Path


D4_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = D4_ROOT.parent
sys.path.insert(0, str(D4_ROOT / "src"))

from d4.redundancy_audit import run_redundancy_audit


if __name__ == "__main__":
    outputs = run_redundancy_audit(
        D4_ROOT / "outputs" / "data" / "D4_main_scores.xlsx",
        PROJECT_ROOT / "D1 Sensor health" / "outputs" / "data" / "D1_event_windows.xlsx",
        D4_ROOT / "outputs" / "data" / "D4_event_windows.xlsx",
        D4_ROOT / "outputs" / "integration" / "D4V151_composite_refresh",
        D4_ROOT / "outputs" / "data" / "D1_D4_redundancy_audit.xlsx",
    )
    print(outputs["score_dependence"].to_string(index=False))
    print(outputs["composite_ablation"].to_string(index=False))
