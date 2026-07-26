from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


D5_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = D5_ROOT.parent


def load_yaml(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Expected a mapping in {path}")
    return data


@dataclass(frozen=True)
class D5Paths:
    project_root: Path
    d5_root: Path
    canonical_observations: Path
    canonical_flags: Path
    time_base_contract: Path
    d1_scores: Path
    d2_scores: Path
    d3_scores: Path
    d4_scores: Path
    local_output_root: Path
    sensitivity_output_root: Path
    shadow_v2_output_root: Path
    plot_data_root: Path
    figure_root: Path
    report_root: Path


def resolve_paths() -> D5Paths:
    raw = load_yaml(D5_ROOT / "configs" / "common" / "paths.yaml")

    def project_path(key: str) -> Path:
        path = Path(raw[key])
        return path if path.is_absolute() else PROJECT_ROOT / path

    return D5Paths(
        project_root=PROJECT_ROOT,
        d5_root=D5_ROOT,
        canonical_observations=project_path("canonical_observations"),
        canonical_flags=project_path("canonical_flags"),
        time_base_contract=project_path("time_base_contract"),
        d1_scores=project_path("d1_scores"),
        d2_scores=project_path("d2_scores"),
        d3_scores=project_path("d3_scores"),
        d4_scores=project_path("d4_scores"),
        local_output_root=project_path("local_output_root"),
        sensitivity_output_root=project_path("sensitivity_output_root"),
        shadow_v2_output_root=project_path("shadow_v2_output_root"),
        plot_data_root=project_path("plot_data_root"),
        figure_root=project_path("figure_root"),
        report_root=project_path("report_root"),
    )
