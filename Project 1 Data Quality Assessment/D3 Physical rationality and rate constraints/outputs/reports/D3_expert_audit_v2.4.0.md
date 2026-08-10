# D3 v2.4.0 Expert Audit

## Decision

D3 v2.4.0 is internally coherent for retrospective use as an independent physical-plausibility and persistent-rate gate. It is suitable for subdimension aggregation through `D3_gate_status`, with the stated claim limits. The supplementary `D3_total` remains descriptive and must not be averaged into the composite as if provisional operating limits were verified sensor-failure labels.

## Frozen Run

- Run ID: `RUN_D3_v2.4.0_20260810T013252Z_790fee40`
- Study interval: 2025-08-01 00:00 to 2026-04-13 23:59 at 1 min
- Sensor-windows: 43,008; evaluated: 42,840; not evaluated: 168
- Gate outcome: Pass 34,908; Warn 7,932; Fail 0; NotEvaluated 168
- D3 total: mean 4.865; median 5.000; minimum 1.675
- Publication figures: 9; Nature static audit: 0 failures, 0 warnings

## Accepted Method Changes

1. **DO4 physical zero and measurement tolerance are separated.** The physical soft lower boundary is 0 mg/L. The provisional `-0.05 mg/L` parameter is used only as a zero-equivalence tolerance.
2. **DO4 has four auditable states.** Nonnegative, zero-equivalent `[-0.05, 0)`, offset-warning `[-0.20, -0.05)`, and severe-negative `<-0.20 mg/L` evidence are exported separately.
3. **DO4 no longer inherits the aerobic 8 mg/L upper warning.** Its production upper warning is disabled pending a time-blocked post-anoxic template lock.
4. **Raw and process views are separated.** `DO_raw` remains the D3 scoring input. `DO_physicalized=max(DO_raw,0)` is exported only for downstream process calculations.
5. **Persistent rate uses two mutually exclusive levels.** Complete 3-9 min soft-only episodes and >=10 min hard-persistent cores are mapped separately and combined as 0.30/0.70. A hard episode is not counted again as soft-only.
6. **The 30 min non-compensatory cap, impulse-return exclusion, gap-safe derivative, and process-coherence guard remain active.** D3 does not read D1 or D2 scores in production.
7. **ORP interval sensitivity has one canonical implementation.** Width is perturbed around a fixed center; endpoint multiplication that shifted the center was removed from the confirmatory workflow.

## Results of the Revised Contracts

- DO_1_4 had 25.32% physical-negative observations, all within the zero-equivalent interval; offset-warning and severe-negative rates were 0. DO_2_4 physical-negative observations were 0.0024%, also entirely zero-equivalent. Neither channel incurred a DO4 soft-low or inherited soft-high penalty.
- Persistent soft-only evidence occurred in 5,569 windows: 4,130 DO and 1,439 ORP. No >=10 min hard-persistent event was observed. This evidence produces `Warn`, not data-quality `Fail`.
- Controlled morphology validation passed all 8 prespecified scenarios, including spike exclusion, soft ramp detection, hard ramp detection, coherent-process guarding, and missing-recovery protection.
- Rate-limit event-set Jaccard was 0.723, 0.861, 1.000, 0.800, and 0.771 for multipliers 0.8-1.2. The 0.8 result falls below the 0.75 stability reference, so rate thresholds remain provisional.
- Soft-envelope event-set Jaccard was 0.609, 0.757, 1.000, 0.786, and 0.214. The strong edge sensitivity confirms that the operating envelopes are warning priors rather than validated universal limits.

## DO4 Upper-Template Audit

A frozen 70/30 temporal split used D1 and D2 only as a validation-window filter; these scores never enter production D3.

- DO_1_4: 2,727 calibration hours and 1,329 validation hours; candidate upper 0.1087 mg/L; validation exceedance rate 0.226%. Statistical support passed, but the candidate remains disabled pending process/event review.
- DO_2_4: 98 calibration hours and 10 validation hours; candidate upper 1.0588 mg/L. Independent support failed, so promotion is prohibited.

The non-exchangeable monthly distributions of DO_1_4 and DO_2_4 rule out a pooled unconditional DO4 upper bound.

## Weight Decision

The accepted v2.4 change updates the persistent-rate construct while retaining the frozen outer weights `0.50/0.20/0.30`. Relative to v2.3, the `<3` event set is unchanged (Jaccard 1.000), while the continuous score responds to 3-9 min soft-only episodes.

The proposed `0.45/0.35/0.20` rebalance is sensitivity-only. It generated 2,478 additional low-score windows, concentrated in ORP3, and produced a low-event Jaccard of 0.0108 versus v2.3. Because ORP position envelopes lack external labels and site approval, promoting this candidate would overstate the evidence.

## Pending, Not Executed

- Dynamic aerobic DO saturation limits require synchronized local water temperature, barometric pressure, and salinity. These covariates are absent from the canonical D3 input.
- The final DO4 zero-equivalence tolerance requires manufacturer accuracy or zero-oxygen calibration records; `-0.05 mg/L` remains provisional.
- DO4 upper templates require process/event review, and DO_2_4 requires substantially more independent high-quality support.
- ORP1/ORP2/ORP3 position- and regime-conditioned envelopes remain diagnostic until site review and independent event adjudication.
- Rate limits and the 3/10/30 min duration contract require reviewed real events or an expanded shared raw-domain D1-D3 injection study.
- Maintenance labels, expert sign-off, and external-plant transfer validation remain outside the current data package.

## Publication Position

The defensible manuscript claim is that D3 provides an auditable, dimension-independent gate separating instrument-range failure, provisional operating warning, zero-equivalent post-anoxic DO, persistent single-channel rate behavior, and coherent process shocks. It does not establish universal physical thresholds or alarm accuracy without the pending external evidence.
