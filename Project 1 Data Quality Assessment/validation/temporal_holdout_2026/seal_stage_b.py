"""Fingerprint the checkpoint bundle without treating pending scientific QA as pass."""
from __future__ import annotations

import importlib.metadata
import json
import subprocess
from pathlib import Path

from runtime import HERE, PROJECT, OUTPUT, DIMENSIONS, content_hash, sha256, write_json


def main() -> None:
    repo = PROJECT.parent
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=repo).decode().split("\0")
    prefix = PROJECT.name + "/"
    roots = ["1.1 Decomposition", *DIMENSIONS.values(),
             "DQR Multidimensional Aggregation and Evidence-Aware Integration"]
    dependencies = {}
    for name in tracked:
        path = Path(name)
        if not name.startswith(prefix) or path.suffix not in {".py", ".yaml", ".yml"}:
            continue
        rel = path.relative_to(PROJECT.name)
        if rel.parts[0] in roots and not any(p in {"outputs", "artifacts", "Raw data"} for p in rel.parts):
            dependencies[name] = content_hash(repo / path)
    source = {str(p.relative_to(repo)).replace("\\", "/"): content_hash(p)
              for p in HERE.iterdir() if p.is_file() and p.suffix in {".py", ".md", ".yaml", ".mjs"}}
    for name in [".gitattributes", ".gitignore"]:
        source[str((HERE / name).relative_to(repo)).replace("\\", "/")] = content_hash(HERE / name)
    workflow = repo / ".github/workflows/temporal-holdout-ci.yml"
    source[str(workflow.relative_to(repo)).replace("\\", "/")] = content_hash(workflow)
    artifacts = {}
    for root in [OUTPUT, HERE / "intake_audit"]:
        for path in sorted(root.rglob("*")):
            if (not path.is_file() or path.name == "stage_B_manifest.json"
                    or path.name.endswith(".inspect.ndjson")):
                continue
            artifacts[str(path.relative_to(repo)).replace("\\", "/")] = sha256(path)
    write_json(OUTPUT / "stage_B_manifest.json", {
        "schema": "temporal-stage-B-checkpoint-1.0", "created_on": "2026-09-06",
        "scope": "component_replay_and_timing_audit_not_full_holdout_results",
        "scientific_reference_commit": "6799c3a916bbc6840aa2623f915b44d05e5192d6",
        "packaging_commit": "the_git_commit_containing_this_manifest_not_self_referenced",
        "authoritative_freshness": "exact_current_code_config_content_and_artifact_hashes",
        "holdout_opening_allowed": False,
        "source_code_config": source, "imported_project_code_config": dependencies,
        "artifacts": artifacts,
        "generation_runtime": {name: importlib.metadata.version(name) for name in
                               ["numpy", "pandas", "scipy", "scikit-learn", "statsmodels",
                                "arch", "PyYAML", "openpyxl", "matplotlib", "pyarrow", "pillow"]},
        "private_source_verification": "hashes_in_intake_and_recovery_QA_not_distributed_raw_files",
        "figure_visual_inspection": {"H1": "reviewed", "H2": "reviewed_after_legend_correction"},
    })
    print(f"Bound {len(source)} checkpoint sources, {len(dependencies)} dependencies, {len(artifacts)} artifacts")


if __name__ == "__main__":
    main()
