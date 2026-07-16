# D7 Expert Review Report v2.1

**Project:** Topological Role Consistency and Structural Representativeness  
**Run:** `D7-LOCAL-20260716T125319Z`  
**Generated:** 2026-07-16 21:19 CST  
**Decision:** Research package complete; production DQR release blocked.

## 1. Executive verdict

The D7 v2.1 research implementation is complete at the P2/V2 artifact level: Local, Sensitivity and Shadow V2 tracks, frozen templates, hourly scores, raw evidence, validation, plot data, SCI-ready figures, manifests and audit records are present. The Local Track is logically independent of D1, D2, D4 and D6 and consumes only canonical observations, exogenous hydraulic/time context and declared D7 topology.

The project is **not production-ready**. The field topology, asset/serial/channel-position mapping and two-person approval remain pending; only 3 of 56 templates reach L2, while 53 remain L1; swap Top-1 is 0.75, below the 0.80 acceptance target. Consequently `D7_total`, `D7_forDQR` and D6 final arbitration correctly contain zero evaluable rows.

## 2. Scope and dimensional independence

- D7 asks whether a DO/ORP observation still behaves like its declared spatial position and represents its process zone.
- D1 evaluates sensor-intrinsic health and long-term regime-relative behavior; D2 evaluates continuity and information availability; D4 evaluates physical value/rate plausibility; D6 evaluates temporal synchronization between parallel counterparts.
- Local D7 does not consume any D1-D6 score, state or event field. D1/D2/D4 are read only in the physically isolated Sensitivity Track.
- QR/QIR are exogenous context variables only and never receive a D7 score.
- Observed low `D7_raw` is structural evidence, not a confirmed hardware fault.

## 3. Data and result freshness

- Hourly sensor windows: 86,016, spanning 2025-08-01 00:00:00 to 2026-04-13 23:00:00.
- Calculable `D7_raw`: 85,092; mean 3.155, median 3.186, p05 1.483.
- Raw low-score fraction (`D7_raw < 3`): 43.8%; candidate persistent events: 499.
- Full 10-min regime-state trajectory retained; OOD hold rate: 17.1%; confirmed switches: 1102.
- Result provenance is bound to canonical input hashes, topology hash, template/mapping/regime versions and code commit in `D7_run_manifest.json`.

## 4. Applicability and support

- `limited_support`: 70,568 (82.0%)
- `out_of_template`: 14,524 (16.9%)
- `not_evaluable`: 924 (1.1%)

- `L1`: 53 templates
- `L2`: 3 templates

ORP is deliberately forced to L1 `diagonal_robust_z` with `alpha=1.00`. It is never promoted automatically. L0, if encountered in a short or sparse rerun, is disabled rather than written as a low score.

## 5. Validation and sensitivity

| Criterion | Estimate | Target | Result |
|---|---:|---:|---|
| Swap AUROC | 0.917 | >=0.90 | Pass |
| Swap AUPRC | 0.928 | >=0.80 | Pass |
| Swap Top-1 | 0.750 | >=0.80 | **Fail** |
| Common-mode FAR | 0.061 | <=0.10 | Pass |
| Zone-coherent FAR | 0.039 | <=0.10 | Pass |
| Switch chatter rate | 0.000 | <=0.05 | Pass |
| IE_track | 0.041 | <=0.20 | Pass |
| Event Jaccard | 0.844 | >=0.80 | Pass |
| Culprit Spearman rho | 0.978 | >=0.80 | Pass |

Validation uses observed test-period spatial windows with frozen templates. Same-line, same-analyte position swaps are positive controls. Freeze, temporal ramps, common-mode and zone-coherent changes, DO4 floor behavior and dropout are negative/orthogonality controls. The swap detection metrics pass, but localization remains below the release criterion and must not be hidden by threshold tuning.

## 6. Topology and D6 interface

- Declared topology contains 14 DO/ORP nodes, 10 longitudinal edges and seven parallel peer pairs.
- 5 finite candidate mappings exceed the report-only topology drift review threshold. These are hypotheses for field review, not automatic topology updates.
- Shadow V2 has `production_impact=none`; it cannot mutate `topology.yaml`, active templates, `D7_total` or Veto.
- `D7_total` non-null rows: 0; D6 interface evaluable rows: 0.
- D6 protected score columns are untouched because D7 has no D6 write path.

## 7. Figure review

Five multi-panel figure groups are available as SVG, PDF and 600 dpi PNG, backed by `D7_plot_data.parquet/.csv`. All use Arial, 0.8 pt boxed axes, inward ticks, `(a)/(b)/(c)` panel labels, endpoint-aware scales and transparent label backgrounds where annotations cover data. Automated counterpart/font/pixel QA passed: True.

## 8. Critical limitations

1. Topology and asset identity are declared but not field-verified or dual-approved.
2. Effective independent support is inadequate for production gating in 53/56 templates; ORP remains intentionally L1.
3. Swap Top-1 localization is 0.75 versus the 0.80 target.
4. The 499 candidate event windows have no external truth labels; event counts must not be reported as confirmed sensor faults.
5. Regime transition FAR and topology candidate recall are not estimable without external regime/topology truth.
6. `D7_raw` calibration is suitable for comparative research evidence, but operational event thresholds require labeled prospective confirmation.

## 9. Release decision and next actions

The branch may be reviewed and merged as a **research implementation with explicit production gates**. It must not be activated in WW-DQS/DQR arbitration yet.

1. Verify the process drawing, coordinates, asset IDs, serial numbers and channel-position mapping in the field.
2. Obtain independent reviewer and approver signatures; update `topology.yaml` and regenerate all topology-bound templates.
3. Accumulate qualified multi-season effective blocks and pass ORP/DO support exit criteria.
4. Improve and revalidate node localization to Top-1 >=0.80 on blocked holdouts.
5. Add field-confirmed swap/maintenance/topology cases and prospective event labels.
6. Only then set topology status to verified, rerun the full release workflow and consider `D7_total`/D6 final arbitration.
