# 已授权档案敏感性支线：阶段复核

2026-10-20，Asia/Shanghai。技术输出复核 PASS；科学准入 PARTIAL。成功运行 `20261020T144227_611692Z_archive`，原始失败和恢复谱系均保留。

## 1. 目标与实际执行

开发集 Q–COD/T 的 5/15/60 min 平行原型；K=1、两变换、AR(0/1)、三个同期创新Copula、三个探索种子。未开启验证/终端测试、氮、DQR收益、GPD/Vine、SUMO或E1–E3。

## 2. 方法和配置

configs/archive_sensitivity.json 保存全部原型数值与用途；日/周各一组唯一谐波，条件慢项为截距/标准化日历与T，分块条件OLS。经验边际保留原子，用固定种子随机PIT；t自由度仅在登记数值范围内条件伪似然搜索。[SciPy 1.15.3官方接口](https://docs.scipy.org/doc/scipy-1.15.3/reference/generated/scipy.stats.multivariate_t.html)与[statsmodels参考接口](https://www.statsmodels.org/v0.14.4/generated/statsmodels.distributions.copula.api.StudentTCopula.html)已核对，且密度与本机参考实现做数值比对。

## 3. 输入与覆盖

原开发档案393120分钟，其中Q/COD/T技术有效388596分钟；共同完整小时规则保留382380分钟（6373小时，97.268%日历时长），连带排除6216个技术有效分钟。这可能改变事件覆盖，尚无独立事件证据证明排除随机。三尺度的名义水量与COD负荷重算一致，不代表原生测量积分已经验证。合成采用8月1日至8月30日的30日日历窗口，其中共同有效时长665小时；缺口保留并重置状态。记录的T/日历是回顾条件，且生成窗口属于拟合域，不是独立测试。

## 4. 实际结果

12个时间原型、24个经验边际、36个Copula拟合和108条轨迹完成。最大可逆误差9.45e-16；经验广义逆训练支持恢复误差0。下表在各尺度×探索种子上作描述性汇总，不是置信区间或独立环境事件重复。

|变换|AR阶|Copula|τ差中位数|Q一小时ACF差中位数|COD一小时ACF差中位数|负Q行|负COD行|
|---|---:|---|---:|---:|---:|---:|---:|
|identity|0|Gaussian|0.0569|0.6731|0.7434|0|69|
|identity|0|Student_t|0.0658|0.6717|0.7602|0|73|
|identity|0|independence|0.0551|0.6735|0.7673|0|70|
|identity|1|Gaussian|0.0966|0.0213|0.0862|0|752|
|identity|1|Student_t|0.0961|0.0188|0.0542|4|1159|
|identity|1|independence|0.0966|0.0182|0.0688|4|1067|
|log1p|0|Gaussian|0.0388|0.6480|0.7385|0|0|
|log1p|0|Student_t|0.0498|0.6456|0.7612|0|0|
|log1p|0|independence|0.0334|0.6510|0.7644|0|0|
|log1p|1|Gaussian|0.0849|0.0177|0.0662|0|0|
|log1p|1|Student_t|0.0415|0.0227|0.0581|0|0|
|log1p|1|independence|0.0587|0.0128|0.0427|0|0|

3组t自由度接近200数值搜索上界，具体case见边界诊断CSV；优化收敛不代表尾部结构可辨识，不能把200当已确定的物理/统计参数。

## 5. 输出与图表

[诊断数据](../artifacts/archive_sensitivity/validation/synthesis_diagnostics.csv)、[全物理滞后相关](../artifacts/archive_sensitivity/validation/temporal_correlations.csv)、[轨迹文件谱系](../artifacts/archive_sensitivity/validation/trajectory_file_map.csv)、[支持卡](../artifacts/archive_sensitivity/validation/support_card.csv)。两变换各一张三面板图提供SVG/PDF/PNG与全108轨迹源CSV；颜色表示Copula，线型/标记表示AR阶，跨种子取中位数。

## 6. 测试与验收

49项工程测试通过。独立检查实际文件SHA、全部配置组合、时间/支持/T条件、负值账本和正式准入状态，记录于 [archive_execution_verification.json](../run_manifest/archive_execution_verification.json)。一小时在60min网格是拟合的一阶滞后，在5min网格是十二阶；更低误差不构成选60min的理由。应结合已输出6h/24h/168h诊断，不用该原型选择主步长。

## 7. 失败、风险及局限

首次M07在260字符Windows路径处失败；只缩短文件名并用SHA一致检查点恢复，未重新拟合。失败manifest/error.log及M07补充记录保留。108条轨迹共406980个输出行出现8条负Q、3190条负COD，涉及变换['identity']，未裁剪/投影；这是跨配置输出计数，不是真实发生率。本次log1p未出现负值，但expm1(y)在y<0时仍可能为负，不能宣称该变换保证非负。正式物理准入未通过。同期τ优劣随变换/尺度/AR变化，不存在本轮已验证的统一赢家。AR1对一小时ACF的描述改善不等于事件/过程保真、留出改进或跨时滞因果效应。

## 8. 下一步

先审查非负支持、残留自相关/平方创新/CCF、共同支持对候选事件覆盖的影响，再提交是否扩展原有ARMA/低阶VAR候选及冻结规则的证据。暂不扩大t自由度范围、不裁剪负值、不升级复杂分解或GPD。主步长仍null，原生频率UNKNOWN；科学参数/实验或验收变更继续先确认。已批准的M01/M02提交4dd7ae38已推送；本支线新增代码/报告/汇总结果未上传，另备白名单等待确认。
