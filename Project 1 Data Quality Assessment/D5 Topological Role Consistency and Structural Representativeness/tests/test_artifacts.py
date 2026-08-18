from __future__ import annotations

import json

import pandas as pd

from d5_common.config import resolve_paths


def test_plot_data_contract_and_figure_qa() -> None:
    paths = resolve_paths()
    plot_data = pd.read_parquet(paths.plot_data_root / "D5_plot_data.parquet")
    assert set(plot_data["figure_id"].unique()) == {
        "FigD5_1_framework",
        "FigD5_2_spatiotemporal",
        "FigD5_3_evidence",
        "FigD5_4_validation",
        "FigD5_5_governance",
    }
    assert plot_data["source_run_id"].nunique() == 1
    qa = json.loads((paths.figure_root / "D5_figure_qa.json").read_text(encoding="utf-8"))
    assert qa["passed"]
    assert len(qa["figures"]) == 9
    assert qa["profile"]["width_mm"] == 183.0
    assert all(figure["editable_svg_text"] for figure in qa["figures"])
    assert all(abs(figure["pdf_width_mm"] - 183.0) <= 0.5 for figure in qa["figures"])


def test_reconstructed_figure_evidence_contract() -> None:
    paths = resolve_paths()
    plot_data = pd.read_parquet(paths.plot_data_root / "D5_plot_data.parquet")
    framework = plot_data[plot_data["figure_id"].eq("FigD5_1_framework")]
    peer_edges = framework[
        framework["panel"].eq("a") & framework["context"].eq("parallel_peer")
    ]
    assert peer_edges["group"].nunique() == 7
    assert peer_edges.groupby("group").size().eq(2).all()
    evidence = plot_data[plot_data["figure_id"].eq("FigD5_3_evidence")]
    raw = evidence[evidence["record_type"].eq("raw_timeseries")]
    assert {"Target", "Parallel peer", "Same-line neighbor"}.issubset(
        set(raw["group"].dropna())
    )


def test_sensitivity_has_no_production_columns() -> None:
    paths = resolve_paths()
    shadow = pd.read_parquet(paths.sensitivity_output_root / "D5_shadow_scores.parquet")
    assert "D5_forDQR" not in shadow.columns
    assert "D5_zone_consensus" not in shadow.columns
    assert (shadow["track_id"] == "sensitivity").all()
