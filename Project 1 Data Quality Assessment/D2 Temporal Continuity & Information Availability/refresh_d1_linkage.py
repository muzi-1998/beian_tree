"""Refresh only the diagnostic D1 linkage layer of the frozen D2 run."""

from __future__ import annotations

import hashlib
import json
import pickle
from datetime import datetime, timezone
from pathlib import Path

from run_d2_pipeline import extract_freeze_events


ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parent
D1_DATA = PROJECT / "D1 Sensor health" / "outputs" / "data"
STATE_PATH = ROOT / "artifacts" / "d2_state.pkl"
DATA_PATH = ROOT / "artifacts" / "data"
SCORE_PATH = DATA_PATH / "D2_main_scores_hourly.xlsx"
EVENT_PATH = DATA_PATH / "D2_freeze_availability_events.xlsx"
MANIFEST_PATH = DATA_PATH / "D2_d1_linkage_manifest.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> Path:
    d1_manifest_path = D1_DATA / "D1_release_manifest.json"
    if not d1_manifest_path.exists():
        raise FileNotFoundError("Release D1 before refreshing the D2 linkage layer")
    d1_manifest = json.loads(d1_manifest_path.read_text(encoding="utf-8"))
    score_hash_before = sha256_file(SCORE_PATH)

    with STATE_PATH.open("rb") as handle:
        state = pickle.load(handle)
    events = extract_freeze_events(
        state["flags_all"],
        state["subs_all"],
        calibration_id=state.get("calibration_id"),
    )
    events.to_excel(EVENT_PATH, index=False)

    score_hash_after = sha256_file(SCORE_PATH)
    if score_hash_after != score_hash_before:
        raise RuntimeError("D2 core score workbook changed during linkage-only refresh")

    relation_counts = {
        str(key): int(value)
        for key, value in events["relation_to_D1"].value_counts(dropna=False).items()
    }
    manifest = {
        "schema_version": "d2-d1-linkage-manifest-v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "d2_run_id": state.get("run_id"),
        "d2_calibration_id": state.get("calibration_id"),
        "d1_release_id": d1_manifest["release_id"],
        "dependencies": [
            {
                "role": "D1_release_manifest",
                "path": str(d1_manifest_path.relative_to(PROJECT)).replace("\\", "/"),
                "sha256": sha256_file(d1_manifest_path),
            },
            {
                "role": "D1_event_windows",
                "path": "D1 Sensor health/outputs/data/D1_event_windows.xlsx",
                "sha256": sha256_file(D1_DATA / "D1_event_windows.xlsx"),
            },
            {
                "role": "D2_frozen_state",
                "path": "D2 Temporal Continuity & Information Availability/artifacts/d2_state.pkl",
                "sha256": sha256_file(STATE_PATH),
            },
        ],
        "core_score_sha256_before": score_hash_before,
        "core_score_sha256_after": score_hash_after,
        "core_scores_unchanged": True,
        "event_artifact": {
            "path": "artifacts/data/D2_freeze_availability_events.xlsx",
            "sha256": sha256_file(EVENT_PATH),
            "rows": int(len(events)),
            "relation_counts": relation_counts,
            "linked_rows": int(events["linked_D1_event_id"].notna().sum()),
        },
    }
    MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=True), encoding="utf-8"
    )
    print(json.dumps({"rows": len(events), "relations": relation_counts}))
    return MANIFEST_PATH


if __name__ == "__main__":
    main()
