# Revised Temporal Out-of-Sample Re-evaluation

The 108 days (2026-04-14 through 2026-07-30) have already been inspected.
This version is **not a new blind test**. No parameter is fitted on these data.

Inputs include the unchanged archived T0 run from the separate temporal-validation
worktree: raw channel mapping, causal residuals and frozen D1/D2/D5 inference.
The original T0 files are read-only, and every consumed file has a SHA-256 entry
in a stage manifest. Private raw/T0 caches are not silently copied or published.
Reproduction from raw observations first requires that archived T0 pipeline and
the original plant data. Its PR is not merged by this revision.

Execute from the Project 1 root, substituting the archived T0 directory:

```powershell
python validation/revised_reference_20260917/run_reevaluation.py D3 --t0-root <T0>
python validation/revised_reference_20260917/run_reevaluation.py D4 --t0-root <T0>
python validation/revised_reference_20260917/run_reevaluation.py DQR --t0-root <T0>
python validation/revised_reference_20260917/audit_and_report.py --t0-root <T0>
```

## Outputs

- `outputs/D3_scores.parquet`: new frozen neutral-envelope D3 inference.
- `outputs/D4_scores.parquet`: raw-supported causal D4 inference, unchanged frozen public mapping, and evidence metadata.
- `outputs/DQR_node.parquet`, `DQR_pair.parquet`, `DQR_time_join.parquet`: decision-time joins, native formulas and explicit availability clocks.
- `outputs/Reevaluation_source_data.xlsx`: monthly estimands/coverage, paired D4 changes with 7 d block intervals, all-sensor D3 gate comparisons and QA.
- `outputs/Fig_revised_temporal_evaluation.*`: editable PDF/SVG plus 600 dpi PNG/TIFF; Arial, outward ticks, (a)-(d) panels.
- `outputs/Reevaluation_QA.json` and publication/stage manifests: formula, unchanged scores, temporal freshness and file hashes.
- `REEVALUATION_REPORT_ZH.md`: interpretation, denominators and limitations.

The figure is a quantitative comparison grid. It distinguishes coverage from
quality, then shows the combined D4 revision and D3 gate changes. It does not
assert fault truth, tune thresholds, connect absent Full monthly means, or treat
sensor-hours as independent replicates. D4 intervals resample calendar 7 d blocks
within each pair, with 2000 draws; no pooled cross-pair inferential claim is made.
