"""Separate-process runners avoid the legacy projects' shared 'src' package."""
from __future__ import annotations

import argparse
import hashlib
import json
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

from inference_inputs import load_raw, cache_folder
from runtime import HERE, OFFICIAL, OUTPUT, PROJECT, DIMENSIONS, START, END, write_json, content_hash


def d1(raw, folder):
    from d1_frozen_adapter import FrozenD1
    model = FrozenD1()
    processed, residual, innovation = [pd.read_parquet(folder / f"{key}.parquet")
                                       for key in ["processed", "residual", "innovation"]]
    scores, detectors, events = model.predict(raw, processed, residual, innovation)
    scores.to_parquet(folder / "D1_scores.parquet", index=False)
    detectors.to_parquet(folder / "D1_detector_evidence.parquet", index=False)
    pd.Series(model.regime_labels(raw.resample("h").mean())).to_frame().to_parquet(folder / "D4_regime_labels.parquet")
    write_json(folder / "D1_events.json", events)
    if raw.index.max() < START:
        rows = []
        for sensor, block in scores.groupby("sensor_id"):
            old = model.state["D1_v11"][sensor]
            actual = block.set_index("timestamp").D1_total.reindex(old.index)
            rows.append(dict(sensor_id=sensor, n_hours=len(old),
                maximum_error=float((actual-old).abs().max()), na_mismatches=int(actual.isna().ne(old.isna()).sum())))
        table = pd.DataFrame(rows)
        table.to_csv(OUTPUT / "audit/D1_continuation_journal_replay.csv", index=False)
        if table.maximum_error.gt(1e-8).any() or table.na_mismatches.sum():
            raise RuntimeError("D1 continuation changed frozen history")


def d2(raw, folder):
    from audit_d2_causality import pipeline
    import d2_causal_adapter as causal
    pipeline.CACHE = folder
    digest = hashlib.sha256(pd.util.hash_pandas_object(raw, index=True).to_numpy().tobytes())
    for path in [HERE / "d2_causal_adapter.py", HERE / "causal_gap_evidence.py", Path(pipeline.__file__),
                 PROJECT / DIMENSIONS["D2"] / "d2_calibration.yaml"]:
        digest.update(content_hash(path).encode())
    pipeline.CACHE_KEY = digest.hexdigest()[:24]
    pipeline.SOURCE_TIMESTAMP_AUDIT = {"hourly": pd.DataFrame()}
    calibration = yaml.safe_load((PROJECT / DIMENSIONS["D2"] / "d2_calibration.yaml").read_text(encoding="utf-8"))
    flags = causal.preprocess(raw[pipeline.SCORED_CHANNELS], pipeline)
    stats = causal.window_stats(flags, pipeline)
    p50, p05, p50d, p05d = pipeline._build_bench_var_lookup(calibration)
    reference = {**calibration, "bench_var_P50": p50, "bench_var_P05": p05,
                 "bench_var_P50_default": p50d, "bench_var_P05_default": p05d}
    response = pipeline.compute_response_loss_tier1(flags, reference)
    subs = pipeline.compute_subscores(stats, response, calibration)
    result, _ = pipeline.aggregate_d2(subs, calibration)
    scores = pd.concat([frame.assign(sensor_id=s).rename_axis("timestamp").reset_index()
                        for s, frame in result.items()], ignore_index=True)
    scores["available_at"] = scores.timestamp + pd.Timedelta(hours=1)
    scores["source_timestamp_metrics_observable"] = False
    scores["run_id"] = "HOLDOUT-T0-D2-CAUSAL"
    scores = scores.drop(columns=["grade"], errors="ignore")
    scores.to_parquet(folder / "D2_scores.parquet", index=False)
    pd.concat([frame.assign(sensor_id=s).rename_axis("timestamp").reset_index()
               for s, frame in subs.items()]).to_parquet(folder / "D2_evidence.parquet", index=False)


def d3(raw, folder, holdout):
    from replay_d3 import D3, load_frozen_thresholds, D3Pipeline, load_temperature_proxy
    def config(name):
        return yaml.safe_load((D3 / f"configs/d3_{name}.yaml").read_text(encoding="utf-8"))
    configs = {name: config(name) for name in ["physical_bounds", "rate_limits", "mapping", "rules", "dag"]}
    meta = config("sensors")["sensors"]
    sensors = [row["id"] for row in meta]
    thresholds = load_frozen_thresholds(configs, sensors)
    temperature = load_temperature_proxy(config("paths"), OFFICIAL / DIMENSIONS["D3"]).reindex(raw.index)
    # D3 is strictly local to disjoint 2h windows, with no online fitted state.
    starts = (pd.date_range(START-pd.Timedelta(days=1), END-pd.Timedelta(days=1), freq="D") if holdout
              else pd.to_datetime(["2025-08-15", "2025-10-15", "2025-12-15", "2026-02-15", "2026-04-10"]))
    rows = []
    for start in starts:
        data = raw.loc[(raw.index >= start) & (raw.index < start+pd.Timedelta(days=1)), sensors]
        result = D3Pipeline(data, sensors, meta, thresholds, configs, "HOLDOUT-T0-D3", temperature_c=temperature).run()
        rows.append(result["main_scores"])
        print("D3 frozen 2h windows", str(start.date()), flush=True)
    frame = pd.concat(rows, ignore_index=True).rename(columns={"ts": "timestamp"})
    frame["available_at"] = frame.timestamp
    frame.to_parquet(folder / "D3_scores.parquet", index=False)


def d4(raw, folder):
    from d4_frozen_adapter import FrozenD4
    residual = pd.read_parquet(folder / "residual.parquet")
    engine = FrozenD4()
    closed = (residual.index[-1]+pd.Timedelta(minutes=1)).floor("h")-pd.Timedelta(hours=1)
    risks = engine.risks(residual, last_closed_hour=closed)
    risks.to_parquet(folder / "D4_risks.parquet", index=False)
    regime = pd.read_parquet(folder / "D4_regime_labels.parquet").regime_id
    scores = engine.score(risks, regime, pd.read_parquet(folder / "D2_scores.parquet"))
    scores.to_parquet(folder / "D4_scores.parquet", index=False)


def d5(raw, folder):
    from d5_frozen_adapter import FrozenD5
    scores, state, _ = FrozenD5().predict(raw)
    scores.to_parquet(folder / "D5_scores.parquet", index=False)
    state.to_parquet(folder / "D5_regime_state.parquet", index=False)


def dqr(raw, folder, holdout):
    from dqr_asof_adapter import assemble
    inputs = [pd.read_parquet(folder / f"{dim}_scores.parquet") for dim in ["D1", "D2", "D3", "D4", "D5"]]
    labels = (pd.date_range(START, END-pd.Timedelta(hours=1), freq="h") if holdout
              else pd.date_range("2026-04-10", "2026-04-10 23:00", freq="h"))
    node, pair, audit = assemble(*inputs, labels)
    for name, frame in [("DQR_node", node), ("DQR_pair", pair), ("DQR_time_join", audit)]:
        frame.to_parquet(folder / f"{name}.parquet", index=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("dimension", choices=["D1", "D2", "D3", "D4", "D5", "DQR"])
    parser.add_argument("--holdout", action="store_true")
    args = parser.parse_args()
    raw = load_raw(holdout=args.holdout)
    folder = cache_folder(args.holdout)
    if args.dimension in {"D3", "DQR"}:
        globals()[args.dimension.lower()](raw, folder, args.holdout)
    else:
        globals()[args.dimension.lower()](raw, folder)
    print(args.dimension, "completed", "later-period" if args.holdout else "historical", flush=True)


if __name__ == "__main__":
    main()
