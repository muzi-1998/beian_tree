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
import yaml
from PIL import Image


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "cross_project_qa" / "cross_project_freshness_audit.json"
D5_LOCAL_CORE_FILES = (
    "D5_main_scores_hourly.parquet",
    "D5_report_interface.parquet",
    "D5_gate_interface.parquet",
    "D5_spatial_evidence.parquet",
    "D5_sensor_influence.parquet",
    "D5_support_assessment.parquet",
    "D5_regime_state.parquet",
    "D5_reference_window_library.parquet",
    "D5_event_windows.parquet",
    "D5_zone_consensus.parquet",
    "D5_spatial_templates.template_bundle.json",
    "D5_topology_registry.json",
    "D5_topology_registry.yaml",
    "D5_topology_evidence.yaml",
)
D1_DEPENDENCY_PATHS = {
    "strict_v1_inputs": "strict_v1_inputs.pkl",
    "raw_hourly": "raw_hourly.pkl",
    "state_machine_config": "configs/state_machine.yaml",
    "rules_config": "configs/rules.yaml",
    "mapping_config": "configs/mapping.yaml",
    "state_machine_code": "src/aggregation/cooldown_state_machine.py",
    "local_baseline_code": "src/baseline/local_baseline.py",
    "detector_bridge_code": "load_real_data_v11.py",
    "pls_detector_code": "src/detectors/drift_pls.py",
    "pls_peer_validation_code": "src/validation/pls_peer_upgrade.py",
    "pipeline_code": "run_v11_pipeline.py",
}
CANONICAL_PROJECT_DIRS = {
    "D1": "D1 Sensor health",
    "D2": "D2 Temporal Continuity & Information Availability",
    "D3": "D3 Physical rationality and rate constraints",
    "D4": "D4 Parallel-redundancy Temporal Consistency",
    "D5": "D5 Topological Role Consistency and Structural Representativeness",
}
RETIRED_TOP_LEVEL_DIRS = (
    "D4 Physical rationality and rate constraints",
    "D6 Parallel-redundancy Temporal Consistency",
    "D7 Topological Role Consistency and Structural Representativeness",
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
    "D3": {
        "roots": (
            ROOT
            / "D3 Physical rationality and rate constraints"
            / "outputs"
            / "figures",
        ),
        "source_globs": (
            ROOT
            / "D3 Physical rationality and rate constraints"
            / "outputs"
            / "data"
            / "*",
        ),
    },
    "D4-main": {
        "roots": (
            ROOT
            / "D4 Parallel-redundancy Temporal Consistency"
            / "outputs"
            / "figures",
        ),
        "source_globs": (
            ROOT
            / "D4 Parallel-redundancy Temporal Consistency"
            / "outputs"
            / "data"
            / "*",
        ),
    },
    "D4-sensitivity": {
        "roots": (
            ROOT
            / "D4 Parallel-redundancy Temporal Consistency"
            / "outputs"
            / "comparison",
        ),
        "source_globs": (
            ROOT
            / "D4 Parallel-redundancy Temporal Consistency"
            / "outputs"
            / "comparison"
            / "*.xlsx",
        ),
    },
    "D5": {
        "roots": (
            ROOT
            / "D5 Topological Role Consistency and Structural Representativeness"
            / "outputs"
            / "figures",
        ),
        "sources": (
            ROOT
            / "D5 Topological Role Consistency and Structural Representativeness"
            / "outputs"
            / "plot_data"
            / "D5_plot_data.parquet",
        ),
    },
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def d5_local_core_sha256(root: Path) -> str:
    digest = hashlib.sha256()
    for name in D5_LOCAL_CORE_FILES:
        path = root / name
        if not path.is_file():
            raise FileNotFoundError(f"Missing D5 Local core artifact: {path}")
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
    parser.add_argument("--expected-d5-local-sha256", required=True)
    args = parser.parse_args()
    checks: list[dict[str, object]] = []

    d1_data = ROOT / "D1 Sensor health" / "outputs" / "data"
    d1_release_path = d1_data / "D1_release_manifest.json"
    d1_release = load_json(d1_release_path)
    for artifact in d1_release["artifacts"]:
        path = ROOT / "D1 Sensor health" / artifact["path"]
        actual = sha256_file(path)
        record(checks, f"D1:{path.name}", actual == artifact["sha256"], actual)
    d1_root = ROOT / CANONICAL_PROJECT_DIRS["D1"]
    d1_run_manifest = load_json(d1_root / "outputs" / "logs" / "D1_run_manifest.json")
    dependency_hashes = d1_run_manifest.get("dependency_hashes", {})
    for role, relative_path in D1_DEPENDENCY_PATHS.items():
        path = d1_root / relative_path
        actual = sha256_file(path) if path.is_file() else None
        record(
            checks,
            f"D1:dependency:{role}",
            actual == dependency_hashes.get(role),
            {"declared": dependency_hashes.get(role), "actual": actual},
        )
    d1_state = d1_root / "v11_state.pkl"
    actual_state_hash = sha256_file(d1_state)
    record(
        checks,
        "D1:state_pickle",
        actual_state_hash == d1_run_manifest.get("state_pickle_sha256"),
        actual_state_hash,
    )

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
    d2_core_path = (
        ROOT
        / CANONICAL_PROJECT_DIRS["D2"]
        / "artifacts"
        / "data"
        / "D2_main_scores_hourly.xlsx"
    )
    actual_d2_core_hash = sha256_file(d2_core_path)
    record(
        checks,
        "D2:core_scores_current_hash",
        actual_d2_core_hash == d2_manifest.get("core_score_sha256_after"),
        {
            "declared": d2_manifest.get("core_score_sha256_after"),
            "actual": actual_d2_core_hash,
        },
    )

    d3_root = ROOT / CANONICAL_PROJECT_DIRS["D3"]
    d3_manifest = load_json(d3_root / "outputs" / "manifest" / "run_manifest.json")
    d3_contract = d3_manifest.get("independence_contract", {})
    d3_independent = (
        d3_contract.get("D1_score_consumed") is False
        and d3_contract.get("D2_score_consumed") is False
        and d3_contract.get("regime_labels_consumed") is False
        and d3_contract.get("imputed_values_scored") is False
        and d3_contract.get("canonical_1_1_time_grid") is True
    )
    record(
        checks,
        "D3:independent_numeric_contract",
        d3_independent,
        d3_contract,
    )

    d4_root = ROOT / CANONICAL_PROJECT_DIRS["D4"]
    d4_manifest = load_json(d4_root / "outputs" / "data" / "D4_run_manifest.json")
    d4_dependencies = {
        item["dependency"]: item["sha256"] for item in d4_manifest["dependencies"]
    }
    expected_d1 = {
        item["path"].split("/")[-1]: item["sha256"] for item in d1_release["artifacts"]
    }
    record(
        checks,
        "D4:D1_scores_hash",
        d4_dependencies.get("d1_scores") == expected_d1["D1_main_scores_min.xlsx"],
        d4_dependencies.get("d1_scores"),
    )
    record(
        checks,
        "D4:regime_hash",
        d4_dependencies.get("regime_templates") == expected_d1["D1_regime_templates.xlsx"],
        d4_dependencies.get("regime_templates"),
    )
    d4_scores = pd.read_excel(
        d4_root / "outputs" / "data" / "D4_main_scores.xlsx",
        sheet_name="main_scores",
        usecols=["timestamp", "pair_id", "D4_raw", "D4_after_D1"],
    )
    d4_final = pd.read_parquet(
        d4_root
        / "outputs"
        / "integration"
        / "D4_D5_final_arbitration.parquet"
    )
    protected_equal = (
        d4_scores[["D4_raw", "D4_after_D1"]]
        .reset_index(drop=True)
        .equals(
            d4_final[["D4_raw", "D4_after_D1"]].reset_index(drop=True)
        )
    )
    finalization_valid = (
        protected_equal
        and d4_final["finalization_allowed"].any()
        and d4_final.loc[
            d4_final["finalization_allowed"], "D4_forDQR"
        ].notna().all()
        and np.isclose(
            d4_final["D4_numeric_adjustment"].dropna(), 0.0
        ).all()
    )
    record(
        checks,
        "D4:D5_non_destructive_final_arbitration",
        finalization_valid,
        {
            "finalized_rows": int(d4_final["finalization_allowed"].sum()),
            "gate_applicable_rows": int(d4_final["D4_gate_applicable"].sum()),
            "protected_equal": protected_equal,
        },
    )
    d4_readiness = load_json(
        d4_root
        / "outputs"
        / "integration"
        / "D4_D5_aggregation_readiness_manifest.json"
    )
    d4_raw_final = d4_final.loc[
        d4_final["finalization_allowed"], ["D4_raw", "D4_forDQR"]
    ].dropna()
    record(
        checks,
        "D4:raw_is_authoritative_numeric_source",
        d4_readiness.get("numeric_source") == "D4_raw"
        and d4_readiness.get("d1_role") == "interpretation_only"
        and np.allclose(d4_raw_final["D4_raw"], d4_raw_final["D4_forDQR"])
        and np.isclose(d4_readiness.get("max_abs_numeric_adjustment"), 0.0),
        {
            "numeric_source": d4_readiness.get("numeric_source"),
            "d1_role": d4_readiness.get("d1_role"),
            "max_abs_numeric_adjustment": d4_readiness.get(
                "max_abs_numeric_adjustment"
            ),
        },
    )

    d5_root = ROOT / CANONICAL_PROJECT_DIRS["D5"]
    d5_manifest = load_json(d5_root / "outputs" / "sensitivity" / "D5_sensitivity_manifest.json")
    d5_dependencies = {item["role"]: item for item in d5_manifest.get("dependencies", [])}
    record(
        checks,
        "D5_sensitivity:D1_release_id",
        d5_manifest.get("d1_release_id") == d1_release["release_id"],
        d5_manifest.get("d1_release_id"),
    )
    for role in ("D1_scores", "D2_scores", "D3_scores", "D5_local_evidence"):
        item = d5_dependencies.get(role, {})
        path = Path(str(item.get("path", "")))
        if not path.is_absolute():
            path = ROOT / path
        actual = sha256_file(path) if path.is_file() else None
        record(checks, f"D5_sensitivity:{role}", actual == item.get("sha256"), actual)
    record(
        checks,
        "D5_sensitivity:no_production_write",
        d5_manifest.get("production_write_permission") is False
        and d5_manifest.get("authoritative_interface_status")
        == "pending_not_produced"
        and d5_manifest.get("local_imported") is False,
        d5_manifest.get("authoritative_interface_status"),
    )

    d5_local_output = d5_root / "outputs" / "local"
    report_interface = pd.read_parquet(
        d5_local_output / "D5_report_interface.parquet"
    )
    gate_interface = pd.read_parquet(
        d5_local_output / "D5_gate_interface.parquet"
    )
    report_unique = not report_interface.duplicated(
        ["timestamp", "sensor_id"]
    ).any()
    gate_unique = not gate_interface.duplicated(
        ["timestamp", "pair_id"]
    ).any()
    record(
        checks,
        "D5_local:dual_interface_contract",
        report_unique
        and gate_unique
        and "D5_forDQR" not in report_interface
        and "D5_forDQR" not in gate_interface,
        {
            "report_rows": len(report_interface),
            "gate_rows": len(gate_interface),
            "report_unique_sensor_hour": report_unique,
            "gate_unique_pair_hour": gate_unique,
        },
    )
    veto_identity = gate_interface["veto_active"].fillna(False).equals(
        gate_interface["sensor_identity_veto_active"].fillna(False)
    )
    record(
        checks,
        "D5_local:guard_is_not_veto",
        veto_identity
        and gate_interface["attribution_suppressed"].fillna(False).equals(
            gate_interface["process_coherence_guard_active"].fillna(False)
        ),
        {
            "veto_equals_sensor_identity": veto_identity,
            "process_guard_rows": int(
                gate_interface[
                    "process_coherence_guard_active"
                ].fillna(False).sum()
            ),
            "sensor_veto_rows": int(
                gate_interface["sensor_identity_veto_active"]
                .fillna(False)
                .sum()
            ),
        },
    )
    d5_local_manifest = load_json(d5_local_output / "D5_run_manifest.json")
    d5_isolation = d5_local_manifest.get("track_isolation", {})
    record(
        checks,
        "D5_local:independent_numeric_track",
        d5_isolation.get("track_id") == "d5_local"
        and d5_isolation.get("upstream_score_consumed") is False
        and not d5_isolation.get("consumed_sources")
        and set(d5_isolation.get("forbidden_score_dimensions", []))
        == {"D1", "D2", "D3", "D4"},
        d5_isolation,
    )

    local_hash = d5_local_core_sha256(d5_local_output)
    record(
        checks,
        "D5_local:unchanged",
        local_hash == args.expected_d5_local_sha256,
        {"expected": args.expected_d5_local_sha256, "actual": local_hash},
    )

    registry = yaml.safe_load((ROOT / "dimension_registry.yaml").read_text(encoding="utf-8"))
    registry_dimensions = registry.get("canonical_dimensions", {})
    canonical_paths_valid = all(
        (ROOT / project_dir).is_dir()
        and registry_dimensions.get(dimension, {}).get("project_dir") == project_dir
        for dimension, project_dir in CANONICAL_PROJECT_DIRS.items()
    )
    retired_absent = all(not (ROOT / name).exists() for name in RETIRED_TOP_LEVEL_DIRS)
    record(
        checks,
        "D1-D5:canonical_numbering_and_paths",
        canonical_paths_valid
        and retired_absent
        and set(registry_dimensions) == set(CANONICAL_PROJECT_DIRS),
        {
            "canonical_paths_valid": canonical_paths_valid,
            "retired_top_level_dirs_absent": retired_absent,
            "registry_dimensions": sorted(registry_dimensions),
        },
    )
    primary_score_fields = {
        dimension: registry_dimensions.get(dimension, {}).get("primary_score")
        for dimension in CANONICAL_PROJECT_DIRS
    }
    primary_fields_valid = (
        primary_score_fields
        == {
            "D1": "D1_total",
            "D2": "D2_total",
            "D3": "D3_total",
            "D4": "D4_raw",
            "D5": "D5_report_score",
        }
        and "D1_total_hourly"
        in pd.ExcelFile(d1_data / "D1_main_scores_min.xlsx").sheet_names
        and "D2_total"
        in pd.read_excel(d2_core_path, sheet_name=0, nrows=1).columns
        and "D3_total"
        in pd.read_excel(
            d3_root / "outputs" / "data" / "D3_window_scores.xlsx",
            nrows=1,
        ).columns
        and "D4_raw" in d4_scores.columns
        and "D5_report_score" in report_interface.columns
    )
    record(
        checks,
        "D1-D5:authoritative_primary_score_fields",
        primary_fields_valid,
        primary_score_fields,
    )

    audit_d1_release_equivalence(checks)
    for project, spec in FIGURE_PROJECTS.items():
        audit_figure_bundle(checks, project, spec)

    d3_root = ROOT / CANONICAL_PROJECT_DIRS["D3"]
    write_detailed_figure_audit(
        d3_root / "outputs" / "figures",
        d3_root / "outputs" / "reports" / "figure_bundle_audit.json",
        [
            *list((d3_root / "outputs" / "data").glob("*")),
            *list((d3_root / "figures").glob("*.py")),
        ],
    )
    d4_root = ROOT / CANONICAL_PROJECT_DIRS["D4"]
    write_detailed_figure_audit(
        d4_root / "outputs" / "figures",
        d4_root / "outputs" / "qa" / "figure_bundle_audit.json",
        [
            *list((d4_root / "outputs" / "data").glob("*")),
            d4_root / "src" / "d4" / "figure_style.py",
            d4_root / "src" / "d4" / "figures.py",
        ],
    )

    result = {
        "schema_version": "cross-project-freshness-v4",
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
