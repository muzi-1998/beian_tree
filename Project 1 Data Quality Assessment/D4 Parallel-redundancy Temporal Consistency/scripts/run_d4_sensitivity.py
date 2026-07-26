from __future__ import annotations

import sys
from pathlib import Path


D4_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = D4_ROOT.parent
sys.path.insert(0, str(D4_ROOT / "src"))

from d4.sensitivity import run_sensitivity


if __name__ == "__main__":
    outputs = run_sensitivity(D4_ROOT)
    print(f"D4 sensitivity complete: pair rows={len(outputs['pair_summary'])}")
