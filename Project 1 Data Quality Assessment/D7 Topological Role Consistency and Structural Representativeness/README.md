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
- The current declared topology awaits field drawing, asset, coordinate, and
  dual-approval verification. Current results are therefore report-only:
  `D7_raw` is available, while `D7_total` and final D6 arbitration remain empty.

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

The manuscript figures follow `docs/D7_FIGURE_CONTRACT_v2.2.md` and are exported
at 183 mm width as editable SVG/PDF plus 600 dpi PNG/TIFF. Figure source data are
complete frozen plot-data records; no rendering-convenience sample is used.
