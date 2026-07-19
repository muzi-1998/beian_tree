"""Audit final D1 figure bundles and create contact sheets for visual review."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont


ROOT = Path(__file__).parent
FIG_DIR = ROOT / "outputs" / "figures"
QA_DIR = ROOT / "outputs" / "qa" / "figures"
EXPECTED = [
    "Fig1_D1_dimension_matrix",
    "Fig2_monthly_heatmap",
    "Fig3_case_subscores",
    "Fig4_subscore_distribution",
    "Fig5_mapping_curves",
    "Fig6_score_loss_attribution",
    "Fig7_daily_timeseries",
    "Fig8_veto_cooldown",
    "Fig9_input_routing_audit",
    "Fig10_two_tier_regime",
    "Fig11_pls_peer_selection",
    "FigV12_v11_vs_strictV1_hero",
    "FigV13_state_machine_DO_2_3",
    "FigV14_veto3_state_audit",
    "FigV15_pelt_event_id",
    "FigV16_regime_templates",
    "FigV17_scope_qr_qir_offline",
    "FigV18_aggregate_summary",
    "FigV19_recovery_validation",
    "FigV20_adapted_recovery_case",
]
FULL_RESOLUTION_REVIEWED = {
    "Fig3_case_subscores",
    "Fig6_score_loss_attribution",
    "Fig7_daily_timeseries",
    "Fig8_veto_cooldown",
    "Fig9_input_routing_audit",
    "Fig10_two_tier_regime",
    "Fig11_pls_peer_selection",
    "FigV12_v11_vs_strictV1_hero",
    "FigV13_state_machine_DO_2_3",
    "FigV15_pelt_event_id",
    "FigV18_aggregate_summary",
    "FigV20_adapted_recovery_case",
}
VISUAL_REVIEW_CHECKS = [
    "panel labels follow the (a), (b), ... convention",
    "legends and annotations do not obscure decision-relevant data",
    "over-data annotation backgrounds remain partially transparent",
    "data-driven y limits provide only justified headroom",
    "axis labels and tick labels remain legible at final export size",
]


def _generator_for(name: str) -> Path:
    if name.startswith("FigV19") or name.startswith("FigV20"):
        return ROOT / "make_recovery_figures.py"
    if name.startswith(("FigV12", "FigV13", "FigV14", "FigV15")):
        return ROOT / "make_figures_v11.py"
    if name.startswith(("FigV16", "FigV17", "FigV18")):
        return ROOT / "make_figures_v11_part2.py"
    return ROOT / "make_baseline_figures_v11.py"


def _contact_sheet(names: list[str], output: Path) -> None:
    thumb_w, thumb_h, label_h = 640, 440, 34
    columns = 2
    rows = int(np.ceil(len(names) / columns))
    canvas = Image.new("RGB", (columns * thumb_w, rows * (thumb_h + label_h)), "white")
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default()
    for i, name in enumerate(names):
        image = Image.open(FIG_DIR / f"{name}.png").convert("RGB")
        image.thumbnail((thumb_w - 12, thumb_h - 12), Image.Resampling.LANCZOS)
        x0 = (i % columns) * thumb_w + (thumb_w - image.width) // 2
        y0 = (i // columns) * (thumb_h + label_h) + 6
        canvas.paste(image, (x0, y0))
        draw.text(((i % columns) * thumb_w + 8, y0 + thumb_h), name,
                  fill="black", font=font)
    canvas.save(output, dpi=(150, 150))


def main() -> None:
    QA_DIR.mkdir(parents=True, exist_ok=True)
    rows = []
    for name in EXPECTED:
        generator = _generator_for(name)
        sources = [ROOT / "publication_style.py", generator]
        source_mtime = max(path.stat().st_mtime for path in sources)
        row = {
            "figure": name,
            "generator": generator.name,
            "fresh_vs_generator": True,
        }
        for suffix in ("svg", "pdf", "png", "tiff"):
            path = FIG_DIR / f"{name}.{suffix}"
            row[f"{suffix}_exists"] = path.exists()
            row[f"{suffix}_bytes"] = path.stat().st_size if path.exists() else 0
            if not path.exists() or path.stat().st_mtime < source_mtime:
                row["fresh_vs_generator"] = False
        png_path = FIG_DIR / f"{name}.png"
        if png_path.exists():
            image = Image.open(png_path).convert("L")
            array = np.asarray(image)
            row["png_width_px"] = image.width
            row["png_height_px"] = image.height
            row["png_std"] = float(array.std())
            row["png_nonblank"] = bool(array.std() > 2.0)
            row["png_dpi_x"] = float(image.info.get("dpi", (0, 0))[0])
        svg_path = FIG_DIR / f"{name}.svg"
        if svg_path.exists():
            svg_text = svg_path.read_text(encoding="utf-8", errors="ignore")
            row["svg_has_editable_text"] = "<text" in svg_text
        row["visual_review"] = (
            "contact_sheet_and_full_resolution"
            if name in FULL_RESOLUTION_REVIEWED else "contact_sheet"
        )
        row["visual_review_checks"] = VISUAL_REVIEW_CHECKS
        rows.append(row)

    required = [
        "svg_exists", "pdf_exists", "png_exists", "tiff_exists",
        "png_nonblank", "svg_has_editable_text", "fresh_vs_generator",
    ]
    for row in rows:
        row["bundle_pass"] = all(bool(row.get(field, False)) for field in required)
    report = {
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "n_expected": len(EXPECTED),
        "n_passed": sum(row["bundle_pass"] for row in rows),
        "all_passed": all(row["bundle_pass"] for row in rows),
        "visual_review_contract": {
            "all_figures_reviewed_in_contact_sheets": True,
            "full_resolution_reviewed": sorted(FULL_RESOLUTION_REVIEWED),
            "checks": VISUAL_REVIEW_CHECKS,
            "note": "Visual review is recorded separately from automated bundle_pass.",
        },
        "figures": rows,
    }
    (QA_DIR / "D1_figure_bundle_audit.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    _contact_sheet(EXPECTED[:10], QA_DIR / "contact_sheet_01.png")
    _contact_sheet(EXPECTED[10:], QA_DIR / "contact_sheet_02.png")
    print(json.dumps({key: report[key] for key in ("n_expected", "n_passed", "all_passed")}))
    if not report["all_passed"]:
        raise SystemExit("At least one figure bundle failed the audit")


if __name__ == "__main__":
    main()
