# D1-D5 v2.0 confirmatory execution report

Run ID: `D1D5V20-764c93bf3d95`

## Expert feasibility verdict

The reduced v2.0 design is scientifically coherent and more defensible than an equal-status five-score average. D1, D2, D4 and D5 remain dynamic scientific evidence; D3 is implemented as an independent non-compensatory Safety Gate. The composite uses transparent equal weights for eligible D1/D2/D5 node evidence and adds D4 only at pair level.

The current record supports retrospective within-plant validation. It does not support prospective, maintenance-truth, cross-plant or learned-optimal-weight claims.

## Executed work packages

| Work package | Execution | Decision |
|---|---|---|
| WP0 | Frozen SAP, claim registry, split registry, figure contract and immutable run manifest | Complete |
| D1 | Route-accurate core-fault validation plus raw-domain frozen-transform endpoint audit | Internal mechanism validation complete; field truth pending |
| D2 | QFA-window, hard-RLE and gap-mapping OAT with full sensor-hour rescoring | Complete |
| D3 | Grade A instrument Fail, Grade B value/rate Warn and legacy-score separation | Complete; site approval of Grade B sources pending |
| D4 | Target, peer, common-process, opposite-direction and lag mechanisms with timestamp-clustered CI | Complete; ORP shrinkage remains sensitivity-only |
| D5 | Three prespecified structural ablations with complete future-month outer refit | Complete for retrospective validation; deployment governance pending |
| Composite | Full/basic-stratified node, pair and plant products with 7 d and 48 h block bootstrap | Complete without formal A-E grades |

## Key numerical results

### D1

- hard_freeze: recall 1.000 (95% CI 1.000-1.000), AUROC 1.000, false alarms/sensor-day 0.000.
- linear_drift: recall 0.693 (95% CI 0.606-0.771), AUROC 0.544, false alarms/sensor-day 0.148.
- spike: recall 0.396 (95% CI 0.287-0.493), AUROC 0.680, false alarms/sensor-day 4.333.
- step: recall 0.240 (95% CI 0.176-0.298), AUROC 0.684, false alarms/sensor-day 0.000.

The full D1 design is explicitly route-level: spike uses the residual route, step the routed whitened detector input, drift the fixed PLS route, and hard freeze the raw minute route. A separate prespecified subset injects each fault in the raw measurement domain and applies decomposition/whitening parameters fitted before the validation period and then frozen. No contaminated test window is used to refit preprocessing.

Raw-domain frozen-transform audit:
- spike: raw-domain recall 0.375 (cluster 95% CI 0.246-0.508), route/raw agreement 0.844; n=64.
- step: raw-domain recall 0.172 (cluster 95% CI 0.089-0.270), route/raw agreement 0.828; n=64.
- linear_drift: raw-domain recall 0.703 (cluster 95% CI 0.574-0.828), route/raw agreement 1.000; n=64.
- hard_freeze: raw-domain recall 1.000 (cluster 95% CI 1.000-1.000), route/raw agreement 1.000; n=64.

At the locked >=2 sigma region, 0/6 analyte-route strata met the 0.80 recall target. The amplitude-duration maps retain low-recall regions instead of pooling them away.

Spike and Step thresholds were not lowered after observing these results. Any revised detector would require a new development set and an untouched or external validation set; the present package treats low recall as an applicability boundary.

### D2

- Minimum channel-rank Spearman across OAT: 0.996.
- Minimum event Jaccard across OAT: 0.721.
- Process-floor contract checks passed: 6/6.
- DO_1_4 and DO_2_4 share the same process-floor semantics: low IQR is diagnostic, hard digital lock remains unavailable, and missing/long-gap evidence is never exempted.

### D3

- Gate hours/windows: Pass 27689, Warn 15319, Fail 0.
- Minimum warning-event Jaccard across OAT: 0.899.

### D4

- target_drift / AUROC: 0.934 (pair-windows=126, timestamp-clustered where applicable).
- target_drift / AUPRC: 0.915 (pair-windows=126, timestamp-clustered where applicable).
- target_drift / direction_accuracy: 0.992 (pair-windows=126, timestamp-clustered where applicable).
- peer_drift / AUROC: 0.918 (pair-windows=126, timestamp-clustered where applicable).
- peer_drift / AUPRC: 0.892 (pair-windows=126, timestamp-clustered where applicable).
- peer_drift / direction_accuracy: 0.984 (pair-windows=126, timestamp-clustered where applicable).
- target_step / AUROC: 0.936 (pair-windows=126, timestamp-clustered where applicable).
- target_step / AUPRC: 0.920 (pair-windows=126, timestamp-clustered where applicable).
- target_step / direction_accuracy: 1.000 (pair-windows=126, timestamp-clustered where applicable).
- peer_step / AUROC: 0.912 (pair-windows=126, timestamp-clustered where applicable).
- peer_step / AUPRC: 0.900 (pair-windows=126, timestamp-clustered where applicable).
- peer_step / direction_accuracy: 1.000 (pair-windows=126, timestamp-clustered where applicable).
- target_freeze / AUROC: 0.798 (pair-windows=126, timestamp-clustered where applicable).
- target_freeze / AUPRC: 0.774 (pair-windows=126, timestamp-clustered where applicable).
- peer_freeze / AUROC: 0.809 (pair-windows=126, timestamp-clustered where applicable).
- peer_freeze / AUPRC: 0.795 (pair-windows=126, timestamp-clustered where applicable).
- common_equal / conditional_new_FAR: 0.041 (pair-windows=74, timestamp-clustered where applicable).
- common_unequal / asymmetry_detection_rate: 0.500 (pair-windows=74, timestamp-clustered where applicable).
- opposite_direction / asymmetry_detection_rate: 1.000 (pair-windows=74, timestamp-clustered where applicable).
- change_point_lag / severity_monotonic_spearman: 0.000 (pair-windows=630, timestamp-clustered where applicable).

- common_equal: common_process_negative_control; endpoint conditional_new_FAR; included from common-process FAR; contract Pass.
- common_unequal: positive_asymmetry_stress_test; endpoint asymmetry_detection_rate; excluded from common-process FAR; contract Pass.
- opposite_direction: strong_positive_asymmetry_stress_test; endpoint asymmetry_detection_rate; excluded from common-process FAR; contract Pass.

Subhour D4 lag values are retained as supplementary sensitivity only. They do not replace D4_raw or support a formal subhour monotonicity claim. ORP shrinkage remains an exploratory sparse-support analysis.

### D5

- swap_AUROC: 0.912; target >= 0.9; Pass.
- swap_AUPRC: 0.870; target >= 0.8; Pass.
- swap_Top1: 0.700; target >= 0.8; Fail.
- common_mode_FAR: 0.046; target <= 0.1; Pass.
- zone_coherent_FAR: 0.057; target <= 0.1; Pass.

Complete future-month outer refits:
- full_reference / AUROC: 0.967 (outer-fold 95% CI 0.945-0.985); Pass against 0.90.
- full_reference / AUPRC: 0.974 (outer-fold 95% CI 0.960-0.989); Pass against 0.80.
- full_reference / Top1: 0.767 (outer-fold 95% CI 0.683-0.850); Fail against 0.80.
- no_exogenous_context / AUROC: 0.950 (outer-fold 95% CI 0.937-0.965); Pass against 0.90.
- no_exogenous_context / AUPRC: 0.962 (outer-fold 95% CI 0.951-0.973); Pass against 0.80.
- no_exogenous_context / Top1: 0.667 (outer-fold 95% CI 0.617-0.733); Fail against 0.80.
- no_regime_conditioning / AUROC: 0.920 (outer-fold 95% CI 0.902-0.943); Pass against 0.90.
- no_regime_conditioning / AUPRC: 0.941 (outer-fold 95% CI 0.925-0.958); Pass against 0.80.
- no_regime_conditioning / Top1: 0.717 (outer-fold 95% CI 0.667-0.767); Fail against 0.80.
- no_hysteresis / AUROC: 0.963 (outer-fold 95% CI 0.938-0.985); Pass against 0.90.
- no_hysteresis / AUPRC: 0.973 (outer-fold 95% CI 0.957-0.988); Pass against 0.80.
- no_hysteresis / Top1: 0.750 (outer-fold 95% CI 0.667-0.833); Fail against 0.80.

Paired Full-minus-ablation future-month effects:
- no_exogenous_context / AUROC: delta 0.017 (outer-month 95% CI -0.010-0.043; positive in 66.7% of folds).
- no_exogenous_context / AUPRC: delta 0.012 (outer-month 95% CI -0.004-0.029; positive in 83.3% of folds).
- no_exogenous_context / Top1: delta 0.100 (outer-month 95% CI 0.033-0.183; positive in 66.7% of folds).
- no_regime_conditioning / AUROC: delta 0.047 (outer-month 95% CI 0.030-0.065; positive in 100.0% of folds).
- no_regime_conditioning / AUPRC: delta 0.033 (outer-month 95% CI 0.015-0.053; positive in 100.0% of folds).
- no_regime_conditioning / Top1: delta 0.050 (outer-month 95% CI -0.033-0.133; positive in 66.7% of folds).
- no_hysteresis / AUROC: delta 0.003 (outer-month 95% CI 0.000-0.007; positive in 33.3% of folds).
- no_hysteresis / AUPRC: delta 0.001 (outer-month 95% CI 0.000-0.003; positive in 50.0% of folds).
- no_hysteresis / Top1: delta 0.017 (outer-month 95% CI 0.000-0.050; positive in 16.7% of folds).

Full-model Top-1 localization is 0.767 (95% CI 0.683-0.850) and does not meet the locked 0.80 criterion. This limits exact node localization and keeps sensor-level hard Veto disabled; it does not invalidate report-grade D5 detection or retrospective composite aggregation.

### Composite

- Full node-score rows: 39,606.
- Basic extension rows: 46,046.
- Full/basic/limited/insufficient coverage: basic=46,046, full=39,606, limited=364.
- Formal pair-score rows: 37,975.
- Full/basic pair rows: 18,376/19,599.
- D3 is not averaged into Q_node or Q_pair; Fail prevents a high-confidence grade and Warn is retained as an explicit label.
- Coverage-selection audit: Full 39,606 sensor-hours, Basic 46,046; Basic OOD share 29.1% versus Full 0.0%.
- Full is a complete-evidence, calendar/regime/support-selected estimand. It is not generalized to all sensor-hours; Basic is reported separately.

## Pending or disputed items

| ID | Issue | Current handling | Recommended resolution |
|---|---|---|---|
| A-D1-PEER-MARGIN | The v2.0 prose omitted the numeric admission rule already used by the D1 peer-upgrade implementation. | lock_the_existing_2pct_gain_zero_ci_lower_bound_60pct_positive_folds_and_5pct_p90_tail_margin_in_the_SAP | retain the frozen rule; do not add a post-hoc P95 endpoint without a new development protocol. |
| A-D1-RESOLUTION | The degraded resolution increment is not numerically specified. | use_paired_2x_native_or_empirical_resolution_as_exploratory_sensitivity_only | lock the degraded increment from instrument resolution and SCADA encoding metadata before confirmatory reuse. |
| A-D1-INJECTION-ROUTE | The original implementation labelled every route-level trial as raw-domain even though spike, step and drift entered different detector routes. | label_all_primary_trials_by_their_true_route_and_add_a_64_scenario_per_fault_raw_domain_frozen_transform_audit | keep route-level applicability and raw-domain concordance as separate evidence layers; never refit on a contaminated window. |
| A-D1-POSTHOC-THRESHOLD | Lowering Spike or Step thresholds on the same validation trials would optimize to observed confirmatory failures and invalidate the locked false-alarm interpretation. | retain_locked_thresholds_and_report_amplitude_duration_applicability_boundaries | develop any revised detector on a separate development period and evaluate it on a genuinely untouched or external dataset. |
| A-D1-FREEZE-AMPLITUDE | Hard freeze is defined by unchanged duration and has no scientifically valid injected amplitude parameter. | publish_a_duration_only_heatmap_and_label_amplitude_as_not_defined | do not derive a pseudo-amplitude from pre-event variance merely to match the other fault panels. |
| A-D4-SHRINKAGE | The estimator, prior strength and minimum independent block count are not specified. | run sensitivity_only_without_replacing_D4_raw | select one empirical-Bayes estimator in development data, freeze it, then test it in future blocks. |
| A-D4-FAR | Low is qualitative in the work-package table. | use_existing_locked_0_10_ceiling | retain 0.10 in the frozen SAP and cite the originating D4 validation contract. |
| A-D4-COMMON-POOLING | Unequal same-direction and opposite-direction changes are positive asymmetry controls, not common-process false alarms. | conditional_FAR_uses_equal_common_change_only | report both positive controls separately and never include either in the common-process FAR denominator. |
| A-D4-LAG-RESOLUTION | The production change-point timeline is hourly, so 10 and 30 minute lag levels are below its nominal resolution. | remove_subhour_levels_from_main_claim_and_retain_the_existing_grid_as_supplementary_resolution_sensitivity | a future minute-scale auxiliary detector is required before making 10 or 30 minute identification claims. |
| A-D5-NODE-SUPPORT | The v2.0 document did not state the numeric minimum. | retain_current_D5_v2_3_support_contract_and_copy_exact_thresholds_into_the_SAP | cite the frozen SAP and D5 v2.3 support contract together. |
| A-D5-CONTEXT-ABLATION | The v2.0 document did not define K selection or the exact reduced set of structural refits. | run_full_reference_no_exogenous_no_regime_and_no_hysteresis_with_training_only_silhouette_K_and_frozen_future_month_tests | retain only these three high-value ablations and do not search feature combinations using Top1. |
| A-D5-TOP1-SCOPE | The locked Top-1 endpoint governs exact node localization and action eligibility, whereas AUROC/AUPRC govern structural anomaly detection. | retain_report_grade_detection_and_disable_node_specific_hard_action | publish the failed 0.80 localization endpoint transparently; improve localization only on future independent evidence. |
| A-COMP-BOTTLENECK | The primary persistence is given as a range. | use_3h_as_primary_and_2h_as_sensitivity_without_releasing_an_operational_action_gate | preserve the same rule in the manuscript SAP; deployment still requires prospective validation. |
| A-COMP-GRADE | No composite grade cut points are supplied. | publish_continuous_scores_and_coverage_only | lock grade cut points using development-period utility or expert criteria, never the confirmatory blocks. |
| A-D3-SOFT-SOURCE | Existing rules are versioned but several remain expert rules without signed site approval. | retain_as_Grade_B_warning_only | add named source, date, applicable condition and reviewer sign-off to the threshold register. |

## External evidence still required

- D1 maintenance/operator fault and verified recovery records.
- D2 SCADA communication, network alarm and planned-shutdown logs.
- D3 signed site approval for Grade B operating and rate rules, plus independently adjudicated warning events.
- D4 independently adjudicated synchronization/asymmetry events.
- A truly unseen future period and preferably a second treatment plant.
- An independent downstream criterion before any learned weighting or operational-utility claim.

## Prespecified failures retained

- D1 Spike/Step low-recall regions remain visible in the amplitude-duration maps.
- D2 settings that fail the 0.75 event-Jaccard threshold remain in the main OAT figure.
- D4 subhour lag monotonicity is not claimed and is shown as sensitivity-only.
- D5 variants that fail the locked 0.80 Top-1 localization threshold remain reported.

## Publication decision

The package is suitable for a retrospective single-plant methods manuscript with explicit claim boundaries. The completed D5 outer refits remove the previous structural-ablation blocker. It remains unsuitable for an operational deployment claim, learned-optimal-weight claim or cross-plant generalization claim until the listed external evidence is available.
