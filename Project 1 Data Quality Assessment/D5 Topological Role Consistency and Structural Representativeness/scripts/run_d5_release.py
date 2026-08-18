from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parent
D4_ROOT = PROJECT_ROOT / "D4 Parallel-redundancy Temporal Consistency"


def run(script: str) -> None:
    subprocess.run([sys.executable, str(ROOT / "scripts" / script)], cwd=ROOT, check=True)


def run_d4_readiness() -> None:
    subprocess.run(
        [
            sys.executable,
            str(D4_ROOT / "scripts" / "run_d4_d5_readiness.py"),
        ],
        cwd=D4_ROOT,
        check=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rebuild the complete D5 review release")
    parser.add_argument("--include-local", action="store_true")
    args = parser.parse_args()
    if args.include_local:
        run("run_d5_local.py")
    for script in [
        "run_d5_sensitivity.py",
        "run_d5_validation.py",
        "finalize_d5_admission.py",
        "run_d5_topology_review.py",
        "run_d5_shadow_v2.py",
        "run_d5_publication_audit.py",
    ]:
        run(script)
    run_d4_readiness()
    for script in [
        "make_d5_figures.py",
        "build_d5_reports.py",
        "check_d5_release.py",
        "build_d5_reports.py",
        "check_d5_release.py",
    ]:
        run(script)
    subprocess.run([sys.executable, "-m", "pytest", "tests", "-q"], cwd=ROOT, check=True)
