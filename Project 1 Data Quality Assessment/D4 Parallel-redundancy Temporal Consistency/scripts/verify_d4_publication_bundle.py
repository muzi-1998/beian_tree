from __future__ import annotations

import json
import sys
from pathlib import Path


D4_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(D4_ROOT / "src"))

from d4.publication import verify_publication_manifest  # noqa: E402


if __name__ == "__main__":
    result = verify_publication_manifest()
    print(json.dumps(result, indent=2))
    if not result["passed"]:
        raise SystemExit(1)
