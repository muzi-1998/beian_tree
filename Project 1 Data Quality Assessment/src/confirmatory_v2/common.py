from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd
import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_ROOT = PROJECT_ROOT / "configs" / "frozen_v2"
OUTPUT_ROOT = PROJECT_ROOT / "outputs" / "confirmatory"


def read_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_paths(paths: Iterable[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted((Path(item) for item in paths), key=lambda item: item.as_posix()):
        digest.update(path.as_posix().encode("utf-8"))
        digest.update(sha256_file(path).encode("ascii"))
    return digest.hexdigest()


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


def code_paths() -> list[Path]:
    return sorted((PROJECT_ROOT / "src" / "confirmatory_v2").glob("*.py"))


def config_paths() -> list[Path]:
    return sorted(CONFIG_ROOT.glob("*.yaml"))


def build_run_id() -> str:
    payload = sha256_paths([*config_paths(), *code_paths()])
    return f"D1D5V20-{payload[:12]}"


def ensure_run_dir(run_id: str) -> Path:
    target = OUTPUT_ROOT / run_id
    target.mkdir(parents=True, exist_ok=True)
    return target


def stable_frame_hash(frame: pd.DataFrame) -> str:
    ordered = frame.copy()
    ordered.columns = ordered.columns.astype(str)
    for column in ordered.select_dtypes(include=["datetime", "datetimetz"]).columns:
        ordered[column] = ordered[column].astype(str)
    payload = ordered.to_csv(index=False, float_format="%.12g", na_rep="<NA>")
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def json_dump(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=True, default=str),
        encoding="utf-8",
    )


def wilson_interval(successes: int, n: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if n <= 0:
        return np.nan, np.nan
    proportion = successes / n
    denominator = 1.0 + z * z / n
    center = (proportion + z * z / (2.0 * n)) / denominator
    half_width = z * np.sqrt(
        proportion * (1.0 - proportion) / n + z * z / (4.0 * n * n)
    ) / denominator
    return max(0.0, center - half_width), min(1.0, center + half_width)


def contiguous_event_ids(
    active: pd.Series,
    *,
    group: pd.Series | None = None,
    expected_step: pd.Timedelta = pd.Timedelta(hours=1),
) -> pd.Series:
    mask = active.fillna(False).astype(bool)
    if group is None:
        group = pd.Series("_all", index=active.index)
    time = pd.Series(pd.DatetimeIndex(active.index), index=active.index)
    gap = time.groupby(group).diff().ne(expected_step)
    start = mask & (~mask.groupby(group).shift(fill_value=False) | gap)
    event = start.groupby(group).cumsum()
    return event.where(mask)


def event_jaccard(left: pd.Series, right: pd.Series) -> float:
    left_mask = left.fillna(False).astype(bool)
    right_mask = right.fillna(False).astype(bool)
    union = (left_mask | right_mask).sum()
    return float((left_mask & right_mask).sum() / union) if union else 1.0


def moving_block_bootstrap_mean(
    values: np.ndarray,
    *,
    block_size: int,
    repetitions: int,
    rng: np.random.Generator,
) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    array = array[np.isfinite(array)]
    if not len(array):
        return np.full(repetitions, np.nan)
    block_size = min(max(1, int(block_size)), len(array))
    n_blocks = int(np.ceil(len(array) / block_size))
    offsets = np.arange(block_size)
    samples = np.empty(repetitions, dtype=float)
    for index in range(repetitions):
        starts = rng.integers(0, len(array), size=n_blocks)
        sample_index = ((starts[:, None] + offsets) % len(array)).reshape(-1)[: len(array)]
        samples[index] = float(np.mean(array[sample_index]))
    return samples

