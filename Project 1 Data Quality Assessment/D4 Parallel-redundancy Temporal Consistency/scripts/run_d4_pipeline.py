from __future__ import annotations

import sys
from pathlib import Path


D4_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = D4_ROOT.parent
sys.path.insert(0, str(D4_ROOT / "src"))

from d4.pipeline import run_pipeline


if __name__ == "__main__":
    result = run_pipeline(PROJECT_ROOT, D4_ROOT)
    manifest = result["manifest"]
    print(
        f"D4 complete: run_id={manifest['run_id']} rows={manifest['rows']} "
        f"pairs={manifest['pairs']}"
    )
