from __future__ import annotations

import argparse
from pathlib import Path

from src.finalize import finalize_run


def main() -> None:
    parser = argparse.ArgumentParser(description="Render and hash an existing D1 challenger run")
    parser.add_argument("run_id")
    args = parser.parse_args()
    challenger_root = Path(__file__).resolve().parent
    output_dir = challenger_root / "outputs" / args.run_id
    finalize_run(challenger_root, output_dir)
    print(f"Finalized: {output_dir}")


if __name__ == "__main__":
    main()
