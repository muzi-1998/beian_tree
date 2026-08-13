from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd


D4_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(D4_ROOT / "src"))

from d4.episode_validation import run_episode_validation


if __name__ == "__main__":
    data_dir = D4_ROOT / "outputs" / "data"
    main = pd.read_excel(data_dir / "D4_main_scores.xlsx", sheet_name="main_scores")
    outputs = run_episode_validation(
        main, data_dir / "D4_event_duration_validation.xlsx"
    )
    print(outputs["do14_contrasts"].query("block_hours == 168").to_string(index=False))
