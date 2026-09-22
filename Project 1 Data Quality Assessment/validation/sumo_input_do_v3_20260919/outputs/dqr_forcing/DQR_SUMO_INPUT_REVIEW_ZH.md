# DQR 处置后 SUMO 输入审查与交付

## 审查结论

可以输出 8 个 DO 与 6 个 ORP 的数值、Q/E/G、处置动作和连续可输入区间。
当前没有独立资格验证并冻结的故障修复器，所以低质量片段不填入臆测值。
这是 v3.0 规则的输入准备及可运行性审计，尚未完成三策略 SUMO 下游效用实验。

108 天各通道 D5 report 可用 66/2592 h（2.55%），但完整聚合证据 E=1 仅 65/2592 h（2.51%）。
两者不能混称 Full 覆盖率；按实际可用时钟连接后的完整证据分钟数列于通道摘要。
原评分小时中 8 个 DO 没有同时满足 E=1 且 Q<3 的记录。
按实际可用时钟连接后，DO 的低分触发分钟数为 0；ORP 为 120。
在本规则下 Full-DQR 对 DO 的可辨识增益不足，应如实报告，不能为制造组间差异临时降低 E 要求。
D4 是 pair 层关系证据，不能直接把 pair 低分归咎于某一支探头。逐点附带 D4/pair 诊断，但不自动修复两端。

## 文件使用

- `DQR_DO8_5min_20260414_20260730.csv`：108 天 8 个 DO，单位 mg O2/L，time_days 从验证期起点计。
- `DQR_ORP6_5min_20260414_20260730.csv`：6 个 ORP，单位 mV，负值保留。
- `DQR_DO8_5min_with_14d_warmup.csv`：从 2026-03-31 开始，前 14 天共用原始技术合规序列。
- `pilot42d_DO8_DQR.csv` 和 `pilot42d_DO6_Raw.csv`：原拟 14 天预热加 28 天验证候选。DO 连续，但共同过程输入存在缺口，尚非完整 SUMO 可运行包。
- `pilot28d_DO8_DQR.csv`、`pilot28d_DO6_Raw.csv`、`pilot28d_ORP6.csv` 和 `pilot28d_common_process_inputs.csv`：基于共同输入覆盖选出的短期试运行包，前14天预热、后14天评价。
- `do_orp_strategy_audit_1min.parquet`：逐分钟原值、处置值、动作、原因、评分可用时刻与 pair 诊断。
- `DQR_DO_ORP_measurement_1min.csv.gz`：DQR 保留/修复后的测量域数据，DO4 原始小负值仍可追溯。
- `continuous_input_windows.csv`、`blocked_intervals.csv`：连续可输入时段与不可输入片段。空值不得由 SUMO 默认跨长段插值。
- `DQR_DO_ORP_export_audit.xlsx`：通道汇总、月份、时段和方法合同。

主研究用 6 个好氧 DO1-3。DO4 按 D3 已有零点等效阈值，将 [-0.05,0) mg/L
在 SUMO 共用模型输入层表示为 0；Raw 和 measurement 输出保留原负值。
这项物理化处理是三策略相同的暂定表示合同，不作为 DQR 故障修复，也不声称真实 DO 精确为零。
ORP 是诊断及自定义模型辅助数据；常规 Input DO 反应器不把 ORP 当作可直接替代 DO 的 forcing。

## 时间与可运行性

长期评价目标仍为 2026-04-14 至 2026-07-30 共 108 天；建议动态预热 2026-03-31 至 2026-04-13。
原拟 2026-04-14 至 2026-05-11 的28天验证候选，因共同过程输入断点，暂不作为完整可运行包。
当前短期试运行选择为 2026-03-31 00:00:00 至 2026-04-28 00:00:00（结束时刻不含）：
预热 14 天，评价从 2026-04-14 00:00:00 开始，共14天。
选择依据是最早的完整日界连续输入窗口，不依据 DQR 高低或下游结果。
14 天只是预热起点建议，必须先建立统一的稳态/已校核状态，并检查 NH4、MLSS、氮平衡是否稳定。
若需从任意初态起步，应按 SRT/状态收敛决定更长预热，不能保证 14 天自动足够。
一旦遇到长断点，不拼接删除后的日期；三策略共同重构或从同一独立初态重新起算，并排除共同预热段。
本次只依据输入覆盖审查区间，没有读取 SUMO 误差，也没有用出水值反向选择窗口。

这 108 天已经经过 DQR 方法修订与查看，只能称修订后时间外评价。
若独立实验室 NH4/TN 尚未打开，可冻结新的下游分析计划后评价这一终点；
不能重新称整个 DQR 方法首次盲测。28 天约 4 个周区块，主要用于工程试运行；
当前14天短期试运行只能检验模型连接、单位和数值稳定性，不足以支撑周区块置信区间的正式效度主张。
正式效应量和区块 CI 应尽量覆盖 8-12 周或全部108天，而不把分钟数视作独立样本量。

评分按 decision_at 向后连接到分钟时刻，最长保留60分钟，端点不含；未把小时评分提前赋给尚不可用的时刻。
5分钟输出为 [t,t+5min) 均值，需5个分钟均有定义，代表区间值，不是 t 时刻已经可获得的瞬时值。
本文件用于离线动态重放，SUMO 内建议明确区间保持或插值设置。读取器不得跨空值区间自动连线。

## 当前科学边界

1. 需要独立遮蔽/故障注入与人工复核后冻结 repair operator，才能把待修复片段升级为可靠重构。
2. 常规 QC 比较器不能直接沿用上次仅 Hampel 清洗的工作表充当完整 v3.0 对照。
3. 该时段回流渠 MLSS 输入全缺失；如它只用于初态校核，可另提供独立 MLSS/SRT 证据，不能凭空填造。
4. 加药流量计工程单位需核实；现有进出水在线数据不能自动冒充独立实验室真值。
5. 尚未提供冻结 SUMO 模型、统一初态和独立实验室 outcome 集合，因此不能宣称正式下游效度已验证。

## 数值核验

{
  "source_hashes_match": true,
  "holdout_5min_rows": 31104,
  "no_future_score": true,
  "unrecoverable_forcing_stays_nan": true,
  "kept_observations_unchanged": true,
  "ORP_negative_values_retained": true,
  "SUMO_DO_nonnegative": true,
  "pilot_DO8_complete": true,
  "pilot_required_process_complete": false,
  "DO6_numeric_changes_vs_common_raw_5min": 0,
  "all_108d_DO8_continuous": false,
  "no_fault_repair_qualification_claimed": true,
  "selected_14d_pilot_complete_except_documented_model_unit_limits": true
}

## 通道摘要

| sensor_id   |   minutes |   full_evidence_minutes |   evidence_limited_pct |   low_trigger_minutes |   gate_fail_minutes |   repaired_minutes |   unrecoverable_minutes |   zero_equivalent_minutes |
|:------------|----------:|------------------------:|-----------------------:|----------------------:|--------------------:|-------------------:|------------------------:|--------------------------:|
| DO_1_1      |    155520 |                    3900 |                97.4923 |                     0 |                   0 |                  0 |                     596 |                         0 |
| DO_1_2      |    155520 |                    3900 |                97.4923 |                     0 |                   0 |                  0 |                     596 |                         0 |
| DO_1_3      |    155520 |                    3900 |                97.4923 |                     0 |                   0 |                  0 |                     596 |                         0 |
| DO_1_4      |    155520 |                    3900 |                97.4923 |                     0 |                   0 |                  0 |                     598 |                     39653 |
| DO_2_1      |    155520 |                    3900 |                97.4923 |                     0 |                   0 |                  0 |                     597 |                         0 |
| DO_2_2      |    155520 |                    3900 |                97.4923 |                     0 |                   0 |                  0 |                     595 |                         0 |
| DO_2_3      |    155520 |                    3900 |                97.4923 |                     0 |                   0 |                  0 |                     595 |                         0 |
| DO_2_4      |    155520 |                    3900 |                97.4923 |                     0 |                   0 |                  0 |                     596 |                         0 |
| ORP_1_1     |    155520 |                    3900 |                97.4923 |                     0 |                   0 |                  0 |                     595 |                         0 |
| ORP_1_2     |    155520 |                    3900 |                97.4923 |                   120 |                   0 |                  0 |                     715 |                         0 |
| ORP_1_3     |    155520 |                    3900 |                97.4923 |                     0 |                   0 |                  0 |                     597 |                         0 |
| ORP_2_1     |    155520 |                    3900 |                97.4923 |                     0 |                   0 |                  0 |                     596 |                         0 |
| ORP_2_2     |    155520 |                    3900 |                97.4923 |                     0 |                   0 |                  0 |                     595 |                         0 |
| ORP_2_3     |    155520 |                    3900 |                97.4923 |                     0 |                   0 |                  0 |                     595 |                         0 |

## 可运行区间

| scope                                                   | start               | end_exclusive       |        days |   warmup_days |   post_warmup_days | supports_28d_plus_warmup   |
|:--------------------------------------------------------|:--------------------|:--------------------|------------:|--------------:|-------------------:|:---------------------------|
| six_aerobic_DO                                          | 2026-03-31 00:00:00 | 2026-06-29 16:30:00 | 90.6875     |            14 |            76.6875 | True                       |
| six_aerobic_DO                                          | 2026-06-29 23:30:00 | 2026-06-30 10:50:00 |  0.472222   |            14 |             0      | False                      |
| six_aerobic_DO                                          | 2026-06-30 11:05:00 | 2026-06-30 11:25:00 |  0.0138889  |            14 |             0      | False                      |
| six_aerobic_DO                                          | 2026-06-30 13:55:00 | 2026-06-30 14:05:00 |  0.00694444 |            14 |             0      | False                      |
| six_aerobic_DO                                          | 2026-06-30 14:35:00 | 2026-06-30 15:00:00 |  0.0173611  |            14 |             0      | False                      |
| six_aerobic_DO                                          | 2026-06-30 15:10:00 | 2026-06-30 15:25:00 |  0.0104167  |            14 |             0      | False                      |
| six_aerobic_DO                                          | 2026-06-30 15:30:00 | 2026-06-30 15:35:00 |  0.00347222 |            14 |             0      | False                      |
| six_aerobic_DO                                          | 2026-06-30 15:40:00 | 2026-06-30 15:55:00 |  0.0104167  |            14 |             0      | False                      |
| six_aerobic_DO                                          | 2026-06-30 16:05:00 | 2026-07-06 14:10:00 |  5.92014    |            14 |             0      | False                      |
| six_aerobic_DO                                          | 2026-07-06 14:20:00 | 2026-07-31 00:00:00 | 24.4028     |            14 |            10.4028 | False                      |
| eight_DO_common_DO4                                     | 2026-03-31 00:00:00 | 2026-06-29 16:30:00 | 90.6875     |            14 |            76.6875 | True                       |
| eight_DO_common_DO4                                     | 2026-06-29 23:30:00 | 2026-06-30 10:50:00 |  0.472222   |            14 |             0      | False                      |
| eight_DO_common_DO4                                     | 2026-06-30 11:05:00 | 2026-06-30 11:25:00 |  0.0138889  |            14 |             0      | False                      |
| eight_DO_common_DO4                                     | 2026-06-30 13:55:00 | 2026-06-30 14:00:00 |  0.00347222 |            14 |             0      | False                      |
| eight_DO_common_DO4                                     | 2026-06-30 14:35:00 | 2026-06-30 14:55:00 |  0.0138889  |            14 |             0      | False                      |
| eight_DO_common_DO4                                     | 2026-06-30 15:10:00 | 2026-06-30 15:25:00 |  0.0104167  |            14 |             0      | False                      |
| eight_DO_common_DO4                                     | 2026-06-30 15:30:00 | 2026-06-30 15:35:00 |  0.00347222 |            14 |             0      | False                      |
| eight_DO_common_DO4                                     | 2026-06-30 15:40:00 | 2026-06-30 15:55:00 |  0.0104167  |            14 |             0      | False                      |
| eight_DO_common_DO4                                     | 2026-06-30 16:05:00 | 2026-07-06 14:10:00 |  5.92014    |            14 |             0      | False                      |
| eight_DO_common_DO4                                     | 2026-07-06 14:20:00 | 2026-07-31 00:00:00 | 24.4028     |            14 |            10.4028 | False                      |
| eight_DO_plus_required_process_nonmissing_units_pending | 2026-03-31 00:00:00 | 2026-05-09 17:05:00 | 39.7118     |            14 |            25.7118 | False                      |
| eight_DO_plus_required_process_nonmissing_units_pending | 2026-05-09 19:35:00 | 2026-06-29 12:15:00 | 50.6944     |            14 |            36.6944 | True                       |
| eight_DO_plus_required_process_nonmissing_units_pending | 2026-06-29 15:10:00 | 2026-06-29 16:25:00 |  0.0520833  |            14 |             0      | False                      |
| eight_DO_plus_required_process_nonmissing_units_pending | 2026-06-29 23:30:00 | 2026-06-30 10:50:00 |  0.472222   |            14 |             0      | False                      |
| eight_DO_plus_required_process_nonmissing_units_pending | 2026-06-30 11:05:00 | 2026-06-30 11:25:00 |  0.0138889  |            14 |             0      | False                      |
| eight_DO_plus_required_process_nonmissing_units_pending | 2026-06-30 13:55:00 | 2026-06-30 14:00:00 |  0.00347222 |            14 |             0      | False                      |
| eight_DO_plus_required_process_nonmissing_units_pending | 2026-06-30 14:35:00 | 2026-06-30 14:55:00 |  0.0138889  |            14 |             0      | False                      |
| eight_DO_plus_required_process_nonmissing_units_pending | 2026-06-30 15:10:00 | 2026-06-30 15:25:00 |  0.0104167  |            14 |             0      | False                      |
| eight_DO_plus_required_process_nonmissing_units_pending | 2026-06-30 15:30:00 | 2026-06-30 15:35:00 |  0.00347222 |            14 |             0      | False                      |
| eight_DO_plus_required_process_nonmissing_units_pending | 2026-06-30 15:40:00 | 2026-06-30 15:55:00 |  0.0104167  |            14 |             0      | False                      |
| eight_DO_plus_required_process_nonmissing_units_pending | 2026-06-30 16:05:00 | 2026-07-06 14:10:00 |  5.92014    |            14 |             0      | False                      |
| eight_DO_plus_required_process_nonmissing_units_pending | 2026-07-06 14:20:00 | 2026-07-30 21:45:00 | 24.309      |            14 |            10.309  | False                      |

## 软件依据

Dynamita 官方说明 Input DO 由指定 DO 驱动并计算需气量，动态模拟依赖共同初态。
- https://wiki.dynamita.com/en/process_units
- https://wiki.dynamita.com/en/using-sumo
- https://wiki.dynamita.com/en/advanced-simulations

依据文件：260917_DQR_InputDO_下游使用适宜性独立验证方案_顶刊SCI最终可执行版_v3.0.docx。
