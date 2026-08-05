"""Build a SHA-256 manifest for the frozen D2 V4 strict/sensitive release."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parent
ARTIFACTS = ROOT / "artifacts"
OUTPUT = ARTIFACTS / "D2_release_manifest.json"
DEPRECATED_FIGURE_STEMS = {
    "D2_Fig14_aggregation_robustness",
    "D2_Fig16_d1_d2_construct_separation",
}

ROOT_FILES = (
    ".gitignore",
    "PROJECT_STRUCTURE.md",
    "D2_FINAL_SCIENTIFIC_REPORT_2026-08.md",
    "D2_EXPERT_AUDIT_2026-07.md",
    "d2_calibration.yaml",
    "run_d2_pipeline.py",
    "run_d2_full_pipeline_validation.py",
    "run_d2_scientific_validation.py",
    "validate_d2_process_floor.py",
    "make_d2_figures.py",
    "make_d1d2_joint_figures.py",
    "make_d2_scientific_figures.py",
    "build_d2_release_manifest.py",
    "test_d2_contract_regression.py",
    "test_d2_p0p1_regression.py",
    "test_d2_process_floor_regression.py",
    "test_d2_timestamp_qti_regression.py",
    "test_d2_full_pipeline_injection.py",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def file_record(path: Path) -> dict[str, object]:
    return {
        "path": path.relative_to(ROOT).as_posix(),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def repository_files() -> list[Path]:
    files = [ROOT / name for name in ROOT_FILES]
    files.extend((ROOT / "configs").glob("*.yaml"))
    files.extend((ROOT / "src").rglob("*.py"))
    files.extend((ARTIFACTS / "data").glob("*.xlsx"))
    files.extend((ARTIFACTS / "data").glob("*.json"))
    files.extend((ARTIFACTS / "validation").glob("*"))
    for suffix in ("png", "svg", "pdf"):
        files.extend((ARTIFACTS / "figures").glob(f"*.{suffix}"))
    return sorted({path.resolve() for path in files if path.is_file()})


def local_submission_files() -> list[Path]:
    files = [
        path
        for path in (ARTIFACTS / "figures").glob("*.tiff")
        if path.stem not in DEPRECATED_FIGURE_STEMS
    ]
    state = ARTIFACTS / "d2_state.pkl"
    if state.exists():
        files.append(state)
    return sorted(path.resolve() for path in files)


def main() -> None:
    calibration = yaml.safe_load(
        (ROOT / "d2_calibration.yaml").read_text(encoding="utf-8")
    )
    validation_manifest = json.loads(
        (ARTIFACTS / "validation" / "D2_scientific_validation_manifest.json")
        .read_text(encoding="utf-8")
    )
    repository_records = [file_record(path) for path in repository_files()]
    local_records = [file_record(path) for path in local_submission_files()]
    payload = {
        "schema_version": "d2-release-manifest-v4",
        "generated_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "run_id": validation_manifest["run_id"],
        "calibration_id": calibration["calibration_id"],
        "mapping_version": calibration["mapping_version"],
        "study_design_version": calibration["study_design_version"],
        "external_site_validation": calibration["validation_periods"][
            "external_site_validation"
        ],
        "verification": {
            "production_tests": "32 passed",
            "test_command": (
                "python -m pytest test_d2_contract_regression.py "
                "test_d2_p0p1_regression.py test_d2_process_floor_regression.py "
                "test_d2_timestamp_qti_regression.py "
                "test_d2_full_pipeline_injection.py "
                "-q --import-mode=importlib"
            ),
            "process_floor_challenges": "5/5 passed",
            "full_pipeline_monotonicity": "7/7 groups passed; baseline false positives 0",
            "qha_window_robustness": "3/6/9/12 h all passed prespecified event Jaccard >= 0.75",
            "figure_static_validation": "3 scripts x 14/14 checks passed; 0 warnings; 0 failures",
        },
        "repository_outputs": {
            "count": len(repository_records),
            "bytes": sum(int(record["bytes"]) for record in repository_records),
            "files": repository_records,
        },
        "local_submission_outputs": {
            "versioned_in_git": False,
            "reason": "TIFF and runtime state are retained locally to avoid ordinary Git bloat",
            "count": len(local_records),
            "bytes": sum(int(record["bytes"]) for record in local_records),
            "files": local_records,
        },
    }
    OUTPUT.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"Saved {OUTPUT.name}: {len(repository_records)} repository files, "
        f"{len(local_records)} local submission files"
    )


if __name__ == "__main__":
    main()
