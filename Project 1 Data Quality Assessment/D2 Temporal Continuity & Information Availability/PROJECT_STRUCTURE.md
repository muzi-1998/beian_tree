# D2 项目目录说明

> 最后更新：2026-08-05  
> 当前版本：V4 strict/sensitive release  
> 运行号：`D2V4_20260805_1127`

## 项目定位

D2 独立评价时间连续性与信息可用性：

- `Q_TI`：原始时间戳完整性和缺失覆盖率；
- `Q_GS`：缺失片段持续性和拓扑严重度；
- `Q_HA`：有原始观测时的硬信息停滞；
- `D2_Sensitive_risk`：软低动态的联合诊断标签，不参与正式数值聚合。

输入承接 `1.1 Decomposition` 的统一时间底座和原始源文件合同。D1 仅用于构念区分，不参与 D2 计算。

## 核心目录

```text
D2 Temporal Continuity & Information Availability/
|-- configs/
|   |-- d2_mapping.yaml              # V4 映射、权重、Veto、QHA 和 Sensitive 合同
|   |-- d2_sensors.yaml              # 传感器、拓扑、分辨率和 process-floor 定义
|   |-- d2_windows.yaml              # 1 h/6 h/24 h 窗口合同
|   `-- d2_study_design.yaml         # development/validation/terminal test 划分
|-- src/
|   |-- d2_availability/
|   |   |-- scorer.py                # QTI/QGS/QHA 与 D2 聚合
|   |   |-- process_floor.py         # 地板、分辨率受限、硬停滞证据分流
|   |   `-- challenge.py             # 原始时间戳/测量域全管线注入
|   `-- utils/
|       |-- config_loader.py         # YAML 数据类与合同校验
|       `-- timestamp_quality.py     # 排序和对齐前时间戳审计
|-- run_d2_pipeline.py               # V4 主流水线
|-- validate_d2_process_floor.py      # process-floor 机制挑战
|-- run_d2_full_pipeline_validation.py # 时间戳/缺口/停滞端到端注入
|-- run_d2_scientific_validation.py  # 稳健性、消融、低尾、D1-D2 空模型
|-- make_d2_figures.py               # Fig. 01-10
|-- make_d1d2_joint_figures.py       # Fig. 11-12
|-- make_d2_scientific_figures.py    # Fig. 13-18
|-- build_d2_release_manifest.py      # SHA-256 发布清单
|-- test_d2_*.py                     # 回归、合同和注入测试
|-- d2_calibration.yaml              # 时间阻断的单厂开发期参考
|-- D2_FINAL_SCIENTIFIC_REPORT_2026-08.md
`-- artifacts/
    |-- d2_state.pkl                 # 本地完整状态，不纳入 Git
    |-- data/                        # 正式 Excel 输出
    |-- validation/                  # Parquet、验证 Excel 和 manifest
    `-- figures/                     # PNG/TIFF/SVG/PDF 图组
```

## 正式数据输出

| 文件 | 内容 |
|---|---|
| `artifacts/data/D2_main_scores_hourly.xlsx` | 14 通道小时级 QTI/QGS/QHA、D2 Strict、Sensitive 标签与 Veto |
| `artifacts/data/D2_preprocess_flags_hourly.xlsx` | missing、gap、floor、resolution-limited、hard-stasis 等标志 |
| `artifacts/data/D2_gap_run_table.xlsx` | 缺口事件及持续时间 |
| `artifacts/data/D2_hard_availability_events.xlsx` | 45 个硬可用性事件 |
| `artifacts/data/D2_freeze_availability_events.xlsx` | 上述事件的兼容文件名 |
| `artifacts/data/D2_timestamp_audit.xlsx` | 原始时间戳审计和小时定位 |
| `artifacts/data/D2_process_floor_casebook.xlsx` | process-floor 挑战和真实通道案例 |
| `artifacts/data/D2_mapping_params.xlsx` | 映射、权重和合同参数 |
| `artifacts/data/D2_audit_log.xlsx` | 运行号、输入哈希和语义声明 |

## 科学验证输出

`artifacts/validation/` 包含：

- `D2_full_pipeline_injection_response.parquet`：时间戳、缺口、硬停滞剂量响应；
- `D2_full_pipeline_monotonicity.parquet`：7 个单调性检验组；
- `D2_qha_threshold_window_sensitivity.parquet`：阈值和窗口联合敏感性；
- `D2_qha_window_sensitivity.parquet`：真实数据 3/6/9/12 h 事件稳健性；
- `D2_evidence_redundancy_*.parquet`：相关性与证据消融；
- `D2_low_tail_burden.parquet`：每 1000 sensor-hours 低尾负担；
- `D2_sensitive_diagnostic_summary.parquet`：Strict/Sensitive 分层摘要；
- `D2_d1d2_*.parquet`：事件匹配与循环移位空模型；
- `D2_*_source_data.xlsx`：Fig. 14、15、17、18 的绘图源数据；
- `D2_scientific_validation_manifest.json` 和 `D2_full_pipeline_injection_manifest.json`。

## 图组取舍

- 正文优先：Fig. 13-16、Fig. 18；
- 方法或扩展数据：Fig. 01、Fig. 05、Fig. 17；
- 补充材料：Fig. 02-04、Fig. 06-12；
- Fig. 02 因天花板效应明显，不作为主要科学证据。

## 维护规则

1. 修改评分合同后必须完整重跑主管线；
2. 修改 QHA 语义后必须重跑 process-floor、全管线注入和 3/6/9/12 h 窗口验证；
3. 所有新图必须同步输出 Excel 源数据、SVG/PDF 和 600 dpi PNG/TIFF；
4. 每次冻结发布更新本文件、科学报告和 SHA-256 manifest；
5. 未完成外部厂、SCADA 日志或运维真值验证前，不得扩大主张边界。

## 版本记录

| 日期 | 版本 | 变更 |
|---|---|---|
| 2026-08-04 | V3 | 原始时间戳 QTI、条件归一化、五阈值连续映射 |
| 2026-08-05 | V4 | QHA hard-only；Strict/Sensitive 分层；独立证据族；full-pipeline 注入；窗口重验；低尾与证据消融；Fig. 13-18 重绘 |
