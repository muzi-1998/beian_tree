# Stage B figure legends

## H1. Temporal scope and label-to-information-time contracts

(a) Historical reconstruction interval, the original absolute D5 reference
endpoint, and the later108-day input interval. The D5 bar covers the final
10-minute snapshot beginning2026-01-27 04:30. Later-period scores and controlled
challenge performance remain unopened; calendar dates are Asia/Shanghai.
(b) Minimum source-window closure relative to the existing output label:
D1/D2/D4+60min, D5+10min, and D3 zero because D3 already uses an end-exclusive
window endpoint. D3 zero does not imply zero observation history or computation
time. D1/D2 show reporting-hour intervals; their detectors include longer
lookbacks. D4/D5 span24h and D3 spans2h. Additional upstream/processing latencies
and the operational as-of join remain to be verified. These are deterministic
code-derived timing contracts, not measured deployment latency.

## H2. Prefix dependence and old-period numerical sensitivity

(a) A deterministic32min missing run begins two minutes before a prefix cutoff.
The full-series classifier labels its initial missing minutes as a long gap,
although that duration was not known then. The candidate flags long gaps only
after the inherited5min limit is exceeded and recognizes completion only at the
next observation. DO_1_4 is displayed; all14 channels were tested with the same
gap. Blue=true, grey=false, white=unobserved tail of the prefix run.
(b) A deterministic target changes at42h and60h, with a stable reference.
Full-series D4 duplicate grouping suppresses a previously available representative
after future candidates are added. The prefix and strictly as-of candidate agree
for already available times; seven earlier Q_cp values change from2 to5 in the
full-series native computation. The dotted line marks the60h input cutoff. This
is a synthetic contract counterexample, not field fault or accuracy evidence.
(c) Seven old-period pairs, each with6,121 scoring rows. Numbers beside points
are counts; the horizontal axis is the fraction whose Q_cp changes when candidate
de-duplication uses only available information and labels become window closure.
All42,847 pair-hours are included. Native historical CP scores were first
reproduced exactly. Separate de-duplication-only and additional clock comparisons
are exported; their changed-row counts are not additive.
(d) Crossing the D4<3 boundary under that CP-only replacement, holding the other
three subscores, public mappings, weights and D2/support gates fixed. Denominators
are original common evaluable pair-hours (42,371 total), giving1,940 flips. No
D1/D5 re-arbitration or new DQR release is implied. Exact finite-dataset counts
have no bootstrap CI here; hours are not independent replicates. The original
derived row comparisons are in the audit Parquet.

## Source and display QA

Both figures have editable SVG/PDF, PNG preview and600dpi TIFF exports at183mm
width. Arial7pt text,8pt bold panel labels and selected6/5.8pt annotations.
The previews were visually inspected and the initial H2 legend/title overlap
corrected. No text lies outside either canvas. Nature static preflight has no
failures; its inability to infer a computed width is resolved by the runtime
183mm check and SVG dimensions. The local preflight is optional on other
machines and never substitutes for scientific tests.

The source workbook has11 sheets. Floating-point analytical contents are not
rounded; replay tolerances are in the audit tables. These figures belong in
Methods/Extended Data. Future-period applicability, coverage, event burden and
composite figures remain pending the opening gate, not represented by these.
# Update 2026-09-06

H1 now identifies the fixed three-minute D1 short-gap preprocessing delay as
additional to source-window closure. The remaining processing and integration
latencies are not yet certified. Three more workbook sheets document D1 recovery,
candidate scheduling and minute alignment; these are QA evidence, not holdout
performance or new standalone main figures. The original H2 numerical results
are unchanged.
