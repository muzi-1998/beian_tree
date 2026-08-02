# D1 Challenger Detector 最终修订执行版 v1.1

## 文档状态

| 项目 | 内容 |
|---|---|
| 审查对象 | `260802_D1 Challenger Detector 最终开展方案-spike+step.docx` |
| 冻结运行 | `D1C-20260802-v1.1` |
| 科学状态 | 回顾性开发 + 末端 shadow；外部/未来确认待完成 |
| 发布影响 | 未修改现行 D1 release、状态机、事件文件及 D1-D5 聚合输入 |
| 最终判定 | **DO NOT PROMOTE：不得替换当前发布版检测器** |

## 1. 专家级综合审查结论

### 1.1 是否合理可行

方案的研究问题合理，建立独立 D1 challenger 具有明确必要性，并非与现有 D1 重复：

- 当前发布版 Hampel Spike 与 adjacent-KS Step 的机制范围有限，低召回首先需要被量化为适用边界；
- challenger 可以在不改写正式 D1 的前提下检验短时尖峰、短脉冲、临时偏移和持续阶跃的早期候选发现能力；
- 采用冻结时间拆分、事件级固定报警预算和聚类 bootstrap，能够避免随机时序泄漏与逐点伪重复；
- 失败机制与稀疏单元格强制保留，符合顶刊 SCI 对预设分析和负结果报告的要求。

### 1.2 原方案是否冗余或过于复杂

核心算法不冗余，但原方案的验证分层过度展开。最终版作出以下收敛：

| 原方案问题 | 专家判断 | 最终处理 |
|---|---|---|
| 四类机制与 sensor、analyte、route、regime、resolution 全交叉设硬验收 | 组合稀疏，增加多重比较与事后选择空间 | 硬验收仅限预设 primary amplitude-duration region；其余只作描述性边界 |
| 10-59 min temporary shift 纳入确认性 Step | 缺少冻结的分钟级 Section 1.1 route | 暂缓；确认性 temporary shift 从 1 h 起 |
| process-floor response-loss 与普通 Step 同时检验 | 无可比激励，且与 D2 availability 语义重复 | `DO_1_4`、`DO_2_4` 排除普通 Step；只保留 eligibility/exclusion contract |
| 直接用发布阈值比较 challenger | 双方报警率不同，比较不公平 | 主比较在同一 FAR ceiling 下确定工作点；发布工作点仅作次要运行参照 |
| 末端区段称外部确认 | 当前记录已被既往 D1 开发见过 | 仅称 terminal shadow，不作为 external confirmation |
| 增加多个 detector family 或深度学习 | 当前数据不足以支持算法竞赛 | 仅保留一套统一多尺度 GLR challenger |

### 1.3 最终复杂度判断

一个分钟 track、一个小时 track、一个统一 GLR 统计核和两个冻结 comparator 已足以回答当前科学问题。继续增加深度学习、多个 change-point 家族、传感器专属阈值或全排列消融，会使单厂单记录研究出现不必要的自由度，不建议开展。

## 2. 最终修订版研究方案

### 2.1 研究边界

1. 现行 D1 release、状态机、恢复机制、事件窗口和 D1-D5 聚合输入全部只读。
2. challenger 只研究 Spike/Step；Drift、Freeze、Missingness 和 process-floor availability 不在本研究内重定义。
3. 当前数据最多支持回顾性开发与末端 shadow。即使内部门槛通过，也必须获得未来或外部确认才能讨论替换发布版。

### 2.2 机制合同

| 机制 | 检测路线 | 持续时间 | 幅度范围 | Primary region | 及时终点 |
|---|---|---:|---:|---:|---:|
| Impulse spike | 分钟稳健创新 + multiscale GLR | 1 min | 1-5 个局部稳健 σ | ≥3σ | ≤1 min |
| Short burst | 分钟稳健创新 + multiscale GLR | 2-10 min | 0.75-4σ | ≥2σ 且 ≥3 min | ≤5 min |
| Temporary shift | 冻结小时 route + AR(1) 标准化 GLR | 1-24 h | 0.5-3σ | ≥1.5σ 且 ≥2 h | ≤3 h |
| Persistent step | 小时 GLR 候选 + 发布版 KS 持续性确认 | 24-72 h | 0.5-3σ | ≥1.5σ 且 ≥24 h | 候选 ≤3 h |

定义：σ 为对应注入路线在事件前历史中的稳健局部尺度。注入后不重新拟合趋势、季节、白化、AR、尺度地板、映射或阈值。

### 2.3 因果创新与统计量

分钟创新仅使用当前时点之前的历史：

```text
u_t = [x_t - median(x_(t-g-w):x_(t-g))]
      / max(1.4826 MAD, frozen resolution floor, frozen scale floor)
```

小时 route 的中心、AR(1) 系数和创新尺度只由 development period 的 eligible history 冻结。统一多尺度统计量为：

```text
G_t(d) = |sum(u_(t-j), j=0...d-1)| / sqrt(d)
G_t    = max_d G_t(d)
```

- 分钟尺度：1、2、3、5、10 min；
- 小时尺度：1、2、4、8、12、24 h；
- 方向与入选尺度用于解释，不参与阈值回调。

### 2.4 时间拆分与样本设计

| 区段 | 时间 | 允许用途 |
|---|---|---|
| Development | 2025-08-01 至 2025-12-31 | 冻结创新参数、尺度地板和事件阈值 |
| Internal validation | 2026-01-01 至 2026-02-21 | 主要注入验证；禁止再调参数 |
| Terminal shadow | 2026-02-22 至 2026-04-13 | 末端 shadow 与次要注入验证；不称 external |

每类机制预设 96 个 sensor-onset 事件，其中 internal validation 64 个、terminal shadow 32 个，共 384 个唯一事件设计。分钟机制另计算探索性 `2x_resolution`，因此 trial-level 数据共有 576 行。

同一机制库内，同一传感器的 onset 间隔至少 24 h；不同机制可以复用背景窗口，并分别进行机制级推断。最终审计的最小间隔为 24.0 h。

### 2.5 固定报警预算与 comparator

- family ceiling：0.10 events/sensor-day；minute 与 hourly track 各分配 0.05；
- 阈值只使用 presumed-normal development history，不使用 injected recall；
- 禁止 per-sensor、per-analyte 阈值；
- 主 comparator 为发布 detector score 在同一 FAR ceiling 下的可行工作点；
- 若离散分数不能精确达到 ceiling，则使用不超过 ceiling 的最近可行点；
- 发布阈值保持不变，作为次要运行参照单独报告。

没有运维故障真值，因此当前 development 指标必须称为 high-quality eligible subset 中的 **observed alarm rate**，不能称为 truth-verified false-positive rate。

### 2.6 统计推断与升级规则

- 推断单位：sensor-onset event；
- cluster：`sensor_id + sensor-week base block`；
- 2,000 次 paired cluster bootstrap 估计 recall、95% CI 和配对差值；
- 机制级升级要求：`ΔRecall ≥0.15` 且 `95% CI lower >0`；
- 关键 analyte 非劣界值：0.05；
- 固定报警率门控必须通过；
- external/future confirmation 为替换 release 的必要条件。

## 3. 执行中发现并修正的问题

### 3.1 分钟尺度未来信息泄漏

初版实现曾从整段序列估计分辨率/尺度地板，可能使未来值影响过去分数。现已改为只从 development period 冻结；局部注入只投影到该冻结参数，不再重估。

### 3.2 小时注入 σ 语义不一致

初版按 AR innovation scale 注入，与既有 Step calibration 的 routed-input 局部尺度不一致。最终版统一按事件前 routed-input 稳健尺度定义注入幅度，AR 模型仅承担标准化。

### 3.3 发布包与 challenger 的模块隔离

challenger 与发布 D1 均使用 `src` 包名，动态导入存在命名冲突。最终版在隔离目录内复现冻结 comparator 评分公式，不修改发布模块。

### 3.4 Onset 间隔合同

首次 trial 生成未实际强制 24 h 间隔，存在背景窗口重复。最终版按机制库重新抽样并审计：384 个唯一设计、最小间隔 24.0 h、576/576 trial rows 可评估。

以上均为预设合同一致性修正，没有根据 recall 改变报警预算、故障幅度、GLR 尺度或升级门槛。

## 4. 冻结执行结果

### 4.1 主要机制级结果

以下为 internal validation、original resolution、primary region 的预设结果：

| 机制 | Challenger recall (95% cluster CI) | Baseline under same FAR ceiling | Paired Δ (95% CI) | Gate |
|---|---:|---:|---:|---|
| Impulse spike | 0.000 (0.000-0.000) | 0.125 | -0.125 (-0.273-0.000) | FAIL |
| Short burst | 0.000 (0.000-0.000) | 0.135 | -0.135 (-0.250--0.047) | FAIL |
| Temporary shift | 0.026 (0.000-0.086) | 0.000 | 0.026 (0.000-0.086) | FAIL |
| Persistent step | 0.000 (0.000-0.000) | 0.000 | 0.000 (0.000-0.000) | FAIL |

四类机制均未达到升级门槛。不得在同一数据上降低 Spike/Step 阈值或回选其他模型来“修复”结果。

### 4.2 报警率门控

| Track | Role | Threshold | Events/sensor-day | Poisson 95% CI | Gate |
|---|---|---:|---:|---:|---|
| Minute GLR | Challenger | 50.591 | 0.040 | 0.026-0.058 | PASS |
| Minute Hampel score | Baseline ceiling | 23.956 | 0.045 | 0.031-0.065 | PASS |
| Hourly GLR | Challenger | 11.543 | 0.045 | 0.029-0.067 | PASS |
| Hourly released Step score | Baseline ceiling | 0.786 | 0.002 | 0.000-0.010 | PASS |

小时发布分数是离散的，无法精确达到 0.05，因此使用 ceiling 以下最近可行点。Minute challenger 的阈值达到 50.591，说明 presumed-normal development subset 中仍有极端、未裁决的分钟事件。它们不能在没有真值时被全部称为 false positives。

### 4.3 适用边界与 shadow

- 幅度-持续时间图保留全部零召回和失败单元格；
- 独立 sensor-week cluster 少于 5 的单元格以灰色斜线显示，不插值；
- shadow 事件均标记为 `shadow_unadjudicated`，不能用于估计 specificity；
- 末端 shadow 只用于设计未来人工裁决，不支持部署升级。

## 5. 最终专家判定

**DO NOT PROMOTE。**

当前 challenger 在固定报警率 ceiling 下没有证明相对发布 detector score 的机制级召回增益。应保留现行 D1 release。本次运行作为负结果、适用边界和下一轮数据采集依据。

发布版 Spike recall 约 0.394、Step recall 约 0.240，属于偏低水平，但 recall 不能脱离故障幅度、持续时间、报警预算、事件定义和真值来源直接与文献横向比较。本次结果说明，当前主要障碍不是缺少更复杂的算法，而是：

1. 严格报警预算下，故障与快速工艺变化的可分性不足；
2. presumed-normal history 中存在未裁决极端事件；
3. 缺少运维真值和真正独立的未来/外部确认数据；
4. 低氧 process-floor 通道缺少可比、已验证的 excitation。

## 6. 下一步最小充分工作

1. 获取可裁决的运维故障记录，至少区分快速工况变化、真实传感器故障和未知事件。
2. 冻结一个真正未来时间段或外部厂数据，禁止继续把当前记录当作 confirmation。
3. 若开发 challenger v2，先预注册 null-event arbitration 与机制主终点；不得从本次失败结果中回选阈值。
4. 只有获得冻结的分钟级 Section 1.1 route 后，才扩展 10-59 min temporary shift。
5. 只有存在同工艺位置、可比且验证过的 excitation，才研究 process-floor response-loss。

## 7. 待定与异议项

| 事项 | 当前状态 | 所需证据 |
|---|---|---|
| Observed alarm rate 是否可称 FAR | 待定；当前不称 truth-verified FAR | 运维真值或人工盲审负对照 |
| 10-59 min shift | 暂缓 | 冻结的分钟分解/白化 route |
| Process-floor response-loss | 不纳入 D1 challenger | 同工艺位置、可比且验证过的 excitation |
| Release replacement | 拒绝 | 内部门槛通过 + 独立未来/外部确认 |

## 8. 交付物位置

- 英文机器可读方法合同：`docs/D1_challenger_detector_protocol_v1.1.md`
- 中文最终修订执行版：`docs/260802_D1_Challenger_Detector_最终修订执行版_v1.1.md`
- 配置：`configs/*.yaml`
- 代码与测试：`src/`、`tests/`
- 冻结运行：`outputs/D1C-20260802-v1.1/`
- Trial-level 数据：`data/D1_challenger_trials.parquet`
- Excel 图源与汇总：`data/D1_challenger_source_data.xlsx`
- 专家执行报告：`D1_challenger_expert_report.md`
- 完整性：`run_manifest.json`，包含 SHA-256 哈希

本文件是专家审查后的研究方案与冻结执行记录，不构成生产部署授权。
