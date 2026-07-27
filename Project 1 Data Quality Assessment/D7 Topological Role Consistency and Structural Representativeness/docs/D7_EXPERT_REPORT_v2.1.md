# D7 Expert Review Report v2.1

**Project:** Topological Role Consistency and Structural Representativeness
**Run:** `D7-LOCAL-20260726T032027Z`
**Generated:** 2026-07-26 11:38 CST
**Decision:** Research package complete; production DQR release blocked.

## 1. Executive verdict

The D7 v2.1 research implementation is complete at the P2/V2 artifact level: Local, Sensitivity and Shadow V2 tracks, frozen templates, hourly scores, raw evidence, validation, plot data, SCI-ready figures, manifests and audit records are present. The Local Track is logically independent of D1, D2, D4 and D6 and consumes only canonical observations, exogenous hydraulic/time context and declared D7 topology.

The ordinal research topology is confirmed: process line, pool zone, longitudinal order, SCADA-to-physical-point identity and the absence of study-period probe/channel changes are author-confirmed; the provided installation register independently reconciles eight active DO and six active ORP instruments. This is sufficient for research reporting because exact coordinates, asset IDs and serial numbers are not inputs to the ordinal D7 model. The project is **not production-ready** because maintenance provenance, documentary audit and two-person approval remain pending. Current support comprises 48 L1, 8 L2 and 0 L3 templates. Swap Top-1 is 0.70 (95% CI 0.57-0.80, n=60). Consequently `D7_total`, `D7_forDQR` and D6 final arbitration correctly contain zero evaluable rows.

## 2. Scope and dimensional independence

- D7 asks whether a DO/ORP observation still behaves like its declared spatial position and represents its process zone.
- D1 evaluates sensor-intrinsic health and long-term regime-relative behavior; D2 evaluates continuity and information availability; D4 evaluates physical value/rate plausibility; D6 evaluates temporal synchronization between parallel counterparts.
- Local D7 does not consume any D1-D6 score, state or event field. D1/D2/D4 are read only in the physically isolated Sensitivity Track.
- QR/QIR are exogenous context variables only and never receive a D7 score.
- One plant-global regime is inferred from QR/QIR, robust pooled DO/ORP level
  and dispersion, and cyclic time features. Every sensor is then compared with
  its role-specific template under the same active regime.
- Observed low `D7_raw` is structural evidence, not a confirmed hardware fault.

## 3. Data and result freshness

- Hourly sensor windows: 86,016, spanning 2025-08-01 00:00:00 to 2026-04-13 23:00:00.
- Calculable `D7_raw`: 85,092; mean 3.097, median 3.114, p05 1.345.
- Raw low-score fraction (`D7_raw < 3`): 46.0%; candidate persistent events: 529.
- Full 10-min regime-state trajectory retained; OOD hold rate: 15.5%; confirmed switches: 1246.
- Result provenance is bound to canonical input hashes, topology hash, template/mapping/regime versions and code commit in `D7_run_manifest.json`.
- Sensitivity inputs are bound to frozen D1 release `D1REL-1.3.0-f6074be3751f` and exact D2/D4/Local artifact hashes in `D7_sensitivity_manifest.json`.
- Production arbitration remains `pending_not_produced`; no `D7_forDQR` output was generated.

## 4. Applicability and support

- `limited_support`: 65,670 (76.3%)
- `out_of_template`: 13,342 (15.5%)
- `report_only`: 6,080 (7.1%)
- `not_evaluable`: 924 (1.1%)

- `L1`: 48 templates
- `L2`: 8 templates

ORP is deliberately forced to L1 `diagonal_robust_z` with `alpha=1.00`. It is never promoted automatically. L0, if encountered in a short or sparse rerun, is disabled rather than written as a low score.

L1 is diagnostic only. With the research topology confirmed, L2 may populate
both `D7_report_provisional` and the paper-facing `D7_report`, but cannot
populate `D7_total` or activate Veto. Only L3 evidence with production-approved
topology may enter DQR gating. Current provisional report rows:
6,080; research report rows:
6,080.

## 5. Validation and sensitivity

| Criterion | Estimate | Target | Result |
|---|---:|---:|---|
| Swap AUROC | 0.912 | >=0.90 | Pass |
| Swap AUPRC | 0.870 | >=0.80 | Pass |
| Swap Top-1 | 0.700 [0.575, 0.801], n=60 | >=0.80 | **Fail** |
| Common-mode FAR | 0.046 | <=0.10 | Pass |
| Zone-coherent FAR | 0.057 | <=0.10 | Pass |
| Switch chatter rate | 0.000 | <=0.05 | Pass |
| IE_track | 0.048 | <=0.20 | Pass |
| Event Jaccard | 0.825 | >=0.80 | Pass |
| Culprit Spearman rho | 0.962 | >=0.80 | Pass |

Validation uses observed test-period spatial windows with frozen templates. Same-line, same-analyte position swaps are positive controls. Freeze, temporal ramps, common-mode and zone-coherent changes, DO4 floor behavior and dropout are negative/orthogonality controls. The swap detection metrics pass, but localization remains below the release criterion and must not be hidden by threshold tuning.

## 6. Topology and D6 interface

- Declared topology contains 14 DO/ORP nodes, 10 longitudinal edges and seven parallel peer pairs.
- 5 finite candidate mappings exceed the report-only topology drift review threshold. These are hypotheses for field review, not automatic topology updates.
- Shadow V2 has `production_impact=none`; it cannot mutate `topology.yaml`, active templates, `D7_total` or Veto.
- `D7_total` non-null rows: 0; D6 interface evaluable rows: 0.
- D6 protected score columns are untouched because D7 has no D6 write path.

## 7. Figure review

Five multi-panel figure groups are available as SVG, PDF, 600 dpi PNG and LZW-compressed 600 dpi TIFF, backed by `D7_plot_data.parquet/.csv`. All use Arial, 0.8 pt boxed axes, inward ticks, `(a)/(b)/(c)` panel labels, endpoint-aware scales and transparent label backgrounds where annotations cover data. Figure D7-3 decomposes weighted leave-one-out structural attribution; it does not claim Shapley values. Automated counterpart/font/pixel QA passed: True.

## 8. Critical limitations

1. Research topology is author-confirmed and inventory-reconciled, but production documentary audit, maintenance provenance and dual approval remain incomplete.
2. Effective independent support remains inadequate for production gating: L1=48, L2=8, L3=0; ORP remains intentionally L1.
3. Swap Top-1 localization is 0.700 (95% CI 0.575-0.801) versus the 0.80 target.
4. The 529 candidate event windows have no external truth labels; event counts must not be reported as confirmed sensor faults.
5. Regime transition FAR and topology candidate recall are not estimable without external regime/topology truth.
6. `D7_raw` calibration is suitable for comparative research evidence, but operational event thresholds require labeled prospective confirmation.

## 9. Release decision and next actions

The branch may be reviewed and merged as a **research implementation with explicit production gates**. It must not be activated in WW-DQS/DQR arbitration yet.

1. Obtain maintenance, replacement and remapping records for the study interval and reconcile exceptions against the confirmed channel-position mapping.
2. Complete the production documentary audit and obtain independent reviewer and approver signatures; then update `topology.yaml` and regenerate all topology-bound templates.
3. Accumulate qualified multi-season effective blocks and pass ORP/DO support exit criteria.
4. Improve and revalidate node localization to Top-1 >=0.80 on blocked holdouts.
5. Add field-confirmed swap/maintenance/topology cases and prospective event labels.
6. Only then set topology status to verified, rerun the full release workflow and consider `D7_total`/D6 final arbitration.

The required human evidence and role-separated approval procedure are specified
in `docs/D7_FIELD_VERIFICATION_REQUIREMENTS.md`. These inputs cannot be
generated from statistical similarity.
