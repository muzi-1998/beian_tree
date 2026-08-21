# D5 support-migration audit

## Scope and frozen boundary

- Audit ID: `D5-SUPPORT-MIGRATION-V1`
- Source run: `D5-LOCAL-20260727T034533Z`
- Reference endpoint: `2026-01-27T04:30:00`
- Post-reference analysis starts after the 7 d embargo: `2026-02-03T04:30:00`
- Authoritative D5 scores modified: **No**

## Confirmatory result

The decline in D5 report eligibility after January 2026 is **reference-horizon dominated**, not evidence of deteriorating sensor quality. R2 occupies 100.0% of the post-embargo period. All 14 sensor-by-R2 templates are L1 because family effective support is 29 calendar days, below the prespecified L2 threshold of 40 days.

The competing explanations were not supported:

- distinct-month support is 2 months and passes the L2 contract;
- node effective support is 29 days and passes the 20-day threshold;
- node reconstruction coverage is 99.95%, far above the 0.60 threshold;
- stability, blocked holdouts and FAR do not participate in L1-to-L2 admission and therefore cannot explain the L1 migration.

Current post-embargo report coverage is 0.00%. A diagnostic counterfactual that repairs only family effective-day support increases coverage to 92.06% (+92.06 percentage points), identical to the all-L2-support ceiling. The residual 7.94% remains unavailable because OOD or incomplete evidence is preserved.

## Scientific interpretation

The frozen K=4 context model partitions the study trajectory into temporally ordered operating regimes. R2 first becomes dominant shortly before the reference cutoff and reaches 100% occupancy in February-April. Consequently, R2 has only 29 complete reference calendar days even though its node reconstruction evidence is almost complete. D5 correctly abstains rather than extrapolating an under-mature family template.

This is an evidence-availability shift, not a low D5 score. Manuscript language should therefore state that the late-period estimand is limited by frozen-template maturity. Availability-aware and complete-evidence composites must remain separated.

## Recommended D5 actions

1. Keep the authoritative v2.4 scores and L2 thresholds unchanged.
2. Publish the support-migration audit as Supplementary/Extended Data evidence and carry `support_level`, `family_n_effective`, `reference_end`, and D5 availability into DQR aggregation metadata.
3. For a future prospective release, establish a rolling but versioned template lifecycle: a candidate R2 template may be promoted only after 40 effective days and at least 2 months, followed by a frozen prospective validation period.
4. Do not merge regimes solely to recover coverage. A K=3/K=5 refit is a new model-selection exercise and requires outer-fold discrimination, localization, OOD, and interpretability checks.
5. Keep L2-to-L3 stability/FAR limitations separate; they constrain action-grade deployment but do not cause the observed report-coverage loss.

## Publication boundary

The audit is post hoc but uses prespecified support thresholds and frozen artifacts. Counterfactuals are diagnostic upper bounds, not alternative production scores. No post-reference observations were used to update the authoritative templates.
