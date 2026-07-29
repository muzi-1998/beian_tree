from __future__ import annotations

import base64
import json
import subprocess
from pathlib import Path

from PIL import Image


PLUGIN_ROOT = (
    Path.home()
    / ".codex"
    / "plugins"
    / "cache"
    / "scientific-illustrator-tools"
    / "scientific-illustrator"
    / "1.3.0"
)
BRIDGE = PLUGIN_ROOT / "scripts" / "powerpoint-bridge.ps1"


def _bridge(action: str, arguments: dict | None = None) -> dict:
    payload = json.dumps(
        {"action": action, "arguments": arguments or {}},
        ensure_ascii=True,
        separators=(",", ":"),
    )
    encoded = base64.b64encode(payload.encode("utf-8")).decode("ascii")
    completed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(BRIDGE),
            encoded,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if completed.returncode:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip())
    return json.loads(completed.stdout)


def _export_pdf_with_powerpoint(path: Path) -> None:
    escaped = str(path.resolve()).replace("'", "''")
    script = (
        "$ErrorActionPreference='Stop';"
        "Add-Type -AssemblyName Microsoft.Office.Interop.PowerPoint;"
        "$app=[Runtime.InteropServices.Marshal]::GetActiveObject("
        "'PowerPoint.Application');"
        "$presentation=$app.ActivePresentation;"
        f"$presentation.SaveAs('{escaped}',"
        "[Microsoft.Office.Interop.PowerPoint.PpSaveAsFileType]::ppSaveAsPDF)"
    )
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-Command", script],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if completed.returncode:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip())


def _add_shape(
    name: str,
    text: str,
    bounds: tuple[float, float, float, float],
    *,
    fill: str,
    line: str = "#4D4D4D",
    font_size: float = 11,
    bold: bool = False,
) -> None:
    left, top, width, height = bounds
    _bridge(
        "add_shape",
        {
            "slide_index": 1,
            "name": name,
            "shape": "rounded_rectangle",
            "text": text,
            "left": left,
            "top": top,
            "width": width,
            "height": height,
            "fill_color": fill,
            "line_color": line,
            "line_width": 1.0,
            "font_name": "Arial",
            "font_size": font_size,
            "font_color": "#272727",
            "bold": bold,
            "alignment": "center",
            "vertical_alignment": "middle",
            "margin_left": 6,
            "margin_right": 6,
            "margin_top": 4,
            "margin_bottom": 4,
            "word_wrap": True,
            "text_autofit": "shrink_text",
            "pause_after_ms": 0,
        },
    )


def _add_text(
    name: str,
    text: str,
    bounds: tuple[float, float, float, float],
    *,
    font_size: float,
    bold: bool = False,
    color: str = "#272727",
    alignment: str = "left",
) -> None:
    left, top, width, height = bounds
    _bridge(
        "add_textbox",
        {
            "slide_index": 1,
            "name": name,
            "text": text,
            "left": left,
            "top": top,
            "width": width,
            "height": height,
            "font_name": "Arial",
            "font_size": font_size,
            "font_color": color,
            "bold": bold,
            "alignment": alignment,
            "vertical_alignment": "middle",
            "margin_left": 0,
            "margin_right": 0,
            "margin_top": 0,
            "margin_bottom": 0,
            "word_wrap": True,
            "text_autofit": "shrink_text",
            "pause_after_ms": 0,
        },
    )


def _arrow(
    name: str,
    begin: tuple[float, float],
    end: tuple[float, float],
    *,
    color: str = "#767676",
    dash: str = "solid",
    width: float = 1.2,
    end_arrow: str = "triangle",
) -> None:
    _bridge(
        "add_line",
        {
            "slide_index": 1,
            "name": name,
            "begin_x": begin[0],
            "begin_y": begin[1],
            "end_x": end[0],
            "end_y": end[1],
            "line_color": color,
            "line_width": width,
            "line_dash": dash,
            "end_arrow": end_arrow,
            "start_clearance": 0,
            "end_clearance": 1.5,
            "pause_after_ms": 0,
        },
    )


def build_framework_figure(figure_dir: Path) -> tuple[Path, dict]:
    if not BRIDGE.exists():
        raise FileNotFoundError(f"Scientific Illustrator bridge not found: {BRIDGE}")
    figure_dir.mkdir(parents=True, exist_ok=True)
    stem = figure_dir / "FigV2_WWDQS_framework"
    _bridge("new_presentation", {"maximize": True})
    inspected = _bridge(
        "inspect",
        {"max_slides": 10, "max_shapes_per_slide": 20, "include_text": False},
    )
    if int(inspected.get("slide_count", 0)) == 0:
        _bridge(
            "add_slide",
            {
                "position": 1,
                "layout": "blank",
                "name": "WWDQS evidence architecture",
                "pause_after_ms": 0,
            },
        )

    _add_text(
        "title",
        "Evidence architecture and claim boundary",
        (40, 18, 880, 30),
        font_size=19,
        bold=True,
    )
    _add_shape(
        "input_raw",
        "1-min DO/ORP\nmeasurements",
        (40, 84, 122, 70),
        fill="#E8EDF5",
        bold=True,
    )
    _add_shape(
        "temporal_base",
        "1.1 causal multiscale\ntransform\n(frozen in validation)",
        (200, 76, 142, 86),
        fill="#D7E4F2",
        bold=True,
    )
    _arrow("flow_input_to_base", (162, 119), (200, 119))

    dimensions = [
        ("D1", "Sensor\nhealth", "#DDE8F4"),
        ("D2", "Continuity &\navailability", "#DDE8F4"),
        ("D5", "Topological\nstructure", "#DDE8F4"),
        ("D4", "Pair temporal\nconsistency", "#DDE8F4"),
        ("D3", "Independent\nSafety Gate", "#F6E3B7"),
    ]
    x_positions = [378, 488, 598, 708, 818]
    for (dimension, role, fill), left in zip(dimensions, x_positions):
        _add_shape(
            f"dimension_{dimension}",
            f"{dimension}\n{role}",
            (left, 64, 94, 92),
            fill=fill,
            bold=True,
        )
    _arrow(
        "flow_base_to_bus",
        (342, 119),
        (360, 119),
        color="#7884B4",
        width=1.0,
        end_arrow="none",
    )
    _arrow(
        "flow_bus_vertical",
        (360, 119),
        (360, 48),
        color="#7884B4",
        width=1.0,
        end_arrow="none",
    )
    _arrow(
        "flow_bus_horizontal",
        (360, 48),
        (865, 48),
        color="#7884B4",
        width=1.0,
        end_arrow="none",
    )
    for (dimension, _, _), left in zip(dimensions, x_positions):
        _arrow(
            f"flow_bus_to_{dimension}",
            (left + 47, 48),
            (left + 47, 64),
            color="#7884B4" if dimension != "D3" else "#C89B3C",
            width=1.0,
        )

    _add_shape(
        "node_product",
        "Node product\nD1 + D2 + D5\nFull / Basic separate",
        (416, 234, 194, 92),
        fill="#E8D9E2",
        bold=True,
    )
    _add_shape(
        "pair_product",
        "Pair product\nTarget node + peer node\n+ independent D4_raw",
        (678, 234, 194, 92),
        fill="#E8D9E2",
        bold=True,
    )
    for source_x in (425, 535, 645):
        _arrow(
            "node_bus_drop_" + str(source_x),
            (source_x, 156),
            (source_x, 184),
            end_arrow="none",
        )
    _arrow(
        "node_evidence_bus",
        (425, 184),
        (645, 184),
        end_arrow="none",
    )
    _arrow("node_bus_to_product", (513, 184), (513, 234))
    _arrow("pair_d4", (755, 156), (775, 234))
    _arrow("pair_node", (610, 280), (678, 280))
    _add_text(
        "gate_note",
        "Applied after scoring;\nnot averaged",
        (808, 171, 114, 36),
        font_size=9,
        bold=True,
        color="#8A671E",
        alignment="center",
    )

    _add_shape(
        "plant_summary",
        "Plant-level retrospective summary\ncoverage-stratified; no A-E grades",
        (548, 365, 220, 62),
        fill="#E8D9E2",
        bold=True,
    )
    _arrow("node_to_plant", (513, 326), (600, 365))
    _arrow("pair_to_plant", (775, 326), (716, 365))

    _add_shape(
        "claim_supported",
        "Supported\nWithin-plant retrospective robustness",
        (52, 462, 270, 48),
        fill="#DDECDD",
        font_size=9.5,
        bold=True,
    )
    _add_shape(
        "claim_pending",
        "Pending\nField truth, future period, external plant",
        (345, 462, 270, 48),
        fill="#F4E6C7",
        font_size=9.5,
        bold=True,
    )
    _add_shape(
        "claim_prohibited",
        "Not supported\nDeployment effectiveness or optimal weights",
        (638, 462, 270, 48),
        fill="#EBD6D6",
        font_size=9.5,
        bold=True,
    )

    audit = _bridge(
        "audit_figure",
        {
            "slide_index": 1,
            "alignment_tolerance": 0.75,
            "endpoint_clearance": 1.5,
            "text_overflow_tolerance": 1.5,
            "max_findings": 300,
        },
    )
    if int(audit.get("hard_failure_count", 0)) > 0:
        raise RuntimeError(
            "Scientific Illustrator framework audit failed: "
            f"{audit['hard_failure_count']} hard findings"
        )
    _bridge(
        "save",
        {
            "output_path": str(stem.with_suffix(".pptx")),
            "format": "pptx",
            "overwrite": True,
        },
    )
    try:
        _bridge(
            "save",
            {
                "output_path": str(stem.with_suffix(".pdf")),
                "format": "pdf",
                "overwrite": True,
            },
        )
    except RuntimeError as error:
        if "ExportAsFixedFormat" not in str(error):
            raise
        _export_pdf_with_powerpoint(stem.with_suffix(".pdf"))
    _bridge(
        "export_slide_image",
        {
            "slide_index": 1,
            "output_path": str(stem.with_suffix(".png")),
            "width": 3200,
            "height": 1800,
            "overwrite": True,
        },
    )
    with Image.open(stem.with_suffix(".png")) as image:
        image.save(
            stem.with_suffix(".tiff"),
            dpi=(600, 600),
            compression="tiff_lzw",
        )
    (figure_dir / "FigV2_WWDQS_framework_audit.json").write_text(
        json.dumps(audit, indent=2),
        encoding="utf-8",
    )
    return stem, audit
