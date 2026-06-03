# §1.1 时间底座与非平稳特征解析（差异化双轨分解 + 快慢轨白化）

博士论文第一章 1.1 节实施代码。将北岸厂多源异构数据（分钟级 DO/ORP/QR/QIR +
小时级进出水水质）统一转化为**去趋势去周期、并经 ARMA/GARCH 白化的纯净残差 / 创新序列**，
作为 1.2 节数据质量评估的合法输入。实现严格对应 `plan and report/` 下的实施方案 v3.0。

## 快速开始

```bash
pip install xlrd statsmodels arch pyarrow openpyxl   # 其余依赖见下
python run_pipeline.py            # W1→W3 全链路（数小时级数据 + 分钟级 256 天，约数分钟）
python validate.py                # W4 有效性验证 + 案例库
# 快速冒烟：python run_pipeline.py --quick
```

依赖：numpy, pandas, scipy, statsmodels, arch, matplotlib, pyarrow, openpyxl,
pyyaml, xlrd。

## 数据

`Raw data/` 下五个原始文件：
| 文件 | 采样 | 通道 |
|---|---|---|
| `beian_min_1_DO_*.xlsx` | 1 min | DO_1_1..1_4, DO_2_1..2_4 (8) |
| `beian_min_2_ORP*.xlsx` | 1 min | ORP_1_1..1_3, ORP_2_1..2_3 (6) |
| `beian_min_3_QR+QIR*.xlsx` | 1 min | QR_1/2, QIR_1/2 (4 驱动) |
| `beian_h_*_influent_all.xls` | 1 h | pH,T,SS,NH4,TP,TN,COD,Q |
| `beian_h_*_effluent.xls` | 1 h | COD,TP,NH4,TN,pH,T,污泥浓度 |

## 目录结构

```
configs/         paths.yaml / deperiodise.yaml / whiten.yaml  （配置驱动）
src/
  semantics.py             北岸厂工艺语义 + 通道分组（单一真源）
  config/loader.py         UTF-8 安全 YAML 读取 + config hash
  data/
    loader.py              五源原生加载（min + 小时 .xls）
    preprocess.py          TimeAligner / DataImputer：1min 主时钟、多速率 hold、标记位
    consistency.py         值域/速率/守恒/对称 + DO_4 地板vs冻结甄别
  baseline/
    harmonic_order.py      AIC/BIC + 嵌套 F 检验自适应选阶
    deperiodise.py         分区/分变量差异化加性分解（因果拟合窗 + 出水截尾）
    local_baseline.py      事件后局部基线重建（自 D1 复用）
  whiten/
    offline_identify.py    慢轨：ARMA/GARCH 定阶 + 拟合
    online_whitener.py     快轨：冻结系数 O(p+q) 差分 + lfilter 批处理
    diagnostics.py         Ljung-Box / ADF / KPSS / ARCH-LM + 窗口化通过率/ACF
    acceptance_gate.py     换入前平稳可逆/LB/方差校验
    warmup.py              预热热态内部状态交接
    param_store.py         版本化参数 + 原子热替换
  outputs/
    figures.py / tables.py 交付图件与表格
run_pipeline.py            W1→W3 主流程
validate.py                W4 有效性验证 + 案例库
outputs/{parquet,tables,figures,reports,plot_data}/   交付物
run_manifest/              每次运行留痕
```

## 交付物（plan §6.3）

- `outputs/parquet/time_base_1min.parquet` — 统一 1min 等距时间基座 + 全部标识位
- `outputs/parquet/{residual,innovation}_*.parquet` — 残差 / 创新序列数据集
- `outputs/tables/data_inventory.csv` — 多源数据清单（含工艺语义）
- `outputs/tables/consistency_*.csv` — 一致性诊断（QR 负流量、DO_4 工艺低 DO 等）
- `outputs/tables/harmonic_order_table.csv` — 分区/分变量谐波阶数表
- `outputs/tables/arma_garch_order_table.csv` — ARMA/GARCH 阶数表
- `outputs/tables/whitening_before_after.csv` — 白化前后诊断对比
- `outputs/figures/fig_W1_availability_heatmap.png` — 数据可用性热图
- `outputs/figures/fig_W2_decomp_*.png` — 趋势—周期—残差—创新四级分解
- `outputs/figures/fig_W2_spectrum_compare.png` — 三类数据周期谱对比
- `outputs/figures/fig_W3_acf_*.png` — 白化前后 ACF 对比
- `outputs/reports/validation_report.md` — W4 有效性验证报告

## 方法学要点

1. **标记而非清洗**：所有异常以标识位保留（值域违反 / IQR 离群 / 截尾 / hold / 过渡区），
   不在底座阶段抹去——异常本身是 1.2 节评分对象。
2. **差异化双轨分解**：分钟级过程状态用分区自适应高阶谐波 + STL；进水低阶
   (24h+168h)；出水以趋势/季节为主、近检测限左截尾稳健分解。
3. **多速率原生分解后对齐**：小时级在原生 1h 上分解，再阶梯前向保持对齐到 1min（hold_flag），
   不在 1min 网格上分解小时级数据（避免捏造虚假高频）。
4. **因果/滚动分解**：谐波系数在前 30 天参照期因果估计，趋势用后向滚动均值，无未来信息泄漏。
5. **ARMA/GARCH 白化**：去周期残差白化得近似 i.i.d. 创新序列；分钟级低阶 (p,q≤3)，
   出水长记忆放宽 AR≤6；条件异方差显著时叠加 GARCH(1,1)。
6. **快慢轨解耦**：快轨冻结系数 O(p+q) 滤波（不做在线自适应，避免抹平 drift 故障）；
   慢轨离线定阶 + 接受门 + 预热 + 原子热替换。
7. **大 n 诊断**：n=36 万时单次 LB 必拒，故采用窗口化 LB 通过率 + ACF 衰减作为白化充分性度量。
```
