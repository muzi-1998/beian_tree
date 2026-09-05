"""Inventory trusted, local pre-holdout assets without opening later outcomes."""
from __future__ import annotations

import pickle
import sys
from pathlib import Path

import pandas as pd

from runtime import DIMENSIONS, LEGACY, OFFICIAL, OUTPUT, PROJECT, sha256, write_json


def describe(value: object, depth: int = 0) -> object:
    if isinstance(value, dict):
        if depth >= 2:
            return {"kind": "dict", "keys": [str(key) for key in value][:40]}
        return {str(key): describe(item, depth + 1) for key, item in value.items()}
    info: dict = {"kind": type(value).__name__}
    if isinstance(value, (pd.DataFrame, pd.Series)):
        info["shape"] = list(value.shape)
        if isinstance(value, pd.DataFrame):
            info["columns"] = list(value.columns[:60])
        if isinstance(value.index, pd.DatetimeIndex) and len(value):
            info["start"] = str(value.index.min())
            info["end"] = str(value.index.max())
    elif hasattr(value, "__dict__"):
        info["attributes"] = sorted(vars(value))
    elif isinstance(value, (list, tuple)):
        info["length"] = len(value)
        if value:
            info["first_kind"] = type(value[0]).__name__
    elif value is None or isinstance(value, (str, int, float, bool)):
        return value
    return info


def main() -> None:
    candidates = [
        ("1.1", LEGACY / "1.1 Decomposition/outputs/_w2_checkpoint.pkl"),
        ("1.1", LEGACY / "1.1 Decomposition/outputs/_pipeline_state.pkl"),
        ("D1", OFFICIAL / DIMENSIONS["D1"] / "strict_v1_inputs.pkl"),
        ("D1", OFFICIAL / DIMENSIONS["D1"] / "raw_hourly.pkl"),
        ("D1", OFFICIAL / DIMENSIONS["D1"] / "v11_state.pkl"),
    ]
    # Only researcher-owned local caches are deserialized, never downloaded pickle.
    sys.path.insert(0, str(PROJECT / DIMENSIONS["D1"]))
    rows = []
    for dimension, path in candidates:
        row = {"dimension": dimension, "path": str(path), "exists": path.is_file()}
        if path.is_file():
            row.update(sha256=sha256(path), size_bytes=path.stat().st_size)
            try:
                with path.open("rb") as handle:
                    data = pickle.load(handle)
                row["contents"] = describe(data)
                row["read_status"] = "readable_not_yet_release_verified"
                del data
            except (ImportError, AttributeError, ValueError, pickle.UnpicklingError) as exc:
                row["read_status"] = "incompatible_cache_requires_historical_rebuild"
                row["error"] = f"{type(exc).__name__}: {exc}"
        rows.append(row)
        print(dimension, path.name, row.get("read_status", "missing"), flush=True)
    files = []
    for dimension, name in DIMENSIONS.items():
        root = PROJECT / name
        for path in sorted((root / "configs").rglob("*.yaml")):
            files.append({"dimension": dimension, "role": "configuration",
                          "path": path.relative_to(PROJECT).as_posix(),
                          "sha256_raw_bytes": sha256(path)})
    result = {"schema": "temporal-frozen-inventory-1.0",
              "holdout_scores_computed": False, "pickle_assets": rows,
              "configuration_files": files}
    write_json(OUTPUT / "audit/frozen_asset_inventory.json", result)


if __name__ == "__main__":
    main()
