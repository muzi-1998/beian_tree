"""src/config/loader.py — YAML config loading (UTF-8 safe on Windows).

The plan (§6.2, §7.5) mandates config-driven, reproducible runs. We keep the
loader light (plain dicts) but always read UTF-8 so Chinese comments don't
crash on GBK default-encoded Windows hosts.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import yaml


def load_yaml(path: str | Path) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def load_configs(config_dir: str | Path = "configs") -> dict:
    """Load paths / deperiodise / whiten configs into one dict."""
    cd = Path(config_dir)
    return {
        "paths": load_yaml(cd / "paths.yaml"),
        "deperiodise": load_yaml(cd / "deperiodise.yaml"),
        "whiten": load_yaml(cd / "whiten.yaml"),
    }


def config_hash(cfg: dict) -> str:
    """Stable short hash of the merged config (run-manifest provenance)."""
    blob = json.dumps(cfg, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:12]
