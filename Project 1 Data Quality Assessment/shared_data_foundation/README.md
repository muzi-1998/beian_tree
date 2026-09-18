# Shared Raw Support and Process Context

This module owns dimension-neutral observations, support and the versioned D4
context product. It does not own or aggregate D1-D5 quality scores.

- Inputs: Section 1.1 canonical raw minute observations and source time contract.
- Presence excludes missing/imputed values, not constant observed values.
- D4 reference support: complete trailing 24 h window, bilateral minute and hour
  support, development-period lock, frozen context purity >=0.90.
- Context fitting: 24 h mean/std plus cyclic calendar features; scaler and KMeans
  fit on development rows only. No backfill from future feature values.
- D5's separately versioned robust features/posteriors/OOD/hysteresis remain unchanged.
- Output metadata: model ID, training interval, input SHA-256, availability time,
  valid context flag and within-window endpoint-regime purity.

Shared context is not a claim of statistical independence or target-influence
immunity. D4 still consumes the historical Section 1.1 residual product; freezing
context does not retroactively make that historical transform a prospective run.
The previously inspected 108-day period must be labelled revised temporal
out-of-sample re-evaluation after this methodological revision.
