"""Re-export Fig. 3 from frozen statistics, without refitting or resampling."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

PROJECT = Path(__file__).resolve().parents[2]
DQR = PROJECT / "DQR Multidimensional Aggregation and Evidence-Aware Integration"
sys.path.insert(0, str(DQR / "src"))

from dqr_aggregation.common import (OUTPUT_ROOT, generation_source_registry, load_config, write_json)
from dqr_aggregation.figures import _figure_3, run_figure_qa
from dqr_aggregation.figure_style import configure_style
from dqr_aggregation.pipeline import verify_frozen_inputs
from dqr_aggregation.runner import _artifact_inventory


def main():
    config = load_config()
    verify_frozen_inputs(config)
    root = OUTPUT_ROOT
    run_path = root / "manifests/DQR_run_manifest.json"
    pub_path = root / "manifests/DQR_publication_manifest.json"
    run = json.loads(run_path.read_text(encoding="utf-8"))
    publication = json.loads(pub_path.read_text(encoding="utf-8"))
    if generation_source_registry() != run["code_sources"]:
        raise RuntimeError("Re-export requires a fresh full run with the current source contract")
    construct = pd.read_excel(root / "validation/DQR_aggregation_validation.xlsx", sheet_name="construct_validity")
    configure_style()
    _figure_3(config, root / "figures", root / "source_data", construct)
    qa = run_figure_qa(root / "figures", root / "validation/DQR_figure_qa.json")
    assert qa["passed"]
    run["artifacts"] = _artifact_inventory(root, exclude={run_path, pub_path})
    write_json(run_path, run)
    publication["artifacts"] = _artifact_inventory(root, exclude={pub_path})
    write_json(pub_path, publication)
    print(json.dumps({"figure": "DQR_Fig03", "frozen_statistics_reused": True,
                      "no_refit_or_resampling": True, "figure_qa": qa["passed"]}))


if __name__ == "__main__":
    main()
