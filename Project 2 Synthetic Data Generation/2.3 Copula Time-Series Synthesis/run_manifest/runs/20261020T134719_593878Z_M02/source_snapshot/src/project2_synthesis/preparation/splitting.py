"""Calendar splits and contiguous technical support; no fitting or filling."""
from __future__ import annotations

import numpy as np
import pandas as pd


def split_ids(index: pd.DatetimeIndex, study: dict) -> np.ndarray:
    labels = np.full(len(index), "outside_target", dtype=object)
    for item in study["splits"]:
        left = pd.Timestamp(item["start"], tz=study["timezone"])
        right = pd.Timestamp(item["end"], tz=study["timezone"]) + pd.Timedelta(days=1)
        labels[(index >= left) & (index < right)] = item["id"]
    return labels


def contiguous_blocks(index: pd.DatetimeIndex, valid: np.ndarray, profile: str) -> tuple[np.ndarray, list[dict]]:
    """A missing/invalid minute breaks the block; block size is not independence."""
    ids = np.full(len(index), None, dtype=object)
    records = []
    start = None
    for i in range(len(index) + 1):
        active = i < len(index) and bool(valid[i])
        contiguous = i > 0 and i < len(index) and index[i] - index[i - 1] == pd.Timedelta(minutes=1)
        if start is not None and (not active or not contiguous):
            block_id = f"{profile}_{len(records) + 1:06d}"
            ids[start:i] = block_id
            records.append({"block_id": block_id, "support_profile": profile,
                            "start": index[start], "end_exclusive": index[i - 1] + pd.Timedelta(minutes=1),
                            "archive_rows": i - start, "fresh_count": None,
                            "independence_status": "not_assessed"})
            start = None
        if active and start is None:
            start = i
    return ids, records
