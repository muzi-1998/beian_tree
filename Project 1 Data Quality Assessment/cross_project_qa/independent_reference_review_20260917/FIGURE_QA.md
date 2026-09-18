# Figure review

The new reference-admission figure and revised temporal-evaluation figure are
quantitative comparison grids, not model-selection charts. Source data are the
adjacent Excel workbooks. Both use Arial, editable PDF/SVG and 600 dpi PNG/TIFF.
No interpolated performance or fabricated measurements are displayed.

Local Nature source preflight: both plotting sources have 13 passes, no failures,
and one reviewed advisory each:

- `run_reference_sensitivity.py`: complete-pair exclusion is intentional. Every
  contrast exports `n_common`; the warning comparison explicitly uses identical
  neutral support. Empty-union Jaccard remains NA, not 0 or 1.
- `audit_and_report.py`: the random generator resamples observed 7-day blocks for
  confidence intervals; it does not simulate measurement observations. Common
  support and independent block counts are exported for each pair.

Visual inspection covered the two new comparison figures, D3 temperature
envelopes, the D4 evidence-chain schematic and D5 dual-scope complementarity.
D3's panel-c legend was moved into free space; schematic labels were separated;
D5 dark heatmap cells now have white text. D3 has 11 passing figure audits, D4
12; D5 publication and DQR have separate automated figure bundle checks.
DQR evidence-availability legends are separated from titles and trajectories;
the dual-scope confidence-interval legend occupies the central empty band.

SVG trailing whitespace is normalized only as packaging. No plotted values or
image contents are altered. Static checks complement rather than replace visual
inspection and do not certify journal acceptance or scientific validity.
