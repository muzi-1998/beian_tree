# Project2 / 2.3 Copula—时序联合合成

2026-10-20，按 v3 最终研究设计执行。先读[最终大纲与方案](plan%20and%20report/04_第二章大纲与2.3研究方案_v3_20261020.md)、[Python目录](PROJECT_STRUCTURE.md)和[模块输出契约](plan%20and%20report/02_模块输出物与验收契约.md)。M01 来源审计与 M02 开发集档案诊断已实现；主步长和生成模型尚未准入。实际状态及运行证据见 [PROJECT_PROGRESS](reports/PROJECT_PROGRESS.md)，不以代码存在替代科学验证。

正式规则：原生审计后比较5/15/60 min，1 min只存档且需双门准入；同时保存TW/FW及共同支持V/L；E1质量—覆盖、E2受控动态/配对响应、E3冻结来源/比例曲线分别验证；EVT四层执行，EQD有触发条件，MT-AD等不进主线。匹配容差有开发建议值，最终值未冻结，不允许pending变passed。

M09内部进行匹配、准备临时SUMO输入及实验，M10负责最终导出，避免循环依赖。区域ERA5是代理；操作单位、分馏、真实出口标签和SUMO仍有准入项。可以启动2.3.1与Q–COD MVP开发，无需等待全部扩展资料。

旧01方案、03 Word及05/07公式素材、06运行补丁与knowledge文献/图谱保留；其中与本最终稿不一致的旧执行要求已被替代，本轮未重写这些素材或原始数据。原文证据入口见knowledge/12、18A–C，历史执行审查见19。

在本目录运行设计检查（非模型实验）：

```powershell
& 'D:\000_APP\020_APP_code\05_python3.10\python.exe' -X utf8 run_p23_pipeline.py --check-design
& 'D:\000_APP\020_APP_code\05_python3.10\python.exe' -X utf8 -m unittest discover -s tests -v
& 'D:\000_APP\020_APP_code\05_python3.10\python.exe' -X utf8 run_p23_pipeline.py --stage M01
& 'D:\000_APP\020_APP_code\05_python3.10\python.exe' -X utf8 run_p23_pipeline.py --stage M02
```

执行环境的精确包版本登记于 pyproject.toml 的 execution 可选依赖；本次使用现有环境，未安装软件。每阶段先执行测试，再写不可变 run_manifest/runs/<run_id>/ 及当前报告，并保存源码/测试/配置快照。M02 会核验 M01 产物与配置 SHA；输入改变须重跑上游。重跑需增加 `--reason '具体修改或验证原因'`，历史记录持续保留。

用户已确认暂无可核实的原生/SCADA 元数据。M01 的 observed/held/imputed 与 available_at 保持空值，refresh_status=UNKNOWN。M02 的名义 1 min 求积不代表原生测量支持；02_model_frame 是 model_admitted=false 的开发集技术档案。5/15/60 min 只产生候选诊断，main_step_minutes 仍为 null。禁止将该档案直接作为已准入训练集。

reports 下保留一模块一报告及总进度；未执行模块标 PENDING。run_manifest/module_states.json 是实际运行状态来源；module_contracts 的 planned_not_produced 字段保留设计时声明，不用作当前执行判断。任何正式拟合必须读取准入状态，不能仅检查文件是否存在。

GitHub 同步必须先展示拟提交文件清单并获得用户明确确认。原始数据、逐时点 Parquet、临时文件及运行快照中的观测级结果不在默认上传范围；小型日志、配置与源码快照可列入审阅白名单。不执行自动 commit、push、PR 或合并。
