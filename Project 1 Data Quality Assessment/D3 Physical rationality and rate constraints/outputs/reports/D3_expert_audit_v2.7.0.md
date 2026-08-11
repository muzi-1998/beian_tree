# D3 v2.7.0 Expert Audit

## Decision

D3 v2.7.0 is internally coherent and suitable for retrospective gate aggregation under its declared warning-only operational scope. The soft-boundary denominator is now a mathematically closed union probability, temperature uncertainty is propagated without reselecting the production coefficient, and all publication figures were rebuilt around claim boundaries rather than score decoration. The release does not establish universal operating limits, causal process attribution, or alarm sensitivity and specificity without reviewed event truth.

## Frozen Run

- Run ID: `RUN_D3_v2.7.0_20260811T031925Z_b3392abf`.
- Study interval: 2025-08-01 00:00 to 2026-04-13 23:59 at 1 min.
- Sensor-windows: 43,008; D3 score available: 42,748; unavailable: 260.
- Evidence status: sufficient 42,748; insufficient 168; temperature context unavailable 92.
- Gate status: Pass 34,479; Warn 8,274; Fail 0; NotEvaluated 255.
- Five windows without a complete soft-boundary score retain a determinate Warn from independent hard/rate evidence; unavailable context is never converted to Pass.
- Mean evaluated `D3_total`: 4.85408; physical/rate events: 5,615.
- Publication figures: 11; Nature bundle audit: 0 failures and 0 warnings.

## Closed Denominator Semantics

For temperature-conditioned aerobic DO, define low-side violation `L`, high-side violation `H`, and high-side evaluability `T`. The combined soft state is evaluated on:

`E = T OR L`

and the scored rate is:

`P(L OR H | E)`.

This contract has four consequences:

1. Missing temperature plus no low-side violation is unknown, not high-side pass.
2. A known low-side violation is retained even when temperature is absent.
3. Low- and high-side evidence are combined on one probability space.
4. Mutually exclusive low/high violations cannot be double counted.

Compared with v2.6, all 42,748 windows evaluable in both releases have exactly identical `D3_total` values (maximum absolute difference 0). The only score changes are 92 formerly implicit context passes that are now explicitly unavailable. Thus the correction changes evidence semantics and coverage, not the conclusions of evaluable windows.

## Alpha-Uncertainty Propagation

The frozen production coefficients remain the point estimates: 0.278937 for aerobic position 1 and 0.310030 for position 2. Their calendar-day cluster-bootstrap intervals are propagated as supplementary lower/point/upper scenarios, with no threshold reselection.

Across the four scored sensors in independent validation:

| Alpha scenario | Mean minute warning rate | Mean 2 h warning-window rate | Sensors passing both prespecified criteria |
|---|---:|---:|---:|
| Bootstrap lower | 0.619% | 6.353% | 1/4 |
| Point estimate | 0.056% | 0.640% | 4/4 |
| Bootstrap upper | 0.005% | 0.098% | 4/4 |

The asymmetric result is scientifically important: lower alpha values materially increase 2 h warning burden, especially at position 1. It quantifies envelope uncertainty but does not justify widening or replacing the frozen point estimate. Position 3 remains diagnostic-only; DO-2-3 failure is retained as an applicability boundary.

## Additional Spatial Diagnostics

- DO4 retains a physical lower boundary of 0 mg/L and a separate provisional zero-equivalence tolerance of -0.05 mg/L. Raw negative values are never overwritten.
- The paired DO4 median difference is persistently negative for line 1 versus line 2 across all study months; calendar-day block intervals are exported. This supports line-specific zero-offset review, not cross-sensor scoring.
- ORP line differences are position dependent. Median line-1 minus line-2 effects are -21.07 mV at position 1, +125.86 mV at position 2, and +201.26 mV at position 3, with day-block intervals. These results reject an unqualified shared ORP operating envelope but remain diagnostic pending process and maintenance review.

## Publication Figure Revision

The figure set was rebuilt under the local Nature figure contract with Arial text, consistent panel labels, editable SVG/PDF, 600 dpi PNG/TIFF, explicit uncertainty, and no overlapping annotations.

| Figure | Scientific role |
|---|---|
| Fig. 1 | Process topology, three-level threshold contract, attribution route, and D1/D2/D3 ownership boundary |
| Fig. 2 | Scored versus diagnostic evidence landscape and directional burden |
| Fig. 3 | Observed/evaluable coverage and explicit evidence-gate semantics |
| Fig. 4 | Persistent-rate definition, mutually exclusive attribution, morphology, and D1-D3 overlap |
| Fig. 5 | Threshold provenance and diagnostic boundary occupancy |
| Fig. 6 | Gate outcomes, event types, and scored/diagnostic directional profile |
| Fig. 7 | Frozen mechanism cases without post-hoc case selection |
| Fig. 8 | Controlled morphology/rate validation and overlap robustness |
| Fig. 9 | DO4 zero-equivalence, monthly stability, paired-line effect, and candidate upper bound |
| Fig. 10 | Temperature-conditioned alpha calibration, fixed-bound comparison, interval propagation, and forward transfer |
| Fig. 11 | ORP position-specific distributions and paired-line heterogeneity |

Suggested main-text figures are Figs. 1, 4, 6, 8, and 10. Figs. 2, 3, 5, 7, 9, and 11 are high-value supplementary or mechanism figures unless the manuscript centers on threshold transferability.

## Executed Recommendations

- Replaced the sum of side-specific rates with the strict determinable-set union rate.
- Added explicit `soft_state_determinable_count/fraction` fields and propagated them to exports.
- Prevented unavailable temperature context from generating a full D3 score or implicit Pass.
- Added lower/point/upper alpha propagation at minute and 2 h window scales.
- Added prespecified temperature-conditioned versus fixed 8 mg/L comparison.
- Added paired day-block uncertainty for DO4 and ORP spatial effects.
- Rebuilt ten existing figures and added the ORP spatial heterogeneity figure.
- Added frozen mechanism-case configuration and regression tests for denominator and context semantics.

## Deferred or Not Promoted

- No ROC/PR or alarm recall claim is made because independent reviewed event truth is unavailable.
- Position 3 is not widened or promoted; DO-2-3 remains unresolved.
- The DO4 candidate upper bound is not used in production because cross-line support is inadequate.
- ORP position envelopes remain diagnostic; they are not scoring thresholds without site review and independent event adjudication.
- No weight or threshold was tuned to improve the observed score distribution.
- A full shared raw-domain D1-D3 injection matrix is not claimed. Current evidence comprises D3 controlled morphology tests and empirical D1-D3 overlap; a common frozen preprocessing route is still required for a true end-to-end comparison.
- Full weight-simplex optimization is not pursued because it would imply unsupported parameter selection; the existing prespecified sensitivity set is retained.
- The process layout in Fig. 1 is a confirmed analytical topology, not a hydraulic P&ID or asset-verification substitute.

## Reproducibility

- `python -m pytest -q`: 32 passed.
- Full `python run_all.py`: completed successfully.
- Figure bundle: 11/11 present in SVG, PDF, PNG, and TIFF; all are newer than their source scripts, nonblank, Arial-declared, and contain editable SVG text.
- The optional local Nature validator is discoverable rather than a mandatory private dependency.

## Final Claim Boundary

The defensible manuscript claim is that D3 independently identifies instrument-range failures, provisional operating-envelope warnings, and persistent same-sign rate anomalies while preserving process-coherent changes as guarded diagnostics. Site-calibrated temperature normalization improves interpretability at aerobic positions 1-2, but uncertainty propagation, position-3 failure, ORP spatial heterogeneity, and missing external truth explicitly limit generalization. These limitations should remain visible in the manuscript rather than be removed by post-hoc threshold adjustment.
