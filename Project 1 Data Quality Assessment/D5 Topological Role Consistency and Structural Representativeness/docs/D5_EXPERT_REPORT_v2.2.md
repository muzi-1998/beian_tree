# D5 Expert Review Report v2.2

**Project:** Topological Role Consistency and Structural Representativeness
**Run:** `D5-LOCAL-20260726T051805Z`
**Generated:** 2026-07-26 13:27 CST
**Decision:** Scientific D5 score released for final subscore aggregation; automated deployment remains gated.

## 1. Executive verdict

The D5 v2.2 implementation is complete as a regime-conditioned ordinal spatial-structure assessment. Local, Sensitivity and Shadow V2 tracks, frozen templates, hourly scores, validation-graded admission, plot data, SCI-ready figures, manifests and audit records are present. The Local Track remains logically independent of D1, D2, D3 and D4 and consumes only canonical observations, exogenous hydraulic/time context and declared D5 topology.

The ordinal research topology is confirmed: process line, pool zone, longitudinal order, SCADA-to-physical-point identity and the absence of study-period probe/channel changes are author-confirmed; the installation register independently reconciles eight active DO and six active ORP instruments. Exact coordinates, asset IDs and maintenance records are not model inputs and therefore do not suppress retrospective scientific scores. They remain deployment-governance limitations. Current support comprises 14 L1, 34 L2 and 8 L3 templates. `D5_total` contains 39,648 rows and `D5_forDQR` contains 39,648 rows. Swap Top-1 is 0.70 (95% CI 0.57-0.80, n=60), so node-specific hard Veto remains disabled without blocking the score.

## 2. Scope and dimensional independence

- D5 asks whether a DO/ORP observation still behaves like its declared spatial position and represents its process zone.
- D1 evaluates sensor-intrinsic health and long-term regime-relative behavior; D2 evaluates continuity and information availability; D3 evaluates physical value/rate plausibility; D4 evaluates temporal synchronization between parallel counterparts.
- Local D5 does not consume any D1-D4 score, state or event field. D1/D2/D3 are read only in the physically isolated Sensitivity Track.
- QR/QIR are exogenous context variables only and never receive a D5 score.
- One plant-global regime is inferred from QR/QIR, robust pooled DO/ORP level
  and dispersion, and cyclic time features. Every sensor is then compared with
  its role-specific template under the same active regime.
- Observed low `D5_raw` is structural evidence, not a confirmed hardware fault.

## 3. Data and result freshness

- Hourly sensor windows: 86,016, spanning 2025-08-01 00:00:00 to 2026-04-13 23:00:00.
- Calculable `D5_raw`: 85,092; mean 3.097, median 3.114, p05 1.345.
- Raw low-score fraction (`D5_raw < 3`): 46.0%; candidate persistent events: 529.
- Full 10-min regime-state trajectory retained; OOD hold rate: 15.5%; confirmed switches: 1246.
- Result provenance is bound to canonical input hashes, topology hash, template/mapping/regime versions and code commit in `D5_run_manifest.json`.
- Sensitivity inputs are bound to frozen D1 release `D1REL-1.3.0-f6074be3751f` and exact D2/D3/Local artifact hashes in `D5_sensitivity_manifest.json`.
- The isolated Sensitivity Track remains `pending_not_produced` by design; authoritative `D5_forDQR` is produced only by Local admission.

## 4. Applicability and support

- `evaluable`: 39,648 (46.1%)
- `limited_support`: 32,102 (37.3%)
- `out_of_template`: 13,342 (15.5%)
- `not_evaluable`: 924 (1.1%)

- `L2`: 34 templates
- `L1`: 14 templates
- `L3`: 8 templates

ORP uses a conservative `diagonal_robust_z` model with `alpha=1.00`, but model complexity is separated from evidence maturity. L2 requires sufficient effective blocks and month coverage and is admitted for scientific scoring with explicit support metadata; its maximum leave-one-month-out profile FAR is 0.500. L3 additionally requires daily-block bootstrap stability, at least three blocked monthly holdouts and holdout FAR <=0.10; the observed L3 maximum is 0.066. Thus L2 evidence is not described as action-grade or cross-month deployment validated. L0 remains disabled rather than being written as a low score.

L1 is diagnostic only. L2 and L3 may populate `D5_total` and `D5_forDQR` under
the confirmed ordinal topology. Only validation-graded L3 may activate
claim-specific Veto. Deployment approval is reported separately and does not
alter the retrospective score. Current provisional report rows:
39,648; research report rows:
39,648.

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

## 6. Topology and D4 interface

- Declared topology contains 14 DO/ORP nodes, 10 longitudinal edges and seven parallel peer pairs.
- 5 finite candidate mappings exceed the report-only topology drift review threshold. These are hypotheses for field review, not automatic topology updates.
- Shadow V2 has `production_impact=none`; it cannot mutate `topology.yaml`, active templates, `D5_total` or Veto.
- `D5_total` non-null rows: 39648; `D5_forDQR` rows: 39648; D4 interface evaluable rows: 19824.
- Process-coherence protection is active for 66 pair-hours; sensor-specific hard Veto is active for 0 pair-hours.
- D4 `D4_raw` and `D4_after_D1` remain unchanged. D5 changes only gate applicability and causal attribution in the separate final-arbitration artifact.

## 7. Figure review

Five multi-panel figure groups are available as SVG, PDF, 600 dpi PNG and LZW-compressed 600 dpi TIFF, backed by `D5_plot_data.parquet/.csv`. All use Arial, 0.8 pt boxed axes, inward ticks, `(a)/(b)/(c)` panel labels, endpoint-aware scales and transparent label backgrounds where annotations cover data. Figure D5-3 decomposes weighted leave-one-out structural attribution; it does not claim Shapley values. Automated counterpart/font/pixel QA passed: True.

## 8. Critical limitations

1. Research topology is author-confirmed and inventory-reconciled, but production documentary audit, maintenance provenance and dual approval remain incomplete.
2. Effective support is validation graded: L1=14, L2=34, L3=8; L1 regimes remain diagnostic and unavailable for action.
3. Swap Top-1 localization is 0.700 (95% CI 0.575-0.801) versus the 0.80 target.
4. The 529 candidate event windows have no external truth labels; event counts must not be reported as confirmed sensor faults.
5. Regime transition FAR and topology candidate recall are not estimable without external regime/topology truth.
6. `D5_raw` calibration is suitable for comparative research evidence, but operational event thresholds require labeled prospective confirmation.

## 9. Release decision and next actions

The branch may enter final WW-DQS subscore aggregation as a **scientific implementation with claim-specific action gates**. Automated control deployment remains outside the present evidence scope.

1. Use `D5_total` and `D5_forDQR` only where score eligibility is explicit; renormalize missing dimensions rather than substituting a low score.
2. Use process-coherence protection only for persistent validation-graded L3 evidence.
3. Keep sensor-specific hard Veto disabled until blocked localization reaches Top-1 >=0.80.
4. Complete D4-D5 conditional dependence and ablation analysis before fixing final WW-DQS weights.
5. Add field-confirmed topology and event cases as external validation when they become available.
6. Complete documentary audit and dual approval before any automated plant-control deployment.

The deployment evidence and role-separated approval procedure remain specified
in `docs/D5_FIELD_VERIFICATION_REQUIREMENTS.md`; they are not prerequisites for
retrospective scientific aggregation.
