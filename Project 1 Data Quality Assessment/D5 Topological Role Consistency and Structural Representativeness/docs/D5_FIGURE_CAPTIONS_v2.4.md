# D5 Figure Captions v2.4

## Figure D5-1. Author-confirmed topology, applicability and scientific workflow

(a) Author-confirmed longitudinal and parallel-peer topology for two process lines. Solid arrows encode within-line ordinal adjacency and dashed links encode seven homologous cross-line peers; coordinates are schematic rather than surveyed distances. (b) D5 applicability states stratified by analyte. (c) Scientific workflow from context assignment through regime-conditioned role templates and four structural components to the report-or-abstain interface. Governance and deployment approval remain separate from the scoring workflow.

## Figure D5-2. Spatiotemporal score, eligibility and support structure

(a) Daily lower-quartile `D5_raw` for 14 ordered DO/ORP positions, with report-eligibility and out-of-template ribbons. Gray cells denote days with less than 50% report-eligible coverage; A-C mark the lowest-score candidate windows used for case review. The value 3 is an analysis reference, not a validated fault threshold. (b) Sensor-level median and interquartile range; point area represents the fraction below the analysis reference. (c) Monthly raw calculability, report eligibility, out-of-template rate and L1 support. Missing or weakly supported evidence is displayed as abstention, not as low quality.

## Figure D5-3. Case-level structural evidence and attribution

(a) Raw target, homologous parallel peer and same-line neighbor around an unlabeled low-score candidate, with the regime-specific target template and OOD/regime strip. (b) Four structural components and `D5_raw`; the dashed line at 3 is an analysis reference. (c) Normalized diagnostic contributions at the case center and a topology residual map showing node residuals and edge inconsistency. Contributions are diagnostic leave-one-out quantities, not Shapley values. This case is evidence for review and is not a confirmed sensor fault.

## Figure D5-4. Frozen-template validation and track invariance

(a) Criterion margins for controlled same-line position swaps, negative controls and regime chatter; zero indicates the prespecified release boundary and positive values pass. Error bars show 95% intervals where estimable. (b) Controlled-perturbation Top-1 localization by D5-relevant scenario with Wilson 95% intervals. (c) False alarm rates and empirical 95% ranges for orthogonality controls. (d) Local-Sensitivity invariance criterion margins. These are controlled observed-window challenges, not field fault accuracy.

## Figure D5-5. Hierarchical admission and dimension-independent integration

(a) Family-level and final node-level support counts, showing that shared sample support does not automatically upgrade every node. (b) Node bootstrap stability and blocked-temporal holdout FAR for family-L3 candidates; dashed lines show prespecified node thresholds. (c) Coverage of the sensor-hour report interface and pair-hour gate states, including attribution Guard and sensor Veto. (d) D4 independence audit comparing the final D4 score with its sole numeric source, `D4_raw`; the identity line represents zero cross-dimensional adjustment.

## Figure D5-6. Validation, localization and evidence coverage boundary

(a) Estimate-minus-criterion margins from six future-month complete refits of the full model and three prespecified structural ablations. AUROC is compared with 0.90; AUPRC and Top-1 are compared with 0.80. (b) Top-1 localization with fold-cluster 95% intervals and the distribution of topological hop error for three controlled perturbations. (c) Monthly raw calculability, report eligibility, OOD and L1 support. (d) Top-1-only risk-coverage analysis with retained block counts and cluster intervals. Confidence is not calibrated as a selective-localization probability, and these results are not field fault-accuracy estimates.

## Figure D5-7. D4-D5 complementarity across report and raw estimands

(a) Joint density of D4 raw and D5 pair report scores. Overall report-score and raw-calculable Spearman correlations and the descriptive covariate-adjusted rank marker are annotated; the latter is not a causal estimand. (b,c) Spearman rho by analyte, pair, regime and month. The shaded band denotes weak association, |rho| < 0.30. Filled symbols and intervals require at least six independent non-overlapping 7-d process-time blocks; open symbols retain descriptive point estimates based on at least two blocks. (d) Exact low-tail overlap at the prespecified analysis reference of 3. Pair-composite leave-one-dimension sensitivity remains in source data. Values are bound to D4 run `D4V151_20260813_083347`, calibration `D4CAL-V151-66fe1bb6b7d3` and the recorded main-score SHA-256.

## Figure D5-8. Dimension-availability sensitivity of the prototype WW-DQS

(a) Monthly medians for the availability-aware prototype, with open markers showing the same estimator restricted to matched complete-evidence sensor-hours, and the fixed-dimension complete-evidence estimator. (b) Availability-aware and complete-evidence coverage together with D5 availability. (c) Effective numeric dimension count. (d) Descriptive monthly median shift between availability-aware and fixed-dimension estimands. The current calculation covers the D1/D2/D5 node prototype and must be repeated under the final five-dimension contract.

## Figure D5-9. Target-influence and support-threshold robustness

(a) Whole-period and post-reference leave-one-target-out regime disagreement together with OOD-rate response to controlled target offsets. (b) Final-L3 template count across the full prespecified 0.70, 0.80 and 0.90 reference-fraction sensitivity grid and support thresholds. Production thresholds and the 0.70 reference fraction remain frozen. These analyses diagnose model robustness and do not change production templates or thresholds.

## Supplementary Figure D5-S1. Monthly regime occupancy and report-eligibility migration

(a) Monthly occupancy of the frozen K=4 operating regimes and OOD state. The vertical line marks the frozen 0.70 reference endpoint on 27 January 2026. (b) Monthly D5 report eligibility, L1 limited-support occupancy and OOD occupancy. R2 becomes dominant near the reference boundary and occupies all post-embargo evaluable time. Rates are sensor-hour proportions; the figure diagnoses evidence availability rather than sensor quality.

## Supplementary Figure D5-S2. Sensor-by-regime template maturity

Support level for each of the 56 frozen sensor-by-regime templates. Every R2 node remains L1, whereas the other regimes contain L2 or L3 templates. L1 denotes limited template support and is an abstention state, not a low D5 score.

## Supplementary Figure D5-S3. Prespecified L1 admission blockers

(a) Pass/fail matrix for the five prespecified L1-to-L2 support requirements across all 14 R2 sensor templates. Family effective days are the only failed requirement. (b) Support-attributable post-reference sensor-hours by analyte; OOD and not-evaluable hours are excluded from these bars and reported separately in source data.

## Supplementary Figure D5-S4. Diagnostic counterfactual coverage recovery

Post-embargo report coverage under one-at-a-time support repairs. Repairing family effective-day support yields the same 92.06% ceiling as repairing all L2 support requirements; node days, month counts and node reconstruction coverage have no effect. Counterfactuals retain OOD and incomplete-evidence exclusions and do not alter the frozen production model.
