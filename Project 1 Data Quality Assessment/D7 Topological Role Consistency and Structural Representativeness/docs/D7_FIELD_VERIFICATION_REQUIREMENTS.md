# D7 Research Topology Evidence and Production Approval Requirements

## Decision

The current research topology is supported by two complementary sources:

- author confirmation of process line, pool zone, longitudinal order,
  SCADA-to-physical-point one-to-one mapping and no study-period probe/channel
  change;
- an installation register that reconciles eight active DO and six active ORP
  instruments, including analyte, status, brand, range and 4-20 mA signal.

This evidence is sufficient for the current ordinal-topology research model.
Exact surveyed coordinates, asset IDs and serial numbers are not model inputs.
They must not be invented from time-series data.

Until production documentary audit and dual approval are complete:

- `D7_raw`, `D7_report_provisional` and eligible `D7_report` rows may be used as
  research evidence;
- L1 is diagnostic only and L2 is report-only;
- `D7_total`, `D7_forDQR`, Veto and D6 final arbitration remain disabled;
- topology-drift candidates remain hypotheses and cannot modify the registry.

## Research evidence status

The machine-readable evidence ledger is
`configs/common/topology_evidence.yaml`. The source installation register is
not copied into the repository; its checksum, inspected scope and limitations
are recorded in the ledger.

Maintenance records are currently unavailable. This is a provenance limitation
for retrospective interpretation, not an absolute blocker for ordinal research
scoring, because the author confirms no replacement or remapping during the
study.

## Required before production activation

1. Controlled process drawing or equivalent documentary identifier, revision
   and validity interval.
2. Independent audit of every channel's analyte, line, zone, longitudinal order
   and SCADA mapping; asset/serial identity should be added where available.
3. Independent confirmation of every longitudinal edge and parallel
   matched-position pair.
4. Calibration, replacement, relocation, maintenance and channel-remapping
   records covering the study interval, or a documented exception if records
   cannot be recovered.
5. Field-confirmed channel swaps or role changes, if any, with event start/end
   and adjudicated truth label.
6. A reviewer and an approver who are different identifiable people, with
   signed timestamps and recorded decisions.

## Minimum workflow

1. The preparer reconciles documentary evidence without changing model outputs.
2. The reviewer compares the controlled record, SCADA configuration and known
   asset identity.
3. The approver independently checks exceptions and accepts or rejects the
   topology version.
4. Only an approved production version changes
   `production_approval_status` to `approved` and `verification_status` to
   `verified`.
5. All topology-bound regimes, templates, validation, figures, reports and
   manifests are regenerated.

## Evidence that remains unavailable

When documentary or field evidence is unavailable, keep the explicit
`NOT_AVAILABLE_IN_PROVIDED_REGISTER` and `PENDING_PRODUCTION_APPROVAL` values.
Do not infer serial numbers, coordinates, signatures or approval status from
time-series data.

The blank intake template is
`configs/common/field_verification_template.csv`. It is an author-input
artifact and is not consumed by the production pipeline until formally
approved. Statistical topology candidates may prioritize review but cannot
replace production approval.
