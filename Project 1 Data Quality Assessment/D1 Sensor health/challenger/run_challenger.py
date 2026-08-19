from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path

from src.validation import run
from src.finalize import finalize_run


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the isolated D1 challenger validation")
    parser.add_argument("--run-id", default=None, help="Optional immutable output directory name")
    args = parser.parse_args()
    challenger_root = Path(__file__).resolve().parent
    project_root = challenger_root.parents[1]
    run_id = args.run_id or datetime.now().strftime("D1C-%Y%m%d-%H%M%S")
    output_dir = challenger_root / "outputs" / run_id
    result = run(project_root, output_dir)
    finalize_run(challenger_root, output_dir)
    print(f"Run complete: {output_dir}")
    print(result["validation"].to_string(index=False))


if __name__ == "__main__":
    main()
