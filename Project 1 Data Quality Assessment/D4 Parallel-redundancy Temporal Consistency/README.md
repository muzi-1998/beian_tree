# D4 Parallel-redundancy Temporal Consistency

D4 evaluates whether paired sensors at homologous locations in the two parallel
biological-treatment trains retain comparable residual distributions, trends,
variability, and structural-change behaviour. The production score is an
independent raw DQR dimension. D2 controls observability, while D1 and D5 are
kept in interpretation and action-governance interfaces that cannot alter the
numeric `D4_raw` score.

## Scientific boundary

- Input signal: the formal de-periodised residuals produced by Section 1.1.
- D2: pair-level evaluation gate and 24 h benchmark-continuity requirement.
- D1: interpretation-only; it never changes `D4_raw`.
- D5: the report interface provides structural context, while the separate
  gate interface may provide an attribution Guard or sensor-identity Veto only
  where node-level L3 validation permits the corresponding claim.
- `python scripts/run_d4_d5_readiness.py` finalizes the scientific D4 value
  non-destructively from `D4_raw`. It verifies protected numeric columns and
  records whether any D5 action gate is applicable. No D5 proxy is generated.
- D4 detects pair asymmetry. It cannot by itself attribute the cause to a sensor
  fault or a real local process asymmetry.

## Layout

```text
configs/              versioned D4 configuration and pair definitions
docs/                 expert audit and scientific decision record
scripts/              reproducible pipeline, validation, and figure entry points
src/d4/               configuration, scoring, validation, output, and figure code
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
python ".\D4 Parallel-redundancy Temporal Consistency\scripts\run_d4_pipeline.py"
python ".\D4 Parallel-redundancy Temporal Consistency\scripts\run_d4_validation.py"
python ".\D4 Parallel-redundancy Temporal Consistency\scripts\make_d4_figures.py"
python ".\D4 Parallel-redundancy Temporal Consistency\scripts\run_d4_sensitivity.py"
python ".\D4 Parallel-redundancy Temporal Consistency\scripts\check_d4_outputs.py"
python -m pytest ".\D4 Parallel-redundancy Temporal Consistency\tests" -q
```

The current production run is identified in
`outputs/data/D4_run_manifest.json`; downstream users should verify its input
hashes rather than rely on file modification times.

## Current acceptance status

The restored v1.2 raw core uses public variable-by-regime calibration from
high-quality windows (bilateral D1 >= 4.5, bilateral D2 continuity >= 24 h,
complete residual windows). The numeric aggregation source remains `D4_raw`;
D1/D2 benchmark admission is an evidence-quality screen, not a score blend.
Sparse ORP high-quality support requires a documented variable-level fallback
and remains a calibration limitation. External labelled-event validation and
action-grade D5 causal attribution must not be claimed from the current package.
