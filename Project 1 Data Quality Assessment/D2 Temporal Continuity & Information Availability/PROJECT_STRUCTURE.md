# D2 Temporal Continuity & Information Availability — 项目结构

> **最后更新：** 2026-08-04
> **当前版本：** V3 confirmatory release（raw-source timestamp QTI + hard-availability QFA + blocked validation）
> **维护规则：** 每次新增、移动或删除文件后同步更新本文件

---

## 目录

- [项目概述](#项目概述)
- [完整目录树](#完整目录树)
- [各层说明](#各层说明)
  - [根目录核心文件](#根目录核心文件)
  - [configs/ — YAML 配置层](#configs--yaml-配置层)
  - [src/ — P2 源码模块](#src--p2-源码模块)
  - [artifacts/ — 流水线产物](#artifacts--流水线产物)
  - [artifacts_pre_p0p1/ — 补丁前备份](#artifacts_pre_p0p1--补丁前备份)
  - [cache/ — 中间缓存](#cache--中间缓存)
  - [d2_fix_kit/ — 参考存档](#d2_fix_kit--参考存档)
- [运行指南](#运行指南)
- [测试状态](#测试状态)
- [版本变更记录](#版本变更记录)

---

## 项目概述

本模块计算 **D2（时间连续性与信息可用性）** 综合评分，覆盖北岸 LCH 污水厂 14 条传感器通道（DO×8 + ORP×6），时间范围 2025-08-01 至 2026-04-13。主输入承接 `1.1 Decomposition` 的统一时间轴、逐通道原始观测和预处理契约；D1 仅用于事件一致性关联，不参与 D2 映射、校准或评分。

| 指标 | 值 |
|------|----|
| 评分通道数 | 14（DO_1_1~4、DO_2_1~4、ORP_1_1~3、ORP_2_1~3）|
| 支持通道数 | 4（QR_1/2、QIR_1/2，不进 D2 主链路）|
| 完整性/断点主窗口 | 24 h 滚动，1 h 步长 |
| QFA 窗口 | 6 h 滚动，1 h 步长 |
| 输出行数 | 6121 小时/通道（完整 24 h 暖机后）|
| 配置驱动 | P2：所有阈值/权重/拓扑均来自 `configs/*.yaml` |

### V3 冻结发布

- 运行号：`D2V3_20260804_1939`
- 映射版本：`d2_v3_source_timestamp_qti_r1`
- QTI：原始时间戳排序前审计；missing/true irregular/duplicate/out-of-order 权重为 0.65/0.25/0.05/0.05，并按可观测证据条件归一化
- gap recovery：仅作为 QGS 诊断，不在 QTI 重复扣分
- 分段映射：五阈值连续下降，移除旧最高断点 2→1 硬突跳
- 校准号：`NorthBank_D2_v2_20260804`
- Development：2025-08-01 至 2025-12-31
- Internal validation：2026-01-01 至 2026-02-21
- Terminal test：2026-02-22 至 2026-04-13
- External-site validation：`deferred`；当前仅允许单厂回顾性主张
- 生产 QFA：缺失、长断点、至少 15 min 硬观测锁死；soft RLE、低 IQR、process floor、resolution limit 和 response-loss 均仅诊断

---

## 完整目录树

```
D2 Temporal Continuity & Information Availability/
│
├── PROJECT_STRUCTURE.md            ← 本文件（项目结构说明，随改动更新）
├── D2_FINAL_SCIENTIFIC_REPORT_2026-08.md ← V3 最终科学审查、结果与主张边界
│
├── run_d2_pipeline.py              ← V3 主流水线（评分、事件、原始时间戳审计与冻结状态）
├── run_d2_scientific_validation.py ← 权重/阈值/低尾/效应量/D1-D2 空模型验证
├── build_d2_release_manifest.py    ← 发布文件 SHA-256 清单生成器
├── make_d2_figures.py              ← SCI 级出图脚本（Fig01–10）
├── make_d1d2_joint_figures.py      ← B-1/B-2 联合出图脚本（nature-skills 规范，Fig11–12）
├── make_d2_scientific_figures.py   ← Nature 规范论文价值图（Fig13–16）
├── validate_d2_process_floor.py    ← 四类 process-floor 挑战验证与真实通道摘要
├── test_d2_p0p1_regression.py      ← P0/P1 回归测试
├── test_d2_contract_regression.py  ← 1.1→D2 契约与 scorer 一致性测试
├── test_d2_process_floor_regression.py ← 地板/锁死/小波动/响应恢复回归测试
├── generate_d1_event_windows.py    ← 可选：从 D1 pkl 提取 D1 事件索引
├── d2_calibration.yaml             ← D2 内部工程校准文件（不拟合 D1）
│
├── beian_min_*.xlsx                ← 兼容性回退输入（默认不使用、不入库）
│
├── configs/                        ← P2 YAML 配置层（替代全部硬编码常量）
│   ├── d2_mapping.yaml             ← 子分权重、分段断点、veto 规则、安全地板
│   ├── d2_sensors.yaml             ← 14 通道定义、POOL_TOPOLOGY、传感器精度
│   ├── d2_windows.yaml             ← 多尺度窗口（1h/6h/24h/7d）及时间网格
│   └── d2_study_design.yaml        ← 阻断时间区块、cluster bootstrap 与外部验证状态
│
├── src/                            ← P2 源码模块（供 run_d2_pipeline.py 导入）
│   ├── __init__.py
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── config_loader.py        ← D2Config dataclass + load_config() + _validate()
│   │   └── timestamp_quality.py    ← 原始时间戳哈希核验、排序前事件分类与小时定位
│   └── d2_availability/
│       ├── __init__.py
│       ├── process_floor.py        ← 标准与 process-floor QFA 证据分流
│       └── scorer.py               ← TemporalIntegrityScorer / GapSeverityScorer /
│                                      FreezeAvailabilityScorer / D2Aggregator
│
├── artifacts/                      ← 所有流水线产物（由 run_d2_pipeline.py 写入）
│   ├── d2_state.pkl                ← 本地完整状态（~313 MB，不入 Git）
│   ├── data/                       ← Excel 输出 + 报告文档
│   │   ├── D2_main_scores_hourly.xlsx          ← Q_TI/Q_GS/Q_FA/D2_total 小时级评分
│   │   ├── D2_preprocess_flags_hourly.xlsx     ← 小时级预处理标志聚合
│   │   │                                         独立含 floor/resolution/freeze/QFA 字段
│   │   ├── D2_gap_run_table.xlsx               ← 所有断点事件（起止时间/时长/类型）
│   │   ├── D2_freeze_availability_events.xlsx  ← 生产硬可用性事件（含 D1 描述性链接）
│   │   │                                         列：linked_D1_event_id / linked_D1_fault_type / relation_to_D1
│   │   ├── D2_interpolation_ledger.xlsx        ← 短断点（≤5 min）线性插补台账
│   │   ├── D2_mapping_params.xlsx              ← 分段映射参数（P1-B 含 P95_gap_min）
│   │   ├── D2_sensor_availability_profile.xlsx ← 传感器长期可用性摘要
│   │   ├── D2_timestamp_audit.xlsx             ← 原始时间戳排序前事件、小时计数与哈希审计
│   │   ├── D2_audit_log.xlsx                   ← 运行元数据 + 输入文件 SHA16（P1-E）
│   │   ├── D2_process_floor_validation.xlsx    ← 四类挑战与真实通道验证数据
│   │   ├── D2_process_floor_validation.json    ← 机器可读验证摘要
│   │   ├── D2_Fig05_source_data.xlsx           ← Fig05 四面板源数据
│   │   └── D2_d1_linkage_manifest.json         ← D1 联动依赖与评分不变性哈希
│   ├── validation/                 ← Parquet/Excel 科学验证结果与哈希 manifest
│   └── figures/                    ← Nature 图表（PNG/TIFF 600 DPI + 可编辑 SVG/PDF）
│       ├── D2_Fig01_overview_heatmap.{png,svg,pdf}  ← D2 总评分热力图（14 ch × 日均）
│       ├── D2_Fig02_subscore_violins.{png,svg,pdf}      ← Q_TI/Q_GS/Q_FA 小提琴图
│       ├── D2_Fig03_missing_rate_timeline.{png,svg,pdf} ← 缺失率时间序列
│       ├── D2_Fig04_gap_severity.{png,svg,pdf}          ← 断点严重度
│       ├── D2_Fig05_freeze_availability.{png,svg,pdf}   ← 地板诊断与生产 QFA 证据分离
│       ├── D2_Fig06_mapping_curves.{png,svg,pdf}    ← 配置驱动分段映射曲线（8 指标）
│       ├── D2_Fig07_availability_profile.{png,svg,pdf}  ← 传感器可用性画像
│       ├── D2_Fig08_d1_d2_relationship.{png,svg,pdf}    ← D1–D2 关系密度图 + 时序
│       ├── D2_Fig09_veto_analysis.{png,svg,pdf}         ← Veto 分析
│       ├── D2_Fig10_calibration_summary.{png,svg,pdf}   ← 校准与 ECDF 概要
│       ├── D2_Fig11_B1_event_cooccurrence.{png,svg,pdf} ← B-1 事件共现矩阵
│       ├── D2_Fig12_B2_d1d2_timeseries.{png,svg,pdf} ← B-2 D1–D2 时序对比
│       ├── D2_Fig13_process_floor_contract.*       ← 工艺地板与硬不可用机制分离
│       ├── D2_Fig14_aggregation_robustness.*       ← 权重、lambda 与映射稳健性
│       ├── D2_Fig15_low_tail_reporting.*           ← 阻断阶段低尾风险
│       ├── D2_Fig16_d1_d2_construct_separation.*   ← D1-D2 构念区分与空模型
│       └── D2_Fig17_timestamp_qti_audit.*          ← 原始时间戳审计、QTI 权重与损失归因
│
├── artifacts_pre_p0p1/             ← P0+P1 补丁应用前的状态备份（只读存档）
│   ├── d2_state.pkl                ← 补丁前完整状态（~228 MB）
│   └── d2_calibration_pre_p0p1.yaml ← 补丁前校准文件（veto 阈值全为 0，退化态）
│
├── cache/                          ← 输入+配置+代码哈希命名的中间缓存（不入 Git）
│
└── d2_fix_kit/                     ← 原始 Fix Kit（参考存档，不参与运行）
    ├── README.md                   ← Fix Kit 总说明
    ├── patches/                    ← P0+P1 补丁
    │   ├── apply_guide.md          ← 补丁应用指南（操作步骤）
    │   ├── d2_pipeline_patches.py  ← P0/P1 补丁代码片段
    │   └── test_d2_p0p1_regression.py ← P0+P1 回归测试（参考原版）
    ├── diff_report/                ← 差异报告工具
    │   ├── compute_diff_metrics.py ← 差异指标计算脚本
    │   └── D2_diff_report_template.md ← 报告模板（空白版）
    └── p2_refactor/                ← P2 重构参考原版
        ├── configs/                ← YAML 配置原版（已部署到项目 configs/）
        ├── src/                    ← 源码原版（已部署到项目 src/）
        └── tests/
            └── test_scorer_unit.py ← P2 单元测试（8 项）
```

---

## 各层说明

### 根目录核心文件

| 文件 | 说明 | 是否自动生成 |
|------|------|-------------|
| `run_d2_pipeline.py` | 主流水线，含步骤 1–14（加载→预处理→校准→评分→导出）| 否 |
| `make_d2_figures.py` | 调用 artifacts/d2_state.pkl 生成 Fig01–10（10 张 SCI 图，600 DPI）| 否 |
| `make_d1d2_joint_figures.py` | B-1/B-2 联合出图：事件共现矩阵 + D1–D2 时序对比（nature-skills 规范，SVG+PNG）| 否 |
| `validate_d2_process_floor.py` | 生成四类受控挑战及 DO_1_4/DO_2_4 真实结果验证工作簿和 JSON | 否 |
| `test_d2_p0p1_regression.py` | P0/P1 回归测试；D1 链接只作描述性一致性检查 | 否 |
| `test_d2_contract_regression.py` | 通道级缺失、整段长缺口和生产 scorer 一致性测试 | 否 |
| `test_d2_process_floor_regression.py` | 验证真实地板、数字锁死、小幅波动、离开地板后恢复 | 否 |
| `generate_d1_event_windows.py` | 可选生成 D1 事件索引；当前主链读取 `D1 Sensor health/outputs/data/` | 否 |
| `d2_calibration.yaml` | D2 内部工程校准；输入哈希变化时自动重建 | **是** |

### configs/ — YAML 配置层

P2 引入，替代 `run_d2_pipeline.py` 中全部硬编码常量。**跨厂部署只需替换此目录。**

| 文件 | 替代的硬编码段 |
|------|----------------|
| `d2_mapping.yaml` | `ENG_DEFAULTS`（断点/权重/veto 上限/安全地板）|
| `d2_sensors.yaml` | `SCORED_CHANNELS` / `SUPPORT_CHANNELS` / `POOL_TOPOLOGY` |
| `d2_windows.yaml` | 窗口长度/步长/时间网格 |

### src/ — P2 源码模块

```python
from src.utils.config_loader import load_config
cfg = load_config(Path("configs"), version="v1")   # 返回 D2Config（frozen dataclass）
```

`scorer.py` 中四个类全部消费 `D2Config`，无全局变量，支持独立单测。
`process_floor.py` 将低 IQR 诊断与生产 QFA 证据解耦；DO_1_4 和 DO_2_4
仅由缺失、长断点及原始观测硬 RLE≥15 min 触发 QFA 不可用。

### artifacts/ — 流水线产物

- **data/**：每次 `run_d2_pipeline.py` 完整运行后覆盖写入
- **figures/**：每次 `make_d2_figures.py` 运行后覆盖写入
- **d2_state.pkl**：保存全部通道的 `all_D2` / `subs_all` / `calib` 等中间结果，供测试脚本和出图脚本读取

### artifacts_pre_p0p1/ — 补丁前备份

**只读存档**，记录 P0+P1 应用前的退化状态（veto 阈值全为 0.0，误报率 >40%）。

### cache/ — 中间缓存

流水线各步骤写入带输入、配置和代码哈希的 PKL；依赖变化后旧缓存自动失效。
**安全删除**：删除后重跑流水线会自动重建。

### d2_fix_kit/ — 参考存档

**不参与任何运行**，仅作版本历史参考。
`patches/` 中的补丁内容已于 2026-05-25 全部应用到 `run_d2_pipeline.py`。
`p2_refactor/` 中的 configs/src 已于同日部署到项目根目录 `configs/` 和 `src/`。

---

## 运行指南

### 首次初始化（一次性）
```bash
# Step 0：从 D1 pkl 生成 D1_event_windows.xlsx（激活 P1-C D1 链接）
python generate_d1_event_windows.py
# 输出：../D1 Sensor health/outputs/data/D1_event_windows.xlsx（当前 72 条 D1 事件）
```

### 完整流水线
```bash
# 主评分、事件、审计与冻结状态
python run_d2_pipeline.py

# process-floor 机制挑战与真实通道摘要
python validate_d2_process_floor.py

# 聚合、阈值、低尾、分析物效应及 D1-D2 空模型
python run_d2_scientific_validation.py
```

### 生成图表
```bash
# Fig01–10（PNG + 可编辑 SVG/PDF）
python make_d2_figures.py
# 输出：artifacts/figures/D2_Fig01~10.{png,svg,pdf}

# Fig11–12（B-1 事件共现矩阵 + B-2 时序对比，需先完成 A-1 和完整流水线）
python make_d1d2_joint_figures.py
# 输出：artifacts/figures/D2_Fig11~12.{png,svg,pdf}

# Fig13–16（论文价值图；同时输出 PNG/SVG/PDF/TIFF）
python make_d2_scientific_figures.py

# 冻结发布 SHA-256 清单
python build_d2_release_manifest.py
```

### 回归测试
```bash
# D2 回归 + 1.1 契约 + process-floor 测试（24/24 通过）
python -m pytest test_d2_contract_regression.py test_d2_p0p1_regression.py test_d2_process_floor_regression.py -q --import-mode=importlib

# P2 单元测试（8/8 通过）
pytest d2_fix_kit/p2_refactor/tests/test_scorer_unit.py -v

# 模块化 scorer 测试（8/8 通过）
pytest d2_fix_kit/p2_refactor/tests/test_scorer_unit.py -v
```

### 清空缓存重跑
```bash
# Windows PowerShell
Remove-Item cache\*.pkl -Force
python run_d2_pipeline.py
```

---

## 测试状态

| 测试文件 | 测试数 | 通过 | 已知失败 | 说明 |
|----------|--------|------|----------|------|
| 三项生产/契约/process-floor 回归 | 24 | 24 | 0 | 含 6 h QFA、阻断时间设计、hard/soft 证据分离、peer 诊断资格与地板挑战 |
| `d2_fix_kit/p2_refactor/tests/test_scorer_unit.py` | 8 | 8 | 0 | P2 Scorer 单元测试全部通过 |
| **生产发布核验** | **24** | **24** | **0** | 发布命令显式限定生产测试，避免历史 `d2_fix_kit` 同名测试收集冲突 |

---

## 版本变更记录

| 日期 | 版本 | 变更内容 |
|------|------|----------|
| 2026-08-04 | V3 source-timestamp QTI | 从 1.1 原始 Excel 排序前审计 duplicate/out-of-order/true-irregular；gap recovery 与 QTI 解耦；QTI 改为 0.65/0.25/0.05/0.05 条件归一化；四阈值映射升级为五阈值连续映射；新增 Fig17、阈值退化参考、28 项顶层回归测试 |
| 2026-08-04 | V2 confirmatory | 冻结 development/internal/terminal 时间区块；QFA 仅采用硬可用性证据；response-loss 降为诊断；完成 9 组权重/lambda、映射、低尾、ORP-DO、D1-D2 循环移位验证；新增 Fig13–16、最终科学报告与发布 manifest；外部厂验证明确暂缓 |
| 2026-07-22 | process-floor QFA R1 | DO_1_4/DO_2_4 启用后缺氧地板专用路线；低 IQR 仅诊断；拆分 floor/resolution/freeze/QFA；QFA 修正为 6 h；后缺氧路线禁用 response-loss，标准路线仅允许平行池同位置 peer；四类挑战 4/4 通过；完整重跑 D2、12 张图与 D1 联动清单 |
| 2026-07-10 | V1.1 contract | D2 主输入切换为 1.1 时间基座契约；逐通道缺失；整段长缺口不插值；24 h 完整暖机；D1 从校准中移除，仅作事件一致性；缓存绑定输入/配置/代码哈希；12 张图统一 PNG/SVG/PDF |
| 2026-05-25 | V1 | 初始流水线完成；`run_d2_pipeline.py`（1132 行）、`make_d2_figures.py`（750 行）；10 张 SCI 图；9 张 Excel 输出 |
| 2026-05-25 | P0 | 修复 veto 阈值退化 bug（bench P99=0 时全窗口误报 veto）；加入安全地板机制 `_apply_floor()`；生成 `d2_calibration.yaml` 结构化 veto_thresholds |
| 2026-05-25 | P1 | P1-A：Q_GS 增加 P95_gap 项（权重 0.30）；P1-B：映射参数表补 P95_gap_min 行；P1-C：冻结事件表增 D1 事件链接列；P1-D/E：新增 `D2_audit_log.xlsx` 运行元数据 |
| 2026-05-25 | P2 | 外置配置层：新建 `configs/`（3 个 YAML）和 `src/`（config_loader + scorer）；`run_d2_pipeline.py` 全部硬编码段替换为 YAML 驱动；P2 单元测试 8/8 通过 |
| 2026-05-25 | 整理 | 删除根目录重复文档（README/guide/template/zip）；`D2_diff_report.*` 移入 `artifacts/data/`；`d2_calibration_pre_p0p1.yaml` 移入 `artifacts_pre_p0p1/`；清除所有 `__pycache__` |
| 2026-05-26 | A-1 | 新增 `generate_d1_event_windows.py`；生成 `D1_event_windows.xlsx`（321 条 D1 事件，9 列含 fault_type）至 D1 artifacts/data/；P1-C 链接逻辑修订（链接任意 D1 异常事件而非仅 Q_freeze）；新增 `linked_D1_fault_type` 列；D2 冻结事件 D1 链接率达 20.3%（3076/15183）|
| 2026-05-26 | A-2 | `test_p0_veto_rate_reasonable` 修订为三项精确断言（L_max_p99<500/missing_p99<1000/健康通道占比）；新增 `test_p1c_d1_linkage_rate_meaningful`；测试套件升至 **17/17 全通过** |
| 2026-05-26 | B-1 | 新增 `make_d1d2_joint_figures.py` B-1 模块：3 面板事件共现矩阵（堆叠条图 + 故障类型热力图 + 时长箱线图）；输出 D2_Fig11_B1_event_cooccurrence.{png,svg}（nature-skills 规范，figsize=14×7）|
| 2026-05-26 | B-2 | 同文件 B-2 模块：6 通道（DO_1_1/DO_1_4/DO_2_4/ORP_1_1/ORP_2_1/ORP_2_2）D1–D2 时序对比，3×2 面板网格，等级带背景/D1 事件着色/D2 veto 着色/7d 滚动均线；输出 D2_Fig12_B2_d1d2_timeseries.{png,svg}（figsize=14×10）|
| 2026-05-26 | 出图 V2 | `make_d2_figures.py` 全面升级至 nature-skills 规范：① 强制三行 rcParams（font.sans-serif / svg.fonttype='none'）；② 用 PAL 替换 WONG 调色板；③ 新增 `apply_publication_style()` / `add_panel_label()` / `luminance()`；④ `save_fig()` 改为 PNG 300 DPI + SVG 双导出；⑤ 所有多面板图加面板字母标签（A/B/C…）；⑥ tick 方向 in / 轴线宽 1.0（精细图）；全部 10 张图（Fig01–10）已重新生成，累计输出 **24 对 PNG+SVG** |
