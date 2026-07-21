# D1 project directory guide

## Authoritative entry points

| Path | Responsibility |
|---|---|
| `load_real_data_v11.py` | Section 1.1 bridge, detector execution, freeze routing, and topology-constrained PLS selection |
| `calibrate_step_mapping.py` | Raw-input Step fault injection, grid search, LOCO validation, applicability audit |
| `run_v11_pipeline.py` | Formal final-candidate state machine, aggregation, and run manifest |
| `run_recovery_validation.py` | Natural-data sensitivity and controlled mechanism challenges |
| `excel_exporter_v11.py` | Eighteen core D1 workbooks |
| `make_baseline_figures_v11.py` | Figures 1-11 |
| `make_pls_peer_topology_figure.py` | Supplementary Fig. S1 formal all-channel PLS peer topology |
| `make_figures_v11.py` | Figures V12-V15 |
| `make_figures_v11_part2.py` | Figures V16-V18 |
| `make_recovery_figures.py` | Figures V19-V20 |
| `audit_d1_figures.py` | Figure bundle and contact-sheet QA |
| `generate_final_expert_report.py` | Synchronized expert DOCX report |

## Core implementation

| Path | Responsibility |
|---|---|
| `src/baseline/bridge_decomposition_11.py` | Per-channel residual/innovation routing and effective sample size |
| `src/calibration/step_injection.py` | Step injection library, mapping optimization, and LOCO validation |
| `src/detectors/drift_pls.py` | Explicit same-analyte topology and residual-standardized PLS detector |
| `src/validation/pls_peer_upgrade.py` | DO_2_4 three-model forward validation, block bootstrap, terminal hold-out, controlled injections, and admission decision |
| `src/mapping/mapper.py` | Score mappings and process-floor freeze combination |
| `src/baseline/local_baseline.py` | Causal contiguous baseline and empirical scale floor |
| `src/aggregation/cooldown_state_machine.py` | Six-state event and recovery logic |
| `src/aggregation/recovery_metrics.py` | Episode recovery, censoring, KM, relapse, and conservation |
| `src/aggregation/d1_aggregator.py` | Final D1 aggregation and conservative state caps |
| `configs/rules.yaml` | Channel scope, floor-freeze policy, aggregation, and veto rules |
| `configs/mapping.yaml` | Authoritative score mappings; Step `k=16.0`, `x0=0.55` |
| `configs/state_machine.yaml` | Authoritative recovery configuration |

## Generated artifacts

| Path | Contents |
|---|---|
| `v11_state.pkl` | Formal run state and downstream source of truth |
| `outputs/logs/D1_run_manifest.json` | Run ID, bridge/detector code hashes, conservation, scale and mapping calibration |
| `outputs/logs/D1_step_mapping_calibration.json` | Machine-readable Step calibration manifest |
| `outputs/data/D1_step_mapping_calibration.xlsx` | Parameter grid, LOCO, scenarios, and applicability audit |
| `outputs/data/D1_mapping_params.xlsx` | Config-synchronized mapping coefficients and calibration summary |
| `outputs/data/D1_detector_outputs_raw.xlsx` | Detector evidence, freeze routing, PLS peer audit and matrix |
| `outputs/data/D1_pls_DO24_validation.xlsx` | Model definitions, temporal split, 6,138 hourly predictions/errors, all fold gains, bootstrap samples, clean windows, 936 injection rows, gates, and final decision |
| `outputs/figures/` | Twenty-one formal figure bundles only |
| `outputs/plot_data/` | Figure source workbooks and calibration scenario CSV |
| `outputs/qa/figures/` | Contact sheets and automated audit JSON |
| `outputs/D1_Sensor_Health_Expert_Report_Auto.docx` | Synchronized final expert report |

## PLS peer-topology contract

- Core peers are same-analyte adjacent sensors and available same-position twin-pool sensors.
- Only same-pool second-order neighbours are eligible candidates. Formal admission requires full-period forward validation, moving-block bootstrap uncertainty, terminal hold-out confirmation, and four controlled-injection classes.
- A single valid core peer is scientifically reportable as limited redundancy; the implementation never fills a sparse core by channel-name order.
- `DO_1_4` is excluded as a predictor because its process-floor behaviour is not exchangeable with ordinary DO channels.
- `DO_2_4` retains the `DO_2_3` one-component core model. `DO_2_2` is preserved as a tested and rejected candidate rather than being silently promoted.
- Fig. 11 preserves the DO_2_4 candidate-admission evidence; Supplementary Fig. S1 reports the production-active peer topology for all 14 channels. The latter omits rejected candidates by design.
- `v11_state.pkl`, `D1_detector_outputs_raw.xlsx`, `D1_pls_DO24_validation.xlsx`, `Fig11_pls_peer_selection_data.xlsx`, and `FigS1_pls_formal_peer_topology_data.xlsx` preserve the selected peers, validation evidence, redundancy status, and topology contract.

## Reproduction order

```powershell
python load_real_data_v11.py
python run_v11_pipeline.py
python calibrate_step_mapping.py
python run_v11_pipeline.py
python run_recovery_validation.py
python excel_exporter_v11.py
python make_baseline_figures_v11.py
python make_pls_peer_topology_figure.py
python make_figures_v11.py
python make_figures_v11_part2.py
python make_recovery_figures.py
python audit_d1_figures.py
python generate_final_expert_report.py
python -m pytest -q
```

The first calibration pass selects the mapping from a valid prior state; the second pipeline pass embeds the final calibration manifest in the formal state. Outputs from different `run_id` values must not be combined.
