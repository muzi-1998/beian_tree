from __future__ import annotations

import pickle
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import yaml
from scipy.stats import qmc
from sklearn.metrics import average_precision_score, roc_auc_score

from .common import CONFIG_ROOT, PROJECT_ROOT, read_yaml, wilson_interval


D1_ROOT = PROJECT_ROOT / "D1 Sensor health"


def _load_d1_api():
    import src

    d1_source = str(D1_ROOT / "src")
    if d1_source not in src.__path__:
        src.__path__.append(d1_source)
    from src.calibration.step_injection import confirmation_gate, logistic_quality
    from src.detectors.drift_pls import PLSVirtualSensorDetector
    from src.detectors.spike_hampel import HampelSpikeDetector
    from src.detectors.step_adjacent_ks import AdjacentKSStepDetector

    return (
        confirmation_gate,
        logistic_quality,
        PLSVirtualSensorDetector,
        HampelSpikeDetector,
        AdjacentKSStepDetector,
    )


def _robust_scale(values: pd.Series) -> float:
    finite = values.dropna().to_numpy(dtype=float)
    if not len(finite):
        return np.nan
    median = float(np.median(finite))
    scale = 1.4826 * float(np.median(np.abs(finite - median)))
    if not np.isfinite(scale) or scale <= 1e-9:
        scale = float(np.std(finite))
    return max(scale, 1e-9)


def _consecutive_alarm(values: np.ndarray, duration: int) -> tuple[bool, float]:
    active = np.asarray(values, dtype=bool)
    if len(active) < duration:
        return False, np.nan
    run = np.convolve(active.astype(int), np.ones(duration, dtype=int), mode="valid")
    hits = np.flatnonzero(run >= duration)
    return bool(len(hits)), float(hits[0]) if len(hits) else np.nan


def _quantize(series: pd.Series, step: float | None) -> pd.Series:
    if step is None or not np.isfinite(step) or step <= 0:
        return series
    return (series / step).round() * step


def _empirical_resolution(series: pd.Series) -> float:
    values = np.sort(series.dropna().unique().astype(float))
    if len(values) < 2:
        return np.nan
    increments = np.diff(values)
    increments = increments[increments > 1e-12]
    return float(np.quantile(increments, 0.10)) if len(increments) else np.nan


def _finite_max(values: pd.Series | np.ndarray) -> float:
    array = np.asarray(values, dtype=float)
    finite = array[np.isfinite(array)]
    return float(finite.max()) if len(finite) else np.nan


def _finite_min(values: pd.Series | np.ndarray) -> float:
    array = np.asarray(values, dtype=float)
    finite = array[np.isfinite(array)]
    return float(finite.min()) if len(finite) else np.nan


def _finite_median(values: pd.Series | np.ndarray) -> float:
    array = np.asarray(values, dtype=float)
    finite = array[np.isfinite(array)]
    return float(np.median(finite)) if len(finite) else np.nan


def _prepare_clean_hours(
    state: dict,
    d2_state: dict,
    d3_gate: pd.DataFrame,
) -> dict[str, pd.DatetimeIndex]:
    d3 = d3_gate.copy()
    d3["timestamp"] = pd.to_datetime(d3["timestamp"])
    fail = {
        sensor: set(frame.loc[frame["D3_gate_status"].eq("Fail"), "timestamp"])
        for sensor, frame in d3.groupby("sensor_id")
    }
    clean: dict[str, pd.DatetimeIndex] = {}
    for sensor in state["scored_channels"]:
        d1 = state["D1_v11"][sensor]
        d2 = d2_state["all_D2"][sensor]["usable_tag"].reindex(d1.index)
        mask = d1.ge(4.5) & d2.eq("train_ok")
        mask &= d1.index >= pd.Timestamp("2025-11-01")
        mask &= d1.index <= pd.Timestamp("2026-04-06")
        if sensor in fail:
            mask &= ~pd.Series(d1.index.isin(fail[sensor]), index=d1.index)
        clean[sensor] = pd.DatetimeIndex(d1.index[mask])
    return clean


def _pick_onsets(
    clean: dict[str, pd.DatetimeIndex],
    state: dict,
    *,
    analyte: str,
    n: int,
    rng: np.random.Generator,
) -> list[tuple[str, pd.Timestamp, int]]:
    sensors = [sensor for sensor in state["scored_channels"] if sensor.startswith(analyte)]
    choices = []
    for sensor in sensors:
        index = clean[sensor]
        for timestamp in index[::24]:
            regime = int(state["regime_labels"].reindex([timestamp]).iloc[0])
            choices.append((sensor, pd.Timestamp(timestamp), regime))
    if not choices:
        raise RuntimeError(f"No clean D1 validation hours are available for {analyte}")
    selected = rng.integers(0, len(choices), size=n)
    return [choices[index] for index in selected]


def _fit_pls_models(state: dict) -> tuple[dict[str, object], dict[str, list[str]]]:
    _, _, PLSVirtualSensorDetector, _, _ = _load_d1_api()
    audit = state["detectors_raw"]["pls_peer_selection_audit"].copy()
    models = {}
    peers: dict[str, list[str]] = {}
    for sensor in state["scored_channels"]:
        raw = audit.loc[sensor, "selected_peers"]
        selected = [value for value in str(raw).split(";") if value]
        detector = PLSVirtualSensorDetector(
            n_components=int(audit.loc[sensor, "selected_n_components"]),
            train_days=21,
        )
        detector.fit(state["df_h"], target=sensor, peer_cols=selected)
        models[sensor] = detector
        peers[sensor] = selected
    return models, peers


def _pls_z(detector, frame: pd.DataFrame, target: str) -> np.ndarray:
    model, sx, sy, sigma_residual, medians, peers, _ = detector._models[target]
    prepared = frame.loc[:, [target, *peers]].copy().ffill().fillna(medians).fillna(0.0)
    prediction_s = model.predict(sx.transform(prepared[peers].to_numpy(dtype=float))).ravel()
    prediction = sy.inverse_transform(prediction_s.reshape(-1, 1)).ravel()
    return np.abs(prepared[target].to_numpy(dtype=float) - prediction) / sigma_residual


def _spike_trial(
    residual: pd.Series,
    onset: pd.Timestamp,
    amplitude: float,
    duration_min: int,
    direction: int,
    resolution_step: float | None,
) -> tuple[float, float, bool, bool, float]:
    _, _, _, HampelSpikeDetector, _ = _load_d1_api()
    start = onset - pd.Timedelta(minutes=90)
    end = onset + pd.Timedelta(minutes=duration_min + 90)
    blank = residual.loc[start:end].copy()
    scale = _robust_scale(blank.loc[: onset - pd.Timedelta(minutes=1)])
    blank = _quantize(blank, resolution_step)
    injected = blank.copy()
    event_end = onset + pd.Timedelta(minutes=duration_min - 1)
    injected.loc[onset:event_end] += direction * amplitude * scale
    injected = _quantize(injected, resolution_step)
    detector = HampelSpikeDetector(window_min=21, k=3.0)
    blank_score = detector.score(blank.rename(residual.name)).raw_score
    injected_score = detector.score(injected.rename(residual.name)).raw_score
    evaluation_end = event_end + pd.Timedelta(minutes=10)
    blank_eval = blank_score.loc[onset:evaluation_end]
    injected_eval = injected_score.loc[onset:evaluation_end]
    hits = np.flatnonzero(injected_eval.to_numpy(dtype=float) > 3.0)
    delay = float(hits[0]) if len(hits) else np.nan
    return (
        _finite_max(blank_eval),
        _finite_max(injected_eval),
        bool((blank_eval > 3.0).any()),
        bool((injected_eval > 3.0).any()),
        delay,
    )


def _step_trial(
    routed: pd.Series,
    onset: pd.Timestamp,
    amplitude: float,
    duration_h: float,
    direction: int,
    neff_ratio: float,
    mapping: dict,
    degraded_resolution: bool,
) -> tuple[float, float, bool, bool, float]:
    confirmation_gate, logistic_quality, _, _, AdjacentKSStepDetector = _load_d1_api()
    start = onset - pd.Timedelta(hours=72)
    end = onset + pd.Timedelta(hours=max(72, int(np.ceil(duration_h)) + 48))
    blank = routed.loc[start:end].copy()
    scale = _robust_scale(blank.loc[: onset - pd.Timedelta(hours=1)])
    resolution_step = _empirical_resolution(blank) * 2.0 if degraded_resolution else None
    blank = _quantize(blank, resolution_step)
    injected = blank.copy()
    event_end = onset + pd.Timedelta(hours=max(1, int(np.ceil(duration_h))) - 1)
    injected.loc[onset:event_end] += direction * amplitude * scale
    injected = _quantize(injected, resolution_step)

    def quality(series: pd.Series) -> pd.Series:
        q24 = logistic_quality(
            AdjacentKSStepDetector(24, 0.001, neff_ratio).score(series).raw_score,
            float(mapping["k"]),
            float(mapping["x0"]),
        )
        q36 = logistic_quality(
            AdjacentKSStepDetector(36, 0.001, neff_ratio).score(series).raw_score,
            float(mapping["k"]),
            float(mapping["x0"]),
        )
        return pd.Series(confirmation_gate(q24, q36), index=series.index)

    blank_q = quality(blank)
    injected_q = quality(injected)
    evaluation_end = event_end + pd.Timedelta(hours=48)
    blank_eval = blank_q.loc[onset:evaluation_end]
    injected_eval = injected_q.loc[onset:evaluation_end]
    hits = np.flatnonzero(injected_eval.to_numpy(dtype=float) <= 2.5)
    return (
        float(5.0 - _finite_min(blank_eval)),
        float(5.0 - _finite_min(injected_eval)),
        bool((blank_eval <= 2.5).any()),
        bool((injected_eval <= 2.5).any()),
        float(hits[0]) if len(hits) else np.nan,
    )


def _drift_trial(
    state: dict,
    detector,
    peer_columns: list[str],
    sensor: str,
    onset: pd.Timestamp,
    amplitude: float,
    duration_h: float,
    direction: int,
    resolution_step: float | None,
) -> tuple[float, float, bool, bool, float, float]:
    hours = max(12, int(np.ceil(duration_h)))
    start = onset - pd.Timedelta(hours=48)
    end = onset + pd.Timedelta(hours=hours + 24)
    blank = state["df_h"].loc[start:end, [sensor, *peer_columns]].copy()
    scale = _robust_scale(blank.loc[: onset - pd.Timedelta(hours=1), sensor])
    profile = np.linspace(0.0, direction * amplitude * scale, hours)
    event_index = pd.date_range(onset, periods=hours, freq="1h")
    if resolution_step is not None:
        blank.loc[:, sensor] = _quantize(blank[sensor], resolution_step)
    injected = blank.copy()
    injected.loc[event_index, sensor] += profile
    injected.loc[:, sensor] = _quantize(injected[sensor], resolution_step)
    blank_z = _pls_z(detector, blank, sensor)
    injected_z = _pls_z(detector, injected, sensor)
    local_index = blank.index
    evaluation = (local_index >= onset) & (
        local_index <= event_index[-1] + pd.Timedelta(hours=12)
    )
    blank_alarm, _ = _consecutive_alarm(blank_z[evaluation] >= 3.0, 3)
    injected_alarm, delay = _consecutive_alarm(injected_z[evaluation] >= 3.0, 3)

    common = blank.copy()
    common.loc[event_index, sensor] += profile
    common.loc[:, sensor] = _quantize(common[sensor], resolution_step)
    for peer in peer_columns:
        peer_scale = _robust_scale(
            blank.loc[: onset - pd.Timedelta(hours=1), peer]
        )
        peer_profile = np.linspace(
            0.0,
            direction * amplitude * peer_scale,
            hours,
        )
        common.loc[event_index, peer] += peer_profile
    common_z = _pls_z(detector, common, sensor)
    common_alarm, _ = _consecutive_alarm(common_z[evaluation] >= 3.0, 3)
    return (
        _finite_max(blank_z[evaluation]),
        _finite_max(injected_z[evaluation]),
        blank_alarm,
        injected_alarm,
        delay,
        float(common_alarm),
    )


def _freeze_trial(
    raw: pd.Series,
    onset: pd.Timestamp,
    duration_min: int,
    precision: float,
    degraded_resolution: bool,
) -> tuple[float, float, bool, bool, float]:
    start = onset - pd.Timedelta(minutes=60)
    end = onset + pd.Timedelta(minutes=duration_min + 30)
    blank = raw.loc[start:end].copy()
    effective_precision = precision * 2.0 if degraded_resolution else precision
    blank = _quantize(blank, effective_precision if degraded_resolution else None)
    injected = blank.copy()
    event_index = pd.date_range(onset, periods=duration_min, freq="1min")
    injected.loc[event_index] = float(blank.loc[: onset - pd.Timedelta(minutes=1)].iloc[-1])

    def run_lengths(series: pd.Series) -> pd.Series:
        equal = series.diff().abs().le(max(effective_precision * 0.25, 1e-9)).fillna(False)
        groups = (~equal).cumsum()
        return equal.groupby(groups).cumsum()

    blank_run = run_lengths(blank).loc[event_index]
    injected_run = run_lengths(injected).loc[event_index]
    blank_alarm = bool(blank_run.ge(15).any())
    injected_alarm = bool(injected_run.ge(15).any())
    hits = np.flatnonzero(injected_run.to_numpy(dtype=float) >= 15)
    return (
        float(blank_run.max()),
        float(injected_run.max()),
        blank_alarm,
        injected_alarm,
        float(hits[0] + 1) if len(hits) else np.nan,
    )


def _summaries(trials: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    rows = []
    stratified = []
    for fault, attempted in trials.groupby("fault_type"):
        frame = attempted[attempted["valid_evaluation"]].copy()
        if frame.empty:
            continue
        successes = int(frame["detected"].sum())
        low, high = wilson_interval(successes, len(frame))
        labels = np.r_[np.zeros(len(frame)), np.ones(len(frame))]
        scores = np.r_[frame["blank_statistic"], frame["injected_statistic"]]
        rows.append(
            {
                "fault_type": fault,
                "n_trials": len(frame),
                "n_attempted": len(attempted),
                "n_excluded_not_evaluable": len(attempted) - len(frame),
                "event_recall": successes / len(frame),
                "recall_ci_low": low,
                "recall_ci_high": high,
                "AUROC": float(roc_auc_score(labels, scores)),
                "AUPRC": float(average_precision_score(labels, scores)),
                "false_alarms_per_sensor_day": float(
                    frame["blank_alarm"].sum()
                    / np.maximum(frame["evaluation_hours"].sum() / 24.0, 1e-9)
                ),
                "median_detection_delay": _finite_median(frame["detection_delay"]),
                "common_process_conditional_new_far": float(
                    frame.loc[
                        ~frame["blank_alarm"], "common_process_alarm"
                    ].dropna().mean()
                )
                if frame.loc[
                    ~frame["blank_alarm"], "common_process_alarm"
                ].notna().any()
                else np.nan,
                "analysis_unit": "independent_injection_episode",
            }
        )
        for keys, group in frame.groupby(["analyte", "route"]):
            success = int(group["detected"].sum())
            ci_low, ci_high = wilson_interval(success, len(group))
            stratified.append(
                {
                    "fault_type": fault,
                    "analyte": keys[0],
                    "route": keys[1],
                    "n_trials": len(group),
                    "event_recall": success / len(group),
                    "recall_ci_low": ci_low,
                    "recall_ci_high": ci_high,
                    "median_detection_delay": _finite_median(group["detection_delay"]),
                }
            )
    return pd.DataFrame(rows), pd.DataFrame(stratified)


def run_d1_validation(output_dir: Path, d3_gate: pd.DataFrame) -> dict[str, pd.DataFrame]:
    design = read_yaml(CONFIG_ROOT / "validation_design.yaml")["D1"]
    with (D1_ROOT / "v11_state.pkl").open("rb") as handle:
        state = pickle.load(handle)
    with (
        PROJECT_ROOT
        / "D2 Temporal Continuity & Information Availability"
        / "artifacts"
        / "d2_state.pkl"
    ).open("rb") as handle:
        d2_state = pickle.load(handle)
    with (
        PROJECT_ROOT / "1.1 Decomposition" / "outputs" / "_pipeline_state.pkl"
    ).open("rb") as handle:
        decomposition = pickle.load(handle)
    with (
        PROJECT_ROOT / "1.1 Decomposition" / "outputs" / "_w2_checkpoint.pkl"
    ).open("rb") as handle:
        raw = pickle.load(handle)["out"]["df_min"]

    clean = _prepare_clean_hours(state, d2_state, d3_gate)
    models, peers = _fit_pls_models(state)
    sensor_cfg = yaml.safe_load(
        (
            PROJECT_ROOT
            / "D2 Temporal Continuity & Information Availability"
            / "configs"
            / "d2_sensors.yaml"
        ).read_text(encoding="utf-8")
    )["sensors"]
    mapping = yaml.safe_load((D1_ROOT / "configs" / "mapping.yaml").read_text(encoding="utf-8"))[
        "step"
    ]
    rng = np.random.default_rng(20260727)
    rows = []
    fault_specs = [
        ("spike", int(design["core_faults"]["spike"]["target_trials"])),
        ("step", int(design["core_faults"]["step"]["target_trials"])),
        ("linear_drift", int(design["core_faults"]["linear_drift"]["target_trials"])),
        ("hard_freeze", int(design["core_faults"]["hard_freeze"]["target_trials"])),
    ]
    for fault, total in fault_specs:
        sampler = qmc.LatinHypercube(d=2, seed=int(rng.integers(0, 2**31 - 1)))
        lhs = sampler.random(total)
        per_analyte = {"DO": total // 2, "ORP": total - total // 2}
        schedule = []
        for analyte, count in per_analyte.items():
            schedule.extend(_pick_onsets(clean, state, analyte=analyte, n=count, rng=rng))
        rng.shuffle(schedule)
        for trial_no, ((sensor, onset, regime), point) in enumerate(zip(schedule, lhs), 1):
            analyte = sensor.split("_")[0]
            route = state["scoring_mode"][sensor]
            direction = -1 if trial_no % 2 else 1
            resolution_mode = (
                "original" if ((trial_no - 1) // 2) % 2 == 0 else "degraded_2x"
            )
            degraded_resolution = resolution_mode == "degraded_2x"
            sensor_precision = float(sensor_cfg[sensor]["precision"])
            amplitude = 0.5 + 2.5 * float(point[0])
            common_process_alarm = np.nan
            if fault == "spike":
                duration = 1 + int(np.floor(9 * point[1]))
                result = _spike_trial(
                    decomposition["resid_min"][sensor],
                    onset + pd.Timedelta(minutes=30),
                    amplitude,
                    duration,
                    direction,
                    sensor_precision * 2.0 if degraded_resolution else None,
                )
                evaluation_hours = max(1.0, (duration + 10) / 60.0)
                duration_value, duration_unit = duration, "min"
            elif fault == "step":
                duration = 0.5 + 47.5 * float(point[1])
                result = _step_trial(
                    state["whitened_input_h"][sensor],
                    onset,
                    amplitude,
                    duration,
                    direction,
                    float(state["eff_neff"].get(sensor, 1.0)),
                    mapping,
                    degraded_resolution,
                )
                evaluation_hours = duration + 48.0
                duration_value, duration_unit = duration, "h"
            elif fault == "linear_drift":
                duration = 12.0 + 156.0 * float(point[1])
                drift_result = _drift_trial(
                    state,
                    models[sensor],
                    peers[sensor],
                    sensor,
                    onset,
                    amplitude,
                    duration,
                    direction,
                    sensor_precision * 2.0 if degraded_resolution else None,
                )
                result = drift_result[:5]
                common_process_alarm = drift_result[5]
                evaluation_hours = duration + 12.0
                duration_value, duration_unit = duration, "h"
            else:
                duration = 15 + int(np.floor((1440 - 15) * point[1]))
                result = _freeze_trial(
                    raw[sensor],
                    onset + pd.Timedelta(minutes=15),
                    duration,
                    sensor_precision,
                    degraded_resolution,
                )
                amplitude = np.nan
                evaluation_hours = duration / 60.0
                duration_value, duration_unit = duration, "min"
            rows.append(
                {
                    "trial_id": f"D1V2-{fault}-{trial_no:04d}",
                    "fault_type": fault,
                    "sensor_id": sensor,
                    "analyte": analyte,
                    "regime_id": regime,
                    "route": route,
                    "resolution_mode": resolution_mode,
                    "onset": onset,
                    "amplitude_sigma": amplitude,
                    "direction": direction,
                    "duration": duration_value,
                    "duration_unit": duration_unit,
                    "blank_statistic": result[0],
                    "injected_statistic": result[1],
                    "blank_alarm": result[2],
                    "detected": result[3],
                    "detection_delay": result[4],
                    "common_process_alarm": common_process_alarm,
                    "evaluation_hours": evaluation_hours,
                    "injection_domain": (
                        "original_measurement_scale_with_frozen_training_route_projection"
                    ),
                    "analysis_unit": "independent_injection_episode",
                    "valid_evaluation": bool(
                        np.isfinite(result[0]) and np.isfinite(result[1])
                    ),
                }
            )
    trials = pd.DataFrame(rows)
    summary, stratified = _summaries(trials)
    design_audit = (
        trials.groupby(
            ["fault_type", "analyte", "regime_id", "route", "resolution_mode"],
            as_index=False,
        )
        .agg(
            n_trials=("trial_id", "size"),
            distinct_sensors=("sensor_id", "nunique"),
            distinct_onsets=("onset", "nunique"),
            amplitude_min=("amplitude_sigma", "min"),
            amplitude_max=("amplitude_sigma", "max"),
            duration_min=("duration", "min"),
            duration_max=("duration", "max"),
            n_evaluable=("valid_evaluation", "sum"),
        )
    )
    excluded = trials.loc[~trials["valid_evaluation"]].copy()
    if not excluded.empty:
        excluded["exclusion_reason"] = "nonfinite_local_evaluation_statistic"
    outputs = {
        "D1_injection_trials": trials,
        "D1_injection_summary": summary,
        "D1_injection_stratified": stratified,
        "D1_design_audit": design_audit,
        "D1_excluded_injection_trials": excluded,
        "D1_existing_peer_model_audit": state["detectors_raw"][
            "pls_peer_selection_audit"
        ].reset_index(),
        "D1_existing_DO24_peer_controls": state["detectors_raw"][
            "pls_do24_injection_scenarios"
        ].copy(),
        "D1_existing_DO24_peer_control_summary": state["detectors_raw"][
            "pls_do24_injection_summary"
        ].copy(),
    }
    for name, frame in outputs.items():
        frame.to_parquet(output_dir / f"{name}.parquet", index=False)
    return outputs
