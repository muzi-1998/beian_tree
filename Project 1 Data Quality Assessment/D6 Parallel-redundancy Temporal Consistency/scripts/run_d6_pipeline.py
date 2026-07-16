from __future__ import annotations

import sys
from pathlib import Path


D6_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = D6_ROOT.parent
sys.path.insert(0, str(D6_ROOT / "src"))

from d6.pipeline import run_pipeline


if __name__ == "__main__":
    result = run_pipeline(PROJECT_ROOT, D6_ROOT)
    manifest = result["manifest"]
    print(
        f"D6 complete: run_id={manifest['run_id']} rows={manifest['rows']} "
        f"pairs={manifest['pairs']}"
    )
