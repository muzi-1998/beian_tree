from __future__ import annotations

import hashlib
import json
from pathlib import Path

import yaml
import pandas as pd

from .figures import generate_all
from .reporting import write_report
from .validation import build_applicability_surface


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def finalize_run(challenger_root: Path, output_dir: Path) -> None:
    data_dir = output_dir / "data"
    thresholds = json.loads((data_dir / "D1_challenger_thresholds.json").read_text(encoding="utf-8"))
    with (challenger_root / "configs" / "challenger_sap.yaml").open("r", encoding="utf-8") as handle:
        sap = yaml.safe_load(handle)
    trials = pd.read_parquet(data_dir / "D1_challenger_trials.parquet")
    surface = build_applicability_surface(
        trials, int(sap["reporting"]["sparse_cell_min_clusters"])
    )
    surface.to_parquet(data_dir / "D1_challenger_applicability_surface.parquet", index=False)
    workbook = data_dir / "D1_challenger_source_data.xlsx"
    with pd.ExcelWriter(workbook, engine="openpyxl", mode="a", if_sheet_exists="replace") as writer:
        surface.to_excel(writer, sheet_name="applicability", index=False)
    generate_all(output_dir, thresholds)
    write_report(output_dir, sap)
    manifest_path = output_dir / "run_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["outputs"] = {}
    for path in sorted(output_dir.rglob("*")):
        if path.is_file() and path != manifest_path:
            manifest["outputs"][str(path.relative_to(output_dir))] = _sha256(path)
    temporary = manifest_path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(manifest_path)
