# D7 Field Verification and Approval Requirements

## Decision

Field topology, asset identity, channel mapping and dual approval require human
intervention. Statistical similarity, graph learning or channel-swap injection
may prioritize records for review, but none of them can replace field evidence
or approval.

Until this gate is complete:

- `D7_raw` and `D7_report_provisional` may be used as research evidence;
- L1 is diagnostic only and L2 is report-only;
- `D7_total`, `D7_forDQR`, Veto and D6 final arbitration remain disabled;
- topology-drift candidates remain hypotheses and cannot modify the registry.

## Required evidence

1. Controlled process drawing or as-built P&ID identifier, revision and validity
   interval.
2. For every channel: sensor ID, asset ID, serial number, PLC/SCADA tag,
   analyte, process line, zone, longitudinal order, installation depth or
   coordinate, and evidence source.
3. Confirmation of every longitudinal edge and parallel matched-position pair.
4. Calibration, replacement, relocation, maintenance and channel-remapping
   records covering the study interval.
5. Field-confirmed channel swaps or role changes, if any, with event start/end
   and adjudicated truth label.
6. A reviewer and an approver who are different identifiable people, with
   signed timestamps and recorded decisions.

## Minimum workflow

1. The preparer enters evidence without changing model outputs.
2. The reviewer compares drawing, SCADA configuration and field asset identity.
3. The approver independently checks exceptions and accepts or rejects the
   topology version.
4. Only an approved version is copied into `configs/common/sensors.yaml` and
   `configs/common/topology.yaml`.
5. All topology-bound regimes, templates, validation, figures, reports and
   manifests are regenerated.

## Evidence that remains unavailable

When field access is unavailable, leave the current
`PENDING_FIELD_VERIFICATION` values unchanged. Do not infer serial numbers,
coordinates, signatures or approval status from time-series data.

The blank intake template is
`configs/common/field_verification_template.csv`. It is an author-input
artifact and is not consumed by the production pipeline until formally
approved.
