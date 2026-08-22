from __future__ import annotations

import json
from pathlib import Path, PureWindowsPath

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
AUDIT_ROOT = ROOT / "outputs" / "audit" / "support_migration"


def _sha256(path: Path) -> str:
    import hashlib

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative_path(value: str) -> Path:
    return Path(*PureWindowsPath(value).parts)


def main() -> None:
    manifest_path = AUDIT_ROOT / "D5_support_migration_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    failures: list[str] = []

    for section in ("source_sha256", "artifacts"):
        for relative, record in manifest.get(section, {}).items():
            path = ROOT / _relative_path(relative)
            expected = record["sha256"] if isinstance(record, dict) else record
            if not path.exists():
                failures.append(f"missing:{relative}")
            elif _sha256(path) != expected:
                failures.append(f"sha256_mismatch:{relative}")

    loss = pd.read_parquet(AUDIT_ROOT / "05_coverage_loss_attribution.parquet")
    counts = loss.set_index("loss_class")["loss_sensor_hours"].astype(int).to_dict()
    expected_counts = {
        "limited_support": 21_588,
        "out_of_template": 1_834,
        "not_evaluable": 28,
    }
    if counts != expected_counts:
        failures.append(f"loss_decomposition_mismatch:{counts}")
    if int(loss["loss_sensor_hours"].sum()) != 23_450:
        failures.append("post_period_loss_does_not_close")
    if abs(float(loss["coverage_percentage_point_contribution"].sum()) - 100.0) > 1e-9:
        failures.append("coverage_percentage_points_do_not_close")

    blockers = pd.read_parquet(AUDIT_ROOT / "03_L1_to_L2_blockers.parquet")
    if len(blockers) != 14 or not blockers["blocker_set"].eq("family_days").all():
        failures.append("L1_blocker_contract_changed")
    horizon = pd.read_parquet(AUDIT_ROOT / "07_reference_horizon_sensitivity.parquet")
    if horizon["effective_support_recalculated"].any():
        failures.append("reference_horizon_overclaims_effective_support")

    result = {
        "passed": not failures,
        "audit_id": manifest.get("audit_id"),
        "failures": failures,
        "source_count": len(manifest.get("source_sha256", {})),
        "artifact_count": len(manifest.get("artifacts", {})),
        "authoritative_scores_modified": manifest.get("authoritative_scores_modified"),
    }
    print(json.dumps(result, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
