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

The v2.0 confirmatory execution fixes the aggregation architecture as four
dynamic evidence products plus one independent safety interface:

- D1 and D2 are node-score-ready.
- D3 is Gate-ready. `D3_gate_status` is the primary interface; `D3_total`
  remains a supplementary legacy analysis and is not averaged into WW-DQS.
- D4 is score-ready through `D4_raw`; attribution and action gates remain
  separate.
- D5 report-eligible L2/L3 rows are score-ready. Missing or L1-only evidence is
  not converted into a low score. The D5 action gate remains limited to
  node-specific L3 evidence.

The retrospective composite has been executed with prespecified equal weights,
eligible-dimension renormalization, 7 d moving-block bootstrap uncertainty and
48 h block sensitivity. It remains a single-plant retrospective scientific
product, not an externally validated operational decision instrument.

## Aggregation rules

1. Join by canonical sensor and time keys without interpolation across a quality
   dimension's non-evaluable rows.
2. Keep `score`, `evaluable`, `evidence_level`, `uncertainty` and `lineage`
   together.
3. Renormalize weights only over eligible dimensions; never replace missing
   evidence with the lowest score.
4. Compute the node score as the equal mean of eligible D1, D2 and D5 evidence.
   A formal node score requires at least two eligible dimensions; one dimension
   is diagnostic only.
5. Compute the pair score as the equal mean of target-node score,
   reference-node score and `D4_raw`, only when all three are evaluable.
6. Keep D3 Fail/Warn/Pass outside both numeric means. Fail blocks
   high-confidence grading; Warn remains an explicit physical-evidence label.
7. Keep sensor-identity Veto separate from the numeric composite.
8. Treat process-coherence Guard as attribution suppression, not Veto.
9. Report the composite, effective dimension count, coverage class and
   uncertainty together.
10. Do not publish A-E grades until grade cut points are frozen independently
    of the confirmatory record.
11. Freeze the dimension registry and artifact SHA-256 manifest for every paper
   release.

The authoritative v2.0 retrospective run is
`outputs/confirmatory/D1D5V20-a2b2bef69861/`.
