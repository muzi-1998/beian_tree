# D1-D5 v2.0 confirmatory execution guide

## Authoritative run

- Run ID: `D1D5V20-a2b2bef69861`
- Location: `outputs/confirmatory/D1D5V20-a2b2bef69861/`
- Status: `completed_with_prespecified_pending_items`
- Manifest: `run_manifest.json`
- Execution report: `D1_D5_V2_EXECUTION_REPORT.md`

The run directory is content-addressed from the frozen configuration and
confirmatory code bundle. A completed run is immutable and is reused rather
than overwritten.

## Reproduction

From `Project 1 Data Quality Assessment`:

```powershell
python scripts/run_confirmatory_v2.py
```

Focused checks:

```powershell
python -m pytest tests/test_confirmatory_v2.py -q
python C:\Users\27233\.codex\skills\nature-figure\scripts\validate_figure.py src/confirmatory_v2/figures.py --json
```

## Package contents

- `configs/`: frozen SAP, claim registry, validation design, figure contract
  and ambiguity registry snapshots.
- `temporal_split_registry.parquet`: six expanding future-month folds.
- `source_artifact_registry.parquet`: input lineage and SHA-256 values.
- `D1_*`: core-fault injection episodes, exclusions, summaries, strata and
  existing peer negative controls.
- `D2_*`: full sensor-hour OAT scores, stability summaries, reason migration
  and process-floor challenges.
- `D3_*`: Safety Gate, threshold register and warning OAT.
- `D4_*`: target/peer/common/lag mechanism trials, confidence intervals and ORP
  shrinkage sensitivity.
- `D5_*`: component ablation, blocked validation, support/coverage and locked
  admission criteria.
- `WWDQS_*`: node, pair and plant products, coverage, block-bootstrap
  uncertainty, bottleneck sensitivity and dimension ablation.
- `figures/`: SVG, PDF, 600 dpi PNG and LZW TIFF plus a figure manifest.

## Formal interfaces

- Node: equal mean of eligible D1, D2 and D5; at least two eligible dimensions.
- Pair: equal mean of target node, reference node and `D4_raw`.
- D3: independent Pass/Warn/Fail Safety Gate, never averaged.
- Missing/non-evaluable evidence: excluded and reported; never mapped to low or
  high quality.
- D5 hard Veto: disabled because Top-1 localization is below 0.80.
- A-E grade cut points: pending; continuous scores and coverage only.

## Claim boundary

The package supports a retrospective single-plant methods claim and
within-plant temporal/mechanism robustness. It does not support prospective
operational effectiveness, maintenance-truth diagnostic accuracy, learned
optimal weights, untouched terminal-test performance or cross-plant
transportability.
