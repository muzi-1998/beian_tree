# D3 v2.2 Expert Audit

## Overall assessment

D3 v2.2 is complete and internally consistent as an **independent univariate physical-plausibility baseline**. It is not yet a final plant-wide mechanistic D3 model: the operational thresholds still require site/instrument validation, and coupled mass-balance or process-state constraints have not been implemented.

## Current result provenance

- Run ID: `RUN_D3_v2.2.0_20260726T084811Z_4246fb53`
- Canonical observation interval: `2025-08-01 00:00` to `2026-04-13 23:59`
- Input grid: 368,640 one-minute rows, without D3 interpolation
- Analysis windows: 43,008 sensor windows (14 sensors x 3,072 windows)
- Evaluated: 42,840; not evaluated because of insufficient evidence: 168
- Configuration SHA-256 prefix: `4246fb539828`
- Code SHA-256 prefix: `a7bb005ad33d`

The manifest stores complete source-file fingerprints and full hashes. These fields, rather than file modification times, define whether an output is current.

## Final results

- Mean D3: 4.799; median: 5.000; minimum: 1.500
- Usability: 38,865 `train_ok`, 3,948 `report_only`, 27 `invalid`, 168 `not_evaluated`
- Dominant evidence: 35,846 none, 5,775 soft-bound, 1,219 rate, 168 insufficient evidence
- Physical event windows: 50 total (27 instrument range, 14 soft bound, 9 rate)
- Lowest sensor means: DO-1-4 = 3.758, ORP-2-3 = 3.856, ORP-1-3 = 4.691

## Scientific logic corrections

1. D3 now consumes only section 1.1's canonical raw observation clock. Missing values remain missing; no interpolated values are scored.
2. D1 and D2 scores, cooldown states, freshness states, and regime labels are prohibited as D3 inputs. Cross-sensor rate coherence is retained as a diagnostic only and cannot change D3.
3. Boundary sticking and benchmark-tail occupancy are diagnostic only. They no longer contribute 10% to D3, avoiding overlap with D1 floor/freeze and distribution-tail evidence.
4. Scoring uses only hard value, soft value, and rate evidence with weights 0.50/0.20/0.30. Zero violations map exactly to 5.
5. Missing observations interrupt violation runs and robust-rate estimates; gaps cannot be bridged by filling or compaction.
6. Evidence-insufficient windows return `NaN/not_evaluated`, rather than an artificial high-quality score.
7. The former DO instrument lower limit of 0 mg/L contradicted the hard physical tolerance of -0.2 mg/L and created thousands of false invalid windows. The instrument range now contains the hard physical range, and a regression contract prevents recurrence.
8. Arbitrary K-means regime names and synthesized regime-specific bounds were removed. Fixed, auditable thresholds are used until a defensible regime calibration study exists.

## Independence from D1 and D2

D1, D2, and D3 are parallel quality dimensions joined only downstream. D1 owns sensor state; D2 owns continuity/availability; D3 owns observed value/rate physical plausibility. The final manifest confirms that D1 scores, D2 scores, imputed values, and regime labels were not consumed. This separation prevents double penalties while preserving a shared time grid.

## File organization

The executable project now lives directly at the D3 module root. Configurations, source, tests, CI checks, figures, current outputs, reports, and manifest each have one owner directory. Duplicate v2.1 root/nested deliverables were moved to ignored `archive/v2.1_delivery/`; `outputs/` contains only current v2.2 products.

## Figure assessment

The seven figures were rebuilt as compact double-column scientific figures with Arial, 0.8-pt axes, restrained multi-hue colors, outward ticks for open axes, inward ticks for full-frame heatmaps, and lowercase parenthesized panel labels. Labels and legends were moved away from evidence; unavoidable in-panel labels use staggered leader lines and semi-transparent neutral backing. Each figure is exported as editable SVG, PDF, and 600-dpi PNG.

`figure_bundle_audit.json` reports 7 figures, 0 failures, nonblank PNGs, Arial declarations, conforming panel labels, and outputs newer than their source scripts.

## Remaining limitations before journal submission

1. Validate DO/ORP hard, soft, instrument, and rate limits against probe datasheets, calibration/maintenance records, process-engineer review, and site operating envelopes.
2. Perform sensitivity and uncertainty analyses for threshold choices, mapping parameters, window length, and veto caps.
3. Add externally justified multivariate constraints only where mass balance, redox coupling, hydraulic residence, or process topology can be supported; these must remain separate from D1/D2 evidence.
4. Validate event precision/recall against independently reviewed abnormal-event labels.
5. Report the low-DO behavior of DO-1-4 as an operational plausibility finding, not automatically as sensor failure; D1 must adjudicate sensor-state evidence independently.
