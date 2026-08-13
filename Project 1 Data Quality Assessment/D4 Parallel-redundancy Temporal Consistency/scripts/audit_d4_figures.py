"""Audit the D4 publication figure bundle and its traceable source data."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import numpy as np
from PIL import Image


D4_ROOT = Path(__file__).resolve().parents[1]
FIGURES = D4_ROOT / "outputs" / "figures"
SOURCE_DATA = D4_ROOT / "outputs" / "figure_source_data"
REPORT = D4_ROOT / "outputs" / "qa" / "d4_figure_bundle_audit.json"
PLOT_SOURCE = D4_ROOT / "src" / "d4" / "figures.py"
STYLE_SOURCE = D4_ROOT / "src" / "d4" / "figure_style.py"
EXPECTED_STEMS = (
    "FigD4_1_scientific_construct",
    "FigD4_2_pair_mechanism_profile",
    "FigD4_3_burden_coverage_calibration",
    "FigD4_4_formal_episode_cases",
    "FigD4_5_mechanism_specificity",
    "FigD4_6_ablation_and_lag_resolution",
    "FigS1_all_pair_residual_trajectories",
    "FigS2_trend_concordance",
    "FigS3_numeric_independence_audit",
    "FigS4_distribution_construct_ablation",
    "FigS5_do14_episode_duration",
)
VALIDATOR_CANDIDATES = (
    (
        "environment",
        Path(os.environ["D4_NATURE_VALIDATOR"]).expanduser()
        if os.environ.get("D4_NATURE_VALIDATOR") else None,
    ),
    ("repository", D4_ROOT / "scripts" / "validate_figure.py"),
    (
        "installed_skill",
        Path.home() / ".codex" / "skills" / "nature-figure" / "scripts" / "validate_figure.py",
    ),
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _image_audit(path: Path) -> dict[str, object]:
    with Image.open(path) as image:
        rgb = np.asarray(image.convert("RGB"), dtype=np.float32)
    gray = rgb.mean(axis=2)
    nonwhite = float((gray < 250).mean())
    return {
        "width_px": int(rgb.shape[1]),
        "height_px": int(rgb.shape[0]),
        "pixel_std": float(gray.std()),
        "nonwhite_fraction": nonwhite,
        "nonblank": bool(gray.std() > 2.0 and nonwhite > 0.01),
    }


def main() -> None:
    failures: list[str] = []
    warnings: list[str] = []
    validator_source, validator = next(
        ((source, path) for source, path in VALIDATOR_CANDIDATES if path and path.exists()),
        (None, None),
    )
    preflight = {"status": "optional_validator_unavailable", "failures": 0, "warnings": 0}
    if validator:
        result = subprocess.run(
            [sys.executable, str(validator), str(PLOT_SOURCE), "--json"],
            check=False, capture_output=True, text=True, encoding="utf-8",
        )
        if result.stdout.strip():
            payload = json.loads(result.stdout)
            counts = payload.get("summary", {}).get("counts", {})
            preflight = {
                "status": "executed",
                "validator_source": validator_source,
                "failures": int(counts.get("FAIL", 0)),
                "warnings": int(counts.get("WARN", 0)),
            }
        else:
            preflight = {"status": "invalid_output", "failures": 1, "warnings": 0}
        if preflight["failures"]:
            failures.append(f"nature_preflight_fail:{preflight['failures']}")
        if preflight["warnings"]:
            warnings.append(f"nature_preflight_warn:{preflight['warnings']}")

    source_mtime = max(PLOT_SOURCE.stat().st_mtime, STYLE_SOURCE.stat().st_mtime)
    rows = []
    for stem in EXPECTED_STEMS:
        exports: dict[str, object] = {}
        for extension in ("svg", "pdf", "png", "tiff"):
            path = FIGURES / f"{stem}.{extension}"
            exists = path.exists() and path.stat().st_size > 0
            fresh = bool(exists and path.stat().st_mtime >= source_mtime)
            exports[extension] = {
                "exists": exists,
                "fresh": fresh,
                "bytes": path.stat().st_size if exists else 0,
                "sha256": _sha256(path) if exists else None,
            }
            if not exists:
                failures.append(f"missing:{path.name}")
            elif not fresh:
                failures.append(f"stale:{path.name}")
        workbook = SOURCE_DATA / f"{stem}_source_data.xlsx"
        workbook_exists = workbook.exists() and workbook.stat().st_size > 0
        if not workbook_exists:
            failures.append(f"missing:{workbook.name}")
        png_path = FIGURES / f"{stem}.png"
        image = _image_audit(png_path) if png_path.exists() else {"nonblank": False}
        if not image["nonblank"]:
            failures.append(f"blank:{png_path.name}")
        svg_path = FIGURES / f"{stem}.svg"
        svg = svg_path.read_text(encoding="utf-8") if svg_path.exists() else ""
        svg_checks = {
            "editable_text": "<text" in svg,
            "arial_declared": "Arial" in svg,
            "panel_a_present": "(a)" in svg,
        }
        for check, passed in svg_checks.items():
            if not passed:
                failures.append(f"{check}:{svg_path.name}")
        rows.append(
            {
                "stem": stem,
                "role": "main" if stem.startswith("FigD4") else "supplementary",
                "exports": exports,
                "source_data": {
                    "exists": workbook_exists,
                    "bytes": workbook.stat().st_size if workbook_exists else 0,
                    "sha256": _sha256(workbook) if workbook_exists else None,
                },
                "png": image,
                "svg": svg_checks,
            }
        )

    observed_stems = {path.stem for path in FIGURES.glob("*.png")}
    expected_set = set(EXPECTED_STEMS)
    unexpected = sorted(observed_stems - expected_set)
    missing = sorted(expected_set - observed_stems)
    if unexpected:
        failures.extend(f"unexpected_png:{stem}" for stem in unexpected)
    if missing:
        failures.extend(f"missing_png:{stem}" for stem in missing)

    report = {
        "audit_version": "d4-nature-figure-audit-v1.0",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "backend": "python",
        "figure_contract": {"main": 6, "supplementary": 5, "observed": len(rows)},
        "nature_preflight": preflight,
        "unexpected_png_stems": unexpected,
        "missing_png_stems": missing,
        "failures": failures,
        "warnings": warnings,
        "passed": not failures,
        "figures": rows,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("figure_contract", "passed", "failures", "warnings")}, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
