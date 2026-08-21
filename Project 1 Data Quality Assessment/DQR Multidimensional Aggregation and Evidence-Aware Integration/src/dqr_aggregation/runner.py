from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import yaml

from .common import (
    OUTPUT_ROOT,
    generation_configuration_record,
    generation_content_sha256,
    generation_source_registry,
    git_commit,
    load_config,
    make_run_id,
    sha256_file,
    sha256_text_lf,
    stable_frame_hash,
    write_json,
)
from .figures import build_all_figures, run_figure_qa
from .pipeline import (
    build_dimension_long,
    build_monthly_coverage,
    build_node_scores,
    build_pair_scores,
    build_phase_evidence_summary,
    load_d1,
    load_d2,
    load_d3,
    load_d4,
    load_d5,
    verify_frozen_inputs,
)
from .reports import (
    write_directory_guide,
    write_expert_review,
    write_figure_captions,
    write_scientific_report,
    write_workbook,
)
from .validation import (
    aggregator_comparison,
    block_bootstrap_summary,
    complete_case_invariance,
    construct_validity,
    coverage_shift,
    dimension_ablation,
    pending_validation_registry,
    pair_weighting_sensitivity,
    selection_composition_decomposition,
    weight_sensitivity,
)


def _contract_checks(
    config: dict[str, Any],
    *,
    inputs: pd.DataFrame,
    dimension_long: pd.DataFrame,
    node: pd.DataFrame,
    pair: pd.DataFrame,
    invariance: pd.DataFrame,
    decomposition: pd.DataFrame,
    pair_threshold_sweep: pd.DataFrame,
) -> pd.DataFrame:
    score_min = float(config["aggregation"]["score_min"])
    score_max = float(config["aggregation"]["score_max"])
    low_tail_threshold = float(config["aggregation"]["low_tail_threshold"])
    formal_rows = pair_threshold_sweep.loc[
        np.isclose(pair_threshold_sweep["threshold"], low_tail_threshold)
    ]
    partitions_close = bool(
        len(formal_rows) == 1
        and (
            formal_rows["both_count"]
            + formal_rows["hierarchical_only_count"]
            + formal_rows["native_atom_only_count"]
            + formal_rows["neither_count"]
        ).iloc[0]
        == formal_rows["n_complete_pair_hours"].iloc[0]
        and formal_rows["hierarchical_low_tail_count"].iloc[0]
        == (
            formal_rows["both_count"] + formal_rows["hierarchical_only_count"]
        ).iloc[0]
        and formal_rows["native_atom_low_tail_count"].iloc[0]
        == (
            formal_rows["both_count"] + formal_rows["native_atom_only_count"]
        ).iloc[0]
    )
    checks = [
        (
            "frozen_input_hashes",
            bool(inputs["sha256_match"].all()),
            "all declared D1-D5 artifacts match the frozen SHA-256 registry",
        ),
        (
            "D3_not_numerically_averaged",
            bool(dimension_long.loc[dimension_long["dimension"].eq("D3"), "score_1to5"].isna().all()),
            "D3 has diagnostic_score_1to5 and gate status only",
        ),
        (
            "D4_pair_level_only",
            bool(
                dimension_long.loc[dimension_long["dimension"].eq("D4"), "object_type"]
                .eq("pair")
                .all()
            ),
            "native D4 is not copied into sensor rows",
        ),
        (
            "D5_missing_not_low",
            bool(
                dimension_long.loc[
                    dimension_long["dimension"].eq("D5")
                    & ~dimension_long["report_eligible"],
                    "score_1to5",
                ]
                .isna()
                .all()
            ),
            "ineligible or missing D5 evidence remains NA",
        ),
        (
            "node_score_range",
            bool(
                node[["Q_node_full", "Q_node_core12", "Q_node_available"]]
                .stack()
                .between(score_min, score_max)
                .all()
            ),
            "all node estimands remain on the frozen 1-5 scale",
        ),
        (
            "pair_score_range",
            bool(
                pair[["Q_pair_full", "Q_pair_core", "Q_pair_available"]]
                .stack()
                .between(score_min, score_max)
                .all()
            ),
            "all pair estimands remain on the frozen 1-5 scale",
        ),
        (
            "node_evidence_range",
            bool(node["E_node"].between(0, 1).all()),
            "node evidence completeness remains in [0,1]",
        ),
        (
            "pair_evidence_range",
            bool(pair["E_pair"].between(0, 1).all()),
            "pair evidence completeness remains in [0,1]",
        ),
        (
            "complete_case_invariance",
            bool(invariance["passed"].all()),
            "Q_full equals Q_available on identical complete-evidence rows",
        ),
        (
            "quality_not_multiplied_by_evidence",
            bool(
                node["core_aggregation_formula"]
                .eq("equal_mean_D1_D2_fixed")
                .all()
                and pair["core_aggregation_formula"]
                .eq("equal_mean_left_core12_right_core12_D4_raw")
                .all()
            ),
            "Q and E remain separate published variables",
        ),
        (
            "node_core_fixed_formula",
            bool(
                np.allclose(
                    node.loc[node["Q_node_core12"].notna(), "Q_node_core12"],
                    node.loc[
                        node["Q_node_core12"].notna(), ["D1_total", "D2_total"]
                    ].mean(axis=1),
                    rtol=0,
                    atol=1e-12,
                )
            ),
            "Q_node_core12 is the fixed D1-D2 longitudinal estimand",
        ),
        (
            "pair_core_fixed_formula",
            bool(
                np.allclose(
                    pair.loc[pair["Q_pair_core"].notna(), "Q_pair_core"],
                    pair.loc[
                        pair["Q_pair_core"].notna(),
                        ["left_Q_node_core12", "right_Q_node_core12", "D4_raw"],
                    ].mean(axis=1),
                    rtol=0,
                    atol=1e-12,
                )
            ),
            "Q_pair_core is the fixed left-core/right-core/D4 estimand",
        ),
        (
            "phase_reference_metadata_complete",
            bool(
                dimension_long[["phase_role", "reference_status", "version_hash"]]
                .notna()
                .all()
                .all()
            ),
            "every dimension row carries phase, reference and version provenance",
        ),
        (
            "D4_mapping_support_metadata_complete",
            bool(
                dimension_long.loc[
                    dimension_long["dimension"].eq("D4"),
                    "mapping_support_class",
                ]
                .isin(["exact", "variable_fallback", "global_fallback", "insufficient"])
                .all()
            ),
            "D4 mapping support is explicit on every pair-hour",
        ),
        (
            "D5_L1_is_limited_evidence_not_low_quality",
            bool(
                dimension_long.loc[
                    dimension_long["dimension"].eq("D5")
                    & dimension_long["support_level"].eq("L1"),
                    ["report_eligible", "score_1to5"],
                ]
                .pipe(lambda x: (~x["report_eligible"] & x["score_1to5"].isna()).all())
            ),
            "D5 L1 remains diagnostic-only limited evidence",
        ),
        (
            "D5_hard_veto_disabled",
            config["aggregation"]["D5_sensor_hard_veto"] == "disabled_top1_below_0.80",
            "D5 report evidence cannot trigger a sensor hard Veto",
        ),
        (
            "A_E_grades_disabled",
            str(config["aggregation"]["A_E_grades"]).startswith("disabled"),
            "grades await prospective and downstream criterion validation",
        ),
        (
            "strict_release_fail_closed",
            bool(node["strict_release_status"].ne("released").all() and pair["strict_release_status"].ne("released").all()),
            "D1 lacks a distinct validated hard-fault interface",
        ),
        (
            "selection_composition_exact_closure",
            bool(decomposition["overall_closure_error"].abs().le(1e-12).all()),
            "total observed shift equals selection-only plus within-Full D5 contribution",
        ),
        (
            "pair_low_tail_partition_exact_closure",
            partitions_close,
            "formal-threshold overlap cells partition all complete pair-hours exactly",
        ),
    ]
    return pd.DataFrame(checks, columns=["check_id", "passed", "interpretation"])


def _artifact_inventory(output_root: Path, *, exclude: set[Path]) -> list[dict[str, Any]]:
    rows = []
    canonical_text_suffixes = {".csv", ".json", ".md", ".svg", ".txt", ".yaml", ".yml"}
    for path in sorted(item for item in output_root.rglob("*") if item.is_file()):
        if path in exclude:
            continue
        canonical_text = path.suffix.lower() in canonical_text_suffixes
        rows.append(
            {
                "relative_path": path.relative_to(output_root).as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": sha256_text_lf(path) if canonical_text else sha256_file(path),
                "hash_method": (
                    "sha256_utf8_lf_canonical" if canonical_text else "sha256_raw_bytes"
                ),
            }
        )
    return rows


def _summary(
    config: dict[str, Any],
    node: pd.DataFrame,
    pair: pd.DataFrame,
    block_summary: pd.DataFrame,
    decomposition: pd.DataFrame,
    pair_weighting: pd.DataFrame,
) -> dict[str, Any]:
    def counts(frame: pd.DataFrame) -> dict[str, int]:
        return {str(key): int(value) for key, value in frame["coverage_class"].value_counts().items()}

    primary_block = int(config["statistics"]["primary_block_hours"])
    primary = block_summary.loc[block_summary["block_hours"].eq(primary_block)]

    def plant_estimate(scope: str, estimand: str) -> float:
        row = primary.loc[
            primary["scope"].eq(scope) & primary["estimand"].eq(estimand), "estimate"
        ]
        return float(row.iloc[0])

    effects = decomposition.loc[
        decomposition["stratum_type"].eq("overall")
        & decomposition["stratum"].eq("all")
    ].set_index("effect")
    sensitivity = pair_weighting.iloc[0]
    return {
        "node_rows": len(node),
        "pair_rows": len(pair),
        "node_coverage": counts(node),
        "pair_coverage": counts(pair),
        "node_Q_full_nonnull": int(node["Q_node_full"].notna().sum()),
        "node_Q_core12_nonnull": int(node["Q_node_core12"].notna().sum()),
        "node_Q_available_nonnull": int(node["Q_node_available"].notna().sum()),
        "pair_Q_full_nonnull": int(pair["Q_pair_full"].notna().sum()),
        "pair_Q_core_nonnull": int(pair["Q_pair_core"].notna().sum()),
        "pair_Q_available_nonnull": int(pair["Q_pair_available"].notna().sum()),
        "sensor_hour_pooled_means": {
            "node_Q_full": float(node["Q_node_full"].mean()),
            "node_Q_core12": float(node["Q_node_core12"].mean()),
            "node_Q_availability_aware": float(node["Q_node_available"].mean()),
            "pair_Q_full": float(pair["Q_pair_full"].mean()),
            "pair_Q_core": float(pair["Q_pair_core"].mean()),
            "pair_Q_availability_aware": float(pair["Q_pair_available"].mean()),
        },
        "plant_hour_aggregated_means": {
            "node_Q_full": plant_estimate("node", "full"),
            "node_Q_core12": plant_estimate("node", "core_fixed"),
            "node_Q_availability_aware": plant_estimate("node", "availability_aware"),
            "pair_Q_full": plant_estimate("pair", "full"),
            "pair_Q_core": plant_estimate("pair", "core_fixed"),
            "pair_Q_availability_aware": plant_estimate("pair", "availability_aware"),
            "aggregation_rule": "median_across_objects_per_hour_then_mean_across_plant_hours",
        },
        "selection_composition_decomposition": {
            "selection_only": float(effects.loc["selection_only", "estimate"]),
            "within_Full_D5_compositional_contribution": float(
                effects.loc["within_Full_D5_compositional_contribution", "estimate"]
            ),
            "total_observed_estimand_shift": float(
                effects.loc["total_observed_estimand_shift", "estimate"]
            ),
            "absolute_closure_error": float(
                abs(effects["overall_closure_error"].iloc[0])
            ),
            "analysis_unit": "sensor_hour_pooled",
        },
        "pair_weighting_sensitivity": {
            "spearman": float(sensitivity["spearman"]),
            "low_tail_jaccard": float(sensitivity["low_tail_jaccard"]),
            "decision_flip_rate_at_3": float(sensitivity["decision_flip_rate_at_3"]),
            "hierarchical_low_tail_count": int(
                sensitivity["hierarchical_low_tail_count"]
            ),
            "native_atom_low_tail_count": int(
                sensitivity["native_atom_low_tail_count"]
            ),
            "intersection_both_count": int(sensitivity["intersection_both_count"]),
            "union_count": int(sensitivity["union_count"]),
            "hierarchical_event_count": int(sensitivity["hierarchical_event_count"]),
            "native_atom_event_count": int(sensitivity["native_atom_event_count"]),
            "hierarchical_median_episode_duration_h": float(
                sensitivity["hierarchical_median_episode_duration_h"]
            ),
            "native_atom_median_episode_duration_h": float(
                sensitivity["native_atom_median_episode_duration_h"]
            ),
            "formal_model_changed": False,
        },
        "D3_gate_status_node": {
            str(key): int(value) for key, value in node["D3_gate_status"].value_counts().items()
        },
        "release_status": "retrospective_scientific_aggregation_ready_with_prespecified_pending_items",
        "deployment_status": "not_released",
    }


def run_aggregation() -> dict[str, Any]:
    config = load_config()
    run_id = make_run_id(config)
    output_root = OUTPUT_ROOT
    data_root = output_root / "data"
    validation_root = output_root / "validation"
    report_root = output_root / "reports"
    manifest_root = output_root / "manifests"
    for path in (data_root, validation_root, report_root, manifest_root):
        path.mkdir(parents=True, exist_ok=True)

    input_registry = verify_frozen_inputs(config)
    d1 = load_d1(config)
    d2 = load_d2(config)
    d3 = load_d3(config)
    d4 = load_d4(config)
    d5, _ = load_d5(config)

    dimension_long = build_dimension_long(config, d1, d2, d3, d4, d5)
    phase_evidence = build_phase_evidence_summary(dimension_long)
    node = build_node_scores(config, d1, d2, d3, d5)
    pair = build_pair_scores(config, node, d4)
    monthly = build_monthly_coverage(node, pair)

    invariance = complete_case_invariance(node, pair)
    aggregators = aggregator_comparison(config, node, pair)
    ablation = dimension_ablation(config, node, pair)
    weight_draws, weight_summary = weight_sensitivity(config, node, pair)
    selection = coverage_shift(node)
    decomposition, decomposition_draws = selection_composition_decomposition(config, node)
    block_summary = block_bootstrap_summary(config, node, pair)
    construct = construct_validity(config, pair)
    (
        pair_weighting,
        pair_weighting_rows,
        pair_threshold_sweep,
        pair_low_tail_episodes,
    ) = pair_weighting_sensitivity(config, pair)
    pending = pending_validation_registry(config)
    contracts = _contract_checks(
        config,
        inputs=input_registry,
        dimension_long=dimension_long,
        node=node,
        pair=pair,
        invariance=invariance,
        decomposition=decomposition,
        pair_threshold_sweep=pair_threshold_sweep,
    )
    if not contracts["passed"].all():
        failed = contracts.loc[~contracts["passed"], "check_id"].tolist()
        raise RuntimeError(f"Aggregation contract checks failed: {failed}")

    artifact_names = config["output_artifacts"]
    data_paths = {
        "dimension_long": data_root / artifact_names["dimension_long"],
        "node_hourly": data_root / artifact_names["node_scores"],
        "pair_hourly": data_root / artifact_names["pair_scores"],
        "coverage_monthly": data_root / artifact_names["coverage_monthly"],
        "phase_evidence_summary": data_root / artifact_names["phase_evidence_summary"],
        "estimand_decomposition": data_root / "DQR_estimand_decomposition.parquet",
        "estimand_decomposition_bootstrap": data_root / "DQR_estimand_decomposition_bootstrap.parquet",
        "pair_weighting_sensitivity": data_root / "DQR_pair_weighting_sensitivity.parquet",
        "pair_low_tail_threshold_sweep": data_root / "DQR_pair_low_tail_threshold_sweep.parquet",
        "pair_low_tail_episodes": data_root / "DQR_pair_low_tail_episodes.parquet",
    }
    dimension_long.to_parquet(data_paths["dimension_long"], index=False)
    node.to_parquet(data_paths["node_hourly"], index=False)
    pair.to_parquet(data_paths["pair_hourly"], index=False)
    monthly.to_parquet(data_paths["coverage_monthly"], index=False)
    phase_evidence.to_parquet(data_paths["phase_evidence_summary"], index=False)
    decomposition.to_parquet(data_paths["estimand_decomposition"], index=False)
    decomposition_draws.to_parquet(
        data_paths["estimand_decomposition_bootstrap"], index=False
    )
    pair_weighting_rows.to_parquet(data_paths["pair_weighting_sensitivity"], index=False)
    pair_threshold_sweep.to_parquet(
        data_paths["pair_low_tail_threshold_sweep"], index=False
    )
    pair_low_tail_episodes.to_parquet(
        data_paths["pair_low_tail_episodes"], index=False
    )

    validation_path = validation_root / "DQR_aggregation_validation.xlsx"
    write_workbook(
        validation_path,
        {
            "input_freshness": input_registry,
            "phase_evidence_summary": phase_evidence,
            "contract_checks": contracts,
            "complete_case_identity": invariance,
            "aggregator_comparison": aggregators,
            "weight_summary": weight_summary,
            "weight_draws": weight_draws,
            "dimension_ablation": ablation,
            "coverage_selection": selection,
            "estimand_decomposition": decomposition,
            "estimand_bootstrap": decomposition_draws,
            "block_bootstrap": block_summary,
            "construct_validity": construct,
            "pair_weighting": pair_weighting,
            "pair_threshold_sweep": pair_threshold_sweep,
            "pair_low_tail_episodes": pair_low_tail_episodes,
            "pending_registry": pending,
        },
    )
    downstream_path = validation_root / "DQR_downstream_validation.xlsx"
    write_workbook(
        downstream_path,
        {
            "status": pending.loc[pending["validation_id"].isin(["V7-prospective-temporal-holdout", "V8-downstream-fitness-for-use"])],
            "required_endpoints": pd.DataFrame(
                {
                    "endpoint_family": ["prediction", "state estimation", "process simulation"],
                    "required_frozen_bundle": ["forecast targets and split", "EnKF residual/coverage targets", "SUMO fitness-for-use targets"],
                    "current_status": ["not_available", "not_available", "not_available"],
                    "score_effect": ["none", "none", "none"],
                }
            ),
        },
    )
    qa_json = validation_root / "DQR_contract_checks.json"
    write_json(
        qa_json,
        {
            "run_id": run_id,
            "passed": bool(contracts["passed"].all()),
            "checks": contracts.to_dict("records"),
            "table_hashes": {
                "dimension_long": stable_frame_hash(dimension_long),
                "node_hourly": stable_frame_hash(node),
                "pair_hourly": stable_frame_hash(pair),
                "coverage_monthly": stable_frame_hash(monthly),
                "phase_evidence_summary": stable_frame_hash(phase_evidence),
                "estimand_decomposition": stable_frame_hash(decomposition),
                "pair_weighting_sensitivity": stable_frame_hash(pair_weighting_rows),
                "pair_low_tail_threshold_sweep": stable_frame_hash(pair_threshold_sweep),
                "pair_low_tail_episodes": stable_frame_hash(pair_low_tail_episodes),
            },
        },
    )

    figure_paths = build_all_figures(
        config,
        output_root=output_root,
        node=node,
        pair=pair,
        monthly=monthly,
        aggregators=aggregators,
        weight_draws=weight_draws,
        ablation=ablation,
        construct=construct,
        decomposition=decomposition,
        pair_weighting_summary=pair_weighting,
        pair_weighting_rows=pair_weighting_rows,
        pair_threshold_sweep=pair_threshold_sweep,
        pair_low_tail_episodes=pair_low_tail_episodes,
    )
    figure_qa = run_figure_qa(
        output_root / "figures", validation_root / "DQR_figure_qa.json"
    )

    report_path = report_root / "DQR_aggregation_scientific_report.md"
    write_scientific_report(
        report_path,
        run_id=run_id,
        node=node,
        pair=pair,
        invariance=invariance,
        aggregators=aggregators,
        weight_summary=weight_summary,
        coverage_shift=selection,
        block_summary=block_summary,
        construct=construct,
        decomposition=decomposition,
        pair_weighting=pair_weighting,
        pair_threshold_sweep=pair_threshold_sweep,
        pending=pending,
    )
    write_directory_guide(report_root / "DQR_aggregation_directory_guide.md")
    write_figure_captions(report_root / "DQR_figure_captions.md")
    write_expert_review(report_root / "DQR_v2.3_expert_review.md", node, pair)
    estimand_registry = {
        "schema_version": config["schema_version"],
        "quality_evidence_gate_contract": config["evidence_contract"],
        "node_estimands": config["aggregation"]["node_estimands"],
        "pair_estimands": config["aggregation"]["pair_estimands"],
        "longitudinal_primary": config["aggregation"]["longitudinal_primary"],
        "complete_evidence_primary": config["aggregation"]["complete_evidence_primary"],
        "phase_contracts": config["phase_contracts"],
        "claim_boundary": {
            "full": "complete-evidence scientific estimand",
            "core_fixed": "fixed-composition longitudinal estimand",
            "available": "operational extension; cross-mask trend interpretation prohibited",
        },
    }
    (data_root / artifact_names["estimand_registry"]).write_text(
        yaml.safe_dump(estimand_registry, sort_keys=False, allow_unicode=False),
        encoding="utf-8",
    )

    run_manifest_path = manifest_root / "DQR_run_manifest.json"
    publication_manifest_path = manifest_root / "DQR_publication_manifest.json"
    configuration = generation_configuration_record()
    code_sources = generation_source_registry()
    scientific_content_sha256 = generation_content_sha256(
        configuration, code_sources, input_registry
    )
    scientific_generation_commit = git_commit()
    run_manifest = {
        "schema_version": config["schema_version"],
        "contract_version": config["contract_version"],
        "run_id": run_id,
        "provenance": {
            "scientific_generation_commit": scientific_generation_commit,
            "scientific_generation_content_sha256": scientific_content_sha256,
            "authority": "code_config_and_frozen_input_content_hashes",
            "publication_bundle_commit": "external_release_commit_or_tag_not_embedded_to_avoid_self_reference",
            "packaging_changes_after_generation": "permitted_only_when_scientific_content_hash_remains_exact",
        },
        "configuration": configuration,
        "code_sources": code_sources,
        "input_registry": input_registry.to_dict("records"),
        "contracts": contracts.to_dict("records"),
        "summary": _summary(
            config, node, pair, block_summary, decomposition, pair_weighting
        ),
        "validation_status": pending.to_dict("records"),
        "figure_qa_passed": figure_qa["passed"],
        "artifacts": _artifact_inventory(
            output_root, exclude={run_manifest_path, publication_manifest_path}
        ),
    }
    write_json(run_manifest_path, run_manifest)
    publication_manifest = {
        "schema_version": "northbank-dqr-publication-manifest-v2.2",
        "run_id": run_id,
        "provenance": run_manifest["provenance"],
        "release_status": run_manifest["summary"]["release_status"],
        "claim_boundary": {
            "A_E_grades": "disabled",
            "D5_hard_veto": "disabled",
            "prospective_validation": config["study"]["future_holdout"]["status"],
            "downstream_validation": "pending_not_executed",
            "deployment": "not_released",
        },
        "source_dependencies": input_registry.to_dict("records"),
        "artifacts": _artifact_inventory(output_root, exclude={publication_manifest_path}),
    }
    write_json(publication_manifest_path, publication_manifest)
    return {
        "run_id": run_id,
        "output_root": str(output_root),
        "summary": run_manifest["summary"],
        "contract_checks_passed": True,
        "figure_qa_passed": True,
        "figure_files": [str(path) for path in figure_paths],
        "run_manifest": str(run_manifest_path),
        "publication_manifest": str(publication_manifest_path),
    }
