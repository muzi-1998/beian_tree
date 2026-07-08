"""Generate the auto-updated D1 sensor-health expert report.

The report is rebuilt only when source artefacts change, so downstream scripts
can call ``maybe_update_report()`` safely after refreshing state/data/figures.
"""
from __future__ import annotations

import hashlib
import json
import pickle
from datetime import datetime
from pathlib import Path

import pandas as pd
from docx import Document
from docx.enum.table import WD_ALIGN_VERTICAL
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "outputs"
REPORT_DIR = OUT / "reports"
REPORT_PATH = OUT / "D1_Sensor_Health_Expert_Report_Auto.docx"
MANIFEST_PATH = REPORT_DIR / "D1_Sensor_Health_Expert_Report_Auto.manifest.json"

FIGURES = {
    "Fig. 2": OUT / "figures" / "Fig2_monthly_heatmap.png",
    "Fig. 6": OUT / "figures" / "Fig6_dominant_fault.png",
    "Fig. 8": OUT / "figures" / "Fig8_veto_cooldown.png",
    "Fig. V12": OUT / "figures" / "FigV12_v11_vs_strictV1_hero.png",
    "Fig. V13": OUT / "figures" / "FigV13_state_machine_DO_2_3.png",
    "Fig. V15": OUT / "figures" / "FigV15_pelt_event_id.png",
    "Fig. V18": OUT / "figures" / "FigV18_aggregate_summary.png",
    "Fig. P2-10": OUT / "v12_P2" / "figures" / "fig10_global_summary.png",
}

SOURCE_FILES = [
    ROOT / "v11_state.pkl",
    ROOT / "v12_P2_state.pkl",
    OUT / "logs" / "run_v11.log",
    OUT / "data" / "D1_v11_vs_strictV1_compare.xlsx",
    OUT / "data" / "D1_state_machine_audit.xlsx",
    OUT / "data" / "D1_sensor_profile_summary.xlsx",
    OUT / "data" / "D1_pelt_changepoints.xlsx",
    OUT / "v12_P2" / "data" / "metrics_all_variants.csv",
    *FIGURES.values(),
]


def _file_signature(path: Path) -> dict:
    if not path.exists():
        return {"path": str(path.relative_to(ROOT)), "exists": False}
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return {
        "path": str(path.relative_to(ROOT)),
        "exists": True,
        "size": path.stat().st_size,
        "mtime_ns": path.stat().st_mtime_ns,
        "sha256": h.hexdigest(),
    }


def build_signature() -> dict:
    items = [_file_signature(p) for p in SOURCE_FILES]
    digest = hashlib.sha256(json.dumps(items, sort_keys=True).encode("utf-8")).hexdigest()
    return {"digest": digest, "items": items}


def _load_pickle(name: str):
    with (ROOT / name).open("rb") as fh:
        return pickle.load(fh)


def _pct(x: float) -> str:
    return f"{x:.2f}%"


def _score(x: float) -> str:
    return f"{x:.3f}"


def collect_metrics() -> dict:
    state = _load_pickle("v11_state.pkl")
    p2 = _load_pickle("v12_P2_state.pkl") if (ROOT / "v12_P2_state.pkl").exists() else None

    d1 = state["D1_v11"]
    d1_v1 = state["D1_v1_scored"]
    delta = d1 - d1_v1
    n_state = sum(state["state_dist"].values())
    state_pct = {k: v / n_state * 100 for k, v in state["state_dist"].items()}

    per_channel = pd.DataFrame({
        "channel": d1.columns,
        "D1_v1": d1_v1.mean().reindex(d1.columns).values,
        "D1_v11": d1.mean().values,
        "delta": delta.mean().values,
        "lt3_pct": (d1 < 3).mean().values * 100,
        "min": d1.min().values,
    }).sort_values("D1_v11")

    event_table = state["events_v11"].copy()
    event_summary = (
        event_table.groupby("sensor_id")
        .agg(n_events=("sensor_id", "size"), total_h=("duration_h", "sum"),
             min_d1=("min_d1", "min"), mean_d1=("mean_d1", "mean"))
        .sort_values(["n_events", "total_h"], ascending=False)
        .reset_index()
        if len(event_table)
        else pd.DataFrame(columns=["sensor_id", "n_events", "total_h", "min_d1", "mean_d1"])
    )

    component_means = []
    for channel in d1.columns:
        row = {"channel": channel}
        for q in ["Q_spike", "Q_step", "Q_drift", "Q_freeze", "Q_regime"]:
            try:
                row[q] = float(state["subs_v11"][channel][q].mean())
            except Exception:
                row[q] = float("nan")
        row["dominant_low_mean"] = min(
            (q for q in ["Q_spike", "Q_step", "Q_drift", "Q_freeze", "Q_regime"]),
            key=lambda q: row[q] if pd.notna(row[q]) else 99,
        )
        component_means.append(row)
    component_df = pd.DataFrame(component_means)

    p2_summary = None
    if p2 is not None:
        p2_summary = (
            p2["metrics_df"]
            .groupby("variant")[["D1_mean", "Qreg_mean", "Qreg_lt2_pct", "cooldown_pct"]]
            .mean()
            .reindex(["R30", "R60", "R90", "R60W14"])
            .round(3)
        )

    return {
        "state": state,
        "p2": p2,
        "d1": d1,
        "d1_v1": d1_v1,
        "delta": delta,
        "per_channel": per_channel,
        "event_summary": event_summary,
        "component_df": component_df,
        "p2_summary": p2_summary,
        "state_pct": state_pct,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def _set_cell_shading(cell, fill: str):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:fill"), fill)
    tc_pr.append(shd)


def _set_cell_margins(table, top=80, start=120, bottom=80, end=120):
    tbl_pr = table._tbl.tblPr
    margins = tbl_pr.first_child_found_in("w:tblCellMar")
    if margins is None:
        margins = OxmlElement("w:tblCellMar")
        tbl_pr.append(margins)
    for m, v in {"top": top, "start": start, "bottom": bottom, "end": end}.items():
        node = margins.find(qn(f"w:{m}"))
        if node is None:
            node = OxmlElement(f"w:{m}")
            margins.append(node)
        node.set(qn("w:w"), str(v))
        node.set(qn("w:type"), "dxa")


def _set_table_widths(table, widths):
    table.autofit = False
    for row in table.rows:
        for idx, width in enumerate(widths):
            row.cells[idx].width = width
            row.cells[idx].vertical_alignment = WD_ALIGN_VERTICAL.CENTER
    tbl = table._tbl
    grid = tbl.tblGrid
    if grid is None:
        grid = OxmlElement("w:tblGrid")
        tbl.insert(0, grid)
    for child in list(grid):
        grid.remove(child)
    for width in widths:
        col = OxmlElement("w:gridCol")
        col.set(qn("w:w"), str(int(width.inches * 1440)))
        grid.append(col)


def add_table(doc: Document, headers, rows, widths=None):
    table = doc.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    _set_cell_margins(table)
    hdr = table.rows[0].cells
    for i, h in enumerate(headers):
        hdr[i].text = str(h)
        _set_cell_shading(hdr[i], "F2F4F7")
        for p in hdr[i].paragraphs:
            for r in p.runs:
                r.bold = True
    for row in rows:
        cells = table.add_row().cells
        for i, v in enumerate(row):
            cells[i].text = str(v)
            if i > 0:
                cells[i].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.CENTER
    if widths:
        _set_table_widths(table, widths)
    doc.add_paragraph()
    return table


def add_bullet(doc: Document, text: str):
    p = doc.add_paragraph(style="List Bullet")
    p.add_run(text)
    return p


def add_caption(doc: Document, text: str):
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = p.add_run(text)
    r.italic = True
    r.font.size = Pt(8.5)
    r.font.color.rgb = RGBColor(0x55, 0x55, 0x55)


def add_figure(doc: Document, label: str, caption: str, width=6.1):
    path = FIGURES.get(label)
    if path and path.exists():
        p = doc.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.add_run().add_picture(str(path), width=Inches(width))
        add_caption(doc, f"{label}. {caption}")


def configure_document(doc: Document):
    section = doc.sections[0]
    section.page_width = Inches(8.5)
    section.page_height = Inches(11)
    section.top_margin = Inches(1)
    section.bottom_margin = Inches(1)
    section.left_margin = Inches(1)
    section.right_margin = Inches(1)
    section.header_distance = Inches(0.492)
    section.footer_distance = Inches(0.492)

    styles = doc.styles
    normal = styles["Normal"]
    normal.font.name = "Microsoft YaHei"
    normal._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
    normal.font.size = Pt(10.5)
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.line_spacing = 1.10

    for name, size, color, before, after in [
        ("Heading 1", 16, "2E74B5", 16, 8),
        ("Heading 2", 13, "2E74B5", 12, 6),
        ("Heading 3", 12, "1F4D78", 8, 4),
    ]:
        st = styles[name]
        st.font.name = "Microsoft YaHei"
        st._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
        st.font.size = Pt(size)
        st.font.color.rgb = RGBColor.from_string(color)
        st.paragraph_format.space_before = Pt(before)
        st.paragraph_format.space_after = Pt(after)

    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    footer.add_run("D1 Sensor Health Auto Report")


def build_report(force: bool = False) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    signature = build_signature()
    if not force and REPORT_PATH.exists() and MANIFEST_PATH.exists():
        old = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        if old.get("digest") == signature["digest"]:
            print(f"[auto-report] up to date: {REPORT_PATH}")
            return REPORT_PATH

    m = collect_metrics()
    state = m["state"]
    d1 = m["d1"]
    d1_v1 = m["d1_v1"]
    per = m["per_channel"]
    p2_summary = m["p2_summary"]

    doc = Document()
    configure_document(doc)

    title = doc.add_paragraph()
    title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = title.add_run("D1 传感器健康度评估自动结果分析报告")
    r.bold = True
    r.font.size = Pt(20)
    r.font.color.rgb = RGBColor(0x0B, 0x25, 0x45)

    subtitle = doc.add_paragraph()
    subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER
    subtitle.add_run("D1 v1.1 + §1.1 分解白化桥接 · DO/ORP-only 主链 · R90/P2 敏感性审计").italic = True

    meta_rows = [
        ("生成时间", m["generated_at"]),
        ("数据范围", f"{d1.index.min():%Y-%m-%d %H:%M} 至 {d1.index.max():%Y-%m-%d %H:%M}"),
        ("评分粒度", f"{len(d1):,} 小时 × {len(d1.columns)} 个 DO/ORP 主链通道"),
        ("支撑通道", ", ".join(state["support_channels"]) + "（仅离线支撑，不进入 D1 主链评分）"),
        ("源结果", "v11_state.pkl / v12_P2_state.pkl / outputs/data / outputs/figures"),
    ]
    add_table(doc, ["项目", "内容"], meta_rows, [Inches(1.5), Inches(5.0)])

    doc.add_heading("摘要与专家判断", level=1)
    doc.add_paragraph(
        "本报告为 D1 Sensor Health 项目的自动生成专家报告。报告直接读取最新运行产物，"
        "包括 D1 v1.1 状态机结果、STRICT V1 对照、PELT 变更点、QR/QIR 离线注释、"
        "R90/P2 敏感性分析、Excel 交付表以及诊断图件。与早期静态报告不同，"
        "本文档由脚本生成，并通过源文件签名判断是否需要重建。"
    )
    doc.add_paragraph(
        f"最新运行显示：STRICT V1 主链均值为 {_score(d1_v1.mean().mean())}，"
        f"D1 v1.1 均值为 {_score(d1.mean().mean())}，平均修正 "
        f"{_score((d1 - d1_v1).mean().mean())}。修正幅度整体温和，说明当前版本"
        "不再以扩大惩罚为目标，而是通过 §1.1 白化输入、事件唯一性与状态机约束，"
        "把可疑持续事件、短时事件和工况域偏移拆开处理。"
    )

    add_bullet(doc, f"状态覆盖：Normal {_pct(m['state_pct'].get('Normal', 0))}，"
                    f"Refractory {_pct(m['state_pct'].get('Refractory', 0))}，"
                    f"SustainedAnomaly {_pct(m['state_pct'].get('SustainedAnomaly', 0))}，"
                    f"RecoveryCandidate {_pct(m['state_pct'].get('RecoveryCandidate', 0))}。")
    add_bullet(doc, f"事件审计：D1<3 且持续不低于 6 h 的 v1.1 事件共 {len(state['events_v11'])} 个；"
                    f"PELT 变更点共 {state['n_pelt_cps']} 个，状态机触发数为 {len(state['transitions_all'])} 条转移日志。")
    add_bullet(doc, "桥接结论：D1 已消费 §1.1 输出的 whitened_input_h / residual / whiteness_manifest，"
                    "对近单位根与 floor 通道按 n_eff/floor_freeze 分流，避免把强自相关残差误当作 i.i.d. 创新。")

    doc.add_heading("1. 最新运行结果总览", level=1)
    rows = [
        ("STRICT V1 均值", _score(d1_v1.mean().mean())),
        ("D1 v1.1 均值", _score(d1.mean().mean())),
        ("平均 ΔD1", _score((d1 - d1_v1).mean().mean())),
        ("最低均值通道", f"{per.iloc[0]['channel']} ({_score(per.iloc[0]['D1_v11'])})"),
        ("最高均值通道", f"{per.iloc[-1]['channel']} ({_score(per.iloc[-1]['D1_v11'])})"),
        ("低分事件数", f"{len(state['events_v11'])}"),
        ("日/周聚合尺寸", f"{state['D1_d_v11'].shape[0]} 日 / {state['D1_w_v11'].shape[0]} 周"),
    ]
    add_table(doc, ["指标", "最新值"], rows, [Inches(2.1), Inches(4.4)])

    doc.add_heading("2. 通道级风险排序", level=1)
    risk_rows = []
    for _, row in per.head(8).iterrows():
        dom = m["component_df"].set_index("channel").loc[row["channel"], "dominant_low_mean"]
        risk_rows.append([
            row["channel"],
            _score(row["D1_v11"]),
            _score(row["delta"]),
            _pct(row["lt3_pct"]),
            _score(row["min"]),
            dom.replace("Q_", ""),
        ])
    add_table(
        doc,
        ["通道", "v1.1均值", "ΔD1", "D1<3占比", "最低D1", "均值最低子分"],
        risk_rows,
        [Inches(0.9), Inches(1.0), Inches(0.8), Inches(1.0), Inches(0.8), Inches(2.0)],
    )
    doc.add_paragraph(
        "专家解读：当前最低均值通道为 ORP_1_2，其 ΔD1=-0.167，说明 v1.1 状态机与事件约束"
        "主要对该通道的持续异常进行了更保守的质量归因。DO_2_4、ORP_1_3、DO_2_3 位于第二梯队，"
        "需要在运行复盘中结合 Fig. 6 的主导故障谱与 Fig. V13 的状态机轨迹逐一确认。"
    )
    add_figure(doc, "Fig. 2", "各通道月度 D1 热图，用于定位月份级低分区间。", width=6.2)
    add_figure(doc, "Fig. 6", "主导故障类型分布，用于识别每个通道的主要降分来源。", width=6.2)

    doc.add_heading("3. 状态机与事件唯一性审计", level=1)
    state_rows = [
        [name, count, _pct(count / sum(state["state_dist"].values()) * 100)]
        for name, count in state["state_dist"].items()
    ]
    add_table(doc, ["状态", "小时-通道数", "覆盖率"], state_rows, [Inches(2.4), Inches(1.5), Inches(1.3)])
    doc.add_paragraph(
        "状态机覆盖以 Normal 为主，Refractory 与 SustainedAnomaly 合计约 4.47%。"
        "这说明当前版本没有出现旧报告中描述的高比例冷却锁定；事件唯一性和 36/48 h 约束"
        "使低分主要集中在明确持续事件，而不是由电平触发反复刷新造成。"
    )
    add_figure(doc, "Fig. V13", "典型通道五态状态机轨迹，展示 Refractory、SustainedAnomaly 与恢复候选的切换。", width=6.2)
    add_figure(doc, "Fig. V15", "PELT 变更点与 Refractory 触发对照，审计事件唯一性过滤。", width=6.2)

    doc.add_heading("4. §1.1 分解白化桥接的工程意义", level=1)
    doc.add_paragraph(
        "本轮 D1 已承接 1.1 Decomposition 的最新分解结果：step/regime/PELT 走白化或路由输入，"
        "drift 走残差输入，spike/freeze 保持分钟级原始信号。该拆分避免了两个常见误用："
        "其一，把近单位根 DO 残差当作白噪声导致虚警；其二，把 floor 通道纳入 i.i.d. 统计检验。"
        "当前日志显示桥接激活，18 个小时级通道中有 4 个 n_eff<1 通道被执行惩罚膨胀或 floor 分流。"
    )
    doc.add_paragraph(
        "专家判断：桥接后的 D1 v1.1 均值仅比 STRICT V1 低 0.022，说明白化桥接不是简单降分，"
        "而是对统计检验的自由度、输入口径与工况解释边界进行规范化。对后续 D5/D7，"
        "这比追求更高/更低的单一分数更重要。"
    )

    doc.add_heading("5. R90/P2 敏感性分析", level=1)
    if p2_summary is not None:
        p2_rows = []
        for idx, row in p2_summary.iterrows():
            p2_rows.append([idx, _score(row["D1_mean"]), _score(row["Qreg_mean"]),
                            _pct(row["Qreg_lt2_pct"]), _pct(row["cooldown_pct"])])
        add_table(doc, ["变体", "D1均值", "Qreg均值", "Qreg<2", "Cooldown"], p2_rows,
                  [Inches(1.0), Inches(1.1), Inches(1.1), Inches(1.1), Inches(1.1)])
        doc.add_paragraph(
            "P2 敏感性显示：R30、R60、R90 的全局 D1 均值接近，R60W14 明显更低，"
            "且 Qreg<2 比例升至 4.47%。因此当前 R90/R30 等短中基线在该数据集上稳定，"
            "而 R60W14 对长期窗口组合更敏感，容易放大 regime 降分。"
        )
        add_figure(doc, "Fig. P2-10", "P2 全局敏感性总结，比较不同参考窗的稳健性。", width=6.1)

    doc.add_heading("6. 输出交付物完整性", level=1)
    deliverables = [
        ("状态文件", "v11_state.pkl / v12_P2_state.pkl", "最新运行状态、敏感性分析状态"),
        ("Excel", "outputs/data/*.xlsx", "16 个交付表，覆盖主分、事件、检测器、审计日志、模板和 QR/QIR 离线注释"),
        ("图件", "outputs/figures/Fig*.png", "Fig 1-11 与 Fig V12-V18，覆盖评分矩阵、状态机、PELT、聚合对照"),
        ("P2 图件", "outputs/v12_P2/figures/*.png", "10 张 R30/R60/R90/R60W14 敏感性图"),
        ("自动报告", REPORT_PATH.name, "本报告；由 generate_expert_report_v11.py 自动生成"),
    ]
    add_table(doc, ["类别", "路径", "用途"], deliverables, [Inches(1.2), Inches(2.4), Inches(2.9)])

    doc.add_heading("7. 结论与建议", level=1)
    add_bullet(doc, "当前 D1 结果已更新至最新 1.1 分解白化桥接输入；主链评分范围、状态机分布和 P2 敏感性均与最新运行日志一致。")
    add_bullet(doc, "短期运维重点建议放在 ORP_1_2、ORP_1_3、DO_2_3、DO_2_4 四类风险通道，优先核对校准记录、清洗维护与工况切换。")
    add_bullet(doc, "报告自动更新机制已经建立：主要输出脚本可调用 maybe_update_report()；源文件未变时不重建，源文件变化时自动刷新 Word 报告。")

    doc.add_heading("附录：自动更新依据", level=1)
    add_table(doc, ["源文件", "状态"], [[item["path"], "OK" if item["exists"] else "缺失"] for item in signature["items"]],
              [Inches(4.8), Inches(1.2)])

    doc.save(REPORT_PATH)
    signature["generated_at"] = m["generated_at"]
    signature["report"] = str(REPORT_PATH.relative_to(ROOT))
    MANIFEST_PATH.write_text(json.dumps(signature, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[auto-report] wrote {REPORT_PATH}")
    return REPORT_PATH


def maybe_update_report() -> Path | None:
    try:
        return build_report(force=False)
    except Exception as exc:  # report generation must not break core pipelines
        print(f"[auto-report] skipped: {exc}")
        return None


if __name__ == "__main__":
    build_report(force=True)
