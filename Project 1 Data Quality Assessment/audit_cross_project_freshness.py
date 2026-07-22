"""Audit hash-level freshness across the released D1 downstream chain."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "cross_project_qa" / "cross_project_freshness_audit.json"
D7_LOCAL_CORE_FILES = (
    "D7_main_scores_hourly.parquet",
    "D7_spatial_evidence.parquet",
    "D7_sensor_influence.parquet",
    "D7_regime_state.parquet",
    "D7_reference_window_library.parquet",
    "D7_event_windows.parquet",
    "D7_zone_consensus.parquet",
    "D7_spatial_templates.template_bundle.json",
    "D7_topology_registry.json",
    "D7_topology_registry.yaml",
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def d7_local_core_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for name in D7_LOCAL_CORE_FILES:
        path = root / name
        if not path.is_file():
            raise FileNotFoundError(f"Missing D7 Local core artifact: {path}")
        digest.update(name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def record(checks: list[dict[str, object]], name: str, passed: bool, detail: object) -> None:
    checks.append({"check": name, "passed": bool(passed), "detail": detail})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-d7-local-sha256", required=True)
    args = parser.parse_args()
    checks: list[dict[str, object]] = []

    d1_data = ROOT / "D1 Sensor health" / "outputs" / "data"
    d1_release_path = d1_data / "D1_release_manifest.json"
    d1_release = load_json(d1_release_path)
    for artifact in d1_release["artifacts"]:
        path = ROOT / "D1 Sensor health" / artifact["path"]
        actual = sha256_file(path)
        record(checks, f"D1:{path.name}", actual == artifact["sha256"], actual)

    d2_manifest = load_json(
        ROOT
        / "D2 Temporal Continuity & Information Availability"
        / "artifacts"
        / "data"
        / "D2_d1_linkage_manifest.json"
    )
    record(
        checks,
        "D2:D1_release_id",
        d2_manifest.get("d1_release_id") == d1_release["release_id"],
        d2_manifest.get("d1_release_id"),
    )
    record(
        checks,
        "D2:core_scores_unchanged",
        d2_manifest.get("core_scores_unchanged")
        and d2_manifest.get("core_score_sha256_before")
        == d2_manifest.get("core_score_sha256_after"),
        d2_manifest.get("core_score_sha256_after"),
    )

    d6_root = ROOT / "D6 Parallel-redundancy Temporal Consistency"
    d6_manifest = load_json(d6_root / "outputs" / "data" / "D6_run_manifest.json")
    d6_dependencies = {
        item["dependency"]: item["sha256"] for item in d6_manifest["dependencies"]
    }
    expected_d1 = {
        item["path"].split("/")[-1]: item["sha256"] for item in d1_release["artifacts"]
    }
    record(
        checks,
        "D6:D1_scores_hash",
        d6_dependencies.get("d1_scores") == expected_d1["D1_main_scores_min.xlsx"],
        d6_dependencies.get("d1_scores"),
    )
    record(
        checks,
        "D6:regime_hash",
        d6_dependencies.get("regime_templates") == expected_d1["D1_regime_templates.xlsx"],
        d6_dependencies.get("regime_templates"),
    )
    d6_scores = pd.read_excel(
        d6_root / "outputs" / "data" / "D6_main_scores.xlsx",
        sheet_name="main_scores",
        usecols=["D6_forDQR", "D6_forDQR_is_final", "D6_forDQR_status"],
    )
    status_counts = d6_scores["D6_forDQR_status"].astype(str).value_counts().to_dict()
    allowed_pending_statuses = {"pending_D7_arbitration", "not_evaluable_or_D1_missing"}
    pending = (
        d6_scores["D6_forDQR"].isna().all()
        and not d6_scores["D6_forDQR_is_final"].fillna(False).astype(bool).any()
        and set(status_counts).issubset(allowed_pending_statuses)
        and status_counts.get("pending_D7_arbitration", 0) > 0
    )
    record(checks, "D6:D7_arbitration_pending", pending, status_counts)

    d7_root = ROOT / "D7 Topological Role Consistency and Structural Representativeness"
    d7_manifest = load_json(d7_root / "outputs" / "sensitivity" / "D7_sensitivity_manifest.json")
    d7_dependencies = {item["role"]: item for item in d7_manifest.get("dependencies", [])}
    record(
        checks,
        "D7_sensitivity:D1_release_id",
        d7_manifest.get("d1_release_id") == d1_release["release_id"],
        d7_manifest.get("d1_release_id"),
    )
    for role in ("D1_scores", "D2_scores", "D4_scores", "D7_local_evidence"):
        item = d7_dependencies.get(role, {})
        path = Path(str(item.get("path", "")))
        if not path.is_absolute():
            path = ROOT / path
        actual = sha256_file(path) if path.is_file() else None
        record(checks, f"D7_sensitivity:{role}", actual == item.get("sha256"), actual)
    record(
        checks,
        "D7_sensitivity:no_production_write",
        d7_manifest.get("production_write_permission") is False
        and d7_manifest.get("D7_forDQR_status") == "pending_not_produced"
        and d7_manifest.get("local_imported") is False,
        d7_manifest.get("D7_forDQR_status"),
    )

    local_hash = d7_local_core_sha256(d7_root / "outputs" / "local")
    record(
        checks,
        "D7_local:unchanged",
        local_hash == args.expected_d7_local_sha256,
        {"expected": args.expected_d7_local_sha256, "actual": local_hash},
    )

    result = {
        "schema_version": "cross-project-freshness-v1",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "d1_release_id": d1_release["release_id"],
        "checks": checks,
        "n_checks": len(checks),
        "n_passed": sum(item["passed"] for item in checks),
        "all_passed": all(item["passed"] for item in checks),
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, indent=2, ensure_ascii=True), encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("n_checks", "n_passed", "all_passed")}))
    return 0 if result["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
