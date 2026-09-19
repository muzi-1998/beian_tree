# SUMO Input DO downstream-validation data package

This module prepares the common process-input layer for the frozen SUMO Input
DO validation protocol. It never overwrites source files.

## Time-scale contract

- `1 min`: provenance, technical QC and sensitivity analysis.
- `5 min`: primary SUMO forcing and process-input time base.
- `1 h`: DQR joins, context summaries and reporting only.

All cleaning is completed at 1 min before aggregation. The 5 min and 1 h
products therefore share the same provenance and cannot silently diverge.

## Cleaning contract

1. Preserve the raw value.
2. Apply registered or primitive physical-domain checks.
3. Treat small negative flow readings as zero-equivalent only when their
   magnitude is no more than 5% of the channel's positive median. More extreme
   negative values remain invalid.
4. Apply a conservative 15 min centered rolling median/MAD Hampel screen
   (`k = 6`) to state variables. For flow and dosing channels, Hampel is
   diagnostic-only because short actuator/pump pulses are valid process input
   unless corroborating actuator-state evidence proves otherwise.
5. Linearly interpolate only internally bounded gaps of at most 3 min. Longer
   gaps remain missing and are carried to the QA outputs.
6. Aggregate cleaned minute data by arithmetic mean with at least 80% native
   support (4/5 points for 5 min; 48/60 points for 1 h).

The centered Hampel operation is an offline common technical-QC step shared by
all downstream strategies. It must not be described as a real-time causal
filter. A trailing-window implementation is required for future online use.

## Outputs

`outputs/` contains five workbooks:

- process inputs at 1 min, 5 min and 1 h;
- DO/ORP at 1 min and 5 min.

Each process workbook starts with `Raw`, `Clean` and `Derived_m3d`. The DO/ORP
workbooks start with `Raw` and `Clean`. Compact QA and data-dictionary sheets
follow the requested data sheets. Machine-readable Parquet files preserve the
same values and a bit-mask provenance table.

The methodological rationale and downstream-use boundaries are frozen in
`TIME_SCALE_AND_DATA_CONTRACT_ZH.md`. In particular, the DO/ORP `Clean` sheet
is a conventional technical-QC copy; it does not replace the independent Raw
and DQR input routes required by the validation protocol.

The minute workbooks contain tens of millions of cells. They are exported with
a constant-memory streaming writer because the standard in-memory artifact
engine does not complete this scale reliably. Workbook row counts, headers,
styles, panes and representative values are independently re-opened and
verified after export.

## Important unit limitation

The ferric chloride and sodium acetate tags are registered as `m3/h`, but their
observed magnitudes require confirmation against PLC scaling and flow-meter
engineering units. Their `m3/d` conversions are mathematically correct under
the registered unit and are explicitly marked provisional; they must not be
used as confirmed dosing volumes until that audit is closed.

## DQR-conditioned forcing export

`export_dqr_forcing.py` consumes the revised temporal DQR scores and the
preserved minute observations. Its separate `outputs/dqr_forcing/` bundle
contains eight DO and six ORP channels, 5 min CSV inputs, minute action
provenance, continuous-window and process-coverage audits, and a review report.
The six aerobic DO channels are the primary Input DO comparison. DO4 is a
shared post-anoxic input with an explicitly flagged zero-equivalence view;
signed ORP is diagnostic data for the process model.

The export applies the v3.0 full-evidence `Q < 3` rule using the actual score
decision clock. It does not claim that a repair operator has been qualified.
Unrecoverable observations stay missing and split runnable intervals. Current
DO values therefore coincide with the common raw baseline; the bundle cannot
establish downstream improvement without a later independent experiment.

Unlike the earlier general-purpose 80%-support preparation, this forcing
export requires all five constituent minutes to be defined in each 5 min
interval. An unrecoverable minute cannot disappear inside an interval mean.
The XLSX audit stores local wall-clock dates without timezone conversion.

Run `python export_dqr_forcing.py`, `node build_dqr_audit.mjs`,
`python verify_dqr_export.py`, `python export_dqr_forcing.py --finalize`, then
`python verify_dqr_export.py --verify-hashes`. The independent verifier checks
minute-to-5 min reconciliation, missing values, score availability, DO4 shared
handling, signed ORP, workbook timestamps, and frozen source/code/output hashes.
The 28-day trial bundle contains
14 days of shared warm-up and 14 days of evaluation, selected using input
availability only. Unit and model-initialization requirements remain explicit.

The selected pilot starts on 2026-04-10; evaluation is 2026-04-24 through
2026-05-07. D5 report availability (66/2592 h, 2.55%) must not be confused with
complete aggregate evidence (65/2592 h, 2.51%). Neither figure licenses filling
missing evidence with a high score or inventing a qualified repair model.

The bundled spreadsheet authoring runtime currently exits with status 1 after
reporting successful XLSX export and rendering. Do not infer validity from
that message alone: the independent verifier reopens the delivered workbook
and checks every window timestamp and channel summary against the source
tables. Those checks pass for this release; runtime teardown remains an
authoring-tool limitation, not a reason to suppress verification errors.
