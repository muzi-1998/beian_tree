"""Execute the authorized development-only archive prototype, retaining failures."""
from __future__ import annotations

from datetime import datetime, timezone
import importlib.metadata
import json
from pathlib import Path
import shutil
import traceback

import numpy as np
import pandas as pd
from scipy import stats

from .numerics import (EmpiricalMargin, block_slices, design_matrix, draw_copula, fit_copulas,
                       fit_temporal, inverse_transform, lagged_correlation, reconstruct, transform)
from .reporting import append_archive_reports
from ..runtime import run_tests, sha256, write_json


class ArchiveRun:
    def __init__(self, root: Path):
        self.root = root
        self.config = json.loads((root / "configs/archive_sensitivity.json").read_text(encoding="utf-8"))
        self.study = json.loads((root / "configs/study_design.json").read_text(encoding="utf-8"))
        if (self.config["fit_split"] != "development" or self.config["open_validation"]
                or self.config["open_terminal_test"] or self.config["model_admitted"]
                or self.config["formal_main_step_minutes"] is not None or self.config["regime_K"] != 1
                or self.config["measurement_support"] != "UNKNOWN"
                or set(self.config["steps_minutes"]) != {5, 15, 60}):
            raise ValueError("Archive authorization scope violated")
        self.run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%fZ") + "_archive"
        self.run_dir = root / "run_manifest/archive_sensitivity/runs" / self.run_id
        self.run_dir.mkdir(parents=True, exist_ok=False)
        self.dest = self.run_dir / "artifacts/archive_sensitivity"
        self.dest.mkdir(parents=True)
        self.hashes = {}
        for path in list((root / "configs").glob("*.json")) + list((root / "src").rglob("*.py")) + list((root / "tests").glob("*.py")):
            rel = path.relative_to(root)
            target = self.run_dir / "source_snapshot" / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            self.hashes[rel.as_posix()] = sha256(path)
        self.tests = run_tests(root, self.run_dir)
        self.failures = []
        self.stage_records = []
        self.numeric_tolerance = self.study["numerical_invariants"]["relative_roundtrip_error_max"]
        write_json(self.run_dir / "environment.json", {"packages": {name: importlib.metadata.version(name)
                   for name in ["numpy", "pandas", "scipy", "pyarrow", "matplotlib"]}, "installed_new_packages": False})

    def path(self, rel: str) -> Path:
        path = self.dest / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def annotate(self, frame: pd.DataFrame) -> pd.DataFrame:
        frame = frame.copy()
        frame["run_id"] = self.run_id
        frame["purpose"] = "archive_sensitivity"
        frame["measurement_support"] = "UNKNOWN"
        frame["model_admitted"] = False
        frame["split"] = "development"
        return frame

    def record(self, stage: str, objective: str, method: str, metrics: dict, files: list[str], status: str = "PASS") -> None:
        relative_files = []
        output_hashes = {}
        for name in files:
            source = self.dest / name
            if not source.is_file():
                raise ValueError(f"Cannot declare missing output: {name}")
            target = self.root / "artifacts/archive_sensitivity" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            relative_files.append(target.relative_to(self.root).as_posix())
            output_hashes[name] = {"sha256": sha256(source), "bytes": source.stat().st_size}
        record_path = self.run_dir / f"{stage}_record.json"
        result = {"stage": stage, "run_id": self.run_id, "status": status, "objective": objective, "method": method,
                  "input": "已验证 SHA 的 M02 开发档案；Q/COD/T 同一完整日历小时支持。原生信息 UNKNOWN。",
                  "metrics": metrics, "outputs": relative_files, "output_hashes": output_hashes,
                  "limitations": "仅既有对齐档案的开发期描述；拟合/比较不是留出效果或真实事件证据。档案行数不是独立新测量数；T/日历是回顾性条件。",
                  "next": "展示全部已配置原型及失败；正式步长/阈值/模型选择仍待证据和确认，不启用氮、SUMO 或 E1–E3。",
                  "record": record_path.relative_to(self.root).as_posix(), "tests": self.tests,
                  "source_and_config_sha256": self.hashes, "scientific_admission": "PENDING"}
        write_json(record_path, result)
        states_path = self.root / "run_manifest/archive_sensitivity_states.json"
        states = json.loads(states_path.read_text(encoding="utf-8")) if states_path.exists() else {}
        states.setdefault(stage, []).append(result)
        write_json(states_path, states)
        append_archive_reports(self.root)
        self.stage_records.append(result)
        # Keep a stage-local report as executed, including correctly rooted links.
        report = (self.root / f"reports/{stage}_执行报告.md").read_text(encoding="utf-8")
        report = report.replace("../artifacts/archive_sensitivity/", "artifacts/archive_sensitivity/")
        (self.run_dir / f"{stage}_执行报告.md").write_text(report, encoding="utf-8")
        print(json.dumps({"stage": stage, "status": status, "metrics": metrics}, ensure_ascii=False), flush=True)


def prepare_support(run: ArchiveRun) -> dict[int, pd.DataFrame]:
    states = json.loads((run.root / "run_manifest/module_states.json").read_text(encoding="utf-8"))
    manifest = states["M02"]["manifest"]
    if manifest["result"]["status"] == "FAIL":
        raise ValueError("Failed formal intake/preparation cannot supply this prototype")
    entry = next(x for x in manifest["outputs"] if x["path"] == "artifacts/data/02_model_frame.parquet")
    source = run.root / entry["path"]
    if sha256(source) != entry["sha256"]:
        raise ValueError("M02 frame changed since its recorded run")
    frame = pd.read_parquet(source)
    if not frame["split"].eq("development").all() or not frame["native_refresh_status"].eq("UNKNOWN").all():
        raise ValueError("Non-development or mislabelled native support")
    frame = frame.set_index("timestamp").sort_index()
    good = frame["technical_support_Q_COD_T"]
    hour = frame.index.floor("h")
    sizes = good.groupby(hour).agg(["sum", "size"])
    complete_hours = sizes.index[(sizes["sum"] == 60) & (sizes["size"] == 60)]
    common = pd.Series(hour.isin(complete_hours), index=frame.index)
    cards, tables = [], {}
    files = []
    for step in run.config["steps_minutes"]:
        group = frame.loc[common, ["Q", "COD", "T"]].groupby(pd.Grouper(freq=f"{step}min"))
        count = group.size()
        qsum = group["Q"].sum(min_count=1)
        qcsum = (frame.loc[common, "Q"] * frame.loc[common, "COD"]).groupby(pd.Grouper(freq=f"{step}min")).sum(min_count=1)
        table = pd.DataFrame({"Q": qsum / count.replace(0, np.nan), "COD_FW": qcsum / qsum,
                              "COD_TW": group["COD"].mean(), "T": group["T"].mean(),
                              "V_m3": qsum / 60, "COD_load_kg": qcsum / 60000,
                              "archive_rows": count})
        table = table.loc[count == step].copy()
        if not len(table) or not np.isfinite(table.to_numpy()).all():
            raise ValueError("Empty or nonfinite common calendar support")
        breaks = table.index.to_series().diff().ne(pd.Timedelta(minutes=step))
        table["block_id"] = breaks.cumsum().to_numpy()
        table["step_minutes"] = step
        table["regime"] = 0
        table.index.name = "timestamp"
        tables[step] = table
        name = f"data/support_{step:02d}m.parquet"
        run.annotate(table.reset_index()).to_parquet(run.path(name), index=False, compression="zstd")
        files.append(name)
        cards.append({"step_minutes": step, "archive_bins": len(table), "archive_minutes": int(table["archive_rows"].sum()),
                      "common_hours": len(complete_hours), "technical_blocks": int(table["block_id"].nunique()),
                      "development_calendar_minutes": len(frame), "retained_calendar_fraction": float(common.mean()),
                      "discarded_archive_minutes": int((~common).sum()), "V_m3": float(table["V_m3"].sum()),
                      "COD_load_kg": float(table["COD_load_kg"].sum()), "fresh_count": None})
    cards_frame = pd.DataFrame(cards)
    for variable in ["V_m3", "COD_load_kg"]:
        error = float((cards_frame[variable] - cards_frame[variable].iloc[0]).abs().max() / max(abs(cards_frame[variable].iloc[0]), 1))
        if error > run.numeric_tolerance:
            raise ValueError("Cross-scale common-support integral failed")
    run.annotate(cards_frame).to_csv(run.path("validation/support_card.csv"), index=False, encoding="utf-8-sig")
    files.append("validation/support_card.csv")
    run.record("M02", "建立三尺度相同日历暴露的档案支线输入。", "仅保留 Q/COD/T 全部技术有效的完整小时；三尺度重聚合相同分钟集合，缺口不填补。完整小时是支线比较支持定义，不是原生覆盖合格门。",
               {"common_hours": len(complete_hours), "archive_minutes": int(common.sum()), "support_by_scale": cards,
                "formal_main_step_minutes": None, "M02_source_sha256": entry["sha256"]}, files)
    state_info = {"K": 1, "state": 0, "event_rules": "not_defined", "fresh_count": None,
                  "independent_events": None, "natural_state_process": "not_claimed", "regime_is_confirmed_event": False}
    write_json(run.path("models/K1_state.json"), state_info)
    run.record("M03", "先运行 K=1 基线，不制造事件分层。", "所有技术档案支持标为状态 0；不运行 K-means、不设高Q/降雨/毒性阈值。",
               state_info, ["models/K1_state.json"])
    return tables


def temporal_cases(run: ArchiveRun, tables: dict[int, pd.DataFrame]) -> list[dict]:
    cases, diagnostics, files = [], [], []
    anchor = pd.Timestamp(run.study["splits"][0]["start"], tz=run.study["timezone"])
    for step, table in tables.items():
        minutes = np.asarray((table.index - anchor).total_seconds() / 60)
        design, basis = design_matrix(minutes, table["T"].to_numpy(), run.config["harmonic_period_minutes"])
        raw = table[["Q", "COD_FW"]].to_numpy()
        blocks = table["block_id"].to_numpy()
        for kind in run.config["transform_candidates"]:
            for p, q in run.config["arma_pilot_orders"]:
                cid = f"s{step:02d}_{kind}_ar{p}"
                try:
                    if q != 0:
                        raise ValueError("MA candidates are outside the current partial implementation")
                    y = transform(raw, kind)
                    fit = fit_temporal(y, design, blocks, p)
                    recovered = inverse_transform(reconstruct(fit, blocks), kind)
                    error = float(np.max(np.abs(recovered - raw) / np.maximum(np.abs(raw), 1)))
                    if error > run.numeric_tolerance:
                        raise ValueError("Inverse round-trip exceeded the existing numerical tolerance")
                    case = {"id": cid, "step": step, "transform": kind, "table": table, "blocks": blocks,
                            "fit": fit, "basis": basis, "design": design, "raw": raw}
                    cases.append(case)
                    components = pd.DataFrame({"timestamp": table.index, "block_id": blocks})
                    for j, variable in enumerate(["Q", "COD"]):
                        for name, array in [("x", raw), ("y", y), ("baseline", fit["baseline"]),
                                            ("residual", fit["residual"]), ("innovation", fit["innovations"])]:
                            components[f"{variable}_{name}"] = array[:, j]
                    name = f"data/{cid}_components.parquet"
                    run.annotate(components).to_parquet(run.path(name), index=False, compression="zstd")
                    files.append(name)
                    bundle = {"case_id": cid, "step_minutes": step, "transform": kind, "basis": basis,
                              "beta": fit["beta"].tolist(), "phi": fit["phi"].tolist(), "order": [p, q],
                              "initial_positions": fit["initial_positions"].tolist(),
                              "initial_residuals": fit["initial_residuals"].tolist(), "roundtrip_error_scaled": error}
                    name = f"models/{cid}_temporal.json"
                    write_json(run.path(name), bundle)
                    files.append(name)
                    diagnostics.append({"case_id": cid, "step_minutes": step, "transform": kind, "p": p, "q": q,
                                        "status": "PASS", "roundtrip_error_scaled": error,
                                        "phi_Q": float(fit["phi"][0]), "phi_COD": float(fit["phi"][1]),
                                        "archive_bins": len(table), "innovation_pairs": int(fit["eligible"].sum())})
                except (ValueError, np.linalg.LinAlgError, FloatingPointError) as exc:
                    run.failures.append({"stage": "M04", "case_id": cid, "reason": str(exc)})
                    diagnostics.append({"case_id": cid, "status": "FAIL", "reason": str(exc)})
    run.annotate(pd.DataFrame(diagnostics)).to_csv(run.path("validation/temporal_roundtrip.csv"), index=False, encoding="utf-8-sig")
    files.append("validation/temporal_roundtrip.csv")
    run.record("M04", "实现和核验条件慢项/唯一谐波与 AR(0/1) 的完整可逆原型。",
               "identity/log1p 两候选；截距、标准化日历时间/T、各一个日/周正弦余弦；全开发期条件 OLS。AR仅用同连续块内相邻记录，块首状态保存；不跨缺口、不选最优。",
               {"configured_cases": len(diagnostics), "successful_cases": len(cases),
                "failed_cases": len(diagnostics) - len(cases), "max_roundtrip_error_scaled": max((d.get("roundtrip_error_scaled", 0) for d in diagnostics), default=None)}, files,
               "PARTIAL" if run.failures else "PASS")
    if not cases:
        raise ValueError("No reversible temporal case succeeded")
    return cases


def fit_margins_and_dependence(run: ArchiveRun, cases: list[dict]) -> None:
    margin_rows, margin_files, copula_rows = [], [], []
    for i, case in enumerate(cases):
        innovations = case["fit"]["innovations"][case["fit"]["eligible"]]
        rng = np.random.default_rng(run.config["seeds"][0] + i)
        margins = [EmpiricalMargin.fit(innovations[:, j]) for j in range(2)]
        u = np.column_stack([margin.pit(innovations[:, j], rng) for j, margin in enumerate(margins)])
        errors = [float(np.max(np.abs(margin.ppf(u[:, j]) - innovations[:, j]))) for j, margin in enumerate(margins)]
        if max(errors) > run.numeric_tolerance:
            raise ValueError("Empirical generalized inverse did not recover training support")
        case.update(margins=margins, u=u)
        data = {"case_id": case["id"], "pit_seed": run.config["seeds"][0] + i,
                "definition": "empirical generalized inverse; atoms retained; CDF(PPF(u)) need not equal u",
                "sorted_innovations": [margin.sorted_values.tolist() for margin in margins]}
        name = f"models/{case['id']}_empirical_margins.json"
        write_json(run.path(name), data)
        margin_files.append(name)
        for j, variable in enumerate(["Q", "COD"]):
            values = innovations[:, j]
            threshold = float(np.quantile(values, run.config["tail_reference_quantile"]))
            margin_rows.append({"case_id": case["id"], "variable": variable, "archive_innovations": len(values),
                                "unique_values": len(np.unique(values)), "roundtrip_absolute_error": errors[j],
                                "q975_reference": threshold, "above_q975_archive_points": int((values > threshold).sum()),
                                "independent_tail_clusters": None, "GPD_enabled": False})
    run.annotate(pd.DataFrame(margin_rows)).to_csv(run.path("validation/empirical_margin_checks.csv"), index=False, encoding="utf-8-sig")
    margin_files.append("validation/empirical_margin_checks.csv")
    run.record("M05", "经验创新边际与原子质量的数值核验；不启用GPD。",
               "全时点创新总体的经验CDF/广义逆；固定种子随机PIT，保留并披露并列值。97.5%仅为点尾支持参照，不推定独立事件簇。",
               {"case_margins": len(margin_rows), "max_training_support_recovery_error": max(row["roundtrip_absolute_error"] for row in margin_rows), "GPD_enabled": False}, margin_files)
    for case in cases:
        models = fit_copulas(case["u"], run.config["student_df_numeric_search"])
        case["copulas"] = models
        for model in models:
            copula_rows.append({"case_id": case["id"], **model})
            if model["fit_status"] != "PASS":
                run.failures.append({"stage": "M06", "case_id": case["id"], **model})
    write_json(run.path("models/copula_bundle.json"), copula_rows)
    run.annotate(pd.DataFrame(copula_rows)).to_csv(run.path("validation/copula_fits.csv"), index=False, encoding="utf-8-sig")
    run.record("M06", "同一经验边际和时间模型下拟合三个同期创新基线。",
               "独立/Gaussian/Student-t；椭圆相关由tau映射，允许负相关。t自由度用开发期条件伪似然数值搜索，报告搜索范围和边界距离；不做IID似然推断或模型优选。二维原型不冒称高维Vine。",
               {"copula_fits": len(copula_rows), "failed_fits": sum(m["fit_status"] != "PASS" for m in copula_rows)},
               ["models/copula_bundle.json", "validation/copula_fits.csv"], "PARTIAL" if any(m["fit_status"] != "PASS" for m in copula_rows) else "PASS")


def generate_and_diagnose(run: ArchiveRun, cases: list[dict]) -> pd.DataFrame:
    metrics, files, trajectories, temporal_diagnostics = [], [], [], []
    start = pd.Timestamp(run.study["splits"][0]["start"], tz=run.study["timezone"])
    end = start + pd.Timedelta(days=run.config["pilot_calendar_days"])
    for case in cases:
        fit, table, step = case["fit"], case["table"], case["step"]
        for lag_minutes in run.config["diagnostic_lag_minutes"]:
            lag = lag_minutes // step
            for a, b in [(0, 0), (1, 1), (0, 1), (1, 0)]:
                for domain, values in [("raw", case["raw"]), ("innovation", fit["innovations"]), ("innovation_squared", fit["innovations"] ** 2)]:
                    corr, pairs = lagged_correlation(values[:, a], values[:, b], case["blocks"], lag)
                    temporal_diagnostics.append({"case_id": case["id"], "domain": domain, "from": ["Q", "COD"][a], "to": ["Q", "COD"][b],
                                                 "lag_minutes": lag_minutes, "correlation": corr, "archive_pairs": pairs, "independent_pairs": None})
        context = np.asarray((table.index >= start) & (table.index < end))
        reference = case["raw"][context]
        baseline = fit["baseline"][context]
        blocks = case["blocks"][context]
        phi = fit["phi"]
        max_phi = float(np.max(np.abs(phi)))
        burnin = 0 if max_phi == 0 else int(np.ceil(np.log(run.numeric_tolerance) / np.log(max_phi)))
        for copula in case["copulas"]:
            for seed in run.config["seeds"]:
                tid = f"{case['id']}_{copula['family']}_{seed}"
                try:
                    if burnin > run.config["maximum_numerical_burnin"]:
                        raise ValueError("AR decay warmup exceeds numerical budget; no shortened warmup")
                    rng = np.random.default_rng(seed)
                    residual = np.empty_like(reference)
                    clips = 0
                    for segment in block_slices(blocks):
                        u, clipped = draw_copula(copula, segment.stop - segment.start + burnin, rng)
                        clips += clipped
                        eta = np.column_stack([margin.ppf(u[:, j]) for j, margin in enumerate(case["margins"])])
                        state = np.zeros(2)
                        for i, innovation in enumerate(eta):
                            state = phi * state + innovation
                            if i >= burnin:
                                residual[segment.start + i - burnin] = state
                    synthetic = inverse_transform(baseline + residual, case["transform"])
                    if not np.isfinite(synthetic).all():
                        raise ValueError("Nonfinite generated values retained as failed trajectory")
                    negative = (synthetic < 0).sum(axis=0)
                    out = pd.DataFrame({"timestamp": table.index[context], "block_id": blocks,
                                        "Q_unconstrained": synthetic[:, 0], "COD_FW_unconstrained": synthetic[:, 1],
                                        "T_fixed_archive_context": table.loc[context, "T"].to_numpy(),
                                        "Q_negative": synthetic[:, 0] < 0, "COD_negative": synthetic[:, 1] < 0})
                    name = f"data/trajectories/{tid}.parquet"
                    run.annotate(out).to_parquet(run.path(name), index=False, compression="zstd")
                    files.append(name)
                    record = {"trajectory_id": tid, "case_id": case["id"], "step_minutes": step,
                              "transform": case["transform"], "p": fit["order"], "family": copula["family"], "seed": seed,
                              "archive_bins": len(reference), "segments": len(block_slices(blocks)), "burnin_per_segment": burnin,
                              "U_numeric_endpoint_clips": clips, "Q_negative_rows": int(negative[0]), "COD_negative_rows": int(negative[1]),
                              "status": "PASS", "physical_admission": "PENDING_NO_REPAIR", "hindsight_conditioned": True}
                    trajectories.append(record)
                    row = dict(record)
                    row["tau_reference"] = float(stats.kendalltau(reference[:, 0], reference[:, 1]).statistic)
                    row["tau_synthetic"] = float(stats.kendalltau(synthetic[:, 0], synthetic[:, 1]).statistic)
                    row["tau_abs_error"] = abs(row["tau_synthetic"] - row["tau_reference"])
                    for j, variable in enumerate(["Q", "COD"]):
                        for q in [.05, .5, .95]:
                            row[f"{variable}_q{q}_reference"] = float(np.quantile(reference[:, j], q))
                            row[f"{variable}_q{q}_synthetic"] = float(np.quantile(synthetic[:, j], q))
                        for lag_min in run.config["diagnostic_lag_minutes"]:
                            r, n = lagged_correlation(reference[:, j], reference[:, j], blocks, lag_min // step)
                            s, _ = lagged_correlation(synthetic[:, j], synthetic[:, j], blocks, lag_min // step)
                            row[f"{variable}_acf_{lag_min}m_reference"] = r
                            row[f"{variable}_acf_{lag_min}m_synthetic"] = s
                            row[f"{variable}_acf_{lag_min}m_archive_pairs"] = n
                    metrics.append(row)
                except (ValueError, FloatingPointError, np.linalg.LinAlgError) as exc:
                    failure = {"stage": "M07", "trajectory_id": tid, "reason": str(exc), "status": "FAIL"}
                    run.failures.append(failure)
                    trajectories.append(failure)
    trajectory_frame = pd.DataFrame(trajectories)
    run.annotate(trajectory_frame).to_csv(run.path("validation/trajectory_manifest.csv"), index=False, encoding="utf-8-sig")
    files.append("validation/trajectory_manifest.csv")
    run.record("M07", "同条件下递推合成原型并保存失败与初始化。",
               "固定开发期前30日的同一日历/T；每连续段独立预热，AR遗忘数由phi与既定数值容差计算。三个种子仅供复现探索，不视为独立环境事件。结果为未修正序列。",
               {"requested_trajectories": len(trajectories), "successful_trajectories": len(metrics), "failed_trajectories": len(trajectories) - len(metrics)}, files,
               "PARTIAL" if len(metrics) < len(trajectories) else "PASS")
    negatives = trajectory_frame[["Q_negative_rows", "COD_negative_rows"]].sum().to_dict() if len(metrics) else {}
    run.record("M08", "保存未经修正序列的负值账本，不实施未经准入的物理修正。", "逐轨迹记负Q/负COD和数值端点处理；不裁剪、不投影、不导SUMO。技术生成成功不能代表物理边界可用。",
               {"negative_archive_rows_by_variable": negatives, "physical_correction_executed": False}, ["validation/trajectory_manifest.csv"], "PARTIAL")
    diagnostics = pd.DataFrame(metrics)
    run.annotate(diagnostics).to_csv(run.path("validation/synthesis_diagnostics.csv"), index=False, encoding="utf-8-sig")
    run.annotate(pd.DataFrame(temporal_diagnostics)).to_csv(run.path("validation/temporal_correlations.csv"), index=False, encoding="utf-8-sig")
    run.annotate(pd.DataFrame(run.failures, columns=["stage", "case_id", "trajectory_id", "reason"])).to_csv(run.path("validation/failure_ledger.csv"), index=False, encoding="utf-8-sig")
    run.record("M09", "报告回顾条件下同期与动态档案差异及失败，不作正式贡献实验。", "仅相同30日、相同日历支持比较；相关按真实物理滞后和同连续块配对。展示全部尺度/变换/AR/家族与种子，不选赢家，不作p值/独立事件区间。",
               {"diagnostic_trajectories": len(diagnostics), "development_lag_diagnostics": len(temporal_diagnostics),
                "total_recorded_failures": len(run.failures), "heldout_rows_used": 0, "E1_E2_E3_executed": False},
               ["validation/synthesis_diagnostics.csv", "validation/temporal_correlations.csv", "validation/failure_ledger.csv"])
    return diagnostics


def main() -> int:
    root = Path(__file__).resolve().parents[3]
    run = ArchiveRun(root)
    try:
        if run.tests["status"] != "PASS":
            raise ValueError("Pre-execution tests failed")
        tables = prepare_support(run)
        cases = temporal_cases(run, tables)
        fit_margins_and_dependence(run, cases)
        diagnostics = generate_and_diagnose(run, cases)
        from .figures import plot_diagnostics
        figure_files = plot_diagnostics(run, diagnostics)
        run.record("M11", "全原型配置的同期/动态差异图及源数据。", "两变换各三面板，颜色为Copula家族、线型/标记为AR阶；跨种子中位数只作描述，不作置信区间。",
                   {"figures": 2, "source_trajectories": len(diagnostics), "visual_QA": "PENDING"}, figure_files, "PARTIAL")
        write_json(run.run_dir / "manifest.json", {"run_id": run.run_id, "purpose": "archive_sensitivity", "status": "PARTIAL",
                   "scientific_admission": "PENDING", "formal_main_step_minutes": None, "stages": run.stage_records,
                   "failure_count": len(run.failures), "config_and_code_sha256": run.hashes,
                   "implementation_references": ["https://docs.scipy.org/doc/scipy-1.15.3/reference/generated/scipy.stats.multivariate_t.html",
                                                  "https://www.statsmodels.org/stable/tsa.html"]})
        print(json.dumps({"run_id": run.run_id, "status": "PARTIAL", "scope": "archive_only", "failures": len(run.failures)}, ensure_ascii=False), flush=True)
        return 0
    except Exception as exc:
        (run.run_dir / "error.log").write_text(traceback.format_exc(), encoding="utf-8")
        write_json(run.run_dir / "manifest.json", {"run_id": run.run_id, "status": "FAIL", "error": str(exc), "completed_stages": run.stage_records})
        print(json.dumps({"run_id": run.run_id, "status": "FAIL", "error": str(exc)}, ensure_ascii=False), flush=True)
        return 1
