# Final five-dimension WW-DQS contract

## Canonical numbering

The only current public numbering is:

| ID | Dimension | Previous lineage |
|---|---|---|
| D1 | Sensor health | unchanged |
| D2 | Temporal continuity and information availability | unchanged |
| D3 | Physical rationality and rate constraints | former D4 |
| D4 | Parallel-redundancy temporal consistency | former D6 |
| D5 | Topological role consistency and structural representativeness | former D7 |

Historical archived reports, run IDs and checksums retain their original labels.
They are provenance records, not current interfaces. New code, output names,
figures, reports and manuscript text must use D1-D5 only.

## Independence boundary

Each raw subscore must be calculated without another dimension's numeric score.
Shared observations and the section 1.1 time/regime foundation are permitted,
but downstream quality scores may only enter explicitly labelled interpretation,
eligibility or validation tracks:

- D1 is independent sensor-state evidence.
- D2 is independent timestamp, missingness and hard-run evidence. D1 linkage is
  explanatory and must leave the D2 score hash unchanged.
- D3 is independent plausibility evidence from unimputed observations and fixed
  physical/rate rules.
- D4 aggregation uses `D4_raw`. D1 is interpretation-only; D2 may determine
  whether paired evidence is observable; D5 supplies a separate report/gate
  interface and cannot rewrite `D4_raw`.
- D5 Local uses observations, confirmed ordinal topology and exogenous
  hydraulic/time context. Cross-dimension sensitivity is isolated and has no
  production write permission.

## Aggregation eligibility

The project may enter a locked retrospective aggregation-calibration stage:

- D1, D2 and D3 are score-ready.
- D4 is score-ready through `D4_raw`; attribution and action gates remain
  separate.
- D5 report-eligible L2/L3 rows are score-ready. Missing or L1-only evidence is
  not converted into a low score. The D5 action gate remains limited to
  node-specific L3 evidence.

The final composite is not yet a validated clinical-style decision instrument.
Before claiming a final WW-DQS index, weights, uncertainty propagation,
missing-dimension renormalization and external criterion validity must be
pre-specified and validated.

## Aggregation rules

1. Join by canonical sensor and time keys without interpolation across a quality
   dimension's non-evaluable rows.
2. Keep `score`, `evaluable`, `evidence_level`, `uncertainty` and `lineage`
   together.
3. Renormalize weights only over eligible dimensions; never replace missing
   evidence with the lowest score.
4. Keep sensor-identity Veto separate from the numeric composite.
5. Treat process-coherence Guard as attribution suppression, not Veto.
6. Report both the composite and its effective dimension count.
7. Freeze the dimension registry and artifact SHA-256 manifest for every paper
   release.
