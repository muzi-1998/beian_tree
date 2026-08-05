"""Dose-response validation from raw timestamp/measurement challenges to D2 scores."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from src.d2_availability.challenge import evaluate_raw_series
from src.utils.config_loader import load_config


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "artifacts" / "validation"
OUT.mkdir(parents=True, exist_ok=True)
CFG = load_config(ROOT / "configs", version="v2")
START = pd.Timestamp("2026-01-01 00:00")
END = pd.Timestamp("2026-01-05 23:59")
ONSET = pd.Timestamp("2026-01-03 12:00")


def baseline(sensor_id: str) -> pd.DataFrame:
    index = pd.date_range(START, END, freq="1min")
    phase = np.arange(len(index), dtype=float)
    if sensor_id.startswith("ORP"):
        values = (-120 + 18 * np.sin(2 * np.pi * phase / 360)
                  + 3 * np.sin(phase / 19) + (phase % 2) * 1.5)
        values = np.round(values * 2) / 2
    else:
        values = (1.8 + 0.35 * np.sin(2 * np.pi * phase / 360)
                  + 0.05 * np.sin(phase / 17) + (phase % 2) * 0.03)
        values = np.round(values, 2)
    return pd.DataFrame({"timestamp": index, "value": values})


def summarize(result: dict, *, onset: pd.Timestamp, end: pd.Timestamp,
              route: str, scenario: str, severity: float, sensor_id: str) -> dict:
    scores = result["scores"].loc[onset.floor("h"):end.ceil("h") + pd.Timedelta(hours=24)]
    relevant = {"timestamp": "Q_TI", "gap": "Q_GS", "stasis": "Q_HA"}[route]
    series = scores[relevant].dropna()
    strict = scores["D2_total"].dropna()
    affected = series.loc[series.lt(4.5)]
    post = scores.loc[end.ceil("h"):, relevant].dropna()
    recovered = post.ge(4.95).rolling(2, min_periods=2).sum().ge(2)
    recovery_ts = recovered.index[np.flatnonzero(recovered.to_numpy())[0]] if recovered.any() else pd.NaT
    audit = result["audit"]
    denominator = max(int(audit["valid_transition"].sum()), 1)
    return {
        "route": route,
        "scenario": scenario,
        "severity": severity,
        "sensor_id": sensor_id,
        "analyte": sensor_id.split("_")[0],
        "onset": onset,
        "fault_end": end,
        "actual_duplicate_rate": float(audit["duplicate"].sum() / denominator),
        "actual_out_of_order_rate": float(audit["out_of_order"].sum() / denominator),
        "actual_true_irregular_rate": float(audit["true_irregular"].sum() / denominator),
        "min_Q_TI": float(scores["Q_TI"].min()),
        "min_Q_GS": float(scores["Q_GS"].min()),
        "min_Q_HA": float(scores["Q_HA"].min()),
        "min_D2_strict": float(strict.min()),
        "relevant_deficit_auc": float((5.0 - series).clip(lower=0).sum()),
        "strict_deficit_auc": float((5.0 - strict).clip(lower=0).sum()),
        "detected_below_4_5": bool(len(affected)),
        "strict_low_below_3": bool(strict.lt(3.0).any()),
        "first_detection_delay_h": (
            float((affected.index[0] - onset).total_seconds() / 3600) if len(affected) else np.nan
        ),
        "recovery_time_h": (
            float((recovery_ts - end).total_seconds() / 3600)
            if len(affected) and pd.notna(recovery_ts) else np.nan
        ),
    }


def timestamp_challenges() -> list[dict]:
    rows = []
    raw0 = baseline("DO_1_1")
    n = len(raw0)
    for fault, rates in {"duplicate": (0.0, 0.001, 0.005, 0.01, 0.05),
                         "out_of_order": (0.0, 0.001, 0.005, 0.01, 0.05)}.items():
        for rate in rates:
            raw = raw0.copy()
            count = int(round(rate * n))
            positions = np.linspace(1800, n - 1800, max(count, 1), dtype=int)[:count]
            if fault == "duplicate" and count:
                duplicate_rows = raw.iloc[positions]
                raw = pd.concat([raw, duplicate_rows]).sort_index(kind="stable").reset_index(drop=True)
            elif fault == "out_of_order" and count:
                for position in positions:
                    if position + 1 >= len(raw):
                        continue
                    raw.iloc[[position, position + 1]] = raw.iloc[[position + 1, position]].to_numpy()
            result = evaluate_raw_series(raw, CFG, expected_start=START, expected_end=END)
            rows.append(summarize(
                result, onset=START + pd.Timedelta(hours=24), end=END,
                route="timestamp", scenario=fault, severity=rate, sensor_id="DO_1_1"
            ))
    for interval_sec in (60, 66, 70, 90, 110):
        raw = raw0.copy()
        positions = np.arange(2000, n - 1000, 240)
        raw.loc[positions, "timestamp"] += pd.to_timedelta(interval_sec - 60, unit="s")
        result = evaluate_raw_series(raw, CFG, expected_start=START, expected_end=END)
        rows.append(summarize(
            result, onset=START + pd.Timedelta(hours=24), end=END,
            route="timestamp", scenario="irregular_interval_sec",
            severity=float(interval_sec), sensor_id="DO_1_1"
        ))
    return rows


def gap_challenges() -> list[dict]:
    rows = []
    for sensor_id in ("DO_1_1", "ORP_1_1"):
        raw0 = baseline(sensor_id)
        for duration in (2, 5, 6, 15, 20, 30, 60, 360):
            end = ONSET + pd.Timedelta(minutes=duration - 1)
            raw = raw0.loc[~raw0["timestamp"].between(ONSET, end)].copy()
            result = evaluate_raw_series(
                raw, CFG, expected_start=START, expected_end=END, sensor_id=sensor_id
            )
            rows.append(summarize(
                result, onset=ONSET, end=end, route="gap", scenario="single_gap_min",
                severity=float(duration), sensor_id=sensor_id
            ))
        raw = raw0.copy()
        keep = pd.Series(True, index=raw.index)
        for offset in range(0, 300, 30):
            start = ONSET + pd.Timedelta(minutes=offset)
            keep &= ~raw["timestamp"].between(start, start + pd.Timedelta(minutes=1))
        result = evaluate_raw_series(
            raw.loc[keep], CFG, expected_start=START, expected_end=END, sensor_id=sensor_id
        )
        rows.append(summarize(
            result, onset=ONSET, end=ONSET + pd.Timedelta(minutes=271), route="gap",
            scenario="ten_two_minute_gaps", severity=20.0, sensor_id=sensor_id
        ))
    return rows


def stasis_challenges() -> tuple[list[dict], list[dict]]:
    rows, sensitivity = [], []
    for sensor_id in ("DO_1_1", "ORP_1_1"):
        raw0 = baseline(sensor_id)
        for duration in (10, 15, 20, 30, 45, 60, 90, 120, 180):
            end = ONSET + pd.Timedelta(minutes=duration - 1)
            raw = raw0.copy()
            mask = raw["timestamp"].between(ONSET, end)
            raw.loc[mask, "value"] = float(raw.loc[mask, "value"].iloc[0])
            result = evaluate_raw_series(
                raw, CFG, expected_start=START, expected_end=END, sensor_id=sensor_id
            )
            rows.append(summarize(
                result, onset=ONSET, end=end, route="stasis",
                scenario="persistent_stasis_min", severity=float(duration), sensor_id=sensor_id
            ))

        end = ONSET + pd.Timedelta(minutes=59)
        raw = raw0.copy()
        mask = raw["timestamp"].between(ONSET, end)
        raw.loc[mask, "value"] = float(raw.loc[mask, "value"].iloc[0])
        for hard_min in (10, 15, 20, 30):
            for window_h in (3, 6, 9, 12):
                result = evaluate_raw_series(
                    raw, CFG, expected_start=START, expected_end=END,
                    sensor_id=sensor_id, hard_stasis_min=hard_min,
                    qha_window_hours=window_h,
                )
                record = summarize(
                    result, onset=ONSET, end=end, route="stasis",
                    scenario="threshold_window_sensitivity", severity=60.0,
                    sensor_id=sensor_id,
                )
                record["hard_stasis_threshold_min"] = hard_min
                record["qha_window_h"] = window_h
                sensitivity.append(record)
    return rows, sensitivity


def monotonicity(frame: pd.DataFrame) -> pd.DataFrame:
    rows = []
    eligible = frame.loc[frame["scenario"].isin([
        "duplicate", "out_of_order", "irregular_interval_sec",
        "single_gap_min", "persistent_stasis_min",
    ])]
    for keys, group in eligible.groupby(["route", "scenario", "sensor_id"]):
        route, scenario, sensor_id = keys
        ordered = group.sort_values("severity")
        rho = spearmanr(ordered["severity"], ordered["relevant_deficit_auc"]).statistic
        rows.append({
            "route": route,
            "scenario": scenario,
            "sensor_id": sensor_id,
            "n_levels": len(ordered),
            "spearman_severity_vs_deficit": float(rho),
            "monotonic_non_decreasing": bool(
                np.all(np.diff(ordered["relevant_deficit_auc"].to_numpy()) >= -1e-9)
            ),
        })
    return pd.DataFrame(rows)


def main() -> None:
    response = pd.DataFrame(timestamp_challenges() + gap_challenges())
    stasis, sensitivity = stasis_challenges()
    response = pd.concat([response, pd.DataFrame(stasis)], ignore_index=True)
    sensitivity = pd.DataFrame(sensitivity)
    monotonic = monotonicity(response)
    outputs = {
        "D2_full_pipeline_injection_response.parquet": response,
        "D2_qha_threshold_window_sensitivity.parquet": sensitivity,
        "D2_full_pipeline_monotonicity.parquet": monotonic,
    }
    for name, frame in outputs.items():
        frame.to_parquet(OUT / name, index=False)
    workbook = OUT / "D2_full_pipeline_injection_source_data.xlsx"
    with pd.ExcelWriter(workbook, engine="openpyxl") as writer:
        response.to_excel(writer, sheet_name="dose_response", index=False)
        sensitivity.to_excel(writer, sheet_name="QHA_window_threshold", index=False)
        monotonic.to_excel(writer, sheet_name="monotonicity", index=False)
    summary = {
        "schema_version": "d2-full-pipeline-injection-v2",
        "production_threshold_min": 15,
        "production_qha_window_h": 6,
        "monotonic_groups_passed": int(monotonic["monotonic_non_decreasing"].sum()),
        "monotonic_groups_total": int(len(monotonic)),
        "baseline_false_positive_groups": int(response.loc[
            ((response["scenario"].isin(["duplicate", "out_of_order"]))
             & response["severity"].eq(0.0))
            | (response["scenario"].eq("irregular_interval_sec")
               & response["severity"].eq(60.0)),
            "detected_below_4_5",
        ].sum()),
        "recovery_is_conditional_on_detection": True,
        "files": {},
    }
    for path in [*(OUT / name for name in outputs), workbook]:
        summary["files"][path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    (OUT / "D2_full_pipeline_injection_manifest.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
