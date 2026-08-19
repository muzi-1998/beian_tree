from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter


def write_workbook(path: Path, sheets: dict[str, pd.DataFrame]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        for name, frame in sheets.items():
            frame.to_excel(writer, sheet_name=name[:31], index=False)
        for sheet in writer.book.worksheets:
            sheet.freeze_panes = "A2"
            sheet.auto_filter.ref = sheet.dimensions
            for cell in sheet[1]:
                cell.font = Font(name="Arial", size=9, bold=True, color="FFFFFF")
                cell.fill = PatternFill("solid", fgColor="3D5A80")
                cell.alignment = Alignment(horizontal="center", vertical="center")
            for column_index, cells in enumerate(sheet.columns, 1):
                values = [str(cell.value) if cell.value is not None else "" for cell in cells]
                width = min(max(max(map(len, values), default=0) + 2, 10), 42)
                sheet.column_dimensions[get_column_letter(column_index)].width = width
                for cell in cells[1:]:
                    cell.font = Font(name="Arial", size=8)
                    cell.alignment = Alignment(vertical="top", wrap_text=True)


def _pct(value: float) -> str:
    return f"{100 * value:.1f}%"


def write_scientific_report(
    path: Path,
    *,
    run_id: str,
    node: pd.DataFrame,
    pair: pd.DataFrame,
    invariance: pd.DataFrame,
    aggregators: pd.DataFrame,
    weight_summary: pd.DataFrame,
    coverage_shift: pd.DataFrame,
    block_summary: pd.DataFrame,
    construct: pd.DataFrame,
    decomposition: pd.DataFrame,
    pair_weighting: pd.DataFrame,
    pair_threshold_sweep: pd.DataFrame,
    pending: pd.DataFrame,
) -> None:
    node_counts = node["coverage_class"].value_counts()
    pair_counts = pair["coverage_class"].value_counts()
    primary = block_summary.loc[block_summary["block_hours"].eq(168)].copy()
    selection = coverage_shift.loc[
        (coverage_shift["stratum_type"] == "overall")
        & (coverage_shift["stratum"] == "all")
    ].iloc[0]
    d4_d5_report = construct.loc[
        (construct["scope"] == "D4_D5_dual_scope")
        & (construct["right"] == "D5_report")
    ].iloc[0]
    d4_d5_raw = construct.loc[
        (construct["scope"] == "D4_D5_dual_scope")
        & (construct["right"] == "D5_raw")
    ].iloc[0]
    effects = decomposition.loc[
        decomposition["stratum_type"].eq("overall")
        & decomposition["stratum"].eq("all")
    ].set_index("effect")
    pair_native = pair_weighting.iloc[0]
    node_equal = aggregators.loc[
        (aggregators["scope"] == "node")
        & (aggregators["aggregator"] == "arithmetic_equal_weight")
    ].iloc[0]
    pair_equal = aggregators.loc[
        (aggregators["scope"] == "pair")
        & (aggregators["aggregator"] == "arithmetic_equal_weight")
    ].iloc[0]
    node_weight = weight_summary.loc[
        (weight_summary["scope"] == "node")
        & (weight_summary["metric"] == "spearman_vs_equal")
    ].iloc[0]
    pair_weight = weight_summary.loc[
        (weight_summary["scope"] == "pair")
        & (weight_summary["metric"] == "spearman_vs_equal")
    ].iloc[0]
    rows = [
        "# D1-D5 hierarchical data-quality aggregation report",
        "",
        f"Run ID: `{run_id}`",
        "",
        "## Confirmatory estimands",
        "",
        "The release implements a hierarchical Quality-Evidence-Gate contract. "
        "D1, D2 and eligible D5 evidence form node-level quality; homologous left/right "
        "node quality and native D4_raw form pair-level quality. D3 is retained as an "
        "independent non-compensatory safety gate and is never averaged into either score. "
        "Evidence completeness is reported separately and is never multiplied by quality.",
        "",
        "- `Q_node_full = mean(D1, D2, D5_report)` when all three formal scores exist.",
        "- `Q_node_available = mean(D1, D2[, D5_report])`; D1 and D2 are mandatory.",
        "- `Q_pair_full = mean(left Q_node_full, right Q_node_full, D4_raw)`.",
        "- `Q_pair_available = mean(left Q_node_available, right Q_node_available, D4_raw)`.",
        "- `E_node` and `E_pair` quantify evidence coverage, not data quality.",
        "",
        "## Current results",
        "",
        f"The node table contains {len(node):,} sensor-hours: "
        f"{node_counts.get('full', 0):,} Full, {node_counts.get('basic', 0):,} Basic, "
        f"{node_counts.get('limited', 0):,} Limited and "
        f"{node_counts.get('insufficient', 0):,} Insufficient. The pair table contains "
        f"{len(pair):,} native pair-hours: {pair_counts.get('full', 0):,} Full, "
        f"{pair_counts.get('basic', 0):,} Basic and {pair_counts.get('limited', 0):,} Limited.",
        "",
        f"The complete-case identity check passed for both levels (maximum absolute "
        f"difference {invariance['maximum_absolute_difference'].max():.3g}). Under equal "
        f"arithmetic aggregation, the complete-evidence low-tail rate was "
        f"{_pct(node_equal['low_tail_rate'])} for nodes and {_pct(pair_equal['low_tail_rate'])} "
        "for pairs.",
        "",
        f"Sensor-hour pooled means were {node['Q_node_full'].mean():.3f} (node Full), "
        f"{node['Q_node_available'].mean():.3f} (node availability-aware), "
        f"{pair['Q_pair_full'].mean():.3f} (pair Full) and "
        f"{pair['Q_pair_available'].mean():.3f} (pair availability-aware). These are "
        "not the plant-hour aggregated means reported below, which first summarize all "
        "objects within each plant-hour and then average over time.",
        "",
        f"The Full and Basic node subsets are not exchangeable: their overall standardized "
        f"mean difference was {selection['standardized_mean_difference_full_minus_basic']:.2f} "
        f"and Wasserstein distance was {selection['wasserstein_distance']:.2f}. Full is "
        "therefore the complete-evidence estimand; availability-aware Basic extends coverage "
        "but must be displayed separately.",
        "",
        f"The sensor-hour estimand decomposition separated a selection-only shift of "
        f"{effects.loc['selection_only', 'estimate']:.3f} "
        f"(95% block CI {effects.loc['selection_only', 'ci_low']:.3f} to "
        f"{effects.loc['selection_only', 'ci_high']:.3f}) from a within-Full D5 "
        f"compositional contribution of "
        f"{effects.loc['within_Full_D5_compositional_contribution', 'estimate']:.3f} "
        f"({effects.loc['within_Full_D5_compositional_contribution', 'ci_low']:.3f} to "
        f"{effects.loc['within_Full_D5_compositional_contribution', 'ci_high']:.3f}). "
        f"Their sum equals the total "
        f"observed estimand shift of "
        f"{effects.loc['total_observed_estimand_shift', 'estimate']:.3f}; absolute "
        f"closure error was {abs(effects['overall_closure_error'].iloc[0]):.2g}. This is "
        "a descriptive estimand decomposition, not a causal effect decomposition.",
        "",
        f"Across constrained prespecified weights, median Spearman agreement with equal "
        f"weights was {node_weight['median']:.3f} for nodes and {pair_weight['median']:.3f} "
        "for pairs. This supports rank robustness within the examined weight region, but does "
        "not identify optimal weights because no frozen downstream criterion is available.",
        "",
        f"D4 showed modest association with both formal D5_report (Spearman rho = "
        f"{d4_d5_report['spearman']:.3f}, 7 d synchronized-block 95% CI "
        f"{d4_d5_report['spearman_ci_low']:.3f} to "
        f"{d4_d5_report['spearman_ci_high']:.3f}) and calculable D5_raw "
        f"(rho = {d4_d5_raw['spearman']:.3f}, 95% CI "
        f"{d4_d5_raw['spearman_ci_low']:.3f} to {d4_d5_raw['spearman_ci_high']:.3f}). "
        "The dual scope supports complementarity without asserting causal independence.",
        "",
        f"At pair level, hierarchical equal-component and seven-atom equal weighting "
        f"had Spearman rho = {pair_native['spearman']:.3f}, low-tail Jaccard = "
        f"{pair_native['low_tail_jaccard']:.3f}, and "
        f"{_pct(pair_native['decision_flip_rate_at_3'])} decision flips at Q < 3. "
        "Thus global ranking was broadly concordant but rare low-tail episode identity "
        "was not robust to flattening the hierarchy. This is a supplementary robustness "
        "comparison; the formal hierarchical model was not selected or changed from these data.",
        "",
        f"At the formal Q < {pair_native['formal_low_tail_threshold']:.2f} threshold, "
        f"the hierarchical and native-atom estimands identified "
        f"{int(pair_native['hierarchical_low_tail_count']):,} and "
        f"{int(pair_native['native_atom_low_tail_count']):,} low-tail pair-hours, "
        f"respectively. Their partition comprised {int(pair_native['both_count']):,} both, "
        f"{int(pair_native['hierarchical_only_count']):,} hierarchical-only, "
        f"{int(pair_native['native_atom_only_count']):,} native-atom-only and "
        f"{int(pair_native['neither_count']):,} neither hours. The corresponding episode "
        f"counts were {int(pair_native['hierarchical_event_count']):,} and "
        f"{int(pair_native['native_atom_event_count']):,}, with median durations of "
        f"{pair_native['hierarchical_median_episode_duration_h']:.1f} h and "
        f"{pair_native['native_atom_median_episode_duration_h']:.1f} h.",
        "",
        f"Across the prespecified Q < {pair_threshold_sweep['threshold'].min():.2f}-"
        f"{pair_threshold_sweep['threshold'].max():.2f} sensitivity range, low-tail "
        f"Jaccard ranged from {pair_threshold_sweep['low_tail_jaccard'].min():.3f} to "
        f"{pair_threshold_sweep['low_tail_jaccard'].max():.3f}, while decision-flip "
        f"fractions ranged from {pair_threshold_sweep['decision_flip_rate'].min():.3f} "
        f"to {pair_threshold_sweep['decision_flip_rate'].max():.3f}. The sweep tests "
        "whether the formal Q < 3 result is threshold-local; it is not used to choose "
        "a replacement threshold or weighting model.",
        "",
        "## Statistical interpretation",
        "",
        "The primary uncertainty analysis uses synchronized 7 d process-time blocks so that "
        "all sensors and pairs sharing an operating disturbance remain in the same resample. "
        "The 48 h and 14 d analyses are sensitivity bounds. Inferential intervals are only "
        "reported when at least six independent blocks are available.",
        "",
    ]
    for _, item in primary.iterrows():
        rows.append(
            f"- {item['scope']} / {item['estimand']}: {item['estimate']:.3f} "
            f"(95% CI {item['ci_low']:.3f}-{item['ci_high']:.3f}; "
            f"{int(item['n_evaluable_plant_hours']):,} evaluable plant-hours)."
        )
    rows.extend(
        [
            "",
            "## Claim boundary and release decision",
            "",
            "This release is suitable for retrospective scientific aggregation and manuscript "
            "analysis. It is not an automated deployment release. D5 hard Veto remains disabled "
            "because controlled perturbation Top-1 localization is 0.767, below the prespecified "
            "0.80 criterion. A-E grades remain disabled. The D1 export lacks a distinct validated "
            "hard-fault interface, so Strict eligibility remains a contract candidate rather than "
            "a finalized automatic release flag.",
            "",
            "The prospective 2026-04-14 to 2026-07-31 holdout and downstream fitness-for-use "
            "validation remain pending because the required frozen D1-D5 and endpoint bundles do "
            "not exist. Missing maintenance/metrological evidence is recorded as not available and "
            "is never assigned a neutral or low score.",
            "",
            "## Pending registry",
            "",
        ]
    )
    for _, item in pending.iterrows():
        rows.append(
            f"- `{item['validation_id']}`: **{item['status']}**. "
            f"{item['reason']} Consequence: {item['blocking_effect']}."
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(rows) + "\n", encoding="utf-8")


def write_directory_guide(path: Path) -> None:
    text = """# D1-D5 aggregation directory guide

This directory is a peer-level cross-dimensional integration layer. D5 is one
input dimension and is not the parent of D1-D4. No native D1-D5 scores are
overwritten.

## Configuration and code

- `configs/aggregation_v2.yaml`: frozen input hashes, estimands and validation rules.
- `src/dqr_aggregation/`: loading, aggregation, statistics, figures, reports and manifests.
- `scripts/run_dqr_aggregation.py`: complete deterministic release build.
- `scripts/verify_dqr_aggregation.py`: formula, freshness, manifest and figure verification.
- `tests/test_aggregation_v2.py`: synthetic and released-output contract tests.

## Generated outputs

- `outputs/aggregation_v2/data/`: dimension-long, node-hour, pair-hour, coverage,
  estimand-decomposition and pair-weighting sensitivity tables.
- `outputs/aggregation_v2/validation/`: statistical workbooks and machine-readable QA.
- `outputs/aggregation_v2/figures/`: 183 mm Nature-style PNG/PDF/SVG/TIFF files.
- `outputs/aggregation_v2/source_data/`: one source-data workbook per figure.
- `outputs/aggregation_v2/reports/`: scientific report, captions and this guide.
- `outputs/aggregation_v2/manifests/`: frozen run and publication manifests.

The run manifest records the scientific-generation commit for orientation, but
publication freshness is governed by exact canonical hashes of the current
configuration, every aggregation source module and all frozen D1-D5 inputs. The
publication-bundle commit or release tag is external metadata so that a manifest
never attempts to hash a commit that contains itself.

Figures 6 and 7 specified in the study plan are intentionally absent until the
prospective holdout and downstream endpoint bundles become available. Their
absence is a prespecified pending status, not a missing build artifact.
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_figure_captions(path: Path) -> None:
    text = """# Figure captions

**Figure 1 | Hierarchical quality, evidence completeness and safety-gate contract.**
Node quality combines D1, D2 and formally eligible D5 evidence, while pair quality
combines the two homologous nodes with native D4 evidence. D3 is a separate
non-compensatory gate. Quality and evidence completeness occupy separate axes.

**Figure 2 | Evidence availability and estimand stability across the study period.**
Monthly coverage and D5 L1-L3/OOD support migration are shown with Full and
availability-aware quality, evidence completeness, and the selection-only,
within-Full D5 compositional contribution and total observed estimand shifts. Full and availability-aware
series are distinct estimands and must not be pooled.

**Figure 3 | Pairwise construct complementarity across D1-D5.**
Pairwise-complete Spearman association and low-tail Jaccard overlap are estimated
without treating absence as a low score. D4-D5 intervals use synchronized 7 d
process-time block resampling; stratified estimates are descriptive when fewer
than six independent blocks are available.

**Figure 4 | Prespecified aggregation robustness.**
Equal arithmetic averaging is the primary method. Geometric, soft-minimum and
hard-minimum operators, constrained weight draws and leave-one-dimension-out
analyses are sensitivity checks and do not replace the primary score.

**Figure 5 | Multidimensional evidence around representative sensor and pair episodes.**
Hourly D1, D2, D5, node and native D4 evidence are shown around a median stable
benchmark window, two frozen D5 case-registry entries and an independently
registered D4 episode. Pale-gold shading denotes D3 Warn and grey hatching denotes
NotEvaluated. No panel is selected as the all-period maximum or minimum, and the
figure does not claim maintenance-confirmed fault truth.

**Extended Data Figure 1 | Pair hierarchical versus native-atom weighting.**
Complete-evidence pair-hours compare the formal equal-component hierarchy with
equal weighting of seven native atoms. Score concordance, low-tail hours,
exact overlap partitions, episode burden and a prespecified Q-threshold sweep are
sensitivity evidence, not model selection.

Figures 6 and 7 remain pending because prospective holdout scores and frozen
downstream endpoint bundles are unavailable.
"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
