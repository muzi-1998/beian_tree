# D7 Project Directory Guide v2.1

**Generated:** 2026-07-16 21:19 CST  
**Update rule:** every computational or figure change must rerun reports and release QA.

## 1. Project layout

```text
D7 Topological Role Consistency and Structural Representativeness/
|-- configs/
|   |-- common/          # paths, sensors, topology and interface schemas
|   |-- local/           # production-isolated D7 Local policies
|   |-- sensitivity/     # upstream-filter sensitivity only
|   `-- shadow_v2/       # graph/topology research only
|-- src/
|   |-- d7_common/       # shared configuration, hashing and robust math
|   |-- d7_local/        # Local contracts, context, templates, evidence, scoring and outputs
|   |-- d7_sensitivity/  # physically isolated shadow pipeline
|   `-- d7_shadow_v2/    # no-production-impact graph research
|-- scripts/             # reproducible entry points
|-- tests/               # contract and regression tests
|-- docs/                # version-reviewable Markdown reports
`-- outputs/             # generated artifacts by track and role
```

## 2. Track isolation

| Track | Allowed inputs | Forbidden outputs |
|---|---|---|
| `d7_local` | Canonical 1-min observations/flags, QR/QIR context, declared topology, frozen D7 assets | Reading D1-D6 score/state/event inputs |
| `sensitivity` | Frozen Local evidence plus D1/D2/D4 read-only filters | `D7_forDQR`, zone consensus, active templates, D6 arbitration |
| `shadow_v2` | Canonical observations and declared topology | Automatic topology update, Veto, Local score mutation |

## 3. Output roots

| Path | Role |
|---|---|
| `outputs/local` | Authoritative Local scores, evidence, templates, audits and D6 read-only interface |
| `outputs/sensitivity` | D1/D2/D4-filtered shadow reference sensitivity; no production writes |
| `outputs/shadow_v2` | Graph/topology research candidates with production impact fixed to none |
| `outputs/plot_data` | Frozen long-table data used by every manuscript figure |
| `outputs/figures` | SVG/PDF/600 dpi PNG figures and figure QA |
| `outputs/reports` | Expert report, directory guide and figure captions |

## 4. Core entry points

```powershell
python scripts/run_d7_local.py
python scripts/run_d7_sensitivity.py
python scripts/run_d7_validation.py
python scripts/run_d7_topology_review.py
python scripts/run_d7_shadow_v2.py
python scripts/make_d7_figures.py
python scripts/build_d7_reports.py
python scripts/check_d7_release.py
python -m pytest tests -q
```

Use `python scripts/run_d7_release.py --include-local` after data, topology, template, mapping or core scoring changes. For report/figure-only edits, omit `--include-local`.

## 5. Update protocol

1. Work on an `agent/*` branch; do not write half-complete results to `main`.
2. Change configuration and code together; never edit generated score tables by hand.
3. Run the fastest contract tests, then the affected track.
4. Rebuild validation, plot data, all figure counterparts, reports and release QA.
5. Inspect PNG figures and rendered DOCX pages visually.
6. Stage only the D7 directory, commit, push the branch and open a draft PR.
7. Report branch, commit, compare/PR URL and all failed release gates to the user.
8. Merge only after explicit confirmation.

## 6. Production activation checklist

- [ ] Field drawing ID is real and versioned.
- [ ] All asset IDs, serial numbers and channel tags are verified.
- [ ] Coordinates are surveyed or approved, not schematic placeholders.
- [ ] Reviewer and approver are two identified independent people.
- [ ] Topology validity interval covers the evaluated data.
- [ ] All topology-bound template hashes are regenerated.
- [ ] Required support tiers and ORP exit criteria pass.
- [ ] Swap AUROC/AUPRC and Top-1 pass blocked validation.
- [ ] Transition FAR and topology tests have external truth.
- [ ] Local-Sensitivity invariance gates pass.
- [ ] D6 protected columns have max absolute difference zero.
- [ ] `D7_total` is populated only for genuinely evaluable rows.

## 7. File ownership rules

- `configs/common/topology.yaml` is the only declared production topology source; Shadow outputs never overwrite it.
- Parquet is authoritative for tabular data; Excel is a human-review mirror with the same semantics.
- `D7_plot_data` is the sole manuscript-figure input; figure scripts do not recompute business metrics.
- Reports and this guide are generated artifacts and must be refreshed on every release workflow.
- Missing/limited/OOD evidence is represented by status plus `NaN`, never by a fabricated low score.

## 8. Current branch gate

Current release classification: **research review complete, production blocked**. The immediate blockers are field topology/asset verification, effective support and Top-1 localization.
