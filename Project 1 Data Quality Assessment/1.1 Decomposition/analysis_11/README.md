# §1.1 结果分析 — analysis_11/

三条结果分析工作流,全部 **manifest 驱动**(分流/阈值/统计单位都读 `scoring_mode`/`group`/`zone`)、**严格因果**、**Okabe-Ito 配色**,且每张图的绘图数据落地 `outputs/plot_data/`。

运行:`cd analysis_11 && python run_all.py`(或单独 `python work1_variance.py` 等)。
Python 解释器需含 pandas/numpy/scipy/statsmodels/matplotlib/pyarrow/pyyaml。

---

## 工作一 · 方差贡献率(`work1_variance.py`)
**支撑"为什么要差异化分解"。**

- 方法:**逐步移除方差衰减**(加性分量不正交,裸比例不闭合)。
  `r0=Var(X)`,`r1=Var(X−m)`,`r2=Var(e)` → trend% `=(r0−r1)/r0`、seasonal% `=(r1−r2)/r0`、residual% `=r2/r0`,**恒闭合到 100%**。
- 因果分量:`m = causal_trend(X, 3×最长周期)`(回看均值,过≥3 个完整周期把季节抹平,只留慢漂移)+ 因果同相位 STL 季节,均来自 §1.1 的 `_causal_trend`/`_causal_stl_seasonal`,无未来样本。
- 整段对照(隔离泄漏代价):仅翻转趋势口径(回看→居中),季节固定 → `Δresidual% = 因果−整段`。
- 对硬通道(§1.1 谐波前推过拟合、残差≥信号)以 `‡` 标注并在表中给 `decomp_overfit`/`resid_final_pct`。

**产出**:`fig_1x_variance_partition_profile.png`(堆叠条,按工艺位置排序,蓝/橙/灰=trend/seasonal/residual)· 表 `A1_variance_partition.csv` · 数据 `outputs/plot_data/fig_1x_variance_partition_profile.csv`。

**验收**:闭合误差 0.0000%;剖面呈工艺梯度(好氧 DO 趋势+残差为主、近单位根 DO 残差高、ORP 周期占比起来、出水以残差为主)。

---

## 工作二 · 残差白化效果(`work2_whitening.py`)
**支撑核心方法论 + 物理机理。三轨绝不混报。**

- **iid 轨**:`e(t)→η(t)` before/after ACF(共享 y,标 mabsacf 降幅)+ 窗口化 LB 通过率 + PACF(附录)。
- **autocorr_aware 轨**:不做 before/after;残差 ACF 慢衰 + 频谱宽带 roll-off(无主峰)+ `n_eff/n` → "不可白化而非白化失败"(中性蓝,非警示红)。
- **floor_freeze 轨**:退出白化考核,仅表内标注。
- **Ljung–Box** 用窗口化通过率 + 效应量(`mabsacf`),正文须讨论大-n 单次 LB 过度功效(n≈3.7e5 近乎全拒)。
- **平稳性双检**:ADF + KPSS;识别"ADF 拒单位根但 n_eff/n≪1"的近单位根区间(正是好氧前段三通道)。

**产出**:`fig_2a_iid_acf_before_after.png`(图 A)· `fig_2b_nearUR_acf_spectrum.png`(图 B)· `fig_1x_whiteness_control_gradient.png`(正文机理:沿程白化性梯度,按 scoring_mode 着色)· `fig_A2_pacf_order.png`(附录)· 主表 `T1_whitening_main.csv` · 各图数据 bundle。

**验收**:iid 通道 mabsacf 平均降 **93.5%**、窗口 LB 通过率 0.029→0.323;autocorr_aware acf1≈0.981、n_eff/n≈0.0094、ADF 全拒(近单位根);全表与 manifest 一致。

---

## 工作三 · 尖峰事件统计(`work3_spikes.py`)
**定位为 §1.1 sanity check;正式尖峰检测/阈值标定/事件归因归 §1.2 D1。**

- 按 `scoring_mode` 分流阈值:**iid** → 局部 Hampel(k·MAD)on 创新 η;**autocorr_aware** → 局部 Hampel on 残差/robust_z(禁用全局 3MAD/99% 分位,否则被慢游走主导→事件数失义);**floor_freeze** → 不做,走 freeze/截尾。
- 报**事件率/千点**(不同长度/采样率可比);CI 对 autocorr_aware 用**有效样本** `n·n_eff` 而非 n。

**产出**:`fig_A3_spike_event_rate.png` · 表 `A2_spike_event_rate.csv` · 数据 bundle。

**验收**:autocorr_aware 通道率未因自相关虚高(局部 Hampel,与 iid 同量级,非全局阈值的虚高);iid 创新率高于高斯尾期望(≈2.7/千)反映**白化后仍重尾**(白噪但非正态,GARCH/Student-t 创新的预期特征)——§1.2 尖峰检测应用稳健而非高斯阈值。

---

## 数据来源
`outputs/parquet/{time_base_1min, residual_min, innovation_min, influent_hourly, effluent_hourly, residual_influent, residual_effluent, innovation_influent, innovation_effluent}.parquet` · `outputs/tables/{whiteness_manifest, whitening_before_after}.csv` · `configs/deperiodise.yaml`。
正文留 3 图(方差剖面、白化 before/after+近单位根、白化性-受控强度梯度)+ 主表 T1;PACF、事件率表入附录。
