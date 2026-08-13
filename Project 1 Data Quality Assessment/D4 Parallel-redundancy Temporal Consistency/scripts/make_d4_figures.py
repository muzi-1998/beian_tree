from __future__ import annotations

import sys
from pathlib import Path


D4_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = D4_ROOT.parent
sys.path.insert(0, str(D4_ROOT / "src"))

from d4.config import load_config
from d4.figures import make_all_figures


LEGACY_STEMS = (
    "FigD4_1_paired_residual_consistency",
    "FigD4_2_subscore_contribution",
    "FigD4_3_trend_slope_scatter",
    "FigD4_4_raw_score_heatmap",
    "FigD4_5_status_evaluability",
    "FigD4_6_context_independence",
    "FigD4_7_validation_roc_pr",
    "FigD4_8_validation_ablation",
)


def remove_legacy_exports(output_dir: Path) -> None:
    for stem in LEGACY_STEMS:
        for extension in ("svg", "pdf", "png", "tiff"):
            path = output_dir / f"{stem}.{extension}"
            if path.exists():
                path.unlink()


if __name__ == "__main__":
    cfg = load_config(D4_ROOT / "configs" / "d4.yaml", PROJECT_ROOT)
    figure_dir = D4_ROOT / "outputs" / "figures"
    remove_legacy_exports(figure_dir)
    make_all_figures(cfg, D4_ROOT / "outputs" / "data", figure_dir)
    print("D4 figures complete")
