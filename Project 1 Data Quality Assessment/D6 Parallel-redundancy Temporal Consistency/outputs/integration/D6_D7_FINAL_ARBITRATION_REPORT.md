# D6-D7 Final Arbitration Report

Generated: 2026-07-26T08:06:14.030957+00:00

## Decision

D6 is finalized non-destructively from `D6_raw`. D1 is retained as explanatory
sensor-health context and never changes the D6 numeric dimension. The D7 report
interface provides scientific structural scores, while the separate gate
interface provides process-coherence Guard, node/zone attribution and
sensor-identity Veto only when the corresponding validation claim has passed.

## Current release

- Input rows: 42,847
- Finalized `D6_forDQR` rows: 37,987
- D7 score-ready rows: 0
- D6 sensor-gate-applicable rows: 0
- Process-coherence Guard rows: 0
- Sensor-specific Veto rows: 0
- Maximum absolute numeric adjustment: 0

## Integration states

- `final_independent_D7_limited`: 23,044 rows
- `final_with_D7_report_context`: 19,803 rows

## Interpretation boundary

Missing D7 evidence does not erase or reduce D6. Process-coherent D7 evidence
may suppress sensor-fault attribution while preserving the D6 temporal
consistency score and remains explicitly distinct from Veto. Sensor-specific
hard Veto is unavailable unless the
localization claim passes its prespecified threshold. Production automation
still requires documentary governance and is separate from retrospective
scientific aggregation.
