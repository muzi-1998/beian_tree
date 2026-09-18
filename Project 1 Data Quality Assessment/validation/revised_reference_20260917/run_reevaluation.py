"""Re-evaluate the already inspected 108 days without refitting on later data.

The T0 checkout is an explicit, hashed archival input; no file there is modified.
Run D3, D4 and DQR in separate processes to isolate legacy `src` namespaces.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
OUT = HERE / "outputs"
START, END = pd.Timestamp("2026-04-14"), pd.Timestamp("2026-07-31")
RUN = "REVISED-REFERENCE-20260917"


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def raw_input(t0):
    historical = PROJECT / "1.1 Decomposition/outputs/parquet/time_base_1min_raw.parquet"
    old = pd.read_parquet(historical)
    folder = PROJECT / "1.1 Decomposition/Raw data/09_25.08.01-26.07.30_all data"
    paths = list(folder.glob("*分钟数据*_02_shengwuchi.csv"))
    if len(paths) != 1 or sha(paths[0]) != "18cb7f4617095655d1cb15a932621a5fbf58ac6b8b16a092e6586caba5aa4856":
        raise ValueError("Annual raw minute source differs from the T0 opening contract")
    mapping = pd.read_csv(t0 / "intake_audit/channel_mapping.csv")
    frame = pd.read_csv(paths[0], encoding="utf-8-sig", low_memory=False)
    frame.index = pd.to_datetime(frame.iloc[:, 0], errors="raise")
    frame = frame[mapping.source_column].rename(columns=dict(zip(mapping.source_column, mapping.canonical_id)))
    frame = frame.apply(pd.to_numeric, errors="raise")[old.columns]
    result = pd.concat([old, frame.loc[(frame.index >= START) & (frame.index < END)]])
    if not result.index.equals(pd.date_range(old.index[0], END-pd.Timedelta(minutes=1), freq="min")):
        raise ValueError("Re-evaluation requires the exact complete minute clock, with NA retained")
    return result, [historical, paths[0], t0 / "intake_audit/channel_mapping.csv"]


def d3(t0):
    root = PROJECT / "D3 Physical rationality and rate constraints"
    sys.path.insert(0, str(root))
    from src.common.benchmark_windows import BenchmarkWindows, FixedTailThreshold
    from src.d3_physical.threshold_store import PhysicalBound, ThresholdStore
    from src.pipeline.d3_pipeline import D3Pipeline
    from src.data.input_loader import load_temperature_proxy
    def cfg(name):
        return yaml.safe_load((root / f"configs/d3_{name}.yaml").read_text(encoding="utf-8"))
    configs = {name: cfg(name) for name in ["physical_bounds", "rate_limits", "mapping", "rules", "dag"]}
    meta = cfg("sensors")["sensors"]
    sensors = [r["id"] for r in meta]
    benchmark = BenchmarkWindows(pd.DataFrame(columns=sensors), sensors)
    bounds = []
    table_path = root / "outputs/data/D3_threshold_library.xlsx"
    for row in pd.read_excel(table_path).to_dict("records"):
        fields = {k: row[k] for k in PhysicalBound.__dataclass_fields__}
        fields["benchmark_window_ids"] = tuple(row["benchmark_window_ids"].split(",")) if isinstance(row["benchmark_window_ids"], str) else ()
        for side in ["low", "high"]:
            fields[side] = None if pd.isna(fields[side]) else float(fields[side])
        bound = PhysicalBound(**fields)
        bounds.append(bound)
        if bound.bound_type == "boundary":
            side = "low" if bound.low is not None else "high"
            benchmark._fixed_tails[(bound.sensor_scope, side)] = FixedTailThreshold(bound.sensor_scope, side,
                bound.low if side == "low" else bound.high, bound.source, bound.version, bound.benchmark_window_ids)
    base = ThresholdStore.build(configs["physical_bounds"], configs["rate_limits"], BenchmarkWindows(pd.DataFrame(), sensors))
    thresholds = ThresholdStore(bounds, benchmark, base.sensor_policies)
    raw, inputs = raw_input(t0)
    raw = raw.loc[raw.index >= START-pd.Timedelta(days=1), sensors]
    temperature = load_temperature_proxy(cfg("paths"), root).reindex(raw.index)
    result = D3Pipeline(raw, sensors, meta, thresholds, configs, RUN+"-D3", temperature_c=temperature).run()["main_scores"]
    result = result.rename(columns={"ts": "timestamp"})
    result["available_at"] = result.timestamp
    result.to_parquet(OUT / "D3_scores.parquet", index=False)
    return [*inputs, table_path, *sorted((root / "configs").glob("*.yaml"))]


def d4(t0):
    root = PROJECT / "D4 Parallel-redundancy Temporal Consistency"
    sys.path[:0] = [str(root / "src"), str(PROJECT), str(t0)]
    from causal_change_points import causal_change_timeline
    from shared_data_foundation.inference import infer_context
    from shared_data_foundation.context import pair_support
    from d4.config import load_config
    import d4.pipeline as pipeline
    from d4.scoring import score_from_quantiles, aggregate_scores
    cfg = load_config(root / "configs/d4.yaml", PROJECT)
    raw, inputs = raw_input(t0)
    asset_path = PROJECT / "shared_data_foundation/outputs/D4_context_manifest.json"
    asset = json.loads(asset_path.read_text())
    if pd.Timestamp(asset["fit_end"]) >= START:
        raise ValueError("Context was not fitted before the already-inspected re-evaluation period")
    context = infer_context(raw, asset)
    old_context = pd.read_parquet(PROJECT / "shared_data_foundation/outputs/D4_context_hourly.parquet")
    pd.testing.assert_series_equal(context.regime_id.reindex(old_context.index), old_context.regime_id)
    residual_path = t0 / ".local_qa/holdout_T0/residual.parquet"
    residuals = pd.read_parquet(residual_path)
    last_closed_hour = (residuals.index[-1] + pd.Timedelta(minutes=1)).floor("h") - pd.Timedelta(hours=1)
    residuals = residuals.loc[residuals.index < last_closed_hour + pd.Timedelta(hours=1)]
    columns = sorted({p.target for p in cfg.pairs} | {p.reference for p in cfg.pairs})
    freq = f"{cfg.analysis_interval_minutes}min"
    presence = raw[columns].notna()
    residuals = residuals[columns].where(presence).resample(freq).median().where(presence.resample(freq).mean().ge(cfg.common_support["min_fraction"]))
    # Retain enough raw history for all trailing windows and CP auxiliary evidence.
    residuals = residuals.loc[residuals.index >= START-pd.Timedelta(days=10)]
    def causal(hourly, labels, **kwargs):
        result = causal_change_timeline(hourly, labels+pd.Timedelta(hours=1), **kwargs)
        result.index = labels
        return result
    pipeline.adjacent_ks_change_timeline = causal
    parts = []
    for pair in cfg.pairs:
        risks = pipeline._pair_metrics(residuals, pair, cfg)
        risks = risks.merge(pair_support(raw, pair.target, pair.reference), left_on="timestamp", right_index=True, validate="one_to_one")
        parts.append(risks)
        print("Revised causal D4", pair.pair_id, flush=True)
    result = pd.concat(parts, ignore_index=True).merge(context, left_on="timestamp", right_index=True, validate="many_to_one")
    mapping_path = root / "outputs/data/D4_mapping_params.xlsx"
    mapping = pd.read_excel(mapping_path, sheet_name="public_quantiles")
    for q in ["Q_dist", "Q_trend", "Q_var"]:
        result[q] = np.nan
        for row in mapping.loc[mapping.subscore.eq(q)].itertuples(index=False):
            mask = result.variable.eq(row.variable) & result.regime_id.eq(row.regime_id)
            result.loc[mask, q] = score_from_quantiles(result.loc[mask, row.risk_metric].to_numpy(),
                np.array([row.q50, row.q75, row.q90, row.q97_5]))
    metadata = mapping.loc[mapping.mapping_role.eq("production")].groupby(["variable", "regime_id"], as_index=False).agg(
        calibration_scope=("mapping_scope", lambda x: "|".join(sorted(set(x)))),
        calibration_quality=("calibration_quality", lambda x: "|".join(sorted(set(x)))),
        calibration_evidence_quality=("mapping_evidence_quality", lambda x: "|".join(sorted(set(x)))),
        calibration_independent_blocks=("independent_blocks", "min"),
        calibration_tail_precision_grade=("percentile_precision_grade", lambda x: "wide_interval" if "wide_interval" in set(x) else "supported"))
    result = result.merge(metadata, on=["variable", "regime_id"], how="left", validate="many_to_one")
    result.loc[result.deadband_active, "Q_var"] = 5.
    result["D4_base"], result["D4_raw"] = aggregate_scores(*(result[q].to_numpy() for q in ["Q_dist", "Q_trend", "Q_var", "Q_cp"]), weights=cfg.weights, lambda_blend=cfg.lambda_blend)
    fraction = cfg.common_support["min_fraction"]
    hour_fraction = cfg.common_support["trend_min_common_hour_fraction"]
    result["usable_for_D4"] = (result.raw_complete_window & result.raw_common_fraction_24h.ge(fraction)
        & result.raw_supported_hours_fraction.ge(hour_fraction) & result.valid_fraction_common.ge(fraction)
        & result.valid_fraction_common_hours.ge(hour_fraction) & result.regime_id.notna() & result.D4_raw.notna())
    result["D4_for_validation"] = result.D4_raw.where(result.usable_for_D4)
    result["available_at"] = result.timestamp + pd.Timedelta(hours=1, minutes=3)
    result["interval_start"] = result.timestamp-pd.Timedelta(hours=23)
    result["interval_end_exclusive"] = result.timestamp+pd.Timedelta(hours=1)
    result["run_id"] = RUN+"-D4"
    result["D1_D2_scores_consumed"] = False
    result.to_parquet(OUT / "D4_scores.parquet", index=False)
    return [*inputs, residual_path, asset_path, mapping_path, root / "configs/d4.yaml", t0 / "causal_change_points.py"]


def dqr(t0):
    root = PROJECT / "DQR Multidimensional Aggregation and Evidence-Aware Integration"
    sys.path.insert(0, str(root / "src"))
    from dqr_aggregation.common import load_config
    from dqr_aggregation.pipeline import build_node_scores, build_pair_scores
    # The archived as-of operator is reused with its native aggregation imports
    # already bound to the current project; no archived module is edited.
    sys.path.insert(0, str(t0))
    from dqr_asof_adapter import asof_evidence
    folder = t0 / ".local_qa/holdout_T0"
    inputs = {d: (OUT if d in ["D3", "D4"] else folder) / f"{d}_scores.parquet" for d in ["D1", "D2", "D3", "D4", "D5"]}
    frames = {d: pd.read_parquet(p) for d, p in inputs.items()}
    labels = pd.date_range(START, END-pd.Timedelta(hours=1), freq="h")
    grid = pd.MultiIndex.from_product([labels, sorted(frames["D5"].sensor_id.unique())], names=["timestamp", "sensor_id"]).to_frame(index=False)
    grid["decision_at"] = grid.timestamp+pd.Timedelta(hours=1, minutes=3)
    aligned = {d: asof_evidence(grid, frames[d], dimension=d, object_id="sensor_id", lifetime="2h" if d=="D3" else "1h") for d in ["D1","D2","D3","D5"]}
    keys = ["timestamp", "sensor_id"]
    a, b, c, e = [aligned[d] for d in ["D1","D2","D3","D5"]]
    a["D1_total"] = a.D1_for_validation
    b = b.rename(columns={"veto_flag": "D2_veto_flag", "usable_tag": "D2_usable_tag"})
    e["D5_report_score"] = e.D5_for_validation
    config = load_config()
    node = build_node_scores(config, a[keys+["D1_total"]], b[keys+["D2_total","D2_veto_flag","D2_usable_tag"]], c[keys+["D3_gate_status"]], e)
    pairgrid = pd.MultiIndex.from_product([labels, sorted(frames["D4"].pair_id.unique())], names=["timestamp","pair_id"]).to_frame(index=False)
    pairgrid["decision_at"] = pairgrid.timestamp+pd.Timedelta(hours=1, minutes=3)
    d = asof_evidence(pairgrid, frames["D4"], dimension="D4", object_id="pair_id", lifetime="1h")
    identities = frames["D4"][["pair_id","sensor_id","pair_sensor_id"]].drop_duplicates().set_index("pair_id")
    for name in ["sensor_id","pair_sensor_id"]:
        d[name] = d.pair_id.map(identities[name])
    pair = build_pair_scores(config, node, d)
    audit = grid.copy()
    for dim, values in aligned.items():
        audit = audit.merge(values[keys+[dim+"_source_label", dim+"_available_at"]], on=keys, validate="one_to_one")
    node = node.merge(audit, on=keys, validate="one_to_one")
    for name, frame in [("DQR_node",node), ("DQR_pair",pair), ("DQR_time_join",audit)]:
        frame.to_parquet(OUT / f"{name}.parquet", index=False)
    return [*inputs.values(), t0 / "dqr_asof_adapter.py", root / "configs/aggregation_v2_4.yaml"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["D3", "D4", "DQR"])
    parser.add_argument("--t0-root", type=Path, required=True)
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    inputs = globals()[args.stage.lower()](args.t0_root)
    manifest = {"status": "revised_temporal_out_of_sample_re_evaluation_not_first_blind_test", "period": [str(START), str(END)],
                "run_id": RUN, "stage": args.stage, "no_later_refit": True,
                "inputs": [{"path": str(p), "sha256": sha(p)} for p in inputs],
                "outputs": {p.name: sha(p) for p in OUT.glob(args.stage+"*.parquet")}}
    (OUT / f"{args.stage}_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
