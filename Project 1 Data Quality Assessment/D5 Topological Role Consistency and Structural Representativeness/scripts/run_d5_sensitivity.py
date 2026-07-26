from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from d5_sensitivity import D5SensitivityPipeline  # noqa: E402


if __name__ == "__main__":
    print(json.dumps(D5SensitivityPipeline().run(), indent=2, default=str))
