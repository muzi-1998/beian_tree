# D4 publication-figure expert review

## Scope and locked scientific boundary

This revision implements the 12 August 2026 expert figure review without
re-estimating the production D4 score. The plotted core remains the current
hash-bound D4 release: 42,847 pair-windows across seven homologous pairs.
`D4_raw` is the independent numeric dimension; D2 controls evaluability, while
D1 and D5 provide interpretation or attribution governance and cannot rewrite
the D4 value.

## Main-figure decisions

1. `FigD4_1_scientific_construct` defines paired inputs, the four independent
   evidence families, public calibration, non-compensatory aggregation, and the
   D1/D2/D4/D5 claim boundary.
2. `FigD4_2_pair_mechanism_profile` reports valid-window component medians with
   W-SUN block-bootstrap 95% intervals, D4 distribution, low-tail burden, and
   the ORP fallback limitation.
3. `FigD4_3_burden_coverage_calibration` jointly displays weekly low-score
   fraction, the matching evaluability denominator, and regime-level
   calibration support. Gray cells are unevaluable, not high-quality windows.
4. `FigD4_4_formal_episode_cases` uses only registered events from
   `D4_event_windows.xlsx`; the DO14 and ORP13 cases remain detection examples
   with causal attribution explicitly pending.
5. `FigD4_5_mechanism_specificity` separates ROC/PR performance, equal common
   negative control, unequal/opposite positive controls, and pair-level
   heterogeneity. Spike remains a D1-owned secondary challenge.
6. `FigD4_6_ablation_and_lag_resolution` replaces pooled-only interpretation
   with mechanism-specific paired-window cluster-bootstrap deltas and preserves
   the negative sub-hour lag result.

## Supplementary decisions

`FigS1` retains all-pair trajectories and formal event shading; `FigS2` reports
trend concordance and robust slope differences; `FigS3` verifies that finalized
D4 equals `D4_raw` and that D1/D5 context does not numerically alter the score.
The superseded eight-figure bundle is removed by the reproducible figure entry
point rather than retained beside current results.

## Statistical and visual contract

- Main denominator: `usable_for_D4`; calibration and integration panels state
  their own denominators.
- Temporal aggregation: W-SUN weeks.
- Intervals: week-block bootstrap for field summaries and paired `window_id`
  cluster bootstrap for ablation deltas.
- Exports: editable SVG/PDF and 600 dpi PNG/LZW-TIFF, Arial-first font stack,
  Okabe-Ito color anchors, inward ticks for full frames and outward ticks for
  open axes.
- Traceability: one Excel source workbook per figure plus a SHA-256 figure audit
  manifest in `outputs/qa/d4_figure_bundle_audit.json`.

## Claims intentionally not upgraded

The package does not claim external field accuracy, sensor-level causal truth,
validated ORP regime coverage, or monotonic sub-hour lag sensitivity. Those
claims require adjudicated maintenance/process records, stronger ORP benchmark
support, or a higher-frequency validated change-point design.
