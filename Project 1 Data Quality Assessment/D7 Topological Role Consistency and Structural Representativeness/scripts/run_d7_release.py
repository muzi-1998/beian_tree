from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parent
D6_ROOT = PROJECT_ROOT / "D6 Parallel-redundancy Temporal Consistency"


def run(script: str) -> None:
    subprocess.run([sys.executable, str(ROOT / "scripts" / script)], cwd=ROOT, check=True)


def run_d6_readiness() -> None:
    subprocess.run(
        [
            sys.executable,
            str(D6_ROOT / "scripts" / "run_d6_d7_readiness.py"),
        ],
        cwd=D6_ROOT,
        check=True,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rebuild the complete D7 review release")
    parser.add_argument("--include-local", action="store_true")
    args = parser.parse_args()
    if args.include_local:
        run("run_d7_local.py")
    for script in [
        "run_d7_sensitivity.py",
        "run_d7_validation.py",
        "finalize_d7_admission.py",
        "run_d7_topology_review.py",
        "run_d7_shadow_v2.py",
    ]:
        run(script)
    run_d6_readiness()
    for script in [
        "make_d7_figures.py",
        "build_d7_reports.py",
        "check_d7_release.py",
        "build_d7_reports.py",
        "check_d7_release.py",
    ]:
        run(script)
    subprocess.run([sys.executable, "-m", "pytest", "tests", "-q"], cwd=ROOT, check=True)
