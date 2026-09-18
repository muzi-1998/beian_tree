"""Bind the revised cross-project bundle to exact code, configuration and outputs."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
DQR = PROJECT / "DQR Multidimensional Aggregation and Evidence-Aware Integration"
REVISED = PROJECT / "validation/revised_reference_20260917"
MANIFEST = HERE / "REVISION_RELEASE_MANIFEST.json"


def record(path):
    canonical = path.suffix.lower() in {".py", ".yaml", ".yml", ".json", ".md", ".svg", ".csv"}
    data = (path.read_text(encoding="utf-8-sig").replace("\r\n", "\n").replace("\r", "\n").encode("utf-8")
            if canonical else path.read_bytes())
    return {"path": path.relative_to(PROJECT).as_posix(), "sha256": hashlib.sha256(data).hexdigest(),
            "hash_method": "utf8_lf" if canonical else "raw_bytes"}


def checks():
    sys.path.insert(0, str(DQR / "src"))
    from dqr_aggregation.common import load_config
    from dqr_aggregation.pipeline import verify_frozen_inputs
    registry = verify_frozen_inputs(load_config())
    qa = json.loads((REVISED / "outputs/Reevaluation_QA.json").read_text())
    assert qa["passed"] and all(qa["checks"].values())
    return {"frozen_input_registry": bool(registry.sha256_match.all()), "temporal_checks": qa["checks"]}


def build():
    result = checks()
    paths = set()
    for name in ["D3 Physical rationality and rate constraints", "D4 Parallel-redundancy Temporal Consistency",
                 "D5 Topological Role Consistency and Structural Representativeness", DQR.name]:
        root = PROJECT / name
        for folder in ["src", "scripts", "configs", "tests", "figures", "ci"]:
            for suffix in ["*.py", "*.yaml", "*.yml"]:
                paths.update((root / folder).rglob(suffix))
        paths.update(root.glob("*.py"))
    for folder in [HERE, REVISED, PROJECT / "shared_data_foundation"]:
        paths.update(p for p in folder.rglob("*") if p.is_file()
                     and p.suffix in {".py", ".json", ".md", ".parquet", ".xlsx", ".pdf", ".svg", ".png", ".tiff"}
                     and "__pycache__" not in p.parts and p != MANIFEST)
    named = [
        "D3 Physical rationality and rate constraints/outputs/manifest/run_manifest.json",
        "D3 Physical rationality and rate constraints/outputs/reports/nature_figure_bundle_audit.json",
        "D4 Parallel-redundancy Temporal Consistency/outputs/qa/D4_publication_manifest.json",
        "D4 Parallel-redundancy Temporal Consistency/outputs/qa/numerical_qa.json",
        "D5 Topological Role Consistency and Structural Representativeness/outputs/publication/D5_publication_audit_manifest.json",
        DQR.name+"/outputs/aggregation_v2_4/manifests/DQR_run_manifest.json",
        DQR.name+"/outputs/aggregation_v2_4/manifests/DQR_publication_manifest.json"]
    paths.update(PROJECT / path for path in named)
    d3_outputs = PROJECT / "D3 Physical rationality and rate constraints/outputs"
    for folder in ["data", "validation", "figures"]:
        paths.update(p for p in (d3_outputs / folder).rglob("*") if p.is_file())
    payload = {"schema": "neutral-reference-revision-v1", "frozen_baseline_commit": "6799c3a916bbc6840aa2623f915b44d05e5192d6",
        "authority": "code_config_and_artifact_content_hashes_not_packaging_commit",
        "claim": "computational_and_scoring_dependency_separation_not_statistical_independence",
        "temporal_evaluation": "previously_inspected_revised_temporal_out_of_sample_re_evaluation",
        "checks": result, "files": [record(p) for p in sorted(paths)]}
    MANIFEST.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def verify():
    checks()
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    failed = []
    for row in payload["files"]:
        path = PROJECT / row["path"]
        if not path.is_file() or record(path) != row:
            failed.append(row["path"])
    if failed:
        raise AssertionError(f"Stale revision artifacts/code: {failed}")
    print(json.dumps({"passed": True, "n_bound_files": len(payload["files"]),
        "D1_D2_D5_frozen": True, "revised_temporal_checks": len(payload["checks"]["temporal_checks"])}, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--build", action="store_true")
    args = parser.parse_args()
    if args.build:
        build()
    verify()
