"""Append limited-use evidence to the existing module reports, never promote gates."""
from __future__ import annotations

import json
from pathlib import Path


MARKER = "\n## 已授权档案敏感性支线"


def append_archive_reports(root: Path) -> None:
    path = root / "run_manifest/archive_sensitivity_states.json"
    if not path.exists():
        return
    states = json.loads(path.read_text(encoding="utf-8"))
    rows = []
    for stage, history in sorted(states.items()):
        latest = history[-1]
        report = root / f"reports/{stage}_执行报告.md"
        base = report.read_text(encoding="utf-8").split(MARKER)[0]
        addition = (MARKER + f"\n\n支线技术执行 **{latest['status']}**；正式模型准入仍 PENDING，原生信息 UNKNOWN。"
                    f"运行 `{latest['run_id']}`；用途 `archive_sensitivity`。\n\n")
        headings = ["研究目标与执行内容", "方法、参数及配置版本", "输入数据与质量", "实际结果与关键指标",
                    "输出文件与图表", "测试、消融与验收", "科学风险与局限", "下一步"]
        bodies = [latest["objective"], latest["method"], latest["input"],
                  "```json\n" + json.dumps(latest["metrics"], ensure_ascii=False, indent=2) + "\n```",
                  "\n".join(f"- [{p}](../{p})" for p in latest["outputs"]),
                  "技术检查和预执行测试见当次 manifest/tests.log；未进行正式科学验收或 E1–E3。",
                  latest["limitations"], latest["next"]]
        for i, (heading, body) in enumerate(zip(headings, bodies), 1):
            addition += f"### 支线 {i}. {heading}\n\n{body}\n\n"
        if stage == "M11" and (root / "run_manifest/archive_figure_review.json").exists():
            review = json.loads((root / "run_manifest/archive_figure_review.json").read_text(encoding="utf-8"))
            if review.get("run_id") == latest["run_id"]:
                addition += "人工图表复核追加：PASS；生成时PENDING记录保留。依据见 [archive_figure_review.json](../run_manifest/archive_figure_review.json)。本模块仅完成档案原型图，正式F1–F8证据尚未齐备，阶段仍为PARTIAL。\n\n"
        addition += "### 支线历史\n\n|运行|技术状态|不可变记录|\n|---|---|---|\n"
        for item in history:
            addition += f"|{item['run_id']}|{item['status']}|[记录](../{item['record']})|\n"
        report.write_text(base + addition, encoding="utf-8")
        rows.append(f"|{stage}|{latest['status']}|原型已运行，正式准入未通过|[报告]({stage}_执行报告.md)|")
    progress = root / "reports/PROJECT_PROGRESS.md"
    base = progress.read_text(encoding="utf-8").split(MARKER)[0]
    base = base.replace("，尚未授权/执行。", "，用户已于2026-10-20明确授权；实际支线状态见下表。")
    base = base.replace("，等待明确确认。", "；M01/M02批准清单已执行，后续新增变更另行审阅。")
    base = base.replace("下一步：取得可核实的观测支持或经用户确认的有限用途研究协议后，完成主步长准入。",
                        "下一步：继续已授权档案支线并补齐可核实观测支持；主步长准入仍需原生/事件/负荷证据。")
    base = base.replace("未拟合生成器、未运行 SUMO 或增强实验", "正式主链尚未拟合；档案支线另列，未运行 SUMO 或增强实验")
    receipt = root / "run_manifest/git_sync_M01_M02.json"
    if receipt.exists():
        git = json.loads(receipt.read_text(encoding="utf-8"))
        base = base.replace("GitHub：尚未 commit、push 或创建 PR。", f"GitHub：已按批准清单提交并推送 M01/M02，commit `{git['commit'][:8]}`；无 PR 或合并。后续新增文件尚未上传。")
    addition = MARKER + "\n\n用户于 2026-10-20 明确授权。仅开发集 Q–COD/T；三尺度平行，不批准主步长。\n\n"
    addition += "|模块|支线技术执行|正式主链|证据|\n|---|---|---|---|\n" + "\n".join(rows)
    addition += "\n\n技术 PASS 仅表示该步实际运行和数值检查完成，不等于统计充分、事件保真或下游任务通过。"
    addition += "所有原型选项均展示，尚未选择正式变换、ARMA 阶数、Copula、时间尺度或科学阈值；验证集与终端测试未打开。\n"
    addition += "\n本阶段结论、物理缺陷与尺度比较限制见 [ARCHIVE_SENSITIVITY_阶段复核](ARCHIVE_SENSITIVITY_阶段复核.md)。新增代码/报告/汇总结果及字节保留修复尚未上传，见 [第二阶段Git审阅清单](GITHUB_ARCHIVE_SYNC_PROPOSAL.md)。\n"
    progress.write_text(base + addition, encoding="utf-8")
