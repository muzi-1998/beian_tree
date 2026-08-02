from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from .common import CONFIG_ROOT, PROJECT_ROOT, config_paths, read_yaml, sha256_file


def build_temporal_split_registry() -> pd.DataFrame:
    sap = read_yaml(CONFIG_ROOT / "statistical_analysis_plan_v2.yaml")
    study_start = pd.Timestamp("2025-08-01 00:00:00")
    rows: list[dict[str, Any]] = []
    for item in sap["temporal_validation"]["outer_test_blocks"]:
        test_start = pd.Timestamp(item["test_start"])
        test_end = pd.Timestamp(item["test_end"])
        rows.append(
            {
                "fold_id": item["fold_id"],
                "train_start": study_start,
                "train_end": pd.Timestamp(item["train_end"]),
                "test_start": test_start,
                "test_end": test_end,
                "test_duration_hours": int((test_end - test_start) / pd.Timedelta(hours=1)) + 1,
                "split_type": "expanding_blocked_walk_forward",
                "terminal_status": "reviewed_retrospective_not_untouched",
            }
        )
    return pd.DataFrame(rows)


def source_artifact_registry() -> pd.DataFrame:
    artifacts = [
        ("D1", "D1 Sensor health/outputs/data/D1_main_scores_min.xlsx", "D1_total"),
        ("D2", "D2 Temporal Continuity & Information Availability/artifacts/data/D2_main_scores_hourly.xlsx", "D2_total"),
        ("D3", "D3 Physical rationality and rate constraints/outputs/data/D3_window_scores.xlsx", "D3_gate_source"),
        ("D4", "D4 Parallel-redundancy Temporal Consistency/outputs/data/D4_main_scores.xlsx", "D4_raw"),
        ("D5", "D5 Topological Role Consistency and Structural Representativeness/outputs/local/D5_report_interface.parquet", "D5_report_score"),
    ]
    rows = []
    for dimension, relative, role in artifacts:
        path = PROJECT_ROOT / relative
        rows.append(
            {
                "dimension": dimension,
                "relative_path": relative,
                "role": role,
                "exists": path.exists(),
                "size_bytes": path.stat().st_size if path.exists() else 0,
                "sha256": sha256_file(path) if path.exists() else None,
            }
        )
    return pd.DataFrame(rows)


def config_registry() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "relative_path": path.relative_to(PROJECT_ROOT).as_posix(),
                "sha256": sha256_file(path),
            }
            for path in config_paths()
        ]
    )

