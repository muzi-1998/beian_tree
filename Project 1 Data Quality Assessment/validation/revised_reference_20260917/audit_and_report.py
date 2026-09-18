"""Validate temporal joins and present revised, already-inspected period evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
OUT = HERE / "outputs"
START, END = pd.Timestamp("2026-04-14"), pd.Timestamp("2026-07-31")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main(t0):
    node = pd.read_parquet(OUT / "DQR_node.parquet")
    pair = pd.read_parquet(OUT / "DQR_pair.parquet")
    clock = pd.read_parquet(OUT / "DQR_time_join.parquet")
    old = t0 / ".local_qa/holdout_T0"
    old_node = pd.read_parquet(old / "DQR_node.parquet")
    old_pair = pd.read_parquet(old / "DQR_pair.parquet")
    checks = {}

    def check(name, condition):
        checks[name] = bool(condition)
        if not condition:
            raise AssertionError(name)

    check("complete_108_days_14_nodes_7_pairs", len(node) == 108*24*14 and len(pair) == 108*24*7)
    for name, frame, identity in [("node", node, "sensor_id"), ("pair", pair, "pair_id")]:
        check(name+"_unique", not frame.duplicated(["timestamp", identity]).any())
        check(name+"_period", frame.timestamp.min() == START and frame.timestamp.max() == END-pd.Timedelta(hours=1))
    for dimension in ["D1", "D2", "D3", "D5"]:
        age = clock.decision_at - clock[dimension+"_available_at"]
        known = age.loc[age.notna()]
        check(dimension+"_no_future_or_expired_evidence", (known.ge(pd.Timedelta(0)) & known.lt(pd.Timedelta(hours=2 if dimension=="D3" else 1))).all())
    age = pair.decision_at - pair.D4_available_at
    known = age.loc[age.notna()]
    check("D4_no_future_or_expired_evidence", (known.ge(pd.Timedelta(0)) & known.lt(pd.Timedelta(hours=1))).all())
    keys = ["timestamp", "sensor_id"]
    a, b = node.set_index(keys).sort_index(), old_node.set_index(keys).sort_index()
    for field in ["D1_total", "D2_total", "D5_raw", "D5_report_score", "Q_node_available", "Q_node_core12", "Q_node_full"]:
        check(field+"_unchanged_from_T0", np.allclose(a[field], b[field], equal_nan=True, rtol=0, atol=1e-12))
    check("D5_no_support_backfill", a.coverage_class.equals(b.coverage_class))
    for field, atoms in [("Q_node_core12", ["D1_total", "D2_total"]), ("Q_node_full", ["D1_total", "D2_total", "D5_report_score"])]:
        valid = node[field].notna()
        check(field+"_formula", np.allclose(node.loc[valid, field], node.loc[valid, atoms].mean(axis=1), rtol=0, atol=1e-12))
    valid = pair.Q_pair_core.notna()
    check("pair_core_formula", np.allclose(pair.loc[valid, "Q_pair_core"], pair.loc[valid, ["left_Q_node_core12", "right_Q_node_core12", "D4_raw"]].mean(axis=1), rtol=0, atol=1e-12))
    check("D4_usable_has_calibration_metadata", pair.loc[pair.I_D4, ["calibration_scope", "calibration_evidence_quality", "calibration_independent_blocks", "calibration_tail_precision_grade"]].notna().all().all())
    check("D3_fail_blocks_release", node.loc[node.D3_gate_status.eq("Fail"), "release_status"].eq("gate_fail").all())

    node["month"] = node.timestamp.dt.strftime("%Y-%m")
    monthly = node.groupby("month").agg(n_sensor_hours=("sensor_id", "size"),
        full_rate=("coverage_class", lambda x: x.eq("full").mean()),
        basic_rate=("coverage_class", lambda x: x.eq("basic").mean()),
        limited_rate=("coverage_class", lambda x: x.eq("limited").mean()),
        D5_report_rate=("D5_report_score", lambda x: x.notna().mean()),
        out_of_template_rate=("D5_evaluation_status", lambda x: x.eq("out_of_template").mean()))
    means = node.groupby("month")[["Q_node_core12", "Q_node_full", "Q_node_available"]].mean()
    monthly = monthly.join(means)
    paired = pair.merge(old_pair[["timestamp", "pair_id", "D4_raw", "I_D4"]], on=["timestamp", "pair_id"], suffixes=("", "_T0"), validate="one_to_one")
    rows = []
    # Resample observed calendar blocks only; no simulated measurement data.
    rng = np.random.default_rng(20260917)
    for identity, group in paired.groupby("pair_id"):
        joint = group.loc[group.I_D4.fillna(False) & group.I_D4_T0.fillna(False)].copy()
        joint["delta"] = joint.D4_raw - joint.D4_raw_T0
        joint["block"] = (joint.timestamp-START).dt.days // 7
        blocks = joint.groupby("block").delta.agg(["sum", "count"])
        picks = rng.integers(0, len(blocks), (2000, len(blocks)))
        boot = blocks["sum"].to_numpy()[picks].sum(axis=1)/blocks["count"].to_numpy()[picks].sum(axis=1)
        lo, hi = np.quantile(boot, [.025, .975])
        low, previous_low = joint.D4_raw.lt(3), joint.D4_raw_T0.lt(3)
        union = (low | previous_low).sum()
        rows.append({"pair_id": identity, "n_common_pair_hours": len(joint), "n_7d_blocks": len(blocks),
            "mean_D4_T0": joint.D4_raw_T0.mean(), "mean_D4_revised": joint.D4_raw.mean(),
            "mean_delta": joint.delta.mean(), "delta_ci_low": lo, "delta_ci_high": hi,
            "low_hour_jaccard": (low & previous_low).sum()/union if union else np.nan})
    contrast = pd.DataFrame(rows)
    gates = pd.DataFrame({"revised_warn_pct": a.D3_gate_status.eq("Warn").groupby(level="sensor_id").mean()*100,
                          "T0_warn_pct": b.D3_gate_status.eq("Warn").groupby(level="sensor_id").mean()*100})
    reasons = node.D5_status_reason.value_counts(dropna=False).rename_axis("reason").reset_index(name="sensor_hours")
    with pd.ExcelWriter(OUT / "Reevaluation_source_data.xlsx") as writer:
        monthly.to_excel(writer, sheet_name="monthly_coverage_estimands")
        contrast.to_excel(writer, sheet_name="paired_D4_changes", index=False)
        gates.to_excel(writer, sheet_name="D3_gate_changes")
        reasons.to_excel(writer, sheet_name="D5_status_reasons", index=False)
        pd.DataFrame(list(checks.items()), columns=["check", "passed"]).to_excel(writer, sheet_name="time_formula_freeze_QA", index=False)

    plt.rcParams.update({"font.family": "Arial", "font.size": 7, "axes.titlesize": 8,
        "axes.linewidth": .8, "xtick.direction": "out", "ytick.direction": "out",
        "svg.fonttype": "none", "pdf.fonttype": 42, "legend.frameon": False})
    fig, axes = plt.subplots(2, 2, figsize=(7.20472441, 6.25984252), layout="constrained", gridspec_kw={"height_ratios": [1, 1.35]})
    x, bottom = np.arange(len(monthly)), np.zeros(len(monthly))
    for field, label, color in [("full_rate", "Full", "#0072B2"), ("basic_rate", "Basic", "#ABDDEC"), ("limited_rate", "Limited", "#B5B5B5")]:
        heights = monthly[field].to_numpy()*100
        axes[0,0].bar(x, heights, bottom=bottom, label=label, color=color, width=.65)
        bottom += heights
    axes[0,0].set(xticks=x, xticklabels=monthly.index, ylim=(0, 116), yticks=[0,25,50,75,100], ylabel="Sensor-hours (%)", title="Evidence availability")
    axes[0,0].legend(loc="upper center", ncol=3, fontsize=6.5)
    for field, label, color, marker in [("Q_node_core12", "Fixed Core", "#333333", "o"), ("Q_node_full", "Full", "#0072B2", "s"), ("Q_node_available", "Availability-aware", "#C06A42", "^")]:
        axes[0,1].plot(x, monthly[field], marker=marker, ms=4, lw=1, color=color, label=label)
    axes[0,1].set(xticks=x, xticklabels=monthly.index, ylim=(1,5.15), yticks=[1,2,3,4,5], ylabel="Sensor-hour pooled mean", title="Distinct quality estimands")
    axes[0,1].legend(loc="lower left", fontsize=6.5)
    y = np.arange(len(contrast))
    axes[1,0].errorbar(contrast.mean_delta, y, xerr=[contrast.mean_delta-contrast.delta_ci_low, contrast.delta_ci_high-contrast.mean_delta], fmt="o", ms=4, capsize=2, color="#0072B2", lw=1)
    axes[1,0].axvline(0, color=".6", lw=.7, ls="--")
    axes[1,0].set(yticks=y, yticklabels=contrast.pair_id.str.replace("PAIR_", "", regex=False), xlabel="Revised minus T0 mean D4", title="Combined D4 revision; 95% block CI")
    y = np.arange(len(gates))
    for field, marker, color, label in [("T0_warn_pct", "s", "#9A9A9A", "T0"), ("revised_warn_pct", "o", "#0072B2", "Revised")]:
        axes[1,1].scatter(gates[field], y + (-.13 if field.startswith("T0") else .13), s=12, marker=marker, color=color, label=label)
    axes[1,1].set(yticks=y, yticklabels=gates.index, xlabel="D3 Warn sensor-hours (%)", title="Safety gate is separate from quality")
    axes[1,1].legend(loc="upper right", fontsize=6.5)
    for ax, label in zip(axes.flat, "abcd"):
        ax.spines[["top", "right"]].set_visible(False)
        ax.text(-.12, 1.08, f"({label})", transform=ax.transAxes, weight="bold", size=8, va="bottom")
    fig.savefig(OUT / "Fig_revised_temporal_evaluation.png", dpi=600)
    fig.savefig(OUT / "Fig_revised_temporal_evaluation.pdf")
    fig.savefig(OUT / "Fig_revised_temporal_evaluation.svg")
    fig.savefig(OUT / "Fig_revised_temporal_evaluation.tiff", dpi=600, pil_kwargs={"compression": "tiff_lzw"})
    svg = OUT / "Fig_revised_temporal_evaluation.svg"
    svg.write_text("\n".join(line.rstrip() for line in svg.read_text(encoding="utf-8").splitlines())+"\n", encoding="utf-8")
    plt.close(fig)

    summary = {"sensor_hours": len(node), "pair_hours": len(pair), "D5_report_nonnull": int(node.D5_report_score.notna().sum()),
        "D5_report_rate": float(node.D5_report_score.notna().mean()), "D5_out_of_template_rate": float(node.D5_evaluation_status.eq("out_of_template").mean()),
        "coverage_counts": node.coverage_class.value_counts().to_dict(), "D3_gate_counts": node.D3_gate_status.value_counts().to_dict(),
        "D4_usable_pair_hours": int(pair.I_D4.sum()), "pooled_node_core": node.Q_node_core12.mean(),
        "pooled_node_full": node.Q_node_full.mean(), "pooled_node_available": node.Q_node_available.mean(),
        "pooled_pair_core": pair.Q_pair_core.mean(), "pooled_pair_available": pair.Q_pair_available.mean()}
    (OUT / "Reevaluation_QA.json").write_text(json.dumps({"passed": all(checks.values()), "checks": checks, "summary": summary}, indent=2), encoding="utf-8")
    report = f"""# 108天修订后时间外再评价

评价期：2026-04-14至2026-07-30，共108天。该数据已被查看，本结果不能重新声称首次盲测，也不能用于反向选择参考阈值。

## 执行与时间合同
- D1、D2、D5使用原冻结推断结果，本次未重拟合D5，未将L1/OOD回填为正式评分。
- D3使用中性原始观测校准的冻结α；位置3仍仅诊断。D4使用开发期冻结工况、公共映射和因果变点辅助窗；不读取D1/D2评分筛选。
- 以信息实际可获得时间向后接合；D1/D2/D4/D5证据有效期1 h，D3为2 h，均为半开区间。不回退搜寻更早的非空评分。
- 核验{len(checks)}项通过，包括时间无前视、完整网格、公式、D1/D2/D5及节点质量数值不变、D4校准元数据和安全门控。

## 结果
- 传感器小时：{len(node):,}；测点对小时：{len(pair):,}。
- D5正式report可评价：{summary['D5_report_nonnull']:,}，占{summary['D5_report_rate']:.2%}；out-of-template状态占{summary['D5_out_of_template_rate']:.2%}。
- Full/Basic/Limited：{summary['coverage_counts']}。Full要求D1、D2、D5同时存在，因此与D5单独可评价计数不同。
- 节点质量sensor-hour pooled mean：固定Core {summary['pooled_node_core']:.4f}、Full {summary['pooled_node_full']:.4f}、availability-aware {summary['pooled_node_available']:.4f}。三者不是同一估计目标，不能混合解释。
- D4可用测点对小时：{summary['D4_usable_pair_hours']:,}；完整逐对差值及95%区块区间见源数据。它包含工况、支持和准入的联合修订，不是单独准入的因果效应。

## 图注与限制
图(a)按自然月显示全部sensor-hour覆盖，4月仅14日起、7月至30日；(b)不跨缺失月份连结Full曲线；(c)仅在两版共同可评价pair-hour上计算配对差值，每个测点对进行2000次7 d日历时间区块重采样，点为均值、线为95%百分位区间，无显著性筛选、不作跨pair合并推断；(d)全部14支传感器D3 Warn占比，Warn不是故障真值。比较T0与修订版不用于模型选择。

D5低覆盖没有因本次D3/D4解耦自动解决。主要限制仍是冻结工况适用域及模板支持不足；out-of-template包括后验/OOD门控，不能全部归因为探头故障。后续需要独立新增支持与预先冻结的模板升级及双版本衔接，不得用本期结果回填历史。

本次复用原时间验证分支的冻结D1/D2/D5及因果分解结果作为带SHA-256的归档输入，不修改其原始文件。复现需要这些归档输入；外部故障真值、跨厂验证和下游任务有效性仍未获得。
"""
    (HERE / "REEVALUATION_REPORT_ZH.md").write_text(report, encoding="utf-8")
    artifacts = {p.name: digest(p) for p in OUT.iterdir() if p.is_file() and p.name != "Reevaluation_publication_manifest.json"}
    (OUT / "Reevaluation_publication_manifest.json").write_text(json.dumps({"claim": "revised_temporal_out_of_sample_re_evaluation_not_first_blind_test",
        "summary": summary, "artifacts": artifacts, "source_code": {p.name: digest(p) for p in HERE.glob("*.py")},
        "archived_comparison_inputs": {str(old/p): digest(old/p) for p in ["DQR_node.parquet", "DQR_pair.parquet"]}}, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--t0-root", type=Path, required=True)
    main(parser.parse_args().t0_root)
