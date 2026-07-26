# D1 final figure contract

## Scientific claim and evidence

Every figure must state one principal conclusion and expose the data needed to audit it. Figures V19 and V20 are the primary recovery evidence. `Recovered` occupancy must never be labeled as a recovery rate.

Manuscript-facing figures must report the locked current pipeline. Historical-version score overlays are software regression diagnostics, not scientific validation, and must remain outside the formal figure bundle unless a pre-specified ablation question and independent truth labels justify the comparison.

For Fig. 11, the claim is whether adding `DO_2_2` and/or a second PLS component improves `DO_2_4` prediction without weakening target-fault detection or increasing peer/common-process false alarms. The five panels must retain all forward-fold results, uncertainty, tail error, terminal hold-out, and controlled-injection evidence; a topology diagram alone is insufficient.

For Supplementary Fig. S1, the claim is which peer predictors are actually active in production for every scored channel. Panel (a) must be generated from the formal peer matrix in the current state, while panel (b) must list each target's effective predictors, peer count, retained PLS components, and limited-redundancy status. Rejected candidates belong in Fig. 11 evidence and must not appear as formal links in Fig. S1. The figure note and source workbook must distinguish the full DO_2_4 forward/hold-out/injection audit from the topology-constrained three-fold blocked-CV status of the remaining targets.

Fig. V12 is the current-result synthesis figure. Fig. V13 and Fig. V14 are current state-machine audits. Fig. V18 is the current grade/evidence/event-burden summary. The former Fig. V16 fixed-`k` regime plot is excluded from D1 because arbitrary cluster identifiers and occupancy fractions do not establish interpretable operating regimes; a future D5 version must pass cluster-number, stability, recurrence, and external-semantic validation.

## Geometry and typography

- Python/matplotlib backend only for this release.
- Final double-column width: 183 mm (`7.2 in`); maximum practical height: 170 mm.
- Arial for all visible text; editable text in SVG/PDF.
- Axis and tick linewidth: `0.8 pt`.
- Open axes: ticks point outward.
- Full four-spine frames: ticks point inward; top/right tick labels remain off unless scientifically needed.
- Every visible axis spine includes endpoint ticks.
- Multi-panel identifiers use bold lowercase `(a)`, `(b)`, `(c)` and appear outside the data region.

## Labels and legends

- Labels may not obscure data. Reposition them first.
- If overlap cannot be avoided, use a white annotation background with approximately `0.72` opacity and no border.
- Label only high-information points in crowded scatter plots; export all points in source data.
- Legends must not cover the evidence they describe. Reduce repeated wording before reducing font size.

## Color roles

- Blue: measured/final quantitative evidence.
- Green: Normal/direct recovery/positive outcome.
- Orange: Refractory.
- Amber: BaselinePending.
- Purple: SustainedAnomaly or contextual evidence.
- Pale purple: RecoveryCandidate.
- Red: adverse threshold, failed challenge, or severe evidence.
- Gray: reference/baseline/censoring.

Colors are restrained and role-based, with no decorative gradients. Information must remain interpretable without relying on color alone.

## Export and QA

Each formal figure requires:

- `.svg` with editable Arial text;
- `.pdf` vector output;
- `.png` at 600 dpi;
- `.tiff` at 600 dpi;
- a source-data workbook or table carrying `run_id` and algorithm version.

Run both `audit_d1_figures.py` and the nature skill `audit_figure_bundle.py`. QA contact sheets belong in `outputs/qa/figures/`, never in the formal figure directory.
