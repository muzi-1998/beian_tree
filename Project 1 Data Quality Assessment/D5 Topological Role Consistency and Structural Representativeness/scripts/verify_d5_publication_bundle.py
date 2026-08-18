from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from d5_local.publication import D5PublicationAudit  # noqa: E402


def sha256(path: Path) -> str:
    return D5PublicationAudit._sha256(path)


def main() -> None:
    audit = D5PublicationAudit()
    manifest_path = ROOT / "outputs" / "publication" / "D5_publication_audit_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    failures: list[str] = []
    for item in manifest.get("files", []):
        path = ROOT / item["relative_path"]
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
    if not manifest.get("figure_bundle_finalized", False):
        failures.append("publication_manifest_not_finalized")
    result = {
        "passed": not failures,
        "failures": failures,
        "artifact_count": len(manifest.get("files", [])),
        "d4_dependency": dependency,
        "figure_qa_passed": bool(figure_qa.get("passed", False)),
    }
    print(json.dumps(result, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
