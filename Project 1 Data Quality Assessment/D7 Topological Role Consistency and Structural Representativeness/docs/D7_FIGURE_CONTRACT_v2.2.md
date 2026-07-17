# D7 Figure Contract v2.2

## Scope

This contract governs the five D7 manuscript figure groups. It follows the
`nature-figure` workflow: define the claim and evidence hierarchy first, retain
source-data integrity, use a consistent visual language, and verify editable and
raster exports at final publication size.

The figures visualize frozen D7 outputs. They do not recompute D7 business
metrics, alter topology, infer labels, or release `D7_forDQR`.

## Global visual contract

- Backend: Python/matplotlib only.
- Final width: 183 mm (double-column); panel-specific heights are fixed in code.
- Typography: Arial first, 7 pt base text, bold reserved for panel labels and
  short panel conclusions.
- Panel labels: `(a)`, `(b)`, `(c)`, `(d)` as applicable.
- Axes: 0.75 pt; open axes use outward ticks, full-frame heatmaps use inward
  ticks on all four sides.
- Palette: muted blue for primary spatial evidence, teal for passed/available,
  orange for pending or limited support, red for failed/blocked, and neutral grey
  for references and scaffolding. Color is reinforced by marker shape, line
  position, or explicit text.
- Labels: direct labels or frameless legends; annotations use a translucent white
  background only where needed to preserve the visibility of underlying data.
- Exports: editable SVG and PDF plus 600 dpi PNG and LZW-compressed TIFF.
- Source data: `outputs/plot_data/D7_plot_data.parquet` and `.csv`, with a frozen
  manifest containing source run and hash provenance.
- Exclusions: no rendering-convenience sampling. Only non-finite values are
  omitted by the relevant plotting primitive; source row counts remain recorded.

## Figure D7-1: Evaluation boundary

**Claim.** D7 evaluates declared parallel spatial roles and can retain raw
research evidence, while unverified topology blocks the production score.

**Evidence hierarchy.** Panel (a) is the dominant declared-topology schematic;
panel (b) quantifies Local-track applicability; panel (c) states the evidence and
release boundary. Schematic coordinates are not presented as surveyed geometry.

**Review risk.** Field topology and two-person approval remain pending. The
figure must not imply that `D7_forDQR` is available.

## Figure D7-2: Population-level structure

**Claim.** Low D7 periods are sensor- and time-specific, while effective template
support is dominated by lower tiers.

**Evidence hierarchy.** Panel (a) is the hero heatmap of daily lower-quartile
scores; panel (b) shows the full finite score distributions; panel (c) reports
template counts by support tier.

**Source-data rule.** Panel (b) contains every finite hourly `D7_raw` value from
the frozen Local run. No display sample is permitted.

## Figure D7-3: Event-level evidence chain

**Claim.** Multiple independent spatial components converge during the selected
persistent low-score interval, and the target-excluded attribution identifies a
localized structural contributor.

**Evidence hierarchy.** Panel (a) is the full component time series with the
candidate interval shaded; panel (b) is the target-excluded node influence rank;
panel (c) supplies D7-to-D6 consensus context.

**Review risk.** The event is unlabeled and therefore remains review evidence,
not a confirmed sensor fault or process event. The target highlight must not be
described as ground-truth localization.

## Figure D7-4: Validation and invariance

**Claim.** Discrimination and specificity criteria pass, Local-Sensitivity
invariance is retained, but Top-1 localization remains below its release target.

**Evidence hierarchy.** Panel (a) gives the overall release criteria and targets;
panel (b) decomposes Top-1 by injected scenario; panel (c) shows negative-control
false alarm rates with empirical 95% intervals; panel (d) compares invariance
estimates with prespecified targets.

**Visual rule.** Filled circles are estimates, open diamonds are targets, and
line segments show the estimate-target gap. Pass/fail color never replaces the
explicit target marker.

## Figure D7-5: Governance and release

**Claim.** Template support and state occupancy are auditable, topology-drift
candidates remain report-only, and production release remains closed.

**Evidence hierarchy.** Panels (a) and (b) summarize support and state occupancy;
panel (c) is the dominant report-only topology screen; panel (d) is the release
gate chain.

**Review risk.** Candidate mappings cannot modify the declared production
topology. A blocked gate must not be presented as a failed scientific result; it
is a governance condition for production use.

## Final QA contract

1. Run `python scripts/make_d7_figures.py`.
2. Run the `nature-figure` static source preflight on
   `src/d7_local/figures/make_figures.py` with the Python backend.
3. Confirm all five SVGs retain text nodes and reference Arial.
4. Confirm PNG and TIFF dimensions match and resolve to 180-186 mm at 600 dpi.
5. Inspect every final-size PNG for clipped text, label-data overlap, ambiguous
   colors, missing endpoint ticks, and inconsistent panel ordering.
6. Run `python -m pytest tests -q` and the D7 release checker before publication.
