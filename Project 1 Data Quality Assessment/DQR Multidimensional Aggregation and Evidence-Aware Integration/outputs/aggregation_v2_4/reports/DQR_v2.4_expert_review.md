# DQR v2.4 expert review and implementation decision

## Overall decision

This revision separates D3/D4 reference qualification from other dimensions' numeric scores. D1, D2 and D5 formal scores remain unchanged; D3/D4 have new versioned results. Evidence composition must not be interpreted as temporal changes in data quality.

## Executed

- Added fixed node and pair Core estimands alongside Full and availability-aware estimands.
- Locked Quality, Evidence and Gate as separate non-multiplicative axes; D3 remains fail-closed and non-compensatory.
- Bound D5 support-migration v1.1 into the frozen input registry; L1 remains diagnostic-only limited evidence and is never converted into low quality.
- Added D4 exact/variable-fallback/global-fallback/insufficient metadata to every pair-hour and completed a descriptive mapping-support migration audit.
- Added phase_role, reference_status and version_hash to every dimension-long row, plus a phase/evidence summary and machine-readable estimand registry.
- Retained v2.2/v2.3 outputs and created a separate v2.4 release directory, source-data bundle, figures, reports, tests and SHA-256 manifests.
- Kept A-E grades, D5 hard Veto and optimized weights disabled.

## Main numerical implications

- Sensor-hour pooled node means: Core 4.601, Full 4.252, availability-aware 4.422.
- Sensor-hour pooled pair means: Core 4.226, Full 3.987, availability-aware 4.106.
- These values are intentionally different estimands; their differences are not model disagreement and must not be collapsed into one trend.
- D4 mapping support comprised 85.7% exact, 12.7% variable fallback, 0.0% global fallback and 1.5% insufficient pair-hours.
- ORP variable-fallback validation rows had a D4<3 rate of nan%. Because support class is structurally coupled to regime, this is descriptive and cannot be interpreted as a causal fallback penalty.

## Accepted with modification

- D3/D4 input hashes explicitly bind the neutral-reference releases. D1/D2/D5 numeric hashes and the D5 support-audit manifest remain frozen. Phase labels are integration metadata.
- D4 fallback remains formally scoreable metadata in this release. No global fallback was observed, and exact/fallback strata are regime-confounded. Any future exclusion from Full requires a prospectively frozen rule and new test data.
- D5 post-embargo rows are labelled for aggregation-time interpretation only; this does not create a new independent-validation claim for the D5 model.
- The Nature static preflight warning on D4 `.dropna()` is non-substantive: these calls collapse non-null metadata values; missing-regime rows are explicitly retained as `insufficient`, and all input/evaluable counts are exported.

## Pending and not executed

- Shared D4 K=4 process context is now fitted only before its development cutoff. D5 retains its own frozen posterior/OOD/hysteresis model; equally named regimes are not presumed equivalent.
- Independent D1 hard-fault interface: cannot be reconstructed from a D1_total threshold and requires controlled challenge or reviewed event truth.
- D5 template promotion and bridge: requires future independent support, frozen validation and prospective activation; historical L1 will not be backfilled.
- The 108-day data have already been inspected; revised temporal re-evaluation is separate and cannot supply a new blind-test claim. Downstream fitness-for-use, maintenance/metrological truth, cross-plant validation, learned weights and A-E cutpoints remain unresolved.

## Publication conclusion

DQR v2.4 supports retrospective manuscript analysis with computational/scoring dependency separation, not statistical independence. Core is the longitudinal estimand, Full is the complete-evidence scientific estimand, and availability-aware is an operational extension. The release is not a deployment-grade automated grading or hard-Veto system.
