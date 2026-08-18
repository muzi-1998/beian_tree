from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from d5_local.figures import D5FigureBuilder, D5PlotDataBuilder, run_figure_qa  # noqa: E402
from d5_local.publication import D5PublicationAudit, D5PublicationFigureBuilder  # noqa: E402


if __name__ == "__main__":
    plot_data = D5PlotDataBuilder().build()
    outputs = D5FigureBuilder().build_all()
    if (ROOT / "outputs" / "publication" / "D5_publication_audit_manifest.json").exists():
        outputs.extend(D5PublicationFigureBuilder().build_all())
    qa = run_figure_qa()
    publication_manifest = ROOT / "outputs" / "publication" / "D5_publication_audit_manifest.json"
    if publication_manifest.exists():
        D5PublicationAudit().finalize_figure_bundle()
    print(json.dumps({"plot_rows": len(plot_data), "figure_files": len(outputs), "qa": qa}, indent=2))
