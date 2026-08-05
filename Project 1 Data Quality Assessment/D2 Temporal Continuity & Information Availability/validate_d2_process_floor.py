"""Reproducible challenge-set validation for the D2 process-floor route."""
from __future__ import annotations

import json
import pickle
from pathlib import Path

import pandas as pd

from src.d2_availability.process_floor import route_availability_evidence
from src.utils.config_loader import load_config


ROOT = Path(__file__).resolve().parent
STATE = ROOT / "artifacts" / "d2_state.pkl"
OUT_XLSX = ROOT / "artifacts" / "data" / "D2_process_floor_casebook.xlsx"
OUT_JSON = ROOT / "artifacts" / "data" / "D2_process_floor_contract_test.json"
LEGACY_XLSX = ROOT / "artifacts" / "data" / "D2_process_floor_validation.xlsx"
LEGACY_JSON = ROOT / "artifacts" / "data" / "D2_process_floor_validation.json"


SCENARIOS = {
    "true_low_oxygen_floor": [0.00, 0.01, 0.00, 0.02] * 20,
    "digital_lock": [0.00] * 30,
    "low_oxygen_small_fluctuation": [0.04, 0.05, 0.04, 0.06] * 20,
    "response_recovery_after_floor": [0.00] * 20 + [0.32, 0.38, 0.35, 0.42] * 10,
    "missing_and_long_gap_not_exempt": (
        [0.04, 0.05] * 4
        + [None] * 6
        + [0.04, 0.05] * 5
        + [0.05, 0.06] * 5
    ),
}
LONG_GAP_POSITIONS = {
    "missing_and_long_gap_not_exempt": tuple(range(24, 30)),
}


def _evaluate(
    values: list[float | None],
    *,
    long_gap_positions: tuple[int, ...] = (),
) -> pd.DataFrame:
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
    long_gap = pd.Series(False, index=idx)
    if long_gap_positions:
        long_gap.iloc[list(long_gap_positions)] = True
    routed = route_availability_evidence(
        aligned_value=signal,
        missing=missing,
        long_gap=long_gap,
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
        [
            signal.rename("value"),
            missing.rename("missing"),
            long_gap.rename("long_gap"),
            hard_rle.rename("hard_rle_min"),
            rolling_iqr.rename("rolling_iqr"),
            routed,
        ],
        axis=1,
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
    if name == "response_recovery_after_floor":
        return bool(
            frame["sensor_freeze"].iloc[18]
            and not frame["sensor_freeze"].iloc[20]
            and not frame["floor_occupancy"].iloc[-20:].any()
            and not frame["qfa_unavailable"].iloc[-20:].any()
        )
    unavailable_evidence = frame["missing"] | frame["long_gap"]
    return bool(
        unavailable_evidence.any()
        and frame.loc[unavailable_evidence, "continuity_unavailable"].all()
        and not frame.loc[unavailable_evidence, "qfa_unavailable"].any()
        and not frame.loc[frame["missing"], "sensor_freeze"].any()
    )


def main() -> None:
    if not STATE.exists():
        raise FileNotFoundError("Run run_d2_pipeline.py before process-floor validation")
    with STATE.open("rb") as handle:
        state = pickle.load(handle)

    cfg = load_config(ROOT / "configs", version="v1")
    frames = {
        name: _evaluate(
            values,
            long_gap_positions=LONG_GAP_POSITIONS.get(name, ()),
        )
        for name, values in SCENARIOS.items()
    }
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
            "qfa_unavailable_pct": sub["hard_stasis_fraction_observed"].mean() * 100,
            "freeze_severe_veto_pct": score["veto_reason"].str.contains(
                "hard_stasis_severe", na=False
            ).mean() * 100,
            "total_veto_pct": score["veto_flag"].mean() * 100,
            "mean_Q_FA": sub["Q_HA"].mean(),
        })

    summary_df = pd.DataFrame(summary)
    observed_df = pd.DataFrame(observed)
    semantic_fields = [
        "availability_mode",
        "process_zone",
        "process_floor_threshold",
        "response_loss_enabled",
    ]
    semantic_rows = []
    for channel in ("DO_1_4", "DO_2_4"):
        sensor = cfg.sensors[channel]
        semantic_rows.append(
            {
                "sensor_id": channel,
                **{
                    field: getattr(sensor, field)
                    for field in semantic_fields
                },
            }
        )
    semantic_df = pd.DataFrame(semantic_rows)
    semantic_equal = bool(
        semantic_df[semantic_fields].nunique(dropna=False).eq(1).all()
    )
    contract_checks = pd.DataFrame(
        [
            {
                "contract_check": row.scenario,
                "passed": bool(row.passed),
                "evidence_scope": "synthetic_mechanism_challenge",
            }
            for row in summary_df.itertuples(index=False)
        ]
        + [
            {
                "contract_check": "both_position_4_channels_share_semantics",
                "passed": semantic_equal,
                "evidence_scope": "configuration_contract",
            }
        ]
    )
    timeseries_df = pd.concat(timeseries, ignore_index=True)
    OUT_XLSX.parent.mkdir(parents=True, exist_ok=True)
    for workbook in (OUT_XLSX, LEGACY_XLSX):
        with pd.ExcelWriter(workbook, engine="openpyxl") as writer:
            contract_checks.to_excel(
                writer,
                sheet_name="contract_checks",
                index=False,
            )
            summary_df.to_excel(
                writer,
                sheet_name="challenge_summary",
                index=False,
            )
            timeseries_df.to_excel(
                writer,
                sheet_name="challenge_timeseries",
                index=False,
            )
            observed_df.to_excel(
                writer,
                sheet_name="observed_channels",
                index=False,
            )
            semantic_df.to_excel(
                writer,
                sheet_name="semantic_contract",
                index=False,
            )

    payload = {
        "validation_version": "d2_process_floor_contract_r3_hard_only",
        "qha_window": "6h",
        "hard_rle_min": 15,
        "all_contract_checks_passed": bool(contract_checks["passed"].all()),
        "all_challenges_passed": bool(summary_df["passed"].all()),
        "challenges": summary_df.to_dict(orient="records"),
        "contract_checks": contract_checks.to_dict(orient="records"),
        "semantic_contract": semantic_df.to_dict(orient="records"),
        "observed_channels": observed_df.to_dict(orient="records"),
        "d2_run_id": state.get("run_id"),
    }
    serialized = json.dumps(payload, indent=2)
    OUT_JSON.write_text(serialized, encoding="utf-8")
    LEGACY_JSON.write_text(serialized, encoding="utf-8")
    if not payload["all_contract_checks_passed"]:
        raise AssertionError("At least one process-floor contract check failed")
    print(summary_df.to_string(index=False))
    print(observed_df.to_string(index=False))
    print(f"Saved {OUT_XLSX.name} and {OUT_JSON.name}")


if __name__ == "__main__":
    main()
