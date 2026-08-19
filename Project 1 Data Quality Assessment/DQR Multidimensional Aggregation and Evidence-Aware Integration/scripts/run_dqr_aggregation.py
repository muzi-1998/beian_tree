from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from dqr_aggregation import run_aggregation  # noqa: E402


if __name__ == "__main__":
    print(json.dumps(run_aggregation(), indent=2, ensure_ascii=True))
