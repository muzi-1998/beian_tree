from __future__ import annotations

import sys
from pathlib import Path


D6_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = D6_ROOT.parent
sys.path.insert(0, str(D6_ROOT / "src"))

from d6.sensitivity import run_sensitivity


if __name__ == "__main__":
    outputs = run_sensitivity(D6_ROOT)
    print(f"D6 sensitivity complete: pair rows={len(outputs['pair_summary'])}")
