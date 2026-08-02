# D1-D5 v2.0 confirmatory execution report

Run ID: `D1D5V20-a2b2bef69861`

## Expert feasibility verdict

The reduced v2.0 design is scientifically coherent and more defensible than an equal-status five-score average. D1, D2, D4 and D5 remain dynamic scientific evidence; D3 is implemented as an independent non-compensatory Safety Gate. The composite uses transparent equal weights for eligible D1/D2/D5 node evidence and adds D4 only at pair level.

The current record supports retrospective within-plant validation. It does not support prospective, maintenance-truth, cross-plant or learned-optimal-weight claims.

## Executed work packages

| Work package | Execution | Decision |
|---|---|---|
| WP0 | Frozen SAP, claim registry, split registry, figure contract and immutable run manifest | Complete |
| D1 | Core-fault mixed injection design across analyte, regime and routing strata | Internal mechanism validation complete; field truth pending |
| D2 | QFA-window, hard-RLE and gap-mapping OAT with full sensor-hour rescoring | Complete |
| D3 | Grade A instrument Fail, Grade B value/rate Warn and legacy-score separation | Complete; site approval of Grade B sources pending |
| D4 | Target, peer, common-process, opposite-direction and lag mechanisms | Complete; ORP shrinkage remains sensitivity-only |
| D5 | Component ablation, blocked-month validation, support funnel and locked admission audit | Partial: context/template ablations require outer-fold refit |
| Composite | Node/pair/plant products, coverage, 7 d and 48 h bootstrap, dimension ablation | Complete without formal A-E grades |

## Key numerical results

### D1

- hard_freeze: recall 1.000 (95% CI 0.974-1.000), AUROC 0.999, false alarms/sensor-day 0.096.
- linear_drift: recall 0.698 (95% CI 0.630-0.758), AUROC 0.544, false alarms/sensor-day 0.148.
- spike: recall 0.379 (95% CI 0.302-0.461), AUROC 0.682, false alarms/sensor-day 2.571.
- step: recall 0.240 (95% CI 0.185-0.305), AUROC 0.684, false alarms/sensor-day 0.000.

D1 injections are parameterized in original measurement units and projected through the frozen training-time detector route. The implementation does not refit decomposition or whitening on each contaminated test window. This revision is deliberate: test-window refitting would leak fault information and allow preprocessing to adapt to the injected fault.

### D2

- Minimum channel-rank Spearman across OAT: 0.996.
- Minimum event Jaccard across OAT: 0.721.

### D3

- Gate hours/windows: Pass 27689, Warn 15319, Fail 0.
- Minimum warning-event Jaccard across OAT: 0.899.

### D4

- target_drift / AUROC: 0.934 (n=126).
- target_drift / AUPRC: 0.915 (n=126).
- target_drift / direction_accuracy: 0.992 (n=126).
- peer_drift / AUROC: 0.918 (n=126).
- peer_drift / AUPRC: 0.892 (n=126).
- peer_drift / direction_accuracy: 0.984 (n=126).
- target_step / AUROC: 0.936 (n=126).
- target_step / AUPRC: 0.920 (n=126).
- target_step / direction_accuracy: 1.000 (n=126).
- peer_step / AUROC: 0.912 (n=126).
- peer_step / AUPRC: 0.900 (n=126).
- peer_step / direction_accuracy: 1.000 (n=126).
- target_freeze / AUROC: 0.798 (n=126).
- target_freeze / AUPRC: 0.774 (n=126).
- peer_freeze / AUROC: 0.809 (n=126).
- peer_freeze / AUPRC: 0.795 (n=126).
- common_equal / conditional_new_FAR: 0.041 (n=74).
- common_unequal / asymmetry_detection_rate: 0.500 (n=74).
- opposite_direction / asymmetry_detection_rate: 1.000 (n=74).
- change_point_lag / severity_monotonic_spearman: 0.000 (n=630).

### D5

- swap_AUROC: 0.912; target >= 0.9; Pass.
- swap_AUPRC: 0.870; target >= 0.8; Pass.
- swap_Top1: 0.700; target >= 0.8; Fail.
- common_mode_FAR: 0.046; target <= 0.1; Pass.
- zone_coherent_FAR: 0.057; target <= 0.1; Pass.

### Composite

- Formal node-score rows: 85,652.
- Full/basic/limited/insufficient coverage: basic=46,046, full=39,606, limited=364.
- Formal pair-score rows: 37,975.
- D3 is not averaged into Q_node or Q_pair; Fail prevents a high-confidence grade and Warn is retained as an explicit label.

## Pending or disputed items

| ID | Issue | Current handling | Recommended resolution |
|---|---|---|---|
| A-D1-PEER-MARGIN | Exact equivalence margin, confidence rule and alpha are not specified. | retain_existing_locked_numeric_margins_and_report_them | prespecify a 5_percent P90/P95 noninferiority margin and 95_percent block-bootstrap CI rule. |
| A-D1-RESOLUTION | The degraded resolution increment is not numerically specified. | use_2x_native_or_empirical_resolution_as_sensitivity_only | lock the degraded increment from instrument resolution and SCADA encoding metadata before confirmatory reuse. |
| A-D1-INJECTION-ROUTE | It is unclear whether rerun means applying the frozen causal transform or refitting preprocessing on each contaminated test window. | apply_faults_in_measurement_units_through_the_frozen_training_route_without_refitting | state explicitly that all preprocessing parameters are trained before the injection window and remain frozen during injected evaluation. |
| A-D4-SHRINKAGE | The estimator, prior strength and minimum independent block count are not specified. | run sensitivity_only_without_replacing_D4_raw | select one empirical-Bayes estimator in development data, freeze it, then test it in future blocks. |
| A-D4-FAR | Low is qualitative in the work-package table. | use_existing_locked_0_10_ceiling | retain 0.10 in the frozen SAP and cite the originating D4 validation contract. |
| A-D4-LAG-RESOLUTION | The production change-point timeline is hourly, so 10 and 30 minute lag levels are below its nominal resolution. | retain_all_levels_as_resolution_sensitivity_and_do_not_claim_subhour_identification | either predefine a minute-scale auxiliary change-point detector or restrict the confirmatory lag claim to one hour and longer. |
| A-D5-NODE-SUPPORT | The v2.0 document does not state the numeric minimum. | retain_current_D5_v2_3_support_contract | copy the exact v2.3 node minimums into the manuscript SAP before submission. |
| A-D5-CONTEXT-ABLATION | The document does not define outer-fold refitting, regime-label alignment, K selection or threshold recalibration for these structural ablations. | compute_component_score_space_ablation_and_mark_structural_refits_pending | freeze one outer-fold refit protocol on development months and rerun all structural ablations without reusing confirmatory labels. |
| A-COMP-BOTTLENECK | The primary persistence is given as a range. | report_2h_and_3h_sensitivity_without_releasing_a_primary_action_gate | use 3h as the conservative primary rule and 2h as sensitivity. |
| A-COMP-GRADE | No composite grade cut points are supplied. | publish_continuous_scores_and_coverage_only | lock grade cut points using development-period utility or expert criteria, never the confirmatory blocks. |
| A-D3-SOFT-SOURCE | Existing rules are versioned but several remain expert rules without signed site approval. | retain_as_Grade_B_warning_only | add named source, date, applicable condition and reviewer sign-off to the threshold register. |

## External evidence still required

- D1 maintenance/operator fault and verified recovery records.
- D2 SCADA communication, network alarm and planned-shutdown logs.
- D3 signed site approval for Grade B operating and rate rules, plus independently adjudicated warning events.
- D4 independently adjudicated synchronization/asymmetry events.
- A truly unseen future period and preferably a second treatment plant.
- An independent downstream criterion before any learned weighting or operational-utility claim.

## Publication decision

The package is suitable for a retrospective single-plant methods manuscript after the pending full-refit D5 context ablations and the listed method locks are resolved. It is not yet suitable for an operational deployment claim or a cross-plant generalization claim.
