# D1-D5 aggregation directory guide

The aggregation module is intentionally housed under D5 because D5 is the final
sensor-level evidence dimension, while the output remains a distinct D1-D5
integration layer. No native D1-D5 scores are overwritten.

## Configuration and code

- `configs/aggregation_v2.yaml`: frozen input hashes, estimands and validation rules.
- `src/d5_aggregation/`: loading, aggregation, statistics, figures, reports and manifests.
- `scripts/run_dqr_aggregation.py`: complete deterministic release build.
- `scripts/verify_dqr_aggregation.py`: formula, freshness, manifest and figure verification.
- `tests/test_aggregation_v2.py`: synthetic and released-output contract tests.

## Generated outputs

- `outputs/aggregation_v2/data/`: dimension-long, node-hour, pair-hour and monthly coverage tables.
- `outputs/aggregation_v2/validation/`: statistical workbooks and machine-readable QA.
- `outputs/aggregation_v2/figures/`: 183 mm Nature-style PNG/PDF/SVG/TIFF files.
- `outputs/aggregation_v2/source_data/`: one source-data workbook per figure.
- `outputs/aggregation_v2/reports/`: scientific report, captions and this guide.
- `outputs/aggregation_v2/manifests/`: frozen run and publication manifests.

Figures 6 and 7 specified in the study plan are intentionally absent until the
prospective holdout and downstream endpoint bundles become available. Their
absence is a prespecified pending status, not a missing build artifact.
