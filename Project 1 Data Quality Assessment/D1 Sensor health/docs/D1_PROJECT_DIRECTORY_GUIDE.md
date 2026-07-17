# D1 project directory guide

## Authoritative entry points

| Path | Responsibility |
|---|---|
| `run_v11_pipeline.py` | Formal final-candidate pipeline and run manifest |
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
| `src/baseline/local_baseline.py` | Causal contiguous baseline and empirical scale floor |
| `src/aggregation/cooldown_state_machine.py` | Six-state event and recovery logic |
| `src/aggregation/recovery_metrics.py` | Episode table, event recovery, censoring, KM, relapse, conservation |
| `src/aggregation/d1_aggregator.py` | Final D1 aggregation and conservative state caps |
| `src/state/auxiliary_modules.py` | PELT evidence with signed magnitude and availability time |
| `configs/state_machine.yaml` | Authoritative recovery configuration |
| `configs/mapping.yaml` | Authoritative score mappings, including Step `k=8.0`, `x0=0.40` |

## Generated artifacts

| Path | Contents |
|---|---|
| `v11_state.pkl` | Formal run state; source of all downstream outputs |
| `outputs/logs/D1_run_manifest.json` | Run ID, version, hashes, scale calibration, conservation flag |
| `outputs/data/` | Core workbooks and recovery validation workbook |
| `outputs/figures/` | Twenty formal figure bundles only |
| `outputs/plot_data/` | Figure source workbooks/CSV |
| `outputs/qa/figures/` | Contact sheets and automated audit JSON |
| `outputs/D1_Sensor_Health_Expert_Report_Auto.docx` | Synchronized final expert report |

## Reproduction order

```powershell
python run_v11_pipeline.py
python run_recovery_validation.py
python excel_exporter_v11.py
python make_baseline_figures_v11.py
python make_figures_v11.py
python make_figures_v11_part2.py
python make_recovery_figures.py
python audit_d1_figures.py
python generate_final_expert_report.py
```

The pipeline state must be regenerated before validation, Excel, figures, or the report. Outputs from different `run_id` values must not be combined.
