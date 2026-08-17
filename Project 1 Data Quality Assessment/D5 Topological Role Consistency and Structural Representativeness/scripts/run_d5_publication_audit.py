from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from d5_local.publication import D5PublicationAudit, D5PublicationFigureBuilder  # noqa: E402


if __name__ == "__main__":
    result = D5PublicationAudit().run()
    figures = D5PublicationFigureBuilder().build_all()
    print(json.dumps({**result, "figure_files": [str(path) for path in figures]}, indent=2))
