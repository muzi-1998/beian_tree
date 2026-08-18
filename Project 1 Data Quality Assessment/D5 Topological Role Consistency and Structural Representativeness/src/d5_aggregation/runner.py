from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .common import (
    CONFIG_PATH,
    OUTPUT_ROOT,
    git_commit,
    load_config,
    make_run_id,
    sha256_file,
    stable_frame_hash,
    write_json,
)
from .figures import build_all_figures, run_figure_qa
from .pipeline import (
    build_dimension_long,
    build_monthly_coverage,
    build_node_scores,
    build_pair_scores,
    load_d1,
    load_d2,
    load_d3,
    load_d4,
    load_d5,
    verify_frozen_inputs,
)
from .reports import (
    write_directory_guide,
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
) -> pd.DataFrame:
    score_min = float(config["aggregation"]["score_min"])
    score_max = float(config["aggregation"]["score_max"])
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
            bool(node["Q_node_available"].dropna().between(score_min, score_max).all()),
            "availability-aware node scores remain on the frozen 1-5 scale",
        ),
        (
            "pair_score_range",
            bool(pair["Q_pair_available"].dropna().between(score_min, score_max).all()),
            "availability-aware pair scores remain on the frozen 1-5 scale",
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
                node["aggregation_formula"]
                .eq("equal_arithmetic_mean_over_D1_D2_optional_D5")
                .all()
                and pair["aggregation_formula"]
                .eq("equal_mean_left_node_right_node_D4_raw")
                .all()
            ),
            "Q and E remain separate published variables",
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
    ]
    return pd.DataFrame(checks, columns=["check_id", "passed", "interpretation"])


def _artifact_inventory(output_root: Path, *, exclude: set[Path]) -> list[dict[str, Any]]:
    rows = []
    for path in sorted(item for item in output_root.rglob("*") if item.is_file()):
        if path in exclude:
            continue
        rows.append(
            {
                "relative_path": path.relative_to(output_root).as_posix(),
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return rows


def _summary(node: pd.DataFrame, pair: pd.DataFrame) -> dict[str, Any]:
    def counts(frame: pd.DataFrame) -> dict[str, int]:
        return {str(key): int(value) for key, value in frame["coverage_class"].value_counts().items()}

    return {
        "node_rows": len(node),
        "pair_rows": len(pair),
        "node_coverage": counts(node),
        "pair_coverage": counts(pair),
        "node_Q_full_nonnull": int(node["Q_node_full"].notna().sum()),
        "node_Q_available_nonnull": int(node["Q_node_available"].notna().sum()),
        "pair_Q_full_nonnull": int(pair["Q_pair_full"].notna().sum()),
        "pair_Q_available_nonnull": int(pair["Q_pair_available"].notna().sum()),
        "node_Q_full_mean": float(node["Q_node_full"].mean()),
        "node_Q_available_mean": float(node["Q_node_available"].mean()),
        "pair_Q_full_mean": float(pair["Q_pair_full"].mean()),
        "pair_Q_available_mean": float(pair["Q_pair_available"].mean()),
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
    node = build_node_scores(config, d1, d2, d3, d5)
    pair = build_pair_scores(config, node, d4)
    monthly = build_monthly_coverage(node, pair)

    invariance = complete_case_invariance(node, pair)
    aggregators = aggregator_comparison(config, node, pair)
    ablation = dimension_ablation(config, node, pair)
    weight_draws, weight_summary = weight_sensitivity(config, node, pair)
    selection = coverage_shift(node)
    block_summary = block_bootstrap_summary(config, node, pair)
    construct = construct_validity(config, pair)
    pending = pending_validation_registry(config)
    contracts = _contract_checks(
        config,
        inputs=input_registry,
        dimension_long=dimension_long,
        node=node,
        pair=pair,
        invariance=invariance,
    )
    if not contracts["passed"].all():
        failed = contracts.loc[~contracts["passed"], "check_id"].tolist()
        raise RuntimeError(f"Aggregation contract checks failed: {failed}")

    data_paths = {
        "dimension_long": data_root / "DQR_dimension_long.parquet",
        "node_hourly": data_root / "DQR_node_hourly.parquet",
        "pair_hourly": data_root / "DQR_pair_hourly.parquet",
        "coverage_monthly": data_root / "DQR_coverage_monthly.parquet",
    }
    dimension_long.to_parquet(data_paths["dimension_long"], index=False)
    node.to_parquet(data_paths["node_hourly"], index=False)
    pair.to_parquet(data_paths["pair_hourly"], index=False)
    monthly.to_parquet(data_paths["coverage_monthly"], index=False)

    validation_path = validation_root / "DQR_aggregation_validation.xlsx"
    write_workbook(
        validation_path,
        {
            "input_freshness": input_registry,
            "contract_checks": contracts,
            "complete_case_identity": invariance,
            "aggregator_comparison": aggregators,
            "weight_summary": weight_summary,
            "weight_draws": weight_draws,
            "dimension_ablation": ablation,
            "coverage_selection": selection,
            "block_bootstrap": block_summary,
            "construct_validity": construct,
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
        pending=pending,
    )
    write_directory_guide(report_root / "DQR_aggregation_directory_guide.md")
    write_figure_captions(report_root / "DQR_figure_captions.md")

    run_manifest_path = manifest_root / "DQR_run_manifest.json"
    publication_manifest_path = manifest_root / "DQR_publication_manifest.json"
    source_files = sorted((Path(__file__).parent).glob("*.py"))
    run_manifest = {
        "schema_version": config["schema_version"],
        "contract_version": config["contract_version"],
        "run_id": run_id,
        "source_commit_base": git_commit(),
        "configuration": {
            "path": str(CONFIG_PATH.relative_to(CONFIG_PATH.parents[2])).replace("\\", "/"),
            "sha256": sha256_file(CONFIG_PATH),
        },
        "code_sources": [
            {"path": str(path.relative_to(CONFIG_PATH.parents[2])).replace("\\", "/"), "sha256": sha256_file(path)}
            for path in source_files
        ],
        "input_registry": input_registry.to_dict("records"),
        "contracts": contracts.to_dict("records"),
        "summary": _summary(node, pair),
        "validation_status": pending.to_dict("records"),
        "figure_qa_passed": figure_qa["passed"],
        "artifacts": _artifact_inventory(
            output_root, exclude={run_manifest_path, publication_manifest_path}
        ),
    }
    write_json(run_manifest_path, run_manifest)
    publication_manifest = {
        "schema_version": "northbank-dqr-publication-manifest-v2.0",
        "run_id": run_id,
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
