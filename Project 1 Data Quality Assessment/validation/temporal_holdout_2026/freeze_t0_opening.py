"""Lock the T0 natural-data execution only after documented historical QA."""
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from runtime import HERE, PROJECT, OFFICIAL, OUTPUT, DIMENSIONS, content_hash, sha256, write_json


def main():
    lock = OUTPUT / "T0_opening_lock.json"
    if lock.exists():
        raise RuntimeError("An opening lock already exists; do not silently refreeze after seeing results")
    requirements = {
        "connected_historical_qa.json": ["D4_risk_replay_passed", "D4_asof_CP_equal_to_audited_candidate",
            "DQR_no_future_source", "node_core_formula", "node_full_formula", "pair_core_formula"],
        "D1_actual_continuation_qa.json": ["passed", "no_new_period_values"],
        "D1_full_asset_formula_qa.json": ["passed", "no_new_data_fit"],
        "D1_recovery_replay_qa.json": ["candidate_prefix_passed", "checkpoint_passed"],
        "D2_connected_prefix_qa.json": ["passed", "Strict_and_Sensitive_tested"],
        "D3_historical_replay_qa.json": ["passed", "na_and_gate_exact"],
        "D5_full_replay_qa.json": ["historical_passed", "prefix_passed"],
        "minute_alignment_replay_qa.json": ["native_replay_passed", "daily_checkpoint_passed"],
        "decomposition_replay_qa.json": ["historical_decomposition_equal_1e_8",
            "decomposition_prefix_equal_1e_8", "frozen_filter_checkpoint_equal_1e_10"],
    }
    proofs = {}
    for name, fields in requirements.items():
        path = OUTPUT / "audit" / name
        qa = json.loads(path.read_text(encoding="utf-8"))
        if any(qa.get(field) is not True for field in fields):
            raise RuntimeError(f"Readiness failed: {name}")
        proofs[name] = dict(required_passes=fields, sha256=sha256(path))
    subprocess.run([__import__("sys").executable, "-m", "pytest", str(HERE), "-q"], check=True, cwd=PROJECT)
    packaging_prefixes = ("seal_", "verify_", "plot_", "prepare_", "publish_")
    files = {p for p in HERE.glob("*.py") if not p.name.startswith(packaging_prefixes)}
    files.add(HERE / "T0_LOCKED_EXECUTION_20260907.md")
    files.update((OUTPUT / "assets").glob("*"))
    files.add(HERE / "intake_audit/channel_mapping.csv")
    roots = ["1.1 Decomposition", *DIMENSIONS.values(), "DQR Multidimensional Aggregation and Evidence-Aware Integration"]
    tracked = subprocess.check_output(["git", "ls-files", "-z"], cwd=PROJECT.parent).decode().split("\0")
    for name in tracked:
        path = PROJECT.parent / name
        if not path.is_relative_to(PROJECT):
            continue
        rel = path.relative_to(PROJECT)
        if rel.parts and rel.parts[0] in roots and path.is_file():
            if (path.suffix == ".py" or "configs" in rel.parts or rel.name == "d2_calibration.yaml") and not any(
                    part in {"outputs", "artifacts", "Raw data"} for part in rel.parts):
                files.add(path)
    files.add(PROJECT / DIMENSIONS["D3"] / "outputs/data/D3_threshold_library.xlsx")
    private = ["1.1 Decomposition/outputs/parquet/time_base_1min_raw.parquet", "D1 Sensor health/v11_state.pkl"]
    raw_root = OFFICIAL / "1.1 Decomposition/Raw data/09_25.08.01-26.07.30_all data"
    for pattern in ["*分钟数据*_02_shengwuchi.csv", "*分钟数据*_01_influent+effluent.csv"]:
        matches = list(raw_root.glob(pattern))
        if len(matches) != 1:
            raise RuntimeError("Ambiguous annual source")
        private.append(matches[0].relative_to(OFFICIAL).as_posix())
    stamp = datetime.now(timezone.utc).isoformat()
    write_json(lock, dict(schema="T0-natural-execution-lock-1.0", locked_at_UTC=stamp,
        scope="T0_natural_later_period_scoring_not_challenge_or_T1_model_selection",
        performance_seen_before_lock=False, cutoff="2026-04-14", end_exclusive="2026-07-31",
        scientific_base_commit="6799c3a916bbc6840aa2623f915b44d05e5192d6",
        packaging_commit="commit_containing_manifest; content_SHA_is_authoritative",
        code_config_assets={p.relative_to(PROJECT).as_posix(): content_hash(p) for p in sorted(files) if p.is_file()},
        private_official_inputs={name: sha256(OFFICIAL / name) for name in private},
        readiness_proofs=proofs,
        reconstruction_disclosure="D5 historical numeric equivalence, not archived pickle byte identity; deterministic row reduction is a disclosed amendment",
        restart_contract="replay complete retained raw/history journal; tested alignment/whitener/recovery checkpoints; not a compact live-service claim"))
    write_json(OUTPUT / "opening_gate.json", dict(stage="T0_natural_scoring_authorized", locked_at_UTC=stamp,
        **{key: "passed" for key in ["historical_replay", "prefix_invariance", "chunk_equivalence", "time_contract", "unknown_evidence", "asset_closure"]},
        performance_opening_allowed=True, new_period_scores_computed=False,
        opening_lock_sha256=sha256(lock),
        approval_scope="natural T0 scoring; no future refit, no L1 backfill, no challenge efficacy claim",
        asset_closure_semantics="frozen reconstructed numeric assets, original-byte mismatch disclosed"))
    print("T0 natural-data opening authorized", stamp)


if __name__ == "__main__":
    main()
