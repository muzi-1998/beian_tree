# D1-D5 aggregation directory guide

This directory is a peer-level cross-dimensional integration layer. D5 is one
input dimension and is not the parent of D1-D4. No native D1-D5 scores are
overwritten.

## Configuration and code

- `configs/aggregation_v2.yaml`: frozen input hashes, estimands and validation rules.
- `src/dqr_aggregation/`: loading, aggregation, statistics, figures, reports and manifests.
- `scripts/run_dqr_aggregation.py`: complete deterministic release build.
- `scripts/verify_dqr_aggregation.py`: formula, freshness, manifest and figure verification.
- `tests/test_aggregation_v2.py`: synthetic and released-output contract tests.

## Generated outputs

- `outputs/aggregation_v2/data/`: dimension-long, node-hour, pair-hour, coverage,
  estimand-decomposition and pair-weighting sensitivity tables.
- `outputs/aggregation_v2/validation/`: statistical workbooks and machine-readable QA.
- `outputs/aggregation_v2/figures/`: 183 mm Nature-style PNG/PDF/SVG/TIFF files.
- `outputs/aggregation_v2/source_data/`: one source-data workbook per figure.
- `outputs/aggregation_v2/reports/`: scientific report, captions and this guide.
- `outputs/aggregation_v2/manifests/`: frozen run and publication manifests.

The run manifest records the scientific-generation commit for orientation, but
publication freshness is governed by exact canonical hashes of the current
configuration, every aggregation source module and all frozen D1-D5 inputs. The
publication-bundle commit or release tag is external metadata so that a manifest
never attempts to hash a commit that contains itself.

Figures 6 and 7 specified in the study plan are intentionally absent until the
prospective holdout and downstream endpoint bundles become available. Their
absence is a prespecified pending status, not a missing build artifact.
