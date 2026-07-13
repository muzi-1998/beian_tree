# D4 v2.2: Physical Rationality and Rate Constraints

D4 independently evaluates whether observed DO/ORP values and their temporal rates are physically plausible. It uses the section 1.1 canonical one-minute observation grid but never consumes imputed values, D1/D2 scores, or regime labels.

## Scientific Contract

- **D1 owns sensor state:** freeze, drift, floor, saturation, and sensor-health evidence.
- **D2 owns availability:** missingness, continuity, and information-availability evidence.
- **D4 owns physical plausibility:** hard/soft value bounds and persistent rate-limit violations.
- **Boundary/tail occupancy is diagnostic only:** it is exported for review but excluded from D4 because it overlaps D1 floor/freeze and distribution-tail evidence.
- **Insufficient evidence is not scored:** a 120-minute window requires at least 60 observed values and 59 valid rate estimates; otherwise `D4_total` is `NaN` and `usable_tag=not_evaluated`.

Three zero-anchored subscores map zero violations exactly to 5:

`D4_base = 0.50 Q_hard + 0.20 Q_soft + 0.30 Q_rate`

`D4_pre = 0.75 D4_base + 0.25 min(Q_hard, Q_soft, Q_rate)`

Documented hard-value, instrument-range, and persistent-rate vetoes cap the result. Instrument ranges are contractually required to contain the hard physical range so a stricter zero-tolerance instrument rule cannot override the physical tolerance.

## Data Scope

- Canonical interval: `2025-08-01 00:00` to `2026-04-13 23:59`
- Resolution: 1 minute, no interpolation in D4
- Default analysis window/stride: 120/120 minutes, half-open windows
- Sensors: 8 DO and 6 ORP channels

The manifest records source-file SHA-256 hashes, configuration hash, code hash, versions, run ID, study interval, and result counts.

## Layout

```text
configs/          versioned D4 rules, limits, paths, and independence contract
src/              input, evidence, scoring, pipeline, and export modules
tests/            v2.2 scientific-contract regression tests
ci/               forbidden-coupling and mapping checks
figures/          Python scripts for seven publication figures
outputs/data/     current v2.2 workbooks only
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

The authoritative data products are `D4_window_scores.xlsx`, `D4_value_evidence.xlsx`, `D4_rate_evidence.xlsx`, `D4_boundary_diagnostics.xlsx`, `D4_threshold_library.xlsx`, `D4_physical_events.xlsx`, `D4_mapping_params.xlsx`, and `D4_sensor_summary.xlsx`.

All physical and rate limits remain expert operational priors until validated against probe specifications, plant operating envelopes, maintenance records, and process-engineer review. The current module is a rigorous univariate D4 baseline; coupled mass-balance and process-state constraints are future extensions and must not be inferred from these outputs.
