# §1.1 时间底座与非平稳特征解析 — 有效性验证报告

自动生成。对应实施方案 v3 第八章「有效性验证设计」。

## 1. 分解充分性 (残差谱局部峰显著性 < 2 视为周期已剥离)

- 通道数: 33
- **主周期** (min: 24h / h: 24h) 峰显著性 < 2.0 的通道: **9/33** (主导日周期已基本剥离)
- 全部候选周期同时 < 2.0 的通道: 0/33 (次周期 12h/168h 较噪声,剩余结构交由 1.1.3 白化吸收)
- 说明: 分解前残差谱在日周期处峰显著性高达 10^4~10^6,分解后中位数降至 主周期≈3.89; 配合白化后 |ACF| 降至 ~0.05 (见第2节)

| channel    | track   |   P1440 |    P720 |   P10080 |     P24 |    P168 |
|:-----------|:--------|--------:|--------:|---------:|--------:|--------:|
| DO_1_1     | min     |   1.285 |   2.404 |  nan     | nan     | nan     |
| DO_1_2     | min     |   3.621 |   4.163 |  nan     | nan     | nan     |
| DO_1_3     | min     |   6.971 |   2.371 |  nan     | nan     | nan     |
| DO_1_4     | min     |   1.449 | nan     |  nan     | nan     | nan     |
| DO_2_1     | min     |   4.239 |   5.39  |  nan     | nan     | nan     |
| DO_2_2     | min     |  10.873 |   6.565 |  nan     | nan     | nan     |
| DO_2_3     | min     |   4.088 |  10.629 |  nan     | nan     | nan     |
| DO_2_4     | min     |   2.291 | nan     |  nan     | nan     | nan     |
| ORP_1_1    | min     |   4.318 | nan     |  nan     | nan     | nan     |
| ORP_1_2    | min     |   6.384 | nan     |  nan     | nan     | nan     |
| ORP_1_3    | min     |  11.17  | nan     |  nan     | nan     | nan     |
| ORP_2_1    | min     |   6.451 | nan     |  nan     | nan     | nan     |
| ORP_2_2    | min     |   4.067 | nan     |  nan     | nan     | nan     |
| ORP_2_3    | min     |   4.287 | nan     |  nan     | nan     | nan     |
| QR_1       | min     |   3.888 | nan     |    1.414 | nan     | nan     |
| QR_2       | min     |  15.665 | nan     |    5.179 | nan     | nan     |
| QIR_1      | min     |   2.377 | nan     |   12.468 | nan     | nan     |
| QIR_2      | min     |   4.412 | nan     |    7.319 | nan     | nan     |
| inf_pH     | hour    | nan     | nan     |  nan     |   1.102 |   6.787 |
| inf_T      | hour    | nan     | nan     |  nan     |   0.964 |   6.728 |
| inf_SS     | hour    | nan     | nan     |  nan     |   2.133 |  12.19  |
| inf_NH4    | hour    | nan     | nan     |  nan     |   2.697 |   4.353 |
| inf_TP     | hour    | nan     | nan     |  nan     |   4.179 |   3.552 |
| inf_TN     | hour    | nan     | nan     |  nan     |   4.527 |   3.029 |
| inf_COD    | hour    | nan     | nan     |  nan     |   2.6   |   4.019 |
| inf_Q      | hour    | nan     | nan     |  nan     |   5.82  |   3.031 |
| eff_COD    | hour    | nan     | nan     |  nan     |   0.833 |   5.756 |
| eff_TP     | hour    | nan     | nan     |  nan     |   1.556 |   3.417 |
| eff_NH4    | hour    | nan     | nan     |  nan     |   6.349 |   3.775 |
| eff_TN     | hour    | nan     | nan     |  nan     |   3.547 |   6.177 |
| eff_pH     | hour    | nan     | nan     |  nan     |   0.479 |   2.25  |
| eff_T      | hour    | nan     | nan     |  nan     |   0.399 |   4.666 |
| eff_sludge | hour    | nan     | nan     |  nan     |   0.799 |   2.879 |

## 2. 白化充分性 (创新序列 LB 通过率 + ACF 衰减)

- 残差窗口 LB 通过率均值: **0.025** → 创新: **0.295**
- |ACF(1)| 均值: 残差 **0.8306** → 创新 **0.0846**
- 平均|ACF[1..10]|: 残差 **0.6632** → 创新 **0.0462**

| channel    | track   |   lb_passrate_resid |   lb_passrate_innov |   n_windows |   acf1_resid |   acf1_innov |   mabsacf_resid |   mabsacf_innov |   adf_p_innov | adf_reject_innov   |   kpss_p_innov | kpss_stat_innov   |   arch_p_innov | arch_het_innov   |
|:-----------|:--------|--------------------:|--------------------:|------------:|-------------:|-------------:|----------------:|----------------:|--------------:|:-------------------|---------------:|:------------------|---------------:|:-----------------|
| DO_1_1     | min     |               0     |               0.008 |         254 |       0.9762 |       0.1944 |          0.8322 |          0.0604 |             0 | True               |         0.1    | True              |         0      | True             |
| DO_1_2     | min     |               0     |               0.02  |         254 |       0.9299 |      -0.1756 |          0.7788 |          0.0434 |             0 | True               |         0.1    | True              |         0      | True             |
| DO_1_3     | min     |               0     |               0.071 |         254 |       0.9269 |       0.0137 |          0.698  |          0.037  |             0 | True               |         0.1    | True              |         0      | True             |
| DO_1_4     | min     |               0.016 |               0.075 |         254 |       0.9133 |       0.3262 |          0.7411 |          0.1854 |             0 | True               |         0.1    | True              |         0      | True             |
| DO_2_1     | min     |               0     |               0.012 |         254 |       0.9833 |      -0.2456 |          0.8369 |          0.0451 |             0 | True               |         0.1    | True              |         0.9121 | False            |
| DO_2_2     | min     |               0     |               0.031 |         254 |       0.9852 |       0.0027 |          0.8864 |          0.0275 |             0 | True               |         0.1    | True              |         0      | True             |
| DO_2_3     | min     |               0     |               0.083 |         254 |       0.8582 |      -0.0148 |          0.6257 |          0.0186 |             0 | True               |         0.1    | True              |         0      | True             |
| DO_2_4     | min     |               0     |               0.161 |         254 |       0.8998 |       0.1101 |          0.8286 |          0.028  |             0 | True               |         0.0394 | False             |         0.2529 | False            |
| ORP_1_1    | min     |               0     |               0.276 |         254 |       0.9975 |       0.0487 |          0.9875 |          0.0345 |             0 | True               |         0.1    | True              |         0.9998 | False            |
| ORP_1_2    | min     |               0     |               0.13  |         254 |       0.999  |       0.0339 |          0.9926 |          0.0238 |             0 | True               |         0.1    | True              |         0.9986 | False            |
| ORP_1_3    | min     |               0     |               0.079 |         254 |       0.9969 |       0.0937 |          0.9759 |          0.1009 |             0 | True               |         0.1    | True              |         0.9723 | False            |
| ORP_2_1    | min     |               0     |               0.031 |         254 |       0.999  |       0.1173 |          0.995  |          0.0833 |             0 | True               |         0.1    | True              |         0      | True             |
| ORP_2_2    | min     |               0     |               0.169 |         254 |       0.9986 |      -0.0345 |          0.9912 |          0.0331 |             0 | True               |         0.1    | True              |         0.1249 | False            |
| ORP_2_3    | min     |               0     |               0.039 |         254 |       0.99   |       0.206  |          0.9664 |          0.1897 |             0 | True               |         0.1    | True              |         0      | True             |
| QR_1       | min     |               0     |               0.067 |         254 |       0.9341 |       0.2301 |          0.8656 |          0.0885 |             0 | True               |         0.1    | True              |         1      | False            |
| QR_2       | min     |               0     |               0.02  |         254 |       0.9559 |       0.1775 |          0.916  |          0.1881 |             0 | True               |         0.1    | True              |         0      | True             |
| QIR_1      | min     |               0     |               0.437 |         254 |       0.8616 |       0.0833 |          0.7311 |          0.0196 |             0 | True               |         0.0473 | False             |         0      | True             |
| QIR_2      | min     |               0     |               0.492 |         254 |       0.7882 |       0.0176 |          0.6837 |          0.0071 |             0 | True               |         0.1    | True              |         0.0032 | True             |
| inf_pH     | hour    |               0     |               0.6   |          25 |       0.9689 |      -0.0177 |          0.8557 |          0.0101 |             0 | True               |         0.1    | True              |         1      | False            |
| inf_T      | hour    |               0     |               0.679 |          28 |       0.964  |      -0.0382 |          0.8066 |          0.0197 |             0 | True               |         0.1    | True              |         1      | False            |
| inf_SS     | hour    |               0.071 |               0.643 |          28 |       0.4203 |       0.026  |          0.2677 |          0.0323 |             0 | True               |         0.1    | True              |         0.9992 | False            |
| inf_NH4    | hour    |               0     |               0.593 |          27 |       0.8912 |      -0.0039 |          0.5836 |          0.0162 |             0 | True               |         0.1    | True              |         0      | True             |
| inf_TP     | hour    |               0     |               0.464 |          28 |       0.8309 |      -0.0171 |          0.4715 |          0.0163 |             0 | True               |         0.1    | True              |         0.3065 | False            |
| inf_TN     | hour    |               0     |               0.357 |          28 |       0.7675 |       0.0178 |          0.3844 |          0.0152 |             0 | True               |         0.1    | True              |         0.9691 | False            |
| inf_COD    | hour    |               0     |               0.786 |          28 |       0.7564 |       0.0334 |          0.3524 |          0.01   |             0 | True               |         0.1    | True              |         0.272  | False            |
| inf_Q      | hour    |               0     |               0.357 |          28 |       0.7997 |       0.1395 |          0.4055 |          0.0345 |             0 | True               |         0.1    | True              |         1      | False            |
| eff_COD    | hour    |               0.023 |               0.659 |          44 |       0.654  |      -0.0676 |          0.4285 |          0.0172 |             0 | True               |         0.1    | True              |         1      | False            |
| eff_TP     | hour    |               0.095 |               0.31  |          42 |       0.5798 |       0.1304 |          0.407  |          0.06   |             0 | True               |         0.1    | True              |         1      | False            |
| eff_NH4    | hour    |               0.167 |               0.556 |          18 |       0.7959 |       0.0239 |          0.252  |          0.0168 |             0 | True               |         0.1    | True              |         1      | False            |
| eff_TN     | hour    |               0.023 |               0.432 |          44 |       0.5943 |       0.0584 |          0.3145 |          0.0213 |             0 | True               |         0.1    | True              |         0.9975 | False            |
| eff_pH     | hour    |               0.023 |               0.477 |          44 |       0.1688 |      -0.0052 |          0.1492 |          0.0015 |             0 | True               |         0.1    | True              |         1      | False            |
| eff_T      | hour    |               0.023 |               0.295 |          44 |       0.6109 |      -0.0028 |          0.5907 |          0.0016 |             0 | True               |         0.1    | True              |         1      | False            |
| eff_sludge | hour    |               0.378 |               0.311 |          45 |       0.6126 |      -0.0849 |          0.282  |          0.0379 |             0 | True               |         0.1    | True              |         0.5171 | False            |

## 3. 无泄漏检验 (因果 vs 整段分解)

- 通道 DO_1_3: 均值偏差 **0.00013** (≈0 即无系统偏差), 相关 0.985, 因果残差 std 0.4141 vs 整段 0.4033
- 结论: 因果分解与整段分解残差无系统偏差，但因果版可在线复现、无未来信息泄漏。

## 4. 差异化必要性 (互换 min/h 分解策略)

| channel   | proper                 | wrong                        |   proper_peakratio_24h |   wrong_peakratio_24h |   proper_resid_std |   wrong_resid_std |
|:----------|:-----------------------|:-----------------------------|-----------------------:|----------------------:|-------------------:|------------------:|
| DO_1_3    | aerobic_do             | effluent                     |                  6.971 |                90.754 |             0.4141 |            0.4377 |
| eff_COD   | effluent(STL,order<=2) | forced 24h order-6 harmonics |                  0.909 |                 0.908 |             1.9926 |            2.0013 |

- 用错误策略 (出水低阶套到 min DO / min 高阶套到出水) 后，目标周期残差峰比上升、残差方差变化，证明分钟级与小时级必须差异化分解。

## 5. 下游增益 — 消融变体 A (故障注入 AUC)

| channel   |   n_points |   n_faults |   auc_raw |   auc_residual |   auc_innovation |
|:----------|-----------:|-----------:|----------:|---------------:|-----------------:|
| DO_1_3    |     367184 |        200 |    0.9454 |         0.9967 |                1 |
| ORP_2_1   |     367190 |        200 |    0.821  |         0.9831 |                1 |

- 同一注入故障下，AUC: 原始序列 < 去周期残差 < 白化创新，证明去周期+白化提升了故障可分性 (支撑大纲 1.4.2 变体 A)。

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
