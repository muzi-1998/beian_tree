"""Reproducible challenge-set validation for the D2 process-floor route."""
from __future__ import annotations

import json
import pickle
from pathlib import Path

import pandas as pd

from src.d2_availability.process_floor import route_availability_evidence


ROOT = Path(__file__).resolve().parent
STATE = ROOT / "artifacts" / "d2_state.pkl"
OUT_XLSX = ROOT / "artifacts" / "data" / "D2_process_floor_validation.xlsx"
OUT_JSON = ROOT / "artifacts" / "data" / "D2_process_floor_validation.json"


SCENARIOS = {
    "true_low_oxygen_floor": [0.00, 0.01, 0.00, 0.02] * 20,
    "digital_lock": [0.00] * 30,
    "low_oxygen_small_fluctuation": [0.04, 0.05, 0.04, 0.06] * 20,
    "response_recovery_after_floor": [0.00] * 20 + [0.32, 0.38, 0.35, 0.42] * 10,
}


def _evaluate(values: list[float]) -> pd.DataFrame:
    idx = pd.date_range("2026-01-01", periods=len(values), freq="1min")
    signal = pd.Series(values, index=idx, dtype=float)
    missing = signal.isna()
    same = (
        signal.diff().abs().fillna(1.0).lt(0.01)
        & ~missing
        & ~missing.shift(1, fill_value=True)
    )
    groups = same.ne(same.shift(fill_value=False)).cumsum()
    hard_rle = same.astype(int) * (same.groupby(groups).cumcount() + 1)
    rolling_iqr = (
        signal.rolling("30min", min_periods=15).quantile(0.75)
        - signal.rolling("30min", min_periods=15).quantile(0.25)
    ).fillna(1.0)
    routed = route_availability_evidence(
        aligned_value=signal,
        missing=missing,
        long_gap=pd.Series(False, index=idx),
        rle_run_min=hard_rle,
        hard_rle_run_min=hard_rle,
        rolling_iqr=rolling_iqr,
        low_iqr_threshold=0.02,
        lenient_rle_min=3,
        hard_rle_min=15,
        availability_mode="process_floor",
        process_floor_threshold=0.20,
    )
    return pd.concat(
        [signal.rename("value"), hard_rle.rename("hard_rle_min"),
         rolling_iqr.rename("rolling_iqr"), routed], axis=1
    )


def _passes(name: str, frame: pd.DataFrame) -> bool:
    if name == "true_low_oxygen_floor":
        return bool(
            frame["floor_occupancy"].iloc[-30:].all()
            and frame["resolution_limited"].iloc[-30:].all()
            and not frame["sensor_freeze"].any()
            and not frame["qfa_unavailable"].any()
        )
    if name == "digital_lock":
        return bool(
            frame["sensor_freeze"].iloc[-1]
            and frame["qfa_unavailable"].iloc[-1]
            and not frame["sensor_freeze"].iloc[10]
        )
    if name == "low_oxygen_small_fluctuation":
        return bool(
            frame["resolution_limited"].iloc[-20:].all()
            and not frame["sensor_freeze"].any()
            and not frame["qfa_unavailable"].any()
        )
    return bool(
        frame["sensor_freeze"].iloc[18]
        and not frame["sensor_freeze"].iloc[20]
        and not frame["floor_occupancy"].iloc[-20:].any()
        and not frame["qfa_unavailable"].iloc[-20:].any()
    )


def main() -> None:
    if not STATE.exists():
        raise FileNotFoundError("Run run_d2_pipeline.py before process-floor validation")
    with STATE.open("rb") as handle:
        state = pickle.load(handle)

    frames = {name: _evaluate(values) for name, values in SCENARIOS.items()}
    summary = []
    timeseries = []
    for name, frame in frames.items():
        summary.append({
            "scenario": name,
            "passed": _passes(name, frame),
            "floor_occupancy_pct": frame["floor_occupancy"].mean() * 100,
            "resolution_limited_pct": frame["resolution_limited"].mean() * 100,
            "sensor_freeze_pct": frame["sensor_freeze"].mean() * 100,
            "qfa_unavailable_pct": frame["qfa_unavailable"].mean() * 100,
        })
        tmp = frame.reset_index(names="timestamp")
        tmp.insert(0, "scenario", name)
        timeseries.append(tmp)

    observed = []
    for channel in ("DO_1_4", "DO_2_4"):
        sub = state["subs_all"][channel]
        score = state["all_D2"][channel]
        observed.append({
            "sensor_id": channel,
            "availability_mode": "process_floor",
            "floor_occupancy_pct": sub["floor_occupancy"].mean() * 100,
            "resolution_limited_pct": sub["resolution_limited"].mean() * 100,
            "sensor_freeze_pct": sub["sensor_freeze_cov"].mean() * 100,
            "qfa_unavailable_pct": sub["info_empty_cov"].mean() * 100,
            "freeze_severe_veto_pct": score["veto_reason"].str.contains(
                "freeze_severe", na=False
            ).mean() * 100,
            "total_veto_pct": score["veto_flag"].mean() * 100,
            "mean_Q_FA": sub["Q_FA"].mean(),
        })

    summary_df = pd.DataFrame(summary)
    observed_df = pd.DataFrame(observed)
    OUT_XLSX.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(OUT_XLSX, engine="openpyxl") as writer:
        summary_df.to_excel(writer, sheet_name="challenge_summary", index=False)
        pd.concat(timeseries, ignore_index=True).to_excel(
            writer, sheet_name="challenge_timeseries", index=False
        )
        observed_df.to_excel(writer, sheet_name="observed_channels", index=False)

    payload = {
        "validation_version": "d2_process_floor_r1",
        "qfa_window": "6h",
        "hard_rle_min": 15,
        "all_challenges_passed": bool(summary_df["passed"].all()),
        "challenges": summary_df.to_dict(orient="records"),
        "observed_channels": observed_df.to_dict(orient="records"),
        "d2_run_id": state.get("run_id"),
    }
    OUT_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    if not payload["all_challenges_passed"]:
        raise AssertionError("At least one process-floor challenge failed")
    print(summary_df.to_string(index=False))
    print(observed_df.to_string(index=False))
    print(f"Saved {OUT_XLSX.name} and {OUT_JSON.name}")


if __name__ == "__main__":
    main()
