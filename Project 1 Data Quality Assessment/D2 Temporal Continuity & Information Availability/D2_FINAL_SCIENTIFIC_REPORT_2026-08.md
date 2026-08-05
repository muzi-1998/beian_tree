# D2 Temporal Continuity & Information Availability

## V4 strict/sensitive 科学审查报告

- 冻结日期：2026-08-05
- 运行号：`D2V4_20260805_1127`
- 校准号：`NorthBank_D2_v4_20260805`
- 映射版本：`d2_v4_strict_hard_availability_r1`
- 校准基础：`blocked_development_reference_v4_hard_only`
- 适用范围：北岸厂单厂回顾性评价；外部厂验证暂缓

## 1. 专家结论

D2 V4 已完成进入 D1-D5 子分项聚合所需的技术收口。三个正式子分的职责为：

1. `Q_TI`：原始时间戳完整性和缺失覆盖率；
2. `Q_GS`：缺失片段的持续性和拓扑严重度；
3. `Q_HA`：仅在原始观测存在时评价分辨率等效持续硬停滞。

缺失不再进入 `Q_HA`，低 IQR、3 min soft RLE、response-loss 和平行池单点偏离不直接降低正式分数。正式聚合输出为 `D2_Strict`；软低动态仅形成 `D2_Sensitive_risk` 诊断标签，不产生未经校准的第二套数值评分。

当前约 4.96 的均值是低缺陷数据和分段映射共同造成的天花板结果，不能作为主要通道排序依据。它在当前严格语义下是可解释的，但论文必须以低尾事件负担、事件持续时间、Veto 原因和冻结时间区块为主要结果。

## 2. 评分合同

### 2.1 QTI

`Q_TI` 采用 missing / true irregular / duplicate / out-of-order = `0.65/0.25/0.05/0.05`。重复、乱序和真实不规则采样均在排序、去重和 1 min 对齐之前，从原始时间戳计算。无法观测的分量不按满分处理，而按可观测证据条件归一化。

当前原始源文件中的 duplicate、out-of-order 和 true-irregular 均为 0，因此这些分量的阈值敏感性不能证明阈值“最优”；其功能性由受控原始时间戳注入验证。

### 2.2 QGS

`Q_GS` 独立评价最长缺口、P95 缺口时长和缺口次数。旧 `irregular_rate` 的“缺口后恢复次数”语义已退出 QTI，避免与 gap-run count 重复。

### 2.3 QHA

正式定义为：

`hard_stasis_fraction_observed = hard-stasis minutes / present-raw minutes`

硬停滞是相邻观测变化不超过传感器分辨率阈值且持续至少 15 min 的“分辨率等效持续停滞”，不要求浮点值绝对相等。生产窗口为 6 h。

`Q_FA` 仅保留为兼容别名，数值等于 `Q_HA`；论文、报告和新接口统一使用 `Q_HA`。

## 3. Strict 与 Sensitive

`D2_Strict` 使用 `Q_TI/Q_GS/Q_HA = 0.30/0.30/0.40` 和预设 Veto 合同。该权重是工程先验，不宣称为单厂数据拟合得到的全局最优权重。

`D2_Sensitive_risk` 仅在至少两个独立证据族共同支持并持续 2 h 时触发：

- 内生低动态证据族：low IQR 和 soft RLE 视为同一证据族，不能相互凑数；
- 独立同伴证据族：仅在同工艺位置、可比激励的 peer 存在时启用 response-loss；
- process-floor 通道无可比 peer 时不生成准冻结结论。

按分析物汇总，DO 的内生低动态约 10.77%，联合软证据约 0.059%，持续准冻结嫌疑约 0.043%；ORP 分别约 11.77%、3.96% 和 2.50%。ORP 的软动态风险高于 DO，但 ORP 的正式 `Q_HA < 3` 为 0，说明 V4 没有把稳定工艺平台直接解释成硬不可用。

## 4. Process-floor 合同

五类机制挑战全部通过：真实低氧地板、数字锁死、低氧小幅波动、离开地板后的响应恢复、missing/long gap 不被地板路线豁免。

机制图将前四类响应拆为共享坐标的小型时间序列，并以独立连续性条带显示第五类 missing/long gap。15 min 是首个硬停滞资格门槛；在当前 6 h 投影合同下，受控数字锁死首次使 `Q_HA < 5` 的等效持续时间为 30 min。真实 0 覆盖率以空心零值绘制，不再以正数裁剪后放入对数轴。

| 通道 | 工艺地板占比 | 分辨率受限 | 硬停滞 | QHA Veto | 总 Veto | 平均 QHA |
|---|---:|---:|---:|---:|---:|---:|
| `DO_1_4` | 96.09% | 57.81% | 0.012% | 0.000% | 0.931% | 4.999 |
| `DO_2_4` | 69.89% | 16.88% | 0.254% | 0.310% | 1.242% | 4.987 |

结论：两条位置 4 通道使用相同语义合同。低氧地板和有限分辨率是诊断字段，不是传感器冻结；真实 missing/gap 仍由 QTI/QGS 和相应 Veto 处理。

## 5. 天花板效应与低尾结果

全期平均 D2 为 4.94-4.96，均值、P50 和 IQR 的通道区分力有限。推荐论文主要报告：

- 每 1000 sensor-hours 的低分小时数和 Veto 小时数；
- 每 1000 sensor-hours 的事件数；
- 事件持续时间中位数、P95 和最长不可用事件；
- development / internal validation / terminal test 分阶段结果；
- Strict 覆盖率和 Sensitive 诊断风险率。

三个冻结阶段的通道中位低分负担分别为 6.30、24.04 和 3.27 h/1000 sensor-hours；对应中位 Veto 负担相同，说明正式低尾主要由预设严重事件门控驱动，而不是均值轻微波动。

全分析物低分事件频率在 development、internal validation 和 terminal test 分别为 0.294、0.801 和 1.050 events/1000 sensor-hours。前两阶段事件持续时间中位数分别为 23 h 和 30 h；terminal test 中位数为 4 h、P95 和最大值均为 19 h。Veto 组成随阶段变化：development 几乎全部由 missing 驱动，internal validation 以 gap + missing 为主，terminal test 则出现更高比例的硬停滞。事件数、持续时间和 Veto 原因均按独立量纲展示，不再把 deficit points 与 hours 放在同一纵轴比较。

通道级画像进一步显示，14 个通道的 `D2_Strict` 中位数、P05、IQR 和 P95 均为 5.0，Grade A 占 96.62%-98.04%，确认均值排序存在明显天花板限制。低分负担和 Veto 负担在每个通道上完全一致，为 9.31-12.58 h/1000 sensor-hours；这意味着当前正式低尾均由严重门控事件形成，而不是连续分数轻微下降。DO 第2线通道的 Veto 中约 25%-26% 来自 hard availability loss，其余通道主要由 severe missing、gap + missing 和 severe gap 构成。该结果支持将 Fig. 15 定位为“通道级结果与低尾风险画像”，而不是均值比较图。

## 6. 证据独立性与权重解释

`Q_TI` 与 `Q_GS` 的小时级 Pearson `r`、Spearman `rho`、低分事件 `phi` 和低分事件 Jaccard 分别为 0.961、0.900、0.729 和 0.563，因为缺失比例与缺口严重度共享同一连续性背景；`Q_HA` 与二者的连续相关和低尾重叠均接近 0，有效证据维数为 1.86。

消融结果显示：

- 去除 QTI 中 missing 或去除 QGS，不改变当前低分事件身份，但会改变得分缺口；
- 去除 QHA 后，低分事件 Jaccard 为 0.894（cluster 95% CI 0.787-0.979），候选事件由 47 降至 42；
- 去除 QHA 后通道排序 Spearman 仅约 0.244。

因此，权重稳健性只能表明单厂结论在合理扰动内稳定，不能证明 `0.30/0.30/0.40` 普适最优。QHA 提供了与连续性不同的事件证据，应保留；QTI/QGS 的相关性应在论文中透明报告。

## 7. 端到端注入与窗口稳健性

新增 raw timestamp/measurement 到 D2 的全管线挑战：

- duplicate rate；
- out-of-order rate；
- 66、70、90、110 s 不规则采样；
- 2、5、6、15、20、30、60、360 min 单缺口和 10 个分散的 2 min 缺口；
- 10、15、20、30、45、60、90、120、180 min 持续硬停滞；
- 10/15/20/30 min 阈值与 3/6/9/12 h 窗口组合。

7/7 剂量-响应组满足非递减单调性，未注入基线组假阳性为 0。恢复时间仅在故障已检出时计算。

V4 窗口敏感性结果：

| QHA 窗口 | 低分事件 Jaccard vs 6 h | 是否通过预设 0.75 |
|---:|---:|---|
| 3 h | 0.922 | 是 |
| 6 h | 1.000 | 是 |
| 9 h | 0.979 | 是 |
| 12 h | 0.979 | 是 |

这替代了旧语义版本中不能直接沿用的窗口敏感性结论。

事件数量在 3/6/9/12 h 窗口下分别为 51、47、46 和 46；对应低分小时率约为 1.00%-1.02%。主图同时报告以 sensor-month 为簇的 95% CI，避免只用四个点掩盖事件支持量。单个 20 min 连续缺口的最低 `Q_GS` 为 3.98，而总缺失时长同为 20 min 的十个分散短缺口为 4.70，验证了缺口拓扑而非仅缺失总量的设计目的。

## 8. D1-D2 构念边界

D1 有 81 个健康事件，D2 有 45 个硬可用性事件，仅 5 对在 +/-1 h 容差内一对一匹配。事件 Jaccard 为 0.041，持续时间 Jaccard 为 0.021；传感器特异全期循环移位空模型均值为 0.00113，按 development/validation/terminal-test 阶段约束的敏感性空模型均值为 0.000116，两者的 Monte Carlo 上尾 P 均为 0.0005。

两维度受共同运行背景影响但绝对重叠很小。D1 只用于构念效度解释，不参与 D2 阈值、权重、映射或数值计算。

## 9. 论文图组

建议正文优先使用：

- Fig. 13 `D2_Fig13_process_floor_contract`：五类 process-floor 机制合同、15 min 资格门槛和现场证据分离；
- Fig. 14 `D2_Fig14_evidence_hierarchy_ablation`：分支证据层级、连续/低尾关联与事件级消融；
- Fig. 15 `D2_Fig15_channel_outcome_risk_profile`：通道级分布、A-E 等级构成、低分/Veto 负担、限制来源和阶段变化；
- Fig. 16 `D2_Fig16_limited_event_concordance`：D1-D2 有限时间一致性及阶段约束空模型；
- Fig. 18 `D2_Fig18_full_pipeline_validation`：时间戳、缺口拓扑、硬停滞和窗口稳健性全管线验证。

Fig. 01/05/17 可作为方法或扩展数据；Fig. 02 小提琴图因天花板明显，建议仅置补充材料。所有新增主图使用 Arial、统一轴线、外向刻度和连续 `(a)`-`(f)` 标签；全边框图按图形合同使用向内刻度。每图输出 600 dpi PNG/TIFF 及可编辑 SVG/PDF，并提供 Excel 源数据。

## 10. 已执行与待议

### 已执行

- QHA 硬可用性正式化并从 missing 中解耦；
- Strict 数值与 Sensitive 诊断双层接口；
- 独立证据族联合门控及 process-floor 豁免；
- 修复空 pytest 和不可达断言；
- 增加 full-pipeline 时间戳、缺口和硬停滞注入；
- 重做 3/6/9/12 h V4 窗口稳健性；
- 增加 Pearson/Spearman/低尾 phi/Jaccard、证据消融、事件负担及 D1-D2 全期/阶段约束空模型；
- 重绘具有论文价值的 Fig. 13-18。

### 待议或未执行

- 不生成未经标签校准的 `D2_Sensitive` 数值分数，仅报告风险标签；
- 不加入样本熵或更多局部动态特征，避免在无真值时增加复杂度；
- D7 空间一致性不进入 D2 数值，仅可用于下游归因，保持维度独立；
- 开发期分位数在零缺陷时间戳上退化，故不替换预设工程阈值；
- 其他厂、SCADA/网络/计划停机日志和运维故障真值验证暂缓；
- 当前版本可用于单厂回顾性聚合和论文主结果，但不能宣称跨厂普适或完成原因归属验证。

## 11. 复现顺序

```powershell
python run_d2_pipeline.py
python validate_d2_process_floor.py
python run_d2_full_pipeline_validation.py
python run_d2_scientific_validation.py
python make_d2_figures.py
python make_d1d2_joint_figures.py
python make_d2_scientific_figures.py
python build_d2_release_manifest.py
python -m pytest test_d2_contract_regression.py test_d2_p0p1_regression.py test_d2_process_floor_regression.py test_d2_timestamp_qti_regression.py test_d2_full_pipeline_injection.py -q --import-mode=importlib
```
