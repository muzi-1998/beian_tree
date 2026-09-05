# 2026 年后续时段验证：接入审计与研究方案

状态：**接入审计已执行；完整评分、故障注入、模板更新均未执行。**

- [专家审查与详细研究方案](RESEARCH_PLAN_20260905.md)
- [待锁定的分析合同](protocol_candidate.yaml)，不是已启动的生产配置或事后伪装的预注册。
- [源文件、时间范围与 SHA-256 审计](intake_audit/intake_manifest.json)
- [18 个变量的命名映射](intake_audit/channel_mapping.csv)
- [历史重叠与新增时间戳核验](intake_audit/historical_overlap.csv)
- [小时表、日报表的历史汇总一致性诊断](intake_audit/historical_aggregation_identity.csv)
- [新增期间导出值的月度完整性](intake_audit/new_period_completeness.csv)

## 核心结论

可以准备 **2026-04-14 至 2026-07-30 的同厂锁定时间外推验证**，主输入必须使用同目录的分钟数据，不使用日报均值替代。新增 108 天，名义上 36,288 sensor-hours；实际可评价暴露量由各窗口及证据合同决定。

新旧 18 个通道在 367,156 个共同历史时刻完全一致；旧文件缺失的 1,082 个分钟时刻在新文件中仍为空。原始数据没有修改、复制或上传。新增时段仅检查结构与缺失，不检查评分表现或选择模型。

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
