# M01/M02 阶段 GitHub 同步审阅清单（待用户确认）

生成于 2026-10-20T13:57:17.050241+00:00。当前分支 `codex/sumo-input-preparation-20260919`。未执行暂存、commit、push、PR 或合并。

Project2 当前整体尚未被 Git 跟踪，因此本次拟纳入文件包含必要的最终设计基线，以及本轮实现/报告/实际小型结果。既有最终方案正文未修改，其 SHA 与 M01/M02 运行记录一致。

## 变更内容

- M01：只读两源审计、逐单元原值/来源、技术标记、开发集常数段诊断、标签准入。
- M02：开发集双视图、共同支持负荷、连续块、5/15/60 档案诊断；主步长仍 null。
- 工程：阶段入口/测试、源码配置快照、重跑原因与不可覆盖运行记录；12 份模块报告及总进度。
- 实际结果：364 天/524160 行，3669120 单元标记；最大数值重算误差 4.88e-16；两模块 PARTIAL。

## 测试与审查

两次实际执行前各 33 项测试通过；最新工程回归结果见 run_manifest/stage_regression.log。独立复核、图表人工检查通过。白名单进行了 5 MiB 大小检查和常见凭据特征扫描，无匹配；该扫描不是对所有形式敏感信息的绝对保证。清单含厂站汇总质量/覆盖指标与诊断图，属于本次需要明确确认的上传内容。

## 拟执行操作（尚未授权）

确认后拟创建 `codex/project2-m01-m02-audit` 分支，严格按白名单提交一次，并推送该分支到 origin。拟提交消息：`Implement Project2 M01 intake and M02 archive diagnostics`。不创建 PR、不合并。如用户只批准本地 commit 或要求删去部分结果，应据此缩小操作范围。

## 文件范围

下表 115 个文件，共 1,123,798 bytes；另含本审阅说明、CSV SHA 清单和 TXT 路径清单三项管理文件（不对其自引用求 SHA）。CSV 逐文件保存 SHA256，TXT 使用仓库根相对路径。

排除：全部原始 CSV/XLSX、观测级 Parquet、运行快照中的观测级产物、文献全文/知识总库、Word 素材、缓存和临时文件。不能使用 `git add .`。

|拟提交路径（2.3 工程相对）|bytes|
|---|---:|
|.gitignore|287|
|artifacts/data/01_input_audit.json|2,296|
|artifacts/figures/M01_audit.pdf|40,218|
|artifacts/figures/M01_audit.png|250,774|
|artifacts/figures/M01_audit.svg|22,063|
|artifacts/figures/M01_audit_source.csv|5,778|
|artifacts/figures/M01_figure_qa.json|951|
|artifacts/figures/M01_frequency_source.csv|3,952|
|artifacts/figures/M02_audit.pdf|41,856|
|artifacts/figures/M02_audit.png|233,230|
|artifacts/figures/M02_audit.svg|16,743|
|artifacts/figures/M02_audit_source.csv|2,904|
|artifacts/figures/M02_figure_qa.json|984|
|artifacts/README.md|478|
|artifacts/validation/01_label_admission.json|1,348|
|artifacts/validation/01_native_frequency.csv|3,952|
|artifacts/validation/01_technical_quality.csv|5,778|
|artifacts/validation/02_scale_comparison.csv|2,918|
|artifacts/validation/02_scale_decision.json|1,105|
|configs/environment_policy.md|919|
|configs/experiment_protocol.json|9,068|
|configs/model_candidates.json|3,020|
|configs/module_contracts.json|19,072|
|configs/study_design.json|4,460|
|plan and report/02_模块输出物与验收契约.md|17,802|
|plan and report/04_第二章大纲与2.3研究方案_v3_20261020.md|39,660|
|PROJECT_STRUCTURE.md|8,290|
|pyproject.toml|471|
|README.md|3,344|
|reports/M01_执行报告.md|5,757|
|reports/M02_后续科学准入建议.md|3,517|
|reports/M02_执行报告.md|6,143|
|reports/M03_执行报告.md|1,035|
|reports/M04_执行报告.md|1,036|
|reports/M05_执行报告.md|1,035|
|reports/M06_执行报告.md|1,038|
|reports/M07_执行报告.md|1,037|
|reports/M08_执行报告.md|1,035|
|reports/M09_执行报告.md|1,038|
|reports/M10_执行报告.md|1,034|
|reports/M11_执行报告.md|1,035|
|reports/M12_执行报告.md|1,035|
|reports/PROJECT_PROGRESS.md|1,855|
|run_manifest/design_check.json|1,007|
|run_manifest/execution_verification.json|933|
|run_manifest/figure_review.json|1,119|
|run_manifest/figure_source_preflight.json|2,661|
|run_manifest/module_states.json|15,435|
|run_manifest/runs/20261020T134451_986499Z_M01/environment.json|233|
|run_manifest/runs/20261020T134451_986499Z_M01/M01_执行报告.md|4,813|
|run_manifest/runs/20261020T134451_986499Z_M01/manifest.json|6,621|
|run_manifest/runs/20261020T134451_986499Z_M01/source_snapshot/configs/experiment_protocol.json|9,068|
|run_manifest/runs/20261020T134451_986499Z_M01/source_snapshot/configs/model_candidates.json|3,020|
|run_manifest/runs/20261020T134451_986499Z_M01/source_snapshot/configs/module_contracts.json|19,072|
|run_manifest/runs/20261020T134451_986499Z_M01/source_snapshot/configs/study_design.json|4,460|
|run_manifest/runs/20261020T134451_986499Z_M01/source_snapshot/src/project2_synthesis/__init__.py|106|
|run_manifest/runs/20261020T134451_986499Z_M01/source_snapshot/src/project2_synthesis/cli.py|4,483|
|run_manifest/runs/20261020T134451_986499Z_M01/source_snapshot/src/project2_synthesis/contracts.py|11,977|
|run_manifest/runs/20261020T134451_986499Z_M01/source_snapshot/src/project2_synthesis/figures/audit_figures.py|5,369|
|run_manifest/runs/20261020T134451_986499Z_M01/source_snapshot/src/project2_synthesis/intake/label_admission.py|882|
|run_manifest/runs/20261020T134451_986499Z_M01/source_snapshot/src/project2_synthesis/intake/native_frequency.py|1,732|
|run_manifest/runs/20261020T134451_986499Z_M01/source_snapshot/src/project2_synthesis/intake/source_audit.py|11,343|
|run_manifest/runs/20261020T134451_986499Z_M01/source_snapshot/src/project2_synthesis/preparation/aggregation.py|3,939|
|run_manifest/runs/20261020T134451_986499Z_M01/source_snapshot/src/project2_synthesis/preparation/scale_selection.py|9,789|
|run_manifest/runs/20261020T134451_986499Z_M01/source_snapshot/src/project2_synthesis/preparation/splitting.py|1,625|
|run_manifest/runs/20261020T134451_986499Z_M01/source_snapshot/src/project2_synthesis/runtime.py|10,074|
|run_manifest/runs/20261020T134451_986499Z_M01/tests.log|3,323|
|run_manifest/runs/20261020T134719_593878Z_M02/environment.json|233|
|run_manifest/runs/20261020T134719_593878Z_M02/M02_执行报告.md|5,199|
|run_manifest/runs/20261020T134719_593878Z_M02/manifest.json|7,045|
|run_manifest/runs/20261020T134719_593878Z_M02/source_snapshot/configs/experiment_protocol.json|9,068|
|run_manifest/runs/20261020T134719_593878Z_M02/source_snapshot/configs/model_candidates.json|3,020|
|run_manifest/runs/20261020T134719_593878Z_M02/source_snapshot/configs/module_contracts.json|19,072|
|run_manifest/runs/20261020T134719_593878Z_M02/source_snapshot/configs/study_design.json|4,460|
|run_manifest/runs/20261020T134719_593878Z_M02/source_snapshot/src/project2_synthesis/__init__.py|106|
|run_manifest/runs/20261020T134719_593878Z_M02/source_snapshot/src/project2_synthesis/cli.py|4,483|
|run_manifest/runs/20261020T134719_593878Z_M02/source_snapshot/src/project2_synthesis/contracts.py|11,977|
|run_manifest/runs/20261020T134719_593878Z_M02/source_snapshot/src/project2_synthesis/figures/audit_figures.py|5,369|
|run_manifest/runs/20261020T134719_593878Z_M02/source_snapshot/src/project2_synthesis/intake/label_admission.py|882|
|run_manifest/runs/20261020T134719_593878Z_M02/source_snapshot/src/project2_synthesis/intake/native_frequency.py|1,732|
|run_manifest/runs/20261020T134719_593878Z_M02/source_snapshot/src/project2_synthesis/intake/source_audit.py|11,343|
|run_manifest/runs/20261020T134719_593878Z_M02/source_snapshot/src/project2_synthesis/preparation/aggregation.py|3,939|
|run_manifest/runs/20261020T134719_593878Z_M02/source_snapshot/src/project2_synthesis/preparation/scale_selection.py|9,789|
|run_manifest/runs/20261020T134719_593878Z_M02/source_snapshot/src/project2_synthesis/preparation/splitting.py|1,625|
|run_manifest/runs/20261020T134719_593878Z_M02/source_snapshot/src/project2_synthesis/runtime.py|10,074|
|run_manifest/runs/20261020T134719_593878Z_M02/tests.log|3,323|
|run_manifest/stage_regression.log|3,440|
|run_p23_pipeline.py|278|
|src/project2_synthesis/__init__.py|106|
|src/project2_synthesis/cli.py|4,958|
|src/project2_synthesis/contracts.py|11,977|
|src/project2_synthesis/dependence/README.md|549|
|src/project2_synthesis/export/README.md|572|
|src/project2_synthesis/figures/audit_figures.py|5,369|
|src/project2_synthesis/figures/README.md|477|
|src/project2_synthesis/intake/label_admission.py|882|
|src/project2_synthesis/intake/native_frequency.py|1,732|
|src/project2_synthesis/intake/README.md|935|
|src/project2_synthesis/intake/source_audit.py|11,343|
|src/project2_synthesis/margins/README.md|548|
|src/project2_synthesis/physics/README.md|598|
|src/project2_synthesis/preparation/aggregation.py|3,939|
|src/project2_synthesis/preparation/README.md|1,079|
|src/project2_synthesis/preparation/scale_selection.py|9,789|
|src/project2_synthesis/preparation/splitting.py|1,625|
|src/project2_synthesis/regimes/README.md|568|
|src/project2_synthesis/release/README.md|498|
|src/project2_synthesis/runtime.py|11,165|
|src/project2_synthesis/synthesis/README.md|544|
|src/project2_synthesis/temporal/README.md|578|
|src/project2_synthesis/validation/README.md|965|
|tests/test_design_contracts.py|5,674|
|tests/test_intake_preparation.py|11,727|
|tools/prepare_sync_review.py|9,456|
|tools/verify_execution.py|5,253|
