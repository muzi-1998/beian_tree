from __future__ import annotations

import numpy as np
import pandas as pd
import yaml
from dataclasses import replace

from d5_common.config import D5_ROOT, reference_end_from_fraction
from d5_local.publication.audit import D5PublicationAudit
from scripts.verify_d5_publication_bundle import manifest_relative_path


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
    assert contract["d4_dependency"]["policy"] == (
        "fail_closed_exact_artifact_match"
    )


def test_reference_endpoint_uses_inclusive_shared_contract() -> None:
    index = pd.date_range("2025-01-01", periods=10, freq="10min")
    assert reference_end_from_fraction(index, 0.70) == index[6]


def test_manifest_paths_are_portable_across_operating_systems() -> None:
    expected = D5_ROOT / "outputs" / "figures" / "D5_figure_qa.json"
    relative = manifest_relative_path(
        r"outputs\figures\D5_figure_qa.json"
    )
    assert D5_ROOT / relative == expected


def test_publication_text_hash_normalizes_line_endings(tmp_path) -> None:
    lf_path = tmp_path / "lf.md"
    crlf_path = tmp_path / "crlf.md"
    lf_path.write_bytes(b"heading\nbody\n")
    crlf_path.write_bytes(b"heading\r\nbody\r\n")
    assert D5PublicationAudit._sha256(lf_path) == D5PublicationAudit._sha256(
        crlf_path
    )


def test_d4_dependency_check_is_fail_closed(tmp_path) -> None:
    path = tmp_path / "D4_main_scores.xlsx"
    frame = pd.DataFrame(
        {"run_id": ["R1", "R1"], "calibration_id": ["C1", "C1"]}
    )
    frame.to_excel(path, index=False)
    audit = D5PublicationAudit()
    audit.paths = replace(audit.paths, d4_scores=path)
    audit.config["d4_dependency"].update(
        {
            "expected_run_id": "R1",
            "expected_calibration_id": "C1",
            "expected_main_scores_sha256": audit._sha256(path),
        }
    )
    assert audit.d4_dependency_status()["status"] == "current"
    frame.loc[1, "run_id"] = "R2"
    frame.to_excel(path, index=False)
    assert audit.d4_dependency_status()["status"] == "stale_dependency_blocked"


def test_stratified_overlap_retains_unestimable_cells() -> None:
    audit = D5PublicationAudit()
    timestamps = pd.date_range("2025-01-01", periods=48, freq="1h")
    frame = pd.DataFrame(
        {
            "timestamp": timestamps,
            "D4_raw": np.linspace(1.0, 5.0, 48),
            "D5_pair": np.linspace(1.2, 4.8, 48),
            "variable": ["DO"] * 48,
            "regime_id": [1] * 48,
            "month": ["2025-01"] * 48,
            "pair_id": ["PAIR_DO11"] * 48,
            "time_block": np.repeat([0, 1], 24),
        }
    )
    result = audit._stratified_d4_d5_rho(
        frame, "D5_pair", "D5_raw_calculable"
    )
    assert set(result["stratum_type"]) == {"analyte", "regime", "month", "pair"}
    assert result["estimable"].all()
    assert result["descriptive_estimable"].all()
    assert not result["inferential_estimable"].any()
    assert result["ci95_low"].isna().all()


def test_d4_manifest_identity_requires_run_calibration_and_hash() -> None:
    recorded = {"d4_run_id": "R1", "d4_calibration_id": "C1", "d4_main_scores_sha256": "H1"}
    current = {"d4_run_id": "R1", "d4_calibration_id": "C1", "d4_main_scores_sha256": "H1"}
    assert D5PublicationAudit._d4_identity_matches(recorded, current)
    current["d4_main_scores_sha256"] = "H2"
    assert not D5PublicationAudit._d4_identity_matches(recorded, current)


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


def test_monthly_ood_uses_out_of_template_status() -> None:
    timestamps = pd.date_range("2025-01-01", periods=4, freq="1h")
    frame = pd.DataFrame(
        {
            "timestamp": timestamps,
            "D5_raw": [4.0, 4.0, 4.0, 4.0],
            "D5_report_score": [4.0, np.nan, np.nan, 4.0],
            "support_level": ["L3", "L1", "L2", "L3"],
            "evaluation_status": [
                "evaluable",
                "limited_support",
                "out_of_template",
                "evaluable",
            ],
        }
    )
    result = D5PublicationAudit._monthly_coverage(frame)
    assert result.loc[0, "ood_rate"] == 0.25


def test_publication_dual_scope_sources_are_provenance_ready() -> None:
    audit = D5PublicationAudit()
    for name in [
        "D5_d4_d5_joint_sample.parquet",
        "D5_d4_d5_low_tail_overlap.parquet",
    ]:
        path = audit.output_root / name
        if not path.exists():
            continue
        frame = pd.read_parquet(path)
        assert set(frame["overlap_scope"].unique()) == {
            "D5_report_score",
            "D5_raw_calculable",
        }
        assert {
            "source_D4_run_id",
            "source_D4_calibration_id",
            "source_D4_sha256",
        }.issubset(frame.columns)


def spearman_like(x: pd.Series, y: pd.Series) -> float:
    return float(x.rank().corr(y.rank()))
