# D1 project directory guide

## Authoritative entry points

| Path | Responsibility |
|---|---|
| `load_real_data_v11.py` | Section 1.1 bridge, detector execution, freeze routing, PLS selection |
| `calibrate_step_mapping.py` | Raw-input Step fault injection, grid search, LOCO validation, applicability audit |
| `run_v11_pipeline.py` | Formal final-candidate state machine, aggregation, and run manifest |
| `run_recovery_validation.py` | Natural-data sensitivity and controlled mechanism challenges |
| `excel_exporter_v11.py` | Seventeen core D1 workbooks |
| `make_baseline_figures_v11.py` | Figures 1-11 |
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
| `src/detectors/drift_pls.py` | Same-analyte peer rules, blocked CV, and residual-standardized PLS detector |
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
| `outputs/logs/D1_run_manifest.json` | Run ID, hashes, conservation, scale and mapping calibration |
| `outputs/logs/D1_step_mapping_calibration.json` | Machine-readable Step calibration manifest |
| `outputs/data/D1_step_mapping_calibration.xlsx` | Parameter grid, LOCO, scenarios, and applicability audit |
| `outputs/data/D1_mapping_params.xlsx` | Config-synchronized mapping coefficients and calibration summary |
| `outputs/data/D1_detector_outputs_raw.xlsx` | Detector evidence, freeze routing, PLS peer audit and matrix |
| `outputs/figures/` | Twenty formal figure bundles only |
| `outputs/plot_data/` | Figure source workbooks and calibration scenario CSV |
| `outputs/qa/figures/` | Contact sheets and automated audit JSON |
| `outputs/D1_Sensor_Health_Expert_Report_Auto.docx` | Synchronized final expert report |

## Reproduction order

```powershell
python load_real_data_v11.py
python run_v11_pipeline.py
python calibrate_step_mapping.py
python run_v11_pipeline.py
python run_recovery_validation.py
python excel_exporter_v11.py
python make_baseline_figures_v11.py
python make_figures_v11.py
python make_figures_v11_part2.py
python make_recovery_figures.py
python audit_d1_figures.py
python generate_final_expert_report.py
python -m pytest -q
```

The first calibration pass selects the mapping from a valid prior state; the second pipeline pass embeds the final calibration manifest in the formal state. Outputs from different `run_id` values must not be combined.
