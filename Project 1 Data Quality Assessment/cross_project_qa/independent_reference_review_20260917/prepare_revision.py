"""Preserve released comparisons and calculate the new raw-reference lock."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
D3 = PROJECT / "D3 Physical rationality and rate constraints"
D4 = PROJECT / "D4 Parallel-redundancy Temporal Consistency"
sys.path.insert(0, str(D3))
from src.d3_physical.reference_eligibility import production_calibration_mask_from_raw
from src.validation.do_temperature_validation import _alpha_estimator


def main():
    frozen = HERE / "frozen_baseline"
    frozen.mkdir(exist_ok=True)
    manifest_path = frozen / "manifest.json"
    if not manifest_path.exists():
        registry = {}
        for label, path in {
            "D3_scores": D3 / "outputs/data/D3_window_scores.xlsx",
            "D4_scores": D4 / "outputs/data/D4_main_scores.xlsx",
            "D4_mapping": D4 / "outputs/data/D4_mapping_params.xlsx",
        }.items():
            pd.read_excel(path).to_parquet(frozen / f"{label}.parquet", index=False)
            registry[label] = {"source": path.relative_to(PROJECT).as_posix(),
                               "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        registry["frozen_git_commit"] = subprocess.check_output(
            ["git", "rev-parse", "main"], cwd=PROJECT, text=True).strip()
        manifest_path.write_text(json.dumps(registry, indent=2), encoding="utf-8")
    d = pd.read_parquet(D3 / "outputs/validation/D3_temperature_conditioned_DO_upper.parquet")
    screen_path = frozen / "D3_screened_reference.parquet"
    if not screen_path.exists():
        d[["ts", "sensor_id", "high_quality_evaluable", "frozen_alpha"]].to_parquet(screen_path, index=False)
    d["neutral_eligible"] = False
    for sensor, g in d.groupby("sensor_id"):
        idx = pd.DatetimeIndex(g.ts)
        mask = production_calibration_mask_from_raw(
            pd.Series(g.DO_minute_mg_L.to_numpy(), index=idx),
            pd.Series(g.influent_temperature_C.to_numpy(), index=idx),
            imputed=pd.Series(False, index=idx), time_valid=pd.Series(True, index=idx))
        d.loc[g.index, "neutral_eligible"] = mask.to_numpy()
    rows = []
    for position, g in d.loc[d.phase.eq("calibration") & d.neutral_eligible].groupby("position"):
        estimate = _alpha_estimator(g.DO_over_Csat.to_numpy())
        if len(g) < 43200:
            raise ValueError("Neutral calibration support below locked minimum")
        rows.append({"position": int(position), "alpha": estimate[0],
                     "n_sensor_minutes": len(g), "days": int(g.ts.dt.normalize().nunique()),
                     "screened_alpha": float(g.frozen_alpha.iloc[0])})
    (HERE / "neutral_alpha_lock.json").write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(json.dumps(rows, indent=2))


if __name__ == "__main__":
    main()
