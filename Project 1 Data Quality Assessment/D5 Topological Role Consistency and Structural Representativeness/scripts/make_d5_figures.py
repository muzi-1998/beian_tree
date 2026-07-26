from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from d5_local.figures import D5FigureBuilder, D5PlotDataBuilder, run_figure_qa  # noqa: E402


if __name__ == "__main__":
    plot_data = D5PlotDataBuilder().build()
    outputs = D5FigureBuilder().build_all()
    qa = run_figure_qa()
    print(json.dumps({"plot_rows": len(plot_data), "figure_files": len(outputs), "qa": qa}, indent=2))
