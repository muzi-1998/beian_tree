# D1 Sensor Health: final method and validation record

**Run ID:** `d1-final-57bdbc83894f`

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
12. PLS uses same-analyte peers only, with three-fold blocked temporal validation; DO-ORP suffix matching is prohibited.

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
| Final mean D1 | 4.2436 | STRICT V1 mean = 4.2523 |

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

- Structural peers are same-analyte adjacent and twin-pool channels.
- Additional same-analyte peers require at least 2% median blocked-CV NRMSE improvement and no more than 5% tail-error degradation.
- CV-supported additions occurred for `DO_1_1` (2.31%), `ORP_1_2` (5.13%), and `ORP_2_1` (4.78%).
- No DO-ORP pair was selected; `DO_1_4` is excluded as another target's predictor.
- PLS residual z-scores use training residual scale with a 5% target-scale floor.

## Figure decisions

- Fig. 6 now reports exact additive attribution of `5-D1_pre` and absolute severe-evidence frequency. The previous dominant-minimum plot was removed.
- Fig. 7 retains the state cap and exposes the `ORP_1_2` pre-cap score, cap-active hours, and final 2.5 platform.
- Fig. 9 harmonic demonstration was removed because it duplicated Section 1.1 and mislabelled `raw-residual` as a harmonic component. The replacement audits 1.1-to-D1 routing and detector applicability.
- Fig. 11 now shows the actual selected PLS matrix and blocked-CV gain. The hard-coded DO-ORP peer schematic was removed.

## Release gate

- `pytest`: 17 passed.
- Formal transition conservation: passed.
- Recovery mechanism challenges: 4/4 classes passed for production variant C.
- Excel exporter: 17 core workbooks generated successfully.
- Figure bundle: 20/20 SVG, PDF, PNG, and TIFF bundles passed.
- Nature source preflight: 0 failures; editable SVG/PDF text and Arial-compatible font stack.
- Quantitative figure source data are exported under `outputs/plot_data/`.

## Interpretation boundary

The event recovery rate measures internal state-machine completion, not diagnostic sensitivity or specificity against maintenance truth. Controlled injections validate mechanism behavior but do not replace blind maintenance-log adjudication, site-held-out validation, or prospective fault follow-up.
