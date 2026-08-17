from __future__ import annotations

import numpy as np
import pandas as pd
import yaml

from d5_common.config import D5_ROOT
from d5_local.publication.audit import D5PublicationAudit


def test_publication_contract_keeps_scores_continuous_and_grades_disabled() -> None:
    contract = yaml.safe_load(
        (
            D5_ROOT
            / "configs"
            / "publication"
            / "d5_final_contract.yaml"
        ).read_text(encoding="utf-8")
    )
    assert contract["score_contract"]["primary_scientific_score"] == "D5_raw"
    assert not contract["score_contract"]["grade_bands_enabled"]
    assert contract["claim_boundaries"]["top1_failure_blocks"] == (
        "sensor_specific_hard_veto"
    )


def test_cluster_label_alignment_recovers_permutation() -> None:
    reference = np.array([0, 0, 1, 1, 2, 2])
    candidate = np.array([2, 2, 0, 0, 1, 1])
    mapping = D5PublicationAudit.align_cluster_labels(reference, candidate)
    aligned = np.array([mapping[value] for value in candidate])
    np.testing.assert_array_equal(aligned, reference)


def test_partial_rank_removes_shared_group_shift() -> None:
    frame = pd.DataFrame(
        {
            "x": [1, 2, 3, 11, 12, 13],
            "y": [2, 1, 3, 12, 11, 13],
            "pair": ["a", "a", "a", "b", "b", "b"],
        }
    )
    raw = spearman_like(frame["x"], frame["y"])
    partial = D5PublicationAudit.partial_rank_correlation(
        frame, x="x", y="y", controls=["pair"]
    )
    assert raw > partial


def test_cluster_bootstrap_samples_whole_clusters() -> None:
    frame = pd.DataFrame(
        {"cluster": ["a", "a", "b", "b"], "value": [0.0, 0.0, 1.0, 1.0]}
    )
    low, high = D5PublicationAudit.cluster_bootstrap_interval(
        frame,
        cluster="cluster",
        estimator=lambda sample: float(sample["value"].mean()),
        repetitions=200,
        rng=np.random.default_rng(4),
    )
    assert low == 0.0
    assert high == 1.0


def spearman_like(x: pd.Series, y: pd.Series) -> float:
    return float(x.rank().corr(y.rank()))
