# Final D1-D5 readiness audit

Audit date: 2026-07-29

## Executive decision

The canonical high-frequency dynamic data-quality dimensions are:

| Dimension | Canonical construct | Legacy lineage | Authoritative score |
|---|---|---|---|
| D1 | Sensor health | D1 | `D1_total` (`D1_total_hourly` release sheet) |
| D2 | Temporal continuity and information availability | D2 | `D2_total` |
| D3 | Physical rationality and rate constraints | former D4 | `D3_gate_status`; `D3_total` supplementary only |
| D4 | Parallel-redundancy temporal consistency | former D6 | `D4_raw` |
| D5 | Topological role consistency and structural representativeness | former D7 | `D5_report_score` |

All five constructs are current and reproducible. D1, D2, D4 and D5 remain
numerically separated dynamic evidence; D3 is an independent
non-compensatory Safety Gate. The prespecified retrospective aggregation has
now been executed as run `D1D5V20-854e66de7e6b`. The present evidence does not
support calling it an externally validated, deployment-ready WW-DQS index.

This distinction is important:

- **Retrospective scientific aggregation: completed.**
- **Final manuscript claims: conditionally admitted with the limitations below.**
- **Automated operational deployment: not admitted.**

## v2.0 confirmatory execution outcome

The authoritative package is
`outputs/confirmatory/D1D5V20-854e66de7e6b/`. Its 84 manifested artifacts pass
complete SHA-256 verification. It contains frozen configurations, six expanding
future-month splits, source registries, all derived plot data, six
Nature-ready main-text figure groups, the composite products and the execution
report.

- D1: Hard Freeze recall 1.000, Drift 0.693, Spike 0.396 and Step 0.240. These
  results define applicability boundaries; they do not justify a blanket
  0.80-detection claim. Seven exploratory 2x-resolution spike trials were
  explicitly excluded as locally non-evaluable; the primary native-resolution
  analysis was retained.
- D2: channel ranking was stable (`rho >= 0.996`). QFA 3 h and 12 h event
  Jaccard values were 0.731 and 0.721, below the frozen 0.75 threshold; the 6 h
  primary setting remains supported.
- D3: 27,689 Pass, 15,319 Warn and zero instrument-range Fail windows. All
  warning OAT Jaccard values were at least 0.899. Grade B source approval remains
  pending.
- D4: target/peer drift and step AUROC values were 0.912-0.936; freeze AUROC
  values were 0.798-0.809; equal common-process conditional FAR was 0.041.
  Hourly change-point scoring did not show monotonic severity across
  0-180 min (`rho=0`), so subhour lag identification is not claimed.
- D5: the released swap audit retained AUROC 0.912 and AUPRC 0.870. In the
  complete future-month outer refit, the full model achieved AUROC 0.967,
  AUPRC 0.974 and Top-1 localization 0.767. Detection passed, but localization
  still failed the locked 0.80 gate. Scientific report scores remain eligible;
  sensor-specific hard Veto remains disabled.
- Composite: 85,652 formal node rows and 37,975 formal pair rows were produced.
  Coverage was 39,606 full, 46,046 basic and 364 limited sensor-hours. D5
  report eligibility declines sharply after January 2026 and is shown as
  reduced evidence coverage rather than imputed low quality.

Nature figure source validation passed 14/14 checks with no warnings. The
confirmatory package adds five Python PNG/PDF/SVG/TIFF quantitative groups and
one editable Scientific Illustrator framework group without altering the
existing dimension-specific bundles. The framework audit found 33 native
objects, zero raster pictures and zero findings.

## Freshness evidence

| Dimension | Current run or release | Current status | Aggregation admission |
|---|---|---|---|
| D1 | `d1-final-33fa914b2f71`; `D1REL-1.3.0-cb06fed4b63a` | Released; release artifacts and dependency hashes verified | Yes |
| D2 | `D2V1_20260722_1714`; calibration `NorthBank_D2_v1_20260722` | Core score hash unchanged by refreshed D1 linkage | Yes |
| D3 | `RUN_D3_v2.2.1_20260727T043759Z_8d52c551` | 43,008 windows; 42,840 evaluable; mean score 4.799486 | Yes |
| D4 | `D4V14_20260726_100717`; calibration `D4CAL-V14-7a16d7f511d3` | 42,847 pair-hours; 37,987 finalizable; numeric adjustment exactly zero | Yes, from `D4_raw` |
| D5 | `D5-LOCAL-20260727T034533Z` | 39,648 report-score rows; scientific score released; deployment blocked | Yes for report score; no hard action gate |

The strengthened cross-project audit passed **50/50 checks**. It verifies:

- D1 source, configuration, state and release-artifact hashes;
- the current D2 core workbook hash, not only before/after equality;
- D3 non-consumption of D1/D2 scores, regime labels and imputed values;
- preservation of D4 raw scores through D5 integration;
- D5 Local isolation from all D1-D4 numeric scores;
- report/gate separation and Guard/Veto semantic separation;
- canonical D1-D5 directory names and removal of retired top-level names;
- figure bundle completeness and freshness.

The dimension tests pass **76/76**: D1 23, D2 18, D3 11, D4 10 and D5 14.
Cross-project publication/freshness contract tests pass **10/10** and the added
confirmatory package tests pass **9/9**.

The cross-project freshness audit passes **50/50**. Its D1 dependency and D5
Local bundle hashes now canonicalize text to LF while hashing binary artifacts
unchanged. This removes Windows CRLF false mismatches; the locked portable D5
Local core hash is
`d4d4ec83ed4469b5b7ae9b62d69a8a3c28290c8b6ef841eaa80b4713ceb43a99`.

## Independence assessment

### D1 Sensor health

D1 scores sensor-intrinsic failure evidence and topology-constrained peer
residual evidence. Section 1.1 supplies the canonical time grid and regime
context, not a competing quality score. D2-D5 scores are prohibited numeric
inputs.

**Conclusion:** independent Safety Gate ready. `D3_total` is retained for
supplementary physical-evidence analysis and is not a composite score input.

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

The released swap audit achieved AUROC 0.912 and AUPRC 0.870. Complete
future-month outer refits were additionally performed for the full model,
no-exogenous-context, no-regime and no-hysteresis variants. Full-model Top-1
localization was 0.767 (outer-fold 95% CI 0.683-0.850), below the 0.80
node-action threshold. Therefore, the scientific report score is admitted,
while node-specific hard Veto and deployment are not.

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
9. Use the frozen equal-weight formula. Do not learn weights without a separate
   external criterion.
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

- Preserve the verified installation-register ranges (DO 0-20 mg/L and ORP
  -1500-1500 mV) as instrument evidence, separate from operational alarm
  limits and expert plausibility bounds.
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

### Priority 0: required for claims beyond retrospective aggregation

- Retain the frozen equal-weight and eligible-dimension missingness policy.
- Learn alternative weights only against a separately defined external
  criterion and within nested blocked temporal validation.
- Extend the completed block-bootstrap uncertainty and dimension ablation to
  external criterion analyses.
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

## Implementation feasibility as of 2026-07-29

### Can be executed directly with current data and code

- D1: use the completed analyte-, regime-, amplitude-, duration- and
  resolution-stratified injection outputs to define applicability boundaries;
  extend the frozen raw-domain endpoint audit only when additional compute or
  independent records are available.
- D2: run sensitivity analyses for the 6 h QFA window, 15 min hard RLE and gap
  severity mappings; retain floor occupancy and resolution limitation as
  diagnostics separate from sensor freeze.
- D3: build the threshold-source register from the verified instrument
  workbook and primary literature; perturb hard, soft and rate thresholds and
  report score/event stability with autocorrelation-aware intervals.
- D4: strengthen sparse ORP analyte-by-regime baselines using prespecified
  pooling or shrinkage; add directional target-fault, peer-fault,
  common-process and controlled change-point-lag injections.
- D5: retain the completed full outer refits for no exogenous context, no
  regime conditioning and no hysteresis; test whether additional node
  templates satisfy L3 evidence rules using future evidence. The 0.80 Top-1
  threshold remains a locked acceptance rule, not a tuning target.
- Composite: prespecify weights and missingness rules, run blocked nested
  validation, block-bootstrap uncertainty propagation, dependence analysis,
  dimension ablation and simpler-baseline comparisons.
- Figures: move sparse D3 event heatmaps to the Supplement or filter to
  event-bearing channels with an explicit excluded-channel count; standardize
  sensor IDs; move `Figure X`, `final` and implementation labels from canvases
  to captions.

### Can be started now but requires expert adjudication to become confirmatory

- D1 event recovery and false-alarm validation can be prepared now, but final
  sensitivity and specificity require matched maintenance or operator truth.
- D2 outage patterns can be provisionally classified, but sensor, network and
  planned-downtime causes require SCADA or maintenance-log adjudication.
- D3 stable-window negative controls can estimate an internal false-alarm
  burden, but event precision requires labelled or dual-reviewed events.
- D4 synthetic controls can establish mechanism discrimination, while real
  synchronization and process-asymmetry events require independent review.
- D5 additional L3 candidates may be screened with current records, but each
  node template still requires minimum node-level validation support.
- A within-plant downstream criterion may be analyzed if laboratory, forecast,
  control or assimilation outcomes are supplied and temporally aligned.

### Requires new records, an untouched period or an external dataset

- Maintenance work orders, operator fault logs and verified recovery times for
  D1.
- PLC/SCADA communication logs, network alarms and planned-shutdown records for
  D2.
- Plant design documents and signed expert provenance for operational D3
  thresholds not covered by the instrument register or primary literature.
- Independently confirmed synchronization faults, peer failures and
  common-process events for D4.
- Asset/maintenance provenance and dual approval for D5 deployment. These
  remain deployment blockers only and do not block retrospective scientific
  aggregation.
- A genuinely unseen future period for definitive terminal testing, an
  independent external criterion and a second-plant dataset for
  transportability claims. A segment already inspected during method
  development cannot be relabelled as an untouched test set.

## Figure assessment

The existing dimension bundles remain unchanged. The confirmatory package adds
six curated main-text groups: framework and claim boundary, D1 applicability,
D2 one-at-a-time sensitivity, D3 Safety Gate, D4/D5 mechanism and localization,
and Full/Basic composite evidence. Arial, editable vector text, source-data
workbooks, panel labels and outward/inward tick conventions are implemented
consistently.

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

The current D1-D5 implementation has completed the **retrospective scientific
aggregation stage** and is suitable for drafting the methods/results structure
of a high-frequency dynamic data-quality paper. It is not sufficient for a
definitive claim that the composite is externally validated or ready for
automated plant decisions. The remaining critical work is independent truth,
an untouched future period, external criterion validation and cross-plant
transportability, not another redesign of the five constructs or another
post-hoc structural-ablation search.
