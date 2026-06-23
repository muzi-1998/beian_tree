# D1 → §1.1 Decomposition 对接说明

> 配套审计：[`D1_detector_audit.md`](D1_detector_audit.md)（§3 ROI 清单）。
> 本次改动落实其中 **#1 改输入源 + scoring_mode 分支** 与 **#2 修两处非因果泄漏**。

## 1. 动机（审计结论回顾）

D1 v1.0 用自带的谐波/STL 基线（`src/baseline/deperiodise.py`）对每个通道去周期，
得到的残差 **未白化**。基于 i.i.d. 临界值的检测器——step（相邻 KS）、regime（KS 层）、
PELT——在自相关残差上会 **过度拒绝**（虚假 Q_step / Q_regime 降级、PELT 过分段）。
STL 变体还会 **泄漏未来**（相位分箱均值在整段序列上计算）。

§1.1 已对每个通道做了 ARMA/GARCH 白化，并以 `whiteness_manifest.csv` 给出契约：
每通道的 `scoring_mode`（iid / autocorr_aware / floor_freeze）、`innov_kind`、
`n_eff_ratio`。本次把 D1 的输入源切到 §1.1，并按 `scoring_mode` 路由检测器。

## 2. scoring_mode 路由（D1 的 14 个计分通道）

| scoring_mode | 通道 | i.i.d. 检测器输入 | eff_neff | 统计量去敏 √eff_neff |
|---|---|---|---|---|
| `iid`（已白化） | DO_1_2/1_3/2_3/2_4, ORP_1_1/1_2/1_3/2_1/2_2/2_3 (10) | **创新** innovation（白） | 1.0 | ×1.00（不变） |
| `autocorr_aware`（近单位根） | DO_1_1 (n_eff 0.012), DO_2_1 (0.0085), DO_2_2 (0.0076) | 残差 residual | = n_eff | ×0.09–0.11（~10× 收缩） |
| `floor_freeze`（检测地板） | DO_1_4 (n_eff 0.0453) | （排除） | 0.0 | ×0（归零，交 freeze） |

- **iid**：喂白化创新，i.i.d. 临界值有效，统计量不变。
- **autocorr_aware**（DO_1_1/2_1/2_2，近单位根 acf1≈0.98）：喂残差，但把检测统计量
  按 `√n_eff` 收缩 ~10×，使其不再触发虚警，改倚重多变量 Drift-PLS + D7 一致性。
- **floor_freeze**（DO_1_4，88.99% 在地板）：统计量归零、排除出 step/regime/PELT，
  由 freeze 子分数接管。

## 3. 检测器分工（是否受白化影响）

| 检测器 | 输入 | 白化处理 | 说明 |
|---|---|---|---|
| Spike (Hampel) | 分钟原始 df_min | 不受影响（+修因果窗泄漏） | 局部稳健 |
| Freeze (复合规则) | 分钟原始 df_min | 不受影响 | 规则/RLE/响应损失 |
| **Step (相邻 KS)** | §1.1 路由输入（创新/残差） | **n_eff 去敏** | i.i.d. 敏感 |
| **Regime (W1+KS 两层)** | §1.1 路由输入 | **n_eff 去敏（W1 与 KS 均 ×√n_eff）** | i.i.d. 敏感 |
| **PELT (批校准)** | §1.1 路由输入 | **n_eff 罚项膨胀 1/n_eff** | i.i.d. 敏感 |
| Drift (PLS 虚拟传感器) | §1.1 残差（多变量） | 多变量稳健，不去敏 | 跨通道重构 |
| FF-PCA (辅助) | §1.1 残差（多变量） | 多变量稳健 | SPE 二次确认 |

## 4. 改动文件

| 文件 | 改动 |
|---|---|
| `src/baseline/bridge_decomposition_11.py` | **新增**。加载 §1.1 `residual_min`/`innovation_min`/`whiteness_manifest`，按 `scoring_mode` 构造每通道路由输入 `detector_input_h` + `effective_neff`。 |
| `src/detectors/spike_hampel.py` | **泄漏①修复**：`center=True → center=False`（因果尾窗，不再窥视未来 win//2 分钟）。 |
| `src/detectors/step_adjacent_ks.py` | 新增 `neff_ratio` 参数，KS D 统计量 ×√n_eff。 |
| `src/detectors/regime_two_tier.py` | 新增 `neff_ratio`，W1_norm 与 Tier-2 KS 均 ×√n_eff。 |
| `src/detectors/pelt_batch.py` | 新增 `neff_ratio`，BIC 罚项 ÷n_eff；n_eff=0 直接跳过。 |
| `src/state/auxiliary_modules.py` | 下游 `PELTBatchCalibrator` 同样新增 `neff_ratio`（罚项膨胀）。 |
| `load_real_data_v11.py` | 步骤 2+ 接入桥接（`USE_DECOMP_11` 门控），step/regime 走路由输入 + 每通道 `eff_neff`；drift 走 §1.1 残差；持久化 `scoring_mode`/`eff_neff`/`whitened_input_h` 到 pkl。 |
| `run_v11_pipeline.py` | 下游 PELT 改用 `whitened_input_h` + 每通道 `neff_ratio`（旧 pkl 自动回退残差/1.0）。 |

**泄漏②（STL 未来泄漏）**：在桥接开启时，D1 自带的去周期（含会泄漏的 `stl_decomposition`）
被 §1.1 残差整体替换，因此该泄漏在生效路径上被绕过。

## 5. 如何运行

```bash
# 默认开启桥接（D1_USE_DECOMP_11=1）
python load_real_data_v11.py        # 重算 step/drift/regime（_w11 缓存）+ spike（因果窗）
python run_v11_pipeline.py          # 下游 PELT/状态机/聚合消费新 pkl

# 复现旧（未白化）路径作对照：
D1_USE_DECOMP_11=0 python load_real_data_v11.py
```

缓存说明：spike 缓存更名为 `spike_results_min_causal.pkl`（旧 center=True 缓存不再复用）；
step/drift/regime 在桥接路径用 `_w11` 后缀缓存，与旧缓存并存互不污染；freeze 输入未变，
沿用旧缓存。

依赖：§1.1 的 `outputs/parquet/{residual_min,innovation_min}.parquet` 与
`outputs/tables/whiteness_manifest.csv`（默认从同级 `../1.1 Decomposition/outputs` 读取）。

## 6. 验证状态

- 桥接独立验证：18 通道全部对齐，路由正确（iid=14→创新、autocorr=3→残差、floor=1→归零），
  每通道 `detector_input_h` 与所选源逐点一致。
- n_eff 去敏单测：合成阶跃序列上 neff=1 检出（D=0.875, 19 旗标），neff=0.01 收缩 10×（D=0.0875, 0 旗标），
  neff=0 归零（0 旗标）。
- 全部改动文件 `py_compile` 通过；两个 `PELTBatchCalibrator` 均接受 `neff_ratio`。
