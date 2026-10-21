"""Validate the design or execute an explicitly supported local module."""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import importlib.metadata
from pathlib import Path
import platform
import traceback

from .contracts import validate_design


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-design", action="store_true")
    parser.add_argument("--stage", choices=["M01", "M02"], help="M01 intake or M02 development archive diagnostics")
    parser.add_argument("--reason", help="Required on module reruns; recorded in its history")
    args = parser.parse_args(argv)
    if args.stage and args.check_design:
        parser.error("Use either --check-design or --stage, not both.")
    if not args.check_design and not args.stage:
        parser.print_help()
        return 2
    root = Path(__file__).resolve().parents[2]
    paths = [root / "configs" / f"{name}.json" for name in
             ("study_design", "module_contracts", "model_candidates", "experiment_protocol")]
    try:
        study, contracts, candidates, protocol = [json.loads(p.read_text(encoding="utf-8")) for p in paths]
        check = validate_design(study, contracts, root, protocol=protocol, candidates=candidates)
    except (OSError, ValueError) as exc:
        print(json.dumps({"mode": "design_check_only", "error": str(exc)}, ensure_ascii=False))
        return 1
    if args.stage:
        if not check.ok:
            print(json.dumps({"status": "FAIL", "errors": check.errors}, ensure_ascii=False))
            return 1
        states_path = root / "run_manifest/module_states.json"
        if states_path.exists() and args.stage in json.loads(states_path.read_text(encoding="utf-8")) and not args.reason:
            parser.error("A rerun needs --reason to preserve the reason for changed/repeated results.")
        from .runtime import initialize, publish, run_tests, write_json
        ctx = initialize(root, args.stage)
        tests = run_tests(root, ctx.run_dir)
        try:
            write_json(ctx.run_dir / "environment.json", {
                "python": platform.python_version(), "platform": platform.platform(),
                "packages": {name: importlib.metadata.version(name) for name in
                             ("numpy", "pandas", "pyarrow", "matplotlib")},
                "installation_performed": False})
            if tests["status"] != "PASS":
                raise RuntimeError("Pre-execution tests failed; inspect tests.log.")
            if args.stage == "M01":
                from .intake.source_audit import run_intake
                result = run_intake(ctx)
            else:
                from .preparation.scale_selection import run_preparation
                result = run_preparation(ctx)
            from .figures.audit_figures import plot_audit
            plot_audit(ctx, args.stage)
            result["figure_note"] = ("实际档案诊断图，含源 CSV、可编辑 SVG/PDF 和 PNG；"
                                     "不作为原生频率、主步长、事件或生成质量已通过的证据。")
        except Exception as exc:
            (ctx.run_dir / "error.log").write_text(traceback.format_exc(), encoding="utf-8")
            result = {"status": "FAIL", "objective": "执行请求的模块并保留失败原因。",
                      "metrics": {"error_type": type(exc).__name__, "error": str(exc)},
                      "limitations": ["此次运行失败；临时产物未发布。既有结果可能陈旧，应检查运行历史。"],
                      "next": [f"核查 run_manifest/runs/{ctx.run_id}/error.log 后修复重跑。"]}
        result["change_reason"] = args.reason or "首次实际执行"
        publish(ctx, args.stage, result, tests)
        print(json.dumps({"run_id": ctx.run_id, "module": args.stage, "status": result["status"],
                          "metrics": result.get("metrics"), "report": f"reports/{args.stage}_执行报告.md"},
                         ensure_ascii=False, indent=2))
        return 1 if result["status"] == "FAIL" else 0
    report = {
        "mode": "design_check_only", "algorithms_executed": False,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "design_structure_ok": check.ok, **asdict(check),
        "scientific_readiness": "main_step_and_model_admission_pending; see_module_reports_for_execution",
        "config_sha256": {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
    }
    dest = root / "run_manifest" / "design_check.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if check.ok else 1
