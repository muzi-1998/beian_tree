"""Public post-run verification, independent of private input availability."""
import json
import re
from datetime import datetime
import xml.etree.ElementTree as ET

import numpy as np
import openpyxl
import pandas as pd
from PIL import Image

from opening_lock import verify_lock
from runtime import OUTPUT, START, END


def verify():
    verify_lock()
    root = OUTPUT / "T0_results"
    summary = json.loads((root / "T0_numerical_qa.json").read_text())
    node = pd.read_parquet(root / "DQR_node.parquet")
    pair = pd.read_parquet(root / "DQR_pair.parquet")
    d5 = pd.read_parquet(root / "D5_scores.parquet")
    assert len(node) == summary["n_node_hours"] == 36288
    assert len(pair) == summary["n_pair_hours"] == 18144
    assert node.timestamp.min() == START and node.timestamp.max() == END-pd.Timedelta(hours=1)
    assert not node.duplicated(["timestamp", "sensor_id"]).any()
    assert node.groupby("timestamp").size().eq(14).all()
    assert pair.groupby("timestamp").size().eq(7).all()
    for field in ["D1_total", "D2_total", "D5_report_score", "Q_node_core12", "Q_node_full", "Q_node_available"]:
        x = node[field].dropna()
        assert x.between(1, 5).all(), field
    for dim in ["D1", "D2", "D3", "D5"]:
        assert not (node[f"{dim}_available_at"] > node.decision_at).any()
    assert not (pair.D4_available_at > pair.decision_at).any()
    assert np.allclose(node.Q_node_core12, (node.D1_total+node.D2_total)/2, equal_nan=True)
    assert np.allclose(node.Q_node_full, (node.D1_total+node.D2_total+node.D5_report_score)/3, equal_nan=True)
    numerator = node.D1_total+node.D2_total+node.D5_report_score.fillna(0)
    assert np.allclose(node.Q_node_available, numerator/(2+node.I_D5.astype(int)), equal_nan=True)
    assert np.allclose(pair.Q_pair_core, ((pair.left_Q_node_core12+pair.right_Q_node_core12+pair.D4_raw)/3).where(pair.I_D4), equal_nan=True)
    assert d5.loc[d5.support_level.eq("L1"), "D5_for_validation"].isna().all()
    assert d5.loc[~d5.context_observed | ~d5.current_observed, "D5_for_validation"].isna().all()
    assert d5.D5_for_validation.notna().sum() == summary["D5_report_evaluable"]
    assert node.coverage_class.value_counts().to_dict() == summary["node_coverage"]
    assert node.loc[node.timestamp.eq(END-pd.Timedelta(hours=1)), "D1_total"].isna().all()
    assert node.loc[node.D3_gate_status.eq("NotEvaluated"), "release_status"].isin(["gate_not_evaluated", "not_evaluable"]).all()
    source = OUTPUT / "source_data/T0"
    tables = json.loads((source / "workbook_tables.json").read_text())
    wb = openpyxl.load_workbook(source / "Temporal_holdout_T0_source.xlsx", read_only=True, data_only=True)
    count = 0
    assert wb.sheetnames == [t["name"] for t in tables]
    for table in tables:
        actual = list(wb[table["name"]].values)
        expected = [table["columns"], *table["rows"]]
        assert len(actual) == len(expected)
        for a, b in zip(actual, expected):
            for x, y in zip(a, b):
                if isinstance(y, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}( \d{2}:\d{2}:\d{2})?", y):
                    assert isinstance(x, datetime) and abs((pd.Timestamp(x)-pd.Timestamp(y)).total_seconds()) < .01
                elif isinstance(y, (int, float)):
                    assert isinstance(x, (int, float)) and np.isclose(x, y, atol=1e-12, rtol=1e-12)
                else:
                    assert x == y, (table["name"], x, y)
                count += 1
    wb.close()
    for name in ["Holdout_H3_frozen_coverage_boundary", "Holdout_H4_time_aligned_quality_burden"]:
        svg = ET.parse(OUTPUT / "figures" / f"{name}.svg").getroot()
        assert abs(float(svg.attrib["width"].removesuffix("pt"))*25.4/72-183) < .01
        assert len(svg.findall(".//{http://www.w3.org/2000/svg}text")) > 20
        with Image.open(OUTPUT / "figures" / f"{name}.tiff") as im:
            assert im.width >= 4300 and im.info["dpi"][0] >= 599
        with Image.open(OUTPUT / "figures" / f"{name}.png") as im:
            assert np.asarray(im.convert("RGB")).std() > 10
    print(json.dumps(dict(T0_results_verified=True, workbook_cells=count,
        code_config_asset_lock="exact_match", natural_scoring_complete=True, full_research_validation_complete=False)))


if __name__ == "__main__":
    verify()
