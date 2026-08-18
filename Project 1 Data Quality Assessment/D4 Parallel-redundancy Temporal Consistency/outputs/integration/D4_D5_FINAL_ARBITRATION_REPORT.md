# D4-D5 Final Arbitration Report

Generated: 2026-08-18T03:36:07.983869+00:00

## Decision

D4 is finalized non-destructively from `D4_raw`. D1 is retained as explanatory
sensor-health context and never changes the D4 numeric dimension. The D5 report
interface provides scientific structural scores, while the separate gate
interface provides process-coherence Guard, node/zone attribution and
sensor-identity Veto only when the corresponding validation claim has passed.

## Current release

- Input rows: 42,847
- Core pre-integration `D4_forDQR` non-null rows: 0 (intentional placeholder; not the published integration output)
- Integration-finalized `D4_forDQR` rows: 42,371
- D5 report-context-ready pair-hours: 19,803
- D5 gate/action-ready pair-hours: 0
- D4 sensor-gate-applicable rows: 0
- Process-coherence Guard rows: 0
- Sensor-specific Veto rows: 0
- Maximum absolute numeric adjustment: 0

## Integration states

- `final_independent_D5_limited`: 23,044 rows
- `final_with_D5_report_context`: 19,803 rows

## Interpretation boundary

Missing D5 evidence does not erase or reduce D4. Process-coherent D5 evidence
may suppress sensor-fault attribution while preserving the D4 temporal
consistency score and remains explicitly distinct from Veto. Sensor-specific
hard Veto is unavailable unless the
localization claim passes its prespecified threshold. Production automation
still requires documentary governance and is separate from retrospective
scientific aggregation.

The zero-valued core pre-integration field and the finalized integration field
are different lifecycle stages. The former is deliberately withheld inside the
independent D4 core; the latter is generated non-destructively from `D4_raw` by
this integration layer.
