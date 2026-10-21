"""Authorized archive-only pilot. No formal scale/model admission is performed."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))
from project2_synthesis.archive_sensitivity.runner import main

if __name__ == "__main__":
    raise SystemExit(main())
