# D3 v2.6.0 Expert Audit

## Decision

D3 v2.6.0 resolves the calibration-production estimand mismatch and is suitable for retrospective D3 gate aggregation under the stated scope. Aerobic DO calibration, validation, terminal testing, and production now operate on the same minute-level `DO/Csat` evidence. Positions 1-2 remain scored operational-warning routes; position 3 remains diagnostic-only. The method does not claim a thermodynamic saturation limit or prove that DO-2-3 behavior is process-driven rather than sensor drift.

## Frozen Run

- Run ID: `RUN_D3_v2.6.0_20260811T014014Z_89fb1db3`.
- Study interval: 2025-08-01 00:00 to 2026-04-13 23:59 at 1 min.
- Sensor-windows: 43,008; evaluated: 42,840; not evaluated: 168.
- Gate outcome: Pass 34,566; Warn 8,274; Fail 0; NotEvaluated 168.
- D3 total: mean 4.85438; median 5.000; minimum 1.67461.
- Physical/rate events: 5,620.
- Relative to v2.5, the mean changed by -0.00052, Warn increased by 24 windows, and event count was unchanged. The denominator correction therefore has a small but directionally correct scoring effect.
- Publication figures: 10; figure bundle audit: 0 failures and 0 warnings.

## Temperature Source and Reference

- Source interval: 2025-08-01 00:00 to 2026-07-30 23:59 at 1 min.
- Rows: 524,160; timestamp duplicates: 0; out-of-order rows: 0.
- Raw missing temperature: 4,205 min; invalid-range values: 8 min, all masked.
- Study-grid valid minute coverage: 99.018%; hourly coverage with at least 30 valid min: 99.007%.
- No temporal interpolation or extrapolation is performed.
- Freshwater reference solubility uses Benson-Krause equation 7 at standard atmosphere, as adopted by USGS DOTABLES. The influent temperature remains a plant-level proxy, not an in-basin temperature, pressure, or salinity measurement.

## Minute-Level Frozen Calibration

Calibration is 2025-08-01 through 2026-01-31. Independent validation is 2026-02-01 through 2026-03-31. The terminal test is 2026-04-01 through 2026-04-13. The validation-only benchmark filter requires frozen D1 total, spike, step, drift, freeze and regime scores of at least 4.5 plus eligible D2 Strict evidence. No independent D1 DO saturation/floor sheet exists in the release, so no unavailable field was imputed.

Two parallel lines share one coefficient at each longitudinal position. The estimator is `max(P99, median + 3 x 1.4826 MAD)` of minute DO divided by minute Benson-Krause reference `Csat`. Confidence intervals use 1,000 calendar-day cluster-bootstrap replicates.

| Position | Calibration sensor-minutes | Frozen alpha | 95% day-block CI | Registry |
|---|---:|---:|---:|---|
| 1 | 62,452 | 0.2789373305 | 0.2186-0.3738 | Passed |
| 2 | 113,862 | 0.3100300303 | 0.2817-0.3406 | Passed |
| 3 | 120,644 | 0.5065765789 | 0.4914-0.5377 | Passed |

All coefficients reproduce from frozen sources within `2.6e-11` absolute difference.

## Independent Validation Decision

Promotion requires both a high-quality minute exceedance rate no greater than 2% and a high-quality 2 h warning-window rate no greater than 2% for each sensor. A 2 h window is eligible with at least 60 high-quality minutes and is flagged when more than 2% of those minutes exceed the envelope.

| Sensor | Minute exceedance | 2 h warning-window rate | Decision |
|---|---:|---:|---|
| DO-1-1 | 0.096% | 1.020% | Pass, scored |
| DO-2-1 | 0.005% | 0.000% | Pass, scored |
| DO-1-2 | 0.090% | 1.172% | Pass, scored |
| DO-2-2 | 0.033% | 0.368% | Pass, scored |
| DO-1-3 | 0.000% | 0.000% | Diagnostic only |
| DO-2-3 | 7.627% | 38.983% | Fail, diagnostic only |

Position 3 is not widened or promoted. DO-2-3 is already a sensor-health concern; therefore its failure cannot be attributed solely to aeration or load structure. The result supports only an unresolved position-3/line-2 discrepancy requiring process records and independent drift/maintenance evidence.

## Locked Forward Test and Cross-Line Transfer

- Terminal DO-1-2 reaches 1.868% minute exceedance and 15.054% warning windows.
- Terminal DO-2-1 reaches 0.721% minute exceedance and 2.083% warning windows.
- Terminal DO-2-3 remains high at 5.764% and 58.537%.
- These terminal results are never used to refit or widen alpha.
- Leave-one-line-out validation passes both criteria in both directions at position 2.
- At position 1, the DO-1-1-only template evaluated on DO-2-1 yields 0.273% minute exceedance but 3.043% warning windows; the reverse direction passes. This mild directional asymmetry limits the claim that the pooled template is fully line-independent.
- At position 3, cross-line transfer is strongly asymmetric, reinforcing the diagnostic-only decision.

The pooled position template remains acceptable as a site-specific operational-warning model because it was prespecified and passes time-blocked validation. Cross-line results are an applicability audit, not a post-hoc selection tool.

## Corrected Scoring and Review Defects

- Dynamic high-side rates use only DO minutes with valid temperature. Missing temperature is unevaluated evidence, not an implicit pass.
- Low- and high-side soft rates are calculated on side-specific eligible denominators and combined without duplicating evidence.
- Historical v2.3 `Q_rate` is reconstructed from all hard point violations with the original aggregation and cap semantics. The corrected current-rate versus v2.3 low-event Jaccard is 0.529; the candidate `0.45/0.35/0.20` versus v2.3 Jaccard is 0.014. The candidate weights remain sensitivity-only.
- DO-1-4 and DO-2-4 are excluded from the ORP position/season diagnostic sheet and remain on their dedicated post-anoxic route.
- Nature source validation is optional and discoverable. The main reproduction workflow still performs export freshness, editable-text, and nonblank-image checks when the optional local validator is absent.

## Publication Outputs

- `D3_temperature_conditioned_DO_upper.xlsx`: source audit, Benson-Krause checks, frozen registry, day-block intervals, minute/2 h phase validation, cross-line transfer, sensitivity and exclusions.
- `D3_temperature_conditioned_DO_upper.parquet`: complete minute-level source data for figure reproduction.
- `D3_weight_contract_sensitivity.xlsx`: corrected historical reconstruction and current/candidate comparisons.
- `fig10_temperature_conditioned_do_upper`: editable SVG/PDF and 600 dpi PNG/TIFF.

The defensible manuscript claim is that a full-period influent-temperature proxy can support auditable, minute-resolved operational envelopes at selected aerobic positions while explicitly identifying where temporal and cross-line transfer fail. Failure is retained as an applicability boundary, not hidden by sensor-specific self-normalization or retrospective widening.

## Pending External Evidence

- In-basin temperature, atmospheric pressure and salinity are required before thermodynamic saturation interpretation.
- Airflow, DO setpoints, load/flow records and reviewed maintenance labels are required to attribute terminal and position-3 warnings.
- Manufacturer accuracy or zero-oxygen calibration remains required to lock the DO4 deadband.
- Position-3 scoring requires a new prespecified model with independent validation; the current data do not justify promotion.
- Position-1 cross-line transfer should be repeated with an independent period or external plant before claiming general line invariance.
- Cross-plant transfer and event-level expert adjudication remain pending.

## Reference

U.S. Geological Survey. Office of Water Quality Technical Memorandum 2011.03, *Change to Solubility Equations for Oxygen in Water*. The memorandum adopts the Benson and Krause (1980, 1984) oxygen-solubility equations for USGS computation.
