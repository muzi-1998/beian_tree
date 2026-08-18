# D5 Project Directory Guide v2.4

**Generated:** 2026-08-18 10:57 CST
**Update rule:** every computational or figure change must rerun reports and release QA.

## 1. Project layout

```text
D5 Topological Role Consistency and Structural Representativeness/
|-- configs/
|   |-- common/          # paths, sensors, topology evidence and interface schemas
|   |-- local/           # production-isolated D5 Local policies
|   |-- publication/     # final claim, support and inference contract
|   |-- sensitivity/     # upstream-filter sensitivity only
|   `-- shadow_v2/       # graph/topology research only
|-- src/
|   |-- d5_common/       # shared configuration, hashing and robust math
|   |-- d5_local/        # Local contracts, context, templates, evidence, scoring and outputs
|   |-- d5_sensitivity/  # physically isolated shadow pipeline
|   `-- d5_shadow_v2/    # no-production-impact graph research
|-- scripts/             # reproducible entry points
|-- tests/               # contract and regression tests
|-- docs/                # version-reviewable Markdown reports
`-- outputs/             # generated artifacts by track and role
```

## 2. Track isolation

| Track | Allowed inputs | Forbidden outputs |
|---|---|---|
| `d5_local` | Canonical 1-min observations/flags, QR/QIR context, research topology/evidence, frozen D5 assets | Reading D1-D4 score/state/event inputs |
| `sensitivity` | Frozen Local evidence plus D1/D2/D3 read-only filters | Authoritative report/gate interfaces, active templates, D4 arbitration |
| `shadow_v2` | Canonical observations and declared topology | Automatic topology update, Veto, Local score mutation |

## 3. Output roots

| Path | Role |
|---|---|
| `outputs/local` | Authoritative Local scores, evidence, templates, audits and D4 read-only interface |
| `outputs/sensitivity` | D1/D2/D3-filtered shadow reference sensitivity; no production writes |
| `outputs/shadow_v2` | Graph/topology research candidates with production impact fixed to none |
| `outputs/plot_data` | Frozen long-table data used by every manuscript figure |
| `outputs/figures` | SVG/PDF/600 dpi PNG/TIFF figures and figure QA |
| `outputs/reports` | Expert report, directory guide and figure captions |
| `outputs/publication` | Publication decisions, inference audits, source data and manifest |

## 4. Core entry points

```powershell
python scripts/run_d5_local.py
python scripts/run_d5_sensitivity.py
python scripts/run_d5_validation.py
python scripts/run_d5_publication_audit.py
python scripts/run_d5_topology_review.py
python scripts/run_d5_shadow_v2.py
python scripts/make_d5_figures.py
python scripts/build_d5_reports.py
python scripts/check_d5_release.py
python "../D4 Parallel-redundancy Temporal Consistency/scripts/run_d4_d5_readiness.py"
python -m pytest tests -q
```

Use `python scripts/run_d5_release.py --include-local` after data, topology, template, mapping or core scoring changes. For report/figure-only edits, omit `--include-local`.

## 5. Update protocol

1. Work on an `agent/*` branch; do not write half-complete results to `main`.
2. Change configuration and code together; never edit generated score tables by hand.
3. Run the fastest contract tests, then the affected track.
4. Rebuild validation, plot data, all figure counterparts, reports and release QA.
5. Inspect PNG figures and rendered DOCX pages visually.
6. Stage only the D5 directory, commit, push the branch and open a draft PR.
7. Report branch, commit, compare/PR URL and all failed release gates to the user.
8. Merge only after explicit confirmation.

## 6. Production activation checklist

- [ ] Controlled drawing or equivalent documentary evidence is versioned.
- [ ] Asset/serial identity and maintenance history are reconciled where available.
- [ ] Ordinal positions are independently audited; exact coordinates are required only if used by a future metric.
- [ ] Reviewer and approver are two identified independent people.
- [ ] Topology validity interval covers the evaluated data.
- [ ] All topology-bound template hashes are regenerated.
- [ ] Required support tiers and ORP exit criteria pass.
- [ ] Controlled swap AUROC/AUPRC and Top-1 pass blocked validation.
- [ ] Transition FAR and topology tests have external truth.
- [ ] Local-Sensitivity invariance gates pass.
- [ ] D4 protected columns have max absolute difference zero.
- [ ] `D5_total` is populated only for genuinely evaluable rows.

## 7. File ownership rules

- `configs/common/topology.yaml` is the declared topology contract and
  `configs/common/topology_evidence.yaml` is its research evidence ledger;
  Shadow outputs never overwrite either file.
- `configs/common/field_verification_template.csv` is a blank human-input form;
  it is not evidence until reviewer and approver fields are independently completed.
- Parquet is authoritative for tabular data; Excel is a human-review mirror with the same semantics.
- `D5_plot_data` is the sole manuscript-figure input; figure scripts do not recompute business metrics.
- `D5_report_interface` is the sensor-hour scientific score contract; `D5_gate_interface` is the pair-hour decision and attribution contract.
- Reports and this guide are generated artifacts and must be refreshed on every release workflow.
- Missing/limited/OOD evidence is represented by status plus `NaN`, never by a fabricated low score.

## 8. Current branch gate

Current release classification: **D5 scientific score ready; cross-dimensional publication freeze dependency-gated; automated deployment blocked**. Node-specific hard Veto remains gated by controlled-perturbation Top-1 localization.
