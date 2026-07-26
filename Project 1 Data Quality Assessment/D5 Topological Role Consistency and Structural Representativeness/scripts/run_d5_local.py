from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
os.environ.setdefault("LOKY_MAX_CPU_COUNT", "16")

from d5_local.pipeline import D5Pipeline  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the D5 v2.2 Local Track")
    parser.add_argument(
        "--max-input-rows",
        type=int,
        default=None,
        help="Optional deterministic prefix for smoke tests; omit for release runs.",
    )
    args = parser.parse_args()
    result = D5Pipeline(max_input_rows=args.max_input_rows).run()
    print(
        json.dumps(
            {
                "run_id": result.run_id,
                "output_root": str(result.output_root),
                "main_rows": len(result.main_scores),
                "events": len(result.events),
                "acceptance_status": result.acceptance_status,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
