# D4 mapping-support migration audit

This audit separates score magnitude from mapping evidence maturity. It is descriptive and does not modify D4_raw, mapping thresholds, report eligibility or pair ranking rules.

- Exact variable-regime mapping: 64.1% of pair-hours.
- Variable/global fallback mapping: 35.8% of pair-hours.
- Global fallback mapping: 0.0% of pair-hours.
- Fallback evidence is retained as metadata; exclusion from a future formal estimand requires a prospectively frozen rule and new validation data.
- Event runs are broken at mapping-scope, phase and timestamp discontinuities, preventing artificial cross-boundary episode merging.
- Exact-mapping share was stable at 57.1%-57.1% from 2025-10 through 2026-03; the lower pooled validation exact share therefore reflects regime composition rather than a new late-period fallback expansion.
- ORP variable-fallback rows showed greater validation low-tail burden and longer tail episodes than their development counterpart. Exact and fallback strata correspond to different regimes, so this is a stratified descriptive signal, not an estimate of a causal fallback penalty.
- No global fallback was used. The small insufficient class is retained as non-comparable evidence rather than imputed or scored down.
