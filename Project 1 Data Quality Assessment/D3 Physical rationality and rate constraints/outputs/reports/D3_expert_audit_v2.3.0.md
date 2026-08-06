# D3 v2.3.0 Expert Audit

## Overall Decision

D3 v2.3.0 is internally coherent and suitable for retrospective subdimension aggregation **as an independent non-compensatory gate with explicit claim limits**. Registered instrument-range failure is separated from provisional operating warnings. The supplementary `D3_total` must not be averaged into the composite score.

The module is not yet eligible to claim universally valid DO/ORP operating thresholds or independently validated alarm accuracy. Temperature/pressure/salinity, manufacturer accuracy or zero-oxygen calibration, reviewed process events, and site-approved ORP position/regime envelopes remain unavailable.

## Current Provenance

- Run ID: `RUN_D3_v2.3.0_20260806T042658Z_eae96b72`
- Observation interval: `2025-08-01 00:00` to `2026-04-13 23:59`
- Input: 368,640 one-minute rows; no D3 interpolation
- Analysis: 43,008 non-overlapping two-hour sensor windows
- Evaluated: 42,840; not evaluated: 168
- Independent inputs: raw canonical observations and D3-local peer-rate context only
- D1/D2 scores and external regime labels consumed by production score: no

## Revised Scientific Contract

1. DO `0-20 mg/L` and ORP `-1500 to 1500 mV` are the only instrument-register ranges.
2. DO `0-8 mg/L`, ORP `-400 to 200 mV`, ORP hard operating bounds, and rate limits are explicitly `provisional_expert_prior`.
3. Instrument-range evidence yields `Fail`. Operational hard/soft and persistent-rate evidence yields `Warn`; it does not automatically exclude a window from model training.
4. `DO_1_4` and `DO_2_4` use a provisional `-0.05 mg/L` soft lower edge. The original raw value is retained; no clipping is applied in the audit stream.
5. `Q_persistent_rate` replaces the scientific name `Q_rate`. A deprecated alias remains in the score workbook only for interface compatibility.
6. Soft rate evidence requires at least 3 same-sign rate estimates; hard score evidence requires at least 10; the cap requires more than 30.
7. A 1-3 min impulse-return is excluded within D3 as D1-owned spike morphology. Missing recovery jumps are never bridged.
8. Same-direction evidence in the exact parallel peer, or at least two same-line peers within +/-2 min, forms a process-coherence guard. The guard suppresses single-sensor rate attribution and is not a Veto.
9. Boundary tails and position/season envelopes are diagnostic only.

## Current Results

- Supplementary D3 score: mean `4.899`, median `5.000`, minimum `1.900`
- Gate: 34,908 `Pass`, 7,932 `Warn`, 0 `Fail`, 168 `NotEvaluated`
- Use tag: 34,908 `train_ok`, 7,905 `train_ok_with_operational_warning`, 27 `review_only`, 0 `invalid`
- Recorded event windows: 27 hard-bound warnings, 41 soft-bound low-score windows, and 260 guarded coherent shocks
- Point hard-rate excursion windows: 1,448
- Final persistent hard-rate windows in observed data: 0
- Windows with impulse-return exclusion: 2,001
- Windows with process-coherence exclusion: 301
- Maximum final unguarded hard-rate run: 7 min

The absence of observed persistent-rate events means that real-data threshold sensitivity is not informative: all sampled rate-limit variants contain zero events. It must not be reported as proof of threshold robustness.

## DO4 Zero-Deadband Finding

`DO_1_4` contains 25.31% negative observations, but they are limited to `-0.03` to `-0.01 mg/L` at `0.01 mg/L` resolution. The former zero soft edge therefore classified 25.31% of observed minutes as soft-low violations. Edges at `-0.03`, `-0.05`, and `-0.10 mg/L` all reduce that burden to zero in the current record. `DO_2_4` contains only nine `-0.01 mg/L` observations.

The production edge is provisionally locked at `-0.05 mg/L`, not because it is universally optimal, but because it safely covers the observed resolution-scale noise while retaining a warning interval from `-0.05` to the `-0.2 mg/L` hard tolerance. Manufacturer accuracy or a zero-oxygen calibration is still required for final lock.

## DO Upper-Bound Finding

Values above `8 mg/L` occur, but remain rare in this record. Maximum values exceed `10 mg/L` in several aerobic channels. Their occurrence is not confined to winter, so a date-only seasonal replacement would not constitute a defensible saturation model. The `8 mg/L` line remains a provisional operating warning; dynamic oxygen-saturation correction is pending synchronized temperature, pressure, and salinity.

## ORP Position Finding

ORP soft-bound departures are almost exclusively low-side. ORP-2-3 has soft-low excursions in 71.2% of two-hour windows and ORP-1-3 in 18.5%; high-side excursions are effectively absent. In winter, 88.9% of observed ORP-2-3 minutes are below `-400 mV`.

This pattern is consistent with a strong position/line/regime effect, but it cannot by itself distinguish expected terminal-anoxic conditions from fouling or reference-electrode drift. Position- and season-stratified median/MAD envelopes are exported for diagnosis only. They do not replace the formal warning boundary before process-engineer review and independently adjudicated events.

## Rate Construct Validation

The controlled morphology matrix behaves as intended:

- 1 min and 2 min spikes: impulse-return excluded; no D3 persistent-rate response
- 5 min block: point excursion only; no persistent response
- 30 min rapid ramp: strong persistent response, `Q_persistent_rate=1.10`
- Permanent step: transient point response only; D1 owns the step construct
- Coherent multi-sensor ramp: raw point evidence retained, final D3 rate loss guarded
- Missing recovery jump: no bridged rate event

The ORP dose-response grid shows that rate magnitude alone is insufficient: rates above the hard threshold require enough same-sign estimates to pass the persistence gate. A 10 min injected ramp does not necessarily create 10 valid rate estimates because rates are interval-based and robust smoothing reduces edge support; this duration contract must be described in methods.

Observed D1 spike/step windows have zero overlap with final D3 persistent-rate events because no observed D3 persistent event survives the current rules. Spearman loss correlations are not estimable when the D3 loss is constant. This supports non-duplication in the current dataset but does not replace a shared raw-domain injection experiment.

## Threshold Sensitivity

The sampled soft-envelope event set is sensitive to width perturbation:

- multiplier 0.8: Jaccard `0.609`
- multiplier 0.9: Jaccard `0.757`
- multiplier 1.1: Jaccard `0.786`
- multiplier 1.2: Jaccard `0.214`

Therefore the current soft boundaries are not statistically locked. The result supports transparent warning-only use and argues against treating these rules as validated data-failure thresholds.

## Figure Decision

Eight figures are generated as editable SVG/PDF and 600-dpi PNG with Arial-compatible fonts, 0.8-pt axes, outward ticks for open axes, inward ticks for full frames, lowercase parenthesized panel labels, and source-data-backed quantitative panels.

The most manuscript-relevant revised figures are:

- `fig4_persistent_rate_construct`: point-versus-persistent evidence, exclusions, duration support, and empirical D1-D3 overlap
- `fig6_gate_and_directional_profile`: supplementary score, gate status, guarded events, and low/high boundary direction
- `fig8_boundary_rate_validation`: DO4 deadband, ORP directionality, injected morphology, and threshold sensitivity

Legacy `fig4_rate_constraints` and `fig6_events_profile` are superseded and must not be used in the manuscript.

## Executed Versus Pending

### Executed

- DO4 sensor-group contract and provisional zero deadband
- low/high boundary rates and exceedance magnitudes
- renamed soft-dominant window metric
- explicit provisional threshold provenance
- analyte-specific instrument-veto registry audit
- persistent same-sign rate scoring
- unique persistent-event counting without soft/hard duplication
- impulse-return exclusion
- process-coherence attribution guard
- missing-recovery protection
- controlled morphology and dose-response validation
- +/-10% and +/-20% threshold perturbation
- empirical D1 spike/step versus D3 persistent-rate overlap
- updated gate interface, figures, source data, tests, and manifest

### Pending External Evidence

- dynamic DO saturation boundary using synchronized temperature, pressure, and salinity
- final DO4 deadband using manufacturer accuracy or zero-oxygen calibration
- site-approved ORP position/regime envelopes
- position- and condition-specific rate thresholds
- independent event adjudication and precision/recall
- a fully shared raw-domain D1-D3 injection pipeline with frozen transforms
- process-engineer approval for Grade B operating warnings

These pending items limit threshold generalization and alarm-validity claims, but they do not prevent retrospective aggregation when D3 is used as the stated Pass/Warn/Fail gate.
