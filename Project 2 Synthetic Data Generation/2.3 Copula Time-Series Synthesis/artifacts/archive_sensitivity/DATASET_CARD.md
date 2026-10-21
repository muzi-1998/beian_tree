# Archive sensitivity dataset card

Purpose: retrospective development-only method prototype. Native measurement support UNKNOWN; model_admitted=false; no formal time step.

Inputs: hash-verified M02 aligned archive, Q/COD/T common complete calendar hours. Q in m3/h, COD_FW and COD_TW in source-header mg/L, T in degC. Nitrogen and effluent labels excluded.

Training: 2025-08-01 through 2026-04-30. Generation: first30 development calendar days, same recorded T/time, 665 common support hours; hindsight conditional replay, not forecast.

108 unconstrained trajectories; complete IDs, seeds and file hashes in validation/trajectory_file_map.csv and trajectory_manifest.csv. They share model/context and are not independent environmental event replications.

8 negative Q and 3190 negative COD output rows retained, no physical correction. No SUMO/field-TN/augmentation admission. No natural event frequency, calibrated process response or validated tail extrapolation claim.

Raw observations and observation-level outputs remain local. Latest successful run and immutable failure/recovery history are under run_manifest/archive_sensitivity/runs.
