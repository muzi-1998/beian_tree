from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import matplotlib as mpl
import matplotlib.pyplot as plt


MM_PER_INCH = 25.4


@dataclass(frozen=True)
class FigureProfile:
    name: str = "nature_double"
    width_mm: float = 183.0
    body_text_pt: float = 7.0
    panel_label_pt: float = 8.0
    axis_line_pt: float = 0.8
    raster_dpi: int = 600

    @property
    def width_in(self) -> float:
        return self.width_mm / MM_PER_INCH


PROFILE = FigureProfile()

PALETTE = {
    "blue": "#168AAD",
    "red": "#D1495B",
    "teal": "#2A9D8F",
    "gold": "#D8A72E",
    "orange": "#E76F51",
    "navy": "#3D5A80",
    "gray": "#7A7F87",
    "light_gray": "#D9DEE3",
    "dark": "#222222",
}


def configure_style() -> None:
    mpl.rcParams.update(
        {
            "font.family": "Arial",
            "font.size": PROFILE.body_text_pt,
            "axes.labelsize": PROFILE.body_text_pt,
            "axes.titlesize": PROFILE.body_text_pt,
            "axes.titleweight": "normal",
            "axes.titlepad": 4.0,
            "axes.linewidth": PROFILE.axis_line_pt,
            "xtick.labelsize": 6.5,
            "ytick.labelsize": 6.5,
            "xtick.major.width": PROFILE.axis_line_pt,
            "ytick.major.width": PROFILE.axis_line_pt,
            "xtick.minor.width": 0.6,
            "ytick.minor.width": 0.6,
            "xtick.direction": "in",
            "ytick.direction": "in",
            "xtick.top": False,
            "ytick.right": False,
            "legend.fontsize": 6.3,
            "legend.frameon": False,
            "lines.linewidth": 1.0,
            "patch.linewidth": 0.7,
            "savefig.transparent": False,
            "svg.fonttype": "none",
            "pdf.fonttype": 42,
        }
    )


def panel_label(ax: plt.Axes, label: str) -> None:
    ax.text(
        -0.085,
        1.015,
        f"({label})",
        transform=ax.transAxes,
        fontsize=PROFILE.panel_label_pt,
        fontweight="bold",
        va="bottom",
        ha="right",
        clip_on=False,
    )


def style_axes(ax: plt.Axes, *, boxed: bool = False) -> None:
    ax.spines["left"].set_visible(True)
    ax.spines["bottom"].set_visible(True)
    ax.spines["left"].set_linewidth(PROFILE.axis_line_pt)
    ax.spines["bottom"].set_linewidth(PROFILE.axis_line_pt)
    for side in ("top", "right"):
        ax.spines[side].set_visible(boxed)
        ax.spines[side].set_linewidth(PROFILE.axis_line_pt)
    ax.tick_params(
        which="both",
        direction="in" if boxed else "out",
        top=boxed,
        right=boxed,
        width=PROFILE.axis_line_pt,
        length=3.0,
    )


def save_figure(
    fig: plt.Figure,
    output_root: Path,
    stem: str,
    *,
    tiff_dpi: int | None = None,
) -> list[Path]:
    output_root.mkdir(parents=True, exist_ok=True)
    outputs = [output_root / f"{stem}.{suffix}" for suffix in ("png", "pdf", "svg", "tiff")]
    png, pdf, svg, tiff = outputs
    dpi = tiff_dpi or PROFILE.raster_dpi
    fig.savefig(png, dpi=PROFILE.raster_dpi, facecolor="white")
    fig.savefig(pdf, facecolor="white")
    fig.savefig(svg, facecolor="white")
    svg.write_text(
        "\n".join(line.rstrip() for line in svg.read_text(encoding="utf-8").splitlines())
        + "\n",
        encoding="utf-8",
    )
    fig.savefig(
        tiff,
        dpi=dpi,
        facecolor="white",
        pil_kwargs={"compression": "tiff_lzw"},
    )
    plt.close(fig)
    return outputs
