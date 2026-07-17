# D1 Sensor Health: final method and validation record

**Run ID:** `d1-final-2e29da7b7e67`
**Algorithm:** `1.3.0-final-candidate`
**Scope:** 14 DO/ORP channels; QR/QIR are offline support only.

## Decision

The D1 implementation is suitable as the locked final candidate for the thesis and manuscript workflow. It evaluates the health of an individual sensor from signal-health evidence. It does not score temporal availability (D2), physical-rate plausibility (D4), parallel-redundancy synchrony (D6), or topological representativeness (D7).

## Nine completed revisions

1. Recovery performance is event-level. `Recovered` hourly occupancy is descriptive and is never reported as the recovery rate.
2. Direct recovery and adapted recovery are explicit terminal event outcomes; both require confirmation.
3. Recovery uses a tolerant 12-of-18 h window after a 3 h entry streak, with bounded soft failures and missingness.
4. `Q_regime` and raw `W1_norm` are no longer duplicate production vetoes. W1 remains an explanatory diagnostic.
5. A stable, credible new regime can recover through independent local and peer residual evidence without returning to the historical regime.
6. Local residual scaling uses a causal empirical channel-specific noise floor estimated from the initial calibration prefix.
7. Baseline construction is causal, contiguous, and gap-safe. No future sample may contribute to a current decision.
8. Event retriggering during an active episode requires independent PELT evidence; event IDs are unique and transition conservation is audited.
9. Natural-data sensitivity, four controlled mechanism challenges, source-data exports, run hashes, tests, and Nature-style figure QA are part of the release gate.

## Final results

| Metric | Result | Interpretation |
|---|---:|---|
| Event episodes | 51 | Unique causal anomaly episodes |
| Direct recovery | 44 | Abnormal evidence cleared after Refractory |
| Adapted recovery | 6 | Recovery after stable local-baseline adaptation |
| Superseded | 1 | Replaced by an independently supported event |
| Right-censored | 0 | No unresolved end-of-record episode in this run |
| Event recovery rate | 0.9804 | 50 recovered / 51 completed episodes |
| 95% Wilson interval | 0.8970-0.9965 | Sampling uncertainty remains material |
| Median recovery time | 53 h | Event onset to confirmed recovery |
| Recovered occupancy | 0.22% | A 24 h observation state, not recovery performance |
| Transition conservation | Pass | 51 opened = 51 episode records; no duplicate IDs |

Production variant C passed all expected outcomes for all 14 channel-scaled templates in four mechanism challenges: transient step, stable new regime, persistent fault, and independent retrigger. In particular, stable new regimes recovered and persistent faults did not falsely recover.

## Interpretation boundary

The event recovery rate measures internal state-machine completion, not diagnostic sensitivity or specificity against maintenance truth. The current dataset lacks independently adjudicated sensor-fault and maintenance labels. Controlled injections validate mechanism logic but do not replace end-to-end external validation. These limits must be stated in the manuscript.

## Release gate

- `pytest`: 7 passed.
- Formal state transition conservation: passed.
- Excel workbooks: 18 opened successfully; no formula-error tokens detected.
- Step mapping: logistic `k=8.0`, `x0=0.40`.
- Figure bundles: 20/20 have SVG, PDF, 600 dpi PNG, and 600 dpi TIFF.
- Nature figure audit: 20 figures, 0 failed; SVG text remains editable and Arial is declared.
