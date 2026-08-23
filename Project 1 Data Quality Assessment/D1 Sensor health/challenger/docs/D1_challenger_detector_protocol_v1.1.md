# D1 Challenger Detector Final Protocol v1.1

## Decision boundary

This is an isolated retrospective challenger for D1 Spike and Step detection. It does not overwrite the released D1 score, state machine, event files, release manifest, or any D1-D5 aggregation input. Promotion requires a future or external confirmation set.

## Expert revision of the submitted proposal

The submitted proposal is feasible and addresses a genuine limitation of the released detectors. Its main risk was excessive cross-stratification rather than excessive algorithmic complexity. The final protocol therefore retains one causal multiscale GLR family and removes detector tournaments, deep learning, sensor-specific thresholds and exhaustive mechanism-by-regime acceptance tests.

Four changes are binding:

1. Hard acceptance is limited to prespecified primary amplitude-duration regions. Other analyte, route, resolution and sensor cells are descriptive and sparse cells are shown rather than interpolated.
2. The primary comparator is the released score recalibrated under the same event-rate ceiling on the same development history. If a discrete score cannot attain the ceiling exactly, the closest eligible operating point at or below it is used. The unchanged released operating point is reported separately.
3. Process-floor responsiveness is an eligibility and exclusion contract. DO_1_4 and DO_2_4 are not ordinary Step targets because comparable verified excitation is unavailable; D2 retains ownership of availability and process-floor semantics.
4. Temporary shifts shorter than one hour remain pending. The present record has no frozen minute-level Section 1.1 transform that can support confirmatory route projection.

## Mechanism contract

| Mechanism | Track | Duration | Amplitude | Primary region | Timely endpoint |
|---|---|---:|---:|---:|---:|
| Impulse spike | Minute robust innovation + GLR | 1 min | 1-5 local robust sigma | >=3 sigma | <=1 min |
| Short burst | Minute robust innovation + GLR | 2-10 min | 0.75-4 sigma | >=2 sigma and >=3 min | <=5 min |
| Temporary shift | Frozen hourly route + AR(1)-standardized GLR | 1-24 h | 0.5-3 sigma | >=1.5 sigma and >=2 h | <=3 h |
| Persistent step | Hourly GLR candidate + released KS persistence confirmation | 24-72 h | 0.5-3 sigma | >=1.5 sigma and >=24 h | candidate <=3 h |

All amplitudes are injected in the stated route before the challenger statistic. No decomposition, whitening model, AR parameter, scale floor, threshold or mapping is refitted after injection.

## Data split and threshold lock

- Development: through 31 December 2025. Used only to freeze innovation parameters and event thresholds.
- Internal validation: 1 January to 21 February 2026.
- Terminal shadow: from 22 February 2026 to record end.
- Trial count: 96 prespecified events per mechanism, comprising 64 internal-validation and 32 terminal-shadow onsets.
- Onsets for the same sensor are separated by at least 24 h within each mechanism library; different mechanisms may reuse a background and are inferred separately.
- Event alarm-rate budget: 0.05 events per sensor-day for each of the minute and hourly tracks; family budget 0.10.
- Thresholds are global within each track. Per-sensor and per-analyte thresholds are prohibited.
- Thresholds are selected from presumed-normal development history without using injected recall.

Because maintenance truth is unavailable, the development quantity is an observed alarm rate in a high-quality eligible subset, not a truth-verified false-positive rate.

## Inference and acceptance

The primary unit is a sensor-onset event. Confidence intervals and paired recall differences use 2,000 cluster bootstrap replicates with sensor-week base blocks. Promotion is mechanism-specific and requires all of the following:

- fixed alarm-rate gate passed;
- challenger minus baseline-under-the-same-FAR-ceiling recall >=0.15;
- lower 95% cluster-bootstrap bound of the paired difference >0;
- no key analyte stratum degradation exceeding 0.05;
- independent future or external confirmation before replacing the release.

AUROC and AUPRC are supplementary. Failed mechanisms, sparse cells and exclusions remain in the record.

## Execution outcome

Run `D1C-20260802-v1.1` completed the frozen development calibration, 384 event designs, exploratory 2x minute-resolution sensitivity and terminal shadow. The alarm-rate gates passed, but no mechanism met the paired promotion rule. The current challenger is therefore rejected for release replacement. The failure is an informative applicability boundary and must not be repaired by lowering the released Spike or Step thresholds on the same record.

## Next defensible step

Do not add more algorithms to this dataset. Before a challenger v2, obtain adjudicated maintenance/fault windows or a truly future record, distinguish real faults from rapid process excursions in the calibration null, and pre-register a revised event arbitration rule. Any v2 is a new development study and cannot reuse this run as confirmation.
