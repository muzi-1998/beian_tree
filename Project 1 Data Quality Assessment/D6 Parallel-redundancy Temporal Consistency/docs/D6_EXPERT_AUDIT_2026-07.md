# D6 Expert Audit and Restored v1.2 Contract (2026-07)

## 1. Executive conclusion

The restored implementation, `d6-v1.4-restored-v12-20260714`, is the current
reproducible D6 result. It restores the scientifically important v1.2 rules
without recreating unavailable evidence: a strict high-quality benchmark,
public mapping by variable and operating regime, change-point time-difference
scoring with a 7 d auxiliary window, a 3 h event threshold, and separate
`D6_raw` and downstream-arbitration paths.

`D6_raw` is an independent temporal-consistency dimension. D2 only determines
whether a D6 window is evaluable. Real D1 scores produce
`D6_forDQR_provisional`; they do not overwrite `D6_raw`. Because D7 is not yet
available, final `D6_forDQR` is intentionally null and every downstream result
is marked `provisional_pending_D7`. No D7 score, state, or proxy is generated.

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
3. D1 supplies real bilateral health scores only to the downstream provisional
   fuse. The independent `D6_raw` remains unchanged.
4. D7 is required for final arbitration. While absent, the final
   `D6_forDQR` field remains null.

### High-quality public benchmark

Benchmark windows require bilateral D1 scores >= 4.5, bilateral usable D2
context, at least 24 h continuous coverage, and sufficient pair completeness.
The v1.2 D7 spatial-anomaly exclusion cannot yet be executed and is explicitly
recorded as pending rather than replaced with a proxy.

The final benchmark contains 2,140 windows. DO has adequate regime-specific
support: R0 = 1,252, R1 = 215, R2 = 344, and R3 = 232. ORP has only 97 total
windows: R0 = 17, R1 = 29, R2 = 31, and R3 = 20. Consequently, DO uses public
variable-by-regime mappings, whereas ORP uses a documented variable-level
public fallback. No mapping is calibrated independently for an individual
sensor pair.

Continuous risks are mapped through public q50/q75/q90/q97.5 thresholds. Each
output row stores mapping scope, support size, calibration quality, and a shared
calibration identifier, `D6CAL-V14-20f697901061`.

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

- Run ID: `D6V14_20260714_024929`.
- Configuration: `d6-v1.4-restored-v12-20260714`.
- Calibration: `D6CAL-V14-20f697901061`.
- Data span: 2025-08-01 00:00 to 2026-04-13 23:50.
- Output size: 42,847 pair-windows across seven pairs.
- D2 source run: `D2V1_20260710_1733`.
- Overall evaluability: 79.10%.

The run manifest records SHA-256 hashes for Section 1.1 residuals and time-base
contract, D1 scores and regime templates, D2 scores, D6 configuration, pipeline
code, and scoring code. This makes the workbook bundle traceable to exact input
and code states.

| Pair | Mean D6_raw | Low-score rate | Evaluable rate | Mean Q_cp | 3 h events |
|---|---:|---:|---:|---:|---:|
| DO11 | 3.327 | 33.3% | 97.3% | 2.772 | 126 |
| DO12 | 3.340 | 28.9% | 98.8% | 2.624 | 138 |
| DO13 | 3.140 | 43.5% | 98.8% | 2.764 | 150 |
| DO14 | 3.138 | 43.0% | 23.2% | 2.426 | 40 |
| ORP11 | 3.488 | 25.7% | 93.1% | 3.139 | 143 |
| ORP12 | 3.150 | 46.5% | 74.9% | 3.529 | 142 |
| ORP13 | 2.759 | 63.3% | 67.6% | 2.840 | 139 |

The DO14 low-score rate is conditional on evaluable windows. Its 23.2%
evaluability is a material uncertainty and must accompany any interpretation.
ORP13 remains the clearest persistent pair-consistency concern, but D6 alone
cannot identify which sensor, or whether a local process asymmetry, caused it.

## 4. Internal validation

| Scenario | Metric | Estimate | 95% CI | Criterion | Status |
|---|---|---:|---:|---:|---|
| Unilateral drift | ROC AUC | 0.912 | 0.881-0.944 | >= 0.70 | Pass |
| Unilateral step | ROC AUC | 0.930 | 0.899-0.958 | >= 0.70 | Pass |
| Unilateral freeze | ROC AUC | 0.807 | 0.769-0.858 | >= 0.70 | Pass |
| Unilateral spike | ROC AUC | 0.578 | 0.560-0.604 | Secondary only | Expected limitation |
| Synchronous switch | Conditional new FAR | 0.088 | 0.029-0.162 | <= 0.10 | Point estimate passes |
| Common-mode drift | Conditional new FAR | 0.088 | 0.029-0.162 | <= 0.10 | Point estimate passes |

The synchronous tests use a paired conditional false-alarm rate among windows
that were non-alarming before injection. This avoids confusing pre-existing D6
events with injection-induced false alarms. Its confidence interval crosses
0.10, so more external normal-transition examples are still required. Isolated
spikes remain primarily a D1 responsibility and are not a required D6
acceptance scenario.

These are internal chronological-holdout stress tests, not external clinical or
plant-operation validation. They support implementation correctness and
sensitivity, but do not replace independently labelled field events.

## 5. Three-version sensitivity analysis

The comparison workbook applies one common 3 h event definition to all three
versions and aligns scores by pair and timestamp.

| Pair | Legacy v1.2 proxy | Current v1.3 | Restored v1.4 |
|---|---:|---:|---:|
| DO11 | 4.822 | 3.981 | 3.327 |
| DO12 | 4.743 | 3.989 | 3.340 |
| DO13 | 4.492 | 3.788 | 3.140 |
| DO14 | 4.706 | 4.034 | 3.138 |
| ORP11 | 3.828 | 3.784 | 3.488 |
| ORP12 | 3.370 | 3.772 | 3.150 |
| ORP13 | 2.748 | 3.874 | 2.759 |

Restored v1.4 versus current v1.3 has all-pair Pearson r = 0.705, Spearman rho
= 0.694, mean absolute difference = 0.822, and mean signed difference
(restored - current) = -0.704. The change is therefore scientifically material,
not output noise.

The most consequential case is ORP13: v1.3 pair-specific self-normalization
raised its mean by about 1.13 points relative to the legacy result and obscured
the persistent discrepancy. Public ORP mapping restores a mean of 2.759, close
to the historical 2.748, without reusing the legacy proxy machinery.

Legacy versus restored agreement remains low (all-pair Pearson r = 0.345; mean
absolute difference = 1.182). This is expected: the legacy bundle used proxy
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
2. Expand ORP high-quality benchmark support. The current n = 97 justifies the
   documented variable fallback but not regime-specific ORP claims.
3. Validate the 3 h event rule and change-point timing against independently
   labelled operational events.
4. Treat DO14 conclusions as low-confidence because of limited evaluability.
5. Keep the legacy and v1.3 bundles immutable for audit reproducibility.

Recommendation: merge the restored implementation only with its provisional
status and limitations intact. It is engineering-complete for `D6_raw`, but the
final DQR-facing scientific product remains pending real D7 arbitration.
