"""src/config/loader.py — load YAML configs and validate via dataclass models."""
from __future__ import annotations
import yaml
from pathlib import Path
from .models import ProjectConfig, WindowConfig, MappingConfig

# Two levels up from src/config/ → project root
_PROJECT_ROOT = Path(__file__).parents[2]


def _load_yaml(p: Path) -> dict:
    with open(p, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_project_config(config_dir: "str | Path | None" = None) -> ProjectConfig:
    """Load all YAML configs.

    config_dir defaults to <project_root>/configs so the project works
    on any machine without editing paths.
    """
    if config_dir is None:
        config_dir = _PROJECT_ROOT / "configs"
    cdir = Path(config_dir)

    # windows.yaml has a top-level "windows:" wrapper — strip it before parsing
    raw_windows = _load_yaml(cdir / "windows.yaml")
    windows_dict = raw_windows.get("windows", raw_windows)

    return ProjectConfig(
        windows       = WindowConfig.from_dict(windows_dict),
        mapping       = MappingConfig.from_dict(_load_yaml(cdir / "mapping.yaml")),
        rules         = _load_yaml(cdir / "rules.yaml"),         # raw dict
        state_machine = _load_yaml(cdir / "state_machine.yaml"), # raw dict
        paths         = _load_yaml(cdir / "paths.yaml"),         # raw dict
    )
