"""Freeze the current D1 downstream interface as a hash-bound release."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parent
DATA = ROOT / "outputs" / "data"
LOGS = ROOT / "outputs" / "logs"
RUN_MANIFEST = LOGS / "D1_run_manifest.json"
RELEASE_MANIFEST = DATA / "D1_release_manifest.json"
RELEASE_VERSION = "1.3.0"

CONTRACTS = {
    "D1_main_scores_min.xlsx": {
        "required_sheet": "D1_total_hourly",
        "role": "authoritative hourly D1 score interface",
    },
    "D1_regime_templates.xlsx": {
        "required_sheet": "regime_labels_hourly",
        "role": "authoritative hourly regime context for downstream calibration",
    },
    "D1_event_windows.xlsx": {
        "required_sheet": "all_events",
        "role": "diagnostic D1 event interface for cross-dimension linkage",
    },
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def workbook_contract(path: Path, required_sheet: str) -> dict[str, object]:
    workbook = pd.ExcelFile(path)
    if required_sheet not in workbook.sheet_names:
        raise ValueError(f"{path.name} is missing required sheet {required_sheet!r}")
    frame = pd.read_excel(path, sheet_name=required_sheet)
    return {
        "required_sheet": required_sheet,
        "available_sheets": workbook.sheet_names,
        "rows": int(len(frame)),
        "columns": [str(column) for column in frame.columns],
    }


def main() -> Path:
    if not RUN_MANIFEST.exists():
        raise FileNotFoundError(f"D1 run manifest not found: {RUN_MANIFEST}")
    run_manifest = json.loads(RUN_MANIFEST.read_text(encoding="utf-8"))

    artifacts: list[dict[str, object]] = []
    for filename, contract in CONTRACTS.items():
        path = DATA / filename
        if not path.exists():
            raise FileNotFoundError(f"D1 release artifact not found: {path}")
        artifacts.append(
            {
                "path": f"outputs/data/{filename}",
                "role": contract["role"],
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
                "contract": workbook_contract(path, str(contract["required_sheet"])),
            }
        )

    identity_payload = {
        "source_run_id": run_manifest["run_id"],
        "algorithm_version": run_manifest["algorithm_version"],
        "artifact_hashes": [item["sha256"] for item in artifacts],
    }
    identity = hashlib.sha256(
        json.dumps(identity_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    release_id = f"D1REL-{RELEASE_VERSION}-{identity[:12]}"
    manifest = {
        "schema_version": "d1-release-manifest-v1",
        "release_id": release_id,
        "release_version": RELEASE_VERSION,
        "release_status": "released",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "source_run_id": run_manifest["run_id"],
        "source_algorithm_version": run_manifest["algorithm_version"],
        "source_run_manifest": {
            "path": "outputs/logs/D1_run_manifest.json",
            "sha256": sha256_file(RUN_MANIFEST),
            "state_pickle_sha256": run_manifest.get("state_pickle_sha256"),
        },
        "artifacts": artifacts,
        "downstream_contract": {
            "D2": "diagnostic event linkage only; D2 core score is immutable",
            "D6": "benchmark admission and provisional bilateral D1 fuse",
            "D7": "read-only sensitivity-track filter; D7 Local is isolated",
        },
        "immutability_rule": (
            "Consumers must match artifact SHA-256 values exactly or rerun from this release. "
            "A file modification time is not evidence of freshness."
        ),
    }
    RELEASE_MANIFEST.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=True), encoding="utf-8"
    )
    print(json.dumps({"release_id": release_id, "manifest": str(RELEASE_MANIFEST)}))
    return RELEASE_MANIFEST


if __name__ == "__main__":
    main()
