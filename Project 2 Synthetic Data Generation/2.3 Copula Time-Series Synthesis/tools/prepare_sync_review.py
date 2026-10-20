"""Prepare an exact local Git review whitelist; never stage, commit or upload."""
from __future__ import annotations

import csv
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from project2_synthesis.runtime import sha256, update_reports, write_json


def main() -> None:
    states = json.loads((ROOT / "run_manifest/module_states.json").read_text(encoding="utf-8"))
    contracts = json.loads((ROOT / "configs/module_contracts.json").read_text(encoding="utf-8"))
    update_reports(ROOT, contracts, states)
    summary = json.loads((ROOT / "run_manifest/execution_verification.json").read_text(encoding="utf-8"))
    qa = json.loads((ROOT / "run_manifest/figure_review.json").read_text(encoding="utf-8"))
    for stage in ["M01", "M02"]:
        require_ok = summary[stage]["status"] == "PASS" and qa[stage]["visual_review"] == "PASS"
        require_ok = require_ok and qa[stage]["reviewed_png_sha256"] == sha256(ROOT / f"artifacts/figures/{stage}_audit.png")
        if not require_ok:
            raise ValueError(f"Stage/figure review incomplete: {stage}")
        report = ROOT / f"reports/{stage}_执行报告.md"
        text = report.read_text(encoding="utf-8")
        text += ("\n## 阶段复核与工程更新\n\n"
                 "实际文件的独立复核通过，证据见 [execution_verification.json](../run_manifest/execution_verification.json)。"
                 "当前工程回归日志见 [stage_regression.log](../run_manifest/stage_regression.log)。"
                 "原运行日志及哈希匹配源码/配置快照保留；新增自动快照和重跑原因要求属于工程可追溯性更新，未改变本次数据计算或科研参数。\n\n"
                 "两图人工布局检查通过；绘图源码检查无 FAIL，PNG 未另导出 TIFF 的 WARN 已记录。"
                 "本轮用途为技术诊断，提供可编辑 SVG/PDF 与 600 dpi PNG；期刊最终投稿格式待主研究完成时核定。"
                 "图表复核见 [figure_review.json](../run_manifest/figure_review.json)。科学验收仍为 PARTIAL。\n")
        report.write_text(text, encoding="utf-8")
    progress = ROOT / "reports/PROJECT_PROGRESS.md"
    with progress.open("a", encoding="utf-8") as stream:
        stream.write("\n独立产物复核及图表检查已通过；[复核记录](../run_manifest/execution_verification.json)。"
                     "后续可审阅建议见 [M02_后续科学准入建议](M02_后续科学准入建议.md)，尚未授权/执行。"
                     "Git 操作范围与精确白名单见 [GITHUB_SYNC_PROPOSAL](GITHUB_SYNC_PROPOSAL.md)，等待明确确认。\n")
    files = {ROOT / p for p in [".gitignore", "README.md", "PROJECT_STRUCTURE.md", "pyproject.toml", "run_p23_pipeline.py",
             "plan and report/02_模块输出物与验收契约.md", "plan and report/04_第二章大纲与2.3研究方案_v3_20261020.md",
             "artifacts/README.md", "artifacts/data/01_input_audit.json"]}
    for folder, patterns in {"configs": ["*.json", "*.md"], "src": ["**/*.py", "**/*.md"],
                             "tests": ["*.py"], "tools": ["*.py"], "reports": ["*.md"],
                             "run_manifest": ["design_check.json", "module_states.json", "execution_verification.json",
                                              "figure_review.json", "figure_source_preflight.json", "stage_regression.log"],
                             "artifacts/validation": ["01_*.json", "01_*.csv", "02_*.json", "02_*.csv"],
                             "artifacts/figures": ["M01_*", "M02_*"]}.items():
        for pattern in patterns:
            files.update((ROOT / folder).glob(pattern))
    for stage in ["M01", "M02"]:
        run_dir = ROOT / "run_manifest/runs" / states[stage]["manifest"]["run_id"]
        files.update(run_dir / name for name in ["manifest.json", "tests.log", "environment.json", f"{stage}_执行报告.md"])
        files.update(path for path in (run_dir / "source_snapshot").rglob("*") if path.suffix in {".py", ".json", ".toml"})
    files = {p for p in files if p.is_file() and p.name != "GITHUB_SYNC_PROPOSAL.md"}
    suspicious, rows = [], []
    token_pattern = re.compile(r"AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{30,}|sk-[A-Za-z0-9]{32,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")
    for path in sorted(files):
        size = path.stat().st_size
        if size > 5 * 1024 * 1024:
            raise ValueError(f"Large file unexpectedly in whitelist: {path.relative_to(ROOT)}")
        if path.suffix.lower() in {".py", ".json", ".md", ".toml", ".csv", ".log", ".svg"}:
            for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
                if token_pattern.search(line):
                    suspicious.append({"path": path.relative_to(ROOT).as_posix(), "line": number})
        rows.append({"path": path.relative_to(ROOT).as_posix(), "bytes": size, "sha256": sha256(path)})
    if suspicious:
        write_json(ROOT / "run_manifest/sync_scan_findings.json", suspicious)
        raise ValueError("Possible secrets found; path/line only recorded, no secret values printed.")
    csv_path = ROOT / "reports/GITHUB_SYNC_FILE_LIST.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["path", "bytes", "sha256"])
        writer.writeheader()
        writer.writerows(rows)
    repo_relative = subprocess.run(["git", "rev-parse", "--show-prefix"], cwd=ROOT,
                                   capture_output=True, text=True, encoding="utf-8", check=True).stdout.strip()
    pathspec = ROOT / "reports/GITHUB_SYNC_PATHS.txt"
    approved_paths = [repo_relative + row["path"] for row in rows]
    approved_paths += [repo_relative + "reports/" + name for name in
                       ["GITHUB_SYNC_PROPOSAL.md", "GITHUB_SYNC_FILE_LIST.csv", "GITHUB_SYNC_PATHS.txt"]]
    pathspec.write_text("\n".join(approved_paths) + "\n", encoding="utf-8")
    branch = subprocess.run(["git", "branch", "--show-current"], cwd=ROOT, capture_output=True,
                            text=True, encoding="utf-8", check=True).stdout.strip()
    table = "\n".join(f"|{row['path']}|{row['bytes']:,}|" for row in rows)
    proposal = ("# M01/M02 阶段 GitHub 同步审阅清单（待用户确认）\n\n"
                f"生成于 {datetime.now(timezone.utc).isoformat()}。当前分支 `{branch}`。未执行暂存、commit、push、PR 或合并。\n\n"
                "Project2 当前整体尚未被 Git 跟踪，因此本次拟纳入文件包含必要的最终设计基线，以及本轮实现/报告/实际小型结果。"
                "既有最终方案正文未修改，其 SHA 与 M01/M02 运行记录一致。\n\n"
                "## 变更内容\n\n"
                "- M01：只读两源审计、逐单元原值/来源、技术标记、开发集常数段诊断、标签准入。\n"
                "- M02：开发集双视图、共同支持负荷、连续块、5/15/60 档案诊断；主步长仍 null。\n"
                "- 工程：阶段入口/测试、源码配置快照、重跑原因与不可覆盖运行记录；12 份模块报告及总进度。\n"
                "- 实际结果：364 天/524160 行，3669120 单元标记；最大数值重算误差 4.88e-16；两模块 PARTIAL。\n\n"
                "## 测试与审查\n\n"
                "两次实际执行前各 33 项测试通过；最新工程回归结果见 run_manifest/stage_regression.log。独立复核、图表人工检查通过。"
                "白名单进行了 5 MiB 大小检查和常见凭据特征扫描，无匹配；该扫描不是对所有形式敏感信息的绝对保证。"
                "清单含厂站汇总质量/覆盖指标与诊断图，属于本次需要明确确认的上传内容。\n\n"
                "## 拟执行操作（尚未授权）\n\n"
                "确认后拟创建 `codex/project2-m01-m02-audit` 分支，严格按白名单提交一次，并推送该分支到 origin。"
                "拟提交消息：`Implement Project2 M01 intake and M02 archive diagnostics`。不创建 PR、不合并。"
                "如用户只批准本地 commit 或要求删去部分结果，应据此缩小操作范围。\n\n"
                "## 文件范围\n\n"
                f"下表 {len(rows)} 个文件，共 {sum(x['bytes'] for x in rows):,} bytes；另含本审阅说明、CSV SHA 清单和 TXT 路径清单三项管理文件（不对其自引用求 SHA）。"
                "CSV 逐文件保存 SHA256，TXT 使用仓库根相对路径。\n\n"
                "排除：全部原始 CSV/XLSX、观测级 Parquet、运行快照中的观测级产物、文献全文/知识总库、Word 素材、缓存和临时文件。"
                "不能使用 `git add .`。\n\n|拟提交路径（2.3 工程相对）|bytes|\n|---|---:|\n" + table + "\n")
    (ROOT / "reports/GITHUB_SYNC_PROPOSAL.md").write_text(proposal, encoding="utf-8")
    print(json.dumps({"files_with_sha": len(rows), "additional_review_files": 3,
                      "total_hashed_bytes": sum(x["bytes"] for x in rows), "credential_pattern_matches": 0,
                      "git_mutations_performed": False}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
