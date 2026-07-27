# D3 v2.2.1: Physical Rationality and Rate Constraints

D3 independently evaluates whether observed DO/ORP values and their temporal rates are physically plausible. It uses the section 1.1 canonical one-minute observation grid but never consumes imputed values, D1/D2 scores, or regime labels.

## Scientific Contract

- **D1 owns sensor state:** freeze, drift, floor, saturation, and sensor-health evidence.
- **D2 owns availability:** missingness, continuity, and information-availability evidence.
- **D3 owns physical plausibility:** hard/soft value bounds and persistent rate-limit violations.
- **Boundary/tail occupancy is diagnostic only:** it is exported for review but excluded from D3 because it overlaps D1 floor/freeze and distribution-tail evidence.
- **Insufficient evidence is not scored:** a 120-minute window requires at least 60 observed values and 59 valid rate estimates; otherwise `D3_total` is `NaN` and `usable_tag=not_evaluated`.

Three zero-anchored subscores map zero violations exactly to 5:

`D3_base = 0.50 Q_hard + 0.20 Q_soft + 0.30 Q_rate`

`D3_pre = 0.75 D3_base + 0.25 min(Q_hard, Q_soft, Q_rate)`

Documented hard-value, instrument-range, and persistent-rate vetoes cap the result. Manufacturer ranges are recorded separately from expert operational hard/soft bounds. The instrument Veto range must contain the hard physical range so it cannot override a documented numeric tolerance. The registered ranges are 0-20 mg/L for DO and -1500 to 1500 mV for ORP; DO retains a -0.2 mg/L lower Veto tolerance to prevent quantization/calibration noise from becoming an automatic invalidation.

## Data Scope

- Canonical interval: `2025-08-01 00:00` to `2026-04-13 23:59`
- Resolution: 1 minute, no interpolation in D3
- Default analysis window/stride: 120/120 minutes, half-open windows
- Sensors: 8 DO and 6 ORP channels

The manifest records source-file SHA-256 hashes, configuration hash, code hash, versions, run ID, study interval, and result counts.

## Layout

```text
configs/          versioned D3 rules, limits, paths, and independence contract
src/              input, evidence, scoring, pipeline, and export modules
tests/            v2.2.1 scientific-contract regression tests
ci/               forbidden-coupling and mapping checks
figures/          Python scripts for seven publication figures
outputs/data/     current v2.2.1 workbooks only
outputs/figures/  current SVG, PDF, and 600-dpi PNG figures
outputs/manifest/ current run manifest
outputs/reports/  expert audit and result summary
archive/          ignored v2.1 delivery artifacts
```

## Reproduce

Full canonical run and all figures:

```powershell
python run_all.py
```

Fast checks without recomputing scores:

```powershell
python run_all.py --skip-pipeline
```

Short diagnostic run:

```powershell
python run_all.py --subset-days 2
```

## Current Outputs

The authoritative data products are `D3_window_scores.xlsx`, `D3_value_evidence.xlsx`, `D3_rate_evidence.xlsx`, `D3_boundary_diagnostics.xlsx`, `D3_threshold_library.xlsx`, `D3_physical_events.xlsx`, `D3_mapping_params.xlsx`, and `D3_sensor_summary.xlsx`.

Instrument ranges are supported by the provided installation register. Physical hard/soft and rate limits remain expert operational priors until validated against plant operating envelopes, maintenance records, and process-engineer review. The current module is a rigorous univariate D3 baseline; coupled mass-balance and process-state constraints are future extensions and must not be inferred from these outputs.
