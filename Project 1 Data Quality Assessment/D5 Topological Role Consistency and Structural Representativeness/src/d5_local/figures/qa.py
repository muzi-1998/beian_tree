from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image

from d5_common.config import resolve_paths
from d5_local.outputs.manifest import sha256_file


def run_figure_qa() -> dict[str, object]:
    paths = resolve_paths()
    failures: list[str] = []
    records = []
    stems = [f"FigD5_{index}_{name}" for index, name in [
        (1, "framework"), (2, "spatiotemporal"), (3, "evidence"),
        (4, "validation"), (5, "governance"),
    ]]
    for stem in stems:
        counterparts = [
            paths.figure_root / f"{stem}.{suffix}"
            for suffix in ["png", "pdf", "svg", "tiff"]
        ]
        for path in counterparts:
            if not path.exists() or path.stat().st_size == 0:
                failures.append(f"missing_or_empty:{path.name}")
        if not all(path.exists() for path in counterparts):
            continue
        image = Image.open(counterparts[0]).convert("RGB")
        array = np.asarray(image)
        nonwhite_fraction = float((array < 248).any(axis=2).mean())
        if image.width < 2500 or image.height < 1400:
            failures.append(f"insufficient_600dpi_dimensions:{stem}:{image.size}")
        if nonwhite_fraction < 0.03:
            failures.append(f"near_blank:{stem}:{nonwhite_fraction:.4f}")
        svg = counterparts[2].read_text(encoding="utf-8")
        if "Arial" not in svg:
            failures.append(f"arial_not_embedded_or_referenced:{stem}")
        if "(a)" not in svg:
            failures.append(f"panel_label_missing:{stem}")
        records.append(
            {
                "stem": stem,
                "png_width": image.width,
                "png_height": image.height,
                "nonwhite_fraction": nonwhite_fraction,
                "png_sha256": sha256_file(counterparts[0]),
                "pdf_sha256": sha256_file(counterparts[1]),
                "svg_sha256": sha256_file(counterparts[2]),
                "tiff_sha256": sha256_file(counterparts[3]),
            }
        )
    plot_manifest = paths.plot_data_root / "D5_plot_data_manifest.json"
    if not plot_manifest.exists():
        failures.append("plot_data_manifest_missing")
    result = {
        "passed": not failures,
        "failures": failures,
        "figures": records,
        "checked_contracts": [
            "PNG/PDF/SVG/TIFF counterparts",
            "600 dpi raster dimensions",
            "nonblank raster content",
            "Arial SVG font reference",
            "panel label (a)",
            "frozen plot-data manifest",
        ],
    }
    target = paths.figure_root / "D5_figure_qa.json"
    target.write_text(json.dumps(result, indent=2, ensure_ascii=True), encoding="utf-8")
    return result
