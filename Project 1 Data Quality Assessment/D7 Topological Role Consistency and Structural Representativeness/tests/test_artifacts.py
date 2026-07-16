from __future__ import annotations

import json

import pandas as pd

from d7_common.config import resolve_paths


def test_plot_data_contract_and_figure_qa() -> None:
    paths = resolve_paths()
    plot_data = pd.read_parquet(paths.plot_data_root / "D7_plot_data.parquet")
    assert set(plot_data["figure_id"].unique()) == {
        "FigD7_1_framework",
        "FigD7_2_spatiotemporal",
        "FigD7_3_evidence",
        "FigD7_4_validation",
        "FigD7_5_governance",
    }
    assert plot_data["source_run_id"].nunique() == 1
    qa = json.loads((paths.figure_root / "D7_figure_qa.json").read_text(encoding="utf-8"))
    assert qa["passed"]


def test_sensitivity_has_no_production_columns() -> None:
    paths = resolve_paths()
    shadow = pd.read_parquet(paths.sensitivity_output_root / "D7_shadow_scores.parquet")
    assert "D7_forDQR" not in shadow.columns
    assert "D7_zone_consensus" not in shadow.columns
    assert (shadow["track_id"] == "sensitivity").all()
