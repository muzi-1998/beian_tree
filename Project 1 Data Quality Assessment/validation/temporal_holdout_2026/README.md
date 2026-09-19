# 2026 年后续时段验证：接入、资产恢复与时间审计

状态：**2026-09-07已完成108天T0自然数据评分及DQR时间连接。** 历史合同通过后才开盲；尚未完成新期受控挑战、全部统计敏感性和现场真值验证。

- [最新执行报告与专家结论](T0_EXECUTION_REPORT_20260907.md)
- [开盲前锁定的T0合同](T0_LOCKED_EXECUTION_20260907.md)
- [新期各维度、DQR、接口与逐行派生数据](outputs/T0_results/)
- [新期图件源表](outputs/source_data/T0/Temporal_holdout_T0_source.xlsx)
- [新期图注及解释边界](T0_FIGURE_LEGENDS.md)
- [开盲内容指纹](outputs/T0_opening_lock.json)

## 历史阶段B记录

- [最新续作报告：D1恢复与分钟输入时钟](STAGE_B2_REPORT_20260906.md)
- [阶段B首轮报告：D2/D4时间问题与资产恢复](STAGE_B_REPORT_20260905.md)
- [图件说明](FIGURE_LEGENDS.md)
- [14张配套源表](outputs/source_data/Temporal_holdout_stage_B_source.xlsx)
- [开盲门控](outputs/opening_gate.json)：记录T0授权时刻；其中尚未计算字段指授权时状态，实际完成情况见T0结果QA。
- [本阶段内容指纹](outputs/stage_B_manifest.json)

## 阶段B目录

| 位置 | 内容 |
|---|---|
| `outputs/assets/` | 恢复的模型候选和冻结映射，不含原始逐分钟观测 |
| `outputs/audit/` | 组件重放、合成试验、旧期修正敏感性及逐行派生结果 |
| `outputs/figures/` | 两幅方法/扩展图，SVG/PDF/PNG/TIFF |
| `outputs/source_data/` | CSV/Parquet/XLSX源表 |
| `recover_*`, `replay_*` | 限制在4月14日前的恢复/重放 |
| `causal_*`, `d2_causal_adapter.py`, `information_time.py` | 独立候选，不覆盖正式D1–D5入口 |
| `d1_recovery_adapter.py`, `d1_scheduled_changepoints.py` | D1恢复日志和固定调度候选 |
| `minute_alignment_contract.py` | 3分钟有界延迟及跨块缺口合同 |
| `verify_stage_b.py`, `test_*` | 组件合同与代码/配置/成果hash核验 |

项目根运行 `python -m pytest validation/temporal_holdout_2026 -q` 和
`python validation/temporal_holdout_2026/verify_stage_b.py`，不需要私有原始资料。
现在同时验证阶段B历史证明与T0自然评分包，**不表示故障检出效能已经通过**。重建要求及执行顺序见最新报告。
原始来源通过 `BEIAN_OFFICIAL_PROJECT`、旧缓存通过 `BEIAN_LEGACY_PROJECT` 指定。

## 原接入审计

- [专家审查与详细研究方案](RESEARCH_PLAN_20260905.md)
- [原候选分析合同，历史记录](protocol_candidate.yaml)，实际T0执行锁见上方新合同；不伪装成采集前预注册。
- [源文件、时间范围与 SHA-256 审计](intake_audit/intake_manifest.json)
- [18 个变量的命名映射](intake_audit/channel_mapping.csv)
- [历史重叠与新增时间戳核验](intake_audit/historical_overlap.csv)
- [小时表、日报表的历史汇总一致性诊断](intake_audit/historical_aggregation_identity.csv)
- [新增期间导出值的月度完整性](intake_audit/new_period_completeness.csv)

## 核心结论

可以准备 **2026-04-14 至 2026-07-30 的同厂锁定时间外推验证**，主输入必须使用同目录的分钟数据，不使用日报均值替代。新增 108 天，名义上 36,288 sensor-hours；实际可评价暴露量由各窗口及证据合同决定。

新旧 18 个通道在 367,156 个共同历史时刻完全一致；旧文件缺失的 1,082 个分钟时刻在新文件中仍为空。原始数据没有修改、复制或上传。接入阶段仅检查结构与缺失；2026-09-07通过后续就绪检查后才开启评分，未用新期选择模型。

**先完成冻结推断接口和历史回放，再打开新时段的评分结果。** 当前 D5 通用入口仍会重新按输入长度计算参考期、拟合模板；不能把全年数据直接交给该入口后称为独立验证。

## 本次文件范围

本目录是跨 D1–D5 的验证入口，不属于 D5 的子模块。原项目的 `outputs`、评分、图件、报告和冻结合同均未改写。候选文件夹名称表示研究启动日期，而非采集日期。

## 复现接入审计

在本目录运行：

```powershell
python -m pytest test_audit_intake.py -q
python audit_intake.py --raw-root 'D:/004_git/beian_tree-main/Project 1 Data Quality Assessment/1.1 Decomposition/Raw data'
```

环境：Python 3.10.5，pandas 2.3.3；还使用 numpy、openpyxl、PyYAML 和 pytest。读取大 Excel 需要数分钟。原始资料须由有权限的研究者在本地提供，不随本目录发布。其他机器只需替换 `--raw-root`。

JSON 中原始文件及 CSV 的 hash 均指**实际字节**，不是科学数值内容摘要。本目录保留 CSV/JSON 字节，避免提交时改变换行使审计失效。`freeze_commit` 是本次审计读取的正式 release 基点，不声称它是后来文档提交的 HEAD。
