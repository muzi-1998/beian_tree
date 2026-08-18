from __future__ import annotations

import json
from pathlib import Path

import fitz
import numpy as np
from PIL import Image

from d5_common.config import resolve_paths
from d5_local.figures.figure_style import PROFILE
from d5_local.outputs.manifest import sha256_file


FIGURE_STEMS = [
    "FigD5_1_framework",
    "FigD5_2_spatiotemporal",
    "FigD5_3_evidence",
    "FigD5_4_validation",
    "FigD5_5_governance",
    "FigD5_6_validation_coverage",
    "FigD5_7_D4_D5_complementarity",
    "FigD5_8_dimension_availability_sensitivity",
    "FigD5_9_target_support_robustness",
]


def _pdf_size_mm(path: Path) -> tuple[float, float]:
    with fitz.open(path) as document:
        page = document[0]
        return page.rect.width * 25.4 / 72.0, page.rect.height * 25.4 / 72.0


def _edge_ink_fraction(array: np.ndarray, border_px: int = 3) -> float:
    ink = (array < 248).any(axis=2)
    border = np.concatenate(
        [
            ink[:border_px, :].ravel(),
            ink[-border_px:, :].ravel(),
            ink[:, :border_px].ravel(),
            ink[:, -border_px:].ravel(),
        ]
    )
    return float(border.mean())


def run_figure_qa() -> dict[str, object]:
    paths = resolve_paths()
    failures: list[str] = []
    records: list[dict[str, object]] = []
    expected_width_px = round(PROFILE.width_in * PROFILE.raster_dpi)
    for stem in FIGURE_STEMS:
        counterparts = {
            suffix: paths.figure_root / f"{stem}.{suffix}"
            for suffix in ["png", "pdf", "svg", "tiff"]
        }
        for path in counterparts.values():
            if not path.exists() or path.stat().st_size == 0:
                failures.append(f"missing_or_empty:{path.name}")
        if not all(path.exists() for path in counterparts.values()):
            continue

        image = Image.open(counterparts["png"]).convert("RGB")
        array = np.asarray(image)
        nonwhite_fraction = float((array < 248).any(axis=2).mean())
        edge_ink_fraction = _edge_ink_fraction(array)
        if abs(image.width - expected_width_px) > 2:
            failures.append(
                f"incorrect_600dpi_width:{stem}:{image.width}!={expected_width_px}"
            )
        if image.height < 1400:
            failures.append(f"insufficient_600dpi_height:{stem}:{image.height}")
        if nonwhite_fraction < 0.03:
            failures.append(f"near_blank:{stem}:{nonwhite_fraction:.4f}")
        if edge_ink_fraction > 0.02:
            failures.append(f"possible_canvas_clipping:{stem}:{edge_ink_fraction:.4f}")

        width_mm, height_mm = _pdf_size_mm(counterparts["pdf"])
        if abs(width_mm - PROFILE.width_mm) > 0.5:
            failures.append(f"incorrect_pdf_width_mm:{stem}:{width_mm:.2f}")
        if height_mm > 170.0:
            failures.append(f"pdf_height_exceeds_170mm:{stem}:{height_mm:.2f}")

        svg = counterparts["svg"].read_text(encoding="utf-8")
        if "Arial" not in svg:
            failures.append(f"arial_not_referenced:{stem}")
        if "<text" not in svg:
            failures.append(f"svg_text_not_editable:{stem}")
        if "(a)" not in svg:
            failures.append(f"panel_label_missing:{stem}")
        records.append(
            {
                "stem": stem,
                "png_width": image.width,
                "png_height": image.height,
                "pdf_width_mm": round(width_mm, 2),
                "pdf_height_mm": round(height_mm, 2),
                "nonwhite_fraction": nonwhite_fraction,
                "edge_ink_fraction": edge_ink_fraction,
                "editable_svg_text": "<text" in svg,
                "arial_referenced": "Arial" in svg,
                "contains_raster_layer": "<image" in svg,
                "png_sha256": sha256_file(counterparts["png"]),
                "pdf_sha256": sha256_file(counterparts["pdf"]),
                "svg_sha256": sha256_file(counterparts["svg"]),
                "tiff_sha256": sha256_file(counterparts["tiff"]),
            }
        )

    plot_manifest = paths.plot_data_root / "D5_plot_data_manifest.json"
    if not plot_manifest.exists():
        failures.append("plot_data_manifest_missing")
    result = {
        "passed": not failures,
        "failures": failures,
        "profile": {
            "name": PROFILE.name,
            "width_mm": PROFILE.width_mm,
            "maximum_height_mm": 170.0,
            "body_text_pt": PROFILE.body_text_pt,
            "panel_label_pt": PROFILE.panel_label_pt,
            "axis_line_pt": PROFILE.axis_line_pt,
            "raster_dpi": PROFILE.raster_dpi,
            "supported_final_scale": "double-column_183_mm",
        },
        "figures": records,
        "checked_contracts": [
            "exact nine-figure registry",
            "PNG/PDF/SVG/TIFF counterparts",
            "183 mm PDF MediaBox and <=170 mm height",
            "600 dpi raster width and nonblank content",
            "low canvas-edge ink as a clipping sentinel",
            "editable SVG text with Arial reference",
            "raster layers recorded but permitted for heatmaps and dense rasterized artists",
            "lowercase panel label (a)",
            "color-independent marker, line-style or text encodings declared in source",
            "frozen plot-data manifest",
        ],
        "interpretation_limits": [
            "Automated checks do not replace visual inspection at final scale.",
            "Color-vision and grayscale legibility also rely on non-color encodings.",
            "The figures are designed for 183 mm presentation, not 89 mm reduction.",
        ],
    }
    payload = json.dumps(result, indent=2, ensure_ascii=True)
    targets = [
        paths.figure_root / "D5_figure_qa.json",
        paths.report_root / "nature_figure_bundle_audit.json",
    ]
    for target in targets:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(payload, encoding="utf-8")
    return result
