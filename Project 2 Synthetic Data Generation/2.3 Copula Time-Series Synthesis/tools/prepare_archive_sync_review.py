"""Build a second-stage exact whitelist, without Git mutations or uploads."""
from __future__ import annotations

import csv
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from project2_synthesis.runtime import sha256, write_json


def main() -> None:
    prefix = subprocess.check_output(["git", "rev-parse", "--show-prefix"], cwd=ROOT, text=True).strip()
    repo = Path(subprocess.check_output(["git", "rev-parse", "--show-toplevel"], cwd=ROOT, text=True).strip())
    changed = subprocess.check_output(["git", "diff", "--name-only", "-z", "--", prefix], cwd=repo)
    files = {repo / name.decode("utf-8") for name in changed.split(b"\0") if name}
    byte_review = json.loads((ROOT / "run_manifest/git_byte_preservation_review.json").read_text(encoding="utf-8"))
    # Git's stat cache need not show conversion-only differences until renormalize.
    files.update(ROOT / item["path"] for item in byte_review["files"])
    for rel in [".gitattributes", "configs/archive_sensitivity.json", "run_archive_sensitivity.py", "tests/test_archive_sensitivity.py",
                "run_manifest/archive_sensitivity_states.json", "run_manifest/archive_execution_verification.json",
                "run_manifest/archive_regression.log", "run_manifest/archive_figure_preflight.json", "run_manifest/archive_figure_review.json",
                "run_manifest/git_sync_M01_M02.json", "reports/ARCHIVE_SENSITIVITY_阶段复核.md",
                "run_manifest/git_byte_preservation_review.json",
                "artifacts/archive_sensitivity/DATASET_CARD.md"]:
        files.add(ROOT / rel)
    files.update((ROOT / "src/project2_synthesis/archive_sensitivity").glob("*.py"))
    files.update((ROOT / "tools").glob("*archive*.py"))
    for directory in ["validation", "figures"]:
        files.update((ROOT / "artifacts/archive_sensitivity" / directory).glob("*"))
    for run_dir in (ROOT / "run_manifest/archive_sensitivity/runs").iterdir():
        if run_dir.is_dir():
            files.update(p for p in run_dir.iterdir() if p.is_file() and p.suffix in {".json", ".md", ".log"})
            files.update(p for p in (run_dir / "source_snapshot").rglob("*") if p.is_file() and p.suffix in {".py", ".json"})
    with (ROOT / "reports/GITHUB_SYNC_FILE_LIST.csv").open(encoding="utf-8-sig", newline="") as stream:
        old_hashes = {row["path"]: row["sha256"] for row in csv.DictReader(stream)}
    secret = re.compile(r"AKIA[0-9A-Z]{16}|ghp_[A-Za-z0-9]{30,}|sk-[A-Za-z0-9]{32,}|-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")
    rows = []
    for path in sorted(files):
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT).as_posix()
        if relative.startswith("reports/GITHUB_ARCHIVE_"):
            continue
        if path.suffix.lower() in {".parquet", ".xlsx", ".docx"} or "/raw data/" in path.as_posix():
            raise ValueError(f"Observation or unrelated file in whitelist: {relative}")
        if path.stat().st_size > 5 * 1024 * 1024:
            raise ValueError(f"Large file in whitelist: {relative}")
        if path.suffix.lower() in {".py", ".json", ".md", ".csv", ".svg", ".log", ".txt", ".toml"}:
            if secret.search(path.read_text(encoding="utf-8-sig")):
                raise ValueError(f"Possible credential pattern in {relative}; value not printed")
        digest = sha256(path)
        kind = "new_or_changed_archive_stage"
        if old_hashes.get(relative) == digest:
            blob = subprocess.check_output(["git", "cat-file", "blob", "HEAD:" + prefix + relative], cwd=repo)
            raw = path.read_bytes()
            if raw != blob and raw.replace(b"\r\n", b"\n") == blob:
                kind = "byte_preservation_only"
        rows.append({"path": relative, "bytes": path.stat().st_size, "sha256": digest, "change_kind": kind})
    byte_only = sum(row["change_kind"] == "byte_preservation_only" for row in rows)
    if byte_only != byte_review["audit_count"]:
        raise ValueError("Byte-preservation repair list changed; rerun its audit before requesting approval")
    csv_path = ROOT / "reports/GITHUB_ARCHIVE_FILE_LIST.csv"
    with csv_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["path", "bytes", "sha256", "change_kind"])
        writer.writeheader()
        writer.writerows(rows)
    extras = ["reports/GITHUB_ARCHIVE_SYNC_PROPOSAL.md", "reports/GITHUB_ARCHIVE_FILE_LIST.csv", "reports/GITHUB_ARCHIVE_PATHS.txt"]
    (ROOT / extras[2]).write_text("\n".join([prefix + row["path"] for row in rows] + [prefix + path for path in extras]) + "\n", encoding="utf-8")
    verification = json.loads((ROOT / "run_manifest/archive_execution_verification.json").read_text(encoding="utf-8"))
    match = re.search(r"Ran (\d+) tests", (ROOT / "run_manifest/archive_regression.log").read_text(encoding="utf-8-sig"))
    regression_tests = int(match.group(1)) if match else None
    table = "\n".join(f"|{r['path']}|{r['bytes']:,}|{r['change_kind']}|" for r in rows)
    proposal = ("# 已授权档案敏感性支线：第二阶段 Git 同步审阅（未获上传确认）\n\n"
                "此前118路径已按用户确认提交并推送，commit 4dd7ae38；本文件只提出后续提交，不延用此前上传授权。\n\n"
                "## 实际变更\n\n"
                "- 独立archive配置/入口，完整共同小时支持、K=1、可逆AR(0/1)、经验边际、独立/Gaussian/t、30日回顾条件合成。\n"
                f"- 12时间原型、24边际、36Copula、108轨迹、576滞后诊断；实际运行前49项、最新工程回归{regression_tests}项测试通过。数值/源文件复核PASS，科学准入PARTIAL。\n"
                "- 负Q8行、负COD3190行未修正；主步长null、原生信息UNKNOWN，未开启留出、氮、SUMO或E1–E3。\n"
                "- 260字符路径失败及SHA检查点恢复保留，恢复未重新拟合；逐模块报告/进度、图和源表已更新。\n\n"
                "## 精确字节保留修复\n\n"
                "首轮Git按自动CRLF规范化保存文本，与本地运行SHA不同；已核对为换行差异。新增仅本工程的.gitattributes，禁止换行转换，拟在下一次提交保留原件字节；不修改旧commit或重写历史。"
                f"本清单中{byte_only}个文件标为byte_preservation_only，当前本地SHA仍与原审阅清单一致，逻辑/数值未改。其他条目为本阶段内容或状态记录更新。\n\n"
                "## 上传范围与检查\n\n"
                f"{len(rows)}个带SHA文件，共{sum(r['bytes'] for r in rows):,} bytes；另含本说明及CSV/TXT管理文件3项。"
                "排除全部观测级Parquet、原始资料、经验边际的完整样本数组、其他大型拟合模型、文献/Word、缓存和临时文件。"
                "清单含厂站汇总指标、拟合相关/自由度和诊断图，需要用户对本清单明确确认。常见凭据特征未匹配，单文件均小于5MiB。\n\n"
                "## 拟执行操作\n\n"
                "确认后在codex/project2-m01-m02-audit分支追加一次commit并push至origin；不创建PR、不合并。"
                "拟提交消息：Add authorized archive sensitivity pilot and preserve audit bytes。"
                "仅按GITHUB_ARCHIVE_PATHS.txt暂存，再对该清单执行renormalize并逐文件比较暂存blob SHA与本地审阅SHA，全部一致后commit/push。未经确认不执行。\n\n"
                "## 阶段证据\n\n"
                f"运行{verification['run_id']}；技术验证见run_manifest/archive_execution_verification.json，"
                "科学讨论见reports/ARCHIVE_SENSITIVITY_阶段复核.md，图表人工复核见run_manifest/archive_figure_review.json。\n\n"
                "|拟提交路径（工程相对）|bytes|变更类型|\n|---|---:|---|\n" + table + "\n")
    (ROOT / extras[0]).write_text(proposal, encoding="utf-8")
    print(json.dumps({"hashed_files": len(rows), "additional_review_files": 3, "byte_preservation_only": byte_only,
                      "total_hashed_bytes": sum(row["bytes"] for row in rows), "git_mutations": False}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
