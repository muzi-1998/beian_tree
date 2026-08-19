from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml


DQR_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = DQR_ROOT.parent
CONFIG_PATH = DQR_ROOT / "configs" / "aggregation_v2.yaml"
OUTPUT_ROOT = DQR_ROOT / "outputs" / "aggregation_v2"


def load_config() -> dict[str, Any]:
    payload = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("aggregation_v2.yaml must contain a mapping")
    return payload


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text_lf(path: Path) -> str:
    """Hash UTF-8 text after newline normalization for cross-platform provenance."""
    text = path.read_text(encoding="utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def generation_configuration_record() -> dict[str, str]:
    return {
        "path": CONFIG_PATH.relative_to(PROJECT_ROOT).as_posix(),
        "sha256": sha256_text_lf(CONFIG_PATH),
        "hash_method": "sha256_utf8_lf_canonical",
    }


def generation_source_registry() -> list[dict[str, str]]:
    source_paths = [
        *Path(__file__).parent.glob("*.py"),
        *(DQR_ROOT / "scripts").glob("*.py"),
    ]
    return [
        {
            "path": path.relative_to(PROJECT_ROOT).as_posix(),
            "sha256": sha256_text_lf(path),
            "hash_method": "sha256_utf8_lf_canonical",
        }
        for path in sorted(source_paths)
    ]


def generation_content_sha256(
    configuration: dict[str, Any],
    code_sources: list[dict[str, Any]],
    input_registry: pd.DataFrame | list[dict[str, Any]],
) -> str:
    records = (
        input_registry.to_dict("records")
        if isinstance(input_registry, pd.DataFrame)
        else input_registry
    )
    inputs = [
        {
            key: record.get(key)
            for key in (
                "dimension",
                "artifact_role",
                "relative_path",
                "actual_sha256",
                "hash_method",
            )
        }
        for record in records
    ]
    payload = {
        "configuration": configuration,
        "code_sources": sorted(code_sources, key=lambda item: item["path"]),
        "frozen_inputs": sorted(
            inputs, key=lambda item: (item["dimension"], item["artifact_role"])
        ),
    }
    canonical = json.dumps(
        payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def stable_frame_hash(frame: pd.DataFrame) -> str:
    normalized = frame.copy()
    normalized.columns = normalized.columns.astype(str)
    for column in normalized.columns:
        if pd.api.types.is_datetime64_any_dtype(normalized[column]):
            normalized[column] = normalized[column].astype(str)
    payload = normalized.to_csv(index=False, float_format="%.12g", na_rep="<NA>")
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def git_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=PROJECT_ROOT,
            text=True,
            encoding="utf-8",
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "unavailable"


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True, default=str),
        encoding="utf-8",
    )


def expand_end_exclusive_windows(frame: pd.DataFrame) -> pd.DataFrame:
    """Expand whole-hour D3 windows onto the preceding covered hours."""
    required = {"timestamp", "sensor_id", "window_min", "D3_gate_status"}
    missing = sorted(required.difference(frame.columns))
    if missing:
        raise KeyError(f"D3 window fields missing: {missing}")
    blocks: list[pd.DataFrame] = []
    for duration_min, group in frame.groupby("window_min", sort=False):
        duration = int(duration_min)
        if duration <= 0 or duration % 60:
            raise ValueError(f"D3 window_min must be positive whole hours: {duration}")
        for hours_back in range(duration // 60, 0, -1):
            block = group.copy()
            block["source_window_end_exclusive"] = block["timestamp"]
            block["timestamp"] = block["timestamp"] - pd.Timedelta(hours=hours_back)
            blocks.append(block)
    if not blocks:
        return frame.iloc[0:0].copy()
    expanded = pd.concat(blocks, ignore_index=True)
    precedence = {"Pass": 0, "Warn": 1, "NotEvaluated": 2, "Fail": 3}
    expanded["_precedence"] = expanded["D3_gate_status"].map(precedence).fillna(2)
    return (
        expanded.sort_values("_precedence")
        .groupby(["timestamp", "sensor_id"], sort=False, as_index=False)
        .tail(1)
        .drop(columns="_precedence")
        .sort_values(["sensor_id", "timestamp"])
        .reset_index(drop=True)
    )


def arithmetic(values: np.ndarray, weights: np.ndarray | None = None) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    if weights is None:
        return np.nanmean(array, axis=1)
    weight_array = np.asarray(weights, dtype=float)
    valid = np.isfinite(array)
    numerator = np.nansum(array * weight_array, axis=1)
    denominator = np.sum(valid * weight_array, axis=1)
    return np.divide(
        numerator,
        denominator,
        out=np.full(len(array), np.nan),
        where=denominator > 0,
    )


def geometric(values: np.ndarray) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    return np.exp(np.nanmean(np.log(array), axis=1))


def soft_min(values: np.ndarray, tau: float) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    return -float(tau) * np.log(np.nanmean(np.exp(-array / float(tau)), axis=1))


def combine_gate(left: pd.Series, right: pd.Series) -> pd.Series:
    states = pd.DataFrame({"left": left, "right": right}).fillna("NotEvaluated")
    return pd.Series(
        np.select(
            [
                states.eq("Fail").any(axis=1),
                states.eq("NotEvaluated").any(axis=1),
                states.eq("Warn").any(axis=1),
            ],
            ["Fail", "NotEvaluated", "Warn"],
            default="Pass",
        ),
        index=states.index,
        dtype="object",
    )


def make_run_id(config: dict[str, Any]) -> str:
    payload = sha256_text_lf(CONFIG_PATH).encode("ascii")
    for source in generation_source_registry():
        payload += source["path"].encode("utf-8") + source["sha256"].encode("ascii")
    for spec in config["inputs"].values():
        for key, value in sorted(spec.items()):
            if key.startswith("expected_") and key.endswith("sha256"):
                payload += str(value).encode("ascii")
    return f"DQRAGG-V22-{hashlib.sha256(payload).hexdigest()[:12]}"
