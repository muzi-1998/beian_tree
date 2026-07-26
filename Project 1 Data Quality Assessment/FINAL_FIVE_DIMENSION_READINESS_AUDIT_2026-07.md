# Final D1-D5 readiness audit

Audit date: 2026-07-26

## Executive decision

The canonical high-frequency dynamic data-quality dimensions are:

| Dimension | Canonical construct | Legacy lineage | Authoritative score |
|---|---|---|---|
| D1 | Sensor health | D1 | `D1_total` (`D1_total_hourly` release sheet) |
| D2 | Temporal continuity and information availability | D2 | `D2_total` |
| D3 | Physical rationality and rate constraints | former D4 | `D3_total` |
| D4 | Parallel-redundancy temporal consistency | former D6 | `D4_raw` |
| D5 | Topological role consistency and structural representativeness | former D7 | `D5_report_score` |

All five dimensions are current, reproducible and numerically separated at the
dimension-score layer. They may enter a locked retrospective aggregation and
calibration study. The present evidence does not yet support calling the
composite an externally validated, deployment-ready WW-DQS index.

This distinction is important:

- **Subscore aggregation development: admitted.**
- **Final manuscript composite after prespecified calibration: conditionally admitted.**
- **Automated operational deployment: not admitted.**

## Freshness evidence

| Dimension | Current run or release | Current status | Aggregation admission |
|---|---|---|---|
| D1 | `d1-final-33fa914b2f71`; `D1REL-1.3.0-cb06fed4b63a` | Released; release artifacts and dependency hashes verified | Yes |
| D2 | `D2V1_20260722_1714`; calibration `NorthBank_D2_v1_20260722` | Core score hash unchanged by refreshed D1 linkage | Yes |
| D3 | `RUN_D3_v2.2.0_20260726T084811Z_4246fb53` | 43,008 windows; 42,840 evaluable; mean score 4.799 | Yes |
| D4 | `D4V14_20260726_100717`; calibration `D4CAL-V14-7a16d7f511d3` | 42,847 pair-hours; 37,987 finalizable; numeric adjustment exactly zero | Yes, from `D4_raw` |
| D5 | `D5-LOCAL-20260726T101447Z` | 39,648 report-score rows; scientific score released; deployment blocked | Yes for report score; no hard action gate |

The strengthened cross-project audit passed **50/50 checks**. It verifies:

- D1 source, configuration, state and release-artifact hashes;
- the current D2 core workbook hash, not only before/after equality;
- D3 non-consumption of D1/D2 scores, regime labels and imputed values;
- preservation of D4 raw scores through D5 integration;
- D5 Local isolation from all D1-D4 numeric scores;
- report/gate separation and Guard/Veto semantic separation;
- canonical D1-D5 directory names and removal of retired top-level names;
- figure bundle completeness and freshness.

Formal tests passed **83/83**: D1 23, D2 18, D3 10, D4 10, D5 14 and
cross-project publication-style tests 8.

## Independence assessment

### D1 Sensor health

D1 scores sensor-intrinsic failure evidence and topology-constrained peer
residual evidence. Section 1.1 supplies the canonical time grid and regime
context, not a competing quality score. D2-D5 scores are prohibited numeric
inputs.

**Conclusion:** numerically independent and aggregation-ready.

### D2 Temporal continuity and information availability

D2 scores timestamp continuity, missingness, hard runs and information
availability. D1 event linkage is interpretive only and the linkage refresh
does not rewrite `D2_total`.

**Conclusion:** numerically independent and aggregation-ready.

### D3 Physical rationality and rate constraints

D3 scores unimputed observations against fixed value/rate evidence. It does not
consume D1 or D2 scores, D1 regime labels, or imputed values.

**Conclusion:** numerically independent and aggregation-ready.

### D4 Parallel-redundancy temporal consistency

`D4_raw` is the independent dimension score. D2 may determine whether a
pair-hour is observable. D1 is interpretation-only. D5 provides separate
report/gate evidence and cannot rewrite `D4_raw`; the observed maximum numeric
adjustment is 0.

**Conclusion:** aggregation-ready only from `D4_raw`. `D4_after_D1` must not be
used as the composite input.

### D5 Topological role consistency and structural representativeness

D5 Local uses confirmed ordinal topology, sensor observations, QR/QIR context
and time-of-day context. Its Local track consumes no D1-D4 score. The isolated
sensitivity track may read D1-D4 but has no production-write permission.

Validation achieved swap AUROC 0.912 and AUPRC 0.870. Swap Top-1 localization
was 0.70, below the 0.80 node-action threshold. Therefore, the scientific
report score is admitted, while node-specific hard Veto and deployment are not.

**Conclusion:** `D5_report_score` is aggregation-ready for eligible rows.
`D5_gate_interface` remains a separate action interface.

## Required aggregation contract

1. Align all dimensions on the canonical Section 1.1 time grid and sensor ID.
2. Carry `score`, `evaluable`, `evidence_level`, `uncertainty` and `lineage`
   separately for every dimension.
3. Never replace a missing or non-evaluable dimension with a low score.
4. Renormalize weights over eligible dimensions and report the effective
   dimension count.
5. Keep sensor-identity Veto outside the weighted score.
6. Keep process-coherence Guard as attribution suppression, not a Veto.
7. Use `D4_raw`, not `D4_after_D1`, as the D4 numeric input.
8. Use `D5_report_score` for aggregation and keep the D5 gate interface
   separate.
9. Freeze mapping functions and aggregation weights before the final temporal
   test period is opened.
10. Report both the composite estimate and propagated uncertainty.

## Dimension-specific work before a top-journal claim

### D1

- Validate fault and recovery episodes against maintenance or operator records.
- Extend controlled injection calibration across analyte, regime, amplitude,
  duration and sensor-resolution strata.
- Report event-level sensitivity, false-alarm rate, recovery-time uncertainty
  and right-censoring, not only hourly state occupancy.
- Externally validate topology-constrained peer models and floor-channel logic.
- Prespecify how low-variance process floors differ from digital freeze.

### D2

- Validate outages and long runs against SCADA communication and maintenance
  logs where available.
- Distinguish sensor outage, network outage, planned downtime and process-floor
  resolution limitation.
- Report threshold sensitivity for the 6 h QFA window, 15 min hard RLE and gap
  severity mappings.
- Validate response-loss only with process-matched peers and comparable
  excitation.
- Add temporal and, preferably, external-plant validation.

### D3

- Trace every physical/rate threshold to an instrument range, process design
  source, literature source or expert-approved rule.
- Quantify threshold uncertainty and show that conclusions are stable under
  defensible perturbations.
- Validate event precision and false-positive burden against labelled or
  adjudicated events.
- Evaluate seasonal and major operating-regime transportability.
- Add multivariate constraints only when a defensible process mechanism exists;
  avoid complexity that cannot be independently verified.

### D4

- Increase benchmark support for analyte-by-regime strata, especially sparse
  ORP strata.
- Validate change-point lag and 3 h event persistence against independently
  adjudicated paired-sensor events.
- Report confidence intervals for all pair-level scores and event metrics.
- Test common-mode process changes, target faults and peer faults as separate
  negative/positive controls.
- Repeat validation on an independent time block and, if possible, a second
  plant or treatment line.

### D5

- Raise node-localization Top-1 performance above the prespecified 0.80
  threshold before enabling sensor-specific hard Veto.
- Expand node-level L3 support beyond the current three admitted templates.
- Complete asset/maintenance provenance and dual approval before operational
  deployment; these items do not block retrospective scientific scoring.
- Validate topology and event truth on independent records.
- Retain the report/gate dual interface and never infer a D5 action from the
  sensitivity track.

## Cross-dimensional work before final manuscript lock

### Priority 0: required for the definitive composite

- Prespecify the aggregation family, weight constraints and missing-dimension
  policy.
- Estimate weights with nested blocked temporal validation or a separately
  defined downstream criterion; do not optimize and test on the same period.
- Propagate subscore uncertainty by block bootstrap or an equivalent
  autocorrelation-aware method.
- Quantify inter-dimension dependence, redundancy and effective dimensionality.
- Perform leave-one-dimension-out ablation and weight-sensitivity analysis.
- Reserve an untouched terminal time block for final composite evaluation.

### Priority 1: required for a strong top-journal paper

- Establish criterion validity against downstream forecast, control, data
  assimilation or expert-adjudicated usability outcomes.
- Report convergent and discriminant validity without claiming causal
  independence.
- Add seasonal/regime subgroup stability and uncertainty intervals.
- Compare the five-dimensional score with simpler baselines.
- Define manuscript claims separately for scientific diagnosis, DQR admission
  and operational action.

### Priority 2: strongly recommended

- Add external-plant validation or clearly label the study as single-plant.
- Publish frozen source data tables, configuration files, manifests and
  executable environment information under a FAIR data/code plan.
- Predefine multiplicity control for confirmatory subgroup analyses.
- Conduct an independent code and rule review before manuscript submission.

## Figure assessment

The current formal bundle contains 52 PNG/PDF/SVG figure sets with zero bundle
failures; D5 also provides TIFF exports. Arial, editable SVG/PDF text, panel
labels and outward/inward tick conventions are implemented consistently.

Recommended final manuscript curation:

- Remove embedded `Figure X`, `final` and implementation-oriented wording from
  main-text canvases; move those details to captions.
- Use one sensor-ID convention across all dimensions. D1/D2 currently use
  underscores while some D3 figures display hyphens.
- Move D3 event panels with many empty rows to the Supplement or render only
  channels with events while explicitly reporting the excluded zero-event
  count.
- Keep D4 validation curves because they transparently show that spike
  discrimination is secondary; do not overstate the spike result.
- Keep D5 validation figures because they make the Top-1 limitation and
  negative controls visible.
- For final typesetting, place D2 group labels outside the data matrix or use a
  non-occluding margin annotation.

## Final conclusion

The current D1-D5 implementation is suitable for the **final subscore
aggregation development stage** and for drafting the methods/results structure
of a high-frequency dynamic data-quality paper. It is not yet sufficient for a
definitive claim that the composite score is externally validated or ready for
automated plant decisions. The remaining critical work is composite
calibration, uncertainty propagation, blocked independent testing and external
criterion validation, not another redesign of the five subdimensions.
