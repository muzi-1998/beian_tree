"""Local execution provenance and one-report-per-module bookkeeping."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
from typing import Any


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


@dataclass
class Execution:
    root: Path
    run_id: str
    run_dir: Path
    study: dict[str, Any]
    contracts: dict[str, Any]
    config_hashes: dict[str, str]

    @property
    def output_dir(self) -> Path:
        return self.run_dir / "artifacts"

    def output(self, relative: str) -> Path:
        path = self.output_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def metadata(self) -> dict[str, str]:
        return {"run_id": self.run_id,
                "protocol_sha256": self.config_hashes["configs/experiment_protocol.json"],
                "study_sha256": self.config_hashes["configs/study_design.json"]}


def initialize(root: Path, stage: str) -> Execution:
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ") + "_" + stage
    run_dir = root / "run_manifest" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    hashes = {str(p.relative_to(root)).replace("\\", "/"): sha256(p)
              for p in sorted((root / "configs").glob("*.json"))}
    return Execution(root, run_id, run_dir,
                     json.loads((root / "configs/study_design.json").read_text(encoding="utf-8")),
                     json.loads((root / "configs/module_contracts.json").read_text(encoding="utf-8")), hashes)


def run_tests(root: Path, run_dir: Path) -> dict[str, Any]:
    command = [sys.executable, "-X", "utf8", "-m", "unittest", "discover", "-s", "tests", "-v"]
    result = subprocess.run(command, cwd=root, capture_output=True, text=True, encoding="utf-8", check=False)
    (run_dir / "tests.log").write_text(result.stdout + result.stderr, encoding="utf-8")
    return {"status": "PASS" if result.returncode == 0 else "FAIL", "returncode": result.returncode,
            "command": command, "log": str((run_dir / "tests.log").relative_to(root)).replace("\\", "/")}


def publish(ctx: Execution, stage: str, result: dict[str, Any], tests: dict[str, Any]) -> None:
    """Publish only complete outputs; retain immutable per-run copies and reports."""
    outputs = []
    for path in sorted(ctx.output_dir.rglob("*")) if ctx.output_dir.exists() else []:
        if path.is_file():
            rel = path.relative_to(ctx.output_dir)
            outputs.append({"path": "artifacts/" + rel.as_posix(), "bytes": path.stat().st_size,
                            "sha256": sha256(path)})
    manifest = {"run_id": ctx.run_id, "module": stage, "result": result, "tests": tests,
                "config_sha256": ctx.config_hashes, "outputs": outputs,
                "code_sha256": {p.relative_to(ctx.root).as_posix(): sha256(p)
                                for p in sorted((ctx.root / "src").rglob("*.py"))},
                "final_plan_sha256": sha256(ctx.root / "plan and report/04_第二章大纲与2.3研究方案_v3_20261020.md"),
                "timestamp_utc": datetime.now(timezone.utc).isoformat()}
    write_json(ctx.run_dir / "manifest.json", manifest)
    if result["status"] != "FAIL":
        for item in outputs:
            rel = Path(item["path"]).relative_to("artifacts")
            target = ctx.root / "artifacts" / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ctx.output_dir / rel, target)
    state_path = ctx.root / "run_manifest/module_states.json"
    states = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}
    history = states.get(stage, {}).get("history", [])
    history.append({"run_id": ctx.run_id, "status": result["status"],
                    "reason": result.get("change_reason", "首次实际执行"),
                    "manifest": (ctx.run_dir / "manifest.json").relative_to(ctx.root).as_posix()})
    states[stage] = {"manifest": manifest, "history": history}
    write_json(state_path, states)
    update_reports(ctx.root, ctx.contracts, states)
    current = ctx.root / "reports" / f"{stage}_执行报告.md"
    shutil.copy2(current, ctx.run_dir / f"{stage}_执行报告.md")


def update_reports(root: Path, contracts: dict[str, Any], states: dict[str, Any]) -> None:
    reports = root / "reports"
    reports.mkdir(exist_ok=True)
    rows = []
    for module in contracts["modules"]:
        stage = module["id"]
        state = states.get(stage)
        if state:
            manifest = state["manifest"]
            result, tests = manifest["result"], manifest["tests"]
            status = result["status"]
            metrics = "\n".join(f"|{key}|{json.dumps(value, ensure_ascii=False)}|" for key, value in result.get("metrics", {}).items())
            files = "\n".join(f"- [{x['path']}](../{x['path']}) — {x['bytes']:,} bytes，SHA256 `{x['sha256']}`" for x in manifest["outputs"])
            history = "\n".join(f"|{x['run_id']}|{x['status']}|{x['reason']}|[manifest](../{x['manifest']})|" for x in state["history"])
            text = (f"# {stage} {module['name']} 执行报告\n\n当前阶段验收：**{status}**；运行 `{manifest['run_id']}`。\n\n"
                    f"## 1. 研究目标与执行内容\n\n{result.get('objective', '')}\n\n"
                    f"## 2. 方法、参数与配置版本\n\n{result.get('methods', '')}\n\n"
                    f"配置 SHA256 与全部代码 SHA 见[本次运行清单](../run_manifest/runs/{manifest['run_id']}/manifest.json)。"
                    f"最终方案 SHA256：`{manifest['final_plan_sha256']}`。\n\n"
                    f"## 3. 输入数据与质量情况\n\n{result.get('inputs', '')}\n\n"
                    f"## 4. 实际运行结果与关键指标\n\n|指标|实测或计算结果|\n|---|---|\n{metrics}\n\n"
                    f"## 5. 输出文件与论文图表\n\n{files or '未发布结果文件。'}\n\n"
                    f"图表解释：{result.get('figure_note', '无已验证论文结论图。')}\n\n"
                    f"## 6. 测试、验证、消融及验收\n\n测试：**{tests['status']}**；[完整日志](../{tests['log']})。\n\n"
                    + "\n".join(f"- {x['status']}：{x['name']}；{x['reason']}" for x in result.get("checks", []))
                    + "\n\n消融、生成质量和 SUMO 响应尚未执行。技术恒等式通过不代表统计或过程验证通过。\n\n"
                    + "## 7. 异常问题、科学性风险与局限\n\n" + "\n".join(f"- {x}" for x in result.get("limitations", []))
                    + "\n\n## 8. 待解决事项、建议与下一步\n\n" + "\n".join(f"- {x}" for x in result.get("next", []))
                    + f"\n\n## 运行与修改历史\n\n|运行|状态|原因|不可变记录|\n|---|---|---|---|\n{history}\n")
        else:
            status = "PENDING"
            text = f"# {stage} {module['name']} 执行报告\n\n当前阶段验收：**PENDING**。此文件是进度记录，不是运行或验证结果。\n\n"
            contents = ["目标按最终方案与模块契约执行；本模块尚未运行。",
                        "未拟合、未冻结新参数；候选与实验规则仍以 configs 为准。",
                        "尚未接收通过相应用途准入的上游输入。",
                        "无实测结果、无效果指标。",
                        "尚无本模块实际产物；不得将计划路径当作已完成文件。",
                        "PENDING；尚无本模块算法行为、消融或科学验证结果。",
                        "上游原生信息、主步长及相关用途准入未完成。",
                        "等待上游科学门；方法、核心参数或验收标准的实质变更须先征得用户确认。"]
            headings = ["研究目标与执行内容", "方法、参数与配置版本", "输入数据与质量情况", "实际运行结果与关键指标",
                        "输出文件与论文图表", "测试、验证、消融及验收", "异常问题、科学性风险与局限", "待解决事项、建议与下一步"]
            text += "\n\n".join(f"## {i}. {h}\n\n{c}" for i, (h, c) in enumerate(zip(headings, contents), 1)) + "\n"
        (reports / f"{stage}_执行报告.md").write_text(text, encoding="utf-8")
        rows.append(f"|{stage}|{module['name']}|{status}|[报告]({stage}_执行报告.md)|")
    progress = ("# Project2 项目总进度\n\n采用一模块一报告；状态区分技术执行和科学准入。\n\n"
                "|模块|职责|阶段验收|证据|\n|---|---|---|---|\n" + "\n".join(rows)
                + "\n\n已开展：只读来源审计与开发集候选尺度档案诊断。未批准主步长；未拟合生成器、未运行 SUMO 或增强实验。\n\n"
                "原生周期及 SCADA 元数据：用户确认暂无可核实资料，保持 UNKNOWN。不得将值重复判为保持，也不得将行数视为独立新测量数。\n\n"
                "下一步：取得可核实的观测支持或经用户确认的有限用途研究协议后，完成主步长准入。"
                "M03–M12 正式主链依赖相应用途门；可先进行代码和契约准备，但不能生成正式模型效果结论。\n\n"
                "GitHub：尚未 commit、push 或创建 PR。每阶段检查敏感/大文件并提交审阅清单，获得明确确认后才执行相应 Git 操作。\n")
    (reports / "PROJECT_PROGRESS.md").write_text(progress, encoding="utf-8")
