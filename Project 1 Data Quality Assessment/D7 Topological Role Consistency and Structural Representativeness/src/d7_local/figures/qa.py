from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image

from d7_common.config import resolve_paths
from d7_local.outputs.manifest import sha256_file


def run_figure_qa() -> dict[str, object]:
    paths = resolve_paths()
    failures: list[str] = []
    records = []
    figures = {
        "FigD7_1_framework": ["(a)", "(b)", "(c)"],
        "FigD7_2_spatiotemporal": ["(a)", "(b)", "(c)"],
        "FigD7_3_evidence": ["(a)", "(b)", "(c)"],
        "FigD7_4_validation": ["(a)", "(b)", "(c)", "(d)"],
        "FigD7_5_governance": ["(a)", "(b)", "(c)", "(d)"],
    }
    for stem, panel_labels in figures.items():
        counterparts = {
            suffix: paths.figure_root / f"{stem}.{suffix}"
            for suffix in ["png", "tiff", "pdf", "svg"]
        }
        for path in counterparts.values():
            if not path.exists() or path.stat().st_size == 0:
                failures.append(f"missing_or_empty:{path.name}")
        if not all(path.exists() for path in counterparts.values()):
            continue
        image = Image.open(counterparts["png"]).convert("RGB")
        array = np.asarray(image)
        nonwhite_fraction = float((array < 248).any(axis=2).mean())
        if image.width < 4250 or image.height < 2000:
            failures.append(f"insufficient_600dpi_dimensions:{stem}:{image.size}")
        width_mm = image.width / 600 * 25.4
        if not 180.0 <= width_mm <= 186.0:
            failures.append(f"unexpected_final_width_mm:{stem}:{width_mm:.2f}")
        if nonwhite_fraction < 0.03:
            failures.append(f"near_blank:{stem}:{nonwhite_fraction:.4f}")
        tiff = Image.open(counterparts["tiff"])
        if tiff.size != image.size:
            failures.append(f"png_tiff_dimension_mismatch:{stem}:{image.size}:{tiff.size}")
        svg = counterparts["svg"].read_text(encoding="utf-8")
        if "Arial" not in svg:
            failures.append(f"arial_not_embedded_or_referenced:{stem}")
        if "<text" not in svg:
            failures.append(f"editable_svg_text_missing:{stem}")
        for label in panel_labels:
            if label not in svg:
                failures.append(f"panel_label_missing:{stem}:{label}")
        records.append(
            {
                "stem": stem,
                "png_width": image.width,
                "png_height": image.height,
                "final_width_mm_at_600dpi": width_mm,
                "nonwhite_fraction": nonwhite_fraction,
                "png_sha256": sha256_file(counterparts["png"]),
                "tiff_sha256": sha256_file(counterparts["tiff"]),
                "pdf_sha256": sha256_file(counterparts["pdf"]),
                "svg_sha256": sha256_file(counterparts["svg"]),
            }
        )
    plot_manifest = paths.plot_data_root / "D7_plot_data_manifest.json"
    if not plot_manifest.exists():
        failures.append("plot_data_manifest_missing")
    else:
        manifest = json.loads(plot_manifest.read_text(encoding="utf-8"))
        if manifest.get("rendering_samples_removed") != 0:
            failures.append("plot_data_contains_rendering_sample_exclusions")
    result = {
        "passed": not failures,
        "failures": failures,
        "figures": records,
        "checked_contracts": [
            "PNG/TIFF/PDF/SVG counterparts",
            "600 dpi raster dimensions",
            "183 mm final figure width",
            "nonblank raster content",
            "Arial editable SVG text",
            "complete panel-label sequence",
            "frozen plot-data manifest",
            "no rendering-convenience sampling",
        ],
    }
    target = paths.figure_root / "D7_figure_qa.json"
    target.write_text(json.dumps(result, indent=2, ensure_ascii=True), encoding="utf-8")
    return result
