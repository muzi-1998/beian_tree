# D1 Challenger Detector Expert Review and Execution Report

**Decision:** DO NOT PROMOTE

## Scientific boundary

The run is an isolated retrospective development and terminal-shadow study. It did not modify the released D1 scores, state machine, D1 release manifest, or any D1-D5 aggregation input. The terminal segment is not external confirmation because the record has been seen by prior D1 development.

The primary comparison uses the released detector score recalibrated on the same clean development history under the same event-rate ceiling. The hourly released score is discrete and cannot attain the ceiling exactly, so the closest eligible operating point at or below the ceiling is used. The released operating point is retained only as a secondary operational reference. Observed alarms in presumed-normal history are an alarm-rate proxy, not a truth-verified false-positive rate.

## Prespecified result

| Mechanism | Challenger recall (95% cluster CI) | Baseline under same FAR ceiling | Paired delta (95% cluster CI) | Gate |
|---|---:|---:|---:|---|
| impulse_spike | 0.000 (0.000-0.000) | 0.125 | -0.125 (-0.273-0.000) | FAIL |
| persistent_step | 0.000 (0.000-0.000) | 0.000 | 0.000 (0.000-0.000) | FAIL |
| short_burst | 0.000 (0.000-0.000) | 0.135 | -0.135 (-0.250--0.047) | FAIL |
| temporary_shift | 0.026 (0.000-0.086) | 0.000 | 0.026 (0.000-0.086) | FAIL |

## Fixed alarm-rate calibration

| Track | Role | Threshold | Events/sensor-day | 95% Poisson CI |
|---|---|---:|---:|---:|
| minute_glr | challenger | 50.591 | 0.040 | 0.026-0.058 |
| minute_glr | baseline_fixed_far | 23.956 | 0.045 | 0.031-0.065 |
| hourly_glr | challenger | 11.543 | 0.045 | 0.029-0.067 |
| hourly_glr | baseline_fixed_far | 0.786 | 0.002 | 0.000-0.010 |

## Expert judgment

1. The original proposal was scientifically defensible but over-specified where every mechanism was crossed with every sensor, regime and resolution stratum. The revised protocol keeps 96 events per mechanism while restricting hard acceptance to prespecified primary amplitude-duration regions; remaining cells are descriptive.
2. A single multiscale GLR family is adequate for a challenger. A detector tournament, deep learning or per-sensor threshold optimization would be redundant and would increase multiplicity and overfitting risk.
3. Minute and hourly tracks require different frozen innovations. Shifts below one hour remain pending because no frozen minute-level Section 1.1 transform exists for confirmatory use.
4. DO_1_4 and DO_2_4 are excluded from ordinary Step confirmation. Their process-floor responsiveness belongs to the D2 availability contract and cannot be inferred without comparable verified excitation.
5. Promotion requires future or external confirmation. Failure of a mechanism-specific gate is retained as an applicability boundary and must not be repaired by lowering the released Spike or Step thresholds on the same data.

## Outputs

All trial rows, exclusions, model parameters, threshold audits, applicability cells, shadow events, figure source data and SHA-256 hashes are stored under this immutable run directory.
