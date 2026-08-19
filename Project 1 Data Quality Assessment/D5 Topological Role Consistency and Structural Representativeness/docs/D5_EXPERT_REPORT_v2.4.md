# D5 Expert Review Report v2.4

**Project:** Topological Role Consistency and Structural Representativeness
**Run:** `D5-LOCAL-20260727T034533Z`
**Generated:** 2026-08-18 18:58 CST
**Decision:** Scientific D5 score released for final subscore aggregation; automated deployment remains gated.

## 1. Executive verdict

The D5 v2.4 release retains the frozen v2.3 scoring implementation and adds publication-grade validation, coverage, complementarity and target-influence audits. Local, Sensitivity and Shadow V2 tracks, frozen templates, hourly scores, validation-graded admission, dual report/gate interfaces, plot data, SCI-ready figures, manifests and audit records are present. The Local Track remains logically independent of D1, D2, D3 and D4 and consumes only canonical observations, exogenous hydraulic/time context and declared D5 topology.

The ordinal research topology is confirmed: process line, pool zone, longitudinal order, SCADA-to-physical-point identity and the absence of study-period probe/channel changes are author-confirmed; the installation register independently reconciles eight active DO and six active ORP instruments. Exact coordinates, asset IDs and maintenance records are not model inputs and therefore do not suppress retrospective scientific scores. They remain deployment-governance limitations. Family-level support identifies 8 L3 candidates, but node-specific blocked validation retains only 3 final L3 templates; the current effective distribution is L1=14, L2=39 and L3=3. `D5_report_score` contains 39,648 rows. Controlled-perturbation swap Top-1 is 0.70 (95% CI 0.57-0.80, n=60), so node-specific hard Veto remains disabled without blocking the score.

## 2. Scope and dimensional independence

- D5 asks whether a DO/ORP observation still behaves like its declared spatial position and represents its process zone.
- D1 evaluates sensor-intrinsic health and long-term regime-relative behavior; D2 evaluates continuity and information availability; D3 evaluates physical value/rate plausibility; D4 evaluates temporal synchronization between parallel counterparts.
- Local D5 does not consume any D1-D4 score, state or event field. D1/D2/D3 are read only in the physically isolated Sensitivity Track.
- QR/QIR are exogenous context variables only and never receive a D5 score.
- One plant-global regime is inferred from QR/QIR, robust pooled DO/ORP level
  and dispersion, and cyclic time features. Every sensor is then compared with
  its role-specific template under the same active regime.
- The pooled context includes each target with bounded median/dispersion influence. Strict target exclusion is a sensitivity challenge, not a production-model claim.
- Observed low `D5_raw` is structural evidence, not a confirmed hardware fault.

## 3. Data and result freshness

- Hourly sensor windows: 86,016, spanning 2025-08-01 00:00:00 to 2026-04-13 23:00:00.
- Calculable `D5_raw`: 85,092; mean 3.097, median 3.114, p05 1.345.
- Raw low-score fraction (`D5_raw < 3`): 46.0%; candidate persistent events: 529.
- Full 10-min regime-state trajectory retained; OOD hold rate: 15.5%; confirmed switches: 1246.
- Result provenance is bound to canonical input hashes, topology hash, template/mapping/regime versions and code commit in `D5_run_manifest.json`.
- Sensitivity inputs are bound to frozen D1 release `D1REL-1.3.0-cb06fed4b63a` and exact D2/D3/Local artifact hashes in `D5_sensitivity_manifest.json`.
- The isolated Sensitivity Track remains `pending_not_produced` by design; it cannot write either authoritative report scores or gate decisions.

## 4. Applicability and support

- `evaluable`: 39,648 (46.1%)
- `limited_support`: 32,102 (37.3%)
- `out_of_template`: 13,342 (15.5%)
- `not_evaluable`: 924 (1.1%)

- `L2`: 39 templates
- `L1`: 14 templates
- `L3`: 3 templates

ORP uses a conservative `diagonal_robust_z` model with `alpha=1.00`, but model complexity is separated from evidence maturity. Family support is shared once by analyte, regime and model family without multiplying the effective sample by the number of sensors. Every target-specific reconstruction then undergoes its own coverage, residual-scale bootstrap and leave-one-month-out FAR validation. Final support is the lower of family and node maturity. L2 evidence remains valid for scientific scoring but is not described as action-grade or cross-month deployment validated. L0 remains disabled rather than being written as a low score.

L1 is diagnostic only. L2 and L3 may populate `D5_total` and the sensor-hour
`D5_report_interface` under the confirmed ordinal topology. Only final L3
nodes may enter the pair-hour `D5_gate_interface`. Process coherence is an
attribution Guard rather than a Veto; only validated sensor-identity evidence
may activate hard Veto. Deployment approval is reported separately and does
not alter the retrospective score. Current provisional report rows:
39,648; research report rows:
39,648.

## 5. Validation and sensitivity

| Criterion | Estimate | Target | Result |
|---|---:|---:|---|
| Controlled swap discrimination AUROC | 0.912 | >=0.90 | Pass |
| Controlled swap discrimination AUPRC | 0.870 | >=0.80 | Pass |
| Controlled perturbation Top-1 localization | 0.700 [0.575, 0.801], n=60 | >=0.80 | **Fail** |
| Common-mode FAR | 0.046 | <=0.10 | Pass |
| Zone-coherent FAR | 0.057 | <=0.10 | Pass |
| Switch chatter rate | 0.000 | <=0.05 | Pass |
| IE_track | 0.048 | <=0.20 | Pass |
| Event Jaccard | 0.825 | >=0.80 | Pass |
| Culprit Spearman rho | 0.962 | >=0.80 | Pass |

Validation uses observed test-period spatial windows with frozen templates. Same-line, same-analyte position swaps are positive controls. Freeze, temporal ramps, common-mode and zone-coherent changes, DO4 floor behavior and dropout are negative/orthogonality controls. The swap detection metrics pass, but localization remains below the release criterion and must not be hidden by threshold tuning.

The publication audit additionally reports six future-month controlled-challenge refits (discrimination AUROC 0.967, AUPRC 0.974, controlled-perturbation Top-1 localization 0.767), Top-2/MRR localization, synchronized 7-d D4-D5 dependence under report-score and raw-calculable overlap, target-influence sensitivity, monthly support migration and dimension-availability sensitivity. Current D4-D5 Spearman rho is 0.119 for report scores and 0.171 for raw-calculable scores; the proportions of descriptive strata with |rho| below 0.30 are 94.7% and 86.4%, respectively. These are controlled observed-window challenges, not field fault-detection or localization accuracy. Confidence-risk coverage is not monotonic; the current confidence field remains evidence metadata and is not a calibrated hard-Veto gate.

## 6. Topology and D4 interface

- Declared topology contains 14 DO/ORP nodes, 10 longitudinal edges and seven parallel peer pairs.
- 5 finite candidate mappings exceed the report-only topology drift review threshold. These are hypotheses for field review, not automatic topology updates.
- Shadow V2 has `production_impact=none`; it cannot mutate `topology.yaml`, active templates, `D5_total` or Veto.
- `D5_total` and report-interface rows: 39648; D5 pair-interface evaluable rows: 19824.
- Process-coherence Guard is active for 0 pair-hours; sensor-specific hard Veto is active for 0 pair-hours.
- The final D4 numeric source is `D4_raw`. D1 is interpretation-only, while D5 supplies report context, attribution Guard and validated sensor-identity decisions.

## 7. Figure review

Nine multi-panel figure groups are available as editable SVG/PDF, 600 dpi PNG and LZW-compressed 600 dpi TIFF on a fixed 183 mm canvas. All use Arial and 0.8 pt axes; open plots use outward ticks, whereas genuinely full-boxed maps use inward ticks. Panel labels, annotation backgrounds and endpoint-aware scales follow one shared style contract. Figures D5-1-D5-3 now connect declared topology, score applicability and case-level evidence; Figure D5-6 reports criterion margins, localization and evidence coverage; Figure D5-7 reports joint density, stratified D4-D5 overlap and exact low-tail concordance; Figure D5-8 separates availability-aware, matched complete-case and fixed-dimension estimands; Figure D5-9 reports post-reference target influence and the full reference-fraction support grid. Automated export/layout QA passed: True.

## 8. Critical limitations

1. Research topology is author-confirmed and inventory-reconciled, but production documentary audit, maintenance provenance and dual approval remain incomplete.
2. Family-level L3 support does not imply node-level action validity: 8 family-L3 candidates reduce to 3 final node-L3 templates after blocked validation.
3. Controlled-perturbation swap Top-1 localization is 0.700 (95% CI 0.575-0.801) versus the 0.80 target.
4. The 529 candidate event windows have no external truth labels; event counts must not be reported as confirmed sensor faults.
5. Regime transition FAR and topology candidate recall are not estimable without external regime/topology truth.
6. `D5_raw` calibration is suitable for comparative research evidence, but operational event thresholds require labeled prospective confirmation.

## 9. Release decision and next actions

The branch may enter final WW-DQS subscore aggregation as a **scientific implementation with claim-specific action gates**. Automated control deployment remains outside the present evidence scope.

1. Use `D5_report_score` only where report eligibility is explicit; renormalize missing dimensions rather than substituting a low score.
2. Use the separate gate interface only for final L3 nodes and treat process coherence as an attribution Guard, never as Veto.
3. Keep sensor-specific hard Veto disabled until controlled blocked localization reaches Top-1 >=0.80.
4. Report availability-aware and fixed-dimension complete-evidence WW-DQS separately; never interpret a dimension-availability shift as a quality trend.
5. Cross-dimensional manuscript values are frozen only while the exact D4 run, calibration and SHA-256 remain current; any D4 change requires a full audit rerun.
6. Add field-confirmed topology and event cases as external validation when they become available.
7. Complete documentary audit and dual approval before any automated plant-control deployment.

The deployment evidence and role-separated approval procedure remain specified
in `docs/D5_FIELD_VERIFICATION_REQUIREMENTS.md`; they are not prerequisites for
retrospective scientific aggregation.
