# M01 intake

状态：来源/技术审计已实现并实际运行；当前科学验收 PARTIAL，原生信息和标签尚待准入。实际证据见 reports/M01_执行报告.md。

以configs/module_contracts.json、configs/experiment_protocol.json及02输出契约为准；04最终稿为研究设计依据。

实际产物（逐次 SHA 与运行状态见 run_manifest/module_states.json）：

- `artifacts/data/01_input_audit.json`
- `artifacts/data/01_observation_flags.parquet`
- `artifacts/validation/01_native_frequency.csv`
- `artifacts/validation/01_label_admission.json`

主要验收：原生更新/保持/延迟有证据；累计Q拒绝；标签观测算子；DQR不伪造。

原生采样、保持、插值、延迟暂无可核实元数据，保留 UNKNOWN 与可空身份字段。数值重复诊断不能据此转成保持身份或刷新周期。本模块不插值、不修复氮关系、不伪造 DQR。
