from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(script: str) -> None:
    subprocess.run([sys.executable, str(ROOT / "scripts" / script)], cwd=ROOT, check=True)


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
        "make_d7_figures.py",
        "build_d7_reports.py",
        "check_d7_release.py",
        "build_d7_reports.py",
        "check_d7_release.py",
    ]:
        run(script)
    subprocess.run([sys.executable, "-m", "pytest", "tests", "-q"], cwd=ROOT, check=True)
