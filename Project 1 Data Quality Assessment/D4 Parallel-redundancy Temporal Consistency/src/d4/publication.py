from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path, PureWindowsPath

import pandas as pd


D4_ROOT = Path(__file__).resolve().parents[2]
MANIFEST_PATH = D4_ROOT / "outputs" / "qa" / "D4_publication_manifest.json"
TEXT_SUFFIXES = {
    ".csv",
    ".json",
    ".md",
    ".py",
    ".svg",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}


def publication_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    if path.suffix.lower() in TEXT_SUFFIXES:
        content = path.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        digest.update(content)
        return digest.hexdigest()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def manifest_relative_path(value: str) -> Path:
    return Path(*PureWindowsPath(value).parts)


def publication_artifacts() -> list[Path]:
    fixed = [
        D4_ROOT / "configs" / "d4.yaml",
        D4_ROOT / "src" / "d4" / "pipeline.py",
        D4_ROOT / "src" / "d4" / "scoring.py",
        D4_ROOT / "src" / "d4" / "figures.py",
        D4_ROOT / "src" / "d4" / "figure_style.py",
        D4_ROOT / "outputs" / "data" / "D4_main_scores.xlsx",
        D4_ROOT / "outputs" / "data" / "D4_mapping_params.xlsx",
        D4_ROOT / "outputs" / "data" / "D4_run_manifest.json",
        D4_ROOT / "outputs" / "data" / "D4_event_duration_validation.xlsx",
        D4_ROOT / "outputs" / "integration" / "D4_D5_aggregation_readiness.xlsx",
        D4_ROOT / "outputs" / "integration" / "D4_D5_final_arbitration.parquet",
        D4_ROOT / "outputs" / "integration" / "D4_D5_FINAL_ARBITRATION_REPORT.md",
        D4_ROOT
        / "outputs"
        / "integration"
        / "D4_D5_aggregation_readiness_manifest.json",
    ]
    figures = sorted((D4_ROOT / "outputs" / "figures").glob("Fig*.*"))
    source_data = sorted(
        (D4_ROOT / "outputs" / "figure_source_data").glob("*_source_data.xlsx")
    )
    return fixed + figures + source_data


def build_publication_manifest() -> Path:
    run_manifest_path = D4_ROOT / "outputs" / "data" / "D4_run_manifest.json"
    run_manifest = json.loads(run_manifest_path.read_text(encoding="utf-8"))
    main_scores = D4_ROOT / "outputs" / "data" / "D4_main_scores.xlsx"
    files = publication_artifacts()
    missing = [str(path) for path in files if not path.exists()]
    if missing:
        raise FileNotFoundError(f"Missing D4 publication artifacts: {missing}")
    payload = {
        "version": "d4-publication-manifest-v1.0",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "sha256_policy": "canonical_lf_for_text_raw_bytes_for_binary",
        "run_id": run_manifest["run_id"],
        "calibration_id": run_manifest["calibration_id"],
        "d4_main_scores_sha256": publication_sha256(main_scores),
        "files": [
            {
                "relative_path": path.relative_to(D4_ROOT).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": publication_sha256(path),
            }
            for path in files
        ],
    }
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return MANIFEST_PATH


def verify_publication_manifest() -> dict[str, object]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    failures: list[str] = []
    for item in manifest.get("files", []):
        path = D4_ROOT / manifest_relative_path(item["relative_path"])
        if not path.exists():
            failures.append(f"missing:{item['relative_path']}")
        elif publication_sha256(path) != item["sha256"]:
            failures.append(f"sha256_mismatch:{item['relative_path']}")

    main_scores_path = D4_ROOT / "outputs" / "data" / "D4_main_scores.xlsx"
    identity = pd.read_excel(
        main_scores_path,
        sheet_name="main_scores",
        usecols=["run_id", "calibration_id"],
    )
    run_ids = identity["run_id"].dropna().astype(str).unique().tolist()
    calibration_ids = (
        identity["calibration_id"].dropna().astype(str).unique().tolist()
    )
    if run_ids != [str(manifest["run_id"])]:
        failures.append("run_id_not_unique_or_manifest_mismatch")
    if calibration_ids != [str(manifest["calibration_id"])]:
        failures.append("calibration_id_not_unique_or_manifest_mismatch")
    if publication_sha256(main_scores_path) != manifest["d4_main_scores_sha256"]:
        failures.append("main_scores_manifest_hash_mismatch")

    numerical_qa = json.loads(
        (D4_ROOT / "outputs" / "qa" / "numerical_qa.json").read_text(
            encoding="utf-8"
        )
    )
    figure_qa = json.loads(
        (D4_ROOT / "outputs" / "qa" / "d4_figure_bundle_audit.json").read_text(
            encoding="utf-8"
        )
    )
    integration = json.loads(
        (
            D4_ROOT
            / "outputs"
            / "integration"
            / "D4_D5_aggregation_readiness_manifest.json"
        ).read_text(encoding="utf-8")
    )
    if not numerical_qa.get("passed", False):
        failures.append("numerical_qa_failed")
    if not figure_qa.get("passed", False):
        failures.append("figure_qa_failed")
    if figure_qa.get("figure_contract", {}).get("observed") != 12:
        failures.append("figure_bundle_not_twelve")
    if numerical_qa.get("core_final_D4_forDQR_preintegration_nonnull") != 0:
        failures.append("core_preintegration_field_not_withheld")
    finalized = integration.get("integration_final_D4_forDQR_nonnull")
    if finalized != numerical_qa.get("integration_final_D4_forDQR_nonnull"):
        failures.append("integration_finalized_count_mismatch")
    if integration.get("d4_sha256") != publication_sha256(main_scores_path):
        failures.append("integration_d4_source_hash_mismatch")
    report_path = D4_ROOT / "outputs" / "integration" / "D4_D5_FINAL_ARBITRATION_REPORT.md"
    if integration.get("report_sha256") != publication_sha256(report_path):
        failures.append("integration_report_hash_mismatch")

    return {
        "passed": not failures,
        "failures": failures,
        "artifact_count": len(manifest.get("files", [])),
        "run_id": run_ids[0] if len(run_ids) == 1 else None,
        "calibration_id": calibration_ids[0] if len(calibration_ids) == 1 else None,
        "core_preintegration_nonnull": numerical_qa.get(
            "core_final_D4_forDQR_preintegration_nonnull"
        ),
        "integration_finalized_nonnull": finalized,
        "figure_qa_passed": bool(figure_qa.get("passed", False)),
    }
