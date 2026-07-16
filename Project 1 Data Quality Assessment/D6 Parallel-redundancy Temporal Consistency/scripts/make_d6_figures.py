from __future__ import annotations

import sys
from pathlib import Path


D6_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = D6_ROOT.parent
sys.path.insert(0, str(D6_ROOT / "src"))

from d6.config import load_config
from d6.figures import make_all_figures


if __name__ == "__main__":
    cfg = load_config(D6_ROOT / "configs" / "d6.yaml", PROJECT_ROOT)
    make_all_figures(cfg, D6_ROOT / "outputs" / "data", D6_ROOT / "outputs" / "figures")
    print("D6 figures complete")
