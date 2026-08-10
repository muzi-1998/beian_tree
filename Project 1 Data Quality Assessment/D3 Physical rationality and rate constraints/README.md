# D3 v2.5.0: Physical Rationality and Persistent-Rate Constraints

D3 independently evaluates whether observed DO/ORP values and sustained temporal changes are physically plausible. It uses the section 1.1 canonical one-minute observation grid, but never consumes imputed values, D1/D2 scores, or external regime labels in production scoring.

## Scientific Contract

- **D1 owns sensor state:** spike, step, drift, freeze, floor, saturation, and recovery evidence.
- **D2 owns continuity and availability:** timestamp integrity, missingness, gaps, and hard information stasis.
- **D3 owns observed-value plausibility and persistent same-sign rate evidence.**
- **Instrument failure and operating warning are separate:** registered instrument-range violations are data-quality `Fail`; provisional operating bounds and rates are `Warn`, not automatic training exclusion.
- **Process coherence is a guard:** a synchronous, same-direction peer response suppresses single-sensor rate attribution but is retained as a process diagnostic. It is not a Veto.
- **Boundary/tail occupancy remains diagnostic only:** it is excluded from D3 scoring because it overlaps D1 floor/freeze and distribution-tail evidence.
- **Insufficient evidence is not scored:** a 120-minute window requires at least 60 observed values and 59 valid rate estimates.

The supplementary plausibility score is:

`Q_persistent_rate = 0.30 Q_soft-only + 0.70 Q_hard-persistent`

`D3_base = 0.50 Q_value_hard + 0.20 Q_value_soft + 0.30 Q_persistent_rate`

`D3_pre = 0.75 D3_base + 0.25 min(Q_value_hard, Q_value_soft, Q_persistent_rate)`

`D3_total` is retained for descriptive analysis. Downstream aggregation must use `D3_gate_status`; it must not average the provisional operating score into the composite quality index.

The proposed `0.45/0.35/0.20` rebalance remains sensitivity-only: it caused a large ORP3 soft-envelope reclassification without external labels. v2.5 retains the frozen outer weights.

## Threshold Status

- Registered instrument ranges are `0-20 mg/L` for DO and `-1500 to 1500 mV` for ORP.
- The fixed aerobic DO `8 mg/L` warning has been retired. Positions 1-2 use a frozen, temperature-conditioned operational upper envelope; position 3 is diagnostic-only because its temporal transfer criterion failed.
- ORP `-400 to 200 mV`, ORP hard operating range `-500 to 500 mV`, and all rate limits remain `provisional_expert_prior`.
- `DO_1_4` and `DO_2_4` are explicit post-anoxic sensors. Their physical soft lower boundary remains `0 mg/L`; `-0.05 mg/L` is a separate provisional zero-equivalence tolerance evaluated at `0`, `-0.03`, `-0.05`, and `-0.10 mg/L`.
- DO4 values in `[-0.05, 0) mg/L` are retained as raw observations and flagged as zero-equivalent without reducing `Q_value_soft`; `[-0.20, -0.05) mg/L` is an offset warning and values below `-0.20 mg/L` remain severe.
- DO4 does not inherit the aerobic `8 mg/L` upper warning. Production upper scoring is disabled until a time-blocked post-anoxic template has adequate independent support.
- The temperature covariate is the aligned minute influent-temperature record. Values outside `0-40 °C` are masked and audited; missing values are never interpolated or extrapolated.
- The freshwater standard-atmosphere saturation polynomial is used only as a temperature normalizer. Influent temperature is not an in-basin thermodynamic measurement, so this envelope is an operational warning and never an instrument-range Veto.
- Calibration uses hourly mean DO and hourly median temperature with at least 30 valid temperature minutes. D1/D2 filter high-quality calibration windows only in validation; production D3 reads frozen position coefficients and temperature, never D1/D2 scores.
- Frozen position coefficients are `0.2870480956`, `0.3146109551`, and `0.4898265899`. Positions 1-2 passed independent validation; position 3 remains diagnostic-only because DO-2-3 exceeded the prespecified 2% high-quality warning criterion.
- ORP position/season robust envelopes are exported as diagnostics only. They do not replace production thresholds before site review and independent event adjudication.

## Persistent-Rate Definition

- Soft evidence requires a same-sign exceedance lasting at least 3 min.
- Soft-only evidence covers complete 3-9 min episodes that contain no hard-persistent core.
- Hard score evidence requires a same-sign exceedance lasting at least 10 min; its points are not counted again as soft-only evidence.
- The non-compensatory persistent-rate cap remains at more than 30 min.
- A 1-3 min impulse-return that returns to its prior baseline is assigned to the D1 spike construct and excluded from D3 rate loss.
- Missing-data recovery jumps are not bridged.
- Coherent same-direction changes in the exact parallel peer, or at least two same-line peers, are guarded within a +/-2 min tolerance.

These durations and rates remain provisional until supported by reviewed plant events and external evidence.

## Data Scope

- Canonical interval: `2025-08-01 00:00` to `2026-04-13 23:59`
- Resolution: 1 minute, no D3 interpolation
- Default analysis window/stride: 120/120 minutes, half-open windows
- Sensors: 8 DO and 6 ORP channels

The manifest records source SHA-256 hashes, configuration/code hashes, versions, run ID, study interval, result counts, and the locked/pending scientific contracts.

## Layout

```text
configs/             versioned thresholds, mappings, paths, and independence contract
src/                 evidence, scoring, guard, validation, pipeline, and export modules
tests/               scientific-contract regression tests
ci/                  forbidden-coupling and mapping checks
figures/             Python scripts for ten publication figures
outputs/data/        current scoring and evidence workbooks
outputs/validation/  threshold, construct, overlap, and source-data audits
outputs/figures/     editable SVG/PDF and 600-dpi PNG figures
outputs/manifest/    current run manifest
outputs/reports/     expert audit and result summary
```

## Reproduce

Full scoring, validation, and figures:

```powershell
python run_all.py
```

Rebuild validation without changing the frozen score tables:

```powershell
python run_validation.py
```

Rebuild figures only:

```powershell
python run_all.py --skip-pipeline
```

## Authoritative Outputs

Core outputs are `D3_window_scores.xlsx`, `D3_value_evidence.xlsx`, `D3_rate_evidence.xlsx`, `D3_boundary_diagnostics.xlsx`, `D3_threshold_library.xlsx`, `D3_physical_events.xlsx`, `D3_mapping_params.xlsx`, and `D3_sensor_summary.xlsx`.

Validation outputs additionally include `D3_DO4_zero_equivalence_views.parquet`, `D3_weight_contract_sensitivity.xlsx`, `D3_temperature_conditioned_DO_upper.xlsx`, and `D3_temperature_conditioned_DO_upper.parquet`. The temperature workbook contains source QA, frozen-registry reproduction, phase validation, alpha sensitivity, and exclusions. D1/D2 are validation filters only and are never consumed by production D3 scoring.

The current project supports an internally consistent retrospective D3 gate and a defensible site-calibrated temperature-conditioned warning for aerobic positions 1-2. It does not establish a thermodynamic saturation limit, a validated position-3 upper envelope, universal operating thresholds, alarm precision/recall, or a fully shared raw-domain D1-D3 injection claim.
