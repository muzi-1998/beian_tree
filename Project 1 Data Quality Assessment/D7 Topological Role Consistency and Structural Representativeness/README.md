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
  instruments. Eligible L2 windows may therefore populate paper-facing
  `D7_report`.
- Maintenance provenance, production documentary audit and dual approval remain
  pending. `D7_total`, Veto, `D7_forDQR` and final D6 arbitration remain empty.
- The Local regime model is plant-global: QR/QIR, robust pooled DO/ORP level
  and dispersion, and cyclic time features define one shared process context.
  Gradient, rank and leave-one-out evidence are learned and evaluated within
  that shared regime.
- L1 is diagnostic, L2 can support research reporting, and only
  production-approved L3 evidence can enter DQR gating or Veto.

See `configs/common/topology_evidence.yaml` for the research evidence ledger and
`docs/D7_FIELD_VERIFICATION_REQUIREMENTS.md` for the production documentary and
two-person approval gate. Statistical topology candidates cannot replace it.

## Reproduce

Run from `Project 1 Data Quality Assessment`:

```powershell
python ".\D7 Topological Role Consistency and Structural Representativeness\scripts\run_d7_local.py"
python ".\D7 Topological Role Consistency and Structural Representativeness\scripts\run_d7_sensitivity.py"
python ".\D7 Topological Role Consistency and Structural Representativeness\scripts\run_d7_validation.py"
python ".\D7 Topological Role Consistency and Structural Representativeness\scripts\make_d7_figures.py"
python ".\D7 Topological Role Consistency and Structural Representativeness\scripts\build_d7_reports.py"
python ".\D7 Topological Role Consistency and Structural Representativeness\scripts\check_d7_release.py"
python -m pytest ".\D7 Topological Role Consistency and Structural Representativeness\tests" -q
```

The report and directory guide are generated from the current manifest and
artifact inventory. Every project rerun updates both documents.
