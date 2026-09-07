"""Exercise the connected Strict/Sensitive entry point before opening holdout."""
from pathlib import Path
import tempfile

import numpy as np
import pandas as pd

from run_dimension_inference import d2
from runtime import OUTPUT, write_json
from audit_d2_causality import pipeline


def main():
    index = pd.date_range("2026-02-01", periods=4*1440, freq="min")
    t = np.arange(len(index))
    raw = pd.DataFrame({s: (0.1 if s.endswith("_4") else 2.) + .04*np.sin(t*.9)
        if s.startswith("DO") else -120+10*np.sin(t*.9) for s in pipeline.SCORED_CHANNELS}, index=index)
    cut = 3*1440
    raw.iloc[cut-2:cut+60] = np.nan
    raw.loc[index[1800:2800], "ORP_1_2"] = -120.
    with tempfile.TemporaryDirectory(prefix="d2-connected-") as directory:
        root = Path(directory)
        for label, data in [("full", raw), ("prefix", raw.iloc[:cut])]:
            folder = root/label
            folder.mkdir()
            d2(data, folder)
        rows = []
        for name in ["D2_scores", "D2_evidence"]:
            a = pd.read_parquet(root/"prefix"/(name+".parquet")).set_index(["timestamp", "sensor_id"])
            b = pd.read_parquet(root/"full"/(name+".parquet")).set_index(["timestamp", "sensor_id"]).reindex(a.index)
            pd.testing.assert_frame_equal(a, b, check_dtype=False)
            rows.append(dict(artifact=name, rows=len(a), columns=len(a.columns), prefix_equal=True))
    write_json(OUTPUT/"audit/D2_connected_prefix_qa.json", dict(passed=True,
        Strict_and_Sensitive_tested=True, frozen_response_loss_reference=True,
        unknown_source_timestamp_metrics=True, comparisons=rows, holdout_opened=False))
    print(rows)


if __name__ == "__main__":
    main()
