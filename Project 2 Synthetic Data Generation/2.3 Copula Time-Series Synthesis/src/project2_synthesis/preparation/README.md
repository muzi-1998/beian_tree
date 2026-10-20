# M02 preparation

状态：开发集档案算术诊断已实现并运行；主步长和真实原生支持待定，当前科学验收 PARTIAL。证据见 reports/M02_执行报告.md。

以configs/module_contracts.json、configs/experiment_protocol.json及02输出契约为准；04最终稿为研究设计依据。

实际有限用途产物（逐次 SHA 与运行状态见 run_manifest/module_states.json）：

- `artifacts/data/02_model_frame.parquet`
- `artifacts/data/02_time_blocks.parquet`
- `artifacts/validation/02_scale_comparison.csv`
- `artifacts/data/02_concentration_views.parquet`
- `artifacts/data/02_load_ledger.parquet`
- `artifacts/validation/02_scale_decision.json`

主要验收：5/15/60无默认优先；1min双门；TW/FW分开；共同支持V/L守恒及切分。

02_model_frame 为 model_admitted=false 的开发集技术档案。TW/FW/V/L 使用相同技术支持、名义 1 min 档案求积；不是已验证的原生测量积分。主步长仍 null。技术连续块不是独立事件，完整档案窗口不是测量覆盖准入。
