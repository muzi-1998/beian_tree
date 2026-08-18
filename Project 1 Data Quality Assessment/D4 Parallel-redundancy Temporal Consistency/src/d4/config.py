from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class PairConfig:
    pair_id: str
    target: str
    reference: str
    zone: str

    @property
    def variable(self) -> str:
        return self.target.split("_", 1)[0]


@dataclass(frozen=True)
class D4Config:
    version: str
    window_hours: int
    step_hours: int
    analysis_interval_minutes: int
    min_valid_fraction: float
    phase_contract: dict[str, Any]
    common_support: dict[str, Any]
    distribution: dict[str, Any]
    pairs: tuple[PairConfig, ...]
    deadband: dict[str, float]
    weights: dict[str, float]
    lambda_blend: float
    change_point: dict[str, Any]
    benchmark: dict[str, Any]
    arbitration: dict[str, Any]
    classification: dict[str, Any]
    paths: dict[str, Path]


def load_config(path: Path, project_root: Path) -> D4Config:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    weights = {k: float(v) for k, v in raw["aggregation"]["weights"].items()}
    if set(weights) != {"dist", "trend", "var", "cp"}:
        raise ValueError("D4 aggregation must define dist/trend/var/cp weights")
    if abs(sum(weights.values()) - 1.0) > 1e-9:
        raise ValueError("D4 aggregation weights must sum to 1")
    pairs = tuple(PairConfig(**item) for item in raw["pairs"])
    if len({p.pair_id for p in pairs}) != len(pairs):
        raise ValueError("pair_id values must be unique")
    paths = {key: (project_root / value).resolve() for key, value in raw["paths"].items()}
    return D4Config(
        version=str(raw["version"]),
        window_hours=int(raw["window_hours"]),
        step_hours=int(raw["step_hours"]),
        analysis_interval_minutes=int(raw["analysis_interval_minutes"]),
        min_valid_fraction=float(raw["min_valid_fraction"]),
        phase_contract=raw["phase_contract"],
        common_support=raw["common_support"],
        distribution=raw["distribution"],
        pairs=pairs,
        deadband={k: float(v) for k, v in raw["deadband"].items()},
        weights=weights,
        lambda_blend=float(raw["aggregation"]["lambda_blend"]),
        change_point=raw["change_point"],
        benchmark=raw["benchmark"],
        arbitration=raw["arbitration"],
        classification=raw["classification"],
        paths=paths,
    )
