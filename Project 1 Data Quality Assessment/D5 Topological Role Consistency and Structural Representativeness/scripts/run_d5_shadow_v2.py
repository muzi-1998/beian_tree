from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from d5_shadow_v2 import D5GraphShadowPipeline  # noqa: E402


if __name__ == "__main__":
    print(json.dumps(D5GraphShadowPipeline().run(), indent=2, default=str))
