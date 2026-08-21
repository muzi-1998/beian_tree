# DQR v2.3 expert review and implementation decision

## Overall decision

The proposal is scientifically coherent and addresses the principal remaining risk: changes in evidence composition must not be interpreted as temporal changes in data quality. The accepted P0 changes were implemented without changing any frozen D1-D5 formal score.

## Executed

- Added fixed node and pair Core estimands alongside Full and availability-aware estimands.
- Locked Quality, Evidence and Gate as separate non-multiplicative axes; D3 remains fail-closed and non-compensatory.
- Bound D5 support-migration v1.1 into the frozen input registry; L1 remains diagnostic-only limited evidence and is never converted into low quality.
- Added D4 exact/variable-fallback/global-fallback/insufficient metadata to every pair-hour and completed a descriptive mapping-support migration audit.
- Added phase_role, reference_status and version_hash to every dimension-long row, plus a phase/evidence summary and machine-readable estimand registry.
- Retained v2.2 outputs and created a separate v2.3 release directory, source-data bundle, figures, reports, tests and SHA-256 manifests.
- Kept A-E grades, D5 hard Veto and optimized weights disabled.

## Main numerical implications

- Sensor-hour pooled node means: Core 4.601, Full 4.252, availability-aware 4.422.
- Sensor-hour pooled pair means: Core 4.132, Full 3.905, availability-aware 4.012.
- These values are intentionally different estimands; their differences are not model disagreement and must not be collapsed into one trend.
- D4 mapping support comprised 64.1% exact, 35.8% variable fallback, 0.0% global fallback and 0.1% insufficient pair-hours.
- ORP variable-fallback validation rows had a D4<3 rate of 67.0%. Because support class is structurally coupled to regime, this is descriptive and cannot be interpreted as a causal fallback penalty.

## Accepted with modification

- Native D1-D3 files were not rewritten merely to add phase labels. The harmonized fields are added at the integration interface, preserving upstream frozen hashes; native exports should change only in a new versioned upstream release.
- D4 fallback remains formally scoreable metadata in this release. No global fallback was observed, and exact/fallback strata are regime-confounded. Any future exclusion from Full requires a prospectively frozen rule and new test data.
- D5 post-embargo rows are labelled for aggregation-time interpretation only; this does not create a new independent-validation claim for the D5 model.
- The Nature static preflight warning on D4 `.dropna()` is non-substantive: these calls collapse non-null metadata values; missing-regime rows are explicitly retained as `insufficient`, and all input/evaluable counts are exported.

## Pending and not executed

- D1 development-only frozen K=4 context shadow and the dependent D4 regime-shadow comparison: require a separately preregistered model artifact and paired sensitivity run.
- Independent D1 hard-fault interface: cannot be reconstructed from a D1_total threshold and requires controlled challenge or reviewed event truth.
- D5 template promotion and bridge: requires future independent support, frozen validation and prospective activation; historical L1 will not be backfilled.
- Prospective post-2026-04-13 scoring, downstream fitness-for-use, maintenance/metrological truth, cross-plant validation, learned weights and A-E cutpoints: required data are unavailable.

## Publication conclusion

DQR v2.3 is suitable for retrospective manuscript analysis as a hierarchical, evidence-aware and non-compensatory aggregation framework. Core is the longitudinal estimand, Full is the complete-evidence scientific estimand, and availability-aware is an operational extension. The release is not a deployment-grade automated grading or hard-Veto system.
