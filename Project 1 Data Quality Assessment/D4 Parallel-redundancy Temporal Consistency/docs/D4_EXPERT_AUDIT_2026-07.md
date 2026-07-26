# D4 Final Expert Audit (2026-07)

## Executive decision

D4 is complete for retrospective scientific subscore aggregation. Its numeric
source is exclusively `D4_raw`, which measures pair/edge-level temporal
consistency between homologous sensors in the two treatment lines. D1 is
interpretation-only, D2 controls whether paired evidence is observable, and D5
is supplied through separate report and action-gate interfaces. None can
rewrite `D4_raw`.

The current integration finalizes 37,987 of 42,847 pair-hours. The maximum
absolute difference between the final scientific D4 value and `D4_raw` is
0.0. No D5 proxy is generated. Because no matched pair currently has
node-specific L3 support at both ends, the D5 action gate is applicable to zero
pair-hours; process Guard and sensor Veto are therefore both inactive. This
limits automated attribution, not the independent D4 score.

## Scientific contract

1. Section 1.1 supplies the de-periodised residual time base.
2. D4 uses one public analyte-by-regime mapping learned from qualified common
   benchmark windows; it does not self-normalize each pair.
3. Benchmark admission requires bilateral D1 >= 4.5, bilateral D2 usability,
   at least 24 h continuous coverage and complete paired residual evidence.
   These are evidence-quality screens and do not blend D1 or D2 scores into
   `D4_raw`.
4. Change-point timing uses adjacent 12 h distributions within a 7 d auxiliary
   window. The pair score distinguishes synchronous, delayed and unilateral
   changes.
5. D4 events require evaluable `D4_raw < 3` for at least 3 h.
6. `D4_after_D1` is retained only as historical interpretive sensitivity.
   It is not an aggregation input.
7. D5 report evidence may explain spatial context. The separate action gate may
   suppress sensor attribution through a process-coherence Guard or activate a
   sensor-identity Veto only where the corresponding node-level claim has
   passed.

## Current result

- Run: `D4V14_20260726_100717`
- Configuration: `d4-v1.4-canonical-d4-20260726`
- Calibration: `D4CAL-V14-7a16d7f511d3`
- Study span: 2025-08-01 00:00 to 2026-04-13 23:50
- Rows: 42,847 across seven homologous pairs
- Evaluable rows: 37,987 (88.66%)
- Events: 1,008 runs of at least 3 h
- Integration status: `final_independent_D4_with_dual_D5_interfaces`
- Finalized rows: 37,987
- D5 gate-applicable rows: 0
- Maximum numeric adjustment: 0.0

| Pair | Mean D4 raw | Low-score rate | Evaluable rate | 3 h events |
|---|---:|---:|---:|---:|
| DO11 | 3.368 | 31.4% | 97.5% | 124 |
| DO12 | 3.391 | 26.5% | 98.7% | 128 |
| DO13 | 3.198 | 40.6% | 98.8% | 162 |
| DO14 | 2.978 | 47.8% | 98.8% | 79 |
| ORP11 | 3.425 | 27.7% | 92.3% | 136 |
| ORP12 | 3.040 | 49.2% | 70.3% | 215 |
| ORP13 | 2.650 | 67.6% | 64.2% | 164 |

DO14 is no longer made unavailable merely by its post-anoxic low-DO floor.
Its high evaluability and low pair-consistency score are separate findings:
D2 confirms that data exist, while D4 detects inter-line inconsistency. D4
alone cannot determine whether the cause is a sensor fault or a real local
process difference.

## Validation

| Scenario | Metric | Estimate | 95% CI | Decision |
|---|---|---:|---:|---|
| Unilateral drift | ROC AUC | 0.934 | 0.905-0.960 | Pass |
| Unilateral step | ROC AUC | 0.936 | 0.903-0.963 | Pass |
| Unilateral freeze | ROC AUC | 0.798 | 0.749-0.849 | Pass |
| Unilateral spike | ROC AUC | 0.561 | 0.546-0.581 | Secondary only |
| Synchronous switch | Conditional new FAR | 0.041 | 0.000-0.095 | Pass |
| Common-mode drift | Conditional new FAR | 0.041 | 0.000-0.095 | Pass |

Isolated spikes remain primarily a D1 responsibility. The validation supports
implementation correctness and mechanism sensitivity but does not replace
independently adjudicated field events.

## Figure decision

The formal bundle contains `FigD4_1` to `FigD4_8`. The main heatmap and status
barcode show only current independent `D4_raw` evidence. D1 context appears
only in the explicitly labelled independence diagnostic. The historical
three-version comparison remains an internal sensitivity artifact and is not
required in the main manuscript.

All formal figures use Arial, 0.8 pt axes, lowercase panel labels, inward ticks
for full frames, outward ticks for open frames, and PNG/PDF/SVG counterparts.

## Remaining top-journal limitations

1. Expand ORP benchmark support so every regime can use an exact stratum rather
   than the documented variable-level fallback.
2. Validate the 3 h event rule and change-point timing against independent
   operational-event labels.
3. Add process records or field cases for DO14 and ORP13 to separate real
   inter-line asymmetry from sensor-specific causes.
4. Add external temporal or plant validation; current injection tests are
   internal chronological stress tests.
5. Keep sensor attribution and automated Veto claims disabled until D5 has
   sufficient matched node-level L3 support and localization performance.

These limitations do not block retrospective D4 subscore aggregation when
eligibility and uncertainty are reported. They block stronger causal and
deployment claims.
