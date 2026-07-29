from __future__ import annotations

import json
import platform
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .common import (
    CONFIG_ROOT,
    PROJECT_ROOT,
    build_run_id,
    code_paths,
    config_paths,
    ensure_run_dir,
    git_commit,
    json_dump,
    sha256_file,
    sha256_paths,
)
from .composite import run_composite
from .d1_validation import run_d1_validation
from .d2_sensitivity import run_d2_sensitivity
from .d3_safety_gate import run_d3_sensitivity
from .d4_validation import run_d4_validation
from .d5_validation import run_d5_validation
from .figures import (
    figure_composite,
    figure_d1,
    figure_d2,
    figure_d3,
    figure_d4_d5,
    write_figure_manifest,
)
from .framework import build_framework_figure
from .report import build_execution_report
from .wp0 import build_temporal_split_registry, config_registry, source_artifact_registry


def _artifact_manifest(output_dir: Path) -> list[dict[str, Any]]:
    rows = []
    for path in sorted(output_dir.rglob("*")):
        if path.is_file() and path.name != "run_manifest.json":
            rows.append(
                {
                    "relative_path": path.relative_to(output_dir).as_posix(),
                    "size_bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
    return rows


def run_confirmatory_v2() -> Path:
    run_id = build_run_id()
    output_dir = ensure_run_dir(run_id)
    manifest_path = output_dir / "run_manifest.json"
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if str(manifest.get("status", "")).startswith("completed"):
            return output_dir
    config_snapshot = output_dir / "configs"
    config_snapshot.mkdir(exist_ok=True)
    for path in config_paths():
        shutil.copy2(path, config_snapshot / path.name)

    split = build_temporal_split_registry()
    source_registry = source_artifact_registry()
    configs = config_registry()
    split.to_parquet(output_dir / "temporal_split_registry.parquet", index=False)
    source_registry.to_parquet(output_dir / "source_artifact_registry.parquet", index=False)
    configs.to_parquet(output_dir / "config_registry.parquet", index=False)

    d3 = run_d3_sensitivity(output_dir)
    d1 = run_d1_validation(output_dir, d3["D3_safety_gate"])
    d2 = run_d2_sensitivity(output_dir)
    d4 = run_d4_validation(output_dir)
    d5 = run_d5_validation(output_dir)
    composite = run_composite(output_dir, d3["D3_safety_gate"])

    figure_dir = output_dir / "figures"
    figure_dir.mkdir(exist_ok=True)
    framework_stem, framework_audit = build_framework_figure(figure_dir)
    figure_stems = [
        framework_stem,
        *figure_d1(d1, figure_dir),
        *figure_d2(d2, figure_dir),
        *figure_d3(d3, figure_dir),
        *figure_d4_d5(d4, d5, figure_dir),
        *figure_composite(composite, figure_dir),
    ]
    source_paths = sorted(output_dir.glob("*.parquet"))
    write_figure_manifest(figure_dir, figure_stems, source_paths, run_id)
    build_execution_report(output_dir, run_id, d1, d2, d3, d4, d5, composite)

    manifest = {
        "schema_version": "ww-dqs-confirmatory-run-v2.0",
        "run_id": run_id,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "status": "completed_with_prespecified_pending_items",
        "code_commit": git_commit(),
        "python_version": sys.version,
        "platform": platform.platform(),
        "config_bundle_sha256": sha256_paths(config_paths()),
        "code_bundle_sha256": sha256_paths(code_paths()),
        "source_artifacts": source_registry.to_dict(orient="records"),
        "temporal_validation": {
            "outer_folds": len(split),
            "untouched_terminal_test": False,
        },
        "framework_audit": framework_audit,
        "artifacts": _artifact_manifest(output_dir),
    }
    json_dump(output_dir / "run_manifest.json", manifest)
    return output_dir
