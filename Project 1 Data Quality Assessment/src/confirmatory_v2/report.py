from __future__ import annotations

from pathlib import Path

import pandas as pd

from .common import CONFIG_ROOT, read_yaml


def _format_metric(value: float) -> str:
    return "NA" if pd.isna(value) else f"{value:.3f}"


def build_execution_report(
    output_dir: Path,
    run_id: str,
    d1: dict[str, pd.DataFrame],
    d2: dict[str, pd.DataFrame],
    d3: dict[str, pd.DataFrame],
    d4: dict[str, pd.DataFrame],
    d5: dict[str, pd.DataFrame],
    composite: dict[str, pd.DataFrame],
    coverage_selection: dict[str, pd.DataFrame],
) -> Path:
    d1_summary = d1["D1_injection_summary"]
    d2_summary = d2["D2_oat_summary"]
    d3_summary = d3["D3_oat_summary"]
    d4_summary = d4["D4_mechanism_summary"]
    d5_acceptance = d5["D5_acceptance"]
    d5_outer = d5["D5_outer_refit_summary"]
    d1_raw = d1["D1_raw_endpoint_summary"]
    d1_high = d1["D1_high_amplitude_summary"]
    d2_floor_checks = d2["D2_process_floor_contract_checks"]
    d4_control_contract = d4["D4_common_change_contract"]
    d5_paired = d5["D5_outer_refit_paired_delta_summary"]
    coverage_summary = coverage_selection[
        "D5_coverage_selection_summary"
    ].set_index("indicator")["value"]
    gate_counts = d3["D3_safety_gate"]["D3_gate_status"].value_counts()
    node = composite["WWDQS_node_scores"]
    pair = composite["WWDQS_pair_scores"]
    ambiguities = read_yaml(CONFIG_ROOT / "ambiguity_registry.yaml")["items"]

    lines = [
        "# D1-D5 v2.0 confirmatory execution report",
        "",
        f"Run ID: `{run_id}`",
        "",
        "## Expert feasibility verdict",
        "",
        "The reduced v2.0 design is scientifically coherent and more defensible than an equal-status five-score average. "
        "D1, D2, D4 and D5 remain dynamic scientific evidence; D3 is implemented as an independent non-compensatory Safety Gate. "
        "The composite uses transparent equal weights for eligible D1/D2/D5 node evidence and adds D4 only at pair level.",
        "",
        "The current record supports retrospective within-plant validation. It does not support prospective, maintenance-truth, "
        "cross-plant or learned-optimal-weight claims.",
        "",
        "## Executed work packages",
        "",
        "| Work package | Execution | Decision |",
        "|---|---|---|",
        "| WP0 | Frozen SAP, claim registry, split registry, figure contract and immutable run manifest | Complete |",
        "| D1 | Route-accurate core-fault validation plus raw-domain frozen-transform endpoint audit | Internal mechanism validation complete; field truth pending |",
        "| D2 | QFA-window, hard-RLE and gap-mapping OAT with full sensor-hour rescoring | Complete |",
        "| D3 | Grade A instrument Fail, Grade B value/rate Warn and legacy-score separation | Complete; site approval of Grade B sources pending |",
        "| D4 | Target, peer, common-process, opposite-direction and lag mechanisms with timestamp-clustered CI | Complete; ORP shrinkage remains sensitivity-only |",
        "| D5 | Three prespecified structural ablations with complete future-month outer refit | Complete for retrospective validation; deployment governance pending |",
        "| Composite | Full/basic-stratified node, pair and plant products with 7 d and 48 h block bootstrap | Complete without formal A-E grades |",
        "",
        "## Key numerical results",
        "",
        "### D1",
        "",
    ]
    for row in d1_summary.itertuples(index=False):
        lines.append(
            f"- {row.fault_type}: recall {_format_metric(row.event_recall)} "
            f"(95% CI {_format_metric(row.recall_ci_low)}-{_format_metric(row.recall_ci_high)}), "
            f"AUROC {_format_metric(row.AUROC)}, false alarms/sensor-day "
            f"{_format_metric(row.false_alarms_per_sensor_day)}."
        )
    lines.extend(
        [
            "",
            "The full D1 design is explicitly route-level: spike uses the residual route, step the routed whitened detector input, "
            "drift the fixed PLS route, and hard freeze the raw minute route. A separate prespecified subset injects each fault in "
            "the raw measurement domain and applies decomposition/whitening parameters fitted before the validation period and then frozen. "
            "No contaminated test window is used to refit preprocessing.",
            "",
            "Raw-domain frozen-transform audit:",
        ]
    )
    for row in d1_raw.itertuples(index=False):
        lines.append(
            f"- {row.fault_type}: raw-domain recall {_format_metric(row.raw_domain_recall)} "
            f"(cluster 95% CI {_format_metric(row.recall_ci_low)}-{_format_metric(row.recall_ci_high)}), "
            f"route/raw agreement {_format_metric(row.detection_agreement)}; n={int(row.n_scenarios)}."
        )
    high_primary = d1_high[
        d1_high["resolution_mode"].eq("original")
        & d1_high["route"].eq("all_routes")
    ]
    if high_primary.empty:
        high_primary = d1_high[d1_high["resolution_mode"].eq("original")]
    lines.extend(
        [
            "",
            f"At the locked >=2 sigma region, {int(high_primary['target_passed'].sum())}/"
            f"{len(high_primary)} analyte-route strata met the 0.80 recall target. "
            "The amplitude-duration maps retain low-recall regions instead of pooling them away.",
            "",
            "Spike and Step thresholds were not lowered after observing these results. "
            "Any revised detector would require a new development set and an untouched "
            "or external validation set; the present package treats low recall as an "
            "applicability boundary.",
            "",
            "### D2",
            "",
            f"- Minimum channel-rank Spearman across OAT: {_format_metric(d2_summary['channel_rank_spearman'].min())}.",
            f"- Minimum event Jaccard across OAT: {_format_metric(d2_summary['event_jaccard'].min())}.",
            f"- Process-floor contract checks passed: "
            f"{int(d2_floor_checks['passed'].sum())}/{len(d2_floor_checks)}.",
            "- DO_1_4 and DO_2_4 share the same process-floor semantics: low IQR is diagnostic, "
            "hard digital lock remains unavailable, and missing/long-gap evidence is never exempted.",
            "",
            "### D3",
            "",
            f"- Gate hours/windows: Pass {int(gate_counts.get('Pass', 0))}, Warn {int(gate_counts.get('Warn', 0))}, "
            f"Fail {int(gate_counts.get('Fail', 0))}.",
            f"- Minimum warning-event Jaccard across OAT: {_format_metric(d3_summary['event_jaccard'].min())}.",
            "",
            "### D4",
            "",
        ]
    )
    for row in d4_summary.itertuples(index=False):
        n_value = getattr(row, "n_pair_windows", pd.NA)
        lines.append(
            f"- {row.scenario} / {row.metric}: {_format_metric(row.estimate)} "
            f"(pair-windows={n_value}, timestamp-clustered where applicable)."
        )
    lines.append("")
    for row in d4_control_contract.itertuples(index=False):
        lines.append(
            f"- {row.scenario}: {row.statistical_role}; endpoint {row.contract_endpoint}; "
            f"{'included' if row.contributes_to_common_process_FAR else 'excluded'} "
            f"from common-process FAR; contract "
            f"{'Pass' if row.role_contract_passed else 'Fail'}."
        )
    lines.extend(
        [
            "",
            "Subhour D4 lag values are retained as supplementary sensitivity only. "
            "They do not replace D4_raw or support a formal subhour monotonicity claim. "
            "ORP shrinkage remains an exploratory sparse-support analysis.",
            "",
            "### D5",
            "",
        ]
    )
    for row in d5_acceptance.itertuples(index=False):
        if row.criterion in {
            "swap_AUROC",
            "swap_AUPRC",
            "swap_Top1",
            "common_mode_FAR",
            "zone_coherent_FAR",
        }:
            lines.append(
                f"- {row.criterion}: {_format_metric(row.estimate)}; target {row.operator} {row.target}; "
                f"{'Pass' if row.passed else 'Fail'}."
            )
    lines.append("")
    lines.append("Complete future-month outer refits:")
    for row in d5_outer.itertuples(index=False):
        lines.append(
            f"- {row.variant} / {row.metric}: {_format_metric(row.estimate)} "
            f"(outer-fold 95% CI {_format_metric(row.ci95_low)}-"
            f"{_format_metric(row.ci95_high)}); "
            f"{'Pass' if row.passed else 'Fail'} against {row.threshold:.2f}."
        )
    lines.extend(
        [
            "",
            "Paired Full-minus-ablation future-month effects:",
        ]
    )
    for row in d5_paired.itertuples(index=False):
        lines.append(
            f"- {row.ablation_variant} / {row.metric}: delta "
            f"{_format_metric(row.mean_delta_full_minus_ablation)} "
            f"(outer-month 95% CI {_format_metric(row.ci95_low)}-"
            f"{_format_metric(row.ci95_high)}; positive in "
            f"{row.positive_gain_fold_fraction:.1%} of folds)."
        )
    full_top1 = d5_outer[
        d5_outer["variant"].eq("full_reference")
        & d5_outer["metric"].eq("Top1")
    ].iloc[0]
    lines.extend(
        [
            "",
            f"Full-model Top-1 localization is {_format_metric(full_top1['estimate'])} "
            f"(95% CI {_format_metric(full_top1['ci95_low'])}-"
            f"{_format_metric(full_top1['ci95_high'])}) and does not meet the "
            "locked 0.80 criterion. This limits exact node localization and keeps "
            "sensor-level hard Veto disabled; it does not invalidate report-grade "
            "D5 detection or retrospective composite aggregation.",
        ]
    )
    lines.extend(
        [
            "",
            "### Composite",
            "",
            f"- Full node-score rows: {int(node['Q_node_full'].notna().sum()):,}.",
            f"- Basic extension rows: {int(node['Q_node_basic'].notna().sum()):,}.",
            f"- Full/basic/limited/insufficient coverage: "
            + ", ".join(
                f"{key}={int(value):,}"
                for key, value in node["coverage_class"].value_counts().items()
            )
            + ".",
            f"- Formal pair-score rows: {int(pair['Q_pair'].notna().sum()):,}.",
            f"- Full/basic pair rows: {int(pair['Q_pair_full'].notna().sum()):,}/"
            f"{int(pair['Q_pair_basic'].notna().sum()):,}.",
            "- D3 is not averaged into Q_node or Q_pair; Fail prevents a high-confidence grade and Warn is retained as an explicit label.",
            f"- Coverage-selection audit: Full "
            f"{int(coverage_summary['full_sensor_hours']):,} sensor-hours, Basic "
            f"{int(coverage_summary['basic_sensor_hours']):,}; Basic OOD share "
            f"{float(coverage_summary['basic_OOD_share']):.1%} versus Full "
            f"{float(coverage_summary['full_OOD_share']):.1%}.",
            "- Full is a complete-evidence, calendar/regime/support-selected estimand. "
            "It is not generalized to all sensor-hours; Basic is reported separately.",
            "",
            "## Pending or disputed items",
            "",
            "| ID | Issue | Current handling | Recommended resolution |",
            "|---|---|---|---|",
        ]
    )
    for item in ambiguities:
        lines.append(
            f"| {item['ambiguity_id']} | {item['issue']} | {item['execution_policy']} | "
            f"{item['recommended_resolution']} |"
        )
    lines.extend(
        [
            "",
            "## External evidence still required",
            "",
            "- D1 maintenance/operator fault and verified recovery records.",
            "- D2 SCADA communication, network alarm and planned-shutdown logs.",
            "- D3 signed site approval for Grade B operating and rate rules, plus independently adjudicated warning events.",
            "- D4 independently adjudicated synchronization/asymmetry events.",
            "- A truly unseen future period and preferably a second treatment plant.",
            "- An independent downstream criterion before any learned weighting or operational-utility claim.",
            "",
            "## Prespecified failures retained",
            "",
            "- D1 Spike/Step low-recall regions remain visible in the amplitude-duration maps.",
            "- D2 settings that fail the 0.75 event-Jaccard threshold remain in the main OAT figure.",
            "- D4 subhour lag monotonicity is not claimed and is shown as sensitivity-only.",
            "- D5 variants that fail the locked 0.80 Top-1 localization threshold remain reported.",
            "",
            "## Publication decision",
            "",
            "The package is suitable for a retrospective single-plant methods manuscript with explicit claim boundaries. "
            "The completed D5 outer refits remove the previous structural-ablation blocker. It remains unsuitable for an operational "
            "deployment claim, learned-optimal-weight claim or cross-plant generalization claim until the listed external evidence is available.",
        ]
    )
    path = output_dir / "D1_D5_V2_EXECUTION_REPORT.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
