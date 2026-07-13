# D6 Expert Audit and Revision Record (2026-07)

## 1. Executive conclusion

The two established design documents contain a strong engineering skeleton, but
the imported D6 package was not a complete or current implementation. It was a
flat proxy-era result bundle: the advertised `src/d6`, YAML configuration, tests,
and figure modules were absent; both entry scripts imported missing modules and
used hard-coded Linux paths; the internal audit run was dated 2026-05-30 and
declared D1/D2/D7 as proxies. Those results therefore could not be treated as the
latest D6 outputs after the July updates to Section 1.1, D1, and D2.

This revision rebuilds D6 as a reproducible independent dimension. The core is
now suitable for merging and downstream DQR integration. It is not yet suitable
for claiming that a pair asymmetry is specifically a sensor fault, because a
current D7 spatial-consensus product and externally labelled process-asymmetry
events are unavailable.

## 2. Expert evaluation of the established plans

### Strengths retained

1. The seven explicit `pair_id` keys are necessary and scientifically clear.
2. Distribution, trend, variability, and change-point evidence form a defensible
   multi-aspect description of pairwise temporal consistency.
3. A physical low-excitation deadband is appropriate for the variability term.
4. The non-compensatory blend prevents one very poor subscore from being hidden
   by three high subscores.
5. Separating score, detector evidence, mapping parameters, events, validation,
   profiles, multiscale products, and audit metadata is good reproducibility
   practice.
6. Six injection scenarios and ablation analysis are directionally appropriate,
   provided synchronous changes are assessed by false-alarm rate rather than
   presented as an anomalous positive class.

### Design issues corrected

1. **Causal overreach.** A paired discrepancy is symmetric evidence. It cannot,
   without independent spatial/process evidence, distinguish a faulty sensor
   from a real local process asymmetry. The current labels therefore use
   `pair_asymmetry` and retain `causal_attribution=unresolved_sensor_or_process_cause`.
2. **Dimension contamination.** The v1.2 proposal modified `D6_forDQR` using D1
   and D7. That makes D6 partly a function of other dimensions and invalidates a
   clean independence claim. In v1.3, D1 and D7 do not change D6.
3. **Double penalty from D2.** D2 now gates whether a pair can be evaluated; D6
   does not lower a score because observations are missing.
4. **Proxy contract violation.** The old scripts recalculated proxy D1, D2, D7,
   and regime variables despite claiming read-only adapters. Current D1 and D2
   outputs are read directly; D7 is not fabricated.
5. **Calibration leakage.** Pair-specific mapping quantiles use only the first
   70% of D2-non-veto, sufficiently complete windows. Internal validation uses
   the final 30%, preserving chronological separation.
6. **Inconsistent benchmark fallback.** D1-based benchmark selection produced
   different eligibility rules across pairs. D1 has therefore been removed from
   calibration and retained only as context.
7. **Deadband semantics.** The deadband sets only `Q_var=5` under physically
   negligible excitation. It does not suppress distribution, trend, or
   change-point evidence and does not bypass another dimension.

## 3. Current implementation and result freshness

- Current run: `D6V13_20260713_103039`.
- Data span: 2025-08-01 23:00 to 2026-04-13 23:00.
- Main output: 42,847 hourly pair windows across seven pairs.
- Evaluable fraction: 79.10%; 8,956 windows are explicitly `not_evaluable`.
- Input residuals: Section 1.1 `residual_min` production output.
- D2 context: current calibrated D2 hourly output and veto state.
- Traceability: SHA-256 hashes for the residual, time-base contract, D1, and D2
  inputs are stored in `D6_audit_log.xlsx` and `D6_run_manifest.json`.

The old proxy and current scores differ materially: their aligned D6 raw scores
have low agreement and approximately one score point mean absolute difference.
This is expected because the old run recomputed proxies and used a different
mapping population. The legacy workbooks are retained only for audit history.

## 4. Current scientific results

| Pair | Mean D6 | Pair-asymmetry rate | Evaluable rate | Events |
|---|---:|---:|---:|---:|
| DO11 | 3.98 | 12.0% | 97.3% | 76 |
| DO12 | 3.99 | 11.8% | 98.8% | 89 |
| DO13 | 3.79 | 17.1% | 98.8% | 135 |
| DO14 | 4.03 | 3.3% | 23.3% | 36 |
| ORP11 | 3.78 | 17.6% | 93.1% | 169 |
| ORP12 | 3.77 | 14.9% | 74.9% | 121 |
| ORP13 | 3.87 | 9.5% | 67.6% | 79 |

DO14's low evaluable rate is a D2 availability limitation, not evidence of high
or low D6 quality. This distinction is now visible in the score tables and Fig.D2.

### Chronological internal stress tests

| Scenario | Metric | Estimate (95% cluster-bootstrap CI) | Required |
|---|---|---:|---|
| Unilateral drift | ROC AUC | 0.931 (0.901-0.963) | Yes |
| Unilateral step | ROC AUC | 0.894 (0.850-0.932) | Yes |
| Unilateral freeze | ROC AUC | 0.811 (0.770-0.859) | Yes |
| Unilateral spike | ROC AUC | 0.553 (0.538-0.573) | No; D1 owns isolated spikes |
| Synchronous switch | False-alarm rate | 0.016 (0.000-0.040) | Yes |
| Common-mode drift | False-alarm rate | 0.016 (0.000-0.040) | Yes |

The ablation shows that distribution consistency carries the largest incremental
discrimination. Removing trend or change-point evidence does not reduce aggregate
AUC in the current injected set; those terms are retained for event explanation,
but their weights should be rechecked against externally labelled events before
the final manuscript claim.

## 5. Figure audit

### Problems in the proxy-era figures

- oversized bold titles dominated the data region;
- composite panels used bare `a`/`b` rather than `(a)`/`(b)`;
- legends and labels overlapped dense scatter or bar evidence;
- Fig.M3 was severely overplotted;
- the heatmap relied on red-green semantics;
- the bilateral-switch ROC was interpreted backwards;
- the ablation contained no uncertainty and showed no measurable D1/D7 layer
  contribution despite claiming a three-layer benefit;
- only SVG and 300 dpi PNG were supplied; PDF and 600 dpi outputs were absent.

### Current figure contract

All eight figures are generated from current outputs by Python and exported as
editable SVG, PDF, and 600 dpi PNG. Arial is declared first; visible spines and
ticks use 0.8 pt; full-frame plots use inward ticks, open axes use outward ticks;
every visible spine endpoint has a tick; composite panels use bold lowercase
parenthesised labels. Legends occupy reserved whitespace, and any in-panel text
uses a translucent white backing. The automated bundle audit reports eight
figures and zero failures.

## 6. File placement

The previous flat directory has been replaced by a conventional configuration,
source, scripts, tests, outputs, documentation, QA, and legacy hierarchy. This
separates reproducible inputs and code from generated deliverables and prevents
proxy-era files from being mistaken for current results.

## 7. Remaining risks and publication wording

1. D6 is complete as an independent pair-consistency score, not as a causal
   sensor-fault classifier.
2. Internal injection validation is not a substitute for labelled field events.
3. D7-aware evidence fusion must be implemented downstream and validated before
   using `process_asymmetry` or `sensor_asymmetry` causal labels.
4. DO14's low evaluability requires a D2/data-source investigation.
5. Trend and change-point weights require external-event sensitivity analysis.
6. Manuscript wording should state that isolated spikes are assessed by D1;
   D6's primary role is persistent or structural pair asymmetry.

**Merge recommendation:** merge the current D6 core, outputs, tests, and figures.
Do not merge any manuscript claim that D6 alone identifies the causal source of
an asymmetry or that a D7 arbitration benefit has already been demonstrated.
