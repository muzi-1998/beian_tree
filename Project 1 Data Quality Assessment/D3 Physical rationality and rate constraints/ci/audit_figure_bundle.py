"""Audit D3 publication figures, exports, and Nature static preflight."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
FIGURES = ROOT / "figures"
OUTPUT = ROOT / "outputs" / "figures"
REPORT = ROOT / "outputs" / "reports" / "nature_figure_bundle_audit.json"
VALIDATOR = Path.home() / ".codex" / "skills" / "nature-figure" / "scripts" / "validate_figure.py"

FIGURE_MAP = {
    "fig1_framework_overview.py": "fig1_framework_overview",
    "fig2_score_landscape.py": "fig2_score_landscape",
    "fig3_evidence_coverage.py": "fig3_evidence_coverage",
    "fig4_persistent_rate_construct.py": "fig4_persistent_rate_construct",
    "fig5_boundary_fixed_threshold.py": "fig5_boundary_fixed_threshold",
    "fig6_gate_and_directional_profile.py": "fig6_gate_and_directional_profile",
    "fig7_case_studies.py": "fig7_case_studies",
    "fig8_boundary_rate_validation.py": "fig8_boundary_rate_validation",
    "fig9_do4_zero_equivalence_contract.py": "fig9_do4_zero_equivalence_contract",
    "fig10_temperature_conditioned_do_upper.py": "fig10_temperature_conditioned_do_upper",
}


def _image_audit(path: Path) -> dict:
    with Image.open(path) as image:
        rgb = np.asarray(image.convert("RGB"), dtype=np.float32)
    gray = rgb.mean(axis=2)
    return {
        "width_px": int(rgb.shape[1]),
        "height_px": int(rgb.shape[0]),
        "pixel_std": float(gray.std()),
        "nonwhite_fraction": float((gray < 250).mean()),
        "nonblank": bool(gray.std() > 2.0 and (gray < 250).mean() > 0.01),
    }


def main() -> None:
    rows = []
    failures = []
    warnings = []
    for script_name, stem in FIGURE_MAP.items():
        script = FIGURES / script_name
        result = subprocess.run(
            [sys.executable, str(VALIDATOR), str(script), "--json"],
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        preflight = json.loads(result.stdout)
        counts = preflight.get("summary", {}).get("counts", {})
        fail_count = int(counts.get("FAIL", 0))
        warn_count = int(counts.get("WARN", 0))
        exports = {}
        for extension in ("svg", "pdf", "png", "tiff"):
            path = OUTPUT / f"{stem}.{extension}"
            exists = path.exists() and path.stat().st_size > 0
            exports[extension] = {
                "exists": exists,
                "bytes": path.stat().st_size if exists else 0,
                "newer_than_source": exists and path.stat().st_mtime >= script.stat().st_mtime,
            }
            if not exists:
                failures.append(f"missing:{path.name}")
            elif not exports[extension]["newer_than_source"]:
                failures.append(f"stale:{path.name}")
        image = _image_audit(OUTPUT / f"{stem}.png")
        if not image["nonblank"]:
            failures.append(f"blank:{stem}.png")
        svg_text = (OUTPUT / f"{stem}.svg").read_text(encoding="utf-8")
        svg_checks = {
            "arial_declared": "Arial" in svg_text,
            "editable_text": "<text" in svg_text,
            "panel_a_present": "(a)" in svg_text,
        }
        for check, passed in svg_checks.items():
            if not passed:
                failures.append(f"{check}:{stem}.svg")
        if fail_count:
            failures.append(f"preflight_fail:{script_name}:{fail_count}")
        if warn_count:
            warnings.append(f"preflight_warn:{script_name}:{warn_count}")
        rows.append(
            {
                "script": script_name,
                "stem": stem,
                "preflight_failures": fail_count,
                "preflight_warnings": warn_count,
                "exports": exports,
                "png": image,
                "svg": svg_checks,
            }
        )
    payload = {
        "audit_version": "d3-nature-figure-audit-v2.5.0",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "backend": "python",
        "n_figures": len(rows),
        "failures": failures,
        "warnings": warnings,
        "passed": not failures,
        "figures": rows,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    print(json.dumps({key: payload[key] for key in ("n_figures", "passed", "failures", "warnings")}, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
