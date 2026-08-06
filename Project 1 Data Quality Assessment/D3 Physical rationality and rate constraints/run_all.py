"""Validate, run, and render the complete D3 v2.3 project."""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path


ROOT = Path(__file__).parent.resolve()


def run(command: list[str]) -> None:
    print(f"$ {' '.join(command)}", flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-pipeline", action="store_true")
    parser.add_argument("--subset-days", type=int)
    parser.add_argument("--window-min", type=int, default=120)
    parser.add_argument("--stride-min", type=int, default=120)
    args = parser.parse_args()
    started = time.time()

    run([sys.executable, "ci/check_d3_imports.py"])
    run([sys.executable, "-m", "pytest", "tests/test_v23_contracts.py", "-q"])

    if not args.skip_pipeline:
        pipeline = [
            sys.executable,
            "run_d3.py",
            "--window-min",
            str(args.window_min),
            "--stride-min",
            str(args.stride_min),
        ]
        if args.subset_days is not None:
            pipeline.extend(["--subset-days", str(args.subset_days)])
        run(pipeline)

    scripts = [
        "fig1_framework_overview.py",
        "fig2_score_landscape.py",
        "fig3_evidence_coverage.py",
        "fig4_persistent_rate_construct.py",
        "fig5_boundary_fixed_threshold.py",
        "fig6_gate_and_directional_profile.py",
        "fig7_case_studies.py",
        "fig8_boundary_rate_validation.py",
    ]
    for script in scripts:
        run([sys.executable, str(Path("figures") / script)])

    run([sys.executable, "ci/audit_figure_bundle.py"])

    print(f"D3 v2.3.0 complete in {time.time() - started:.1f} s")
    print(f"Data: {ROOT / 'outputs' / 'data'}")
    print(f"Figures: {ROOT / 'outputs' / 'figures'}")
    print(f"Manifest: {ROOT / 'outputs' / 'manifest' / 'run_manifest.json'}")
    print(f"Figure audit: {ROOT / 'outputs' / 'reports' / 'nature_figure_bundle_audit.json'}")


if __name__ == "__main__":
    main()
