from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from d5_local.reports import D5ReportBuilder  # noqa: E402


if __name__ == "__main__":
    for output in D5ReportBuilder().build_all():
        print(output)
