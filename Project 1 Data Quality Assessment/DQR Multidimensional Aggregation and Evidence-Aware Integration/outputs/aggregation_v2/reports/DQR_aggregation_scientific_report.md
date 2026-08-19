# D1-D5 hierarchical data-quality aggregation report

Run ID: `DQRAGG-V21-c625c1a2edc9`

## Confirmatory estimands

The release implements a hierarchical Quality-Evidence-Gate contract. D1, D2 and eligible D5 evidence form node-level quality; homologous left/right node quality and native D4_raw form pair-level quality. D3 is retained as an independent non-compensatory safety gate and is never averaged into either score. Evidence completeness is reported separately and is never multiplied by quality.

- `Q_node_full = mean(D1, D2, D5_report)` when all three formal scores exist.
- `Q_node_available = mean(D1, D2[, D5_report])`; D1 and D2 are mandatory.
- `Q_pair_full = mean(left Q_node_full, right Q_node_full, D4_raw)`.
- `Q_pair_available = mean(left Q_node_available, right Q_node_available, D4_raw)`.
- `E_node` and `E_pair` quantify evidence coverage, not data quality.

## Current results

The node table contains 86,016 sensor-hours: 39,606 Full, 46,004 Basic, 406 Limited and 0 Insufficient. The pair table contains 42,847 native pair-hours: 19,774 Full, 22,583 Basic and 490 Limited.

The complete-case identity check passed for both levels (maximum absolute difference 0). Under equal arithmetic aggregation, the complete-evidence low-tail rate was 0.4% for nodes and 1.2% for pairs.

Sensor-hour pooled means were 4.252 (node Full), 4.422 (node availability-aware), 3.905 (pair Full) and 4.012 (pair availability-aware). These are not the plant-hour aggregated means reported below, which first summarize all objects within each plant-hour and then average over time.

The Full and Basic node subsets are not exchangeable: their overall standardized mean difference was -0.86 and Wasserstein distance was 0.32. Full is therefore the complete-evidence estimand; availability-aware Basic extends coverage but must be displayed separately.

The sensor-hour estimand decomposition separated a selection-only shift of 0.069 (95% block CI 0.030 to 0.113) from a within-Full D5 composition effect of -0.387 (-0.447 to -0.329). Their sum equals the total observed estimand shift of -0.318; absolute closure error was 0. This is a descriptive estimand decomposition, not a causal effect decomposition.

Across constrained prespecified weights, median Spearman agreement with equal weights was 0.992 for nodes and 0.985 for pairs. This supports rank robustness within the examined weight region, but does not identify optimal weights because no frozen downstream criterion is available.

D4 showed modest association with both formal D5_report (Spearman rho = 0.119, 7 d synchronized-block 95% CI 0.046 to 0.198) and calculable D5_raw (rho = 0.171, 95% CI 0.092 to 0.246). The dual scope supports complementarity without asserting causal independence.

At pair level, hierarchical equal-component and seven-atom equal weighting had Spearman rho = 0.892, low-tail Jaccard = 0.048, and 1.1% decision flips at Q < 3. Thus global ranking was broadly concordant but rare low-tail episode identity was not robust to flattening the hierarchy. This is a supplementary robustness comparison; the formal hierarchical model was not selected or changed from these data.

## Statistical interpretation

The primary uncertainty analysis uses synchronized 7 d process-time blocks so that all sensors and pairs sharing an operating disturbance remain in the same resample. The 48 h and 14 d analyses are sensitivity bounds. Inferential intervals are only reported when at least six independent blocks are available.

- node / full: 4.290 (95% CI 4.216-4.360; 2,829 evaluable plant-hours).
- node / availability_aware: 4.475 (95% CI 4.419-4.529; 6,115 evaluable plant-hours).
- pair / full: 3.917 (95% CI 3.856-3.975; 2,825 evaluable plant-hours).
- pair / availability_aware: 4.033 (95% CI 3.987-4.079; 6,062 evaluable plant-hours).

## Claim boundary and release decision

This release is suitable for retrospective scientific aggregation and manuscript analysis. It is not an automated deployment release. D5 hard Veto remains disabled because controlled perturbation Top-1 localization is 0.767, below the prespecified 0.80 criterion. A-E grades remain disabled. The D1 export lacks a distinct validated hard-fault interface, so Strict eligibility remains a contract candidate rather than a finalized automatic release flag.

The prospective 2026-04-14 to 2026-07-31 holdout and downstream fitness-for-use validation remain pending because the required frozen D1-D5 and endpoint bundles do not exist. Missing maintenance/metrological evidence is recorded as not available and is never assigned a neutral or low score.

## Pending registry

- `V3-controlled-composite-discrimination`: **pending_not_executed**. no unified frozen event-truth matrix across native node and pair evidence Consequence: candidate aggregators remain sensitivity-only.
- `V7-prospective-temporal-holdout`: **pending_not_executed_inputs_not_scored_by_frozen_D1_D5**. 2026-04-14 to 2026-07-31 has not been scored by the frozen D1-D5 stack Consequence: no prospective effectiveness or A-E cutpoint claim.
- `V8-downstream-fitness-for-use`: **pending_not_executed**. no frozen SUMO, EnKF or prediction endpoint bundle is available in this release Consequence: no optimized weights or criterion-referenced grades.
- `D1-release-hard-fault-interface`: **pending_interface**. D1 release exports score and legacy score>=3 tag, not a distinct validated hard-fault field Consequence: Strict eligibility is a contract candidate, not an automated final release.
- `measurement-assurance`: **not_available_not_scored**. maintenance and metrological records are not available Consequence: excluded rather than assigned a neutral or low value.
