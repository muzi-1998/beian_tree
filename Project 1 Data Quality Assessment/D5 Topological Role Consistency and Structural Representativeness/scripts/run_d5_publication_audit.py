from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from d5_local.publication import D5PublicationAudit, D5PublicationFigureBuilder  # noqa: E402
from d5_local.figures import run_figure_qa  # noqa: E402


if __name__ == "__main__":
    audit = D5PublicationAudit()
    result = audit.run()
    figures = D5PublicationFigureBuilder().build_all()
    figure_qa = run_figure_qa()
    manifest = audit.finalize_figure_bundle()
    print(
        json.dumps(
            {
                **result,
                "figure_files": [str(path) for path in figures],
                "figure_qa_passed": figure_qa["passed"],
                "manifest": str(manifest),
            },
            indent=2,
        )
    )
