D6 平行冗余时序一致性模块 — 交付说明（v1.2，全周期运行版）
================================================================

本目录为 Class C-minDQR 框架中 **D6 维度（平行冗余时序一致性，动态维度，权重 0.16）**
的完整工程实现、运行结果与分析图。代码严格按《D6_平行冗余时序一致性实施方案_最终修订版_v1_2》
与《D6_Python工程目录与模块输出物明细_v1_0》编写。

数据：现场分钟级真实数据 368,238 分钟（约 255 天，2025-08-01 至 2026-04-13），
7 对孪生传感器（DO 好氧/后缺氧 4 对、ORP 厌氧/前缺氧 3 对），24 h 主窗口、1 h 步进，
全周期主评分共 42,798 条窗口记录。


目录结构
--------
scripts/                 全部源代码（可直接运行）
  src/d6/                D6 子包
    config/              配置模型与加载校验（models.py / loader.py）
    pair_manager.py      孪生对主键管理（PairManager）
    upstream_adapter/    上游只读适配器（D1/D7/D2/regime；D6 绝不重算上游统计量）
    residual/            配对残差视图与窗口切片
    subscores/           四个子探测器：dist(W1/KS/CvM) / trend(Theil-Sen) / var(IQR 对数比) / cp(相邻 KS 变点)
    deadband/            物理死区 δ_phys 闸门（独立对象，支持消融）
    mapping/             风险→1..5 分位映射（基准分位标定）
    aggregation/         非补偿聚合（D6_base / D6_raw，λ=0.75）
    arbitration/         三层仲裁引擎（死区闸门→D1双侧熔断→D7同区共识）
    labeling/            四类状态标签 + fuse_active/deadband_active 双旗标
    benchmark/           7 对高质量基准窗口库 + 分位标定
    pipeline/            数据装载/去周期 + 两阶段流水线（compute_raw / score）
    validation/          六类注入(INJ-A..F) / 指标 / 消融 / 冗余相关
    outputs/             10 个 Excel 交付物写出器
    figures/             8 张 SCI 级图（Nature 风格）
  configs/d6/            10 个 YAML 配置（pairs/zoning/deadband/subscores/mapping/
                         arbitration/windows/aggregation/output/paths）
  run_stage_a.py         可断点续跑的全周期 Stage-A 驱动（逐对检查点）
  run_all.py             端到端主编排（装载→残差→上游→评分→10 表→验证→图→manifest）

results/                 10 个 Excel 交付物
figures/                 8 张图，每张含 .svg(矢量可编辑文字) 与 .png(300 dpi)


十个 Excel 交付物（results/）
------------------------------
必交 (6)：
  D6_main_scores.xlsx            主评分，42,798 行，含 D6_raw / D6_forDQR 双字段
  D6_event_windows.xlsx          465 个低分事件窗（含案例研究子表）
  D6_detector_outputs_raw.xlsx   四探测器原始风险量（dist/trend/var/cp 分表）
  D6_mapping_params.xlsx         分位映射参数、死区表、cp 规则表、聚合权重、版本
  D6_pair_benchmark_library.xlsx 基准窗口库与风险分位
  D6_benchmark_results.xlsx      验证结果（summary_vs_targets / injection_trials /
                                 ablation_comparison / correlation_results / roc_pr_curves）
推荐 (4)：
  D6_pair_profile_summary.xlsx   逐对画像（标签占比、主导证据、事件数）
  D6_multiscale_aggregates.xlsx  时/日/周多尺度聚合（含 DQR 闸门 q05 / 报告 q25）
  D6_arbitration_log.xlsx        仲裁转移日志、冲突、逐层统计、熔断分布
  D6_audit_log.xlsx              运行清单、配置快照、上游版本契约


八张分析图（figures/）与对应绘图源文件
----------------------------------------
核心 (src/d6/figures/fig_core.py)：
  Fig_M1_paired_residual_consistency  7 对配对残差双线叠加 + 低一致性区阴影  → fig_M1()
  Fig_M2_subscore_contribution        子分加权贡献分解（堆叠+分组条）        → fig_M2()
  Fig_M3_trend_slope_scatter          Theil-Sen 斜率 (β_s, β_s′) 散点+1:1 对角线 → fig_M3()
诊断 (src/d6/figures/fig_diag.py)：
  Fig_D1_dqr_heatmap                  7对×ISO周 D6_forDQR 热图（统一 1-5 色标）  → fig_D1()
  Fig_D2_status_barcode               状态标签 + 熔断/死区旗标条码              → fig_D2()
  Fig_D3_arbitration_scatter          D6_raw vs D6_forDQR 仲裁效果散点          → fig_D3()
验证 (src/d6/figures/fig_valid.py)：
  Fig_V1_roc_pr                       单侧故障 vs 同步过程切换的 ROC/PR        → fig_V1()
  Fig_V2_ablation                     三层仲裁消融（AUC / 全局FAR / 夜间FAR）   → fig_V2()

共同样式：src/d6/figures/figure_style.py
  强制 Nature 规则：sans-serif 字体栈(Arial优先)、svg.fonttype='none'(文字可编辑)、
  隐藏上/右轴线、无边框图例、小写加粗面板标号、Y 轴贴合数据、语义化配色、
  每图同时输出 SVG + 300 dpi PNG 并关闭画布。


关键验证结论（D6_benchmark_results.xlsx → summary_vs_targets，10/10 达标）
--------------------------------------------------------------------------
  INJ-A 单侧漂移：D6_raw AUC = 0.965（目标 >0.85）  ✓ 能检出单侧传感器故障
  INJ-B 单侧阶跃：AUC = 0.738  ✓
  INJ-C 单侧冻结：AUC = 0.648  ✓
  INJ-D 单侧尖峰：AUC = 0.768  ✓
  INJ-E 同步过程切换：AUC = 0.370（目标 <0.45）  ✓ 正确地“不报警”（真实工况切换）
  INJ-F 共模退化：D6_raw AUC = 0.423（不报警），但 fuse_active 触发率 0.968  ✓
                  共模由 D1 双侧熔断接管并置中，而非误判为一致性异常
  物理死区：夜间 FAR 由 44.5% 降至 4.8%，降幅 89%（目标 ≥50%）  ✓
  冗余独立性：corr(D6_raw, D1健康) = 0.27、corr(D6_forDQR, D7) = 0.02（目标 <0.65）  ✓
              证明 D6 携带 D1/D7 不具备的独立信息，作为冗余维度成立


复现方式
--------
  cd scripts
  python run_stage_a.py     # 全周期 Stage-A 探测器计算（逐对检查点，可断点续跑）
  python run_all.py         # 端到端：评分 → 10 个 Excel → 验证 → 8 张图 → manifest
  # 快速冒烟（45 天）：python run_all.py --smoke

依赖：numpy, pandas, scipy, scikit-learn, matplotlib, openpyxl, pyyaml
（变点检测使用 scipy + numpy 相邻-KS 实现，对应方案 V1 设计“相邻-KS 在线为主，PELT 离线标定”，
  无需 ruptures/statsmodels。）


设计要点说明
------------
1. 双字段分离：D6_raw（仲裁前）与 D6_forDQR（仲裁后）始终独立保存——这是冗余验证的前提
   （方案 §6），也是 Fig_D3 与冗余相关分析的依据。
2. 两阶段流水线：昂贵的探测器 Stage-A 仅算一次，四种消融在同一 Stage-A 输出上重复 Stage-B
   评分，符合“消融共享探测器输出”的要求。
3. 上游只读契约：D1/D7/D2/regime 经适配器以派生代理形式接入；D6 绝不重算上游统计量，
   上游算法升级只要字段语义不变即无需改动 D6（方案工程目录 §3.2）。
4. 物理死区 δ_phys（DO 0.20 mg/L、ORP 15 mV，按工况可调）作为独立闸门对象，
   抑制夜间低波动期的伪报警；其价值在 Fig_V2 与 ablation_comparison 中量化。

运行版本：D6 v1.2 ；运行 ID：D6-20260530-full
