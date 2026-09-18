# D3/D4中性参考准入与跨维度评分依赖分离：执行报告

## 总体结论

已按六项最终建议实施。正式路线改为“共享原始数据基础 + 独立质量证据生成 + 分层整合”。准确表述是**计算与评分依赖分离**，不是统计独立。D1/D2不再决定D3温度包络主参考及D4主参考/可评价资格；D5原模型、正式数值、L1支持状态及OOD规则未调整。

本次修改不以提高分数、扩大Full覆盖或降低警告率为模型选择目标。参考准入确实会改变数值，应保留敏感性结果，而不能声称“只是工程迁移、结果基本不变”。

## 已执行的六项

1. **D3 v2.8.0**：只改温度条件DO包络参考准入，估计器、训练期、饱和值公式、位置共享方式、评分权重均保持。中性条件为原始DO存在、未插补、温度有效、注册量程内、每小时至少30个原始有效分钟。恒定但真实存在的观测不因低方差被排除。旧D1/D2筛选α冻结为敏感性，不称为故障真值清洁集。
2. **D4 v1.6**：主参考不使用D1≥4.5及D2评分/Veto。要求完整过去24 h窗口、双侧同步原始支持、风险指标支持、开发期锁定及工况纯度≥0.90。分钟同步支持和小时支持阈值维持0.80；“完整24 h”表示窗口跨度完整，不表示1440分钟不得有任何缺失。硬停滞有观测时计为存在，不能被支持层提前屏蔽。
3. **公共参考及证据强度**：继续analyte×regime公共映射，保留窗口数、独立7 d区块及尾部分位点精度。每个pair-hour携带calibration scope、quality、evidence quality、independent blocks和tail precision grade；这些是证据元数据，不额外惩罚D4_raw。block-median quantiles、P99截尾及排除最高风险区块均仅敏感性。
4. **共享工况模块**：新增`shared_data_foundation`。D4的24 h均值/标准差及周期特征、标准化、K=4聚类仅用开发期拟合；未来数据仅推断，不回填前部特征。D5保留独立版本的稳健特征、后验、OOD和滞回，不把D4的R0-R3强行等同于D5同名标签。D1冻结历史结果未被静默重算。
5. **独立性与时间测试**：D3中性资格计算禁止读取其他评分工作簿；D4在删除评分输入列、注入低D1分/高D2 Veto并禁止工作簿访问后，参考集合、映射及原始评分保持一致。未来原始数据扰动不改变开发期工况模型；常值观测和缺失的支持语义有独立测试。
6. **下游刷新与历史保留**：D3/D4验证、事件、敏感性、图源及图件已重跑；D5仅刷新D4依赖审查与相关图表；DQR创建`outputs/aggregation_v2_4`，不覆盖v2.2/v2.3。原数据与原时间验证分支未修改，旧D3/D4数据保留在`frozen_baseline`并绑定原Git提交。108天采用单独的“修订后时间外再评价”目录，禁止重新声称首次盲测。

## 关键结果

### D3：参考假设具有实际影响

| 好氧位置 | 原筛选α | 新中性α | 相对变化 | 本次角色 |
|---|---:|---:|---:|---|
| 1 | 0.2789373 | 0.3463141 | +24.2% | 运行软警告 |
| 2 | 0.3100300 | 0.3715629 | +19.8% | 运行软警告 |
| 3 | 0.5065766 | 0.6814501 | +34.5% | 仍仅诊断 |

估计器仍为`max(P99, median + 3 × 1.4826 × MAD)`，两条平行线同位置共享，不做每支传感器完全自我归一化。校准期仍为2025-08至2026-01；后续阶段不参与参数估计。

在**相同中性支持**上，新路线验证期好氧位置1/2的2 h警告率为0%–0.424%。这只是警告发生率，不是无故障真值支持的假阳性率。DO_2_3在旧筛选α下的2 h警告率为33.05%，新α下为0.424%，但包络变宽不能证明传感器恢复正常，因此位置3未晋级。

历史正式评分仅4支好氧位置1/2通道变化，平均增加0.0106–0.0267分；其余10支评分不变。201个2 h窗口由Warn转为Pass，对应聚合接口减少402个Warn sensor-hours。个别窗口变化可达1.6分，不应以小均值掩盖局部影响。

### D4：不能把筛选敏感性误写成稳健无差异

在相同原始风险指标和冻结工况下，仅改回D1/D2筛选，7对通道均值相对中性主路线降低0.190–0.521分，低分小时Jaccard为0.380–0.748。这说明跨维度筛选确实塑造参考分布；中性主路线避免这条数值依赖，但并不等价于获得故障真值。

工况纯度0.80/0.90/1.00敏感性相对稳定，低分小时Jaccard不低于约0.991。其他稳健估计器仍为敏感性，不据验证表现挑选替代正式估计器。P99截尾基本不改变P97.5及以下映射是结构上的预期，不能把这一无变化单独当作强验证。

主路线有42,189个可评价pair-hours。受控挑战AUROC：drift 0.880、step 0.840、freeze 0.727；共同工况负对照conditional FAR约0.0319。它们是受控挑战性能，不是现场故障检出率。D1–D4 Spearman约0.168；D4–D5 report/raw双范围Spearman约0.179/0.153，支持有限关联而非统计独立。

### DQR及108天

历史期节点Full 39,606、Basic 46,004、Limited 406；D1/D2/D5不变，所以节点Quality不变，D3 Gate与D4驱动的pair结果更新。Quality、Evidence和Gate继续分开，不把证据不足乘入质量。

108天端到端结果：36,288 sensor-hours、18,144 pair-hours；D4可用17,661 pair-hours。D5正式report仅924个sensor-hours（2.546%），Full为910（2.508%），二者分母相同但Full还要求D1/D2存在。D5 out-of-template状态占56.60%，其余主要为有限模板支持；不能把全部不可评价归因于OOD或传感器故障。

108天节点Core/Full/availability-aware的sensor-hour pooled mean分别为4.6308/4.1228/4.6166，均与原T0节点数值一致。不可将Full与Basic差异直接解释为真实质量变化。D3 Warn为5,330个sensor-hours。完整时间接合、冻结数值及公式核验共23项通过。

## 结果位置

相对于`Project 1 Data Quality Assessment`：

| 内容 | 位置 |
|---|---|
| D3正式结果、校准/敏感性与11幅图 | `D3 Physical rationality and rate constraints/outputs/` |
| D4正式结果、公共映射、验证及12幅图 | `D4 Parallel-redundancy Temporal Consistency/outputs/` |
| D5更新的依赖、双范围关联及图表 | `D5 Topological Role Consistency and Structural Representativeness/outputs/publication/`、`outputs/figures/` |
| DQR新版数据、6组图、报告、manifest | `DQR Multidimensional Aggregation and Evidence-Aware Integration/outputs/aggregation_v2_4/` |
| 中性准入与旧筛选的完整对照 | 本目录`D3_reference_comparison.xlsx`、`D4_reference_comparison.xlsx` |
| 专题敏感性图与源数据 | 本目录`Fig_reference_admission_sensitivity.*`及以上两个工作簿 |
| 108天结果、图源、图、QA与报告 | `validation/revised_reference_20260917/` |
| 共享冻结工况 | `shared_data_foundation/outputs/` |

## 验证记录

- 单元与合同测试：D3 34项、D4 28项、D5 35项、共享冻结工况2项；DQR聚合另有8项测试与24项发布核验。
- 108天修订后时间外再评价：23项时间接合、公式、冻结评分与来源核验通过。
- D3图件审计11幅、D4图件审计12幅通过；D5与DQR发布核验同时检查图件和派生数据哈希。
- 专题敏感性图及108天图均提供PNG、TIFF、矢量PDF/SVG与源数据工作簿。静态审计保留对重采样或完整配对筛选的提示，理由见`FIGURE_QA.md`，不将它们伪装为零警告。
- `REVISION_RELEASE_MANIFEST.json`以代码、配置、数据和图件内容哈希为权威；提交号仅标识冻结历史基线。独立CI检查当前检出版本与该清单精确一致。

## 待定及未执行

- 未升级位置3、未以警告率更低为理由重选α或映射、未提升D5 L1/OOD样本等级。
- 未把D5工况替换为D4工况，未重算D1/D2/D5正式评分，未改变聚合权重，未启用A–E或D5硬Veto。
- 历史Section 1.1分解仍是回顾性产品；此次冻结工况不能倒推出整条历史链具有前瞻因果性。108天复用已冻结的因果分解/白化归档输入，另行执行D4因果变点及时间接合。
- 同工况分布受真实故障污染仍可能影响中性参考。这里以敏感性揭示而非用D1删除高风险样本掩盖；需要维护记录、独立故障真值或今后未查看的数据进一步检验。
- D5 Top-1低于预设0.80、外部效标、运维真值、跨厂验证及下游模型效用仍是论文明确限制，不能由本次解耦修复替代。
- 108天归档输入位于原时间验证工作分支，需要随该归档流程才能从原始数据完整重现；本修订不擅自合并其PR、不覆盖原T0结果。

## 建议的材料与方法表述

Primary reference qualification was based on dimension-neutral observations rather than other dimensions' numerical quality scores. D3 temperature-normalized envelopes retained the frozen estimator and used observed, non-imputed, in-range DO with valid temperature and sufficient raw support. D4 public analyte-by-regime mappings used synchronized bilateral raw support over complete trailing windows and a development-fitted process-context model. Observed stasis remained present evidence. D1/D2-screened references and alternative robust estimators were evaluated as sensitivity analyses, not fault-truth references. Score magnitude, calibration evidence strength and integration gates were retained as separate interfaces. This design establishes computational and scoring-dependency separation, not statistical independence. Evaluation on the previously inspected 108-day extension is reported as revised temporal out-of-sample re-evaluation.
