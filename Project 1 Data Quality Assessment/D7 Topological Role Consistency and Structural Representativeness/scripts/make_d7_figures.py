from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from d7_local.figures import D7FigureBuilder, D7PlotDataBuilder, run_figure_qa  # noqa: E402


if __name__ == "__main__":
    plot_data = D7PlotDataBuilder().build()
    outputs = D7FigureBuilder().build_all()
    qa = run_figure_qa()
    print(json.dumps({"plot_rows": len(plot_data), "figure_files": len(outputs), "qa": qa}, indent=2))
