"""Replay frozen D3 with an archived threshold library, never recalibrate."""
from __future__ import annotations

import sys

import numpy as np
import pandas as pd
import yaml

from runtime import DIMENSIONS, OFFICIAL, OUTPUT, PROJECT, START, sha256, write_json

D3 = PROJECT / DIMENSIONS["D3"]
sys.path.insert(0, str(D3))
from src.common.benchmark_windows import BenchmarkWindows, FixedTailThreshold
from src.d3_physical.threshold_store import PhysicalBound, ThresholdStore
from src.pipeline.d3_pipeline import D3Pipeline
from src.data.input_loader import load_temperature_proxy


def load_frozen_thresholds(configs: dict, sensors: list[str]) -> ThresholdStore:
    table = pd.read_excel(D3 / "outputs/data/D3_threshold_library.xlsx")
    benchmark = BenchmarkWindows(pd.DataFrame(columns=sensors), sensors)
    bounds = []
    for row in table.to_dict("records"):
        ids = row["benchmark_window_ids"]
        if not isinstance(ids, str):
            ids = ()
        else:
            ids = tuple(ids.split(",")) if ids else ()
        fields = {key: row[key] for key in PhysicalBound.__dataclass_fields__}
        fields["benchmark_window_ids"] = ids
        for name in ("low", "high"):
            fields[name] = None if pd.isna(fields[name]) else float(fields[name])
        bound = PhysicalBound(**fields)
        bounds.append(bound)
        if bound.bound_type == "boundary":
            side = "low" if bound.low is not None else "high"
            benchmark._fixed_tails[(bound.sensor_scope, side)] = FixedTailThreshold(
                bound.sensor_scope, side, bound.low if side == "low" else bound.high,
                bound.source, bound.version, ids)
    baseline_store = ThresholdStore.build(configs["physical_bounds"], configs["rate_limits"],
                                          BenchmarkWindows(pd.DataFrame(), sensors))
    return ThresholdStore(bounds, benchmark, baseline_store.sensor_policies)


def main() -> None:
    def config(name):
        return yaml.safe_load((D3 / f"configs/d3_{name}.yaml").read_text(encoding="utf-8"))
    configs = {name: config(name) for name in ("physical_bounds", "rate_limits", "mapping", "rules", "dag")}
    sensor_meta = config("sensors")["sensors"]
    sensors = [row["id"] for row in sensor_meta]
    thresholds = load_frozen_thresholds(configs, sensors)
    raw_path = OFFICIAL / "1.1 Decomposition/outputs/parquet/time_base_1min_raw.parquet"
    raw = pd.read_parquet(raw_path)[sensors]
    if raw.index.max() >= START:
        raise ValueError("D3 replay may not read holdout values")
    paths = config("paths")
    temperature = load_temperature_proxy(paths, OFFICIAL / DIMENSIONS["D3"]).reindex(raw.index)
    published = pd.read_excel(D3 / "outputs/data/D3_window_scores.xlsx")
    published["ts"] = pd.to_datetime(published.ts)
    published = published.set_index(["ts", "sensor_id"])
    # Fixed dates selected without inspecting the new period or old score extrema.
    starts = pd.to_datetime(["2025-08-15", "2025-10-15", "2025-12-15", "2026-02-15", "2026-04-10"])
    rows, comparisons = [], []
    for start in starts:
        stop = start + pd.Timedelta(hours=24)
        frame = raw.loc[(raw.index >= start) & (raw.index < stop)]
        out = D3Pipeline(frame, sensors, sensor_meta, thresholds, configs,
                         "HISTORICAL-REPLAY", temperature_c=temperature).run()
        now = out["main_scores"].set_index(["ts", "sensor_id"])
        old = published.reindex(now.index)
        for col in ("Q_value_hard", "Q_value_soft", "Q_persistent_rate", "D3_total"):
            error = (now[col] - old[col]).abs()
            rows.append({"day": str(start.date()), "metric": col, "n_windows": len(now),
                         "na_mismatches": int((now[col].isna() != old[col].isna()).sum()),
                         "max_abs_difference": float(error.max()),
                         "n_different_1e_8": int((error > 1e-8).sum())})
        comparison = now[["D3_total", "D3_gate_status", "evidence_status"]].join(
            old[["D3_total", "D3_gate_status", "evidence_status"]], rsuffix="_published").reset_index()
        comparisons.append(comparison)
        print(start.date(), "D3 replay", len(now), flush=True)
    table = pd.DataFrame(rows)
    comparison = pd.concat(comparisons, ignore_index=True)
    output = OUTPUT / "audit"
    output.mkdir(parents=True, exist_ok=True)
    table.to_csv(output / "D3_historical_replay.csv", index=False)
    comparison.to_parquet(output / "D3_historical_replay_rows.parquet", index=False)
    passed = (table.n_different_1e_8.sum() == 0 and table.na_mismatches.sum() == 0
              and comparison.D3_gate_status.eq(comparison.D3_gate_status_published).all()
              and comparison.evidence_status.eq(comparison.evidence_status_published).all())
    write_json(output / "D3_historical_replay_qa.json", {
        "passed": bool(passed), "n_sensor_windows": len(comparison),
        "numeric_tolerance": 1e-8,
        "na_and_gate_exact": bool(table.na_mismatches.sum() == 0
                                  and comparison.D3_gate_status.eq(comparison.D3_gate_status_published).all()
                                  and comparison.evidence_status.eq(comparison.evidence_status_published).all()),
        "new_period_scores_computed": False,
        "thresholds_refitted": False,
        "raw_source_sha256": sha256(raw_path),
        "threshold_library_sha256": sha256(D3 / "outputs/data/D3_threshold_library.xlsx"),
    })


if __name__ == "__main__":
    main()
