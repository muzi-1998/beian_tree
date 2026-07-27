from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(
    output_root: Path,
    *,
    identity: dict[str, Any],
    study: dict[str, Any],
    scale: dict[str, Any],
    dependencies: list[dict[str, Any]],
    methods: dict[str, Any],
    scientific_boundaries: list[str],
    acceptance: dict[str, Any],
) -> dict[str, Any]:
    output_root = Path(output_root)
    artifacts = []
    for path in sorted(output_root.glob("D5_*")):
        if path.name == "D5_run_manifest.json" or not path.is_file():
            continue
        artifacts.append(
            {
                "path": path.name,
                "role": _role(path.name),
                "size": path.stat().st_size,
                "sha256": sha256_file(path),
                "schema_version": identity["schema_version"],
            }
        )
    manifest = {
        **identity,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "study": study,
        "scale": scale,
        "dependencies": dependencies,
        "methods": methods,
        "track_isolation": {
            "track_id": "d5_local",
            "upstream_score_consumed": False,
            "consumed_sources": [],
            "forbidden_score_dimensions": ["D1", "D2", "D3", "D4"],
        },
        "artifacts": artifacts,
        "scientific_boundaries": scientific_boundaries,
        "acceptance": acceptance,
    }
    target = output_root / "D5_run_manifest.json"
    target.write_text(json.dumps(manifest, indent=2, ensure_ascii=True, default=str), encoding="utf-8")
    return manifest


def _role(name: str) -> str:
    if "main_scores" in name:
        return "authoritative_local_score"
    if "zone_consensus" in name or "d4_interface" in name:
        return "d4_read_only_interface"
    if "topology" in name:
        return "topology_registry_or_review_evidence"
    if "template" in name or "mapping" in name:
        return "frozen_method_asset"
    if "report" in name.lower():
        return "human_readable_report"
    return "auditable_research_artifact"
