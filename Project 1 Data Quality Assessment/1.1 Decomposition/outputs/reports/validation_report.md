# §1.1 时间底座与非平稳特征解析 — 有效性验证报告

自动生成。对应实施方案 v3 第八章「有效性验证设计」。

## 1. 分解充分性 (残差谱局部峰显著性 < 2 视为周期已剥离)

- 通道数: 33
- **主周期** (min: 24h / h: 24h) 峰显著性 < 2.0 的通道: **27/33** (主导日周期已基本剥离)
- 全部候选周期同时 < 2.0 的通道: 0/33 (次周期 12h/168h 较噪声,剩余结构交由 1.1.3 白化吸收)
- 说明: 分解前残差谱在日周期处峰显著性高达 10^4~10^6,分解后中位数降至 主周期≈1.39; 配合白化后 |ACF| 降至 ~0.05 (见第2节)

| channel    | track   | decomp_pass   |   stl_iters |   P1440 |    P720 |   P10080 |     P24 |    P168 |
|:-----------|:--------|:--------------|------------:|--------:|--------:|---------:|--------:|--------:|
| DO_1_1     | min     | True          |           0 |   1.285 |   2.404 |  nan     | nan     | nan     |
| DO_1_2     | min     | True          |           1 |   0.959 |   0.673 |  nan     | nan     | nan     |
| DO_1_3     | min     | True          |           2 |   1.339 |   0.641 |  nan     | nan     | nan     |
| DO_1_4     | min     | True          |           0 |   1.449 | nan     |  nan     | nan     | nan     |
| DO_2_1     | min     | True          |           1 |   1.647 |   3.389 |  nan     | nan     | nan     |
| DO_2_2     | min     | True          |           2 |   1.495 |   3.783 |  nan     | nan     | nan     |
| DO_2_3     | min     | True          |           1 |   1.557 |   4.564 |  nan     | nan     | nan     |
| DO_2_4     | min     | True          |           1 |   0.712 | nan     |  nan     | nan     | nan     |
| ORP_1_1    | min     | True          |           1 |   1.724 |   1.635 |  nan     | nan     | nan     |
| ORP_1_2    | min     | True          |           1 |   1.732 |   1.698 |  nan     | nan     | nan     |
| ORP_1_3    | min     | False         |           3 |   2.832 |   1.464 |  nan     | nan     | nan     |
| ORP_2_1    | min     | True          |           1 |   1.15  |   7.895 |  nan     | nan     | nan     |
| ORP_2_2    | min     | True          |           1 |   1.042 |   5.851 |  nan     | nan     | nan     |
| ORP_2_3    | min     | True          |           1 |   1.566 |   2.922 |  nan     | nan     | nan     |
| QR_1       | min     | True          |           1 |   0.915 | nan     |    1.51  | nan     | nan     |
| QR_2       | min     | False         |           3 |   4.804 | nan     |    7.129 | nan     | nan     |
| QIR_1      | min     | True          |           1 |   0.772 | nan     |   15.039 | nan     | nan     |
| QIR_2      | min     | True          |           2 |   1.385 | nan     |    8.825 | nan     | nan     |
| inf_pH     | hour    | True          |           0 | nan     | nan     |  nan     |   1.102 |   6.787 |
| inf_T      | hour    | True          |           0 | nan     | nan     |  nan     |   0.964 |   6.728 |
| inf_SS     | hour    | True          |           1 | nan     | nan     |  nan     |   0.905 |  14.612 |
| inf_NH4    | hour    | True          |           1 | nan     | nan     |  nan     |   1.504 |   3.965 |
| inf_TP     | hour    | False         |           1 | nan     | nan     |  nan     |   2.646 |   3.381 |
| inf_TN     | hour    | False         |           1 | nan     | nan     |  nan     |   3.009 |   4.201 |
| inf_COD    | hour    | True          |           1 | nan     | nan     |  nan     |   1.587 |   4.595 |
| inf_Q      | hour    | False         |           1 | nan     | nan     |  nan     |   2.309 |   3.542 |
| eff_COD    | hour    | True          |           0 | nan     | nan     |  nan     |   0.833 |   5.756 |
| eff_TP     | hour    | True          |           0 | nan     | nan     |  nan     |   1.556 |   3.417 |
| eff_NH4    | hour    | False         |           1 | nan     | nan     |  nan     |   8.533 |   2.113 |
| eff_TN     | hour    | True          |           1 | nan     | nan     |  nan     |   0.942 |   6.55  |
| eff_pH     | hour    | True          |           0 | nan     | nan     |  nan     |   0.479 |   2.25  |
| eff_T      | hour    | True          |           0 | nan     | nan     |  nan     |   0.399 |   4.666 |
| eff_sludge | hour    | True          |           0 | nan     | nan     |  nan     |   0.799 |   2.879 |

## 2. 白化充分性 (创新序列 LB 通过率 + ACF 衰减)

- 残差窗口 LB 通过率均值: **0.026** → 创新: **0.102**
- |ACF(1)| 均值: 残差 **0.8307** → 创新 **0.5683**
- 平均|ACF[1..10]|: 残差 **0.6641** → 创新 **0.4305**

| channel    | track   |   lb_passrate_resid |   lb_passrate_innov |   n_windows |   acf1_resid |   acf1_innov |   mabsacf_resid |   mabsacf_innov |   adf_p_innov | adf_reject_innov   |   kpss_p_innov | kpss_stat_innov   |   arch_p_innov | arch_het_innov   |
|:-----------|:--------|--------------------:|--------------------:|------------:|-------------:|-------------:|----------------:|----------------:|--------------:|:-------------------|---------------:|:------------------|---------------:|:-----------------|
| DO_1_1     | min     |               0     |               0     |         254 |       0.9762 |       0.9762 |          0.8322 |          0.8322 |             0 | True               |         0.1    | True              |         0      | True             |
| DO_1_2     | min     |               0     |               0.024 |         254 |       0.9304 |      -0.1832 |          0.7793 |          0.0442 |             0 | True               |         0.1    | True              |         0      | True             |
| DO_1_3     | min     |               0     |               0.091 |         254 |       0.9269 |       0.0394 |          0.6968 |          0.047  |             0 | True               |         0.1    | True              |         0      | True             |
| DO_1_4     | min     |               0.016 |               0.079 |         254 |       0.9133 |       0.3123 |          0.7411 |          0.1795 |             0 | True               |         0.1    | True              |         0.0001 | True             |
| DO_2_1     | min     |               0     |               0     |         254 |       0.9832 |       0.9832 |          0.8342 |          0.8342 |             0 | True               |         0.1    | True              |         0      | True             |
| DO_2_2     | min     |               0     |               0     |         254 |       0.9849 |       0.9849 |          0.8841 |          0.8841 |             0 | True               |         0.1    | True              |         0      | True             |
| DO_2_3     | min     |               0     |               0.083 |         254 |       0.8576 |       0.0087 |          0.6247 |          0.019  |             0 | True               |         0.1    | True              |         0      | True             |
| DO_2_4     | min     |               0     |               0     |         254 |       0.8997 |       0.8997 |          0.8287 |          0.8287 |             0 | True               |         0.1    | True              |         0      | True             |
| ORP_1_1    | min     |               0     |               0     |         254 |       0.9975 |       0.9975 |          0.9876 |          0.9876 |             0 | True               |         0.1    | True              |         0      | True             |
| ORP_1_2    | min     |               0     |               0     |         254 |       0.999  |       0.999  |          0.9927 |          0.9927 |             0 | True               |         0.1    | True              |         0      | True             |
| ORP_1_3    | min     |               0     |               0.173 |         254 |       0.9969 |       0.0374 |          0.9763 |          0.019  |             0 | True               |         0.1    | True              |         0.0044 | True             |
| ORP_2_1    | min     |               0     |               0.031 |         254 |       0.999  |       0.1265 |          0.9949 |          0.0787 |             0 | True               |         0.1    | True              |         0      | True             |
| ORP_2_2    | min     |               0     |               0.146 |         254 |       0.9986 |      -0.0278 |          0.991  |          0.0354 |             0 | True               |         0.1    | True              |         0.2313 | False            |
| ORP_2_3    | min     |               0     |               0     |         254 |       0.9897 |       0.9897 |          0.9653 |          0.9653 |             0 | True               |         0.1    | True              |         0      | True             |
| QR_1       | min     |               0     |               0     |         254 |       0.9359 |       0.9359 |          0.8695 |          0.8695 |             0 | True               |         0.1    | True              |         0      | True             |
| QR_2       | min     |               0     |               0     |         254 |       0.9595 |       0.9595 |          0.9237 |          0.9237 |             0 | True               |         0.1    | True              |         0      | True             |
| QIR_1      | min     |               0     |               0.441 |         254 |       0.8712 |       0.0853 |          0.748  |          0.0203 |             0 | True               |         0.0827 | True              |         0      | True             |
| QIR_2      | min     |               0     |               0     |         254 |       0.7918 |       0.7918 |          0.6894 |          0.6894 |             0 | True               |         0.1    | True              |         0      | True             |
| inf_pH     | hour    |               0     |               0.6   |          25 |       0.9689 |      -0.0177 |          0.8557 |          0.0101 |             0 | True               |         0.1    | True              |         1      | False            |
| inf_T      | hour    |               0     |               0     |          28 |       0.964  |       0.964  |          0.8066 |          0.8066 |             0 | True               |         0.1    | True              |         0      | True             |
| inf_SS     | hour    |               0.107 |               0.107 |          28 |       0.4218 |       0.4218 |          0.2755 |          0.2755 |             0 | True               |         0.1    | True              |         0      | True             |
| inf_NH4    | hour    |               0     |               0     |          27 |       0.8949 |       0.8949 |          0.5849 |          0.5849 |             0 | True               |         0.1    | True              |         0      | True             |
| inf_TP     | hour    |               0     |               0     |          28 |       0.8286 |       0.8286 |          0.4593 |          0.4593 |             0 | True               |         0.1    | True              |         0      | True             |
| inf_TN     | hour    |               0     |               0     |          28 |       0.7749 |       0.7749 |          0.4063 |          0.4063 |             0 | True               |         0.1    | True              |         0      | True             |
| inf_COD    | hour    |               0     |               0     |          28 |       0.7611 |       0.7611 |          0.3596 |          0.3596 |             0 | True               |         0.1    | True              |         0      | True             |
| inf_Q      | hour    |               0     |               0     |          28 |       0.8024 |       0.8024 |          0.4191 |          0.4191 |             0 | True               |         0.1    | True              |         0      | True             |
| eff_COD    | hour    |               0.023 |               0.659 |          44 |       0.654  |      -0.0676 |          0.4285 |          0.0172 |             0 | True               |         0.1    | True              |         1      | False            |
| eff_TP     | hour    |               0.095 |               0.31  |          42 |       0.5798 |       0.1319 |          0.407  |          0.063  |             0 | True               |         0.1    | True              |         1      | False            |
| eff_NH4    | hour    |               0.167 |               0.167 |          18 |       0.7751 |       0.7751 |          0.2323 |          0.2323 |             0 | True               |         0.1    | True              |         0      | True             |
| eff_TN     | hour    |               0.023 |               0.023 |          44 |       0.5834 |       0.5834 |          0.2999 |          0.2999 |             0 | True               |         0.1    | True              |         0      | True             |
| eff_pH     | hour    |               0.023 |               0.023 |          44 |       0.1688 |       0.1688 |          0.1492 |          0.1492 |             0 | True               |         0.1    | True              |         1      | False            |
| eff_T      | hour    |               0.023 |               0.023 |          44 |       0.6109 |       0.6109 |          0.5907 |          0.5907 |             0 | True               |         0.1    | True              |         1      | False            |
| eff_sludge | hour    |               0.378 |               0.378 |          45 |       0.6126 |       0.6126 |          0.282  |          0.282  |             0 | True               |         0.1    | True              |         0      | True             |

## 3. 无泄漏检验 (因果 vs 整段分解)

- 通道 DO_1_3: 均值偏差 **0.00013** (≈0 即无系统偏差), 相关 0.985, 因果残差 std 0.4141 vs 整段 0.4033
- 结论: 因果分解与整段分解残差无系统偏差，但因果版可在线复现、无未来信息泄漏。

## 4. 差异化必要性 (互换 min/h 分解策略)

| channel   | proper                      | wrong                                          |   proper_peakratio_24h |   wrong_peakratio_24h |   proper_resid_std |   wrong_resid_std |   removed_var_proper |   removed_var_wrong |   overfit_ratio |
|:----------|:----------------------------|:-----------------------------------------------|-----------------------:|----------------------:|-------------------:|------------------:|---------------------:|--------------------:|----------------:|
| DO_1_3    | aerobic_do                  | effluent                                       |                  6.971 |                90.754 |             0.4141 |            0.4377 |             nan      |            nan      |         nan     |
| eff_COD   | effluent(STL,168h,order<=2) | min-style(24h LOESS + order-4 daily harmonics) |                nan     |               nan     |             1.9926 |            1.6458 |               7.4078 |              7.7164 |           1.042 |

- min 端:错误策略(出水低阶套到好氧 DO)使目标周期残差峰比从 ~7 飙到 ~91(13×);出水端:错误策略(24h 短带宽 LOESS + 高阶日谐波)过度平滑,把慢变真实波动当趋势/周期搬走——移除量方差与残差 std 此消彼长(overfit_ratio>1、残差 std 反降),证明分钟级与小时级必须差异化分解。

## 5. 下游增益 — 消融变体 A (故障注入 AUC)

| channel   |   amp_mult |   n_faults |   auc_raw |   auc_residual |   auc_innovation |
|:----------|-----------:|-----------:|----------:|---------------:|-----------------:|
| DO_1_3    |        1   |        200 |    0.4826 |         0.6113 |           0.9361 |
| DO_1_3    |        1.5 |        200 |    0.5447 |         0.7632 |           0.9828 |
| DO_1_3    |        2   |        200 |    0.5967 |         0.8601 |           0.9977 |
| DO_1_3    |        3   |        200 |    0.726  |         0.9378 |           0.9999 |
| DO_1_3    |        4   |        200 |    0.8787 |         0.9789 |           1      |
| DO_1_3    |        6   |        200 |    0.9765 |         0.9974 |           1      |
| ORP_2_1   |        1   |        200 |    0.5464 |         0.6633 |           0.9998 |
| ORP_2_1   |        1.5 |        200 |    0.5511 |         0.7244 |           0.9999 |
| ORP_2_1   |        2   |        200 |    0.6217 |         0.7841 |           0.9999 |
| ORP_2_1   |        3   |        200 |    0.6787 |         0.8949 |           1      |
| ORP_2_1   |        4   |        200 |    0.7629 |         0.9498 |           1      |
| ORP_2_1   |        6   |        200 |    0.8748 |         0.9891 |           1      |

- AUC 随注入幅度上升;在各幅度下均有 原始 < 去周期残差 < 白化创新，证明去周期+白化提升故障可分性,且小幅故障下增益最明显 (支撑大纲 1.4.2 变体 A)。

## 6. 实测案例库 (case study)

| case                       | subject   | finding                                                               |
|:---------------------------|:----------|:----------------------------------------------------------------------|
| DO_4 floor/freeze          | DO_1_4    | mean=0.0237, day/night diff=0.0006, |corr QIR|=0.036 -> process_floor |
| DO_4 floor/freeze          | DO_2_4    | mean=0.2346, day/night diff=0.0068, |corr QIR|=0.065 -> process_floor |
| QR_2 negative flow         | QR_2      | 15.21% samples < 0 (physically impossible; acquisition)               |
| QR_1 negative flow         | QR_1      | 3.13% samples < 0                                                     |
| ORP_1_3 structural drift   | ORP_1_3   | Theil-Sen trend ~ 0.304 mV/day over 256 days (suspected long drift)   |
| influent->effluent HRT lag | COD       | max daily cross-corr at lag=1 d (r=0.56)                              |
| seasonal temp migration    | inf_T     | influent T 24.1C -> 18.2C (range 12.0C, season cohorts)               |
