from __future__ import annotations

import json

import matplotlib.pyplot as plt
import pandas as pd

from d7_common.config import resolve_paths
from d7_local.figures.make_figures import D7FigureBuilder


def test_framed_heatmap_uses_primary_axis_ticks_only() -> None:
    fig, ax = plt.subplots()
    D7FigureBuilder._framed_primary_axes(ax)
    fig.canvas.draw()

    assert all(spine.get_visible() for spine in ax.spines.values())
    assert all(tick.tick1line.get_visible() for tick in ax.xaxis.get_major_ticks())
    assert all(not tick.tick2line.get_visible() for tick in ax.xaxis.get_major_ticks())
    assert all(tick.tick1line.get_visible() for tick in ax.yaxis.get_major_ticks())
    assert all(not tick.tick2line.get_visible() for tick in ax.yaxis.get_major_ticks())
    plt.close(fig)


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
    main = pd.read_parquet(paths.local_output_root / "D7_main_scores_hourly.parquet")
    distribution = plot_data[
        (plot_data["figure_id"] == "FigD7_2_spatiotemporal")
        & (plot_data["panel"] == "b")
        & (plot_data["record_type"] == "score_distribution")
    ]
    assert len(distribution) == int(main["D7_raw"].notna().sum())
    manifest = json.loads(
        (paths.plot_data_root / "D7_plot_data_manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["rendering_samples_removed"] == 0
    qa = json.loads((paths.figure_root / "D7_figure_qa.json").read_text(encoding="utf-8"))
    assert qa["passed"]
    assert all(180.0 <= record["final_width_mm_at_600dpi"] <= 186.0 for record in qa["figures"])
    for record in qa["figures"]:
        stem = record["stem"]
        assert (paths.figure_root / f"{stem}.tiff").exists()
        svg = (paths.figure_root / f"{stem}.svg").read_text(encoding="utf-8")
        assert "<text" in svg


def test_sensitivity_has_no_production_columns() -> None:
    paths = resolve_paths()
    shadow = pd.read_parquet(paths.sensitivity_output_root / "D7_shadow_scores.parquet")
    assert "D7_forDQR" not in shadow.columns
    assert "D7_zone_consensus" not in shadow.columns
    assert (shadow["track_id"] == "sensitivity").all()
