from __future__ import annotations

import sys
from pathlib import Path


D4_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = D4_ROOT.parent
sys.path.insert(0, str(D4_ROOT / "src"))

from d4.config import load_config
from d4.figures import make_all_figures


if __name__ == "__main__":
    cfg = load_config(D4_ROOT / "configs" / "d4.yaml", PROJECT_ROOT)
    make_all_figures(cfg, D4_ROOT / "outputs" / "data", D4_ROOT / "outputs" / "figures")
    print("D4 figures complete")
