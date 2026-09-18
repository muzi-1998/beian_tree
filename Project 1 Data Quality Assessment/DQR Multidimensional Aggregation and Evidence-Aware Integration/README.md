# DQR Multidimensional Aggregation and Evidence-Aware Integration

This peer-level integration module combines the frozen D1-D5 evidence
interfaces without making D5 the parent of the other dimensions.

## Scientific contract

- D1, D2 and eligible D5 are equal-weight node evidence.
- D3 is an independent non-compensatory safety gate and is never averaged.
- D4 remains native pair evidence and is never copied into sensor rows.
- Missing D5 evidence remains unavailable; it is never coded as poor quality.
- `Q` (quality), `E` (evidence completeness) and `G` (D3 gate) are reported separately.
- Full, fixed Core and availability-aware estimands are retained in parallel.
- Fixed Core is the longitudinal estimand; Full is the complete-evidence estimand.
- Availability-aware scores are not compared across changing dimension masks.
- D5 L1 and D4 fallback are evidence-support states, not automatic low quality.
- A-E grades, deployment release and optimized weights remain disabled pending
  prospective and downstream validation.

## Reproduce

```powershell
python scripts/run_dqr_aggregation.py
python -m pytest tests -q
python scripts/verify_dqr_aggregation.py
```

All frozen input hashes, generated artifact hashes, contract checks and figure
QA results are recorded under `outputs/aggregation_v2_4/`. The v2.2/v2.3 outputs
are retained for audit history. D3/D4 use neutral-reference releases; D1/D2/D5
numeric results and the D5 support audit remain frozen. The already inspected
108-day extension is a separate revised temporal out-of-sample re-evaluation,
not a first blind test: `../validation/revised_reference_20260917/`.
