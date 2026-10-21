# 已授权档案敏感性支线：第二阶段 Git 同步审阅（未获上传确认）

此前118路径已按用户确认提交并推送，commit 4dd7ae38；本文件只提出后续提交，不延用此前上传授权。

## 实际变更

- 独立archive配置/入口，完整共同小时支持、K=1、可逆AR(0/1)、经验边际、独立/Gaussian/t、30日回顾条件合成。
- 12时间原型、24边际、36Copula、108轨迹、576滞后诊断；实际运行前49项、最新工程回归50项测试通过。数值/源文件复核PASS，科学准入PARTIAL。
- 负Q8行、负COD3190行未修正；主步长null、原生信息UNKNOWN，未开启留出、氮、SUMO或E1–E3。
- 260字符路径失败及SHA检查点恢复保留，恢复未重新拟合；逐模块报告/进度、图和源表已更新。

## 精确字节保留修复

首轮Git按自动CRLF规范化保存文本，与本地运行SHA不同；已核对为换行差异。新增仅本工程的.gitattributes，禁止换行转换，拟在下一次提交保留原件字节；不修改旧commit或重写历史。本清单中56个文件标为byte_preservation_only，当前本地SHA仍与原审阅清单一致，逻辑/数值未改。其他条目为本阶段内容或状态记录更新。

## 上传范围与检查

196个带SHA文件，共2,819,400 bytes；另含本说明及CSV/TXT管理文件3项。排除全部观测级Parquet、原始资料、经验边际的完整样本数组、其他大型拟合模型、文献/Word、缓存和临时文件。清单含厂站汇总指标、拟合相关/自由度和诊断图，需要用户对本清单明确确认。常见凭据特征未匹配，单文件均小于5MiB。

## 拟执行操作

确认后在codex/project2-m01-m02-audit分支追加一次commit并push至origin；不创建PR、不合并。拟提交消息：Add authorized archive sensitivity pilot and preserve audit bytes。仅按GITHUB_ARCHIVE_PATHS.txt暂存，再对该清单执行renormalize并逐文件比较暂存blob SHA与本地审阅SHA，全部一致后commit/push。未经确认不执行。

## 阶段证据

运行20261020T144227_611692Z_archive；技术验证见run_manifest/archive_execution_verification.json，科学讨论见reports/ARCHIVE_SENSITIVITY_阶段复核.md，图表人工复核见run_manifest/archive_figure_review.json。

|拟提交路径（工程相对）|bytes|变更类型|
|---|---:|---|
|.gitattributes|87|new_or_changed_archive_stage|
|.gitignore|517|new_or_changed_archive_stage|
|artifacts/archive_sensitivity/DATASET_CARD.md|1,162|new_or_changed_archive_stage|
|artifacts/archive_sensitivity/figures/archive_diagnostics_identity.pdf|47,733|new_or_changed_archive_stage|
|artifacts/archive_sensitivity/figures/archive_diagnostics_identity.png|433,359|new_or_changed_archive_stage|
|artifacts/archive_sensitivity/figures/archive_diagnostics_identity.svg|30,186|new_or_changed_archive_stage|
|artifacts/archive_sensitivity/figures/archive_diagnostics_log1p.pdf|48,242|new_or_changed_archive_stage|
|artifacts/archive_sensitivity/figures/archive_diagnostics_log1p.png|460,455|new_or_changed_archive_stage|
|artifacts/archive_sensitivity/figures/archive_diagnostics_log1p.svg|30,599|new_or_changed_archive_stage|
|artifacts/archive_sensitivity/figures/archive_diagnostics_source.csv|86,718|new_or_changed_archive_stage|
|artifacts/archive_sensitivity/figures/figure_contract.json|786|new_or_changed_archive_stage|
|artifacts/archive_sensitivity/validation/copula_fits.csv|9,375|new_or_changed_archive_stage|
|artifacts/archive_sensitivity/validation/empirical_margin_checks.csv|3,650|new_or_changed_archive_stage|
|artifacts/archive_sensitivity/validation/failure_ledger.csv|95|new_or_changed_archive_stage|
|artifacts/archive_sensitivity/validation/grouped_descriptive_summary.csv|1,120|new_or_changed_archive_stage|
|artifacts/archive_sensitivity/validation/student_df_boundary_diagnostics.csv|1,118|new_or_changed_archive_stage|
|artifacts/archive_sensitivity/validation/support_card.csv|760|new_or_changed_archive_stage|
|artifacts/archive_sensitivity/validation/synthesis_diagnostics.csv|90,950|new_or_changed_archive_stage|
|artifacts/archive_sensitivity/validation/temporal_correlations.csv|82,646|new_or_changed_archive_stage|
|artifacts/archive_sensitivity/validation/temporal_roundtrip.csv|2,206|new_or_changed_archive_stage|
|artifacts/archive_sensitivity/validation/trajectory_file_map.csv|23,330|new_or_changed_archive_stage|
|artifacts/archive_sensitivity/validation/trajectory_manifest.csv|22,489|new_or_changed_archive_stage|
|artifacts/data/01_input_audit.json|2,296|byte_preservation_only|
|artifacts/figures/M01_audit.svg|22,063|byte_preservation_only|
|artifacts/figures/M01_audit_source.csv|5,778|byte_preservation_only|
|artifacts/figures/M01_figure_qa.json|951|byte_preservation_only|
|artifacts/figures/M01_frequency_source.csv|3,952|byte_preservation_only|
|artifacts/figures/M02_audit.svg|16,743|byte_preservation_only|
|artifacts/figures/M02_audit_source.csv|2,904|byte_preservation_only|
|artifacts/figures/M02_figure_qa.json|984|byte_preservation_only|
|artifacts/validation/01_label_admission.json|1,348|byte_preservation_only|
|artifacts/validation/01_native_frequency.csv|3,952|byte_preservation_only|
|artifacts/validation/01_technical_quality.csv|5,778|byte_preservation_only|
|artifacts/validation/02_scale_comparison.csv|2,918|byte_preservation_only|
|artifacts/validation/02_scale_decision.json|1,105|byte_preservation_only|
|configs/archive_sensitivity.json|2,216|new_or_changed_archive_stage|
|configs/experiment_protocol.json|9,068|byte_preservation_only|
|configs/model_candidates.json|3,020|byte_preservation_only|
|configs/module_contracts.json|19,072|byte_preservation_only|
|configs/study_design.json|4,460|byte_preservation_only|
|plan and report/02_模块输出物与验收契约.md|17,802|byte_preservation_only|
|plan and report/04_第二章大纲与2.3研究方案_v3_20261020.md|39,660|byte_preservation_only|
|PROJECT_STRUCTURE.md|10,512|new_or_changed_archive_stage|
|pyproject.toml|519|new_or_changed_archive_stage|
|README.md|4,974|new_or_changed_archive_stage|
|reports/ARCHIVE_SENSITIVITY_阶段复核.md|5,048|new_or_changed_archive_stage|
|reports/GITHUB_SYNC_PROPOSAL.md|9,858|new_or_changed_archive_stage|
|reports/M01_执行报告.md|5,757|byte_preservation_only|
|reports/M02_后续科学准入建议.md|3,938|new_or_changed_archive_stage|
|reports/M02_执行报告.md|9,838|new_or_changed_archive_stage|
|reports/M03_执行报告.md|2,996|new_or_changed_archive_stage|
|reports/M04_执行报告.md|6,581|new_or_changed_archive_stage|
|reports/M05_执行报告.md|4,932|new_or_changed_archive_stage|
|reports/M06_执行报告.md|3,141|new_or_changed_archive_stage|
|reports/M07_执行报告.md|19,391|new_or_changed_archive_stage|
|reports/M08_执行报告.md|2,827|new_or_changed_archive_stage|
|reports/M09_执行报告.md|3,177|new_or_changed_archive_stage|
|reports/M10_执行报告.md|1,034|byte_preservation_only|
|reports/M11_执行报告.md|3,988|new_or_changed_archive_stage|
|reports/M12_执行报告.md|1,035|byte_preservation_only|
|reports/PROJECT_PROGRESS.md|3,553|new_or_changed_archive_stage|
|run_archive_sensitivity.py|305|new_or_changed_archive_stage|
|run_manifest/archive_execution_verification.json|979|new_or_changed_archive_stage|
|run_manifest/archive_figure_preflight.json|2,667|new_or_changed_archive_stage|
|run_manifest/archive_figure_review.json|962|new_or_changed_archive_stage|
|run_manifest/archive_regression.log|5,114|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T143451_066150Z_archive/environment.json|190|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T143451_066150Z_archive/error.log|1,763|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T143451_066150Z_archive/M02_record.json|6,671|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T143451_066150Z_archive/M02_执行报告.md|9,596|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T143451_066150Z_archive/M03_record.json|4,574|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T143451_066150Z_archive/M03_执行报告.md|2,763|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T143451_066150Z_archive/M04_record.json|10,417|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T143451_066150Z_archive/M04_执行报告.md|6,276|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T143451_066150Z_archive/M05_record.json|7,651|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T143451_066150Z_archive/M05_执行报告.md|4,663|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T143451_066150Z_archive/M06_record.json|4,801|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T143451_066150Z_archive/M06_执行报告.md|2,905|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T143451_066150Z_archive/M07_failure_supplement.json|4,408|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T143451_066150Z_archive/manifest.json|36,921|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T143451_066150Z_archive/source_snapshot/configs/archive_sensitivity.json|2,216|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T143451_066150Z_archive/source_snapshot/configs/experiment_protocol.json|9,068|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T143451_066150Z_archive/source_snapshot/configs/model_candidates.json|3,020|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T143451_066150Z_archive/source_snapshot/configs/module_contracts.json|19,072|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T143451_066150Z_archive/source_snapshot/configs/study_design.json|4,460|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T143451_066150Z_archive/source_snapshot/src/project2_synthesis/__init__.py|106|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T143451_066150Z_archive/source_snapshot/src/project2_synthesis/archive_sensitivity/__init__.py|81|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T143451_066150Z_archive/source_snapshot/src/project2_synthesis/archive_sensitivity/figures.py|4,440|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T143451_066150Z_archive/source_snapshot/src/project2_synthesis/archive_sensitivity/numerics.py|9,612|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T143451_066150Z_archive/source_snapshot/src/project2_synthesis/archive_sensitivity/reporting.py|3,354|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T143451_066150Z_archive/source_snapshot/src/project2_synthesis/archive_sensitivity/runner.py|28,320|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T143451_066150Z_archive/source_snapshot/src/project2_synthesis/cli.py|4,958|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T143451_066150Z_archive/source_snapshot/src/project2_synthesis/contracts.py|11,977|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T143451_066150Z_archive/source_snapshot/src/project2_synthesis/figures/audit_figures.py|5,369|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T143451_066150Z_archive/source_snapshot/src/project2_synthesis/intake/label_admission.py|882|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T143451_066150Z_archive/source_snapshot/src/project2_synthesis/intake/native_frequency.py|1,732|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T143451_066150Z_archive/source_snapshot/src/project2_synthesis/intake/source_audit.py|11,343|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T143451_066150Z_archive/source_snapshot/src/project2_synthesis/preparation/aggregation.py|3,939|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T143451_066150Z_archive/source_snapshot/src/project2_synthesis/preparation/scale_selection.py|9,789|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T143451_066150Z_archive/source_snapshot/src/project2_synthesis/preparation/splitting.py|1,625|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T143451_066150Z_archive/source_snapshot/src/project2_synthesis/runtime.py|11,349|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T143451_066150Z_archive/source_snapshot/tests/test_archive_sensitivity.py|8,114|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T143451_066150Z_archive/source_snapshot/tests/test_design_contracts.py|5,674|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T143451_066150Z_archive/source_snapshot/tests/test_intake_preparation.py|11,727|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T143451_066150Z_archive/tests.log|4,880|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T144227_611692Z_archive/environment.json|190|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T144227_611692Z_archive/M02_record.json|9,960|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T144227_611692Z_archive/M02_执行报告.md|9,826|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T144227_611692Z_archive/M03_record.json|7,863|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T144227_611692Z_archive/M03_执行报告.md|2,993|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T144227_611692Z_archive/M04_record.json|13,706|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T144227_611692Z_archive/M04_执行报告.md|6,506|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T144227_611692Z_archive/M05_record.json|10,940|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T144227_611692Z_archive/M05_执行报告.md|4,893|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T144227_611692Z_archive/M06_record.json|8,090|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T144227_611692Z_archive/M06_执行报告.md|3,135|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T144227_611692Z_archive/M07_record.json|34,426|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T144227_611692Z_archive/M07_执行报告.md|19,064|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T144227_611692Z_archive/M08_record.json|7,828|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T144227_611692Z_archive/M08_执行报告.md|2,824|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T144227_611692Z_archive/M09_record.json|8,363|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T144227_611692Z_archive/M09_执行报告.md|3,168|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T144227_611692Z_archive/M11_record.json|9,397|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T144227_611692Z_archive/M11_执行报告.md|3,718|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T144227_611692Z_archive/manifest.json|120,772|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T144227_611692Z_archive/source_snapshot/configs/archive_sensitivity.json|2,216|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T144227_611692Z_archive/source_snapshot/configs/experiment_protocol.json|9,068|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T144227_611692Z_archive/source_snapshot/configs/model_candidates.json|3,020|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T144227_611692Z_archive/source_snapshot/configs/module_contracts.json|19,072|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T144227_611692Z_archive/source_snapshot/configs/study_design.json|4,460|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T144227_611692Z_archive/source_snapshot/src/project2_synthesis/__init__.py|106|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T144227_611692Z_archive/source_snapshot/src/project2_synthesis/archive_sensitivity/__init__.py|81|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T144227_611692Z_archive/source_snapshot/src/project2_synthesis/archive_sensitivity/figures.py|4,440|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T144227_611692Z_archive/source_snapshot/src/project2_synthesis/archive_sensitivity/numerics.py|9,612|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T144227_611692Z_archive/source_snapshot/src/project2_synthesis/archive_sensitivity/reporting.py|3,604|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T144227_611692Z_archive/source_snapshot/src/project2_synthesis/archive_sensitivity/runner.py|33,264|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T144227_611692Z_archive/source_snapshot/src/project2_synthesis/cli.py|4,958|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T144227_611692Z_archive/source_snapshot/src/project2_synthesis/contracts.py|11,977|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T144227_611692Z_archive/source_snapshot/src/project2_synthesis/figures/audit_figures.py|5,369|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T144227_611692Z_archive/source_snapshot/src/project2_synthesis/intake/label_admission.py|882|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T144227_611692Z_archive/source_snapshot/src/project2_synthesis/intake/native_frequency.py|1,732|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T144227_611692Z_archive/source_snapshot/src/project2_synthesis/intake/source_audit.py|11,343|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T144227_611692Z_archive/source_snapshot/src/project2_synthesis/preparation/aggregation.py|3,939|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T144227_611692Z_archive/source_snapshot/src/project2_synthesis/preparation/scale_selection.py|9,789|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T144227_611692Z_archive/source_snapshot/src/project2_synthesis/preparation/splitting.py|1,625|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T144227_611692Z_archive/source_snapshot/src/project2_synthesis/runtime.py|11,349|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T144227_611692Z_archive/source_snapshot/tests/test_archive_sensitivity.py|10,356|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T144227_611692Z_archive/source_snapshot/tests/test_design_contracts.py|5,674|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T144227_611692Z_archive/source_snapshot/tests/test_intake_preparation.py|11,727|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity/runs/20261020T144227_611692Z_archive/tests.log|4,991|new_or_changed_archive_stage|
|run_manifest/archive_sensitivity_states.json|158,772|new_or_changed_archive_stage|
|run_manifest/design_check.json|1,007|byte_preservation_only|
|run_manifest/execution_verification.json|933|byte_preservation_only|
|run_manifest/figure_review.json|1,119|byte_preservation_only|
|run_manifest/figure_source_preflight.json|2,661|byte_preservation_only|
|run_manifest/git_byte_preservation_review.json|17,120|new_or_changed_archive_stage|
|run_manifest/git_sync_M01_M02.json|600|new_or_changed_archive_stage|
|run_manifest/module_states.json|15,435|byte_preservation_only|
|run_manifest/runs/20261020T134451_986499Z_M01/environment.json|233|byte_preservation_only|
|run_manifest/runs/20261020T134451_986499Z_M01/M01_执行报告.md|4,813|byte_preservation_only|
|run_manifest/runs/20261020T134451_986499Z_M01/manifest.json|6,621|byte_preservation_only|
|run_manifest/runs/20261020T134451_986499Z_M01/source_snapshot/configs/experiment_protocol.json|9,068|byte_preservation_only|
|run_manifest/runs/20261020T134451_986499Z_M01/source_snapshot/configs/model_candidates.json|3,020|byte_preservation_only|
|run_manifest/runs/20261020T134451_986499Z_M01/source_snapshot/configs/module_contracts.json|19,072|byte_preservation_only|
|run_manifest/runs/20261020T134451_986499Z_M01/source_snapshot/configs/study_design.json|4,460|byte_preservation_only|
|run_manifest/runs/20261020T134451_986499Z_M01/tests.log|3,323|byte_preservation_only|
|run_manifest/runs/20261020T134719_593878Z_M02/environment.json|233|byte_preservation_only|
|run_manifest/runs/20261020T134719_593878Z_M02/M02_执行报告.md|5,199|byte_preservation_only|
|run_manifest/runs/20261020T134719_593878Z_M02/manifest.json|7,045|byte_preservation_only|
|run_manifest/runs/20261020T134719_593878Z_M02/source_snapshot/configs/experiment_protocol.json|9,068|byte_preservation_only|
|run_manifest/runs/20261020T134719_593878Z_M02/source_snapshot/configs/model_candidates.json|3,020|byte_preservation_only|
|run_manifest/runs/20261020T134719_593878Z_M02/source_snapshot/configs/module_contracts.json|19,072|byte_preservation_only|
|run_manifest/runs/20261020T134719_593878Z_M02/source_snapshot/configs/study_design.json|4,460|byte_preservation_only|
|run_manifest/runs/20261020T134719_593878Z_M02/tests.log|3,323|byte_preservation_only|
|run_manifest/stage_regression.log|3,440|byte_preservation_only|
|src/project2_synthesis/archive_sensitivity/__init__.py|81|new_or_changed_archive_stage|
|src/project2_synthesis/archive_sensitivity/figures.py|4,440|new_or_changed_archive_stage|
|src/project2_synthesis/archive_sensitivity/numerics.py|9,612|new_or_changed_archive_stage|
|src/project2_synthesis/archive_sensitivity/reporting.py|4,725|new_or_changed_archive_stage|
|src/project2_synthesis/archive_sensitivity/runner.py|33,264|new_or_changed_archive_stage|
|src/project2_synthesis/dependence/README.md|549|byte_preservation_only|
|src/project2_synthesis/export/README.md|572|byte_preservation_only|
|src/project2_synthesis/figures/README.md|477|byte_preservation_only|
|src/project2_synthesis/intake/README.md|935|byte_preservation_only|
|src/project2_synthesis/margins/README.md|548|byte_preservation_only|
|src/project2_synthesis/physics/README.md|598|byte_preservation_only|
|src/project2_synthesis/preparation/README.md|1,079|byte_preservation_only|
|src/project2_synthesis/regimes/README.md|568|byte_preservation_only|
|src/project2_synthesis/release/README.md|498|byte_preservation_only|
|src/project2_synthesis/runtime.py|11,349|new_or_changed_archive_stage|
|src/project2_synthesis/synthesis/README.md|544|byte_preservation_only|
|src/project2_synthesis/temporal/README.md|578|byte_preservation_only|
|src/project2_synthesis/validation/README.md|965|byte_preservation_only|
|tests/test_archive_sensitivity.py|11,859|new_or_changed_archive_stage|
|tools/prepare_archive_sync_review.py|8,398|new_or_changed_archive_stage|
|tools/verify_archive_execution.py|14,843|new_or_changed_archive_stage|
