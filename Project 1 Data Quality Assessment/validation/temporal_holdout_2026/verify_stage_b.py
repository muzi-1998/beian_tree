"""Public, reproducible checkpoint QA; scientific holdout gate must remain closed."""
from __future__ import annotations

import json
from datetime import datetime
import re
import xml.etree.ElementTree as ET

import numpy as np
import openpyxl
import pandas as pd
from PIL import Image

from runtime import HERE, PROJECT, OUTPUT, content_hash, sha256, require_opening_gate


def verify_workbook() -> int:
    sources = json.loads((OUTPUT / "source_data/workbook_tables.json").read_text(encoding="utf-8"))
    wb = openpyxl.load_workbook(OUTPUT / "source_data/Temporal_holdout_stage_B_source.xlsx", read_only=True, data_only=True)
    count = 0
    assert wb.sheetnames == [table["name"] for table in sources]
    for table in sources:
        sheet = wb[table["name"]]
        actual = list(sheet.values)
        expected = [table["columns"], *table["rows"]]
        assert len(actual) == len(expected), table["name"]
        for row, want in zip(actual, expected):
            assert len(row) == len(want), table["name"]
            for a, b in zip(row, want):
                if isinstance(b, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}( \d{2}:\d{2}:\d{2})?", b):
                    assert isinstance(a, datetime), (table["name"], a, b)
                    assert abs((pd.Timestamp(a)-pd.Timestamp(b)).total_seconds()) < .01
                elif isinstance(b, (int, float)) and not isinstance(b, bool):
                    assert isinstance(a, (int, float)) and np.isclose(a, b, atol=1e-12, rtol=1e-12), (a, b)
                else:
                    assert a == b, (table["name"], a, b)
                count += 1
    wb.close()
    return count


def main() -> None:
    manifest = json.loads((OUTPUT / "stage_B_manifest.json").read_text(encoding="utf-8"))
    repo = PROJECT.parent
    for kind in ["source_code_config", "imported_project_code_config", "artifacts"]:
        for name, expected in manifest[kind].items():
            path = (repo / name).resolve()
            assert path.is_relative_to(repo.resolve()), name
            assert path.is_file(), name
            actual = sha256(path) if kind == "artifacts" else content_hash(path)
            assert actual == expected, f"Stale {kind}: {name}"
    try:
        require_opening_gate(OUTPUT / "opening_gate.json")
    except RuntimeError:
        pass
    else:
        raise AssertionError("This partial checkpoint cannot open the future scoring gate")
    cp = pd.read_parquet(OUTPUT / "audit/D4_historical_CP_timing_rows.parquet")
    summary = pd.read_csv(OUTPUT / "audit/D4_historical_CP_timing_summary.csv")
    assert len(cp) == summary.n_pair_hours.sum() == 42847
    assert cp.Q_cp_changed.sum() == summary.changed_Q_cp_hours.sum()
    assert cp.low_tail_flip_on_common_support.sum() == summary.low_tail_flip_hours.sum()
    assert cp.timestamp.max() < pd.Timestamp("2026-04-14")
    d1 = json.loads((OUTPUT / "audit/D1_recovery_replay_qa.json").read_text())
    assert d1["native_replay_passed"] and d1["candidate_prefix_passed"] and d1["checkpoint_passed"]
    assert not d1["heldout_scores_computed"]
    d1_rows = pd.read_parquet(OUTPUT / "audit/D1_recovery_historical_rows.parquet")
    d1_summary = pd.read_csv(OUTPUT / "audit/D1_recovery_historical_replay.csv")
    assert len(d1_rows) == d1_summary.n_hours.sum() == d1["n_sensor_hours"] == 85932
    assert d1_rows.timestamp.max() < pd.Timestamp("2026-04-14")
    changed = (d1_rows.D1_native-d1_rows.D1_scheduled_candidate).abs().gt(1e-10).sum()
    assert changed == d1_summary.scheduled_score_changed_hours.sum()
    assert d1_rows.loc[~d1_rows.detector_evidence_complete, "D1_candidate_releasable"].isna().all()
    d1_prefix = pd.read_csv(OUTPUT / "audit/D1_recovery_prefix_audit.csv")
    assert len(d1_prefix) == 42
    assert d1["native_pelt_prefix_passed"] == bool(d1_prefix.native_candidate_symmetric_difference.eq(0).all())
    assert d1_prefix.candidate_event_prefix_equal.all() and d1_prefix.candidate_output_changed_hours.eq(0).all()
    alignment = json.loads((OUTPUT / "audit/minute_alignment_replay_qa.json").read_text())
    assert alignment["native_replay_passed"] and alignment["daily_checkpoint_passed"]
    assert alignment["fixed_preprocessing_publication_delay_minutes"] == 3
    assert not alignment["offline_diagnostic_overlays_used_in_causal_value_transform"]
    assert not alignment["holdout_opened"]
    d5 = json.loads((OUTPUT / "audit/D5_context_recovery_qa.json").read_text())
    assert d5["checks"]["archived_posterior_equal_1e_10"]
    assert not d5["checks"]["archived_model_hash_equal"]
    assert not d5["all_passed"], "Byte identity limitation must remain visible"
    for filename in ["D2_prefix_contract_qa.json", "D4_cp_prefix_contract_qa.json"]:
        audit = json.loads((OUTPUT / "audit" / filename).read_text())
        assert audit.get("all_evidence_prefix_invariant", audit.get("native_prefix_passed")) is False
    for name in ["Holdout_H1_scope_information_clock", "Holdout_H2_causality_counterexamples"]:
        root = ET.parse(OUTPUT / "figures" / f"{name}.svg").getroot()
        points = float(root.attrib["width"].removesuffix("pt"))
        assert abs(points*25.4/72-183) < .01
        assert len(root.findall(".//{http://www.w3.org/2000/svg}text")) > 10
        with Image.open(OUTPUT / "figures" / f"{name}.png") as image:
            pixels = np.array(image.convert("RGB"))
            assert pixels.std() > 10 and (pixels < 240).any(axis=2).mean() > .02
        with Image.open(OUTPUT / "figures" / f"{name}.tiff") as image:
            assert image.width >= 4300 and image.info["dpi"][0] >= 599
    cells = verify_workbook()
    print(json.dumps({"checkpoint_bundle_passed": True, "workbook_cells_verified": cells,
                      "current_code_config_and_artifact_hashes": "matched",
                      "scientific_holdout_ready": False, "holdout_opened": False}))


if __name__ == "__main__":
    main()
