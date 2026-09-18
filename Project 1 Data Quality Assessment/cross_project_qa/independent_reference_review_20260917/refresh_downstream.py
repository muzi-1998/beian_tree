"""Rebuild affected publications in dependency order, preserving D5 scores and DQR v2.3."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd
import yaml

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
D3 = PROJECT / "D3 Physical rationality and rate constraints"
D4 = PROJECT / "D4 Parallel-redundancy Temporal Consistency"
D5 = PROJECT / "D5 Topological Role Consistency and Structural Representativeness"
DQR = PROJECT / "DQR Multidimensional Aggregation and Evidence-Aware Integration"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest_digest(path):
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def run(root, *command):
    print(root.name, *command, flush=True)
    subprocess.run([sys.executable, *command], cwd=root, check=True)


def d4():
    run(D4, "-m", "pytest", "tests", "-q")
    for script in ["run_d4_validation", "run_d4_episode_validation", "run_d4_method_sensitivity",
                   "run_d4_sensitivity", "run_d4_d5_readiness", "run_d4_composite_refresh",
                   "run_d1_d4_redundancy_audit", "make_d4_figures", "audit_d4_figures",
                   "run_d4_mapping_support_migration_audit", "verify_d4_mapping_support_audit",
                   "check_d4_outputs", "build_d4_publication_manifest", "verify_d4_publication_bundle"]:
        run(D4, f"scripts/{script}.py")


def d5():
    lock = yaml.safe_load((DQR / "configs/aggregation_v2_3.yaml").read_text(encoding="utf-8"))
    for dim in ["D1", "D2", "D5"]:
        assert digest(PROJECT / lock["inputs"][dim]["path"]) == lock["inputs"][dim]["expected_sha256"], dim
    manifest = json.loads((D4 / "outputs/data/D4_run_manifest.json").read_text())
    path = D5 / "configs/publication/d5_final_contract.yaml"
    contract = yaml.safe_load(path.read_text(encoding="utf-8"))
    contract["d4_dependency"].update(expected_run_id=manifest["run_id"],
        expected_calibration_id=manifest["calibration_id"], expected_main_scores_sha256=digest(D4 / "outputs/data/D4_main_scores.xlsx"))
    path.write_text(yaml.safe_dump(contract, allow_unicode=True, sort_keys=False), encoding="utf-8")
    run(D5, "-m", "pytest", "tests", "-q")
    run(D5, "scripts/run_d5_publication_audit.py")
    run(D5, "scripts/verify_d5_publication_bundle.py")
    assert digest(PROJECT / lock["inputs"]["D5"]["path"]) == lock["inputs"]["D5"]["expected_sha256"]


def dqr():
    config = yaml.safe_load((DQR / "configs/aggregation_v2_3.yaml").read_text(encoding="utf-8"))
    config["contract_version"] = "2.4.0"
    config["schema_version"] = "northbank-dqr-aggregation-v2.4"
    config["revision"] = {"scope": "neutral_D3_D4_reference_and_score_dependency_separation",
                          "D1_D2_D5_numeric_outputs": "unchanged_SHA256_verified",
                          "evaluation_claim": "revised_retrospective_and_temporal_out_of_sample_re_evaluation"}
    config["study"]["future_holdout"].update(end="2026-07-30 23:59:00",
        status="previously_inspected_108_days_separate_revised_temporal_evaluation_not_first_blind_test")
    for dim in ["D3", "D4"]:
        spec = config["inputs"][dim]
        source = PROJECT / spec["manifest_path"]
        manifest = json.loads(source.read_text(encoding="utf-8"))
        spec.update(expected_sha256=digest(PROJECT / spec["path"]),
                    expected_manifest_sha256=manifest_digest(source), expected_run_id=manifest["run_id"])
        if dim == "D4":
            spec.update(expected_mapping_sha256=digest(PROJECT / spec["mapping_path"]),
                        expected_formal_case_sha256=digest(PROJECT / spec["formal_case_path"]),
                        expected_calibration_id=manifest["calibration_id"])
    spec = config["inputs"]["D5"]
    for name in ["publication_manifest", "dependence", "stratified_dependence"]:
        hasher = manifest_digest if name.endswith("manifest") else digest
        spec[f"expected_{name}_sha256"] = hasher(PROJECT / spec[f"{name}_path"])
    for dim in ["D1", "D2", "D5"]:
        spec = config["inputs"][dim]
        assert digest(PROJECT / spec["path"]) == spec["expected_sha256"], f"Unrequested {dim} score mutation"
    assert manifest_digest(PROJECT / spec["support_audit_manifest_path"]) == spec["expected_support_audit_manifest_sha256"]
    # Match the old registered DO14 episode by temporal overlap, never by a new extreme score.
    old_case_file = config["inputs"]["D4"]["formal_case_path"]
    import io
    old_bytes = subprocess.check_output(["git", "show", "6799c3a:" + "Project 1 Data Quality Assessment/" + old_case_file], cwd=PROJECT)
    old_registry = pd.read_excel(io.BytesIO(old_bytes), sheet_name="episode_registry")
    old_event = old_registry.loc[old_registry.event_id.eq(config["case_studies"]["D4_formal_event_id"])].iloc[0]
    registry = pd.read_excel(PROJECT / old_case_file, sheet_name="episode_registry")
    matches = registry.loc[registry.pair_id.eq(old_event.pair_id)].copy()
    matches["overlap_h"] = ((pd.to_datetime(matches.end_ts).clip(upper=pd.Timestamp(old_event.end_ts))
        - pd.to_datetime(matches.start_ts).clip(lower=pd.Timestamp(old_event.start_ts))).dt.total_seconds()/3600 + 1).clip(lower=0)
    if matches.empty or matches.overlap_h.max() <= 0:
        raise RuntimeError("Revised formal-case registry does not preserve the prespecified historical episode; explicit case audit required")
    chosen = matches.sort_values(["overlap_h", "start_ts"], ascending=[False, True]).iloc[0]
    config["case_studies"].update(D4_formal_event_id=chosen.event_id,
        D4_selection_rule="maximum_temporal_overlap_with_frozen_registered_DO14_episode_not_score_extremum")
    config["output_artifacts"] = {k: v.replace("v2.3", "v2.4") for k, v in config["output_artifacts"].items()}
    (DQR / "configs/aggregation_v2_4.yaml").write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding="utf-8")
    run(DQR, "-m", "pytest", "tests", "-q", "-k", "not released_node_and_pair_formulas and not dimension_roles_and_missing_semantics")
    run(DQR, "scripts/run_dqr_aggregation.py")
    run(DQR, "-m", "pytest", "tests", "-q")
    run(DQR, "scripts/verify_dqr_aggregation.py")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["d4", "d5", "dqr"])
    args = parser.parse_args()
    globals()[args.stage]()
