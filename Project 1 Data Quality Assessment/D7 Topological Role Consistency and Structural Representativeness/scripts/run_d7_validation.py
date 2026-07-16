from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from d7_local.validation import D7ValidationRunner  # noqa: E402


if __name__ == "__main__":
    print(json.dumps(D7ValidationRunner().run(), indent=2, default=str))
