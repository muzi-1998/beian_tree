"""Audit hash-level freshness across the released D1 downstream chain."""

from __future__ import annotations

import argparse
import hashlib
import json
import pickle
import re
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree

import numpy as np
import pandas as pd
from PIL import Image


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "cross_project_qa" / "cross_project_freshness_audit.json"
D7_LOCAL_CORE_FILES = (
    "D7_main_scores_hourly.parquet",
    "D7_spatial_evidence.parquet",
    "D7_sensor_influence.parquet",
    "D7_regime_state.parquet",
    "D7_reference_window_library.parquet",
    "D7_event_windows.parquet",
    "D7_zone_consensus.parquet",
    "D7_spatial_templates.template_bundle.json",
    "D7_topology_registry.json",
    "D7_topology_registry.yaml",
)
FIGURE_FORMATS = (".png", ".svg", ".pdf")
FIGURE_PROJECTS = {
    "1.1": {
        "roots": (ROOT / "1.1 Decomposition" / "outputs" / "figures",),
        "sources": (
            ROOT / "1.1 Decomposition" / "outputs" / "_pipeline_state.pkl",
        ),
    },
    "D1": {
        "roots": (ROOT / "D1 Sensor health" / "outputs" / "figures",),
        "sources": (
            ROOT / "D1 Sensor health" / "v11_state.pkl",
            ROOT / "D1 Sensor health" / "outputs" / "data" / "D1_release_manifest.json",
        ),
    },
    "D2": {
        "roots": (
            ROOT
            / "D2 Temporal Continuity & Information Availability"
            / "artifacts"
            / "figures",
        ),
        "sources": (
            ROOT
            / "D2 Temporal Continuity & Information Availability"
            / "artifacts"
            / "d2_state.pkl",
            ROOT / "D1 Sensor health" / "v11_state.pkl",
            ROOT / "D1 Sensor health" / "outputs" / "data" / "D1_event_windows.xlsx",
        ),
    },
    "D4": {
        "roots": (
            ROOT
            / "D4 Physical rationality and rate constraints"
            / "outputs"
            / "figures",
        ),
        "source_globs": (
            ROOT
            / "D4 Physical rationality and rate constraints"
            / "outputs"
            / "data"
            / "*",
        ),
    },
    "D6-main": {
        "roots": (
            ROOT
            / "D6 Parallel-redundancy Temporal Consistency"
            / "outputs"
            / "figures",
        ),
        "source_globs": (
            ROOT
            / "D6 Parallel-redundancy Temporal Consistency"
            / "outputs"
            / "data"
            / "*",
        ),
    },
    "D6-sensitivity": {
        "roots": (
            ROOT
            / "D6 Parallel-redundancy Temporal Consistency"
            / "outputs"
            / "comparison",
        ),
        "source_globs": (
            ROOT
            / "D6 Parallel-redundancy Temporal Consistency"
            / "outputs"
            / "comparison"
            / "*.xlsx",
        ),
    },
    "D7": {
        "roots": (
            ROOT
            / "D7 Topological Role Consistency and Structural Representativeness"
            / "outputs"
            / "figures",
        ),
        "sources": (
            ROOT
            / "D7 Topological Role Consistency and Structural Representativeness"
            / "outputs"
            / "plot_data"
            / "D7_plot_data.parquet",
        ),
    },
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def d7_local_core_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for name in D7_LOCAL_CORE_FILES:
        path = root / name
        if not path.is_file():
            raise FileNotFoundError(f"Missing D7 Local core artifact: {path}")
        digest.update(name.encode("utf-8"))
        digest.update(path.read_bytes())
    return digest.hexdigest()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def record(checks: list[dict[str, object]], name: str, passed: bool, detail: object) -> None:
    checks.append({"check": name, "passed": bool(passed), "detail": detail})


def _source_paths(spec: dict[str, object]) -> list[Path]:
    paths = [Path(path) for path in spec.get("sources", ())]
    for pattern in spec.get("source_globs", ()):
        pattern = Path(pattern)
        paths.extend(path for path in pattern.parent.glob(pattern.name) if path.is_file())
    return paths


def audit_figure_bundle(
    checks: list[dict[str, object]], project: str, spec: dict[str, object]
) -> None:
    bundles: dict[str, dict[str, Path]] = {}
    for root in spec["roots"]:
        root = Path(root)
        if not root.is_dir():
            record(checks, f"{project}:figure_root", False, str(root))
            return
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in FIGURE_FORMATS:
                key = str(path.relative_to(root).with_suffix(""))
                bundles.setdefault(f"{root.name}/{key}", {})[path.suffix.lower()] = path

    missing = {
        stem: [suffix for suffix in FIGURE_FORMATS if suffix not in formats]
        for stem, formats in bundles.items()
        if any(suffix not in formats for suffix in FIGURE_FORMATS)
    }
    empty = [
        str(path.relative_to(ROOT))
        for formats in bundles.values()
        for path in formats.values()
        if path.stat().st_size == 0
    ]
    record(
        checks,
        f"{project}:figure_bundle_complete",
        bool(bundles) and not missing and not empty,
        {
            "n_figures": len(bundles),
            "required_formats": list(FIGURE_FORMATS),
            "missing": missing,
            "empty": empty,
        },
    )

    sources = _source_paths(spec)
    missing_sources = [str(path.relative_to(ROOT)) for path in sources if not path.is_file()]
    if missing_sources or not sources or not bundles:
        record(
            checks,
            f"{project}:figures_not_older_than_sources",
            False,
            {"missing_sources": missing_sources, "n_sources": len(sources)},
        )
        return
    source_latest = max(path.stat().st_mtime_ns for path in sources)
    stale = [
        str(path.relative_to(ROOT))
        for formats in bundles.values()
        for path in formats.values()
        if path.stat().st_mtime_ns < source_latest
    ]
    record(
        checks,
        f"{project}:figures_not_older_than_sources",
        not stale,
        {
            "source_latest_utc": datetime.fromtimestamp(
                source_latest / 1e9, tz=timezone.utc
            ).isoformat(),
            "stale_files": stale,
        },
    )


def audit_d1_release_equivalence(checks: list[dict[str, object]]) -> None:
    d1_root = ROOT / "D1 Sensor health"
    with (d1_root / "v11_state.pkl").open("rb") as handle:
        state_scores = pickle.load(handle)["D1_v11"]
    released_scores = pd.read_excel(
        d1_root / "outputs" / "data" / "D1_main_scores_min.xlsx",
        sheet_name="D1_total_hourly",
        index_col=0,
    )
    released_scores.index = pd.to_datetime(released_scores.index)
    rows = state_scores.index.intersection(released_scores.index)
    columns = state_scores.columns.intersection(released_scores.columns)
    difference = np.abs(
        state_scores.loc[rows, columns].to_numpy()
        - released_scores.loc[rows, columns].to_numpy()
    )
    max_difference = float(np.nanmax(difference)) if difference.size else float("inf")
    complete = (
        len(rows) == len(state_scores.index) == len(released_scores.index)
        and len(columns) == len(state_scores.columns) == len(released_scores.columns)
    )
    record(
        checks,
        "D1:figure_state_matches_release",
        complete and max_difference <= 1e-12,
        {
            "rows": len(rows),
            "columns": len(columns),
            "max_abs_difference": max_difference,
        },
    )


def _svg_text_values(path: Path) -> list[str]:
    try:
        root = ElementTree.parse(path).getroot()
    except ElementTree.ParseError:
        return []
    return [
        "".join(node.itertext()).strip()
        for node in root.iter()
        if node.tag.rsplit("}", 1)[-1] == "text"
    ]


def write_detailed_figure_audit(
    figure_dir: Path, target: Path, sources: list[Path]
) -> None:
    source_latest = max(path.stat().st_mtime_ns for path in sources if path.is_file())
    records = []
    for png in sorted(figure_dir.glob("*.png")):
        stem = png.stem
        svg = figure_dir / f"{stem}.svg"
        pdf = figure_dir / f"{stem}.pdf"
        with Image.open(png) as image:
            gray = np.asarray(image.convert("L"))
            size = [image.width, image.height]
            nonblank = bool(gray.std() > 2.0)
        svg_source = svg.read_text(encoding="utf-8", errors="ignore") if svg.is_file() else ""
        text_values = _svg_text_values(svg) if svg.is_file() else []
        panel_labels = [
            value for value in text_values if re.fullmatch(r"\([a-z]\)", value)
        ]
        bare_labels = [
            value for value in text_values if re.fullmatch(r"[A-Za-z]", value)
        ]
        outputs = [png, svg, pdf]
        fresh = all(
            path.is_file() and path.stat().st_mtime_ns >= source_latest
            for path in outputs
        )
        records.append({
            "stem": stem,
            "png": png.is_file(),
            "svg": svg.is_file(),
            "pdf": pdf.is_file(),
            "png_size_px": size,
            "png_nonblank": nonblank,
            "svg_text_elements": len(text_values),
            "svg_arial_declared": any(
                family in svg_source for family in ("Arial", "Helvetica", "Liberation Sans")
            ),
            "panel_labels": panel_labels,
            "nonconforming_bare_panel_labels": bare_labels,
            "fresh_vs_sources": fresh,
        })
    for row in records:
        row["passed"] = bool(
            row["png"]
            and row["svg"]
            and row["pdf"]
            and row["png_nonblank"]
            and row["svg_arial_declared"]
            and not row["nonconforming_bare_panel_labels"]
            and row["fresh_vs_sources"]
        )
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "figure_dir": str(figure_dir),
        "figures": len(records),
        "failed": sum(not row["passed"] for row in records),
        "all_passed": bool(records) and all(row["passed"] for row in records),
        "records": records,
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-d7-local-sha256", required=True)
    args = parser.parse_args()
    checks: list[dict[str, object]] = []

    d1_data = ROOT / "D1 Sensor health" / "outputs" / "data"
    d1_release_path = d1_data / "D1_release_manifest.json"
    d1_release = load_json(d1_release_path)
    for artifact in d1_release["artifacts"]:
        path = ROOT / "D1 Sensor health" / artifact["path"]
        actual = sha256_file(path)
        record(checks, f"D1:{path.name}", actual == artifact["sha256"], actual)

    d2_manifest = load_json(
        ROOT
        / "D2 Temporal Continuity & Information Availability"
        / "artifacts"
        / "data"
        / "D2_d1_linkage_manifest.json"
    )
    record(
        checks,
        "D2:D1_release_id",
        d2_manifest.get("d1_release_id") == d1_release["release_id"],
        d2_manifest.get("d1_release_id"),
    )
    record(
        checks,
        "D2:core_scores_unchanged",
        d2_manifest.get("core_scores_unchanged")
        and d2_manifest.get("core_score_sha256_before")
        == d2_manifest.get("core_score_sha256_after"),
        d2_manifest.get("core_score_sha256_after"),
    )

    d6_root = ROOT / "D6 Parallel-redundancy Temporal Consistency"
    d6_manifest = load_json(d6_root / "outputs" / "data" / "D6_run_manifest.json")
    d6_dependencies = {
        item["dependency"]: item["sha256"] for item in d6_manifest["dependencies"]
    }
    expected_d1 = {
        item["path"].split("/")[-1]: item["sha256"] for item in d1_release["artifacts"]
    }
    record(
        checks,
        "D6:D1_scores_hash",
        d6_dependencies.get("d1_scores") == expected_d1["D1_main_scores_min.xlsx"],
        d6_dependencies.get("d1_scores"),
    )
    record(
        checks,
        "D6:regime_hash",
        d6_dependencies.get("regime_templates") == expected_d1["D1_regime_templates.xlsx"],
        d6_dependencies.get("regime_templates"),
    )
    d6_scores = pd.read_excel(
        d6_root / "outputs" / "data" / "D6_main_scores.xlsx",
        sheet_name="main_scores",
        usecols=["D6_forDQR", "D6_forDQR_is_final", "D6_forDQR_status"],
    )
    status_counts = d6_scores["D6_forDQR_status"].astype(str).value_counts().to_dict()
    allowed_pending_statuses = {"pending_D7_arbitration", "not_evaluable_or_D1_missing"}
    pending = (
        d6_scores["D6_forDQR"].isna().all()
        and not d6_scores["D6_forDQR_is_final"].fillna(False).astype(bool).any()
        and set(status_counts).issubset(allowed_pending_statuses)
        and status_counts.get("pending_D7_arbitration", 0) > 0
    )
    record(checks, "D6:D7_arbitration_pending", pending, status_counts)

    d7_root = ROOT / "D7 Topological Role Consistency and Structural Representativeness"
    d7_manifest = load_json(d7_root / "outputs" / "sensitivity" / "D7_sensitivity_manifest.json")
    d7_dependencies = {item["role"]: item for item in d7_manifest.get("dependencies", [])}
    record(
        checks,
        "D7_sensitivity:D1_release_id",
        d7_manifest.get("d1_release_id") == d1_release["release_id"],
        d7_manifest.get("d1_release_id"),
    )
    for role in ("D1_scores", "D2_scores", "D4_scores", "D7_local_evidence"):
        item = d7_dependencies.get(role, {})
        path = Path(str(item.get("path", "")))
        if not path.is_absolute():
            path = ROOT / path
        actual = sha256_file(path) if path.is_file() else None
        record(checks, f"D7_sensitivity:{role}", actual == item.get("sha256"), actual)
    record(
        checks,
        "D7_sensitivity:no_production_write",
        d7_manifest.get("production_write_permission") is False
        and d7_manifest.get("D7_forDQR_status") == "pending_not_produced"
        and d7_manifest.get("local_imported") is False,
        d7_manifest.get("D7_forDQR_status"),
    )

    local_hash = d7_local_core_sha256(d7_root / "outputs" / "local")
    record(
        checks,
        "D7_local:unchanged",
        local_hash == args.expected_d7_local_sha256,
        {"expected": args.expected_d7_local_sha256, "actual": local_hash},
    )

    audit_d1_release_equivalence(checks)
    for project, spec in FIGURE_PROJECTS.items():
        audit_figure_bundle(checks, project, spec)

    d4_root = ROOT / "D4 Physical rationality and rate constraints"
    write_detailed_figure_audit(
        d4_root / "outputs" / "figures",
        d4_root / "outputs" / "reports" / "figure_bundle_audit.json",
        [
            *list((d4_root / "outputs" / "data").glob("*")),
            *list((d4_root / "figures").glob("*.py")),
        ],
    )
    d6_root = ROOT / "D6 Parallel-redundancy Temporal Consistency"
    write_detailed_figure_audit(
        d6_root / "outputs" / "figures",
        d6_root / "outputs" / "qa" / "figure_bundle_audit.json",
        [
            *list((d6_root / "outputs" / "data").glob("*")),
            d6_root / "src" / "d6" / "figure_style.py",
            d6_root / "src" / "d6" / "figures.py",
        ],
    )

    result = {
        "schema_version": "cross-project-freshness-v2",
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "d1_release_id": d1_release["release_id"],
        "checks": checks,
        "n_checks": len(checks),
        "n_passed": sum(item["passed"] for item in checks),
        "all_passed": all(item["passed"] for item in checks),
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(result, indent=2, ensure_ascii=True), encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("n_checks", "n_passed", "all_passed")}))
    return 0 if result["all_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
