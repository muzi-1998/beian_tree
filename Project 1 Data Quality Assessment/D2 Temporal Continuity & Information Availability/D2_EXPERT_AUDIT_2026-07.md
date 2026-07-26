# D2 Expert Audit (2026-07-22)

## Architecture Decision

D2 consumes the canonical 1-minute time base, raw observations and source audit
from **1.1 Decomposition**. D1 remains an external concordance layer: D1 events
may explain D2 events, but cannot fit D2 mappings, thresholds, Veto rules or the
D2 total score.

The two position-4 DO channels are post-anoxic process-floor measurements.
`DO_1_4` and `DO_2_4` therefore use an explicit `process_floor` availability
route; this is a semantic correction, not a global relaxation of D2 Veto.

## Current Verified State

- D2 run: `D2V1_20260722_1714`; calibration:
  `NorthBank_D2_v1_20260722`; mapping: `d2_v1_process_floor_r1`.
- Canonical horizon: 2025-08-01 00:00 to 2026-04-13 23:59
  (368,640 minutes); 6,121 hourly windows per sensor after 24 h warm-up.
- Q_TI/Q_GS use the configured 24 h main window. Q_FA now uses the configured
  6 h freeze window rather than inheriting the 24 h window.
- Gap events: 543; maximum gap: 565 min; interpolated runs never exceed 5 min.
- Process-floor production QFA uses only missing observations, long gaps and
  observed-value hard RLE >=15 min. Low IQR is diagnostic only.
- `floor_occupancy`, `resolution_limited`, `sensor_freeze` and
  `qfa_unavailable` are separately exported.
- response-loss is disabled for the post-anoxic route because no independent,
  same-process-position peer with demonstrably comparable excitation is
  available. Aerobic high-variance channels are not accepted as evidence of
  post-anoxic response loss.
- On standard routes, response-loss peers are restricted to the same variable
  and process position in the parallel treatment line. The former fallback to
  different positions within the same line has been removed.
- D1 linkage release: `D1REL-1.3.0-cb06fed4b63a`. The refreshed event table has
  9,354 rows: 8,957 D2-only, 387 subset, 7 overlap and 3 superset relations.
  Linked fraction is 397/9,354 (4.24%) and is descriptive only.
- D2 core-score SHA-256 remained
  `70a4a093f0900b090d49dbe8eda8a025e5eb840fce44a267f43636627029c08a`
  before and after the linkage refresh.
- Tests: production, contract, modular-scorer and process-floor regression
  18/18 passed.

## Process-Floor Findings

| Sensor | Floor occupancy | Resolution limited | Hard sensor freeze | QFA unavailable | Freeze-severe Veto | Total Veto | Mean Q_FA |
|---|---:|---:|---:|---:|---:|---:|---:|
| DO_1_4 | 96.09% | 57.81% | 0.012% | 0.385% | 0.310% | 0.931% | 4.978 |
| DO_2_4 | 69.89% | 16.88% | 0.254% | 0.625% | 0.621% | 1.242% | 4.965 |

DO_2_4 exhibits the same process-floor mechanism as DO_1_4, but at lower
occupancy and with somewhat more genuine hard-RLE evidence. Applying the same
route to both parallel position-4 sensors is topologically and scientifically
more defensible than treating only DO_1_4 as a special case.

All four controlled challenge classes pass: true low-oxygen floor, exact
digital lock, low-oxygen small fluctuations, and normal response after leaving
the floor. The challenge trajectories, summaries and observed-channel metrics
are exported in `D2_process_floor_validation.xlsx` and JSON.

## Scientific Interpretation

The previous 74.8% DO_1_4 Veto rate and 14.7% DO_2_4 Veto rate were dominated
by low-IQR evidence at a legitimate process floor. They were not defensible as
sensor-unavailability rates. The corrected Veto rates preserve missing/gap and
hard-lock evidence while preventing low DO concentration and finite numerical
resolution from being mislabeled as freeze failure.

This correction does not prove that the probes are perfectly healthy. It says
only that persistent low variability at the post-anoxic floor is insufficient
evidence of unavailability. Maintenance decisions still require independent
checks such as calibration records, cleaning response, redundant colocated
measurements or controlled process excitation.

The remaining Q_FA discrimination is concentrated in standard-route channels,
especially ORP. With the topology-qualified peer rule, ORP_2_2 and ORP_2_3
retain total Veto rates of 28.7% and 31.5%, respectively. About 97% of their
Veto hours include the standard-route `freeze_severe` reason, which is driven
mainly by low-IQR/RLE evidence; response-loss is an aggravating QFA diagnostic,
not the sole source of those Vetoes. These values are not confirmed sensor
faults: process-line asymmetry, legitimate ORP plateaus and unequal excitation
remain plausible. A manually reviewed, regime-stratified sample is required
before using either freeze or response-loss evidence for maintenance decisions.

## Figure Assessment

Fig. 5 now provides the central evidence chain: long-term evidence separation,
process-floor/resolution trajectories, 6 h production-QFA evidence and a
standard-route control. Its source data are exported separately. All D2 and
D1-D2 figures were regenerated from the current state as 600 dpi PNG previews
plus editable SVG/PDF masters. The plotting sources pass the Nature figure
preflight with no failures; vector masters are preferred over TIFF for these
line-art figures.

For a main manuscript, Figs. 1, 5, 7, 9 and 12 carry the strongest sequence.
Mapping, calibration and detailed event-concordance panels are better suited to
Methods or Supplementary Information.
