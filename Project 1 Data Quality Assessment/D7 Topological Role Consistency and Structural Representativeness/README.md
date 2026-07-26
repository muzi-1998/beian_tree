# D7 Topological Role Consistency and Structural Representativeness

D7 evaluates whether each DO/ORP observation still behaves like the declared
spatial position and whether it remains structurally representative of its
process zone. The production `d7_local` track consumes only canonical raw
observations, exogenous hydraulic context, frozen D7 templates, and versioned
topology metadata. It never consumes D1-D6 scores or states.

## Scientific boundary

- D7 does not diagnose a hardware fault type.
- Missing evidence is `NaN` with an explicit status, never a low score.
- D7 does not repeat D4 value/rate rules, D5 dynamic prediction, or D6 paired
  temporal-distribution scoring.
- Sensitivity outputs are physically separated and cannot create production
  scores or the D6 interface.
- Process line, pool zone, longitudinal order, SCADA-to-physical-point identity
  and no study-period probe/channel change are author-confirmed. A provided
  installation register reconciles eight active DO and six active ORP
  instruments. Eligible L2/L3 windows may therefore populate `D7_report`,
  `D7_total` and `D7_forDQR`.
- Maintenance provenance, production documentary audit and dual approval remain
  pending. These items limit automated deployment and confirmatory
  maintenance-cause claims; they do not suppress retrospective scientific
  scores.
- The Local regime model is plant-global: QR/QIR, robust pooled DO/ORP level
  and dispersion, and cyclic time features define one shared process context.
  Gradient, rank and leave-one-out evidence are learned and evaluated within
  that shared regime.
- L1 is diagnostic; L2 supports scientific scoring; L3 supports process-level
  protection after detection and negative-control validation. Sensor-specific
  hard Veto additionally requires localization validation. Automated deployment
  remains separately approval-gated.
- D6 finalizes non-destructively from `D6_after_D1`. D7 contributes score
  applicability, process protection and causal attribution without rewriting
  the D6 numeric score.

See `configs/common/topology_evidence.yaml` for the research evidence ledger and
`docs/D7_FIELD_VERIFICATION_REQUIREMENTS.md` for the production documentary and
two-person approval gate. Statistical topology candidates cannot replace it.

## Reproduce

Run the complete release from `Project 1 Data Quality Assessment`:

```powershell
python ".\D7 Topological Role Consistency and Structural Representativeness\scripts\run_d7_release.py"
python -m pytest ".\D7 Topological Role Consistency and Structural Representativeness\tests" -q
```

The report and directory guide are generated from the current manifest and
artifact inventory. Every project rerun updates both documents.
