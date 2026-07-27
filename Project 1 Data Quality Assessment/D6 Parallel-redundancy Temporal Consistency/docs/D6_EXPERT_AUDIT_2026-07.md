# D6 Expert Audit and Restored v1.2 Contract (2026-07)

## 1. Executive conclusion

The restored implementation, `d6-v1.4-restored-v12-20260714`, is the current
reproducible D6 result. It restores the scientifically important v1.2 rules
without recreating unavailable evidence: a strict high-quality benchmark,
public mapping by variable and operating regime, change-point time-difference
scoring with a 7 d auxiliary window, a 3 h event threshold, and separate
`D6_raw` and downstream-arbitration paths.

`D6_raw` contains only pairwise temporal-consistency evidence, but its public
mapping is conditionally calibrated on D1/D2-qualified benchmark windows. D2
also determines whether a D6 window is evaluable. Real D1 scores produce
`D6_forDQR_provisional`; they do not enter the pairwise risk statistics or
overwrite an already calculated `D6_raw`. Because D7 production arbitration
remains pending, final `D6_forDQR` is intentionally null and every downstream
result is marked `provisional_pending_D7`. No D7 proxy is generated.

The implementation and internal QA are suitable for branch review and for
merging as a transparent provisional D6 module. It is not yet suitable for a
claim of final DQR arbitration or definitive sensor-versus-process causal
attribution.

## 2. Restored scientific contract

### Inputs and dimension boundaries

1. Section 1.1 supplies the production `residual_min` time base. D6 does not
   repeat decomposition or preprocessing.
2. D2 supplies information-availability/evaluability gates. Missingness creates
   `not_evaluable`; it does not lower D6 and therefore is not double-penalized.
3. D1 supplies real bilateral health scores to benchmark admission and the
   downstream provisional fuse. It does not enter pairwise D6 risk statistics;
   D1 release changes nevertheless require explicit D6 recalibration.
4. D7 is required for final arbitration. While absent, the final
   `D6_forDQR` field remains null.

### High-quality public benchmark

Benchmark windows require bilateral D1 scores >= 4.5, bilateral usable D2
context, at least 24 h continuous coverage, and sufficient pair completeness.
The v1.2 D7 spatial-anomaly exclusion cannot yet be executed and is explicitly
recorded as pending rather than replaced with a proxy.

The public calibration pools contain 4,646 DO and 312 ORP benchmark windows.
DO has adequate regime-specific support: R0 = 2,316, R1 = 746, R2 = 1,060,
and R3 = 524. For ORP, only R2 has adequate exact-stratum support (n = 145);
R0 (n = 62), R1 (n = 32), and R3 (n = 73) use the documented variable-level
fallback calibrated on all 312 ORP benchmark windows. No mapping is calibrated
independently for an individual sensor pair.

Continuous risks are mapped through public q50/q75/q90/q97.5 thresholds. Each
output row stores mapping scope, support size, calibration quality, and a shared
calibration identifier, `D6CAL-V14-598338d2c31d`.

### Change-point and event rules

Change points are detected on the original 7 d auxiliary window by comparing
adjacent 12 h distributions. Candidate detections are consolidated before the
nearest target-reference event is matched. The restored score table is:

| Pairwise change-point evidence | Q_cp |
|---|---:|
| Neither side changes | 5 |
| Both change, time difference < 3 h | 5 |
| Both change, 3-12 h | 4 |
| Both change, 12-24 h | 3 |
| Only one changes, persistence < 24 h | 2 |
| Only one changes, persistence >= 24 h | 1 |

Events are constructed only from evaluable `D6_raw < 3` runs lasting at least
3 h. The event workbook therefore describes independent D6 evidence, not a
D1/D7-derived fault label.

### Dual-path output

- `D6_raw`: independent D6 score used for scientific interpretation.
- `D6_after_D1` / `D6_forDQR_provisional`: real v1.2 D1 fuse, retained for
  downstream preparation and visibly marked provisional.
- `D6_forDQR`: final arbitrated value; null until real D7 evidence exists.

The D1 fuse uses the original 2.5 threshold. Bilateral unreliable or
reference-unreliable states are neutralized to 3; target-unreliable states keep
the D6 evidence for later arbitration; bilaterally reliable states pass the raw
score forward. These operations never modify `D6_raw`.

## 3. Current run and result freshness

- Run ID: `D6V14_20260722_091650`.
- Configuration: `d6-v1.4-restored-v12-20260714`.
- Calibration: `D6CAL-V14-598338d2c31d`.
- Data span: 2025-08-01 00:00 to 2026-04-13 23:50.
- Output size: 42,847 pair-windows across seven pairs.
- D2 source run: `D2V1_20260722_1714`.
- Overall evaluability: 88.66% (37,987/42,847 pair-windows).

The run manifest records SHA-256 hashes for Section 1.1 residuals and time-base
contract, D1 scores and regime templates, D2 scores, D6 configuration, pipeline
code, and scoring code. This makes the workbook bundle traceable to exact input
and code states.

| Pair | Mean D6_raw | Low-score rate | Evaluable rate | Mean Q_cp | 3 h events |
|---|---:|---:|---:|---:|---:|
| DO11 | 3.368 | 31.4% | 97.5% | 2.772 | 124 |
| DO12 | 3.391 | 26.5% | 98.7% | 2.624 | 128 |
| DO13 | 3.198 | 40.6% | 98.8% | 2.764 | 162 |
| DO14 | 2.978 | 47.8% | 98.8% | 2.426 | 79 |
| ORP11 | 3.425 | 27.7% | 92.3% | 3.139 | 136 |
| ORP12 | 3.040 | 49.2% | 70.3% | 3.529 | 215 |
| ORP13 | 2.650 | 67.6% | 64.2% | 2.840 | 164 |

The corrected process-floor route raises DO14 evaluability from 23.2% in the
archived v1.3 comparison to 98.8% in the current restored run. This does not
make DO14 healthy by definition: D2 now states that the observations are
temporally available, while D6 independently finds frequent bilateral
inconsistency (mean `D6_raw` = 2.978; low-score rate = 47.8%). This separation
is scientifically preferable to allowing low-DO floor occupancy to mask D6
evidence. ORP13 remains the clearest persistent pair-consistency concern, but
D6 alone cannot identify which sensor, or whether a local process asymmetry,
caused either pattern.

## 4. Internal validation

| Scenario | Metric | Estimate | 95% CI | Criterion | Status |
|---|---|---:|---:|---:|---|
| Unilateral drift | ROC AUC | 0.934 | 0.905-0.960 | >= 0.70 | Pass |
| Unilateral step | ROC AUC | 0.936 | 0.903-0.963 | >= 0.70 | Pass |
| Unilateral freeze | ROC AUC | 0.798 | 0.749-0.849 | >= 0.70 | Pass |
| Unilateral spike | ROC AUC | 0.561 | 0.546-0.581 | Secondary only | Expected limitation |
| Synchronous switch | Conditional new FAR | 0.041 | 0.000-0.095 | <= 0.10 | Pass |
| Common-mode drift | Conditional new FAR | 0.041 | 0.000-0.095 | <= 0.10 | Pass |

The synchronous tests use a paired conditional false-alarm rate among windows
that were non-alarming before injection. This avoids confusing pre-existing D6
events with injection-induced false alarms. Both upper confidence limits now
remain below 0.10, although external normal-transition examples are still
required. Isolated spikes remain primarily a D1 responsibility and are not a
required D6 acceptance scenario.

These are internal chronological-holdout stress tests, not external clinical or
plant-operation validation. They support implementation correctness and
sensitivity, but do not replace independently labelled field events.

## 5. Three-version sensitivity analysis

The comparison workbook applies one common 3 h event definition to all three
versions and aligns scores by pair and timestamp.

| Pair | Legacy v1.2 proxy | Current v1.3 | Restored v1.4 |
|---|---:|---:|---:|
| DO11 | 4.822 | 3.981 | 3.368 |
| DO12 | 4.743 | 3.989 | 3.391 |
| DO13 | 4.492 | 3.788 | 3.198 |
| DO14 | 4.706 | 4.034 | 2.978 |
| ORP11 | 3.828 | 3.784 | 3.425 |
| ORP12 | 3.370 | 3.772 | 3.040 |
| ORP13 | 2.748 | 3.874 | 2.650 |

Restored v1.4 versus current v1.3 has all-pair Pearson r = 0.700, Spearman rho
= 0.688, mean absolute difference = 0.828, and mean signed difference
(restored - current) = -0.707. The change is therefore scientifically material,
not output noise.

The most consequential case is ORP13: v1.3 pair-specific self-normalization
raised its mean by about 1.13 points relative to the legacy result and obscured
the persistent discrepancy. Public ORP mapping now yields a mean of 2.650,
without reusing the legacy proxy machinery.

Legacy versus restored agreement remains low (all-pair Pearson r = 0.394; mean
absolute difference = 1.172). This is expected: the legacy bundle used proxy
inputs, treated most change-point scores as high, and lacked current D2
evaluability gates. It is retained only as a historical sensitivity reference,
not as a reproducible gold standard.

## 6. Figure audit

All D6 figures use the shared publication style: Arial, 0.8 pt axes, complete
endpoint ticks, inward ticks on full frames, outward ticks on open frames,
lowercase panel labels, color-blind-aware colors, and SVG/PDF/600 dpi PNG
exports. Labels were repositioned to avoid data and colorbar occlusion.

The main and diagnostic figure bundle now communicates three distinct layers:
raw temporal-consistency evidence, D1-derived provisional context, and D7
pending status. The three-version sensitivity figure makes the method-induced
score shifts visible and should accompany any manuscript discussion of the
revision.

## 7. Remaining risks and release recommendation

1. Complete D7 and rerun the benchmark spatial-anomaly screen and final
   arbitration. Until then, do not populate or publish final `D6_forDQR`.
2. Expand ORP high-quality benchmark support. The current public pool has
   n = 312, but only R2 has adequate exact-stratum support (n = 145); the other
   regimes remain on a documented variable-level fallback.
3. Validate the 3 h event rule and change-point timing against independently
   labelled operational events.
4. Investigate DO14 with process records and spatial evidence. Its current
   result is no longer limited by D2 evaluability, but D6 cannot distinguish a
   sensor problem from a real post-anoxic inter-line process difference.
5. Keep the legacy and v1.3 bundles immutable for audit reproducibility.

Recommendation: merge the restored implementation only with its provisional
status and limitations intact. It is engineering-complete for `D6_raw`, but the
final DQR-facing scientific product remains pending real D7 arbitration.
# D6-D7 aggregation readiness addendum (2026-07-26)

The D6-D7 relationship is hierarchical rather than a flat weighted average.
D6 remains an edge-level assessment of temporal consistency between parallel
counterparts. D7 contributes node- and zone-level structural evidence that may
later support attribution or arbitration.

`scripts/run_d6_d7_readiness.py` performs a read-only interface audit. It
requires the isolated `d7_local` track, checks timestamp/pair alignment and
support status, and proves that `D6_raw`, `D6_after_D1` and `D6_forDQR` are
unchanged. It does not implement or imply a final arbitration rule.

Current D7 topology is unverified and no L3 template is available. Therefore
all matched rows remain `pending_D7_topology_or_support`, finalization is
disabled, and no D7 proxy is generated.
