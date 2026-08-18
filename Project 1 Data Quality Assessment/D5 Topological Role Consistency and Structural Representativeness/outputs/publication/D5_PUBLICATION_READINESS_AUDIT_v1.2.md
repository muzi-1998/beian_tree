# D5 Publication Readiness Audit v1.2

## Executive decision

D5 is scientifically suitable for continuous-score aggregation in a retrospective single-plant study, with explicit support and coverage restrictions. It is not ready for sensor-specific hard Veto or automated deployment. The current production context is a plant-global robust context, not a strictly target-excluded model.

The six-fold future-month controlled-challenge refit achieved discrimination AUROC 0.967, AUPRC 0.974 and controlled-perturbation Top-1 localization 0.767. Top-1 remains below the prespecified 0.80 criterion and therefore blocks only node-specific hard Veto. Across all 180 controlled perturbations, Top-1 was 0.622, Top-2 0.839 and MRR 0.753; for the prespecified channel-swap endpoint these were 0.700, 0.867 and 0.815, respectively. These quantities are not field sensor-fault detection or localization accuracy.

## Structural ablation

| Removed structure | Paired Top-1 gain of full model | 95% outer-fold CI |
|---|---:|---:|
| `no_exogenous_context` | 0.100 | 0.033 to 0.183 |
| `no_regime_conditioning` | 0.050 | -0.033 to 0.133 |
| `no_hysteresis` | 0.017 | 0.000 to 0.050 |

No-regime conditioning caused the clearest controlled-challenge AUROC/AUPRC discrimination loss, while removing hydraulic/time context caused the clearest controlled-perturbation Top-1 localization loss. Hysteresis produced a small incremental gain. These results support regime conditioning and exogenous context, but do not justify tuning on the terminal folds.

## Coverage and selection

There are 3 months with zero formal D5 report coverage; the minimum monthly report coverage is 0.0%. This is driven primarily by L1 support/OOD migration, so formal composite results represent a complete-evidence subset and cannot be extrapolated to all sensor-hours. Raw scientific evidence remains separately available where calculable.

The current node-level prototype gives 99.6% availability-aware composite coverage but only 46.0% fixed-dimension complete-evidence coverage. These are different estimands and must be shown separately. The calculation currently covers the available D1/D2/D5 node contract and must be repeated after the final five-dimension WW-DQS contract is frozen.

## D4-D5 complementarity

Against D4 run `D4V151_20260813_083347` and calibration `D4CAL-V151-66fe1bb6b7d3` (main-score SHA-256 `c21738a331d19632cc915e4d29cf692920aeccd346a6c74912f0f52dd4a9ca04`), report-score overlap Spearman rho is 0.119, raw-calculable overlap rho is 0.171, adjusted report-score partial rank correlation is 0.108, and report-score low-tail Jaccard is 0.229. For report-score strata, 94.7% of 19 descriptive strata have |rho| below 0.30; 13 meet the six-independent-block CI criterion. For raw-calculable strata, the corresponding values are 86.4%, 22 and 15. The pooled descriptive rate is 90.2%. Point estimates require at least two independent 7 d blocks; bootstrap CIs require at least six. These are non-redundancy diagnostics, not proof of causal independence. Status is `current`.

## Target influence

Leave-one-target-out context refits produced a maximum whole-period regime disagreement of 17.9%, but only 0.2% after the reference period. Under controlled 2.5-MAD target offsets, the MAP context-switch rate remained 0.0%, while the maximum OOD-rate increase was 5.8%. These are sensitivity results. They do not convert the current production model into a target-excluded model, and they must be reported as bounded-influence evidence rather than leakage elimination.

## Confidence limitation

The controlled-injection risk-coverage curve is not monotonic: retaining only the highest-confidence trials does not improve Top-1 localization. Therefore the current uncertainty/confidence field is valid as evidence metadata but is not calibrated as a selective-localization probability and must not be used to release hard Veto.

## Recommendation decisions

| Recommendation | Decision | Scientific rationale |
|---|---|---|
| `full_outer_fold_refit` | `accepted_already_complete` | Six future-month folds; full, no exogenous, no regime and no hysteresis were refit from training data only. |
| `D4_D5_dual_scope_overlap` | `accepted_executed_current` | Report-score and raw-calculable overlap use analyte/regime/month/pair strata with separate descriptive and inferential admission; dependency status is current. |
| `D4_dependency_fail_closed` | `accepted_executed` | Current status requires exact run ID, calibration ID and D4 main-score SHA-256 with one unique run and calibration. |
| `score_support_missingness_freeze` | `accepted_executed` | Continuous scores retained; L1/L2/L3 and missing/OOD semantics frozen; A-E grades disabled. |
| `controlled_perturbation_Top1_0_80_boundary` | `accepted_executed` | Controlled perturbation localization below 0.80 blocks sensor-specific hard Veto only, not the continuous scientific score. |
| `risk_coverage_and_monthly_support` | `accepted_executed_with_limitation` | Field evidence coverage and controlled-injection risk-coverage are separate; current confidence is not calibrated for selective localization. |
| `dimension_availability_sensitivity` | `accepted_executed_prototype` | Availability-aware and fixed-dimension complete-evidence composites are reported separately; rerun after the final D1-D5 numeric contract is frozen. |
| `publication_ci` | `accepted_executed` | Tests, artifact hashes, figure QA and exact D4 dependency are checked by one non-mutating publication bundle gate. |
| `target_excluded_context` | `accepted_with_modification` | Production is accurately named plant-global robust context; leave-one-target-out is an influence challenge, not a false production claim. |
| `support_threshold_sensitivity` | `accepted_executed` | Sensitivity only; no post-hoc production threshold changes. |
| `untouched_future_test` | `pending_external_data` | No untouched data after 2026-04-13 are currently available. |
| `maintenance_event_truth` | `pending_external_data` | Needed for fault/event truth and operational deployment claims. |
| `dual_approval_and_asset_provenance` | `pending_deployment_only` | Does not block retrospective scientific aggregation under the confirmed ordinal topology. |
| `topology_perturbation_robustness` | `pending_prespecified_perturbation_set` | Arbitrary edge edits would be post-hoc; execute only after plausible perturbations are frozen. |
| `ORP_covariance_upgrade` | `not_executed_not_supported` | Current ORP support does not justify replacing the conservative diagonal model; retain as future sensitivity. |
| `conditional_mutual_information` | `not_primary` | Autocorrelated single-plant CMI is estimator-sensitive; partial rank plus block bootstrap is the primary audit. |

## Final claim boundary

- Ready: continuous D5 score, retrospective report interface and process-coherence attribution Guard.
- Conditional: availability-aware aggregation is allowed only with explicit dimension-count and coverage outputs; fixed-dimension complete-evidence results must be reported separately.
- Ready: cross-dimensional D4-D5 publication values are bound to the exact frozen D4 artifact.
- Not ready: sensor-specific hard Veto, causal fault labels, prospective deployment, cross-plant generalization.
- A-E grades remain disabled because no independent future data exist for cutpoint freezing.
- New field data, maintenance truth and dual approval should be treated as external validation/deployment work, not silently imputed into the current retrospective analysis.
