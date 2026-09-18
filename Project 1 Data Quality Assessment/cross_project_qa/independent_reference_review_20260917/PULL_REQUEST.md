## Scope

Separate D3/D4 primary reference qualification from other dimensions' numerical scores. Preserve independent D1/D2/D5 outputs, immutable historical baselines and the distinction between quality, evidence strength and integration gates.

## Scientific changes

- D3 v2.8: neutral observed/non-imputed/in-range/temperature-valid raw reference, unchanged estimator; frozen D1/D2-screened reference becomes sensitivity only. Position 3 remains diagnostic.
- D4 v1.6: synchronized raw support, complete trailing 24 h span and development-fitted stable context replace D1 screening and D2-derived scoring gates. Observed stasis remains present evidence.
- Public analyte-by-regime calibration and independent-block/percentile precision metadata remain separate from D4_raw.
- D5 publication dependency audit refreshed without changing its scoring, support or OOD model.
- DQR v2.4 and a separately archived revised temporal out-of-sample re-evaluation regenerated. The previously inspected 108 days are not presented as a new blind test.

## Results and limitations

D3 alpha changes by about 20-35%; old-screened versus neutral D4 low-hour Jaccard is 0.38-0.75. These are material sensitivity findings, not a claim of unchanged results. D5 formal report coverage in the extension remains 2.546%, with no support promotion. Computational/scoring dependency separation does not establish statistical independence or field fault-truth validity.

## Verification

- D3: 34 tests; D4: 28; D5: 35; shared context: 2; DQR: 8 plus 24 verifier checks.
- Revised temporal evaluation: 23 checks, immutable D1/D2/D5 scores and causal timestamp joins.
- D3: 11 figure audits; D4: 12 figure audits; D5/DQR publication bundles, input hashes, output hashes and code/config freshness verified.
- New neutral-reference CI checks deletion/perturbation invariance and the cross-project release manifest.

See `EXECUTION_REPORT_ZH.md`, `FIGURE_QA.md` and the sensitivity source workbooks in this directory. T0 causal residual archives remain on their existing temporal-validation branch; this PR does not merge PR #26 or overwrite that archive. No unrelated local files or raw source workbooks are included.

## Merge policy

Draft for scientific and engineering review. Do not automatically merge main.
