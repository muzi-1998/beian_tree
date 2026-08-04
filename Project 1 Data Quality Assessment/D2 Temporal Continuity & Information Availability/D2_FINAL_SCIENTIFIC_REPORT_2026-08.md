# D2 Temporal Continuity & Information Availability

## V2 最终科学审查报告

**冻结日期：** 2026-08-04
**运行号：** `D2V2_20260804_1823`
**校准号：** `NorthBank_D2_v2_20260804`
**映射版本：** `d2_v2_hard_availability_r1`
**研究设计：** `d2_blocked_time_v1`

## 1. 专家结论

D2 已完成单厂回顾性研究范围内的科学收口，可以进入 D1-D5 子分项聚合。当前版本对时间完整性、断点严重度与硬信息可用性进行独立评分；D1 仅用于构念一致性分析，不参与 D2 的映射、阈值、权重或数值计算。

当前证据支持以下主张：

1. D2 在冻结的时间区块上具有稳定的内部时序效度。
2. 后缺氧低 DO 工艺地板、数值分辨率受限与传感器数字锁死已经分离。
3. QFA 的生产证据仅包括缺失、长断点和至少 15 min 的硬观测锁死。
4. 预设聚合权重与 `lambda` 的合理扰动不改变通道排序，并仅在极端设置下轻度改变事件边界。
5. D1 与 D2 在时间上存在高于机会水平的共现，但绝对重叠很低，支持二者作为独立评价维度。

当前证据不支持以下主张：

1. 不宣称已经完成跨厂外部验证。
2. 不宣称 `0.20 mg L-1` 工艺地板阈值可直接迁移到其他厂。
3. 无 SCADA、网络和计划停机日志时，不对硬可用性事件作传感器、网络或运维原因归属。
4. 不以本研究结果反向优化 D2 权重、映射断点或低分阈值。

## 2. 校准与验证设计

### 2.1 校准是否来自独立样本

`d2_calibration.yaml` 不是跨厂外部独立样本校准。其科学定位为单厂、时间阻断的开发期参考：

| 阶段 | 时间 | 用途 |
|---|---|---|
| Development | 2025-08-01 至 2025-12-31 | 仅建立描述性参考分布和 response-loss 诊断基准 |
| Internal validation | 2026-01-01 至 2026-02-21 | 冻结参数后的内部时序验证 |
| Terminal test | 2026-02-22 至 2026-04-13 | 末端独立时序测试 |
| External site | 暂缓 | 不影响本次单厂回顾性发布 |

映射断点、Veto 阈值及聚合权重来自预设工程合同，并非从当前全期数据拟合。开发期共含 3649 个有效小时、51086 个传感器小时；验证期和末端测试期未参与参数选择。

因此，论文中应使用 `temporally blocked internal validation`，不能写成 `external independent calibration`。

## 3. QFA 语义与 process-floor 合同

### 3.1 生产与诊断证据分离

生产 QFA 只使用：

- 缺失观测；
- 长断点；
- 连续至少 15 min 的完全数字锁死。

以下字段仅用于解释和敏感性分析，不降低生产 QFA：

- 3 min soft RLE；
- 低 IQR；
- `floor_occupancy`；
- `resolution_limited`；
- response-loss。

response-loss 在配置、评分器、校准表、事件表和传感器画像中均明确标记为 `diagnostic_only`。所有 199 个硬可用性事件的 `response_loss_tier_used` 均为 0。

### 3.2 两条后缺氧 DO 通道

五类机制挑战全部通过：真实低氧地板、数字锁死、低氧小幅波动、离开地板后的响应恢复、缺失/长断点不豁免。

| 通道 | 地板占比 | 分辨率受限 | 硬锁死 | QFA 不可用 | 总 Veto | 平均 QFA |
|---|---:|---:|---:|---:|---:|---:|
| `DO_1_4` | 96.09% | 57.81% | 0.012% | 0.385% | 0.931% | 4.978 |
| `DO_2_4` | 69.89% | 16.88% | 0.254% | 0.625% | 1.242% | 4.965 |

结论是：后缺氧区长期低值和分辨率受限是重要工艺解释，但不等价于传感器不可用。

## 4. 聚合权重与 lambda 稳健性

主模型继续使用 `QTI/QGS/QFA = 0.30/0.30/0.40`、`lambda = 0.70`。该组合是预设合同，不由当前结果选择。

敏感性分析比较等权、QFA 0.40、QFA 0.50 与 `lambda = 0.50/0.70/0.90` 共 9 个组合，并采用 sensor-month cluster bootstrap：

- 所有组合的通道排序 Spearman rho 点估计均为 1.000；
- 95% CI 下界最低为 0.978；
- 低分小时 Jaccard 为 0.919-1.000；
- 低分事件 Jaccard 为 0.820-1.000；
- 极端的等权、`lambda = 0.90` 对事件边界影响最大；
- 低分小时率仅在 1.043%-1.187% 之间变化。

因此，QFA 权重 0.40 可以保留。其合理性来自硬可用性事件的不可替代性和稳健性结果，而不是“冻结比其他维度更重要”的先验断言。由于低 IQR、soft RLE 和 response-loss 已退出生产评分，QFA 与 D1 的冻结/健康检测不构成数值重复。

## 5. 分布、低尾与 ORP 解释

D2 分数高度集中在 5 分，按中位数、IQR 或 P05 展示会产生明显天花板效应。因此，论文主结果应强调小时级低分率、sensor-day 事件负担和时间区块差异；中位数、IQR 与 P05 作为完整描述统计保留在源数据和补充表。

全期低于 3 分的小时率如下：

| 分析物 | QTI | QGS | QFA | D2 total |
|---|---:|---:|---:|---:|
| DO | 0.327% | 1.146% | 0.778% | 1.203% |
| ORP | 0.327% | 1.157% | 0.572% | 1.046% |

ORP 的 soft-stasis 诊断占比为 20.43%，高于 DO 的 10.25%；但修正生产语义后，ORP 的 QFA 低分率、总低分率和 Veto 率均不高于 DO。旧版本中 ORP 低分偏多主要来自低 IQR/短 RLE 被误当成硬不可用，而不是 ORP 本身质量必然更差。

QTI/QGS 映射断点乘以 0.8、1.0 和 1.2 后，低分率变化小于 0.005 个百分点，说明二者低方差主要源于数据中时间戳完整性较高，而不是单一映射选择造成。

## 6. 工艺地板阈值的可迁移性

`0.20 mg L-1` 当前仅用于 `floor_occupancy` 与 `resolution_limited` 的工艺诊断，不进入生产 QFA、Veto 或 D2 total。将阈值改为 0.10、0.20 和 0.30 mg L-1 时，诊断地板占比分别为 71.8%、82.9% 和 88.5%，生产评分不变。

因此，本研究可以主张 D2 对该诊断阈值不敏感，但不能主张 0.20 mg L-1 具有跨季节、跨策略或跨厂的普适生理意义。跨厂阈值验证按研究计划暂缓。

## 7. D1-D2 构念边界

采用 1 h 容差的一对一事件匹配，并使用每通道至少平移 7 d 的循环移位空模型：

- D1 健康事件 81 个；
- D2 硬可用性事件 199 个；
- 一对一匹配 5 对；
- 事件 Jaccard 为 0.0182；
- 时长 Jaccard 为 0.0183；
- 空模型中位数为 0.00374；
- 富集倍数为 4.89；
- Monte Carlo 上界 P = 0.0005。

这表明两类事件可受共同运行背景影响，但 D1 的传感器健康异常与 D2 的时间/信息可用性不是同一构念。Fig. 16 比旧 Fig. 11 更适合作为论文中的主证据；Fig. 12 可作为代表性时序补充图。

## 8. 图组评价与论文取舍

新增 Fig. 13-16 均由 Python/matplotlib 生成，采用 Arial、统一轴线、向外刻度、`(a)`-`(d)` 面板标签、可编辑 SVG/PDF、600 dpi PNG/TIFF，并提供源数据。

| 图 | 论文价值 | 建议位置 |
|---|---|---|
| Fig. 13 process-floor contract | 证明低工艺值与硬不可用分离 | 主文 |
| Fig. 14 aggregation robustness | 证明权重、lambda 和映射扰动稳健 | 主文或扩展数据 |
| Fig. 15 low-tail reporting | 避免中位数天花板，展示真正风险负担 | 主文 |
| Fig. 16 D1-D2 construct separation | 证明维度相关但不重复 | 主文 |
| Fig. 01 overview | 全通道时间概览 | 主文背景或扩展数据 |
| Fig. 05 availability evidence | 详细机制拆分 | 扩展数据 |
| Fig. 02 violins | 天花板明显，信息量较低 | 补充材料 |
| Fig. 06/10 | 映射与校准审计 | 补充方法 |
| Fig. 11/12 | 描述性事件与时序实例 | 补充材料 |

若 D2 作为 D1-D5 综合论文中的一个维度，正文建议优先使用 Fig. 13、Fig. 15 和 Fig. 16，Fig. 14 可压缩为扩展数据；不建议在主文同时保留 Fig. 02 与 Fig. 15。

## 9. 输出与复现

关键产物：

- `configs/d2_study_design.yaml`：冻结时间区块和外部验证状态；
- `d2_calibration.yaml`：开发期参考与预设映射合同；
- `artifacts/data/D2_main_scores_hourly.xlsx`：最终小时级评分；
- `artifacts/data/D2_process_floor_casebook.xlsx`：机制挑战和真实通道案例；
- `artifacts/validation/`：权重、阈值、分布、效应量、D1-D2 空模型及图源数据；
- `artifacts/figures/D2_Fig13-16.*`：新增论文图；
- `artifacts/D2_release_manifest.json`：发布文件 SHA-256 清单。

复现顺序：

```bash
python run_d2_pipeline.py
python validate_d2_process_floor.py
python run_d2_scientific_validation.py
python make_d2_figures.py
python make_d1d2_joint_figures.py
python make_d2_scientific_figures.py
python build_d2_release_manifest.py
python -m pytest test_d2_contract_regression.py test_d2_p0p1_regression.py test_d2_process_floor_regression.py -q --import-mode=importlib
```

## 10. 剩余工作

以下内容不阻断当前单厂子分聚合，但投稿时必须作为限制或后续验证说明：

- 通过 SCADA、网络和计划停机日志验证硬可用性事件原因；
- 在其他厂检验映射、权重与工艺地板诊断阈值的迁移性；
- 在综合指数阶段开展预设权重、覆盖率与下游任务的独立验证，不能用下游结果反向选择本轮 D2 权重。
