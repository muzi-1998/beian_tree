# D4 v1.6 neutral-reference composite refresh

- Run ID: `D4V16-COMPOSITE-63a6f03f0f74`
- Status: retrospective SHA-bound refresh; not untouched terminal validation
- D4 numeric source: `D4_raw`
- D4 calibration: `D4CAL-V16-e615cd349a49`
- Node rows: 86,016
- Pair rows: 42,847
- Plant-day rows: 256
- Node coverage: {"basic": 46046, "full": 39606, "limited": 364}
- Pair coverage: {"basic": 22596, "full": 19593, "limited": 658}

The refresh preserves dimension independence: D1 does not alter D4 numerically,
D3 remains a non-compensatory safety gate, and D5 report availability is exposed
through separate Full and Basic coverage classes. A future untouched period is
still required for terminal confirmation.
