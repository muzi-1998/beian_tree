from __future__ import annotations

import json
import sys
from pathlib import Path, PureWindowsPath

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from d5_local.publication import D5PublicationAudit  # noqa: E402


def sha256(path: Path) -> str:
    return D5PublicationAudit._sha256(path)


def manifest_relative_path(value: str) -> Path:
    """Interpret persisted manifest paths consistently on Windows and POSIX."""
    return Path(*PureWindowsPath(value).parts)


def main() -> None:
    audit = D5PublicationAudit()
    manifest_path = ROOT / "outputs" / "publication" / "D5_publication_audit_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    failures: list[str] = []
    for item in manifest.get("files", []):
        path = ROOT / manifest_relative_path(item["relative_path"])
        if not path.exists():
            failures.append(f"missing:{item['relative_path']}")
        elif sha256(path) != item["sha256"]:
            failures.append(f"sha256_mismatch:{item['relative_path']}")
    figure_qa_path = ROOT / "outputs" / "figures" / "D5_figure_qa.json"
    figure_qa = json.loads(figure_qa_path.read_text(encoding="utf-8"))
    if not figure_qa.get("passed", False):
        failures.append("figure_qa_failed")
    if len(figure_qa.get("figures", [])) != 9:
        failures.append("figure_bundle_not_nine_groups")
    dependency = audit.d4_dependency_status()
    if dependency["status"] != "current":
        failures.append("d4_dependency_stale")
    recorded_dependency = manifest.get("d4_dependency", {})
    finalized_dependency = manifest.get("d4_dependency_verified_at_finalize", {})
    if not audit._d4_identity_matches(recorded_dependency, dependency):
        failures.append("manifest_generation_d4_dependency_mismatch")
    if not audit._d4_identity_matches(finalized_dependency, dependency):
        failures.append("manifest_finalize_d4_dependency_mismatch")
    summary = manifest.get("summary", {})
    summary_identity = {
        "run_id": summary.get("d4_run_id"),
        "calibration_id": summary.get("d4_calibration_id"),
        "sha256": summary.get("d4_main_scores_sha256"),
    }
    if audit._d4_identity(summary_identity) != audit._d4_identity(dependency):
        failures.append("manifest_summary_d4_dependency_mismatch")
    for item in manifest.get("files", []):
        if not audit._d4_dependent_relative(item["relative_path"]):
            continue
        source = item.get("source_dependencies", {}).get("D4", {})
        if audit._d4_identity(source) != audit._d4_identity(dependency):
            failures.append(f"artifact_d4_provenance_mismatch:{item['relative_path']}")

    expected_columns = {
        "source_D4_run_id": dependency["d4_run_id"],
        "source_D4_calibration_id": dependency["d4_calibration_id"],
        "source_D4_sha256": dependency["d4_main_scores_sha256"],
    }
    for name in [
        "D5_d4_d5_dependence.parquet",
        "D5_d4_d5_stratified_rho.parquet",
        "D5_d4_d5_composite.parquet",
        "D5_d4_d5_joint_sample.parquet",
        "D5_d4_d5_low_tail_overlap.parquet",
    ]:
        frame = pd.read_parquet(ROOT / "outputs" / "publication" / name)
        for column, expected in expected_columns.items():
            values = frame[column].dropna().astype(str).unique().tolist()
            if values != [str(expected)]:
                failures.append(f"embedded_d4_provenance_mismatch:{name}:{column}")
    figure_source = (
        ROOT
        / "outputs"
        / "publication"
        / "FigD5_7_D4_D5_complementarity_source_data.xlsx"
    )
    for sheet in [
        "dependence",
        "stratified_rho",
        "joint_density_sample",
        "low_tail_overlap",
        "composite_ablation",
    ]:
        frame = pd.read_excel(figure_source, sheet_name=sheet)
        for column, expected in expected_columns.items():
            values = frame[column].dropna().astype(str).unique().tolist()
            if values != [str(expected)]:
                failures.append(
                    f"figure_source_d4_provenance_mismatch:{sheet}:{column}"
                )
    report_path = (
        ROOT
        / "outputs"
        / "publication"
        / "D5_PUBLICATION_READINESS_AUDIT_v1.2.md"
    )
    report = report_path.read_text(encoding="utf-8")
    for expected in audit._d4_identity(dependency).values():
        if str(expected) not in report:
            failures.append(f"report_d4_provenance_missing:{expected}")
    if not manifest.get("figure_bundle_finalized", False):
        failures.append("publication_manifest_not_finalized")
    result = {
        "passed": not failures,
        "failures": failures,
        "artifact_count": len(manifest.get("files", [])),
        "d4_dependency": dependency,
        "manifest_generation_dependency_matches": audit._d4_identity_matches(
            recorded_dependency, dependency
        ),
        "figure_qa_passed": bool(figure_qa.get("passed", False)),
    }
    print(json.dumps(result, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
