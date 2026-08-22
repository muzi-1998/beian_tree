# D5 Topological Role Consistency and Structural Representativeness

D5 evaluates whether each DO/ORP observation still behaves like the declared
spatial position and whether it remains structurally representative of its
process zone. The production `d5_local` track consumes only canonical raw
observations, exogenous hydraulic context, frozen D5 templates, and versioned
topology metadata. It never consumes D1-D4 scores or states.

## Scientific boundary

- D5 does not diagnose a hardware fault type.
- Missing evidence is `NaN` with an explicit status, never a low score.
- D5 does not repeat D1 sensor-state detection, D3 value/rate rules, or D4
  paired temporal-distribution scoring. The non-selected legacy
  dynamic-prediction module is outside the final five-dimension contract.
- Sensitivity outputs are physically separated and cannot create production
  scores or the D4 interface.
- Process line, pool zone, longitudinal order, SCADA-to-physical-point identity
  and no study-period probe/channel change are author-confirmed. A provided
  installation register reconciles eight active DO and six active ORP
  instruments. Eligible L2/L3 windows may therefore populate `D5_report`,
  `D5_total` and the sensor-hour `D5_report_interface`.
- The register independently verifies inventory count, in-service status,
  brand, range and signal type, but it does not contain per-instrument asset
  identity or explicit line/zone/order/SCADA mapping. Those mappings remain
  author-confirmed research inputs pending documentary audit.
- Maintenance provenance, production documentary audit and dual approval remain
  pending. These items limit automated deployment and confirmatory
  maintenance-cause claims; they do not suppress retrospective scientific
  scores.
- The Local regime model is plant-global: QR/QIR, robust pooled DO/ORP level
  and dispersion, and cyclic time features define one shared process context.
  Gradient, rank and leave-one-out evidence are learned and evaluated within
  that shared regime. Each target has bounded influence on pooled context;
  strict target exclusion is a publication sensitivity challenge, not a
  production-model claim.
- Family-level samples may support an analyte-regime-model family, but every
  node still requires its own blocked-temporal validation. L1 is diagnostic;
  L2 supports scientific scoring; only final node L3 can enter the pair-hour
  action gate.
- The process-coherence mechanism is an attribution Guard, not a Veto.
  Sensor-specific hard Veto additionally requires localization validation.
  Automated deployment remains separately approval-gated.
- D5 exports separate report and gate interfaces. D4 finalizes
  non-destructively from `D4_raw`; D1 and D5 provide interpretation and action
  governance without rewriting the D4 numeric score.
- D4-D5 non-redundancy is audited under two estimands: formal
  `D5_report_score` overlap and extended two-node `D5_raw` calculable overlap,
  with analyte, regime, month and pair strata. Two independent 7 d blocks admit
  a descriptive point estimate; at least six are required for a bootstrap CI.
  Every D4-dependent artifact carries source run, calibration and SHA-256
  provenance, and manuscript values freeze only after exact freshness matching.
- Availability-aware and fixed-dimension complete-evidence WW-DQS summaries
  are separate estimands. Dimension count and coverage must accompany every
  temporal composite; missing D5 evidence is never encoded as low quality.

See `configs/common/topology_evidence.yaml` for the research evidence ledger and
`docs/D5_FIELD_VERIFICATION_REQUIREMENTS.md` for the production documentary and
two-person approval gate. The frozen publication claim contract is
`configs/publication/d5_final_contract.yaml`; its audits and source data are in
`outputs/publication/`. Statistical topology candidates cannot replace these
contracts.

## Reproduce

Run the complete release from `Project 1 Data Quality Assessment`:

```powershell
python ".\D5 Topological Role Consistency and Structural Representativeness\scripts\run_d5_release.py"
python ".\D5 Topological Role Consistency and Structural Representativeness\scripts\run_d5_publication_audit.py"
python ".\D5 Topological Role Consistency and Structural Representativeness\scripts\run_d5_support_migration_audit.py"
python ".\D5 Topological Role Consistency and Structural Representativeness\scripts\verify_d5_support_migration_audit.py"
python ".\D5 Topological Role Consistency and Structural Representativeness\scripts\verify_d5_publication_bundle.py"
python -m pytest ".\D5 Topological Role Consistency and Structural Representativeness\tests" -q
```

The report and directory guide are generated from the current manifest and
artifact inventory. Every project rerun updates both documents.

## Figure bundle

The current nine-figure bundle follows a fixed 183 mm Nature-style contract.
Figures 1-3 provide topology, applicability and case-level evidence; Figures 6-7
carry the principal validation and D4-D5 complementarity claims. Figures 4, 5
and 9 are detailed Extended Data/Supplementary analyses. Figure 8 is an
integrated-WW-DQS prototype and must not be described as the final five-
dimension composite. All quantitative panels have frozen source-data outputs,
and `outputs/figures/D5_figure_qa.json` records export and layout checks.

The supplementary support-migration audit explains the late-period D5
availability shift without modifying frozen scores. It separates L1-to-L2
reference-support blockers from L2-to-L3 stability/FAR constraints and writes
source tables, diagnostic counterfactuals, four publication figures and a
SHA-256 manifest under `outputs/audit/support_migration/`. Support-attributable,
OOD and incomplete-evidence losses are mutually exclusive; reference-fraction
results are explicitly labelled as occupied-day upper bounds unless templates
and validation are fully rebuilt.
