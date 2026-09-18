# D3/D4参考集独立性与最终工作区核查

审查日期：2026-09-17。论文：*Topology- and evidence-aware hierarchical data quality assessment for full-scale wastewater treatment sensor networks*。

本报告依据实际代码、配置、已输出分钟数据和实时GitHub状态。当前消息没有附论文Word的可访问路径，因此不是对Word材料与方法的逐段核稿。本轮只新增审查材料；未修改任何生产参数、评分结果、模型或远程分支。

## 1. 总体结论

建议总体合理，值得实施为新的方法版本，但不应直接把原冻结版本覆盖为“原方法一直独立”。

- 应区分校准独立性、运行时数值独立性与统计独立性。
- 当前D3运行时不读取D1/D2评分，但温度包络系数的参考准入使用D1/D2评分。
- 当前D4参考集依赖D1评分及D2 Veto；可用性还受D2 Veto影响。D4_raw聚合公式没有直接加权D1/D2分数，不等于整条生产链无跨维度评分依赖。
- 这些依赖不自动构成闭环循环推断，更不意味着既往结果无效；但与“从参考准入到原始评分均不使用其他维度数值评分或其派生门控”的强主张不一致。
- 改为中性准入能解除这类依赖，但不能证明无故障污染，也不能证明维度间统计独立。
- 推荐架构：共享原始数据与可观测性基础 + 各维度独立参考与原始证据 + 显式分层整合。共享context和原始数据会自然造成相关性，仍需保留冗余/增量信息审查。

## 2. 已核实的代码事实

以下路径相对于 `D:\004_git\beian_tree-main\Project 1 Data Quality Assessment`。

| 位置 | 实际行为 | 审查结论 |
|---|---|---|
| `D3 Physical rationality and rate constraints/configs/d3_physical_bounds.yaml` | v2.7.0；quality_filter列出D1_total、Q_spike、Q_step、Q_drift、Q_freeze、Q_regime、D2_Strict均不低于4.5及D2 usable | 冻结系数的参考定义含跨维度评分筛选 |
| `D3 Physical rationality and rate constraints/src/validation/do_temperature_validation.py::_quality_masks` | 实际读取D1/D2工作簿，构造逐小时掩码并扩展到分钟 | 并非只有文档残留 |
| 同文件 `build_temperature_envelope_audit` | 用筛选后的calibration分钟重算alpha，与生产冻结alpha核对 | 虽位于validation代码中，实质记录了生产参数的筛选来源 |
| `D3 Physical rationality and rate constraints/src/d3_physical/do_temperature_envelope.py` | 生产读取冻结alpha并乘Csat(T) | 运行时数值不需要D1/D2评分 |
| `D4 Parallel-redundancy Temporal Consistency/src/d4/pipeline.py::_fit_and_score` | development + 同步支持 + 双方D1>=4.5 + 双方24 h D2无Veto形成benchmark | 参考集并不独立于D1/D2 |
| 同文件 `usable_for_D4` | data_ok & d2_ok & D4_raw非空 | 可用性不是纯原始观测支持 |
| 同文件 `_load_context` | 从D1工作簿读取regime标签，并依赖D1评分时间轴校验 | 需解除文件与时间轴归属耦合 |
| `D1 Sensor health/src/baseline/regime_clustering.py` | 原始小时通道24 h均值/标准差和周期特征聚类；调用对传入全部有效特征fit；标签含bfill | 移动文件不能自动解决训练边界、起点回填或在线因果性 |
| `D5 Topological Role Consistency and Structural Representativeness/src/d5_local/pipeline/d5_pipeline.py::_build_regime_state` | 自己构造全厂稳健context，拟合参考期模型，并执行后验/OOD/hysteresis | 不应直接用D1的R0-R3替换D5的现有工况模型 |

D1工作簿中的regime标签与D1的Q_regime不是同一个概念。共享模块只能迁移中性context定义及冻结资产，不能顺带把经D1筛选的所有模板标成中性产物。

## 3. D3：建议接受，但影响不是可以忽略的

### 3.1 已完成的准入初筛测算

保持当前估计器 `alpha = max(P99, median + 3 * 1.4826 * MAD)`、位置池化方式及校准期不变；仅比较原D1/D2筛选与原始值存在、温度有效、DO在登记量程[0,20]内的候选准入。

校准期均为2025-08-01至2026-01-31，不使用108天新期数据。

| 好氧位置 | 原参考sensor-minutes | 中性候选sensor-minutes | 已发布alpha | 候选alpha | 相对变化 |
|---|---:|---:|---:|---:|---:|
| 1 | 62,452 | 521,616 | 0.278937 | 0.346309 | +24.15% |
| 2 | 113,862 | 521,638 | 0.310030 | 0.371540 | +19.84% |
| 3 | 120,644 | 521,647 | 0.506577 | 0.681269 | +34.48% |

这是**准入初筛敏感性**，不是批准后的新alpha。原分钟导出由不插补的读取器生成，但该parquet不含逐原始行的插补/时间戳审计标志；本次尚未加入新的小时支持度、独立时间块准入和区块置信区间。不能把上表称为完整neutral production calibration。

原3个系数重放误差均小于1e-9；原输入哈希未变化。另输出“中性基础+原D1/D2筛选”对照，区分量程过滤与评分过滤的影响。

结论：上限系数对参考集选择具有实质敏感性。固定温度下，上限按相同比例升高；但评分变化、Warn率与事件Jaccard尚需完整重跑，不能用系数变化直接替代这些结果。位置3仍维持现有诊断身份，不能因为包络放宽就自动晋级。

### 3.2 推荐正式参考准入

定义 `N_s,t` 为：原始观测存在、不是插补值、温度有效、时间戳有效、在登记量程内。

正式校准集合：

`B_position = calibration period AND N_s,t AND prespecified raw support eligibility`。

量程外原值只从拟合参考集中排除，仍保留在审计与生产物理边界评分中。不能删除待评价的量程外数据。原始时间戳重复/乱序信息应保存在统一时间轴之前；完成对齐不能凭空证明时间戳没有问题。

按位置合并两条线，但应检查日/线权重失衡，不把分钟数当独立样本量。初版主对照保持现有估计器，以隔离准入变化；日块不确定性、两条线互相迁移验证及block-balanced估计作为敏感性。

原D1/D2筛选版本保留为 `D1/D2-screened reference sensitivity`，不能称ground-truth clean reference，因为D1/D2不是独立故障真值。

### 3.3 不接受的推断

- “max(P99, median+3MAD)已经足够稳健，所以无需污染审查”不成立。MAD分支稳健不意味着P99分支不受高尾污染；max可能由受污染的P99决定。
- “范围内+稳定=传感器健康”不成立。缓慢偏移、持续冻结仍可能满足中性条件。
- 上限放宽后警告减少不等于准确率提高。无独立故障真值时应称warning rate，而非FPR。
- 进水温度是代理变量；alpha*Csat应保持“温度条件化运行参考包络”，不是曝气池实测热力学物理上限。

### 3.4 必须输出的成对比较

在相同待评价分钟/窗口上比较两种reference：alpha及日块95%区间；包络差异；分钟高侧警告率；2 h窗口Warn率；Q_value_soft与D3分数差值；事件交/并集与Jaccard；D3_gate状态转换表；按位置、传感器、月份和阶段分层。置信区间按同步日期/时间块抽样，两条线一起保留。

保持仪表边界、DO4零点等效容差、ORP诊断边界、持续速率算法及现有权重不变。本轮方法修改只针对好氧DO温度包络的参考准入。

## 4. D4：中性准入与独立评分的完整合同

### 4.1 参考准入

`reference_eligible = development_lock AND raw_time_valid AND bilateral_raw_support AND context_stable`。

再在analyte×regime公共参考层面执行窗口数、独立时间块数及分位点精度的证据准入。

- 保留当前开发期2025-08-01至2026-01-24及其后embargo，不把验证数据混入。
- 删除D1>=4.5和D2 Veto-derived continuity的主参考筛选；原筛选只留敏感性。
- 双方同步原始观测覆盖、有效共同小时和最大支持缺口必须覆盖同一个24 h窗口。不能只检查末小时。
- context_stable采用窗口内冻结regime占用/迁移信息，不能拿末小时标签冒充24 h稳定。稳定性门槛需预先锁定；可预设0.8/0.9/1.0作敏感性候选，不能看验证得分后选最优值。
- stable regime是参考准入条件，不应自动成为所有生产窗口的排除条件。真实工况转换恰可能是需要评价的对象；生产侧应输出transition和context-support标签，并锁定映射/不可评价策略。

### 4.2 共同支持不是另一个D2

共享observation-support应只输出raw present、time valid、imputed、同步重叠比例和覆盖度等基本事实。不输出D2分数、Veto、Q_HA阈值或由这些派生的usable标志。

**数值不变但仍有原始观测的硬停滞，不能在shared support中被当作缺失删除。**否则D4会在计算关系失配前排除要检验的冻结故障，反而产生选择偏差。

可采用 `usable_for_D4 = primitive_support_ok AND required_metrics_evaluable AND D4_raw.notna()`。数据存在不是所有统计量均可估；零方差导致的相关性不可估，应由各component自己的统计合同处理，而不是从D2借Veto。

D1/D2只在评分完成后加入解释表。历史 `D4_after_D1`、`D4_forDQR_provisional` 等诊断字段应与正式数值源分开，不得因字段名相似再次进入正式聚合。D4_raw仍为关系维度数值来源。

### 4.3 映射的统计边界

自己的开发期分布定标不属于跨维度评分输入，但只建立了reference-relative score，不自动证明绝对“健康概率”。开发期中长期共同故障仍可被吸收到参考。

- 首次准入对照先保持P50/P75/P90/P97.5、component公式及权重不变，避免同时改变准入和估计器。
- block-balanced quantiles、winsorized、leave-high-risk-block-out适合作敏感性，不宜同时变成多个生产旋钮。
- 不得先用本维度低分删掉所有高风险窗口，再宣称参考“正常”；这是尾部截断，会改变估计目标。
- 不把单个pair完全自我归一化；保留公共analyte/regime映射及pooling范围、独立块数、尾分位点区间等metadata。
- 当前配置确有最少6个7 d时间块的准入，且声明它是暂定可识别性下限，并非精度保证。保留并报告敏感性，不把该数值包装成普适统计定理。
- 支持不足时保持limited/fallback/NA的明确语义；跨analyte的global normalized fallback不能无验证升级为充分证据。

重跑项目：公共基准、映射、主评分、事件、受控注入、共同变化负对照、D1-D4/D4-D5依赖审查、图件及报告。数值/证据变化均需向DQR传播。

## 5. 共享context迁移：同意归属迁移，不同意强制同一个模型

论文放Section 2.2“Shared data foundation and process context”合理。工程建议新建平级共享模块，名称在实施时确定，而不是继续把中性基础归属于D1输出。

分两步：

1. 归属重构：原始数据、时间轴、support schema和冻结context资产进入共享基础；保持模型与历史标签不变，并做逐行/哈希一致性验证。
2. 方法修订：如原context在全历史数据fit或起点有bfill，另建开发期拟合、因果推断的版本。缺失历史信息保留unknown，不能借未来标签回填；重新计算受影响的参考与结果。

共享接口至少携带timestamp、window_start/end、available_at、model_id、fit_end、feature_hash、regime_id、confidence、OOD及support metadata。D4的context fit边界不能晚于其开发锁；不能因D3校准结束更晚而无声延长D4训练期。

D5当前有独立的global-robust特征、reference_fraction、后验、OOD与hysteresis；R1-R4不能仅因名字相同就与D1/D4工况合并。短期可共享基础服务、保留不同model_id；真正统一模型属于额外研究，应重拟合模板、重做支持/OOD与验证。还需保留目标/整对排除context的敏感性，防止目标故障被吸收为“新工况”。

## 6. 实施顺序与验收

1. 保全当前历史release与108天T0 release，冻结源数据和代码/配置哈希；明确方法修订起点。
2. 抽离shared raw-support/context合同，先做不变性测试；评分文件不存在或被扰动时，D3/D4核心仍能产生完全相同的原始证据。
3. D3双参考并行：仅改变准入，锁定估计器；完成历史校准/验证、alpha区间及警告/门控影响审查。
4. D4双参考并行：先去除评分及派生Veto依赖，保持其余公式；再单列稳健估计敏感性。
5. 刷新D5的依赖审查与DQR，不把D3数值混入补偿性质量均值，不把D4下沉为单节点维度。原始数值、证据强度、门控分别输出。
6. 更新论文方法、Fig.1依赖箭头、Fig.3/4证据结果、Fig.5整合结果及source data；执行input/code/config/artifact hash闭环CI。

测试至少覆盖：变动/删除D1/D2评分文件时核心结果不变；中性支持不排除硬停滞；缺失/错位/未满窗口正确处理；24 h窗口与信息可用时间一致；无未来数据影响已发出的结果；相同模型归属迁移前后数值一致；D5模型标签不被误替换；旧freeze和新revision输出不能互相覆盖。

### 新期验证必须保留的边界

108天数据及其D5 OOD/覆盖结果已经查看。现在根据既有研究认识修改参考准入后，可以在**只用旧开发期拟合**的前提下重算这段新期，但应称“修订方法的时间外再评价/敏感性”，不能重新声称该修订在从未查看过的108天上完成首次盲测。保留原T0作为原先冻结方法的外推检验；新方法需要下一段未查看数据或另一厂数据才能获得新的独立确认。

所有标准化、聚类、阈值估计都需只在指定训练期fit，然后对后续数据transform/predict；这包括无监督预处理，不仅是有监督模型。方法依据参见[scikit-learn官方数据泄漏说明](https://scikit-learn.org/1.5/common_pitfalls.html#data-leakage)。

## 7. 论文措辞建议

实施前可以准确写：运行时D3评分采用冻结包络；其参考构建使用跨维度质量筛选；D4使用D1筛选和D2门控，并开展依赖性敏感性分析。不要写成已完成的完全独立框架。

以下是**实施与验证通过之后**可用的方法表述，不代表当前代码已满足：

> All dimensions shared the raw observation time base and a versioned process-context foundation. Dimension-specific reference sets were qualified using prespecified observation-level eligibility criteria rather than scores or score-derived vetoes from other dimensions. Each dimension generated its own numerical evidence before hierarchical integration. This computational separation did not imply statistical independence between dimensions. Cross-dimension score-screened references were retained only for sensitivity analysis.

D3部分另明确operational envelope非物理真值；D4部分明确reference-relative relational consistency；有共同过程context不等于外生context。论文价值在于透明、可复现的证据边界与可用性分层，而不是承诺所有维度不相关或所有新期均可评分。

## 8. 工作区与GitHub最终版本核查

核查方式：git worktree list、各工作区status、实时git ls-remote以及gh pr view 26。

| 本地工作区 | 分支/HEAD | 截至本次核查的用途 |
|---|---|---|
| `D:\004_git\beian_tree-main` | main / 6799c3a916bbc6840aa2623f915b44d05e5192d6 | 与GitHub main完全一致的已合并正式基线，包含PR25 |
| `D:\004_git\beian-val-260905` | codex/temporal-validation-plan-260905 / 871a1b8cfb6387075fdef302a30d95f6f059395f | 最新108天新期端到端结果与因果适配；PR26仍为OPEN/DRAFT，尚未进入main |
| `D:\004_git\beian_tree` | codex/d4-methodology-core-v15 / 96b065d272e2a8340f6b18db208116f52df55305 | 旧D4 PR20工作区，不能作为最新整项目入口 |
| `D:\004_git\beian_tree-d5-l1-audit-260820` | codex/d5-l1-support-audit-260820 / 8f96dd6bbbe0b1f9bfbd5aa8248d67e23af24e3a | 已合并PR24的旧审计工作区 |
| `D:\004_git\beian_tree-dqr-v23-260821` | codex/dqr-v23-evidence-contract-260821 / 378731281fc6f60f42c5c31f5c7efc191788157d | 已合并PR25的旧整合工作区 |

PR26实时状态：MERGEABLE，两个现有checks为SUCCESS，分别为D5 publication bundle与Temporal holdout checkpoint (not performance approval)。这不等于已完成全部科学审阅，也不等于本轮获得了合并授权。

重要：main下尚有未跟踪的论文组合图、September数据提取、历史资料等；validation工作区下还有未跟踪的中英文框架图源文件。仅有文件在本地不等于已提交GitHub。此次并未对全部未跟踪数据逐文件判定新旧，不能宣称任一目录已包含所有最新材料。

**推荐唯一日常项目入口：**

`D:\004_git\beian_tree-main\Project 1 Data Quality Assessment`

但当前它是“已合并正式基线”，还不是“所有最新工作均已归并的最终全集”。之后在该根目录所属仓库从main建立`codex/...`变更分支，审查后再合并；不在旧`beian_tree`继续改主项目，也不直接往main写半成品。

统一前先盘点并保全两个工作区中的未跟踪成果；独立审查PR26后通过Git合并纳入main。不要复制覆盖整个目录，不要把未经判断的历史文件批量git add，也不要删除这些工作区来代替合并。

- [GitHub已合并项目](https://github.com/muzi-1998/beian_tree/tree/main/Project%201%20Data%20Quality%20Assessment)
- [108天新期结果PR26](https://github.com/muzi-1998/beian_tree/pull/26)

## 9. 本轮交付及未执行项

已完成：实际依赖链审查、3个冻结系数重放、中性准入初筛对照、实时本地/远程版本核查、最终修改建议。

同目录文件：

- `EXPERT_REVIEW_ZH.md`：本报告。
- `audit_d3_candidate.py`：只读测算，可在项目根目录执行 `python cross_project_qa/independent_reference_review_20260917/audit_d3_candidate.py`。
- `D3_candidate_reference_contrast.csv`：三种准入路线的系数、支持量和变化。
- `D3_candidate_reference_audit.json`：输入/脚本SHA-256、checkout commit、检查结果及限制。

未执行：生产准入替换、系数/映射晋级、D3/D4/D5/DQR正式重跑、已有图件重绘、PR26合并、目录清理及GitHub推送。本轮用户请求是综合审查和最终建议，不把方案审查等同于正式科学版本升级。
