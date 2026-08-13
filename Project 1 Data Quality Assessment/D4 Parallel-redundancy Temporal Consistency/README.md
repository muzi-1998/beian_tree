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
outputs/data/         current Excel deliverables plus a hash-bound manifest
outputs/figures/      six main and six supplementary publication figures
outputs/figure_source_data/
                      one traceable Excel source workbook per figure
outputs/qa/           automated figure-bundle QA
outputs/comparison/   legacy and v1.4-v1.5.1 method-sensitivity workbooks
outputs/integration/D4V151_composite_refresh/
                      SHA-bound retrospective composite refresh
legacy/2026-05-30-proxy/
                      preserved proxy-era package; not valid as current results
legacy/2026-07-13-v1.3-independent/
                      frozen pre-restoration comparison inputs
legacy/2026-07-26-v1.4-canonical/
                      frozen pre-common-support production package
```

## Reproduce

Run from `Project 1 Data Quality Assessment`:

```powershell
python ".\D4 Parallel-redundancy Temporal Consistency\scripts\run_d4_pipeline.py"
python ".\D4 Parallel-redundancy Temporal Consistency\scripts\run_d4_validation.py"
python ".\D4 Parallel-redundancy Temporal Consistency\scripts\run_d4_episode_validation.py"
python ".\D4 Parallel-redundancy Temporal Consistency\scripts\run_d4_method_sensitivity.py"
python ".\D4 Parallel-redundancy Temporal Consistency\scripts\run_d1_d4_redundancy_audit.py"
python ".\D4 Parallel-redundancy Temporal Consistency\scripts\make_d4_figures.py"
python ".\D4 Parallel-redundancy Temporal Consistency\scripts\audit_d4_figures.py"
python ".\D4 Parallel-redundancy Temporal Consistency\scripts\run_d4_d5_readiness.py"
python ".\D4 Parallel-redundancy Temporal Consistency\scripts\run_d4_composite_refresh.py"
python ".\D4 Parallel-redundancy Temporal Consistency\scripts\check_d4_outputs.py"
python -m pytest ".\D4 Parallel-redundancy Temporal Consistency\tests" -q
```

The current production run is identified in
`outputs/data/D4_run_manifest.json`; downstream users should verify its input
hashes rather than rely on file modification times.

## Current acceptance status

The v1.5.1 raw core uses public variable-by-regime calibration from development-
period high-quality windows (bilateral D1 >= 4.5, bilateral D2 continuity >=
24 h, and at least 80% synchronous common support). W1 and KS are calculated on
the same timestamp support. Regime-template admission also requires at least six
independent 7 d development blocks; tail-quantile precision is reported as an
evidence grade and is not used to tune the threshold retrospectively. The
numeric aggregation source remains `D4_raw`;
D1/D2 benchmark admission is an evidence-quality screen, not a score blend.
Sparse ORP high-quality support requires a documented variable-level fallback
and remains a calibration limitation. The February-April period is an internal
chronological validation period, not a genuinely untouched terminal test,
because upstream transforms had already been developed on the study period.
External labelled-event validation and action-grade D5 causal attribution must
not be claimed from the current package.

## Publication figure set

The six main figures cover the scientific construct, pair-level mechanism
profile, temporal burden and evaluability, formal field episodes, controlled
mechanism validation, and component/resolution limitations. Six supplementary
figures retain all-pair trajectories, trend concordance, the numeric-
independence audit, W1/KS construct ablation, and event-duration inference.
The sixth supplementary figure audits D1-D4 score dependence, formal-event
overlap, and leave-dimension-out pair-composite sensitivity. All
quantitative panels use `usable_for_D4` as the
analysis denominator unless a calibration or integration denominator is stated
explicitly. Formal field cases are selected from `D4_event_windows.xlsx` and
remain detection examples with causal attribution pending.

Every figure is exported as editable SVG and PDF plus 600 dpi PNG and LZW TIFF.
The matching workbook in `outputs/figure_source_data/` records the plotted data,
sample support, interval definition, and calibration provenance. The figure
entry point also removes the superseded eight-figure bundle by fixed filename so
old and current results cannot coexist silently.
