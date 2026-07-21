# D1 Sensor Health: final method and validation record

**Run ID:** `d1-final-8fdd3599890f`

**Algorithm:** `1.3.0-final-candidate`
**Scope:** 14 DO/ORP channels; QR/QIR are offline support only.

## Expert decision

The implementation is suitable as the locked internal final candidate for thesis and manuscript analyses. D1 evaluates individual-sensor signal health and remains independent of D2 availability, D4 physical-rate plausibility, D6 parallel-redundancy synchrony, and D7 topological representativeness. Diagnostic sensitivity and specificity still require independently adjudicated maintenance or fault labels.

## Final method revisions

1. Recovery performance is event-level; `Recovered` hourly occupancy is descriptive only.
2. Direct and adapted recovery are explicit confirmed outcomes.
3. Recovery uses a tolerant 12-of-18 h window after a 3 h entry streak.
4. `Q_regime` is the production regime gate; raw W1 remains diagnostic.
5. A stable credible new regime can recover through local and peer-residual evidence.
6. Local scaling uses causal channel-specific empirical noise floors.
7. Baseline construction is past-only, contiguous, and gap-safe.
8. Active-episode retriggering requires independent PELT evidence.
9. Event identity, censoring, relapse, and transition conservation are formally audited.
10. `DO_1_4` uses a process-floor freeze route: hard RLE is the production score; low variance and uniqueness are diagnostics only.
11. Step mapping is calibrated by raw detector-input sustained-step injection on the valid `iid` domain.
12. PLS uses an explicit same-analyte topology. A second-order peer may enter only after full-period forward validation, moving-block bootstrap uncertainty, a terminal 42-day test, and target/peer/common-process fault injections. A valid one-peer core is retained; lexical or distant-channel fallback is prohibited.

## Final results

| Metric | Result | Interpretation |
|---|---:|---|
| State-machine episodes | 22 | Unique causal anomaly episodes |
| Direct recovery | 15 | Cleared after Refractory |
| Adapted recovery | 6 | Confirmed after local-baseline adaptation |
| Superseded | 1 | Replaced by independent event evidence |
| Right-censored | 0 | No unresolved end-of-record episode |
| Event recovery rate | 0.9545 | 21 recovered / 22 completed episodes |
| 95% Wilson interval | 0.7820-0.9919 | Sampling uncertainty remains material |
| Median recovery time | 53 h | Event onset to confirmed recovery |
| Recovered occupancy | 0.207% | Observation-state occupancy, not recovery rate |
| Relapse at 24/48/72 h | 0/0/0 | No confirmed relapse in this run |
| Transition conservation | Pass | 22 opened = 22 episode records; no duplicate IDs |
| Final mean D1 | 4.2450 | Current locked pipeline |

## Detector calibration and routing

### Process-floor freeze

- `DO_1_4` final mean `Q_freeze`: 4.9993.
- `Q_freeze < 3` rate: 0%.
- Low variance and low uniqueness remain published diagnostics but cannot lower production `Q_freeze` for the process-floor route.
- Hard RLE evidence remains active, so true response loss is not silently ignored.

### Step mapping

| Item | Result |
|---|---:|
| Calibration ID | `step-injection-ea8d55282211` |
| Injection-library SHA-256 | `775d423be3d728fd48533c6e84bfc07af3233164dc6186bf33b3c1969259b970` |
| Final mapping | `k=16.0`, `x0=0.55` |
| Fit domain | 10 `iid` channels; 780 scenarios |
| Blank warning rate | 0% |
| 0.5-sigma hard-error rate | 0.83% |
| Detection rate for >=2-sigma shifts | 86.67% |
| Material miss rate | 13.33% |
| LOCO stability | All 10 folds selected `16.0/0.55` |

Three `autocorr_aware` channels and the process-floor channel remain in the applicability audit but are excluded from parameter fitting. Their corrected-KS ceiling is constrained by `sqrt(n_eff)` and therefore does not share the same mapping-identification domain.

### PLS peers

- Structural peers are same-analyte adjacent and available twin-pool channels. If exclusions leave one valid structural peer, that peer is retained rather than being replaced by unrelated channels.
- Candidate expansion is restricted to same-pool second-order neighbours. The locked comparison is `M0 = DO_2_3, 1 component`, `M1,1 = DO_2_3 + DO_2_2, 1 component`, and `M1,2 = DO_2_3 + DO_2_2, 2 components`.
- The first 21 days are the fixed deployment training period. The subsequent record is covered by 28 forward validation blocks, while the terminal 42 days remain independent. Median-gain uncertainty uses 5,000 circular moving-block bootstrap replicates with a four-block length.
- `M1,1` has a median development gain of -5.35% (95% block-bootstrap CI -16.65% to 0.51%), positive gain in 32.14% of blocks, and development P90 error degradation of 7.89%. Its independent-test NRMSE gain is -19.43% and P90 degradation is 17.30%.
- `M1,2` has a median development gain of -19.50% (95% CI -33.03% to -5.85%), positive gain in 10.71% of blocks, and development P90 degradation of 21.89%. Its independent-test gain is -35.31% and P90 degradation is 31.49%.
- Controlled injections use 13 mutually non-overlapping 48-hour windows that are jointly clean under all three models. Positive/negative 1-, 2-, and 3-sigma target, direct-peer, second-order-peer, and coherent common-process perturbations produce 936 auditable model-scenario rows. `M1,1` does not lose target-fault detection but fails the predictive and terminal-test gates; `M1,2` additionally increases direct-peer and common-process false alarms.
- The final decision is therefore to retain `M0`: `DO_2_4` uses `DO_2_3` only, with one PLS component. `DO_2_2` remains a tested but rejected candidate, not a formal predictor.
- No DO-ORP pair was selected; `DO_1_4` remains excluded as another target's predictor. No lexical, distant-channel, or cross-train fallback is permitted when the topology core is sparse.
- PLS residual z-scores use training residual scale with a 5% target-scale floor.

This correction preserves removal of the unsupported `DO_2_4 -> DO_1_1/DO_1_2` fallback and rejects the provisional `DO_2_2` expansion. In the locked result, the `DO_2_4` final mean is 3.896 and the full project contains 81 `D1 < 3` event windows lasting at least 6 h.

## Figure decisions

- Fig. 6 now reports exact additive attribution of `5-D1_pre` and absolute severe-evidence frequency. The previous dominant-minimum plot was removed.
- Fig. 7 retains the state cap and exposes the `ORP_1_2` pre-cap score, cap-active hours, and final 2.5 platform.
- Fig. 9 harmonic demonstration was removed because it duplicated Section 1.1 and mislabelled `raw-residual` as a harmonic component. The replacement audits 1.1-to-D1 routing and detector applicability.
- Fig. 11 now reports all forward-block gains, median and 95% block-bootstrap interval, positive-gain fraction, P90 error change, terminal-test gain, and controlled-injection deltas. It explicitly records the decision to retain `M0`.
- Supplementary Fig. S1 restores the all-channel audit view that the revised Fig. 11 replaced. It shows only production-active peer links and lists the effective predictor set and PLS component count for every scored channel; rejected candidates remain confined to Fig. 11. Its note and source workbook disclose that DO_2_4 has the full forward/hold-out/injection audit, whereas the remaining targets currently retain topology-constrained three-fold blocked-CV evidence.
- Fig. V12 now reports the current D1 operating profile only: channel-level 7-day moving-block bootstrap intervals, low-quality occupancy, state occupancy, and the cross-sensor temporal envelope.
- Fig. V13 and Fig. V14 retain the current state-machine audit but no longer overlay legacy score trajectories or timer estimates.
- The former Fig. V16 fixed-`k=4` clustering panel is retired from the formal D1 bundle. Its labels were arbitrary KMeans identifiers, its 44.0% R0 share was only `2700/6138 h` occupancy, and the long contiguous runs indicated temporal epochs rather than externally validated recurrent operating regimes. Any future D7 regime figure requires data-driven `k`, stability/recurrence tests, and independent load or control semantics.
- Fig. V18 now reports current grade composition, state-conditioned drift evidence, and event burden only. Historical-version comparison remains an internal software traceability artifact and is not used as manuscript evidence.

## Release gate

- `pytest`: 23 passed.
- Formal transition conservation: passed.
- Recovery mechanism challenges: 4/4 classes passed for production variant C.
- Excel exporter: 18 core workbooks generated successfully; 20 D1 workbooks are present including calibration/validation companions.
- Figure bundle: 20/20 SVG, PDF, PNG, and TIFF bundles passed.
- Nature source preflight: 0 failures; editable SVG/PDF text and Arial-compatible font stack.
- Quantitative figure source data are exported under `outputs/plot_data/`.

## Interpretation boundary

The event recovery rate measures internal state-machine completion, not diagnostic sensitivity or specificity against maintenance truth. Controlled injections validate mechanism behavior but do not replace blind maintenance-log adjudication, site-held-out validation, or prospective fault follow-up.
