"""Natural-data outputs and descriptive estimands; never fit or select a model."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from inference_inputs import cache_folder
from opening_lock import verify_lock
from runtime import OUTPUT, START, END, write_json, sha256

RESULTS = OUTPUT / "T0_results"
SOURCE = OUTPUT / "source_data/T0"


def episodes(frame, score, object_id, dimension):
    """Extract on the original hourly clock, keeping boundary censoring visible."""
    rows = []
    for key, block in frame.groupby(object_id):
        block = block.sort_values("timestamp").set_index("timestamp")
        values = block[score].reindex(pd.date_range(START, END-pd.Timedelta(hours=1), freq="h"))
        low = values.lt(3).to_numpy()
        starts = np.flatnonzero(low & ~np.r_[False, low[:-1]])
        ends = np.flatnonzero(low & ~np.r_[low[1:], False])
        for a, b in zip(starts, ends):
            rows.append(dict(dimension=dimension, object_id=key, start=values.index[a],
                end_exclusive=values.index[b]+pd.Timedelta(hours=1), observed_duration_h=int(b-a+1),
                left_censored=bool(a == 0 or pd.isna(values.iloc[a-1])),
                right_censored=bool(b == len(values)-1 or pd.isna(values.iloc[b+1])),
                definition="one_or_more_contiguous_score_lt3_hours_descriptive_not_native_fault_event"))
    return pd.DataFrame(rows, columns=["dimension", "object_id", "start", "end_exclusive", "observed_duration_h",
        "left_censored", "right_censored", "definition"])


def summarize(frame, field, dimension, object_id):
    rows = []
    for key, block in frame.groupby(object_id):
        x = block[field]
        n = int(x.notna().sum())
        rows.append(dict(dimension=dimension, object_id=key, nominal_hours=2592, evaluated_hours=n,
            coverage_fraction=n/2592, low_hours=int(x.lt(3).sum()),
            low_hours_per_1000_evaluated=1000*x.lt(3).sum()/n if n else np.nan,
            sensor_or_pair_hour_pooled_mean=x.mean(), p05=x.quantile(.05), median=x.median(),
            veto_hours=int(block.veto_flag.eq(1).sum()) if "veto_flag" in block else np.nan))
    return pd.DataFrame(rows)


def main():
    lock = verify_lock(private_inputs=True)
    folder = cache_folder(True)
    RESULTS.mkdir(parents=True, exist_ok=True)
    SOURCE.mkdir(parents=True, exist_ok=True)
    frames, counts = {}, []
    for name in ["D1", "D2", "D3", "D4", "D5", "DQR_node", "DQR_pair", "DQR_time_join"]:
        filename = f"{name}_scores.parquet" if name.startswith("D") and not name.startswith("DQR") else f"{name}.parquet"
        data = pd.read_parquet(folder / filename)
        selected = (data.timestamp.gt(START) & data.timestamp.le(END) if name == "D3"
                    else data.timestamp.ge(START) & data.timestamp.lt(END))
        data = data.loc[selected].copy()
        data["validation_run_id"] = "HOLDOUT-T0-20260907"
        data["opening_lock_sha256"] = sha256(OUTPUT / "T0_opening_lock.json")
        key = "pair_id" if name in {"D4", "DQR_pair"} else "sensor_id"
        assert not data.duplicated(["timestamp", key]).any(), name
        data.to_parquet(RESULTS / filename, index=False)
        frames[name] = data
        counts.append(dict(artifact=name, rows=len(data), objects=data[key].nunique(),
            first_label=str(data.timestamp.min()), last_label=str(data.timestamp.max())))
    d1, d2, d3, d4, d5 = [frames[name] for name in ["D1", "D2", "D3", "D4", "D5"]]
    node, pair = frames["DQR_node"], frames["DQR_pair"]
    assert len(node) == 36288 and len(pair) == 18144
    all_episodes, summaries = [], []
    for name, field, key in [("D1", "D1_for_validation", "sensor_id"), ("D2", "D2_Strict", "sensor_id"),
                            ("D4", "D4_for_validation", "pair_id"), ("D5", "D5_for_validation", "sensor_id"),
                            ("DQR_node", "Q_node_core12", "sensor_id"), ("DQR_pair", "Q_pair_core", "pair_id")]:
        all_episodes.append(episodes(frames[name], field, key, name))
        summaries.append(summarize(frames[name], field, name, key))
    event_table = pd.concat(all_episodes, ignore_index=True)
    event_table.to_parquet(RESULTS / "T0_descriptive_low_tail_episodes.parquet", index=False)
    event_summary = event_table.groupby(["dimension", "object_id"]).agg(
        episodes=("start", "size"), median_observed_duration_h=("observed_duration_h", "median"),
        maximum_observed_duration_h=("observed_duration_h", "max"), right_censored=("right_censored", "sum"))
    burden = pd.concat(summaries, ignore_index=True).merge(event_summary, on=["dimension", "object_id"], how="left")
    burden["episodes"] = burden.episodes.fillna(0).astype(int)
    burden["episodes_per_1000_evaluated"] = 1000*burden.episodes/burden.evaluated_hours.replace(0, np.nan)
    burden.to_csv(SOURCE / "channel_burden.csv", index=False)
    reasons = np.select([
        ~d5.current_observed, ~d5.context_observed,
        d5.regime_state.eq("OODHold"), d5.support_level.eq("L1"), d5.D5_for_validation.notna()],
        ["current_observation_missing", "context_incomplete", "OOD", "L1_limited", "report_available"],
        default="other_not_evaluable")
    d5 = d5.assign(report_availability_reason=reasons, month=d5.timestamp.dt.strftime("%Y-%m"))
    reason_rows = d5.groupby(["month", "sensor_id", "report_availability_reason"]).size().rename("hours").reset_index()
    denominators = d5.groupby(["month", "sensor_id"]).size().rename("nominal_hours").reset_index()
    reason_rows = reason_rows.merge(denominators, on=["month", "sensor_id"])
    reason_rows["fraction"] = reason_rows.hours/reason_rows.nominal_hours
    reason_rows.to_csv(SOURCE / "D5_coverage_reasons.csv", index=False)
    d5[["timestamp", "sensor_id", "D5_for_validation", "D5_raw", "support_level", "regime_state",
        "report_availability_reason", "available_at", "frozen_asset_sha256"]].rename(
            columns={"D5_for_validation": "D5_report_score"}).to_parquet(RESULTS / "D5_report_interface.parquet", index=False)
    # Natural scores do not validate localization or deployment action.
    gate = d5[["timestamp", "sensor_id", "available_at"]].copy()
    for flag in ["sensor_identity_veto_active", "process_coherence_guard_active", "d5_action_ready"]:
        gate[flag] = False
    gate["status"] = "pending_later_period_controlled_validation_not_automatic_deployment"
    gate.to_parquet(RESULTS / "D5_gate_interface.parquet", index=False)
    for name in ["D1_detector_evidence", "D2_evidence", "D4_risks", "D5_regime_state"]:
        data = pd.read_parquet(folder / f"{name}.parquet")
        data.loc[data.timestamp.ge(START) & data.timestamp.lt(END)].to_parquet(RESULTS / f"{name}.parquet", index=False)
    transitions = json.loads((folder / "D1_events.json").read_text())
    write_json(RESULTS / "D1_recovery_transitions_journal.json", transitions)
    daily = []
    for level, frame, core, full, available in [
        ("node", node, "Q_node_core12", "Q_node_full", "Q_node_available"),
        ("pair", pair, "Q_pair_core", "Q_pair_full", "Q_pair_available")]:
        for day, block in frame.groupby(frame.timestamp.dt.floor("D")):
            means = block.groupby("timestamp")[[core, full, available]].mean()
            daily.append(dict(day=day, level=level, nominal_hours=len(block),
                core_plant_hour_mean=means[core].mean(), full_plant_hour_mean=means[full].mean(),
                available_plant_hour_mean=means[available].mean(),
                core_coverage=block[core].notna().mean(), full_coverage=block[full].notna().mean(),
                basic_fraction=block.coverage_class.eq("basic").mean(),
                limited_fraction=block.coverage_class.eq("limited").mean(),
                insufficient_fraction=block.coverage_class.eq("insufficient").mean()))
    daily = pd.DataFrame(daily)
    daily.to_csv(SOURCE / "DQR_daily_quality_coverage.csv", index=False)
    monthly = node.assign(month=node.timestamp.dt.strftime("%Y-%m")).groupby(["month", "sensor_id"]).agg(
        nominal_hours=("timestamp", "size"), core_hours=("Q_node_core12", "count"), full_hours=("Q_node_full", "count"),
        D5_hours=("D5_report_score", "count"))
    monthly.to_csv(SOURCE / "DQR_monthly_coverage.csv")
    gates = d3.assign(month=d3.timestamp.dt.strftime("%Y-%m")).groupby(["month", "sensor_id", "D3_gate_status"]).size().rename("windows").reset_index()
    gates.to_csv(SOURCE / "D3_gate_counts.csv", index=False)
    clock = frames["DQR_time_join"]
    for dim in ["D1", "D2", "D3", "D5"]:
        assert not (clock[f"{dim}_available_at"] > clock.decision_at).any(), dim
    assert not (pair.D4_available_at > pair.decision_at).any()
    assert np.allclose(node.Q_node_core12, ((node.D1_total+node.D2_total)/2), equal_nan=True)
    assert np.allclose(node.Q_node_full, ((node.D1_total+node.D2_total+node.D5_report_score)/3), equal_nan=True)
    assert np.allclose(pair.Q_pair_core, ((pair.left_Q_node_core12+pair.right_Q_node_core12+pair.D4_raw)/3).where(pair.I_D4), equal_nan=True)
    assert d5.loc[d5.support_level.eq("L1"), "D5_for_validation"].isna().all()
    assert d5.loc[~d5.context_observed | ~d5.current_observed, "D5_for_validation"].isna().all()
    assert node.loc[node.timestamp.eq(END-pd.Timedelta(hours=1)), "D1_total"].isna().all()
    # Fixed report/source table, not a replacement for the frozen score inputs.
    summary = dict(run_id="HOLDOUT-T0-20260907", completed_at_UTC=datetime.now(timezone.utc).isoformat(),
        n_node_hours=len(node), n_pair_hours=len(pair), D1_evaluable=int(d1.D1_for_validation.notna().sum()),
        D2_evaluable=int(d2.D2_Strict.notna().sum()), D4_evaluable=int(d4.D4_for_validation.notna().sum()),
        D5_raw_calculable=int(d5.D5_raw.notna().sum()), D5_report_evaluable=int(d5.D5_for_validation.notna().sum()),
        D5_mutually_exclusive_unavailability=d5.report_availability_reason.value_counts().to_dict(),
        node_coverage=node.coverage_class.value_counts().to_dict(), pair_coverage=pair.coverage_class.value_counts().to_dict(),
        D3_window_gates=d3.D3_gate_status.value_counts().to_dict(),
        node_core_sensor_hour_pooled_mean=float(node.Q_node_core12.mean()),
        node_core_plant_hour_aggregated_mean=float(node.groupby("timestamp").Q_node_core12.mean().mean()),
        pair_core_pair_hour_pooled_mean=float(pair.Q_pair_core.mean()),
        pair_core_plant_hour_aggregated_mean=float(pair.groupby("timestamp").Q_pair_core.mean().mean()),
        formal_recall_or_FAR_estimated=False, thresholds_retuned=False, frozen_support_updated=False,
        full_research_plan_complete=False, causal_QA_passed=True,
        opening_lock_sha256=sha256(OUTPUT / "T0_opening_lock.json"), source_period_days=108)
    pd.DataFrame(counts).to_csv(SOURCE / "artifact_counts.csv", index=False)
    write_json(RESULTS / "T0_numerical_qa.json", summary)
    tables = []
    for name in ["artifact_counts", "channel_burden", "DQR_monthly_coverage", "DQR_daily_quality_coverage",
                 "D5_coverage_reasons", "D3_gate_counts"]:
        table = pd.read_csv(SOURCE / f"{name}.csv")
        table = table.astype(object).where(pd.notna(table), None)
        tables.append(dict(name=name[:31], columns=table.columns.tolist(), rows=table.values.tolist()))
    write_json(SOURCE / "workbook_tables.json", tables)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
