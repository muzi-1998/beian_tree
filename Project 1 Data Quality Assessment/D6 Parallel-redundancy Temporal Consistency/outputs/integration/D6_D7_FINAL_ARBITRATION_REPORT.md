# D6-D7 Final Arbitration Report

Generated: 2026-07-26T05:28:05.426060+00:00

## Decision

D6 is finalized non-destructively from `D6_after_D1`. D7 does not modify the
numeric D6 score. It determines whether sensor-fault gating is applicable,
provides node/zone attribution, and can activate claim-specific process
protection or sensor-identity Veto only when the corresponding validation claim
has passed.

## Current release

- Input rows: 42,847
- Finalized `D6_forDQR` rows: 37,975
- D7 score-ready rows: 19,803
- D6 sensor-gate-applicable rows: 18,310
- Process-protection rows: 66
- Sensor-specific Veto rows: 0
- Maximum absolute numeric adjustment: 0

## Integration states

- `final_independent_D7_limited`: 23,044 rows
- `final_process_coherence_protected`: 66 rows
- `final_with_D7_context`: 19,737 rows

## Interpretation boundary

Missing D7 evidence does not erase or reduce D6. Process-coherent D7 evidence
may suspend sensor-fault attribution while preserving the D6 temporal
consistency score. Sensor-specific hard Veto is unavailable unless the
localization claim passes its prespecified threshold. Production automation
still requires documentary governance and is separate from retrospective
scientific aggregation.
