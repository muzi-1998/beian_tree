# D6 Parallel-redundancy Temporal Consistency

D6 evaluates whether paired sensors at homologous locations in the two parallel
biological-treatment trains retain comparable residual distributions, trends,
variability, and structural-change behaviour. The production score is an
independent DQR dimension: D2 controls evaluability, while D1 and future D7
evidence are interpretation context and never alter the D6 score.

## Scientific boundary

- Input signal: the formal de-periodised residuals produced by Section 1.1.
- D2: pair-level evaluation gate only; missingness is not penalised again in D6.
- D1: read-only context only; it is not used for mapping or score modification.
- D7: not currently available and not emulated. Future spatial consensus belongs
  in downstream evidence fusion rather than the D6 core score.
- D6 detects pair asymmetry. It cannot by itself attribute the cause to a sensor
  fault or a real local process asymmetry.

## Layout

```text
configs/              versioned D6 configuration and pair definitions
docs/                 expert audit and scientific decision record
scripts/              reproducible pipeline, validation, and figure entry points
src/d6/               configuration, scoring, validation, output, and figure code
tests/                formula and symmetry regression tests
outputs/data/         ten current Excel deliverables plus a hash-bound manifest
outputs/figures/      eight figures in editable SVG, PDF, and 600 dpi PNG
outputs/qa/           automated figure-bundle QA
legacy/2026-05-30-proxy/
                      preserved proxy-era package; not valid as current results
```

## Reproduce

Run from `Project 1 Data Quality Assessment`:

```powershell
python ".\D6 Parallel-redundancy Temporal Consistency\scripts\run_d6_pipeline.py"
python ".\D6 Parallel-redundancy Temporal Consistency\scripts\run_d6_validation.py"
python ".\D6 Parallel-redundancy Temporal Consistency\scripts\make_d6_figures.py"
python ".\D6 Parallel-redundancy Temporal Consistency\scripts\check_d6_outputs.py"
python -m pytest ".\D6 Parallel-redundancy Temporal Consistency\tests" -q
```

The current production run is identified in
`outputs/data/D6_run_manifest.json`; downstream users should verify its input
hashes rather than rely on file modification times.

## Current acceptance status

The independent D6 core is reproducible and passes all required internal
chronological stress tests. Isolated-spike sensitivity remains intentionally
non-blocking because D1 owns point-spike detection. External labelled-event
validation and D7-aware causal adjudication remain future work and must not be
claimed from the current package.
