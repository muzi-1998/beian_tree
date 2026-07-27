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
) -> Path:
    d1_summary = d1["D1_injection_summary"]
    d2_summary = d2["D2_oat_summary"]
    d3_summary = d3["D3_oat_summary"]
    d4_summary = d4["D4_mechanism_summary"]
    d5_acceptance = d5["D5_acceptance"]
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
        "| D1 | Core-fault mixed injection design across analyte, regime and routing strata | Internal mechanism validation complete; field truth pending |",
        "| D2 | QFA-window, hard-RLE and gap-mapping OAT with full sensor-hour rescoring | Complete |",
        "| D3 | Grade A instrument Fail, Grade B value/rate Warn and legacy-score separation | Complete; site approval of Grade B sources pending |",
        "| D4 | Target, peer, common-process, opposite-direction and lag mechanisms | Complete; ORP shrinkage remains sensitivity-only |",
        "| D5 | Component ablation, blocked-month validation, support funnel and locked admission audit | Partial: context/template ablations require outer-fold refit |",
        "| Composite | Node/pair/plant products, coverage, 7 d and 48 h bootstrap, dimension ablation | Complete without formal A-E grades |",
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
            "D1 injections are parameterized in original measurement units and projected through the frozen training-time detector route. "
            "The implementation does not refit decomposition or whitening on each contaminated test window. This revision is deliberate: "
            "test-window refitting would leak fault information and allow preprocessing to adapt to the injected fault.",
            "",
            "### D2",
            "",
            f"- Minimum channel-rank Spearman across OAT: {_format_metric(d2_summary['channel_rank_spearman'].min())}.",
            f"- Minimum event Jaccard across OAT: {_format_metric(d2_summary['event_jaccard'].min())}.",
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
        lines.append(f"- {row.scenario} / {row.metric}: {_format_metric(row.estimate)} (n={row.n_independent_windows}).")
    lines.extend(["", "### D5", ""])
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
    lines.extend(
        [
            "",
            "### Composite",
            "",
            f"- Formal node-score rows: {int(node['Q_node'].notna().sum()):,}.",
            f"- Full/basic/limited/insufficient coverage: "
            + ", ".join(
                f"{key}={int(value):,}"
                for key, value in node["coverage_class"].value_counts().items()
            )
            + ".",
            f"- Formal pair-score rows: {int(pair['Q_pair'].notna().sum()):,}.",
            "- D3 is not averaged into Q_node or Q_pair; Fail prevents a high-confidence grade and Warn is retained as an explicit label.",
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
            "## Publication decision",
            "",
            "The package is suitable for a retrospective single-plant methods manuscript after the pending full-refit D5 context ablations "
            "and the listed method locks are resolved. It is not yet suitable for an operational deployment claim or a cross-plant "
            "generalization claim.",
        ]
    )
    path = output_dir / "D1_D5_V2_EXECUTION_REPORT.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
