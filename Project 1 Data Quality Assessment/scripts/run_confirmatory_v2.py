from __future__ import annotations

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.confirmatory_v2 import run_confirmatory_v2


if __name__ == "__main__":
    output = run_confirmatory_v2()
    print(f"Confirmatory v2.0 outputs: {output}")

