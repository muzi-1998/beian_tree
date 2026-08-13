# D4 v1.5 methodology review and decision record

## Expert conclusion

The four proposed gaps are scientifically valid and materially relevant to a
high-impact-journal claim. The executable parts have been implemented without
changing the independent meaning of `D4_raw`. The resulting package is suitable
for retrospective scientific aggregation and manuscript drafting, but it is
not yet a field-validated or genuinely untouched terminal-validation package.

## Decisions and implementation

### 1. Incremental value of W1 and KS: accepted with a constrained claim

`Full`, `W1-only`, and `KS-only` were compared on paired internal-validation
windows under location, scale, tail, and mixture challenges. Confidence
intervals use window-cluster bootstrap resampling. Equal common-mode change is
the negative control; unequal same-direction and opposite-direction changes are
positive asymmetry stress tests and are excluded from the common-mode FAR.

The results do not support a claim that the combined estimator is universally
superior. W1 and KS have mechanism-specific strengths. The pre-specified
0.60/0.40 combination is retained as a frozen compromise because it protects
tail sensitivity and common-mode specificity, not because it maximizes the
internal-validation metric. No terminal-period tuning was performed.

### 2. Calibration leakage: accepted, with an explicit upstream limitation

D4 mapping parameters are now fit only on 2025-08-01 to 2026-01-24 development
windows. 2026-01-25 to 2026-01-31 is embargoed, and 2026-02-01 to 2026-04-13 is
used for internal chronological validation. Mapping IDs bind the fit interval,
common-support policy, and distribution-component version.

This does not create a genuinely untouched terminal test retrospectively. The
1.1/D1 upstream transforms had previously been developed using the study
period. A future frozen-data period is therefore still required for terminal
confirmation. The manuscript must use `internal chronological validation`, not
`external` or `untouched terminal validation`, for the current result.

### 3. DO14 event duration: accepted

Episodes are re-extracted inside every synchronous moving-time-block bootstrap
replicate. The primary block length is seven days, with 48-hour and 14-day
sensitivity analyses. The current result supports the descriptive statement
that DO14 pair-asymmetry episodes are fewer but longer. It does not establish
that either DO14 sensor is faulty, because D4 identifies pair asymmetry rather
than causal ownership.

### 4. Synchronous common support: accepted as a production requirement

W1, KS, IQR, and trend metrics now use the same finite timestamps. The output
records common sample count, common hourly support, asymmetric missingness, and
support Jaccard. Production evaluability requires at least 80% common minute and
hour support. This removes an avoidable construct error in which two sensors
could be compared on different temporal samples.

## Additional executed safeguards

- The v1.4 canonical package is preserved under `legacy/2026-07-26-v1.4-canonical`.
- The v1.4-v1.5 method sensitivity is separated from older three-version work.
- D4-D5 readiness continues to finalize from `D4_raw`; D1 remains interpretive.
- A SHA-bound composite refresh reports Full and Basic coverage separately.
- Six main and five supplementary figures have source-data workbooks and Nature
  preflight QA.

## Pending or deliberately not executed

- **Future untouched terminal validation:** requires newly accrued frozen data.
- **Field truth and maintenance adjudication:** requires SCADA/maintenance or
  expert-reviewed event records.
- **External-plant validation:** requires an independent plant dataset.
- **Production ORP shrinkage:** remains sensitivity-only because estimator
  selection and future-period validation are incomplete.
- **Sub-hour lag as a primary claim:** remains supplementary; hourly resolution
  is the defensible production scale.
- **Re-optimizing W1/KS weights:** not performed because selecting weights on the
  internal validation period would recreate the leakage problem.
- **Causal attribution of DO14 episodes:** not claimed without D5 action-grade
  evidence and field records.

## Publication readiness

The D4 dimension is ready for retrospective D1-D5 aggregation and manuscript
method/results drafting with explicit limitations. Final deployment and the
strongest confirmatory claims remain conditional on future untouched data and
field adjudication.
