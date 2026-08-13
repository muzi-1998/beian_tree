# D4 v1.5 composite refresh

- Run ID: `D4V15-COMPOSITE-db23b03bac4d`
- Status: retrospective SHA-bound refresh; not untouched terminal validation
- D4 numeric source: `D4_raw`
- D4 calibration: `D4CAL-V15-f6c351de01b0`
- Node rows: 86,016
- Pair rows: 42,847
- Plant-day rows: 256
- Node coverage: {"basic": 46046, "full": 39606, "limited": 364}
- Pair coverage: {"basic": 22583, "full": 19774, "limited": 490}

The refresh preserves dimension independence: D1 does not alter D4 numerically,
D3 remains a non-compensatory safety gate, and D5 report availability is exposed
through separate Full and Basic coverage classes. A future untouched period is
still required for terminal confirmation.
