from __future__ import annotations

import sys
from pathlib import Path


D4_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(D4_ROOT / "src"))

from d4.publication import build_publication_manifest  # noqa: E402


if __name__ == "__main__":
    print(build_publication_manifest())
