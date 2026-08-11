# D3 v2.6.0: Physical Rationality and Persistent-Rate Constraints

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

The proposed `0.45/0.35/0.20` rebalance remains sensitivity-only because it caused a large ORP3 soft-envelope reclassification without external labels. v2.6 retains the frozen outer weights. The historical v2.3 comparison is reconstructed from all hard point violations, matching the original `Q_rate` contract rather than the later persistent-rate evidence.

## Threshold Status

- Registered instrument ranges are `0-20 mg/L` for DO and `-1500 to 1500 mV` for ORP.
- The fixed aerobic DO `8 mg/L` warning has been retired. Positions 1-2 use a frozen, temperature-conditioned operational upper envelope; position 3 is diagnostic-only.
- ORP `-400 to 200 mV`, ORP hard operating range `-500 to 500 mV`, and all rate limits remain `provisional_expert_prior`.
- `DO_1_4` and `DO_2_4` are explicit post-anoxic sensors. Their physical soft lower boundary remains `0 mg/L`; `-0.05 mg/L` is a separate provisional zero-equivalence tolerance evaluated at `0`, `-0.03`, `-0.05`, and `-0.10 mg/L`.
- DO4 values in `[-0.05, 0) mg/L` are retained as raw observations and flagged as zero-equivalent without reducing `Q_value_soft`; `[-0.20, -0.05) mg/L` is an offset warning and values below `-0.20 mg/L` remain severe.
- DO4 does not inherit an aerobic upper warning. Production upper scoring is disabled until a time-blocked post-anoxic template has adequate independent support.

## Temperature-Conditioned Aerobic DO Upper

- The covariate is the aligned minute influent-temperature record. Values outside `0-40 deg C` are masked and audited; missing values are never interpolated or extrapolated.
- The USGS-adopted Benson-Krause freshwater equation at standard atmosphere is used only as a monotonic temperature normalizer. Influent temperature is not an in-basin thermodynamic measurement, so this envelope is an operational warning and never an instrument-range Veto.
- Calibration, independent validation, terminal testing, and production scoring use the same minute-level `DO/Csat` estimand. Uncertainty uses 1,000 calendar-day cluster-bootstrap replicates.
- The validation-only benchmark requires `D1_total`, `Q_spike`, `Q_step`, `Q_drift`, `Q_freeze`, `Q_regime`, and eligible `D2_Strict` evidence. The frozen D1 release has no independent DO saturation/floor sheet, so no such field is imputed. Production D3 never reads D1/D2 scores.
- Frozen position coefficients are `0.2789373305`, `0.3100300303`, and `0.5065765789`. Positions 1-2 pass both the minute exceedance and 2 h warning-window criteria in independent validation; position 3 remains diagnostic-only because DO-2-3 reaches 7.63% and 38.98%, respectively.
- Terminal testing remains locked: the later DO-1-2 2 h warning-window burden (15.05%) is retained as forward instability and does not trigger retrospective widening.
- Leave-one-line-out transfer is reported separately and is never used to tune the pooled position template.
- Low- and high-side soft violations use side-specific evaluable denominators. Missing temperature is unevaluated high-side evidence, not an implicit pass.
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
ci/                  forbidden-coupling and figure-bundle checks
figures/             Python scripts for ten publication figures
outputs/data/        current scoring and evidence workbooks
outputs/validation/  threshold, construct, overlap, and source-data audits
outputs/figures/     editable SVG/PDF and 600-dpi PNG/TIFF figures
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

The Nature source preflight is optional for reproducibility. It is discovered from `D3_NATURE_VALIDATOR`, a repository-local validator, or an installed Nature skill; export and nonblank-image audits still run when that optional validator is unavailable.

## Authoritative Outputs

Core outputs are `D3_window_scores.xlsx`, `D3_value_evidence.xlsx`, `D3_rate_evidence.xlsx`, `D3_boundary_diagnostics.xlsx`, `D3_threshold_library.xlsx`, `D3_physical_events.xlsx`, `D3_mapping_params.xlsx`, and `D3_sensor_summary.xlsx`.

Validation outputs additionally include `D3_DO4_zero_equivalence_views.parquet`, `D3_weight_contract_sensitivity.xlsx`, `D3_temperature_conditioned_DO_upper.xlsx`, and `D3_temperature_conditioned_DO_upper.parquet`. The temperature workbook contains source QA, Benson-Krause reference checks, frozen-registry reproduction, day-block confidence intervals, minute/2 h phase validation, cross-line transfer, alpha sensitivity, and exclusions. The Parquet file contains the complete minute-level source data for figure reproduction. D1/D2 are validation filters only and are never consumed by production D3 scoring.

The current project supports an internally consistent retrospective D3 gate and a defensible site-calibrated temperature-conditioned warning for aerobic positions 1-2. It does not establish a thermodynamic saturation limit, a validated position-3 upper envelope, universal operating thresholds, alarm precision/recall, or a fully shared raw-domain D1-D3 injection claim. Cross-line asymmetry and terminal-test warnings are explicit applicability limits, not reasons for post-hoc threshold expansion.
