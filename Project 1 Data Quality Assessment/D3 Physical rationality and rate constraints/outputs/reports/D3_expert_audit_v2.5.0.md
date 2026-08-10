# D3 v2.5.0 Expert Audit

## Decision

D3 v2.5.0 replaces the provisional fixed 8 mg/L aerobic DO upper warning with a time-blocked, temperature-conditioned operational envelope. The method is suitable for retrospective D3 gate aggregation under the stated scope: positions 1-2 are scored soft warnings, position 3 is diagnostic-only, and DO4 remains an independent post-anoxic route. The envelope is not a thermodynamic saturation limit or an instrument-failure Veto.

## Frozen Run

- Run ID: `RUN_D3_v2.5.0_20260810T070618Z_1ca914b0`.
- Study interval: 2025-08-01 00:00 to 2026-04-13 23:59 at 1 min.
- Sensor-windows: 43,008; evaluated: 42,840; not evaluated: 168.
- Gate outcome: Pass 34,590; Warn 8,250; Fail 0; NotEvaluated 168.
- D3 total: mean 4.855; median 5.000; minimum 1.675.
- Publication figures: 10; Nature bundle audit: 0 failures, 0 warnings.

## Temperature Source Contract

- Source interval: 2025-08-01 00:00 to 2026-07-30 23:59 at 1 min.
- Rows: 524,160; timestamp duplicates: 0; out-of-order rows: 0.
- Raw missing temperature: 4,205 min; invalid range values: 8 min, all equal to -4.0 °C.
- Invalid values are masked; no temporal interpolation or extrapolation is performed.
- D3 study-hour coverage after requiring at least 30 valid temperature minutes per hour: 99.01%.
- The covariate is influent temperature. It is a site-level process proxy, not an in-basin temperature, pressure, or salinity measurement.

## Frozen Calibration

The calibration period is 2025-08-01 through 2026-01-31. Validation is 2026-02-01 through 2026-03-31; 2026-04-01 through 2026-04-13 is the terminal test. Only hours with D1 total, spike, step, freeze, regime and D2 Strict scores at least 4.5 and an eligible D2 tag enter calibration.

Two parallel lines share one coefficient at each longitudinal position. The estimator is `max(P99, median + 3 x 1.4826 MAD)` of hourly mean DO divided by the freshwater reference saturation calculated from hourly median influent temperature.

| Position | Calibration sensor-hours | Frozen alpha | Registry reproduction |
|---|---:|---:|---|
| 1 | 1,137 | 0.2870480956 | Passed |
| 2 | 2,238 | 0.3146109551 | Passed |
| 3 | 2,547 | 0.4898265899 | Passed |

All coefficients reproduce from the frozen sources within `2.1e-11` absolute difference.

## Temporal Transfer Decision

- Positions 1 and 2: all sensors had 0% high-quality warning rate in the independent validation period. They are promoted as scored operational warnings.
- Position 1 terminal test: DO-2-1 had 1/90 high-quality hours above the envelope (1.11%); the other position-1 channel had none.
- Position 2 terminal test: no high-quality exceedance occurred.
- Position 3: DO-2-3 had 10.50% high-quality warning rate in validation and 2.86% in the terminal test. This exceeds the prespecified 2% promotion criterion, indicating unresolved line-specific aeration/load structure. Position 3 is therefore diagnostic-only and cannot lower D3 through the temperature upper component.

This asymmetric promotion is deliberate. Applying one unconditional position-3 upper envelope would convert real process-state differences into apparent data-quality loss.

## Production Semantics

- Production scoring reads minute DO/ORP, minute influent temperature, and frozen coefficients only.
- D1/D2 scores are prohibited production inputs and are used only to audit calibration-window quality.
- A missing/invalid temperature minute produces unevaluated upper-envelope evidence, not a pass and not a penalty.
- `soft_high_violation_rate_evaluable` uses only minutes with both observed DO and valid temperature.
- Position-3 exceedances remain visible in `D3_value_evidence.xlsx` and the temperature audit parquet while `soft_high_scored=False`.
- DO4 retains physical zero, zero-equivalence, offset-warning, and severe-negative states and never inherits the aerobic envelope.

## Publication Outputs

- `D3_temperature_conditioned_DO_upper.xlsx`: source QA, registry reproduction, phase validation, alpha sensitivity, and exclusions.
- `D3_temperature_conditioned_DO_upper.parquet`: complete hourly source data for figure reproduction.
- `fig10_temperature_conditioned_do_upper`: editable SVG/PDF plus 600 dpi PNG/TIFF.

The defensible paper claim is that a full-period process-temperature proxy supports auditable, time-blocked operational envelopes at selected aerobic positions while exposing where a temperature-only model fails to transfer. The failed position-3 promotion is retained as a scientific boundary, not hidden through sensor-specific self-normalization.

## Remaining Limitations

- In-basin temperature, atmospheric pressure, salinity, airflow, DO setpoints and maintenance labels are unavailable.
- The position-1 terminal estimate has limited high-quality support and should be interpreted with its binomial interval.
- Position 3 requires regime or aeration context before any scored upper envelope can be considered.
- Cross-plant transfer and event-level expert adjudication remain pending.
