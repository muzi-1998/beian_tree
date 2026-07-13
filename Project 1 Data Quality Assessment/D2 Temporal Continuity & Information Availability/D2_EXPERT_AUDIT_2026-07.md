# D2 Expert Audit (2026-07)

## Architecture Decision

D2 must consume the canonical output of **1.1 Decomposition**, specifically the
1-minute time grid, per-channel raw observation values, preprocessing flags and
source audit. It must not consume whitened innovations as availability evidence.

D1 is an **external concordance layer only**. D1 event windows may be linked to
D2 events for interpretation, but D1 scores/events must not fit D2 mappings,
calibration thresholds, veto rules or the D2 total score.

## Current Verified State

- Canonical horizon: 2025-08-01 00:00 to 2026-04-13 23:59 (368,640 minutes).
- D2 output: 6,121 hourly windows per sensor after a complete 24 h warm-up.
- Scored sensors: 14; support channels: 4, excluded from the D2 main score.
- Gap events: 543; maximum gap 565 min.
- Interpolation ledger: maximum imputed run 5 min; long-gap imputation count 0.
- Mapping table: all 8 configured metrics exported from `d2_mapping.yaml`.
- Calibration: `D2_internal_engineering_v1`; D1 fit hours = 0.
- D1 event index: 72 events loaded; D1-D2 concordant events = 650/15,146
  (4.29%), reported descriptively rather than used as an acceptance threshold.
- Figure bundles: 1.1 = 89, D1 = 18, D2 = 12; all have PNG/SVG/PDF counterparts.
- Tests: D2 contract/regression 11/11 and modular scorer 8/8 pass.

## Scientific Interpretation

The revised D2 implementation is internally coherent and reproducible. The
strongest channel discrimination currently comes from Q_FA; Q_TI and Q_GS stay
near 4.96-4.97 for most channels because most timestamp/gap disturbances are
plant-wide and sparse. This is a result, not a plotting defect, but it means the
paper should not claim strong sensor-specific discrimination from Q_TI/Q_GS.

The 15,146 info-empty events are the main residual scientific risk. Their high
frequency and low D1 concordance suggest that the current low-variation/RLE rule
also captures legitimate stable-process periods. Before using event counts as a
fault label or operational alarm, validate duration and low-IQR thresholds on a
manually reviewed stratified event sample and report precision/recall with
uncertainty. Until then, call them **information-availability events**, not
confirmed sensor faults.

For 1.1, 28/33 channels follow the whitened route, while the remaining channels
use autocorrelation-aware or censoring-aware routes. Mean windowed Ljung-Box pass
rate improves from 0.026 to 0.284 and mean absolute ACF decreases from 0.661 to
0.155. The manuscript should describe this as substantial but heterogeneous
decorrelation, not universal whitening.

## Figure Assessment

- **Best methodological evidence chain:** 1.1, because it connects preprocessing,
  decomposition sufficiency, whitening diagnostics and downstream ablation.
- **Best main-text visual economy:** D1, especially the mapping, comparative hero
  panel and state-machine case study.
- **D2 after revision:** suitable for submission; Fig. 1, 5, 7, 8 and 11 carry the
  main argument, while mapping/calibration and detailed veto diagnostics are
  better placed in Methods or Supplementary Information.

All projects now use lowercase panel labels, editable SVG/PDF masters, embedded
fonts and paired high-resolution PNG previews. A specific target journal and two
or three exemplar figures would still help tune final column width, caption
density and main-text/SI allocation, but are not required for the present
technical correction.
