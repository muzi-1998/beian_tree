from __future__ import annotations

import hashlib
import json
from pathlib import Path


D4_ROOT = Path(__file__).resolve().parents[1]
AUDIT_ROOT = D4_ROOT / "outputs" / "audit" / "mapping_support_migration"
MANIFEST_PATH = AUDIT_ROOT / "manifests" / "D4_mapping_support_audit_manifest.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify() -> dict[str, object]:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    checks = {
        "audit_id": manifest.get("audit_id") == "D4-MAPPING-SUPPORT-AUDIT-v1.0",
        "claim_boundary": manifest.get("claim_boundary")
        == "descriptive_mapping_evidence_audit_no_score_recalibration",
        "main_input_hash": manifest["inputs"]["D4_main_scores_sha256"]
        == sha256_file(D4_ROOT / "outputs" / "data" / "D4_main_scores.xlsx"),
        "mapping_input_hash": manifest["inputs"]["D4_mapping_params_sha256"]
        == sha256_file(D4_ROOT / "outputs" / "data" / "D4_mapping_params.xlsx"),
        "global_fallback_nonnegative": manifest["summary"][
            "global_fallback_pair_hour_rate"
        ]
        >= 0,
    }
    artifact_checks = []
    for artifact in manifest["artifacts"]:
        path = AUDIT_ROOT / artifact["relative_path"]
        artifact_checks.append(
            path.exists()
            and path.stat().st_size == artifact["size_bytes"]
            and sha256_file(path) == artifact["sha256"]
        )
    checks["artifact_hashes"] = bool(artifact_checks and all(artifact_checks))
    result = {"passed": all(checks.values()), "checks": checks}
    if not result["passed"]:
        raise RuntimeError(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    print(json.dumps(verify(), indent=2))
