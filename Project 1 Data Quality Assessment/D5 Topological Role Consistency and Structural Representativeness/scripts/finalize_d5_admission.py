from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from d5_local.validation.admission import finalize_d5_admission


if __name__ == "__main__":
    print(json.dumps(finalize_d5_admission(), indent=2, ensure_ascii=True))
