# 108天T0冻结推断执行报告

日期：2026-09-07。Run：`HOLDOUT-T0-20260907`。

## 结论

**原始分钟数据至D1–D5、DQR的T0自然评分已完成。** 不是把历史分数延长到新期，也不是将全年数据重新拟合。历史正式成果未覆盖；新期保留全部名义时钟和缺证据状态。

本结果可以用于论文的“同厂后续时段、固定规则下的覆盖和自然报警负担”部分。**不能据此宣称新期故障Recall/FAR、自动定位或部署效能已经验证。** 完整研究计划中的受控挑战、区块统计敏感性及独立真值仍待完成。

## 开盲与输入

- 2026-09-07 02:43:24 UTC（北京时间10:43:24）在历史证明通过后创建T0开盲锁；其SHA-256为 `dce9a28f3533364c94f10020627e4794bbe29bdf2196080d071dfc903cf6b6cc`。
- 新输入区间为 `[2026-04-14 00:00, 2026-07-31 00:00)`，108天、155,520分钟、14支DO/ORP，另4列QR/QIR协变量。
- 用户已确认位置、标签、量程及探头未变；源数据仅对齐、未填补空值。这是研究者确认，不替代原始SCADA与运维日志。
- 历史原网格及末日缺值保留；不使用新文件回填4月13日的旧末日尾部。原始数据不上传。
- `T0_opening_lock.json` 固定代码、配置、模板、完整ECDF、支持表和输入内容。每次新期运行前重新核验。锁定后未修改科学推断代码或门槛。

## 本轮修改

| 环节 | 实际完成 | 科学边界 |
|---|---|---|
| 1.1至D1/D4 | 原始分钟经有界3分钟处理、固定阶数分解与固定白化进入残差 | 谐波系数继承仅过去30天、每14天更新的政策，不称所有参数永久不变 |
| D1 | 固定PLS/工况模型；实际计算五类检测证据并续接恢复状态 | 历史恢复证据日志不改写；当前观测或完整证据缺失则正式接口NA |
| D2 | Strict/Sensitive完整连接；长缺口和P95改为当时可知信息 | 对齐前时间戳缺陷不可观测，不按零缺陷计满分；不插补Q_HA输入 |
| D3 | 冻结阈值与温度政策逐个2小时窗运行 | 运行Warn不是已确认仪表故障；最新已闭合窗才进入DQR |
| D4 | 新残差/common-support/冻结公共映射；因果变点候选；保留每行校准证据元数据 | D2只做准入，D1仅供冻结工况标签；数值源始终为D4_raw |
| D5 | 恢复完整冻结ECDF、56条支持记录、空间模板和hysteresis；完成真实新期推断 | 不重拟合、不累计新期支持、不将L1补成正式分数；动作接口待新期受控验证 |
| DQR | 按实际可获得时刻接合，原node/pair数学公式不变 | D3仅gate、D4仅pair、证据不乘分数；较新NA不得退回找旧好分数 |

D5原拟合文件重建不具备旧pickle逐字节同一性。旧算术下86,016个sensor-hour的分数、状态和支持完成数值重放；确定性逐行求和修正了BLAS批长度舍入经ECDF放大的前缀问题。该修正影响旧期1,124个D5_raw值，最大差0.002191；832个report值，最大差0.001537。支持与缺值集合不变。相关CSV保留，不把修正版冒称旧输出逐位一致。

## 新期结果

| 项目 | 数量/结果 | 分母或含义 |
|---|---:|---|
| D1可评价 | 36,163 | 36,288名义sensor-hours |
| D2可评价 | 36,288 | 缺失可作为可评分的不良连续性证据，不要求观测始终存在 |
| D4可评价 | 17,787 | 18,144名义pair-hours |
| D5 raw可计算 | 35,672 | 仅表示可形成诊断数值 |
| D5正式report可评价 | 924 | 占名义sensor-hours约2.55% |
| DQR node Full / Basic / Limited | 910 / 35,253 / 125 | 共36,288 |
| DQR pair Full / Basic / Limited | 455 / 17,311 / 378 | 共18,144 |
| D3 Pass / Warn / NotEvaluated | 15,299 / 2,775 / 70 | 18,144个2小时sensor-window，不是小时数 |
| Node core pooled mean | 4.630828 | sensor-hour池化均值 |
| Node core plant-hour mean | 4.630375 | 先按plant-hour聚合，再取时间均值 |
| Pair core pooled / plant-hour mean | 4.140786 / 4.140786 | 本次两种统计口径数值相同，定义仍不同 |

### D5覆盖边界

采用互斥优先级：当前观测缺失 → 必要context缺失 → OOD → L1 → report可用 → 其他不可评价。

| 原因 | sensor-hours |
|---|---:|
| OOD | 20,788 |
| L1 limited support | 14,434 |
| Report available | 924 |
| 当前观测缺失 | 128 |
| 其他不可评价 | 14 |

这些数目不能和非互斥的原始support/OOD字段直接相加。4月14日至6月30日无正式D5；7月每个通道有66小时正式report。所有通道相同的覆盖模式反映共享工况状态和固定支持门控，不代表14次独立的验证结果。

**Full只代表极小的完整证据子集，不能外推到108天全部sensor-hours。** 固定core12应作为纵向主结果；available在D5进入时会改变维度构成；Full只作附覆盖量的条件结果。不得凭扩大Full覆盖而重新调D5阈值或模板。

### 末端与时间合同

- 所有DQR名义小时均输出，但最后一个小时的D1/D4不发布：3分钟预处理延迟所需的末端未来信息不存在。
- D3最后标签为7月31日00:00，代表7月30日22:00–24:00的已闭合窗口，不是多生成一天数据。
- DQR决策时刻为小时标签+1小时3分钟。D5使用当时已结束的10分钟快照；D3为最新已结束的2小时安全证据，保留来源标签和时间，不声称全部证据有相同回看窗。
- 首日包含历史末尾空值及状态续接影响，不能把首日变化单独解释为真实工艺或仪表恶化。

## 检查与复现

开盲前46项合同测试通过。D1实际检测器续接前缀、D2 Strict/Sensitive前缀、D5完整冻结前缀通过；D4真实残差风险与历史一致，因果CP与已审计候选一致；DQR实际接合无未来来源、core/Full/pair公式通过。

新期逐行核验通过：36,288/18,144完整名义网格、唯一键、1–5范围、未来证据排除、L1和当前缺失不补分、末端NA及公式闭合。源Excel六表5,300个单元格与CSV/JSON独立核对。

图件源代码预检14项通过、无警告；SVG/PDF保留可编辑文字，PNG为300dpi、TIFF为600dpi。另有35项原D5测试通过，确认冻结推断的可选接口未破坏原流程。

跨平台复现注意：开盲锁包含4个原D5 JSON schema/CSV模板的Windows换行字节。公开CI在checkout前保留该换行方式，以匹配原始锁，不在看到新期结果后重写锁。科学代码按规范化内容SHA核验，公开派生成果按文件字节SHA核验；提交编号本身不替代内容指纹。

从项目根执行（私有输入仅用于重新计算，不参与公开CI）：

```powershell
python validation/temporal_holdout_2026/run_frozen_transform.py --holdout
python validation/temporal_holdout_2026/run_dimension_inference.py D1 --holdout
python validation/temporal_holdout_2026/run_dimension_inference.py D2 --holdout
python validation/temporal_holdout_2026/run_dimension_inference.py D3 --holdout
python validation/temporal_holdout_2026/run_dimension_inference.py D4 --holdout
python validation/temporal_holdout_2026/run_dimension_inference.py D5 --holdout
python validation/temporal_holdout_2026/run_dimension_inference.py DQR --holdout
python validation/temporal_holdout_2026/publish_t0_results.py
python validation/temporal_holdout_2026/verify_t0_results.py
```

不能再次运行开盲锁定来覆盖已有锁；内容变化会拒绝评分，须建立明确修订。历史日志重放属于可恢复的批处理实现，不声称已完成低内存生产在线服务。

## 文件位置

| 位置 | 内容 |
|---|---|
| `outputs/T0_results/D1_scores.parquet`至`D5_scores.parquet` | 真实新期维度分数、诊断和信息时钟 |
| `outputs/T0_results/DQR_node.parquet`、`DQR_pair.parquet`、`DQR_time_join.parquet` | 聚合值、维度掩码、释放状态、时间来源 |
| `outputs/T0_results/D5_report_interface.parquet`、`D5_gate_interface.parquet` | 正式可评价分数与待验证动作明确分轨 |
| `outputs/T0_results/*evidence*.parquet`、`D4_risks.parquet`、`D5_regime_state.parquet` | 检测证据与逐时/快照状态 |
| `outputs/T0_results/T0_descriptive_low_tail_episodes.parquet` | 原时钟连续低分段及左右删失；≥1小时描述性片段，不冒充各维度原生故障事件 |
| `outputs/T0_results/D1_recovery_transitions_journal.json` | 含历史启动上下文的恢复状态转换日志 |
| `outputs/source_data/T0/` | 图件CSV/JSON和六表Excel |
| `outputs/figures/Holdout_H3*`、`Holdout_H4*` | 两幅新期结果图，SVG/PDF/PNG/600dpi TIFF |
| `outputs/assets/`、`outputs/audit/` | 冻结资产、历史证明、确定性敏感性 |
| `outputs/T0_opening_lock.json`、`outputs/stage_B_manifest.json` | 开盲科学内容锁与最新整个成果包指纹；后者沿用历史文件名 |

H1/H2及阶段B报告保留为开盲前历史审计记录，其“未开启”描述有明确历史时间，不作为当前运行状态。

## 未执行与下一步

1. 新期受控故障矩阵、机制Recall/FAR、D1–D4/D5增量效度与区块CI仍未完成；自然低分率不能替代这些指标。
2. 全部预设7日/2日/14日不确定性、selection/composition分解与pair权重敏感性待开展；当前图为描述性结果，不展示虚构CI。
3. T1成熟化不是本次T0的一部分。如今已看到T0新期表现，未来T1开发必须披露这个事实，不能再把同一整段资料无条件称为未见测试。
4. 未补运维/SCADA原始日志、独立故障真值和跨厂资料；D5动作接口保持待验证，不据自然评分自动启用定位Veto或部署。

专家判断：**已满足启动并完成108天自然评分的工程与时间合同要求，但尚未满足“整个108天验证研究全部通过”的科学结论要求。** 最有价值的现阶段结果是可复现地揭示固定模板的时间迁移适用域和完整证据稀缺性，保留失败边界，并据此约束综合评分的解释范围。
