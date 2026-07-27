from __future__ import annotations

import sys
import json
from pathlib import Path

import numpy as np
import pandas as pd
import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.confirmatory_v2.common import event_jaccard, moving_block_bootstrap_mean
from src.confirmatory_v2.wp0 import build_temporal_split_registry


FINAL_RUN_ID = "D1D5V20-a2b2bef69861"


def test_temporal_splits_are_ordered_and_nonoverlapping() -> None:
    split = build_temporal_split_registry()
    assert (split["train_end"] < split["test_start"]).all()
    assert (split["test_start"].iloc[1:].to_numpy() > split["test_end"].iloc[:-1].to_numpy()).all()
    assert split["fold_id"].is_unique


def test_event_jaccard_handles_empty_and_partial_overlap() -> None:
    empty = pd.Series([False, False])
    assert event_jaccard(empty, empty) == 1.0
    left = pd.Series([True, True, False])
    right = pd.Series([False, True, True])
    assert event_jaccard(left, right) == 1.0 / 3.0


def test_moving_block_bootstrap_is_seed_reproducible() -> None:
    values = np.arange(24, dtype=float)
    first = moving_block_bootstrap_mean(
        values,
        block_size=6,
        repetitions=20,
        rng=np.random.default_rng(7),
    )
    second = moving_block_bootstrap_mean(
        values,
        block_size=6,
        repetitions=20,
        rng=np.random.default_rng(7),
    )
    assert np.array_equal(first, second)
    assert np.isfinite(first).all()


def test_ambiguity_registry_has_complete_decision_fields() -> None:
    path = PROJECT_ROOT / "configs" / "frozen_v2" / "ambiguity_registry.yaml"
    items = yaml.safe_load(path.read_text(encoding="utf-8"))["items"]
    required = {
        "ambiguity_id",
        "issue",
        "execution_policy",
        "status",
        "recommended_resolution",
    }
    assert items
    assert all(required <= set(item) for item in items)
    assert len({item["ambiguity_id"] for item in items}) == len(items)


def test_dimension_registry_keeps_d3_outside_numeric_composite() -> None:
    path = PROJECT_ROOT / "dimension_registry.yaml"
    registry = yaml.safe_load(path.read_text(encoding="utf-8"))
    d3 = registry["canonical_dimensions"]["D3"]
    contract = registry["aggregation_contract"]
    assert d3["primary_interface"] == "D3_gate_status"
    assert d3["legacy_supplementary_score"] == "D3_total"
    assert contract["node_formula"] == "equal_mean_of_eligible_D1_D2_D5"
    assert contract["pair_formula"] == "equal_mean_of_target_node_reference_node_D4_raw"
    assert contract["D3_role"] == "independent_non_compensatory_safety_gate"


def test_final_run_manifest_matches_registry() -> None:
    registry = yaml.safe_load(
        (PROJECT_ROOT / "dimension_registry.yaml").read_text(encoding="utf-8")
    )
    contract = registry["aggregation_contract"]
    run_dir = PROJECT_ROOT / contract["confirmatory_run_location"]
    manifest = json.loads((run_dir / "run_manifest.json").read_text(encoding="utf-8"))
    assert contract["confirmatory_run_id"] == FINAL_RUN_ID
    assert manifest["run_id"] == FINAL_RUN_ID
    assert str(manifest["status"]).startswith("completed")
