# Python工程目录与状态：v3最终设计

2026-10-20 执行更新。M01 已实现来源/技术审计，M02 已实现开发集档案算术诊断，M03–M12 算法待实现；M02 主步长及科学准入仍待定。保留D2式“模块→产物→验证→图→报告”组织，实际执行状态以 reports/PROJECT_PROGRESS.md 与 run_manifest/module_states.json 为准。

## 1. 当前实际目录

```text
2.3 Copula Time-Series Synthesis/
  README.md
  PROJECT_STRUCTURE.md
  pyproject.toml                         # 设计检查零依赖；execution 登记现有运行环境
  run_p23_pipeline.py                    # --check-design；--stage M01/M02
  configs/
    study_design.json                   # 5/15/60、1min双门、TW/FW、切分/变量/标签
    model_candidates.json               # 简约S1、低阶强基线、条件EVT
    experiment_protocol.json            # 新增：E1–E3、匹配量、策略/回放、比例冻结
    module_contracts.json               # 12模块、精确产物ID/路径/依赖/准入
    environment_policy.md
  src/project2_synthesis/
    __init__.py
    cli.py                              # 设计检查、阶段入口、测试与失败记录
    runtime.py                          # SHA、不可变运行清单、一模块一报告/总进度
    contracts.py                        # 已实现：结构与设计禁止项检查
    intake/source_audit.py               # M01 原值/时钟/技术标记/来源
    intake/native_frequency.py           # 开发集档案常数段诊断，原生状态 UNKNOWN
    intake/label_admission.py            # 出口候选标签准入，当前 PENDING
    preparation/aggregation.py           # M02 名义档案共同支持 TW/FW/V/L
    preparation/splitting.py             # 日历切分与不跨缺口技术连续块
    preparation/scale_selection.py        # 5/15/60 诊断；不自动批准主步长
    regimes/README.md                   # M03 待实现
    temporal/README.md                  # M04 待实现
    margins/README.md                   # M05 待实现
    dependence/README.md                # M06 待实现
    synthesis/README.md                 # M07 待实现
    physics/README.md                   # M08 待实现
    validation/README.md                # M09 待实现；含E1–E3协调
    export/README.md                    # M10 待实现；最终导出
    figures/audit_figures.py             # M01/M02 实际技术诊断图；M11 论文整合待实现
    release/README.md                   # M12 待实现
  tests/test_design_contracts.py         # 原19项设计契约测试
  tests/test_intake_preparation.py       # 共同支持/缺口/UNKNOWN/端到端行为测试
  artifacts/                            # 最新成功技术产物；科学准入单独登记
  run_manifest/design_check.json         # 仅检查状态和四配置SHA
  run_manifest/environment_inventory.json
  run_manifest/module_states.json        # 当前实际状态和运行历史
  run_manifest/runs/<run_id>/            # 本地完整快照、日志、清单和历史报告
  reports/
    PROJECT_PROGRESS.md                  # 全项目状态与下一步
    M01_执行报告.md ... M12_执行报告.md    # 八项报告内容；未执行者 PENDING
    GITHUB_SYNC_PROPOSAL.md               # 阶段变更与拟提交清单，用户确认后才 Git 操作
  plan and report/
    01_2.3_具体研究执行方案.md             # 历史方案
    02_模块输出物与验收契约.md             # 当前精确输出/字段
    03_第二章方法学写作底稿_20261020.docx   # 写作素材，执行规则以04最终稿为准
    04_第二章大纲与2.3研究方案_v3_20261020.md
    05_方法学写作底稿_文本与公式源_20261020.md
    06_工况与SUMO运行策略接口_方案补丁_v3.1_20261020.md
    07_POT方法学增补_文本与公式源_20261020.md
```

上级 raw data 只读引用；knowledge 保存文献、审计与历史版本。artifacts 内仅登记真实运行输出，不创建空模型或虚假通过报告。M01/M02 的 PARTIAL 允许保留实际技术结果，不批准后续正式模型；无原生信息时 fresh_count 为 null。当前 02_model_frame 只含开发集、角色为 archive_technical_only，不能被自动下游误当已准入模型数据。

## 2. 模块文件划分（M01/M02 有限实现，其余拟实现）

|模块|拟实现Python文件|一个模块应承担的完整职责|
|---|---|---|
|M01|intake/source_audit.py、native_frequency.py、label_admission.py|已实现来源/时钟/技术标记与元数据缺失审查；未知刷新身份、单位/标签待核项不被自动准入|
|M02|preparation/aggregation.py、scale_selection.py、splitting.py|已实现开发集共同技术支持的名义TW/FW/V/L、5/15/60诊断及技术块；主步长、原生信息和过程准入未完成|
|M03|regimes/events.py、regime_support.py|事件规则、确认层级、持续/状态支持、条件可得性|
|M04|temporal/decomposition.py、filters.py、inverse_state.py|可延展慢/谐波、ARMA/VAR、可逆状态与诊断；MSTL只作有定义延展的敏感性|
|M05|margins/distributions.py、tail_admission.py|主体CDF/PPF、零/删失、四层EVT；L2另建threshold_selection.py仅在触发后|
|M06|dependence/fit.py、temporal_vine_adapter.py|联合创新与直接低阶时序基线；实际库接口/版本先查官方文档|
|M07|synthesis/trajectories.py、scenario_sampling.py|联合采样、逆递推、自然/压力身份、warm-up与失败|
|M08|physics/constraints.py、boundary_contract.py、policy_contract.py|修正前后、单位/分馏/药剂/回流/WAS/DO语义及工程可行性|
|M09|validation/quality_coverage.py、input_matching.py、surrogates.py、sumo_adapter.py、response_pairs.py、augmentation.py|E1–E3完整比较；先匹配后仿真；适配器私有准备临时输入；不反向依赖最终导出|
|M10|export/datasets.py、sumo_delivery.py|基于已通过用途门的最终文件/映射/数据卡，不承担模型校准或实验选优|
|M11|figures/research_figures.py|读取冻结结果画F1–F8，输出源数据/图注/单位/估计目标；不重拟合选赢家|
|M12|release/manifest.py|仅登记实际文件及SHA，区分设计/实现/运行/验证状态|

不强制每个模块都暴露fit/transform/sample：验证、校验和导出具有不同职责。接口必须声明输入视图、支持、时间/单位、拟合域、返回的状态/失败及可逆元数据；内部细节由模块承担。只有确有两个后端（如Gaussian/t/Vine、不同真实SDK）时才引入对应适配器，避免空泛框架。

## 3. 依赖顺序与SUMO闭环

M01–M08提供已准入边界；M09内部按“冻结协议→输入匹配→必要的仿真输入序列化→同策略/回放→响应及现场验证→E3”组织。M09的SUMO适配器只消费M08契约及真实外部模型；运行子目录可保存实际输入文件/日志，并以pair_manifest登记SHA。M10在M09之后导出最终交付资料，因此没有M09↔M10循环。

SUMO安装、版本、模型文件、变量名和Python/CLI接口尚未核定，暂不写假调用。模型未准入时M09仍可运行未来实现的输入/事件评价，SUMO分支记录pending；真实标签未准入时E3同理。有限用途可分阶段交付，数据卡必须写清可用和不可用任务。

## 4. 当前可运行检查

在本目录执行：

```powershell
& 'D:\000_APP\020_APP_code\05_python3.10\python.exe' -X utf8 run_p23_pipeline.py --check-design
& 'D:\000_APP\020_APP_code\05_python3.10\python.exe' -X utf8 -m unittest discover -s tests -v
& 'D:\000_APP\020_APP_code\05_python3.10\python.exe' -X utf8 run_p23_pipeline.py --stage M01
& 'D:\000_APP\020_APP_code\05_python3.10\python.exe' -X utf8 run_p23_pipeline.py --stage M02
```

--check-design 不读取完整观测；M01 只读来源及机械质量，M02 只聚合 development，不拟合生成器或运行 SUMO。main_step/final_tolerance 待证据冻结，设计检查和数值恒等式通过不批准科学门。M03–M12 尚无执行入口，不能传入 --stage。每阶段输出清单保存实际 SHA，Git 同步独立等待用户明确确认。
