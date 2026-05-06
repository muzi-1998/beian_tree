"""src/config/loader.py — load YAML configs and validate via dataclass models."""
from __future__ import annotations
import yaml
from pathlib import Path
from .models import (
    ProjectConfig, WindowConfig, MappingConfig, RulesConfig, PathsConfig,
)


def _load_yaml(p: Path):
    with open(p, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_project_config(config_dir: str = "/home/claude/d1_fsd/configs") -> ProjectConfig:
    cdir = Path(config_dir)
    return ProjectConfig(
        windows=WindowConfig.from_dict(_load_yaml(cdir / "windows.yaml")),
        mapping=MappingConfig.from_dict(_load_yaml(cdir / "mapping.yaml")),
        rules=RulesConfig.from_dict(_load_yaml(cdir / "rules.yaml")),
        paths=PathsConfig.from_dict(_load_yaml(cdir / "paths.yaml")),
    )
