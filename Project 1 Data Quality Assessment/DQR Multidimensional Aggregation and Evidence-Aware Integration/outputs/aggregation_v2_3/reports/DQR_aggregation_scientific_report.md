# D1-D5 hierarchical data-quality aggregation report

Run ID: `DQRAGG-V23-e4486a5f8f5d`

## Confirmatory estimands

The release implements a hierarchical Quality-Evidence-Gate contract. D1, D2 and eligible D5 evidence form node-level quality; homologous left/right node quality and native D4_raw form pair-level quality. D3 is retained as an independent non-compensatory safety gate and is never averaged into either score. Evidence completeness is reported separately and is never multiplied by quality.

- `Q_node_full = mean(D1, D2, D5_report)` when all three formal scores exist.
- `Q_node_core12 = mean(D1, D2)` is the fixed-composition longitudinal estimand.
- `Q_node_available = mean(D1, D2[, D5_report])`; D1 and D2 are mandatory.
- `Q_pair_full = mean(left Q_node_full, right Q_node_full, D4_raw)`.
- `Q_pair_core = mean(left Q_node_core12, right Q_node_core12, D4_raw)`.
- `Q_pair_available = mean(left Q_node_available, right Q_node_available, D4_raw)`.
- `E_node` and `E_pair` quantify evidence coverage, not data quality.

## Current results

The node table contains 86,016 sensor-hours: 39,606 Full, 46,004 Basic, 406 Limited and 0 Insufficient. The pair table contains 42,847 native pair-hours: 19,774 Full, 22,583 Basic and 490 Limited.

The complete-case identity check passed for both levels (maximum absolute difference 0). Under equal arithmetic aggregation, the complete-evidence low-tail rate was 0.4% for nodes and 1.2% for pairs.

Sensor-hour pooled means were 4.252 (node Full), 4.601 (node fixed Core), 4.422 (node availability-aware), 3.905 (pair Full) and 4.132 (pair fixed Core) and 4.012 (pair availability-aware). These are not the plant-hour aggregated means reported below, which first summarize all objects within each plant-hour and then average over time.

The Full and Basic node subsets are not exchangeable: their overall standardized mean difference was -0.86 and Wasserstein distance was 0.32. Full is therefore the complete-evidence estimand; availability-aware Basic extends coverage but must be displayed separately.

D4 pair-hours used exact variable-regime mapping for 64.1%, variable-level fallback for 35.8%, and global fallback for 0.0%. Mapping support is evidence metadata and does not numerically penalize D4_raw. Any future exclusion rule must be prospectively frozen and independently validated.

The sensor-hour estimand decomposition separated a selection-only shift of 0.069 (95% block CI 0.030 to 0.113) from a within-Full D5 compositional contribution of -0.387 (-0.447 to -0.329). Their sum equals the total observed estimand shift of -0.318; absolute closure error was 0. This is a descriptive estimand decomposition, not a causal effect decomposition.

Across constrained prespecified weights, median Spearman agreement with equal weights was 0.992 for nodes and 0.985 for pairs. This supports rank robustness within the examined weight region, but does not identify optimal weights because no frozen downstream criterion is available.

D4 showed modest association with both formal D5_report (Spearman rho = 0.119, 7 d synchronized-block 95% CI 0.046 to 0.198) and calculable D5_raw (rho = 0.171, 95% CI 0.092 to 0.246). The dual scope supports complementarity without asserting causal independence.

At pair level, hierarchical equal-component and seven-atom equal weighting had Spearman rho = 0.892, low-tail Jaccard = 0.048, and 1.1% decision flips at Q < 3. Thus global ranking was broadly concordant but rare low-tail episode identity was not robust to flattening the hierarchy. This is a supplementary robustness comparison; the formal hierarchical model was not selected or changed from these data.

At the formal Q < 3.00 threshold, the hierarchical and native-atom estimands identified 229 and 11 low-tail pair-hours, respectively. Their partition comprised 11 both, 218 hierarchical-only, 0 native-atom-only and 19,545 neither hours. The corresponding episode counts were 99 and 6, with median durations of 2.0 h and 1.5 h.

Across the prespecified Q < 2.50-3.50 sensitivity range, low-tail Jaccard ranged from 0.000 to 0.235, while decision-flip fractions ranged from 0.000 to 0.110. The sweep tests whether the formal Q < 3 result is threshold-local; it is not used to choose a replacement threshold or weighting model.

## Statistical interpretation

The primary uncertainty analysis uses synchronized 7 d process-time blocks so that all sensors and pairs sharing an operating disturbance remain in the same resample. The 48 h and 14 d analyses are sensitivity bounds. Inferential intervals are only reported when at least six independent blocks are available.

- node / full: 4.290 (95% CI 4.216-4.360; 2,829 evaluable plant-hours).
- node / core_fixed: 4.658 (95% CI 4.631-4.678; 6,115 evaluable plant-hours).
- node / availability_aware: 4.475 (95% CI 4.419-4.534; 6,115 evaluable plant-hours).
- pair / full: 3.917 (95% CI 3.856-3.974; 2,825 evaluable plant-hours).
- pair / core_fixed: 4.160 (95% CI 4.127-4.192; 6,062 evaluable plant-hours).
- pair / availability_aware: 4.033 (95% CI 3.986-4.079; 6,062 evaluable plant-hours).

## Claim boundary and release decision

This release is suitable for retrospective scientific aggregation and manuscript analysis. It is not an automated deployment release. D5 hard Veto remains disabled because controlled perturbation Top-1 localization is 0.767, below the prespecified 0.80 criterion. A-E grades remain disabled. The D1 export lacks a distinct validated hard-fault interface, so Strict eligibility remains a contract candidate rather than a finalized automatic release flag.

The prospective 2026-04-14 to 2026-07-31 holdout and downstream fitness-for-use validation remain pending because the required frozen D1-D5 and endpoint bundles do not exist. Missing maintenance/metrological evidence is recorded as not available and is never assigned a neutral or low score.

Longitudinal interpretation is restricted to fixed-composition Core estimands. Full remains the complete-evidence scientific estimand, while availability-aware scores are operational summaries and must not be compared across dimension masks. D5 L1 denotes limited evidence support, not low data quality, and historical L1 hours are never backfilled after a future template upgrade.

## Pending registry

- `V3-controlled-composite-discrimination`: **pending_not_executed**. no unified frozen event-truth matrix across native node and pair evidence Consequence: candidate aggregators remain sensitivity-only.
- `V7-prospective-temporal-holdout`: **pending_not_executed_inputs_not_scored_by_frozen_D1_D5**. 2026-04-14 to 2026-07-31 has not been scored by the frozen D1-D5 stack Consequence: no prospective effectiveness or A-E cutpoint claim.
- `V8-downstream-fitness-for-use`: **pending_not_executed**. no frozen SUMO, EnKF or prediction endpoint bundle is available in this release Consequence: no optimized weights or criterion-referenced grades.
- `D1-release-hard-fault-interface`: **pending_interface**. D1 release exports score and legacy score>=3 tag, not a distinct validated hard-fault field Consequence: Strict eligibility is a contract candidate, not an automated final release.
- `measurement-assurance`: **not_available_not_scored**. maintenance and metrological records are not available Consequence: excluded rather than assigned a neutral or low value.
- `D1-development-only-regime-context-shadow`: **pending_preregistered_shadow**. the downstream K=4 context is retrospective and requires a development-only frozen comparison Consequence: no independent-validation claim is made for the retrospective context.
- `D4-development-only-regime-shadow`: **pending_after_D1_shadow**. D4 sensitivity requires the frozen D1 context artifact before a paired shadow rerun Consequence: current D4 remains retrospective with explicit context-hindsight limitation.
- `D5-prospective-template-lifecycle`: **pending_future_support_and_bridge**. candidate maturity requires new independent support, frozen validation and a dual-score bridge Consequence: historical L1 is not backfilled and no new template version is activated.
