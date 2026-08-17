# D5 Publication Readiness Audit v1.0

## Executive decision

D5 is scientifically suitable for continuous-score aggregation in a retrospective single-plant study, with explicit support and coverage restrictions. It is not ready for sensor-specific hard Veto or automated deployment. The current production context is a plant-global robust context, not a strictly target-excluded model.

The six-fold future-month refit achieved AUROC 0.967, AUPRC 0.974 and Top-1 0.767. Top-1 remains below the prespecified 0.80 criterion and therefore blocks only node-specific hard Veto. Across all 180 local challenges, Top-1 was 0.622, Top-2 0.839 and MRR 0.753; for the prespecified channel-swap endpoint these were 0.700, 0.867 and 0.815, respectively.

## Structural ablation

| Removed structure | Paired Top-1 gain of full model | 95% outer-fold CI |
|---|---:|---:|
| `no_exogenous_context` | 0.100 | 0.033 to 0.183 |
| `no_regime_conditioning` | 0.050 | -0.033 to 0.133 |
| `no_hysteresis` | 0.017 | 0.000 to 0.050 |

No-regime conditioning caused the clearest AUROC/AUPRC detection loss, while removing hydraulic/time context caused the clearest Top-1 localization loss. Hysteresis produced a small incremental gain. These results support regime conditioning and exogenous context, but do not justify tuning on the terminal folds.

## Coverage and selection

There are 3 months with zero formal D5 report coverage; the minimum monthly report coverage is 0.0%. This is driven primarily by L1 support/OOD migration, so formal composite results represent a complete-evidence subset and cannot be extrapolated to all sensor-hours. Raw scientific evidence remains separately available where calculable.

## D4-D5 complementarity

Against D4 run `D4V14_20260726_100717`, Spearman rho is 0.145, adjusted partial rank correlation is 0.136, and low-score Jaccard is 0.235. This supports related but non-identical constructs. Status is `provisional_rerun_after_latest_D4_merge`: the audit must be rerun after the latest D4 branch is merged before manuscript numbers are frozen.

## Target influence

Leave-one-target-out context refits produced a maximum whole-period regime disagreement of 18.0%, but only 0.2% after the reference period. Under controlled 2.5-MAD target offsets, the MAP context-switch rate remained 0.0%, while the maximum OOD-rate increase was 5.8%. These are sensitivity results. They do not convert the current production model into a target-excluded model, and they must be reported as bounded-influence evidence rather than leakage elimination.

## Confidence limitation

The controlled-injection risk-coverage curve is not monotonic: retaining only the highest-confidence trials does not improve Top-1 localization. Therefore the current uncertainty/confidence field is valid as evidence metadata but is not calibrated as a selective-localization probability and must not be used to release hard Veto.

## Recommendation decisions

| Recommendation | Decision | Scientific rationale |
|---|---|---|
| `full_outer_fold_refit` | `accepted_already_complete` | Six future-month folds; full, no exogenous, no regime and no hysteresis were refit from training data only. |
| `D4_D5_incremental_information` | `accepted_executed_provisional` | Executed against D4V14_20260726_100717; rerun after the latest D4 release is merged. |
| `score_support_missingness_freeze` | `accepted_executed` | Continuous scores retained; L1/L2/L3 and missing/OOD semantics frozen; A-E grades disabled. |
| `Top1_0_80_boundary` | `accepted_executed` | Localization failure blocks sensor-specific hard Veto only, not the continuous scientific score. |
| `risk_coverage_and_monthly_support` | `accepted_executed_with_limitation` | Field evidence coverage and controlled-injection risk-coverage are separate; current confidence is not calibrated for selective localization. |
| `target_excluded_context` | `accepted_with_modification` | Production is accurately named plant-global robust context; leave-one-target-out is an influence challenge, not a false production claim. |
| `support_threshold_sensitivity` | `accepted_executed` | Sensitivity only; no post-hoc production threshold changes. |
| `untouched_future_test` | `pending_external_data` | No untouched data after 2026-04-13 are currently available. |
| `maintenance_event_truth` | `pending_external_data` | Needed for fault/event truth and operational deployment claims. |
| `dual_approval_and_asset_provenance` | `pending_deployment_only` | Does not block retrospective scientific aggregation under the confirmed ordinal topology. |
| `topology_perturbation_robustness` | `pending_prespecified_perturbation_set` | Arbitrary edge edits would be post-hoc; execute only after plausible perturbations are frozen. |
| `ORP_covariance_upgrade` | `not_executed_not_supported` | Current ORP support does not justify replacing the conservative diagonal model; retain as future sensitivity. |
| `conditional_mutual_information` | `not_primary` | Autocorrelated single-plant CMI is estimator-sensitive; partial rank plus block bootstrap is the primary audit. |

## Final claim boundary

- Ready: continuous D5 score, retrospective report interface, process-coherence attribution Guard, final subscore aggregation with explicit coverage.
- Not ready: sensor-specific hard Veto, causal fault labels, prospective deployment, cross-plant generalization.
- A-E grades remain disabled because no independent future data exist for cutpoint freezing.
- New field data, maintenance truth and dual approval should be treated as external validation/deployment work, not silently imputed into the current retrospective analysis.
