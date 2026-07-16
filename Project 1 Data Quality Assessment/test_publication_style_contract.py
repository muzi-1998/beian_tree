from __future__ import annotations

import importlib.util
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pytest


ROOT = Path(__file__).parent


def _load_style(relative_path: str):
    path = ROOT / relative_path
    spec = importlib.util.spec_from_file_location(path.parent.name + "_style", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _has_tick_at(values, target, span):
    return np.any(np.isclose(np.asarray(values, dtype=float), target,
                             rtol=0, atol=max(span * 1e-7, 1e-12)))


def test_d1_publication_contract():
    style = _load_style("D1 Sensor health/publication_style.py")
    style.configure_publication_style()
    fig, axes = plt.subplots(1, 2)
    for ax in axes:
        ax.plot([0.2, 0.8], [1.2, 2.8])
        ax.set_xlim(0.17, 0.83)
        ax.set_ylim(1.17, 2.83)
    axes[0].spines["top"].set_visible(False)
    axes[0].spines["right"].set_visible(False)
    for spine in axes[1].spines.values():
        spine.set_visible(True)
    axes[0].set_title("Evidence", loc="left")
    style.finalize_figure(fig)

    assert matplotlib.rcParams["font.sans-serif"][0] == "Arial"
    for index, ax in enumerate(axes):
        assert ax.spines["left"].get_linewidth() == 0.8
        assert ax.spines["bottom"].get_linewidth() == 0.8
        expected_direction = "out" if index == 0 else "in"
        assert all(tick._tickdir == expected_direction for tick in ax.xaxis.majorTicks)
        assert all(tick._tickdir == expected_direction for tick in ax.yaxis.majorTicks)
        assert all(tick._tickdir == expected_direction for tick in ax.xaxis.minorTicks)
        assert all(tick._tickdir == expected_direction for tick in ax.yaxis.minorTicks)
        xloc = np.r_[ax.xaxis.get_majorticklocs(), ax.xaxis.get_minorticklocs()]
        yloc = np.r_[ax.yaxis.get_majorticklocs(), ax.yaxis.get_minorticklocs()]
        xlim, ylim = ax.get_xlim(), ax.get_ylim()
        assert all(_has_tick_at(xloc, value, abs(xlim[1] - xlim[0])) for value in xlim)
        assert all(_has_tick_at(yloc, value, abs(ylim[1] - ylim[0])) for value in ylim)
        if index == 0:
            assert ax.get_title(loc="left") == "(a) Evidence"
        else:
            assert "(b)" in [text.get_text() for text in ax.texts]
    plt.close(fig)


@pytest.mark.parametrize(
    ("relative_path", "setup_name", "finalize_name"),
    [
        ("1.1 Decomposition/src/outputs/figstyle.py",
         "setup_style", "finalize_publication_figure"),
        ("D1 Sensor health/publication_style.py",
         "configure_publication_style", "finalize_figure"),
        ("D2 Temporal Continuity & Information Availability/publication_style.py",
         "configure_publication_style", "finalize_figure"),
        ("D6 Parallel-redundancy Temporal Consistency/src/d6/figure_style.py",
         "configure_style", "finalize"),
    ],
)
def test_tick_direction_tracks_frame_type(relative_path, setup_name, finalize_name):
    style = _load_style(relative_path)
    getattr(style, setup_name)()
    fig, (open_ax, boxed_ax) = plt.subplots(1, 2)
    for ax in (open_ax, boxed_ax):
        ax.plot([0.2, 0.8], [1.2, 2.8])
    open_ax.spines["top"].set_visible(False)
    open_ax.spines["right"].set_visible(False)
    for spine in boxed_ax.spines.values():
        spine.set_visible(True)

    getattr(style, finalize_name)(fig, auto_panel_labels=False)

    for axis in (open_ax.xaxis, open_ax.yaxis):
        assert all(tick._tickdir == "out" for tick in axis.majorTicks)
        assert all(tick._tickdir == "out" for tick in axis.minorTicks)
    for axis in (boxed_ax.xaxis, boxed_ax.yaxis):
        assert all(tick._tickdir == "in" for tick in axis.majorTicks)
        assert all(tick._tickdir == "in" for tick in axis.minorTicks)
    plt.close(fig)


def test_data_annotation_keeps_evidence_visible():
    style = _load_style("D1 Sensor health/publication_style.py")
    fig, ax = plt.subplots()
    annotation = style.annotate_data_label(ax, "DO_2_3", (0.5, 0.5), arrow=True)
    patch = annotation.get_bbox_patch()
    assert patch is not None
    assert 0 < patch.get_alpha() < 1
    assert annotation.arrow_patch is not None
    plt.close(fig)


def test_d2_panel_label_normalization():
    style = _load_style(
        "D2 Temporal Continuity & Information Availability/publication_style.py"
    )
    fig, axes = plt.subplots(2, 1)
    axes[0].set_title("a  Evidence", loc="left")
    axes[1].text(-0.1, 1.03, "B", transform=axes[1].transAxes)
    grade = axes[1].text(0.98, 0.75, "A", transform=axes[1].transAxes)
    style.finalize_figure(fig)
    assert axes[0].get_title(loc="left").startswith("(a) ")
    assert not any(text.get_text() == "(a)" for text in axes[0].texts)
    assert axes[1].texts[0].get_text() == "(b)"
    assert grade.get_text() == "A"
    plt.close(fig)
