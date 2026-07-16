# D6 Parallel-redundancy Temporal Consistency

D6 evaluates whether paired sensors at homologous locations in the two parallel
biological-treatment trains retain comparable residual distributions, trends,
variability, and structural-change behaviour. The production score is an
independent raw DQR dimension. D2 controls evaluability, the real D1 scores feed
the v1.2 bilateral fuse, and D7 is required before the downstream D6-for-DQR
score can be declared final.

## Scientific boundary

- Input signal: the formal de-periodised residuals produced by Section 1.1.
- D2: pair-level evaluation gate and 24 h benchmark-continuity requirement.
- D1: true read-only v1.2 bilateral fuse input; it never changes `D6_raw`.
- D7: not currently available and never emulated. `D6_forDQR` therefore remains
  empty, while `D6_forDQR_provisional` stores the real D1-fused value with an
  explicit `pending_D7_arbitration` status.
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
outputs/comparison/   old/current/restored sensitivity workbook and figure
legacy/2026-05-30-proxy/
                      preserved proxy-era package; not valid as current results
legacy/2026-07-13-v1.3-independent/
                      frozen pre-restoration comparison inputs
```

## Reproduce

Run from `Project 1 Data Quality Assessment`:

```powershell
python ".\D6 Parallel-redundancy Temporal Consistency\scripts\run_d6_pipeline.py"
python ".\D6 Parallel-redundancy Temporal Consistency\scripts\run_d6_validation.py"
python ".\D6 Parallel-redundancy Temporal Consistency\scripts\make_d6_figures.py"
python ".\D6 Parallel-redundancy Temporal Consistency\scripts\run_d6_sensitivity.py"
python ".\D6 Parallel-redundancy Temporal Consistency\scripts\check_d6_outputs.py"
python -m pytest ".\D6 Parallel-redundancy Temporal Consistency\tests" -q
```

The current production run is identified in
`outputs/data/D6_run_manifest.json`; downstream users should verify its input
hashes rather than rely on file modification times.

## Current acceptance status

The restored v1.2 raw core uses public variable-by-regime calibration from
high-quality windows (bilateral D1 >= 4.5, bilateral D2 continuity >= 24 h,
complete residual windows). D7 screening is explicitly pending. Sparse ORP
high-quality support requires a documented variable-level fallback and remains
a calibration limitation. External labelled-event validation and final D7-aware
causal adjudication must not be claimed from the current package.
